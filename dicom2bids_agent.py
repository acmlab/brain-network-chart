#!/usr/bin/env python3
"""
dicom2bids_agent.py  ──  DICOM → BIDS 自动转换 + LLM Agent 分类 + HTML 报告

用法:
  python3 dicom2bids_agent.py                          # 使用内置默认目录
  python3 dicom2bids_agent.py <data_dir> <output_dir>  # 自定义目录

与 dicom2bids.py 的区别：
  序列分类由硬编码正则规则替换为 LLM agent 判断（通过 Ollama 本地运行）。
  所有唯一序列名并发发送给 agent，失败时自动回退到原始正则规则。
"""

from __future__ import annotations
import sys, os, json, re, subprocess, shutil, asyncio
from pathlib import Path
from datetime import datetime

# Force UTF-8 output on Windows (avoids UnicodeEncodeError for → ✓ etc.)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import httpx

# ─── 路径配置 ─────────────────────────────────────────────────────────────────

DATA_DIR   = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/ram/USERS/tao/code/new/data")
OUTPUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/ram/USERS/tao/code/new/bids_output")
CONFIG_PATH = OUTPUT_DIR / "dcm2bids_config.json"
REPORT_PATH = OUTPUT_DIR / "conversion_report.html"

# ─── Agent / Ollama 配置 ──────────────────────────────────────────────────────
# 使用 Ollama 原生 /api/chat 接口，支持 think=False 避免 qwen3 思考 token 超限

OLLAMA_HOSTS = [
    "localhost:11434",
    "yukon.acm.unc.edu:11434",
]
MODEL_NAME = "qwen3:latest"   # 8B 通用模型，结构化输出能力强；think=False 避免 token 超限

# ─── 工具查找 ─────────────────────────────────────────────────────────────────

_EXTRA_BIN = Path('/'.join(sys.executable.split('/')[:-1]))

def find_tool(name: str) -> str | None:
    p = shutil.which(name)
    if p:
        return p
    candidate = _EXTRA_BIN / name
    return str(candidate) if candidate.exists() else None

# ─── 正则分类规则（Agent 失败时的 Fallback） ──────────────────────────────────

RULES = [
    # ── Skip: scouts / localizers / derived images ───────────────────────────
    (r'(?i)(localiz|3-pl|scano|center.at|scout|\bloc\b|AAHScout)',     None,    None),
    (r'(?i)(MoCoSeries|Perfusion_Weighted)',                            None,    None),  # aux/derived
    (r'(?i)RSBrainStem',                                               None,    None),  # ASL prep 4D
    # Derived DWI maps: must check BEFORE generic dwi/dti rule
    (r'(?i)(diffusion_(adc|fa|trace|lowb|exp|color)|mip|colfa)',       None,    None),
    (r'(?i)TRACE[\s_]P\d',                                             None,    None),  # DIFFUSION TRACE P2
    (r'(?i)(_|\b)(ADC|FA|TRACEW|TRACEW|EXP|LOWB|ColorFA|ColFA)(\b|$)',None,    None),
    # ── perf/asl ─────────────────────────────────────────────────────────────
    (r'(?i)(pasl|pcasl|\bcasl\b|arterial[\s_]spin)',                   'perf',  'asl'),
    # ── dwi/sbref: b=0 only acquisitions ─────────────────────────────────────
    (r'(?i)(b[\s=_]?0[\s_-]*(scans?|acqs?|ref)|dti[\s_]*b[\s=_]?0\b)','dwi',  'sbref'),
    # ── fmap ─────────────────────────────────────────────────────────────────
    (r'(?i)phase.?diff',                                               'fmap',  'phasediff'),
    (r'(?i)(field.?map|b0.?map|fmap)',                                 'fmap',  'phasediff'),
    (r'(?i)(se_fs_(pa|ap)|blip.?(up|down)|spin.?echo.?field)',          'fmap',  'epi'),
    (r'(?i)(mag.*echo.?2|echo.?2.*mag)',                               'fmap',  'magnitude2'),
    (r'(?i)(mag.*echo.?1|echo.?1.*mag|magnitude)',                     'fmap',  'magnitude1'),
    # ── anat ─────────────────────────────────────────────────────────────────
    (r'(?i)(swi|susceptib)',                                           'anat',  'T2starw'),
    (r'(?i)(mprage|mp.rage|ir.fspgr|bravo)',                           'anat',  'T1w'),
    (r'(?i)flair',                                                     'anat',  'FLAIR'),  # before T2
    (r'(?i)(t2.fse|fse|t2.tse)',                                       'anat',  'T2w'),
    (r'(?i)(t2.ge|ge.t2|t2.gre|t2\*)',                                'anat',  'T2starw'),
    (r'(?i)t2',                                                        'anat',  'T2w'),
    (r'(?i)t1',                                                        'anat',  'T1w'),
    # ── dwi (raw multi-direction only) ───────────────────────────────────────
    (r'(?i)(dwi|dti|diffusion|advdiff|ep2d.*(diff|dir))',              'dwi',   'dwi'),
    # ── func / other ─────────────────────────────────────────────────────────
    (r'(?i)(bold|fmri|resting|rest|RSWholeBrain)',                     'func',  'bold'),
    (r'(?i)(fgre|gre)',                                                'anat',  'T1w'),
]

def classify(desc: str) -> tuple[str | None, str | None]:
    """正则分类，返回 (datatype, suffix)，(None, None) 表示跳过"""
    for pat, dt, sfx in RULES:
        if re.search(pat, desc):
            return dt, sfx
    return 'anat', 'T1w'

# ── Pre-check: high-confidence deterministic rules applied BEFORE LLM ────────
# Returns a full result dict if we're confident; None defers to LLM.

_PRE_SKIP_RE = re.compile(
    r'(?i)('
    r'(_|\b)(ADC|TRACEW|ColorFA|ColFA|EXP|LOWB)(\b|$)'   # derived DWI maps (FA handled separately)
    r'|(?<![A-Za-z])FA(?![A-Za-z])'                       # standalone FA (not e.g. "FLASH")
    r'|TRACE[\s_]P\d'                                     # DIFFUSION TRACE P2
    r'|MoCoSeries|Perfusion_Weighted'                     # aux/derived
    r'|RSBrainStem'                                       # ASL regional saturation prep (4D)
    r'|AAHScout'                                          # GE scout
    r'|\brel[CT]?BF\b'                                    # relative/absolute CBF perfusion map (derived ASL)
    r'|\bCBF\b'                                           # cerebral blood flow map (derived ASL)
    r')'
)
_PRE_SBREF_RE = re.compile(
    r'(?i)(b[\s=_]?0[\s_-]*(scans?|acqs?|ref\b)|dti[\s_]*b[\s=_]?0\b)'
)
_PRE_ASL_RE = re.compile(r'(?i)(pASL|pcasl|\bCASL\b|arterial[\s_]spin)')
_PRE_FLAIR_RE = re.compile(r'(?i)\bflair\b')
_PRE_LOCALIZER_RE = re.compile(r'(?i)(localiz|3-pl|scano|center.at|\bscout\b|AAHScout)')

# Path-hint: extract modality directory name from file path
_PATH_HINT_RE = re.compile(
    r'(?i)[/\\](?P<mod>T1W?|T2W?|DT[1I]|DWI|F?MRI|BOLD|FLAIR|ASL|PERF|SWI|ANGIO|PDW?)(?=[/\\])'
)

def _extract_path_hint(path: str) -> str | None:
    """Return the first modality-named directory component found in a path."""
    m = _PATH_HINT_RE.search(path)
    return m.group('mod').upper() if m else None


def _precheck_classify(desc: str, path_hint: str | None = None) -> dict | None:
    """High-confidence pre-classification before LLM. Returns result or None."""
    # Priority 1: always-skip (derived maps, auxiliary — not overrideable by path)
    if _PRE_SKIP_RE.search(desc):
        return {"skip": True, "datatype": None, "suffix": None, "task": None,
                "reason": "[precheck] known derived/auxiliary scan → skip"}
    # Priority 2: localizers/scouts inside any directory
    if _PRE_LOCALIZER_RE.search(desc):
        return {"skip": True, "datatype": None, "suffix": None, "task": None,
                "reason": "[precheck] localizer/scout → skip"}
    # Priority 3: high-confidence description patterns
    if _PRE_SBREF_RE.search(desc):
        return {"skip": False, "datatype": "dwi", "suffix": "sbref", "task": None,
                "reason": "[precheck] b=0 only acquisition → dwi/sbref"}
    if _PRE_ASL_RE.search(desc):
        return {"skip": False, "datatype": "perf", "suffix": "asl", "task": None,
                "reason": "[precheck] arterial spin labeling → perf/asl"}
    if _PRE_FLAIR_RE.search(desc):
        return {"skip": False, "datatype": "anat", "suffix": "FLAIR", "task": None,
                "reason": "[precheck] FLAIR sequence → anat/FLAIR"}
    # Resting-state fMRI by description (eyes open/closed = resting state instruction, not a task)
    if re.search(r'(?i)(eyes.?open|eyes.?closed)', desc) and re.search(r'(?i)(fmri|bold|func|epi)', desc):
        return {"skip": False, "datatype": "func", "suffix": "bold", "task": "rest",
                "reason": "[precheck] Eyes Open/Closed resting-state fMRI → func/bold rest"}
    # Priority 4: path-hint for unambiguous modality directories
    if path_hint:
        ph = path_hint.upper()
        if ph in ('DT1', 'DTI', 'DWI'):
            return {"skip": False, "datatype": "dwi", "suffix": "dwi", "task": None,
                    "reason": f"[precheck] dir={path_hint} → dwi/dwi"}
        if ph in ('FMRI', 'MRI', 'BOLD'):
            if re.search(r'(?i)(rest|rsfmri|resting|eyes.?open|eyes.?closed)', desc):
                return {"skip": False, "datatype": "func", "suffix": "bold", "task": "rest",
                        "reason": f"[precheck] dir={path_hint} + rest/eyes → func/bold rest"}
            # Non-rest fMRI: let LLM determine the proper task label to avoid 'task-task'
    return None

