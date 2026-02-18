import type { FileInfo, CorrelationResult, GroupComparisonResult, FDRResult, OutlierResult, CFCWaveletResult, HubDetectionResult, GrowthCurveResult, BoldAdjResult } from './types';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const text = await res.text();
      try {
        const body = JSON.parse(text);
        detail = body.detail || body.error || detail;
      } catch {
        detail = text || detail;
      }
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function uploadFile(file: File, relativePath?: string): Promise<{ status: string; file_info: FileInfo }> {
  const form = new FormData();
  form.append('file', file);
  if (relativePath) form.append('relative_path', relativePath);
  const res = await fetch('/upload', { method: 'POST', body: form });
  return handleResponse(res);
}

export async function listFiles(): Promise<{ status: string; count: number; files: FileInfo[] }> {
  const res = await fetch('/list_files');
  return handleResponse(res);
}

export async function deleteFile(filename: string): Promise<{ status: string }> {
  const res = await fetch('/delete_file', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename }),
  });
  return handleResponse(res);
}

export async function runCorrelation(
  data_source: string,
  var1: string,
  var2: string
): Promise<CorrelationResult> {
  const res = await fetch('/run_correlation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data_source, var1, var2 }),
  });
  return handleResponse(res);
}

export async function runGroupComparison(
  data_source: string,
  group_col: string,
  metric_col: string,
  group_a: string,
  group_b: string,
  method: string
): Promise<GroupComparisonResult & { group_a: string; group_b: string }> {
  const res = await fetch('/run_group_comparison', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data_source, group_col, metric_col, group_a, group_b, method }),
  });
  const data = await handleResponse<GroupComparisonResult>(res);
  return { ...data, group_a, group_b };
}

export async function applyFDRCorrection(p_values: number[]): Promise<FDRResult> {
  const res = await fetch('/apply_fdr_correction', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ p_values }),
  });
  return handleResponse(res);
}

export async function detectOutliers(data_source: string, column: string): Promise<OutlierResult> {
  const res = await fetch('/detect_outliers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data_source, column }),
  });
  return handleResponse(res);
}

export async function runCFCWaveletAnalysis(params: {
  data_path: string;
  window_size?: number;
  step_size?: number;
  padding?: boolean;
  ratio?: number;
  wavelets_num?: number;
  beta?: number;
  gamma?: number;
  max_iter?: number;
  node_select?: number;
}): Promise<CFCWaveletResult> {
  const res = await fetch('/run_cfc_wavelet_analysis', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return handleResponse(res);
}

export async function runHubDetection(params: {
  data_path: string;
  ratio?: number;
  k?: number;
  hub_num?: number;
  use_group?: boolean;
}): Promise<HubDetectionResult> {
  const res = await fetch('/run_hub_detection', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return handleResponse(res);
}

export async function getGrowthCurve(phenotype: string): Promise<{ status: string; phenotype: string; data: GrowthCurveResult['data']; elapsed_seconds: number }> {
  const res = await fetch('/get_growth_curve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phenotype }),
  });
  return handleResponse(res);
}

export async function runNormativeAnalysis(params: {
  x_phenotype: string;
  y_path: string;
  age_col: string;
  val_col: string;
}): Promise<{
  status: string;
  phenotype: string;
  elapsed_seconds: number;
  data: { X: number[]; centiles: number[][]; age: number[]; values: number[] };
}> {
  const res = await fetch('/run_normative_analysis', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return handleResponse(res);
}

export async function parseCSV(filename: string): Promise<{
  status: string;
  filename: string;
  columns: string[];
  rows: string[][];
  total_rows: number;
}> {
  const res = await fetch(`/parse_csv?filename=${encodeURIComponent(filename)}`);
  return handleResponse(res);
}

export async function visualizeBoldAdj(data_path: string, ratio?: number): Promise<BoldAdjResult> {
  const res = await fetch('/visualize_bold_adj', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data_path, ratio }),
  });
  return handleResponse(res);
}
