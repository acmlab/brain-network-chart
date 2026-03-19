export interface FileInfo {
  filename: string;
  size: number;
  upload_time: string;
  is_dir?: boolean;
}

export interface CorrelationResult {
  test: string;
  correlation: number;
  p_value: number;
  significant: boolean;
  n_samples: number;
  'Explanation of results': string;
}

export interface GroupComparisonResult {
  test_used: string;
  statistic: number;
  p_value: number;
  significant: boolean;
  mean_group_1: number;
  mean_group_2: number;
  cohens_d: number;
  effect_size: string;
  'Explanation of results': string;
  group_a: string;
  group_b: string;
}

export interface FDRResult {
  test: string;
  original_p_values: number[];
  corrected_p_values: number[];
  significant_after_correction: boolean[];
  'Explanation of results': string;
}

export interface OutlierResult {
  test: string;
  total_samples: number;
  outlier_count: number;
  outlier_indices: number[];
  outlier_values: number[];
  'Explanation of results': string;
}

export interface CFCWaveletResult {
  status: string;
  data_path: string;
  window_size: number;
  step_size: number;
  num_windows: number;
  cfcs_count: number;
  cfcs: number[][][];
  avg_cfc?: number[][];
  files_cfcs?: { filename: string; cfcs: number[][][] }[];
  files_avg_cfcs?: { filename: string; avg_cfc: number[][] }[];
  elapsed_seconds: number;
  console_output: string;
  progress: { step: string; message: string }[];
}

export interface HubDetectionResult {
  status: string;
  data_path: string;
  num_windows: number;
  k: number;
  hub_num: number;
  use_group: boolean;
  results: {
    method: string;
    hub_nodes?: number[];
    results?: { graph_index: number; hub_nodes: number[] }[];
  };
  elapsed_seconds: number;
  console_output: string;
  progress: { step: string; message: string }[];
  roi_list?: { code: string; name: string }[];
}

export interface BoldAdjResult {
  status: string;
  data_path: string;
  adj_matrices: number[][][];  // list of (nodes, nodes) binary matrices
  num_nodes: number;
  num_windows: number;
  ratio: number;
  roi_list?: { code: string; name: string }[];
}

export interface GrowthCurveResult {
  status: string;
  phenotype: string;
  data: { X: number[]; centiles: number[][] };
  elapsed_seconds: number;
  overlay?: { age: number[]; values: number[] };
}

export interface BidsConversionResult {
  status: string;
  data_dir: string;
  output_dir: string;
  n_nii: number;
  n_errors: number;
  n_warnings: number;
  elapsed_seconds: number;
  console_output: string;
  progress: { step: string; message: string }[];
  report_html: string | null;
  return_code: number;
  pending?: boolean;
  stream_url?: string;
}

export type ResultItem =
  | { id: string; type: 'correlation'; timestamp: string; data: CorrelationResult }
  | { id: string; type: 'group_comparison'; timestamp: string; data: GroupComparisonResult }
  | { id: string; type: 'fdr_correction'; timestamp: string; data: FDRResult }
  | { id: string; type: 'outliers'; timestamp: string; data: OutlierResult }
  | { id: string; type: 'cfc_wavelet'; timestamp: string; data: CFCWaveletResult }
  | { id: string; type: 'hub_detection'; timestamp: string; data: HubDetectionResult }
  | { id: string; type: 'growth_curve'; timestamp: string; data: GrowthCurveResult }
  | { id: string; type: 'bold_adj'; timestamp: string; data: BoldAdjResult }
  | { id: string; type: 'bids_conversion'; timestamp: string; data: BidsConversionResult; onComplete?: () => void };