def safe_label(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]', '', s)[:20] or 'seq'

# ─── LLM Agent 分类 ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a neuroimaging expert classifying MRI series for the BIDS standard.

BIDS organizes only RAW scanner acquisitions — signals directly measured by the MRI hardware.

── STEP 1: Is this a SCOUT / LOCALIZER / DERIVED image? → skip=true ─────────────────────────
Skip these (not raw BIDS data):
• Scouts and localizers: acquired at the very start for patient positioning. They are
  multi-plane or low-resolution orientation images with no diagnostic quality. Clues:
  "3-plane", multi-orientation in a single series, "center at [landmark]", very short scan time.
  "Scano" is a GE manufacturer abbreviation for scanner localizer/scout → skip.
• Derived / post-processed images: computed from raw data AFTER acquisition. Examples:
  ADC maps, FA maps, trace images, color FA, low-b images — all derived from raw DWI.
  MIP/mIP/minIP — intensity projections derived from raw volumes. Always derived regardless of
  what the source data was (e.g., mIP_Images(SW) is still a derived projection, not raw SWI).
  Quantitative maps (T1map, T2map, QSM) generated by offline fitting — skip if reconstructed
  from multiple source images rather than directly sampled from the scanner.
• MoCoSeries — motion correction GRE navigator: NOT diagnostic, skip.
• Perfusion_Weighted — derived perfusion map computed from ASL tag/control subtraction: skip.
• relCBF, CBF, CBV — relative/absolute cerebral blood flow/volume maps derived from ASL: skip.
• RSBrainStem (Regional Saturation brain-stem prep used in ASL protocols): skip.

── STEP 2: BIDS suffix — use MRI physics knowledge ──────────────────────────────────────────
Physics guide for classification:

EchoTime (TE) interpretation — shorter TE favors T1w, longer TE favors T2/T2*:
  TE < 5 ms  → very short, typical of T1-weighted GRE (FGRE, SPGR, FLASH)
  TE 5–30 ms → short, could be T2*-weighted GRE or T1-weighted SE
  TE > 50 ms → long, typical of T2-weighted SE or FLAIR
  TE > 100 ms → very long, T2w or FLAIR

Trust the explicit contrast in the series name when present:
  Series starting with "T1" (e.g., "T1 SE SAG", "t1_fl2d") → T1-weighted, regardless of TE
  Series starting with "T2" with SE/FSE/TSE → T2-weighted spin echo
  Series starting with "T2" with GE/GRE and TE > 10ms → T2*-weighted gradient echo

  How to distinguish raw DWI from derived DWI maps:
  • Raw DWI acquisition: describes ACQUISITION PARAMETERS — number of directions, b-value,
    voxel size, repetitions. Name parts: "40dir", "1300b", "2.5mm", "DTI", "DWI", "DIFFUSION".
    These go in BIDS as dwi/dwi.
  • Derived DWI scalar maps: describe a COMPUTED QUANTITY derived from the raw acquisition.
    The map type is a mathematical/physical measure: ADC (apparent diffusion coefficient),
    FA (fractional anisotropy), TRACEW (trace-weighted), EXP (exponential ADC), LOWB
    (low-b reference), ColorFA (color-coded FA). These should be SKIPPED.
  Rule: if the name contains only acquisition parameters → dwi/dwi. If it contains a
  derived scalar map type (even in compound form like DIFFUSION_ADC, NIFDDTIb100027mm3FA,
  NIFDDTIb100027mm3TRA) → skip. Key: any name ending in FA, TRA, TRACEW, ADC, EXP, LOWB,
  or containing "ColorFA", "colFA" → ALWAYS skip, regardless of other parameters.

BIDS suffixes:
• anat/T1w     — T1-weighted: MPRAGE, BRAVO, IR-FSPGR, SPGR/FSPGR (spoiled GRE → T1w despite
                 gradient echo readout due to RF spoiling), T1 SE (short TR, short TE spin echo)
• anat/T2w     — True T2: spin-echo readout (SE, FSE, TSE, CUBE). Long TR + long TE.
• anat/T2starw — T2*: gradient-echo with long TE (>10 ms) or explicit T2* design. SWI uses
                 phase + magnitude GRE → T2starw.
• anat/FLAIR   — Fluid-attenuated inversion recovery. Very long TE + inversion pulse.
• anat/PDw     — Proton density: long TR, short-to-intermediate TE, minimal T1/T2 weighting.
• dwi/dwi      — Raw multi-direction diffusion acquisition. NOT derived maps.
• dwi/sbref    — b=0 reference scan for DWI: a separate b=0 acquisition with NO diffusion
                 gradient applied. Clues: "b0scan", "b0ref", "DTIb0", "b0 only" in name, or
                 a DWI series explicitly noted as b=0 only (no gradient directions listed).
                 These do NOT have .bvec/.bval files — that is expected for sbref.
• perf/asl     — Arterial Spin Labeling perfusion MRI. Clues: "pASL", "pCASL", "CASL",
                 "ASL", "perfusion", "spin labeling" in the series name. ASL data is 4D
                 (tag/control pairs). Do NOT classify ASL as T1w or any anat suffix.
• perf/m0scan  — M0 equilibrium reference scan for ASL scaling. Clues: "M0", "M0scan",
                 "proton density" acquired as part of an ASL protocol.
• func/bold    — Functional EPI measuring BOLD signal. Infer the BIDS task label from the
                 description: "rsfMRI", "resting", "rest", "Eyes Open" → "rest";
                 task names like "n-back", "working memory", "faces" → short alphanumeric label.
• fmap/phasediff  — Phase difference image from a dual-echo GRE field mapping acquisition.
                    Clues: "phasediff", "phase difference", "phase_diff", two echoes mentioned.
                    Physics: the scanner subtracts phase images at TE1 and TE2 to get a B0 map.
• fmap/magnitude1 — Magnitude image of the FIRST (shorter TE) echo from dual-echo GRE field map.
                    Clues: "magnitude", "mag", "echo1", "e1", or "TE1" paired with field mapping.
• fmap/magnitude2 — Magnitude image of the SECOND (longer TE) echo from dual-echo GRE field map.
                    Clues: "magnitude", "mag", "echo2", "e2", or "TE2" paired with field mapping.
• fmap/fieldmap   — A pre-computed B0 field map in units of Hz.
                    Clues: explicit "Hz", "fieldmap", "B0 map" in name.
• fmap/epi        — EPI-based B0 field map using reversed phase-encode direction (blip-up/blip-down).
                    Clues: "SE_FS_PA", "SE_FS_AP", "SpinEchoFieldMap", "blip", "reversed PE", "spin echo field map",
                    same EPI contrast as bold but acquired for distortion correction.

  NOTE: Dual-echo GRE field maps often come as a set of 3 series (magnitude1, magnitude2,
  phasediff). If only "fieldmap" or "GRE_FIELD_MAP" appears without echo info, classify as
  fmap/phasediff (most common) unless there is explicit evidence of magnitude images.
  B0 field maps are NOT localizers and NOT derived images — they are raw field-measurement
  acquisitions intended to correct distortion in EPI sequences.

── ParentDir hint ───────────────────────────────────────────────────────────────────────────
If a "ParentDir" field is provided it is the name of the modality-named directory that
contains this scan in the dataset (e.g. DT1, T1W, fMRI). Use it as a strong contextual hint:
  ParentDir=DT1 or DTI or DWI → expect dwi/dwi (unless description reveals a derived map)
  ParentDir=fMRI or BOLD      → expect func/bold
  ParentDir=T1W or T1         → expect anat/T1w
  ParentDir=FLAIR             → expect anat/FLAIR
Derived-map rules (Step 1) always override ParentDir — a FA map is still skip even in a DTI dir.

