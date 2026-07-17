import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag


# ============================================================
# CONFIGURATION
# ============================================================

MAX_HTML_SIZE = 100000  # 100KB limit
MAX_OUTPUT_CHARS = 60000  # Default output limit
REQUIRED_ROOT_CLASS = "visualizationCard"

# Default model - change this to your preferred model
DEFAULT_MODEL = "llama3.1:8b"

# Token budgets
MAX_PATCH_TOKENS = 800
MAX_FULL_TOKENS = 4096

logger = logging.getLogger(__name__)


# ============================================================
# DATA CLASSES
# ============================================================


@dataclass
class ValidationResult:
    """Result of HTML validation."""

    valid: bool
    error: Optional[str] = None
    warnings: Optional[List[str]] = None


@dataclass
class VisualizerResponse:
    """External response shape kept for MCP and FastAPI compatibility."""

    status: str  # "success" or "error"
    html: Optional[str] = None
    message: Optional[str] = None
    warnings: Optional[List[str]] = None


class EditIntent(Enum):
    TITLE_CHANGE = "title_change"
    SUBTITLE_CHANGE = "subtitle_change"
    COLOR_CHANGE = "color_change"
    AXIS_LABEL = "axis_label"
    LEGEND_TOGGLE = "legend_toggle"
    DATA_UPDATE = "data_update"
    FONT_SIZE = "font_size"
    ADD_ELEMENT = "add_element"
    REMOVE_ELEMENT = "remove_element"
    LAYOUT_CHANGE = "layout_change"
    STYLE_CHANGE = "style_change"
    COMPLEX = "complex"


@dataclass
class ClassifiedEdit:
    intent: EditIntent
    target_selector: Optional[str] = None
    new_value: Optional[str] = None
    parameters: dict = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class EditResult:
    success: bool
    html: str
    method: str  # "programmatic", "scoped_llm", "full_rewrite", "none"
    changes_description: str
    tokens_used: int = 0


# ============================================================
# PROMPTS
# ============================================================

INTENT_CLASSIFIER_SYSTEM_PROMPT = """You are an edit intent classifier. Given a user's request to modify an HTML visualization, return a JSON object with:
- \"intent\": one of [title_change, subtitle_change, color_change, axis_label, legend_toggle, data_update, font_size, add_element, remove_element, layout_change, style_change, complex]
- \"target_css\": CSS selector for the element to edit, or null
- \"new_value\": the new value if it's a simple replacement, or null
- \"confidence\": 0.0-1.0

Return ONLY the JSON object, nothing else."""


SCOPED_PATCH_SYSTEM_PROMPT = """You are an HTML visualization editor. You will receive:
1. A user's edit request
2. A FRAGMENT of HTML - the specific section that needs editing

Return ONLY the modified HTML fragment. Do not add explanations, markdown fences, or any text outside the HTML. The fragment must be valid HTML and must preserve the same root element tag and class structure.

Rules:
- Make ONLY the change the user requested
- Preserve all existing classes, ids, and data attributes
- Preserve the dark theme (use CSS variables, not hardcoded light colors)
- Do not add external scripts or stylesheets
- If the requested change is unclear, make your best interpretation"""


SYSTEM_PROMPT = """You are an HTML visualization editor. Return ONLY the complete modified HTML card. Rules:
- Start with a div with class \"visualizationCard\"
- Do not use external scripts or stylesheets
- Preserve the dark theme using CSS variables
- Use the vc-header, vc-title, vc-subtitle, vc-body, vc-footer, vc-insight structure
- If data is missing, show a warning block instead of inventing values
- Make ONLY the change the user requested - do not alter anything else"""


# ============================================================
# CLASSIFICATION CONSTANTS
# ============================================================

COLOR_NORMALIZATION_MAP: Dict[str, str] = {
    "red": "#E24B4A",
    "blue": "#378ADD",
    "green": "#639922",
    "yellow": "#EF9F27",
    "orange": "#D85A30",
    "purple": "#7F77DD",
    "pink": "#D4537E",
    "gray": "#888780",
    "grey": "#888780",
    "teal": "#1D9E75",
    "coral": "#D85A30",
    "amber": "#BA7517",
    "black": "#2C2C2A",
    "white": "#F1EFE8",
}

COLOR_WORD_PATTERN = "|".join(sorted(COLOR_NORMALIZATION_MAP.keys(), key=len, reverse=True))

ELEMENT_SELECTOR_MAP: Dict[str, str] = {
    "title": ".vc-title, h1, h2, .title, [class*='title']",
    "subtitle": ".vc-subtitle, .subtitle, [class*='subtitle'], .description",
    "description": ".vc-subtitle, .subtitle, [class*='subtitle'], .description",
    "legend": ".vc-legend, [class*='legend']",
    "grid": "[class*='grid'], .grid",
    "tooltip": "[class*='tooltip'], .tooltip",
    "label": "[class*='label'], .label",
    "annotation": ".vc-insight, [class*='annotation']",
    "footer": ".vc-footer, footer",
    "header": ".vc-header, header",
    "insight": ".vc-insight",
}

