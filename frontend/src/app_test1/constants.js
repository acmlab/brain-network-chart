export const ANALYSIS_METHODS = {
  cfc_wavelet: {
    name: 'CFC Wavelet Analysis',
    description: 'Cross-Frequency Coupling using Harmonic Wavelets',
    config: {
      window: 50,
      step: 3,
      padding: false,
      ratio: 0.1,
      wavelets_num: 10,
      beta: 1.0,
      gamma: 0.1,
      max_iter: 100,
      min_err: 0.000001,
      node_select: 10,
    },
  },
  hub_detection: {
    name: 'Hub Detection',
    description: 'Detect hub nodes in brain networks using Grassmann manifold optimization',
    config: {
      window: 50,
      step: 3,
      padding: false,
      ratio: 0.1,
      k: 2,
      hub_num: 10,
      use_group: false,
    },
  },
};