── OUTPUT ────────────────────────────────────────────────────────────────────────────────────
Return ONLY a single JSON object, no markdown, no extra text:
{"skip": <bool>, "datatype": <string|null>, "suffix": <string|null>, "task": <string|null>, "reason": "<one sentence of medical reasoning>"}
When skip=true: set datatype=null, suffix=null, task=null.
When datatype="func": set "task" to the BIDS task label (alphanumeric only, e.g. "rest", "nback"). For all other datatypes: task=null."""

def _extract_json(raw: str) -> str | None:
    """从模型输出中提取最后一个完整 JSON 对象（正确处理嵌套括号）"""
    depth, start, last_json = 0, None, None
    for i, ch in enumerate(raw):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                last_json = raw[start:i + 1]
    return last_json

async def call_classify_agent(http: httpx.AsyncClient, host: str,
                              desc: str, meta: dict) -> dict:
    """调用 Ollama /api/chat 分类单个序列，返回 {skip, datatype, suffix, reason}"""
    lines = [
        f"SeriesDescription: {desc}",
        f"MRAcquisitionType: {meta.get('acq_type', '')}",
        f"EchoTime(ms): {meta.get('echo_time', 0):.1f}",
        f"RepetitionTime(ms): {meta.get('tr', 0):.1f}",
    ]
    if hint := meta.get("path_hint"):
        lines.append(f"ParentDir: {hint}")
    user = "\n".join(lines)
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 250},
    }
    resp = await http.post(f"http://{host}/api/chat", json=payload, timeout=30)
    resp.raise_for_status()
    raw = resp.json()["message"]["content"].strip()
    candidate = _extract_json(raw)
    if not candidate:
        raise ValueError(f"no JSON in response: {raw[:200]!r}")
    result = json.loads(candidate)
    # 校验必要字段
    assert isinstance(result.get("skip"), bool), "skip must be bool"
    if not result["skip"]:
        _VALID_PAIRS = {
            "anat": {"T1w","T2w","T2starw","FLAIR","PDw","T1map","T2map","T2starmap","angio","MP2RAGE","MEGRE"},
            "dwi":  {"dwi","sbref"},
            "func": {"bold","cbv","sbref"},
            "fmap": {"phasediff","magnitude1","magnitude2","fieldmap","epi","TB1map","RB1map"},
            "perf": {"asl","m0scan"},
        }
        dt  = result.get("datatype")
        sfx = result.get("suffix")
        assert dt in _VALID_PAIRS, f"invalid datatype: {dt!r}"
        # 大小写归一化：允许模型返回 "flair"/"bold" 等大小写不一致的后缀
        sfx_norm = next((s for s in _VALID_PAIRS[dt] if s.lower() == (sfx or "").lower()), sfx)
        result["suffix"] = sfx_norm
        assert sfx_norm in _VALID_PAIRS[dt], f"suffix {sfx!r} not valid for datatype {dt!r}"
    return result

async def _try_hosts(http: httpx.AsyncClient, desc: str, meta: dict) -> dict:
    """依次尝试各 Ollama 主机，全部失败时回退到正则分类"""
    # High-confidence pre-check: bypass LLM for known patterns
    precheck = _precheck_classify(desc, meta.get("path_hint"))
    if precheck:
        return precheck
    last_err = None
    for host in OLLAMA_HOSTS:
        try:
            return await call_classify_agent(http, host, desc, meta)
        except Exception as e:
            last_err = e
    # Fallback
    dt, sfx = classify(desc)
    return {
        "skip":     dt is None,
        "datatype": dt,
        "suffix":   sfx,
        "reason":   f"[fallback] {last_err}",
    }

async def classify_all(
    unique_series: list[tuple[str, dict]]
) -> dict[str, dict]:
    """
    并发分类所有唯一序列，返回 {description: agent_result} 缓存字典。
    限制并发数以避免 Ollama 服务器过载导致输出质量下降。
    """
    sem = asyncio.Semaphore(8)

    async def _bounded(desc: str, meta: dict) -> dict:
        async with sem:
            return await _try_hosts(http, desc, meta)

    async with httpx.AsyncClient(timeout=60) as http:
        tasks = [_bounded(desc, meta) for desc, meta in unique_series]
        results = await asyncio.gather(*tasks)
    return {desc: res for (desc, _), res in zip(unique_series, results)}

# ─── 数据集布局发现（统一 Agent） ─────────────────────────────────────────────

_DATE_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})')

_LAYOUT_PROMPT = """You are analyzing a medical imaging research dataset directory tree.
Produce a layout description to automate DICOM→BIDS conversion.

──── A. SUBJECT ORGANIZATION ────────────────────────────────────────────────
CRITICAL DISTINCTION — modality_grouped vs subject_toplevel:

modality_grouped=TRUE only when:
  • Top-level directories are named after IMAGING TYPES: T1, T2, DTI, DWI, fMRI,
    BOLD, FLAIR, ASL, T1W, DT1, fMRI, PET, etc.
  • The SAME subject ID appears under MULTIPLE top-level modality dirs.
  Example: dataset/T1/sub-001/... AND dataset/DTI/sub-001/... AND dataset/fMRI/sub-001/...

modality_grouped=FALSE (subject_toplevel) when:
  • Top-level directories ARE the subjects: patient codes, participant IDs,
    numeric IDs, alphanumeric study IDs (e.g. mri127, neo-0038-1-1, sub-001).
  • Each top-level dir belongs to exactly ONE subject.
  RULE: If top-level dir names do NOT match imaging-type keywords, set modality_grouped=false.

──── B. SESSION STRUCTURE ───────────────────────────────────────────────────
has_sessions=true when subjects have MULTIPLE time points / visits:
  - date dirs:     subjectDir/series/2007-02-27_09:41/scan_id/*.dcm
  - named visits:  subjectDir/14year/... or subjectDir/baseline/... or subjectDir/visit1/...
has_sessions=false: single acquisition, no session level.

──── C. DICOM SOURCE TYPE ───────────────────────────────────────────────────
  • dcm_dir:    directories with .dcm files
  • no_ext_dir: directories with DICOM files with NO file extension
  • zip:        .zip archive files  (dcm2bids reads them directly as -d)
  • tgz:        .tgz / .tar.gz archive files  (dcm2bids reads them directly as -d)
  • mixed:      combination

──── OUTPUT ─────────────────────────────────────────────────────────────────
Return ONLY valid JSON, no markdown:
{
  "modality_grouped": <bool>,
  "has_sessions": <bool>,
  "subject_glob": "<glob from dataset root (if not modality_grouped) OR from each modality dir (if modality_grouped) to reach subject-ID directories>",
  "session_glob": "<glob from subject dir to session dirs; '' if has_sessions=false>",
  "session_label_from": "date" | "dirname" | "suffix",
  "dicom_glob": "<glob from session/subject dir to DICOM sources; '' means the dir itself is the DICOM root>",
  "dicom_type": "dcm_dir" | "no_ext_dir" | "zip" | "tgz" | "mixed",
  "notes": "<one sentence>"
}

session_label_from:
  "date"    — YYYYMMDD extracted from dir name  (2007-02-27_... → 20070227)
  "dirname" — full dir name cleaned to alphanumeric
  "suffix"  — last '-'-separated part  (neo-0038-1-1-14year → 14year)

dicom_glob examples:
  ""            — pass the session/subject dir itself to dcm2bids
  "DICOM/*.tgz" — .tgz archives inside a DICOM/ subdirectory
  "DICOM/*.zip" — .zip archives inside a DICOM/ subdirectory"""


def _build_dataset_tree(data_dir: Path, max_top: int = 5,
                        max_depth: int = 6, max_children: int = 4) -> str:
    """Build compact tree with file-type summaries at leaves."""
    lines = [f"[Dataset root: {data_dir.name}/]"]
    try:
        top_dirs = sorted(d for d in data_dir.iterdir() if d.is_dir())
    except PermissionError:
        return f"[Cannot read {data_dir}]"

    def walk(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir())
        except PermissionError:
            return
        dirs  = [e for e in entries if e.is_dir()]
        files = [e for e in entries if e.is_file()]
        indent = "  " * depth
        if files:
            cnt: dict[str, int] = {}
            for f in files:
                ext = f.suffix.lower() or "(no ext)"
                cnt[ext] = cnt.get(ext, 0) + 1
            top = sorted(cnt.items(), key=lambda x: -x[1])[:3]
            lines.append(f"{indent}[{len(files)} files: {', '.join(f'{v}×{k}' for k, v in top)}]")
        for d in dirs[:max_children]:
            lines.append(f"{indent}{d.name}/")
            walk(d, depth + 1)
        if len(dirs) > max_children:
            lines.append(f"{indent}... ({len(dirs) - max_children} more dirs)")

    for d in top_dirs[:max_top]:
        lines.append(f"  {d.name}/")
        walk(d, 2)
    if len(top_dirs) > max_top:
        lines.append(f"  ... ({len(top_dirs) - max_top} more top-level dirs, same structure)")
    return "\n".join(lines)


_MODALITY_KEYWORDS = {
    't1', 't2', 't1w', 't2w', 'dti', 'dwi', 'fmri', 'bold', 'flair',
    'asl', 'pet', 'dt1', 'swi', 'anat', 'func', 'perf', 'adc', 'fa',
}

def _heuristic_layout(data_dir: Path) -> dict:
    """Filesystem-based layout heuristic used when the LLM fails to return JSON."""
    top_dirs = [d for d in data_dir.iterdir() if d.is_dir()]
    if not top_dirs:
        return {"modality_grouped": False, "has_sessions": False,
                "subject_glob": "*", "session_glob": "", "session_label_from": "dirname",
                "dicom_glob": "", "dicom_type": "dcm_dir", "notes": "heuristic fallback"}

    # Detect modality_grouped: majority of top dirs match imaging-type keywords
    n_modality = sum(
        1 for d in top_dirs
        if any(k in d.name.lower() for k in _MODALITY_KEYWORDS)
    )
    is_modality_grouped = n_modality >= max(1, len(top_dirs) // 2)
    # Verify: shared subject IDs across ≥2 top dirs
    if is_modality_grouped and len(top_dirs) >= 2:
        ids_a = {m.name for m in top_dirs[0].glob("*") if m.is_dir()}
        ids_b = {m.name for m in top_dirs[1].glob("*") if m.is_dir()}
        if not (ids_a & ids_b):
            is_modality_grouped = False

    # Detect date-based sessions by recursively searching sample subject directories
    sample_dirs = (top_dirs if not is_modality_grouped
                   else [d for d in sorted(top_dirs[0].glob("*")) if d.is_dir()])
    has_sessions = any(
        _DATE_RE.match(d.name)
        for root in sample_dirs[:3] if root.is_dir()
        for d in root.rglob("*") if d.is_dir() and _DATE_RE.match(d.name)
    )

    return {
        "modality_grouped":   is_modality_grouped,
        "has_sessions":       has_sessions,
        "subject_glob":       "*",
        "session_glob":       "*",
        "session_label_from": "date" if has_sessions else "dirname",
        "dicom_glob":         "",
        "dicom_type":         "dcm_dir",
        "notes":              "heuristic fallback",
    }


async def discover_dataset_layout(data_dir: Path, http: httpx.AsyncClient) -> dict:
    """单次 agent 调用，分析整个数据集布局，失败时返回启发式默认值。"""
    tree = _build_dataset_tree(data_dir)
    # On retry, add a stronger JSON-only instruction
    extra_instructions = [
        "",
        "\n\nCRITICAL: Respond with ONLY the JSON object. No text, no markdown fences. Start immediately with '{'.",
    ]
    last_err = None
    for attempt, extra in enumerate(extra_instructions):
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": _LAYOUT_PROMPT + extra},
                {"role": "user",   "content": f"Analyze this dataset:\n\n{tree}"},
            ],
            "stream": False, "think": False,
            "options": {"temperature": 0, "num_predict": 500},
        }
        for host in OLLAMA_HOSTS:
            try:
                resp = await http.post(f"http://{host}/api/chat", json=payload, timeout=60)
                resp.raise_for_status()
                raw  = resp.json()["message"]["content"].strip()
                cand = _extract_json(raw)
                if not cand:
                    raise ValueError(f"no JSON: {raw[:200]!r}")
                result = json.loads(cand)
                assert isinstance(result.get("modality_grouped"), bool)
                assert isinstance(result.get("has_sessions"), bool)
                # Validate modality_grouped: same subject ID must appear in ≥2 top-level dirs
                # Try fixed depths ("*", "*/*") regardless of agent's subject_glob,
                # since the agent often returns overly specific patterns.
                if result.get("modality_grouped"):
                    top_dirs = [d for d in data_dir.iterdir() if d.is_dir()]
                    if len(top_dirs) < 2:
                        # Only one top-level dir: impossible to have multiple modality groups
                        result["modality_grouped"] = False
                        result["subject_glob"] = "*"
                        print("  [layout correction] only 1 top-level dir → subject_toplevel")
                    elif len(top_dirs) >= 2:
                        found_shared = False
                        for test_sg in ["*", "*/*"]:
                            ids_a = {m.name for m in top_dirs[0].glob(test_sg) if m.is_dir()}
                            ids_b = {m.name for m in top_dirs[1].glob(test_sg) if m.is_dir()}
                            n = len(ids_a & ids_b)
                            if n >= 2:
                                # Clear consensus: multiple shared IDs at this depth
                                result["subject_glob"] = test_sg
                                if test_sg != (result.get("subject_glob") or "*"):
                                    print(f"  [layout correction] subject_glob set to"
                                          f" '{test_sg}' ({n} subjects)")
                                found_shared = True
                                break
                            elif n == 1 and test_sg == "*":
                                # Only 1 shared at shallow level — try deeper before deciding
                                continue
                        # Fallback for single-subject modality_grouped datasets
                        if not found_shared:
                            ids_a0 = {m.name for m in top_dirs[0].glob("*") if m.is_dir()}
                            ids_b0 = {m.name for m in top_dirs[1].glob("*") if m.is_dir()}
                            if ids_a0 & ids_b0:
                                result["subject_glob"] = "*"
                                found_shared = True
                        if not found_shared:
                            result["modality_grouped"] = False
                            result["subject_glob"] = "*"
                            print("  [layout correction] no shared IDs across top-level dirs"
                                  " → subject_toplevel")
                print(f"  [layout] modality_grouped={result['modality_grouped']}, "
                      f"has_sessions={result['has_sessions']}, "
                      f"dicom_type={result.get('dicom_type')}")
                print(f"  [layout] {result.get('notes', '')}")
                return result
            except Exception as e:
                last_err = e
    print(f"  [layout heuristic fallback] agent failed: {last_err}")
    result = _heuristic_layout(data_dir)
    print(f"  [layout] modality_grouped={result['modality_grouped']}, "
          f"has_sessions={result['has_sessions']}, dicom_type={result.get('dicom_type')}")
    print(f"  [layout] {result.get('notes', '')}")
    return result