INTENT_PATTERNS: Dict[EditIntent, List[re.Pattern[str]]] = {
    EditIntent.TITLE_CHANGE: [
        re.compile(r"\b(?:change|update|set|make|rename|edit)\b[^\n]{0,120}\btitle\b", re.IGNORECASE),
        re.compile(r"\btitle\b[^\n]{0,120}\b(?:to|should\s+be|as|say|be)\b", re.IGNORECASE),
    ],
    EditIntent.SUBTITLE_CHANGE: [
        re.compile(r"\b(?:change|update|set|make|rename|edit)\b[^\n]{0,120}\b(?:subtitle|description)\b", re.IGNORECASE),
        re.compile(r"\b(?:subtitle|description)\b[^\n]{0,120}\b(?:to|should\s+be|as|say|be)\b", re.IGNORECASE),
    ],
    EditIntent.COLOR_CHANGE: [
        re.compile(
            rf"\b(?:change|make|set|turn|color)\b[^\n]{{0,120}}\b(?:bars?|lines?|area|pie|slices?|background|fill|stroke|chart)\b[^\n]{{0,80}}(?:{COLOR_WORD_PATTERN}|#[0-9a-fA-F]{{3,8}})\b",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?:{COLOR_WORD_PATTERN}|#[0-9a-fA-F]{{3,8}})\b[^\n]{{0,80}}\b(?:bars?|lines?|area|pie|slices?|background|fill|stroke)\b",
            re.IGNORECASE,
        ),
    ],
    EditIntent.AXIS_LABEL: [
        re.compile(r"\b(?:change|update|set|rename|label)\b[^\n]{0,120}\b(?:x|y|horizontal|vertical)\s*-?\s*axis\b", re.IGNORECASE),
        re.compile(r"\b(?:x|y|horizontal|vertical)\s*-?\s*axis\b[^\n]{0,120}\b(?:label|title|name)\b", re.IGNORECASE),
    ],
    EditIntent.LEGEND_TOGGLE: [
        re.compile(r"\b(?:show|hide|toggle|add|remove)\b[^\n]{0,60}\blegend\b", re.IGNORECASE),
    ],
    EditIntent.FONT_SIZE: [
        re.compile(r"\b(?:font|text)\s*size\b", re.IGNORECASE),
        re.compile(r"\b(?:bigger|smaller|larger)\b[^\n]{0,40}\b(?:text|font)\b", re.IGNORECASE),
        re.compile(r"\b\d+\s*px\b", re.IGNORECASE),
    ],
    EditIntent.ADD_ELEMENT: [
        re.compile(r"\b(?:add|include|insert)\b[^\n]{0,120}\b(?:title|subtitle|legend|grid|tooltip|label|annotation|footer|header|insight)\b", re.IGNORECASE),
    ],
    EditIntent.REMOVE_ELEMENT: [
        re.compile(r"\b(?:remove|delete|hide|drop)\b[^\n]{0,120}\b(?:title|subtitle|legend|grid|tooltip|label|annotation|footer|header|insight)\b", re.IGNORECASE),
    ],
    EditIntent.DATA_UPDATE: [
        re.compile(r"\b(?:update|change|replace)\b[^\n]{0,120}\b(?:data|values|numbers|dataset|series)\b", re.IGNORECASE),
    ],
    EditIntent.LAYOUT_CHANGE: [
        re.compile(r"\b(?:layout|arrange|alignment|position|move|resize|spacing)\b", re.IGNORECASE),
    ],
    EditIntent.STYLE_CHANGE: [
        re.compile(r"\b(?:style|theme|professional|cleaner|modern)\b", re.IGNORECASE),
    ],
}

INTENT_PRIORITY: List[EditIntent] = [
    EditIntent.TITLE_CHANGE,
    EditIntent.SUBTITLE_CHANGE,
    EditIntent.COLOR_CHANGE,
    EditIntent.AXIS_LABEL,
    EditIntent.REMOVE_ELEMENT,
    EditIntent.ADD_ELEMENT,
    EditIntent.LEGEND_TOGGLE,
    EditIntent.FONT_SIZE,
    EditIntent.DATA_UPDATE,
    EditIntent.LAYOUT_CHANGE,
    EditIntent.STYLE_CHANGE,
]


# ============================================================
# VALIDATION FUNCTIONS
# ============================================================


def validate_visualization_html(html: str, allow_external_images: bool = False) -> ValidationResult:
    """
    Validate HTML content meets visualization card requirements.
    """
    warnings: List[str] = []

    if not html or not isinstance(html, str):
        return ValidationResult(valid=False, error="HTML content is required")

    if len(html) > MAX_HTML_SIZE:
        return ValidationResult(
            valid=False,
            error=f"HTML content exceeds maximum size limit ({MAX_HTML_SIZE} characters)",
        )

    if REQUIRED_ROOT_CLASS not in html:
        return ValidationResult(
            valid=False,
            error=f"Missing required .{REQUIRED_ROOT_CLASS} root element",
        )

    # Block external script sources
    external_script_pattern = re.compile(r"<script[^>]+src\s*=", re.IGNORECASE)
    if external_script_pattern.search(html):
        return ValidationResult(
            valid=False,
            error="External script sources (<script src=\"...\">) are not permitted",
        )

    # Block external stylesheets
    external_style_pattern = re.compile(r"<link[^>]+href\s*=\s*[\"']https?:", re.IGNORECASE)
    if external_style_pattern.search(html):
        return ValidationResult(
            valid=False,
            error="External stylesheet links are not permitted",
        )

    # Warn about external images
    external_image_pattern = re.compile(r"<img[^>]+src\s*=\s*[\"']https?:", re.IGNORECASE)
    if external_image_pattern.search(html) and not allow_external_images:
        warnings.append("Contains external image references")

    return ValidationResult(valid=True, warnings=warnings if warnings else None)