def _ses_label(dirname: str, label_from: str) -> str:
    if label_from == "date":
        m = _DATE_RE.match(dirname)
        return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else safe_label(dirname)
    elif label_from == "suffix":
        parts = dirname.split("-")
        return safe_label(parts[-1]) if len(parts) > 1 else safe_label(dirname)
    return safe_label(dirname)


def extract_subjects(data_dir: Path, layout: dict) -> list[tuple[str, list[Path]]]:
    """根据布局提取 (subject_id, [subject_roots])，modality_grouped 时聚合多根。"""
    subject_glob = layout.get("subject_glob") or "*"
    if layout.get("modality_grouped"):
        sid_roots: dict[str, list[Path]] = {}
        for top_dir in sorted(d for d in data_dir.iterdir() if d.is_dir()):
            for match in sorted(top_dir.glob(subject_glob)):
                if match.is_dir():
                    sid_roots.setdefault(match.name, []).append(match)
        if not sid_roots and subject_glob != "*":
            print(f"  [subject fallback] '{subject_glob}' found nothing, trying '*'")
            for top_dir in sorted(d for d in data_dir.iterdir() if d.is_dir()):
                for match in sorted(top_dir.glob("*")):
                    if match.is_dir():
                        sid_roots.setdefault(match.name, []).append(match)
        return sorted(sid_roots.items())
    subjects = []
    for match in sorted(data_dir.glob(subject_glob)):
        if match.is_dir():
            subjects.append((match.name, [match]))
    if not subjects and subject_glob != "*":
        print(f"  [subject fallback] '{subject_glob}' found nothing, trying '*'")
        for match in sorted(data_dir.glob("*")):
            if match.is_dir():
                subjects.append((match.name, [match]))
    return subjects


def get_dicom_sources(base_dir: Path, dicom_glob: str) -> list[Path]:
    """从 session 或 subject 目录获取传给 dcm2bids -d 的路径列表。"""
    if not dicom_glob:
        return [base_dir]
    sources = sorted(base_dir.glob(dicom_glob))
    if not sources:
        # If the specific archive extension matches nothing, try other archive types
        # (handles datasets with mixed .tgz and .zip archives)
        g = Path(dicom_glob)
        if g.suffix in _ARCHIVE_EXTS:
            for ext in ('.tgz', '.zip', '.gz', '.bz2'):
                if ext == g.suffix:
                    continue
                alt = sorted(base_dir.glob(str(g.parent / f"*{ext}")))
                if alt:
                    sources = alt
                    break
    return [s for s in sources if s.exists()] or [base_dir]


def get_sessions(subject_roots: list[Path], layout: dict) -> dict[str, list[Path]]:
    """返回 {ses_label: [dicom_sources]}，每个 source 将作为 dcm2bids -d 参数。"""
    label_from = layout.get("session_label_from") or "dirname"
    dicom_glob = layout.get("dicom_glob") or ""
    ses_to_sources: dict[str, list[Path]] = {}

    if label_from == "date":
        # Date-based sessions may be at any depth — rglob to find them robustly
        # (handles both ADNI-style subject/date/ and NIFD-style subject/series/date/)
        for root in subject_roots:
            for d in sorted(root.rglob("*")):
                if d.is_dir() and _DATE_RE.match(d.name):
                    label = _ses_label(d.name, "date")
                    sources = get_dicom_sources(d, dicom_glob)
                    ses_to_sources.setdefault(label, []).extend(sources)
    else:
        # Named sessions (dirname/suffix): use the session_glob from agent
        session_glob = layout.get("session_glob") or "*"
        for root in subject_roots:
            matched = sorted(root.glob(session_glob))
            if not matched and session_glob != "*":
                print(f"  [session fallback] '{session_glob}' found nothing in"
                      f" {root.name}, trying '*'")
                matched = sorted(root.glob("*"))
            for ses_dir in matched:
                if not ses_dir.is_dir():
                    continue
                label = _ses_label(ses_dir.name, label_from)
                sources = get_dicom_sources(ses_dir, dicom_glob)
                ses_to_sources.setdefault(label, []).extend(sources)
    return ses_to_sources

# ─── DICOM 元数据读取 ─────────────────────────────────────────────────────────

_ARCHIVE_EXTS = {'.zip', '.tgz', '.gz', '.bz2'}

def find_series_dirs(root: Path) -> list[Path]:
    """Return directories containing DICOMs, or archive files (.zip/.tgz)."""
    seen: set[Path] = set()
    dirs: list[Path] = []
    # .dcm files
    for f in sorted(root.glob("**/*.dcm")):
        p = f.parent
        if p not in seen:
            seen.add(p); dirs.append(p)
    # no-extension DICOM files
    if not dirs:
        for f in sorted(root.rglob("*")):
            if f.is_file() and not f.suffix and f.name != 'DICOMDIR' and _is_dicom(f):
                p = f.parent
                if p not in seen:
                    seen.add(p); dirs.append(p)
    # archive files
    for ext in ('.zip', '.tgz', '.gz'):
        for f in sorted(root.rglob(f"*{ext}")):
            if f not in seen:
                seen.add(f); dirs.append(f)
    return dirs