def _clean_llm_fragment(raw_output: str, expect_html: bool = True) -> str:
    """Clean LLM output for either HTML fragments or JSON text."""
    cleaned = (raw_output or "").strip()

    # Remove markdown code fences
    cleaned = re.sub(r"^```(?:html|json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    if not expect_html:
        return cleaned.strip()

    # Keep only probable HTML part for fragment/full-card usage
    start = cleaned.find("<")
    end = cleaned.rfind(">")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]

    return cleaned.strip()


def clean_llm_output(raw_output: str) -> str:
    """Compatibility wrapper for legacy tests/callers."""
    return _clean_llm_fragment(raw_output, expect_html=True)


def extract_visualization_card(html: str) -> Optional[str]:
    """Extract just the visualizationCard div from potentially larger HTML."""
    pattern = re.compile(
        r"(<div[^>]*class\s*=\s*[\"'][^\"']*visualizationCard[^\"']*[\"'][^>]*>)",
        re.IGNORECASE,
    )
    match = pattern.search(html)

    if not match:
        return None

    start_pos = match.start()
    depth = 0
    i = start_pos

    while i < len(html):
        if html[i : i + 4].lower() == "<div":
            depth += 1
            i += 4
        elif html[i : i + 6].lower() == "</div>":
            depth -= 1
            if depth == 0:
                return html[start_pos : i + 6]
            i += 6
        else:
            i += 1

    return None


# ============================================================
# OLLAMA CALLER
# ============================================================


async def call_ollama(
    user_prompt: str,
    system_prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Call Ollama API for HTML editing/classification."""
    import ollama

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options={"num_predict": max_tokens, "temperature": temperature},
    )

    return response["message"]["content"]


# ============================================================
# INTENT CLASSIFICATION
# ============================================================


def _selector_for_element_keywords(user_request: str) -> Optional[str]:
    lower = user_request.lower()
    for element, selector in ELEMENT_SELECTOR_MAP.items():
        if re.search(rf"\b{re.escape(element)}\b", lower):
            return selector
    return None


def _intent_to_selector(intent: EditIntent, user_request: str = "") -> Optional[str]:
    default_map: Dict[EditIntent, Optional[str]] = {
        EditIntent.TITLE_CHANGE: ".vc-title",
        EditIntent.SUBTITLE_CHANGE: ".vc-subtitle",
        EditIntent.LEGEND_TOGGLE: ".vc-legend, [class*='legend']",
        EditIntent.COLOR_CHANGE: ".vc-body, .chart-container, svg",
        EditIntent.AXIS_LABEL: ".vc-body, svg, .chart-container",
        EditIntent.DATA_UPDATE: ".vc-body, svg, table, .chart-container",
        EditIntent.FONT_SIZE: ".visualizationCard",
        EditIntent.ADD_ELEMENT: ".vc-body, .visualizationCard",
        EditIntent.REMOVE_ELEMENT: _selector_for_element_keywords(user_request),
        EditIntent.LAYOUT_CHANGE: ".vc-body, .visualizationCard",
        EditIntent.STYLE_CHANGE: ".vc-body, .visualizationCard",
        EditIntent.COMPLEX: ".visualizationCard",
    }
    return default_map.get(intent)


def _extract_value(user_request: str, intent: EditIntent) -> Optional[str]:
    text = user_request.strip()

    quoted_match = re.search(r'"([^"\n]+)"|\'([^\'\n]+)\'', text)
    if quoted_match and intent in {
        EditIntent.TITLE_CHANGE,
        EditIntent.SUBTITLE_CHANGE,
        EditIntent.AXIS_LABEL,
        EditIntent.FONT_SIZE,
        EditIntent.COLOR_CHANGE,
    }:
        return (quoted_match.group(1) or quoted_match.group(2) or "").strip()

    if intent in {EditIntent.TITLE_CHANGE, EditIntent.SUBTITLE_CHANGE, EditIntent.AXIS_LABEL}:
        m = re.search(r"\b(?:to|say|be|as)\s+(.+)$", text, re.IGNORECASE)
        if m:
            return m.group(1).strip().strip(" .,!;:\"'")

    if intent == EditIntent.COLOR_CHANGE:
        hex_match = re.search(r"#[0-9a-fA-F]{3,8}\b", text)
        if hex_match:
            return hex_match.group(0)
        color_match = re.search(rf"\b({COLOR_WORD_PATTERN})\b", text, re.IGNORECASE)
        if color_match:
            return color_match.group(1).lower()

    if intent == EditIntent.FONT_SIZE:
        px_match = re.search(r"\b(\d+)\s*px\b", text, re.IGNORECASE)
        if px_match:
            return f"{px_match.group(1)}px"

    return None


def classify_intent_rules(user_request: str) -> Optional[ClassifiedEdit]:
    """Rule-based intent classifier (cheap and deterministic)."""
    if not user_request or not user_request.strip():
        return None

    for intent in INTENT_PRIORITY:
        patterns = INTENT_PATTERNS.get(intent, [])
        if any(pattern.search(user_request) for pattern in patterns):
            target_selector = _intent_to_selector(intent, user_request)
            new_value = _extract_value(user_request, intent)
            parameters: Dict[str, Any] = {}

            if intent == EditIntent.LEGEND_TOGGLE:
                if re.search(r"\b(?:hide|remove|delete|drop)\b", user_request, re.IGNORECASE):
                    parameters["action"] = "hide"
                elif re.search(r"\b(?:show|add|include)\b", user_request, re.IGNORECASE):
                    parameters["action"] = "show"
                else:
                    parameters["action"] = "toggle"

            if intent == EditIntent.AXIS_LABEL:
                if re.search(r"\b(?:x|horizontal)\b", user_request, re.IGNORECASE):
                    parameters["axis"] = "x"
                elif re.search(r"\b(?:y|vertical)\b", user_request, re.IGNORECASE):
                    parameters["axis"] = "y"

            return ClassifiedEdit(
                intent=intent,
                target_selector=target_selector,
                new_value=new_value,
                parameters=parameters,
                confidence=0.9,
            )

    return None


def _safe_parse_json(raw_text: str) -> Optional[Dict[str, Any]]:
    cleaned = _clean_llm_fragment(raw_text, expect_html=False)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


async def classify_intent_llm(user_request: str, llm_client: Dict[str, str]) -> ClassifiedEdit:
    """Fallback LLM classifier when rule matching cannot confidently classify."""
    provider = llm_client.get("provider", "ollama")
    model = llm_client.get("model", DEFAULT_MODEL)

    if provider != "ollama":
        return ClassifiedEdit(intent=EditIntent.COMPLEX, confidence=0.3)

    user_prompt = f"User request: {user_request}"

    try:
        raw = await call_ollama(
            user_prompt=user_prompt,
            system_prompt=INTENT_CLASSIFIER_SYSTEM_PROMPT,
            model=model,
            max_tokens=100,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("LLM classifier failed: %s", exc)
        return ClassifiedEdit(intent=EditIntent.COMPLEX, confidence=0.3)

    payload = _safe_parse_json(raw)
    if not payload:
        return ClassifiedEdit(intent=EditIntent.COMPLEX, confidence=0.3)

    raw_intent = str(payload.get("intent", "complex")).strip().lower()
    try:
        intent = EditIntent(raw_intent)
    except ValueError:
        intent = EditIntent.COMPLEX

    target_css = payload.get("target_css")
    target_selector = str(target_css).strip() if isinstance(target_css, str) and target_css.strip() else None

    raw_new = payload.get("new_value")
    new_value = str(raw_new).strip() if isinstance(raw_new, str) and raw_new.strip() else None
    if not new_value:
        new_value = _extract_value(user_request, intent)

    raw_confidence = payload.get("confidence", 0.3)
    try:
        confidence = max(0.0, min(1.0, float(raw_confidence)))
    except (TypeError, ValueError):
        confidence = 0.3

    return ClassifiedEdit(
        intent=intent,
        target_selector=target_selector or _intent_to_selector(intent, user_request),
        new_value=new_value,
        confidence=confidence,
    )


# ============================================================
# PROGRAMMATIC DOM EDITS
# ============================================================


def _normalize_color(value: str) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", value):
        return value
    return COLOR_NORMALIZATION_MAP.get(value.lower())


def _handle_title_change(soup: BeautifulSoup, edit: ClassifiedEdit) -> Tuple[bool, str]:
    if not edit.new_value:
        return False, ""

    element = soup.select_one(".vc-title")
    if element is None:
        element = soup.select_one("h1, h2, .title, [class*='title']")
    if element is None:
        return False, ""

    old_text = element.get_text(strip=True)
    element.string = edit.new_value
    return True, f"Changed title from '{old_text}' to '{edit.new_value}'"


def _handle_subtitle_change(soup: BeautifulSoup, edit: ClassifiedEdit) -> Tuple[bool, str]:
    if not edit.new_value:
        return False, ""

    element = soup.select_one(".vc-subtitle")
    if element is None:
        element = soup.select_one(".subtitle, [class*='subtitle'], .description")
    if element is None:
        return False, ""

    old_text = element.get_text(strip=True)
    element.string = edit.new_value
    return True, f"Changed subtitle from '{old_text}' to '{edit.new_value}'"


def _handle_color_change(soup: BeautifulSoup, edit: ClassifiedEdit) -> Tuple[bool, str]:
    if not edit.new_value:
        return False, ""

    color = _normalize_color(edit.new_value)
    if not color:
        return False, ""

    count = 0
    skip_classes = {"vc-body", "vc-header", "vc-footer", "box"}

    for node in soup.find_all(["rect", "path", "line", "circle", "polygon"]):
        classes = set(node.get("class", []))
        if classes.intersection(skip_classes):
            continue

        fill = node.get("fill")
        if fill:
            fill_lower = str(fill).strip().lower()
            if fill_lower not in {"none", "transparent"} and not fill_lower.startswith("url("):
                node["fill"] = color
                count += 1

        stroke = node.get("stroke")
        if stroke:
            stroke_lower = str(stroke).strip().lower()
            if stroke_lower not in {"none", "transparent"}:
                node["stroke"] = color
                count += 1

    for node in soup.find_all(style=True):
        classes = set(node.get("class", []))
        if "visualizationCard" in classes or "vc-body" in classes:
            continue

        style_text = str(node.get("style", ""))
        if "background-color" not in style_text.lower() and "background:" not in style_text.lower():
            continue

        style_new, n = re.subn(
            r"(background(?:-color)?\s*:\s*)([^;]+)",
            lambda m: m.group(1) + color,
            style_text,
            flags=re.IGNORECASE,
        )
        if n > 0:
            node["style"] = style_new
            count += n

    if count > 0:
        return True, f"Changed {count} element(s) to {color}"
    return False, ""


def _handle_remove_element(soup: BeautifulSoup, edit: ClassifiedEdit) -> Tuple[bool, str]:
    if not edit.target_selector:
        return False, ""

    try:
        matches = soup.select(edit.target_selector)
    except Exception:
        return False, ""

    count = 0
    for node in matches:
        node.decompose()
        count += 1

    if count > 0:
        return True, f"Removed {count} element(s)"
    return False, ""


PROGRAMMATIC_HANDLERS: Dict[EditIntent, Callable[[BeautifulSoup, ClassifiedEdit], Tuple[bool, str]]] = {
    EditIntent.TITLE_CHANGE: _handle_title_change,
    EditIntent.SUBTITLE_CHANGE: _handle_subtitle_change,
    EditIntent.COLOR_CHANGE: _handle_color_change,
    EditIntent.REMOVE_ELEMENT: _handle_remove_element,
}


def apply_programmatic_edit(html: str, edit: ClassifiedEdit) -> Optional[EditResult]:
    """Apply deterministic DOM edit without LLM."""
    if edit.intent == EditIntent.COMPLEX:
        return None

    handler = PROGRAMMATIC_HANDLERS.get(edit.intent)
    if handler is None:
        return None

    soup = BeautifulSoup(html, "html.parser")
    try:
        changed, description = handler(soup, edit)
    except Exception as exc:
        logger.warning("Programmatic handler failed for %s: %s", edit.intent.value, exc)
        return None

    if not changed:
        return None

    updated_html = str(soup)
    validation = validate_visualization_html(updated_html)
    if not validation.valid:
        logger.warning("Programmatic output failed validation: %s", validation.error)
        return None

    return EditResult(
        success=True,
        html=updated_html,
        method="programmatic",
        changes_description=description,
        tokens_used=0,
    )


# ============================================================
# DIFF GUARD
# ============================================================


def _flatten_dom(soup: BeautifulSoup) -> List[str]:
    signatures: List[str] = []
    for node in soup.descendants:
        if isinstance(node, Tag):
            classes = node.get("class", [])
            class_sig = ".".join(sorted(classes)) if classes else ""
            text_sig = node.get_text(" ", strip=True)[:80]
            signatures.append(f"{node.name}|{class_sig}|{text_sig}")
    return signatures


def _diff_guard(
    old_html: str,
    new_html: str,
    edit: ClassifiedEdit,
    threshold: float = 0.2,
) -> bool:
    old_soup = BeautifulSoup(old_html, "html.parser")
    new_soup = BeautifulSoup(new_html, "html.parser")

    old_set = set(_flatten_dom(old_soup))
    new_set = set(_flatten_dom(new_soup))
    symmetric_difference = old_set.symmetric_difference(new_set)

    drift_ratio = len(symmetric_difference) / max(len(old_set), len(new_set), 1)
    if drift_ratio > threshold:
        logger.warning(
            "Diff guard rejected edit. intent=%s drift_ratio=%.3f old_nodes=%d new_nodes=%d diff_nodes=%d threshold=%.3f",
            edit.intent.value,
            drift_ratio,
            len(old_set),
            len(new_set),
            len(symmetric_difference),
            threshold,
        )
        return False
    return True


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ============================================================
# SCOPED LLM PATCH
# ============================================================


INTENT_SCOPE_SELECTORS: Dict[EditIntent, List[str]] = {
    EditIntent.TITLE_CHANGE: [".vc-header", "header", ".title"],
    EditIntent.SUBTITLE_CHANGE: [".vc-header", "header", ".subtitle"],
    EditIntent.COLOR_CHANGE: [".vc-body", ".chart-container", "svg", "main"],
    EditIntent.AXIS_LABEL: [".vc-body", "svg", ".chart-container"],
    EditIntent.LEGEND_TOGGLE: [".vc-body", "svg", ".chart-container"],
    EditIntent.DATA_UPDATE: [".vc-body", "svg", "table", ".chart-container"],
    EditIntent.FONT_SIZE: [".visualizationCard"],
    EditIntent.ADD_ELEMENT: [".vc-body", ".visualizationCard"],
    EditIntent.REMOVE_ELEMENT: [".vc-body", ".visualizationCard"],
    EditIntent.LAYOUT_CHANGE: [".vc-body", ".visualizationCard"],
    EditIntent.STYLE_CHANGE: [".vc-body", ".visualizationCard"],
}


def _find_edit_target(soup: BeautifulSoup, edit: ClassifiedEdit) -> Optional[Tag]:
    if edit.target_selector:
        try:
            selected = soup.select_one(edit.target_selector)
        except Exception:
            selected = None
        if selected is not None:
            parent = selected.parent
            if isinstance(parent, Tag) and parent.name != "[document]":
                return parent
            return selected

    for selector in INTENT_SCOPE_SELECTORS.get(edit.intent, []):
        try:
            selected = soup.select_one(selector)
        except Exception:
            selected = None
        if selected is not None:
            return selected

    selected = soup.select_one(".visualizationCard")
    if selected is not None:
        return selected

    return soup.find(True)


def _get_subtree_context(node: Tag) -> str:
    def describe(tag: Optional[Tag]) -> str:
        if not isinstance(tag, Tag):
            return "document"
        classes = " ".join(tag.get("class", []))
        return f"<{tag.name} class='{classes}'>" if classes else f"<{tag.name}>"

    return f"{describe(node)} inside {describe(node.parent if isinstance(node.parent, Tag) else None)}"


async def apply_scoped_llm_patch(
    html: str,
    edit: ClassifiedEdit,
    user_request: str,
    llm_client: Dict[str, str],
) -> Optional[EditResult]:
    provider = llm_client.get("provider", "ollama")
    model = llm_client.get("model", DEFAULT_MODEL)

    if provider != "ollama":
        return None

    soup = BeautifulSoup(html, "html.parser")
    target_node = _find_edit_target(soup, edit)
    if target_node is None:
        return None

    subtree_html = str(target_node)
    subtree_context = _get_subtree_context(target_node)

    user_prompt = (
        f"User request: {user_request}\n\n"
        f"HTML fragment to edit:\n{subtree_html}\n\n"
        f"Context: This fragment is inside a {subtree_context}.\n\n"
        "Return the modified fragment only."
    )

    try:
        raw_output = await call_ollama(
            user_prompt=user_prompt,
            system_prompt=SCOPED_PATCH_SYSTEM_PROMPT,
            model=model,
            max_tokens=MAX_PATCH_TOKENS,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("Scoped LLM patch call failed: %s", exc)
        return None

    cleaned_fragment = _clean_llm_fragment(raw_output, expect_html=True)
    fragment_soup = BeautifulSoup(cleaned_fragment, "html.parser")
    new_root = fragment_soup.find(True)

    if new_root is None:
        logger.warning("Scoped LLM returned empty or non-HTML fragment")
        return None

    if new_root.name != target_node.name:
        logger.warning(
            "Scoped patch root tag mismatch. old=%s new=%s",
            target_node.name,
            new_root.name,
        )
        return None

    target_node.replace_with(new_root)
    result_html = str(soup)

    validation = validate_visualization_html(result_html)
    if not validation.valid:
        logger.warning("Scoped patch produced invalid HTML: %s", validation.error)
        return None

    if not _diff_guard(html, result_html, edit, threshold=0.2):
        logger.warning("Scoped patch rejected by diff guard")
        return None

    return EditResult(
        success=True,
        html=result_html,
        method="scoped_llm",
        changes_description=f"Applied scoped LLM patch for {edit.intent.value}",
        tokens_used=_estimate_tokens(raw_output),
    )


# ============================================================
# FULL REWRITE (LAST RESORT)
# ============================================================


async def apply_full_rewrite(
    html: str,
    user_request: str,
    llm_client: Dict[str, str],
    edit: ClassifiedEdit,
) -> Optional[EditResult]:
    provider = llm_client.get("provider", "ollama")
    model = llm_client.get("model", DEFAULT_MODEL)

    if provider != "ollama":
        return None

    user_prompt = (
        f"User request: {user_request}\n\n"
        f"Current HTML:\n{html}\n\n"
        "Return the complete modified HTML card."
    )

    try:
        raw_output = await call_ollama(
            user_prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            model=model,
            max_tokens=MAX_FULL_TOKENS,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("Full rewrite call failed: %s", exc)
        return None

    cleaned_html = _clean_llm_fragment(raw_output, expect_html=True)
    extracted = extract_visualization_card(cleaned_html)
    if extracted:
        cleaned_html = extracted

    soup = BeautifulSoup(cleaned_html, "html.parser")
    if soup.select_one(".visualizationCard") is None:
        logger.warning("Full rewrite missing .visualizationCard root")
        return None

    validation = validate_visualization_html(cleaned_html)
    if not validation.valid:
        logger.warning("Full rewrite produced invalid HTML: %s", validation.error)
        return None

    drift_ok = _diff_guard(html, cleaned_html, edit, threshold=0.4)
    if not drift_ok and edit.intent == EditIntent.COMPLEX:
        logger.warning("Full rewrite drift accepted for COMPLEX intent")
    elif not drift_ok:
        logger.warning("Full rewrite rejected by diff guard for non-COMPLEX intent")
        return None

    return EditResult(
        success=True,
        html=cleaned_html,
        method="full_rewrite",
        changes_description=f"Applied full rewrite for {edit.intent.value}",
        tokens_used=_estimate_tokens(raw_output),
    )


# ============================================================
# MAIN PIPELINE
# ============================================================


async def edit_visualization(
    html: str,
    user_request: str,
    llm_client: Dict[str, str],
) -> EditResult:
    # Validate input
    if not html or not html.strip():
        return EditResult(
            success=False,
            html=html,
            method="none",
            changes_description="Empty HTML input",
        )

    # Stage 1: Classify intent
    edit = classify_intent_rules(user_request)
    if edit is None:
        edit = await classify_intent_llm(user_request, llm_client)
    logger.info("Classified intent: %s (confidence: %.2f)", edit.intent.value, edit.confidence)

    # Stage 2: Programmatic DOM edit
    if edit.intent != EditIntent.COMPLEX:
        result = apply_programmatic_edit(html, edit)
        if result:
            logger.info("Programmatic edit succeeded: %s", result.changes_description)
            return result

    # Stage 3: Scoped LLM patch
    if edit.intent != EditIntent.COMPLEX or edit.confidence < 0.5:
        result = await apply_scoped_llm_patch(html, edit, user_request, llm_client)
        if result:
            logger.info("Scoped LLM patch succeeded: %s", result.changes_description)
            return result

    # Stage 4: Full rewrite
    result = await apply_full_rewrite(html, user_request, llm_client, edit)
    if result:
        logger.info("Full rewrite used: %s", result.changes_description)
        return result

    # All stages failed
    return EditResult(
        success=False,
        html=html,
        method="none",
        changes_description="All edit methods failed",
    )


# ============================================================
# PUBLIC API FUNCTIONS (SIGNATURES KEPT)
# ============================================================


async def visualizer_edit_html(
    user_query: str,
    html: str,
    max_output_chars: int = MAX_OUTPUT_CHARS,
    model: str = DEFAULT_MODEL,
    provider: str = "ollama",
) -> VisualizerResponse:
    """
    Edit a visualization HTML card based on user query.

    External behavior and route signatures remain unchanged.
    Internal logic now uses an intent-first DOM-aware pipeline.
    """
    _ = max_output_chars  # Kept for compatibility with existing callers.

    input_validation = validate_visualization_html(html)
    if not input_validation.valid:
        return VisualizerResponse(
            status="error",
            message=f"Invalid input HTML: {input_validation.error}",
        )

    if provider != "ollama":
        return VisualizerResponse(
            status="error",
            message=f"Unknown provider: {provider}",
        )

    llm_client = {"provider": provider, "model": model}

    try:
        result = await edit_visualization(html=html, user_request=user_query, llm_client=llm_client)
    except ImportError as exc:
        return VisualizerResponse(
            status="error",
            message=f"Missing dependency: {exc}. Install with pip.",
        )
    except Exception as exc:
        logger.exception("Visualizer pipeline failed")
        return VisualizerResponse(
            status="error",
            message=f"LLM pipeline failed: {exc}",
        )

    if not result.success:
        return VisualizerResponse(
            status="error",
            message=result.changes_description,
            html=result.html,
        )

    output_validation = validate_visualization_html(result.html)
    if not output_validation.valid:
        return VisualizerResponse(
            status="error",
            message=f"Pipeline produced invalid HTML: {output_validation.error}",
        )

    return VisualizerResponse(
        status="success",
        html=result.html,
        warnings=output_validation.warnings,
    )


def visualizer_edit_html_sync(
    user_query: str,
    html: str,
    max_output_chars: int = MAX_OUTPUT_CHARS,
    model: str = DEFAULT_MODEL,
    provider: str = "ollama",
) -> VisualizerResponse:
    """Synchronous wrapper for visualizer_edit_html."""
    return asyncio.run(
        visualizer_edit_html(
            user_query=user_query,
            html=html,
            max_output_chars=max_output_chars,
            model=model,
            provider=provider,
        )
    )


def register_mcp_tool(server, provider: str = "ollama", model: str = DEFAULT_MODEL):
    """
    Register the visualizer_edit_html tool with an MCP server.

    Example:
        from mcp.server import Server
        server = Server("visualizer-agent")
        register_mcp_tool(server, provider="ollama", model="qwen2.5-coder:32b")
    """
    from mcp.types import TextContent

    @server.tool()
    async def visualizer_edit_html_tool(
        user_query: str,
        html: str,
        max_output_chars: int = MAX_OUTPUT_CHARS,
    ) -> list:
        """
        Edit a visualization HTML card based on user instructions.

        Args:
            user_query: What changes to make to the visualization
            html: Current HTML (must contain .visualizationCard root)
            max_output_chars: Maximum output size (default 60000)
        """
        result = await visualizer_edit_html(
            user_query=user_query,
            html=html,
            max_output_chars=max_output_chars,
            model=model,
            provider=provider,
        )

        if result.status == "success":
            response_text = result.html or ""
            if result.warnings:
                response_text += f"\n\n<!-- Warnings: {', '.join(result.warnings)} -->"
            return [TextContent(type="text", text=response_text)]
        return [TextContent(type="text", text=f"Error: {result.message}")]


def create_fastapi_router(provider: str = "ollama", model: str = DEFAULT_MODEL):
    """
    Create a FastAPI router with the visualizer edit endpoint.

    Example:
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(create_fastapi_router(provider="ollama"))
    """
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel

    router = APIRouter(prefix="/api/visualizer", tags=["visualizer"])

    class EditRequest(BaseModel):
        user_query: str
        html: str
        max_output_chars: int = MAX_OUTPUT_CHARS

    class EditResponse(BaseModel):
        status: str
        html: Optional[str] = None
        message: Optional[str] = None
        warnings: Optional[List[str]] = None

    @router.post("/edit_html", response_model=EditResponse)
    async def edit_html_endpoint(request: EditRequest):
        """Edit a visualization HTML card based on user instructions."""
        result = await visualizer_edit_html(
            user_query=request.user_query,
            html=request.html,
            max_output_chars=request.max_output_chars,
            model=model,
            provider=provider,
        )

        if result.status == "error":
            raise HTTPException(status_code=400, detail=result.message)

        return EditResponse(
            status=result.status,
            html=result.html,
            warnings=result.warnings,
        )

    return router


STARTER_HTML = """<div class="visualizationCard bg-slate-900 rounded-xl border border-slate-700 p-4">
  <div class="vc-header">
    <h3 class="vc-title text-slate-100 font-semibold text-base text-center"></h3>
    <p class="vc-subtitle text-slate-400 text-xs text-center mt-1"></p>
  </div>
  <div class="vc-body mt-3">
    <div class="h-[280px] rounded-lg border border-slate-700 bg-slate-950 flex items-center justify-center text-slate-500">
    </div>
  </div>
</div>"""


def run_validation_tests():
    """Run basic validation tests."""
    print("Running validation tests...\n")

    # Test 1: Valid HTML
    result = validate_visualization_html(STARTER_HTML)
    assert result.valid, f"Test 1 failed: {result.error}"
    print("OK Test 1: Valid HTML passes validation")

    # Test 2: Missing visualizationCard
    result = validate_visualization_html("<div>Hello</div>")
    assert not result.valid, "Test 2 failed: Should reject missing root"
    print("OK Test 2: Rejects missing visualizationCard root")

    # Test 3: External script
    result = validate_visualization_html(
        '<div class="visualizationCard"><script src="http://evil.com/bad.js"></script></div>'
    )
    assert not result.valid, "Test 3 failed: Should reject external scripts"
    print("OK Test 3: Rejects external script sources")

    # Test 4: Inline script allowed
    result = validate_visualization_html(
        '<div class="visualizationCard"><script>console.log("ok")</script></div>'
    )
    assert result.valid, f"Test 4 failed: {result.error}"
    print("OK Test 4: Allows inline scripts")

    # Test 5: External stylesheet
    result = validate_visualization_html(
        '<div class="visualizationCard"><link href="https://evil.com/bad.css" rel="stylesheet"></div>'
    )
    assert not result.valid, "Test 5 failed: Should reject external stylesheets"
    print("OK Test 5: Rejects external stylesheets")

    # Test 6: Clean LLM output
    messy_output = "```html\n<div class=\"visualizationCard\">test</div>\n```"
    cleaned = clean_llm_output(messy_output)
    assert cleaned == '<div class="visualizationCard">test</div>', f"Test 6 failed: {cleaned}"
    print("OK Test 6: Cleans markdown fences from output")

    print("\nAll validation tests passed!")


async def quick_test(provider: str = "ollama", model: str = DEFAULT_MODEL):
    """Quick test of the edit function."""
    print(f"\nQuick test using {provider} with model '{model}'...")

    result = await visualizer_edit_html(
        user_query="Add a footer that says 'Source: UK Biobank'",
        html=STARTER_HTML,
        provider=provider,
        model=model,
    )

    if result.status == "success":
        print("Success!")
        print(f"\nOutput HTML:\n{result.html}")
    else:
        print(f"Error: {result.message}")

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Run validation tests
        run_validation_tests()
    elif len(sys.argv) > 1 and sys.argv[1] == "--quick":
        # Run quick LLM test
        provider = sys.argv[2] if len(sys.argv) > 2 else "ollama"
        model = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_MODEL
        asyncio.run(quick_test(provider, model))
    else:
        print("Usage:")
        print("  python visualizer_agent.py --test              # Run validation tests")
        print("  python visualizer_agent.py --quick             # Quick LLM test (Ollama)")