def _is_dicom(path: Path) -> bool:
    try:
        with open(path, 'rb') as f:
            f.seek(128)
            return f.read(4) == b'DICM'
    except Exception:
        return False

def _peek_archive(archive: Path, max_files: int = 5) -> Path | None:
    """Extract a few DICOMs from a zip/tgz to a temp dir for pydicom reading."""
    import tempfile, zipfile, tarfile
    tmpdir = Path(tempfile.mkdtemp(prefix="d2b_"))
    try:
        if archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as z:
                members = [n for n in z.namelist()
                           if n.endswith('.dcm') or ('.' not in Path(n).name and Path(n).name)]
                for m in members[:max_files]:
                    z.extract(m, tmpdir)
        else:  # tgz / gz / bz2
            with tarfile.open(archive) as t:
                members = [m for m in t.getmembers()
                           if m.isfile() and (m.name.endswith('.dcm')
                                              or '.' not in Path(m.name).name)]
                for m in members[:max_files]:
                    t.extract(m, tmpdir)
        return tmpdir if any(tmpdir.rglob("*")) else None
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None

def _read_files_from_source(source: Path) -> tuple[list[Path], str]:
    """Return (dicom_files, rel_label) for a dir or archive source."""
    if source.is_file() and source.suffix in _ARCHIVE_EXTS:
        tmpdir = _peek_archive(source)
        if tmpdir is None:
            return [], source.name
        files = sorted(tmpdir.rglob("*.dcm"))
        if not files:
            files = sorted(f for f in tmpdir.rglob("*") if f.is_file() and not f.suffix)
        return files, source.name
    else:
        files = sorted(source.glob("*.dcm"))
        if not files:
            files = sorted(f for f in source.iterdir()
                           if f.is_file() and not f.suffix and f.name != 'DICOMDIR')
        return files, str(source)

def read_series_info(dicom_roots: list[Path]) -> list[dict]:
    import pydicom
    _TAGS = ['SeriesNumber', 'SeriesDescription', 'MRAcquisitionType',
             'EchoTime', 'RepetitionTime']
    tmp_dirs: list[Path] = []

    def _process_source(source: Path, label: str) -> list[dict]:
        files, _ = _read_files_from_source(source)
        # track extracted tmpdirs for cleanup
        if source.is_file() and source.suffix in _ARCHIVE_EXTS:
            # tmpdir was created inside _peek_archive; clean up after
            pass
        if not files:
            return []
        groups: dict[str, dict] = {}
        for f in files:
            try:
                ds = pydicom.dcmread(str(f), stop_before_pixels=True, specific_tags=_TAGS)
                key = str(getattr(ds, 'SeriesNumber', '0'))
                if key not in groups:
                    groups[key] = {'ds': ds, 'n': 0}
                groups[key]['n'] += 1
            except Exception:
                pass
        result = []
        for key, g in sorted(groups.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
            ds = g['ds']
            scan_num = f"{label}/S{key}" if len(groups) > 1 else label
            result.append({
                "scan_num":    scan_num,
                "description": str(getattr(ds, 'SeriesDescription', '')).strip(),
                "num_files":   g['n'],
                "acq_type":    str(getattr(ds, 'MRAcquisitionType', '')),
                "echo_time":   float(getattr(ds, 'EchoTime', 0) or 0),
                "tr":          float(getattr(ds, 'RepetitionTime', 0) or 0),
                "source_path": str(source),
            })
        return result

    series_list = []
    for source in [s for root in dicom_roots for s in find_series_dirs(root)]:
        owning_root = next((r for r in dicom_roots if source.is_relative_to(r)), dicom_roots[0])
        try:
            rel = str(source.relative_to(owning_root))
        except ValueError:
            rel = source.name
        series_list.extend(_process_source(source, rel))
    return series_list

# ─── 生成 config.json ─────────────────────────────────────────────────────────

def build_config(all_series: list[tuple[str, list[dict]]],
                 cache: dict[str, dict]) -> dict:
    """
    从所有被试序列信息构建 dcm2bids config，分类结果来自 agent cache。
    """
    seen = set()
    descriptions = []
    for _sid, series_list in all_series:
        for s in series_list:
            desc = s["description"]
            if not desc or desc in seen or desc.startswith("[读取失败"):
                continue
            seen.add(desc)

            result = cache.get(desc)
            if result is None or result.get("skip"):
                continue

            dt  = result.get("datatype")
            sfx = result.get("suffix")
            if not dt or not sfx:
                continue

            if dt == "func" and sfx == "bold":
                task = safe_label(result.get("task") or "unknown")
                entities = f"task-{task}"
            else:
                entities = f"acq-{safe_label(desc)}"

            descriptions.append({
                "id":              f"{sfx}_{safe_label(desc)}",
                "datatype":        dt,
                "suffix":          sfx,
                "custom_entities": entities,
                "criteria":        {"SeriesDescription": desc},
            })

    return {"descriptions": descriptions}

# ─── 运行 dcm2bids ────────────────────────────────────────────────────────────

def run_dcm2bids(dcm2bids_bin: str, dcm2niix_bin: str,
                 subject_id: str, scans_roots: list[Path],
                 config_path: Path, output_dir: Path,
                 session_id: str | None = None,
                 cleanup_bids: bool = True) -> subprocess.CompletedProcess:
    if cleanup_bids:
        shutil.rmtree(output_dir / f"sub-{subject_id}", ignore_errors=True)
    # 清理 tmp，防止跨 session sidecar 污染
    # dcm2bids with sessions creates sub-{id}_ses-{ses}; without sessions creates sub-{id}
    tmp_base = output_dir / "tmp_dcm2bids"
    shutil.rmtree(tmp_base / f"sub-{subject_id}", ignore_errors=True)
    if session_id:
        shutil.rmtree(tmp_base / f"sub-{subject_id}_ses-{session_id}", ignore_errors=True)
    env = os.environ.copy()
    env["PATH"] = str(Path(dcm2niix_bin).parent) + ":" + env.get("PATH", "")
    # dcm2bids uses nargs='+' for -d, so all dirs must follow a single -d flag
    cmd = [dcm2bids_bin, "-d"] + [str(r) for r in scans_roots]
    cmd.extend(["-p", subject_id, "-c", str(config_path), "-o", str(output_dir)])
    if session_id:
        cmd.extend(["-s", session_id])
    return subprocess.run(cmd, capture_output=True, text=True, env=env)

# ─── 解析 dcm2bids 配对日志 ───────────────────────────────────────────────────

def parse_pairings(log_text: str) -> tuple[list, list]:
    matched, no_pair = [], []
    for line in log_text.splitlines():
        m = re.search(r'(sub-\S+_\S+)\s+<-\s+(\S+)', line)
        if m:
            matched.append((m.group(1), m.group(2)))
        elif 'No Pairing' in line:
            m2 = re.search(r'No Pairing\s+<-\s+(\S+)', line)
            if m2:
                no_pair.append(m2.group(1))
    return matched, no_pair

def strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

# ─── BIDS 后处理 ──────────────────────────────────────────────────────────────

_TASK_RE = re.compile(r'_task-([A-Za-z0-9]+)_')

def fix_fmap_echoes(output_dir: Path) -> int:
    """
    Rename multi-run phasediff files to proper BIDS fmap names.
    dcm2bids produces _run-01/_run-02/_run-03_phasediff for dual-echo GRE fmaps.
    The correct BIDS names are: magnitude1, magnitude2, phasediff.
    Classifies using EchoNumber + 'P' in ImageType from the sidecar JSON.
    Also injects EchoTime1 / EchoTime2 into the phasediff sidecar.
    """
    fmap_dirs = (list(output_dir.glob("sub-*/fmap"))
                 + list(output_dir.glob("sub-*/ses-*/fmap")))
    fixed = 0
    for fmap_dir in fmap_dirs:
        # Group phasediff JSONs by base key (strip _run-XX suffix)
        groups: dict[str, list[Path]] = {}
        for jf in sorted(fmap_dir.glob("*_phasediff.json")):
            base = re.sub(r'_run-\d+', '', jf.name.replace('_phasediff.json', ''))
            groups.setdefault(base, []).append(jf)

        for base, json_files in groups.items():
            if len(json_files) < 2:
                continue
            # Load and classify each file
            infos = []
            for jf in json_files:
                try:
                    d = json.loads(jf.read_text(encoding='utf-8'))
                except Exception:
                    continue
                infos.append({
                    'path': jf,
                    'data': d,
                    'echo': d.get('EchoNumber', 0),
                    'is_phase': 'P' in (d.get('ImageType') or []),
                    'et': d.get('EchoTime'),
                })
            infos.sort(key=lambda x: (x['is_phase'], x['echo']))

            # Collect echo times for phasediff sidecar
            et1 = next((i['et'] for i in infos if i['echo'] == 1 and not i['is_phase']), None)
            et2 = next((i['et'] for i in infos if i['echo'] == 2 and not i['is_phase']), None)

            for info in infos:
                if info['is_phase']:
                    new_sfx = 'phasediff'
                elif info['echo'] == 1:
                    new_sfx = 'magnitude1'
                elif info['echo'] == 2:
                    new_sfx = 'magnitude2'
                else:
                    continue

                jf = info['path']
                nii = fmap_dir / (jf.name.replace('.json', '.nii.gz'))
                new_json = fmap_dir / f"{base}_{new_sfx}.json"
                new_nii  = fmap_dir / f"{base}_{new_sfx}.nii.gz"

                # Update phasediff sidecar with EchoTime1/EchoTime2
                if new_sfx == 'phasediff' and et1 and et2:
                    d = info['data']
                    d['EchoTime1'] = et1
                    d['EchoTime2'] = et2
                    d.pop('EchoTime', None)
                    jf.write_text(json.dumps(d, indent=4, ensure_ascii=False),
                                  encoding='utf-8')

                if jf != new_json:
                    jf.rename(new_json)
                if nii.exists() and nii != new_nii:
                    nii.rename(new_nii)
                fixed += 1
    return fixed


def fix_sbref_bval(output_dir: Path) -> int:
    """Remove stray *_sbref.bval and *_sbref.bvec files (BIDS does not allow them)."""
    removed = 0
    for ext in ('.bval', '.bvec'):
        for p in output_dir.glob(f"sub-*/**/*_sbref{ext}"):
            p.unlink()
            removed += 1
    return removed


def fix_asl_metadata(output_dir: Path) -> int:
    """Add required BIDS ASL fields to *_asl.json sidecars that are missing them."""
    fixed = 0
    for json_path in output_dir.glob("sub-*/**/*_asl.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        changed = False
        # PostLabelingDelay: use InversionTime if available
        if "PostLabelingDelay" not in data:
            pld = data.get("InversionTime")
            data["PostLabelingDelay"] = float(pld) if pld is not None else 1.8
            changed = True
        # BackgroundSuppression: required bool
        if "BackgroundSuppression" not in data:
            data["BackgroundSuppression"] = False
            changed = True
        # BolusCutOffFlag: required for PASL
        if data.get("ArterialSpinLabelingType") == "PASL" and "BolusCutOffFlag" not in data:
            data["BolusCutOffFlag"] = False
            changed = True
        # RepetitionTimePreparation: use RepetitionTime value
        if "RepetitionTimePreparation" not in data:
            tr = data.get("RepetitionTime")
            if tr is not None:
                data["RepetitionTimePreparation"] = float(tr)
                changed = True
        if changed:
            json_path.write_text(json.dumps(data, indent=4, ensure_ascii=False),
                                 encoding="utf-8")
            fixed += 1
    return fixed


def fix_bold_task_name(output_dir: Path) -> int:
    """Add missing TaskName field to all *_bold.json sidecar files."""
    fixed = 0
    for json_path in output_dir.glob("sub-*/**/*_bold.json"):
        m = _TASK_RE.search(json_path.name)
        if not m:
            continue
        task_name = m.group(1)
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "TaskName" not in data:
            data["TaskName"] = task_name
            json_path.write_text(json.dumps(data, indent=4, ensure_ascii=False),
                                 encoding="utf-8")
            fixed += 1
    return fixed


def fix_fieldmap_units(output_dir: Path) -> int:
    """Add Units='rad/s' to *_fieldmap.json sidecars that are missing it (BIDS required)."""
    fixed = 0
    for json_path in output_dir.glob("sub-*/**/*_fieldmap.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "Units" not in data:
            data["Units"] = "rad/s"
            json_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            fixed += 1
    return fixed


# ─── BIDS 验证 ────────────────────────────────────────────────────────────────

def run_bids_validator(output_dir: Path) -> subprocess.CompletedProcess | None:
    """Run npx bids-validator on the output directory; return None if not available."""
    npx = shutil.which("npx")
    if not npx:
        return None
    # Create .bidsignore to suppress non-BIDS files generated by dcm2bids
    bidsignore = output_dir / ".bidsignore"
    if not bidsignore.exists():
        bidsignore.write_text(
            "conversion_report.html\ndcm2bids_config.json\ntmp_dcm2bids/**\n",
            encoding="utf-8",
        )
    return subprocess.run(
        [npx, "--yes", "bids-validator", str(output_dir)],
        capture_output=True, text=True,
    )

def parse_validator_output(text: str) -> dict:
    """
    Parse bids-validator stdout/stderr into structured dict:
    {
      "issues": [{"type": "ERR"|"WARN", "num": int, "code": str, "desc": str,
                  "files": [str], "more": int}],
      "summary": {"files": str, "size": str, "subjects": str, "sessions": str,
                  "tasks": str, "modalities": str},
      "raw": str,
    }
    """
    text = strip_ansi(text)
    issues: list[dict] = []
    summary: dict = {}

    # Parse issues: lines starting with \t<N>: [ERR|WARN]
    issue_header = re.compile(
        r'^\s+(\d+):\s+\[(ERR|WARN)\]\s+(.*?)\s+\(code:\s*(\d+)\s*-\s*(\w+)\)',
    )
    file_re   = re.compile(r'^\s+\./(.+)')
    more_re   = re.compile(r'^\.\.\. and (\d+) more files')
    cur: dict | None = None

    for line in text.splitlines():
        hm = issue_header.match(line)
        if hm:
            if cur:
                issues.append(cur)
            cur = {
                "type": hm.group(2), "num": int(hm.group(1)),
                "code": hm.group(5), "desc": hm.group(3).strip(),
                "files": [], "more": 0,
            }
            continue
        if cur:
            mm = more_re.search(line)
            if mm:
                cur["more"] = int(mm.group(1))
                continue
            fm = file_re.match(line)
            if fm:
                cur["files"].append(fm.group(1).strip())
    if cur:
        issues.append(cur)

    # Parse summary block (multi-column layout after "Summary:")
    sum_text = ""
    in_sum = False
    for line in text.splitlines():
        if "Summary:" in line:
            in_sum = True
        if in_sum:
            sum_text += " " + line
        if in_sum and "Modalities" in line and ":" in line:
            break

    # Extract individual counters from the summary text
    for pat, key in [
        (r'(\d[\d,]*)\s+Files?,\s+([\d.]+\s*\w+)', None),  # special: "205 Files, 2.56GB"
        (r'(\d+)\s+-\s+Subjects?',   "subjects"),
        (r'(\d+)\s+-\s+Sessions?',   "sessions"),
        (r'(\d+)\s+-\s+Tasks?',      "tasks"),
    ]:
        m = re.search(pat, sum_text, re.IGNORECASE)
        if m and key is None:
            summary["files"] = m.group(1)
            summary["size"]  = m.group(2).strip()
        elif m and key:
            summary[key] = m.group(1)

    # Modalities
    mm = re.search(r'Available Modalities:\s*([\w\s,]+?)(?:\s{4}|$)', sum_text)
    if mm:
        summary["modalities"] = mm.group(1).strip()

    return {"issues": issues, "summary": summary, "raw": text}

# ─── HTML 报告 ────────────────────────────────────────────────────────────────

_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     max-width:1200px;margin:40px auto;padding:0 20px;color:#222}
h1{color:#1a56db;border-bottom:2px solid #1a56db;padding-bottom:8px}
h2{color:#374151;margin-top:36px}h3{color:#4b5563}
.summary{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}
.card{background:#f3f4f6;border-radius:8px;padding:16px 24px;min-width:110px}
.card .num{font-size:2em;font-weight:bold;color:#1a56db}
.card .label{font-size:.85em;color:#6b7280}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.92em}
th{background:#1a56db;color:#fff;padding:8px 12px;text-align:left}
td{padding:7px 12px;border-bottom:1px solid #e5e7eb}
tr:hover td{background:#f9fafb}
.skip{color:#9ca3af;font-style:italic}
.reason{color:#6b7280;font-size:.85em;font-style:italic}
pre{background:#1f2937;color:#e5e7eb;padding:16px;border-radius:6px;
    overflow-x:auto;font-size:.82em;line-height:1.5;white-space:pre-wrap}
.b{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.8em;font-weight:600}
.bg{background:#d1fae5;color:#065f46}.bb{background:#dbeafe;color:#1e40af}
.by{background:#fef3c7;color:#92400e}.br{background:#fee2e2;color:#991b1b}
.bd{background:#f3f4f6;color:#6b7280}.bfb{background:#fce7f3;color:#9d174d}
.ok{color:#059669;font-weight:bold}.err{color:#dc2626;font-weight:bold}
.toc{background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:14px 20px}
.toc a{text-decoration:none;color:#1a56db}.toc a:hover{text-decoration:underline}
details{border:1px solid #e5e7eb;border-radius:6px;margin:6px 0}
details summary{padding:8px 12px;cursor:pointer;font-weight:600;background:#f9fafb;
  border-radius:6px;list-style:none;display:flex;gap:8px;align-items:center}
details[open] summary{border-bottom:1px solid #e5e7eb;border-radius:6px 6px 0 0}
details .files{padding:8px 16px;font-size:.85em;color:#374151;font-family:monospace}
details .files div{padding:2px 0;border-bottom:1px solid #f3f4f6}
"""

def _badge(cls, text):
    return f'<span class="b {cls}">{text}</span>'

def _series_row(s: dict, cache: dict[str, dict]) -> str:
    desc = s["description"]
    if not desc:
        badge = _badge('by', 'No SeriesDescription')
        reason_html = '<span class="reason">(SeriesDescription missing — cannot classify)</span>'
        return (f'<tr><td>{s["scan_num"]}</td><td><em style="color:#999">—</em></td>'
                f'<td>{s["num_files"]}</td><td>{s["acq_type"]}</td>'
                f'<td>{s["echo_time"]:.1f}</td><td>{s["tr"]:.1f}</td>'
                f'<td>{badge}</td><td>{reason_html}</td></tr>')

    result = cache.get(desc)
    if result is None:
        dt, sfx = classify(desc)
        reason = "(unclassified)"
        is_fallback = True
    else:
        dt  = None if result.get("skip") else result.get("datatype")
        sfx = None if result.get("skip") else result.get("suffix")
        reason = result.get("reason", "")
        is_fallback = reason.startswith("[fallback]")

    if dt is None:
        if "derived" in reason or "auxiliary" in reason:
            badge = _badge('bd', 'Skipped (derived/aux)')
        else:
            badge = _badge('bd', 'Skipped (localizer)')
    elif is_fallback:
        badge = _badge('bfb', f'{dt}/{sfx} [fallback]')
    else:
        badge = _badge('bb', f'{dt}/{sfx} acq-{safe_label(desc)}')

    reason_html = f'<span class="reason">{reason}</span>'
    return (f'<tr><td>{s["scan_num"]}</td><td>{desc}</td>'
            f'<td>{s["num_files"]}</td><td>{s["acq_type"]}</td>'
            f'<td>{s["echo_time"]:.1f}</td><td>{s["tr"]:.1f}</td>'
            f'<td>{badge}</td><td>{reason_html}</td></tr>')

def _pairing_rows(matched: list, no_pair: list, series_info: list[dict],
                  cache: dict[str, dict]) -> str:
    skipped_nums: dict[str, str] = {}  # series_num -> skip kind
    for s in series_info:
        result = cache.get(s["description"])
        is_skip = (result is not None and result.get("skip")) or \
                  (result is None and classify(s["description"])[0] is None)
        if is_skip:
            first = s["scan_num"].split("/")[0].lstrip("0") or "0"
            reason = result.get("reason", "") if result else ""
            kind = "derived" if ("derived" in reason or "auxiliary" in reason) else "localizer"
            skipped_nums[first] = kind

    rows = [
        f'<tr><td class="ok">{bids}</td><td>{src}</td><td>{_badge("bg","Matched")}</td></tr>'
        for bids, src in matched
    ]
    for src in no_pair:
        m = re.match(r'^0*(\d+)', src)
        num = m.group(1) if m else ""
        if num in skipped_nums:
            if skipped_nums[num] == "derived":
                label = _badge('bd', 'Derived/aux (skipped)')
            else:
                label = _badge('bd', 'Localizer (skipped)')
        else:
            label = _badge('by', 'Unmatched (check config)')
        rows.append(f'<tr><td class="skip">—</td><td>{src}</td><td>{label}</td></tr>')

    return '\n'.join(rows) or '<tr><td colspan="3">No records</td></tr>'

def _render_validator(vr: dict | None) -> str:
    """Render bids-validator results as an HTML section."""
    if vr is None:
        return '<h2 id="validator">BIDS Validation</h2><p style="color:#6b7280">npx / bids-validator not found, validation skipped.</p>'

    issues = vr.get("issues", [])
    summary = vr.get("summary", {})

    n_err  = sum(1 for i in issues if i["type"] == "ERR")
    n_warn = sum(1 for i in issues if i["type"] == "WARN")

    if n_err == 0 and n_warn == 0:
        status_badge = _badge('bg', '✓ Valid (no issues)')
    elif n_err == 0:
        status_badge = _badge('by', f'⚠ {n_warn} warnings')
    else:
        status_badge = _badge('br', f'✗ {n_err} errors  {n_warn} warnings')

    sum_parts = []
    if summary.get("files"):
        sum_parts.append(f'{summary["files"]} files ({summary.get("size","")})')
    for k, label in [("subjects","subjects"),("sessions","sessions"),("tasks","tasks"),("modalities","modalities")]:
        if summary.get(k):
            sum_parts.append(f'{summary[k]} {label}')
    summary_line = "  |  ".join(sum_parts) if sum_parts else ""

    rows = []
    for iss in issues:
        cls  = "br" if iss["type"] == "ERR" else "by"
        tag  = _badge(cls, iss["type"])
        more = f' <span style="color:#6b7280">… and {iss["more"]} more files</span>' if iss["more"] else ""
        files_html = "".join(f'<div>{f}</div>' for f in iss["files"]) + more
        rows.append(
            f'<details><summary>{tag} &nbsp;'
            f'<span style="color:#6b7280;font-size:.8em">[{iss["code"]}]</span>'
            f' &nbsp;{iss["desc"]}</summary>'
            f'<div class="files">{files_html}</div></details>'
        )

    issues_html = "\n".join(rows) if rows else '<p style="color:#059669">No errors or warnings</p>'
    return f"""<h2 id="validator">BIDS Validation &nbsp;{status_badge}</h2>
<p style="color:#6b7280">{summary_line}</p>
{issues_html}
<details style="margin-top:12px"><summary style="color:#6b7280">Full validator output</summary>
<pre style="margin:0;border-radius:0 0 6px 6px">{vr["raw"]}</pre></details>"""


def generate_report(data_dir: Path, output_dir: Path, config: dict,
                    run_results: list[tuple[str, str | None, list[dict], subprocess.CompletedProcess]],
                    cache: dict[str, dict],
                    validator_result: dict | None = None) -> Path:

    total_matched = total_skipped = 0
    subj_sections = []
    toc = []
    log_blocks = []

    seen_sids: set[str] = set()
    for sid, ses_label, series_info, proc in run_results:
        log_text = strip_ansi((proc.stdout or '') + (proc.stderr or ''))
        matched, no_pair = parse_pairings(log_text)
        total_matched += len(matched)
        total_skipped += len(no_pair)

        rc_cls = 'ok' if proc.returncode == 0 else 'err'
        pairing_rows = _pairing_rows(matched, no_pair, series_info, cache)

        is_first_session = sid not in seen_sids
        seen_sids.add(sid)

        subj_anchor = f"sub-{sid}"
        ses_anchor = f"sub-{sid}" + (f"-ses-{ses_label}" if ses_label else "")

        # Render subject heading + series info only on first occurrence of this subject
        if is_first_session:
            series_rows = '\n'.join(_series_row(s, cache) for s in series_info)
            series_section = f"""<h3>Series Information</h3>
<table>
<tr><th>Series#</th><th>SeriesDescription</th><th>Files</th>
    <th>AcqType</th><th>TE (ms)</th><th>TR (ms)</th><th>Classification</th><th>Agent Reason</th></tr>
{series_rows}
</table>"""
            subj_sections.append(f'<h2 id="{subj_anchor}">Subject: sub-{sid}</h2>\n{series_section}')
            toc.append(f'<a href="#{subj_anchor}">sub-{sid}</a>')

        # Per-session pairing block
        ses_heading = f"Session: ses-{ses_label}" if ses_label else "Pairing Results"
        subj_sections.append(f"""
<h3 id="{ses_anchor}">{ses_heading}</h3>
<table>
<tr><th>BIDS Filename</th><th>Source Sidecar</th><th>Status</th></tr>
{pairing_rows}
</table>
<p>Exit code: <span class="{rc_cls}">{proc.returncode}</span></p>
""")
        log_blocks.append(f'<h3>sub-{sid}' + (f' / ses-{ses_label}' if ses_label else '') + f'</h3><pre>{log_text}</pre>')

    n_subjects = len({sid for sid, *_ in run_results})
    n_nii = len(list(output_dir.glob('sub-*/**/*.nii.gz')))
    all_ok = all(p.returncode == 0 for _, _, _, p in run_results)
    status_badge = _badge('bg', '✓ All OK') if all_ok else _badge('br', '✗ Errors')

    n_fallback = sum(1 for v in cache.values() if v.get("reason", "").startswith("[fallback]"))
    n_missing_desc = sum(
        1 for _, _, series_info, _ in run_results
        for s in series_info if not s.get("description", "").strip()
    )
    if n_missing_desc:
        agent_badge = _badge('br', f'{n_missing_desc} Missing Description')
    elif n_fallback:
        agent_badge = _badge('bfb', f'{n_fallback} Fallback')
    else:
        agent_badge = _badge('bg', 'All Classified')

    vr = validator_result
    n_err  = sum(1 for i in vr["issues"] if i["type"] == "ERR")  if vr else None
    n_warn = sum(1 for i in vr["issues"] if i["type"] == "WARN") if vr else None
    if vr is None:
        valid_badge = _badge('bd', 'Not validated')
    elif n_err == 0:
        valid_badge = _badge('bg', f'✓ Valid ({n_warn} warnings)')
    else:
        valid_badge = _badge('br', f'✗ {n_err} errors  {n_warn} warnings')

    validator_section = _render_validator(vr)
    toc_links = '  |  '.join(toc + ['<a href="#validator">BIDS Validation</a>'])

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>BIDS Conversion Report (Agent)</title><style>{_CSS}</style></head>
<body>
<h1>DICOM → BIDS Conversion Report <small style="font-size:.5em;color:#6b7280">(LLM Agent)</small></h1>
<p style="color:#6b7280">
  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp;
  Data: <code>{data_dir}</code> &nbsp;|&nbsp;
  Output: <code>{output_dir}</code> &nbsp;|&nbsp;
  Model: <code>{MODEL_NAME}</code>
</p>
<div class="summary">
  <div class="card"><div class="num">{n_subjects}</div><div class="label">Subjects</div></div>
  <div class="card"><div class="num">{total_matched}</div><div class="label">Converted</div></div>
  <div class="card"><div class="num">{total_skipped}</div><div class="label">Unmatched</div></div>
  <div class="card"><div class="num">{n_nii}</div><div class="label">NIfTI Files</div></div>
  <div class="card"><div class="num">{status_badge}</div><div class="label">Status</div></div>
  <div class="card"><div class="num">{valid_badge}</div><div class="label">BIDS Valid</div></div>
  <div class="card"><div class="num">{agent_badge}</div><div class="label">Agent</div></div>
</div>

<div class="toc"><strong>Contents:</strong> {toc_links}</div>

{''.join(subj_sections)}

{validator_section}

<h2>Auto-generated config.json</h2>
<pre>{json.dumps(config, ensure_ascii=False, indent=2)}</pre>

<h2>Full Logs</h2>
{''.join(log_blocks)}
</body></html>"""

    REPORT_PATH.write_text(html, encoding='utf-8')
    return REPORT_PATH

# ─── 主流程（异步） ───────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("DICOM → BIDS Auto Conversion (LLM Agent Classification)")
    print("=" * 60)

    # 1. Check tools
    print("\n[1/7] Checking tools ...")
    dcm2bids = find_tool("dcm2bids")
    dcm2niix = find_tool("dcm2niix")
    if not dcm2bids:
        sys.exit("✗ dcm2bids not found; please run install.sh first")
    if not dcm2niix:
        sys.exit("✗ dcm2niix not found; please run install.sh first")
    print(f"  dcm2bids     : {dcm2bids}")
    print(f"  dcm2niix     : {dcm2niix}")
    _npx = shutil.which("npx")
    print(f"  bids-validator: {'npx (' + _npx + ')' if _npx else 'not found (validation will be skipped)'}")

    try:
        import pydicom
    except ImportError:
        sys.exit("✗ pydicom not found; please run install.sh first")

    # 2. Discover dataset layout + subjects
    print(f"\n[2/7] Analyzing dataset structure: {DATA_DIR}")
    async with httpx.AsyncClient(timeout=60) as _http:
        layout = await discover_dataset_layout(DATA_DIR, _http)
    subjects = extract_subjects(DATA_DIR, layout)
    if not subjects:
        sys.exit(f"✗ No subject data found in {DATA_DIR}")
    for sid, roots in subjects:
        roots_str = ", ".join(str(r) for r in roots)
        print(f"  sub-{sid:<12}  →  {roots_str}")

    # 3. Read DICOM metadata
    print(f"\n[3/7] Reading DICOM metadata ...")
    all_series: list[tuple[str, list[dict]]] = []
    for sid, scans_roots in subjects:
        info = read_series_info(scans_roots)
        all_series.append((sid, info))
        print(f"  sub-{sid}: {len(info)} series")

    # 4. Agent batch classification (deduplicated, concurrent)
    print(f"\n[4/7] Agent classifying sequences (model: {MODEL_NAME}) ...")
    desc_meta: dict[str, dict] = {}
    for _sid, series_list in all_series:
        for s in series_list:
            desc = s["description"]
            if desc and desc not in desc_meta and not desc.startswith("[读取失败"):
                desc_meta[desc] = {"acq_type": s["acq_type"],
                                   "echo_time": s["echo_time"],
                                   "tr": s["tr"],
                                   "path_hint": _extract_path_hint(s.get("source_path", ""))}

    unique_list = list(desc_meta.items())
    print(f"  {len(unique_list)} unique series, sending to Agent concurrently ...")

    cache = await classify_all(unique_list)

    n_skip    = sum(1 for v in cache.values() if v.get("skip"))
    n_keep    = len(cache) - n_skip
    n_fallbk  = sum(1 for v in cache.values() if v.get("reason", "").startswith("[fallback]"))
    print(f"  Results: {n_keep} classified / {n_skip} skipped / {n_fallbk} fallback")
    for desc, res in cache.items():
        tag = "skip" if res.get("skip") else f"{res.get('datatype')}/{res.get('suffix')}"
        reason = res.get("reason", "")
        fb = " [FB]" if reason.startswith("[fallback]") else ""
        reason_str = f"  # {reason}" if reason else ""
        print(f"    {desc[:50]:<50}  {tag}{fb}{reason_str}")

    # 5. Write config.json
    config = build_config(all_series, cache)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n[5/7] Config written: {CONFIG_PATH} ({len(config['descriptions'])} rules)")

    desc_file = OUTPUT_DIR / "dataset_description.json"
    if not desc_file.exists():
        desc_file.write_text(json.dumps({
            "Name": "NACC MRI Dataset",
            "BIDSVersion": "1.9.0",
            "DatasetType": "raw"
        }, indent=2), encoding='utf-8')

    ptcp_file = OUTPUT_DIR / "participants.tsv"
    ptcp_file.write_text(
        "participant_id\n" + "\n".join(f"sub-{safe_label(sid)}" for sid, _ in subjects) + "\n",
        encoding='utf-8'
    )

    # 6. 运行 dcm2bids（先清理不属于当前被试列表的旧 sub-* 目录）
    expected_sids = {f"sub-{safe_label(sid)}" for sid, _ in subjects}
    stale = [d for d in OUTPUT_DIR.glob("sub-*") if d.is_dir() and d.name not in expected_sids]
    if stale:
        print(f"\n  [cleanup] Removing {len(stale)} stale subject dirs: {[d.name for d in stale]}")
        for d in stale:
            shutil.rmtree(d)

    print(f"\n[6/7] Running dcm2bids ...")
    run_results: list[tuple[str, str | None, list[dict], subprocess.CompletedProcess]] = []
    for (sid, scans_roots), (_, series_info) in zip(subjects, all_series):
        bids_sid = safe_label(sid)
        if layout.get("has_sessions"):
            sessions = get_sessions(scans_roots, layout)
            print(f"  sub-{bids_sid}: {len(sessions)} sessions (longitudinal)")
            for i, (ses_label, ses_sources) in enumerate(sorted(sessions.items())):
                print(f"    ses-{ses_label} ...", end="", flush=True)
                proc = run_dcm2bids(dcm2bids, dcm2niix, bids_sid, ses_sources,
                                    CONFIG_PATH, OUTPUT_DIR,
                                    session_id=ses_label, cleanup_bids=(i == 0))
                ok = proc.returncode == 0
                matched, _ = parse_pairings((proc.stdout or '') + (proc.stderr or ''))
                print(f"  {'✓' if ok else '✗'}  ({len(matched)} series matched)")
                if not ok:
                    print(strip_ansi(proc.stderr or '')[-300:])
                run_results.append((bids_sid, ses_label, series_info, proc))
        else:
            dicom_glob = layout.get("dicom_glob") or ""
            sources = [s for root in scans_roots for s in get_dicom_sources(root, dicom_glob)]
            print(f"  sub-{bids_sid} ...", end="", flush=True)
            proc = run_dcm2bids(dcm2bids, dcm2niix, bids_sid,
                                sources or scans_roots, CONFIG_PATH, OUTPUT_DIR)
            ok = proc.returncode == 0
            matched, _ = parse_pairings((proc.stdout or '') + (proc.stderr or ''))
            print(f"  {'✓' if ok else '✗'}  ({len(matched)} series matched)")
            if not ok:
                print(strip_ansi(proc.stderr or '')[-300:])
            run_results.append((bids_sid, None, series_info, proc))

    # 7. BIDS validation
    n_bold  = fix_bold_task_name(OUTPUT_DIR)
    n_asl   = fix_asl_metadata(OUTPUT_DIR)
    n_sbref = fix_sbref_bval(OUTPUT_DIR)
    n_fmap  = fix_fmap_echoes(OUTPUT_DIR)
    n_fmunits = fix_fieldmap_units(OUTPUT_DIR)
    fixes = []
    if n_bold:    fixes.append(f"{n_bold} bold.json TaskName added")
    if n_asl:     fixes.append(f"{n_asl} asl.json ASL fields added")
    if n_sbref:   fixes.append(f"removed {n_sbref} sbref.bval/bvec")
    if n_fmap:    fixes.append(f"{n_fmap} fmap files renamed to magnitude1/2+phasediff")
    if n_fmunits: fixes.append(f"{n_fmunits} fieldmap.json Units added")
    if fixes:
        print(f"\n  [post-fix] {' / '.join(fixes)}")

    print(f"\n[7/7] Running bids-validator ...")
    vproc = run_bids_validator(OUTPUT_DIR)
    validator_result: dict | None = None
    if vproc is None:
        print("  npx not found, skipping validation")
    else:
        raw_out = strip_ansi(vproc.stdout + vproc.stderr)
        validator_result = parse_validator_output(raw_out)
        vr = validator_result
        n_err  = sum(1 for i in vr["issues"] if i["type"] == "ERR")
        n_warn = sum(1 for i in vr["issues"] if i["type"] == "WARN")
        sym = "✓" if n_err == 0 else "✗"
        print(f"  {sym}  {n_err} errors, {n_warn} warnings")
        for iss in vr["issues"]:
            label = "[ERR]" if iss["type"] == "ERR" else "[WARN]"
            print(f"    {label} [{iss['code']}] {iss['desc'][:70]}"
                  + (f"  ({len(iss['files'])}+ files)" if iss["files"] else ""))

    report_path = generate_report(DATA_DIR, OUTPUT_DIR, config, run_results, cache,
                                  validator_result=validator_result)

    n_nii = len(list(OUTPUT_DIR.glob("sub-*/**/*.nii.gz")))
    all_ok = all(p.returncode == 0 for _, _, _, p in run_results)

    print(f"\n{'=' * 60}")
    print(f"Done! {'✓ All succeeded' if all_ok else '✗ Errors encountered'}")
    print(f"  NIfTI output: {n_nii} files")
    print(f"  BIDS dir    : {OUTPUT_DIR}")
    print(f"  HTML report : {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
