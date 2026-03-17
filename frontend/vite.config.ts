import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    watch:{usePolling: true,
      interval: 1000,},
    proxy: {
      '/upload': 'http://127.0.0.1:8004',
      '/list_files': 'http://127.0.0.1:8004',
      '/delete_file': 'http://127.0.0.1:8004',
      '/run_correlation': 'http://127.0.0.1:8004',
      '/run_group_comparison': 'http://127.0.0.1:8004',
      '/apply_fdr_correction': 'http://127.0.0.1:8004',
      '/detect_outliers': 'http://127.0.0.1:8004',
      '/run_cfc_wavelet_analysis': 'http://127.0.0.1:8004',
      '/run_hub_detection': 'http://127.0.0.1:8004',
      '/get_growth_curve': 'http://127.0.0.1:8004',
      '/run_normative_analysis': 'http://127.0.0.1:8004',
      '/parse_csv': 'http://127.0.0.1:8004',
      '/roi_figs': 'http://127.0.0.1:8004',
      '/visualize_bold_adj': 'http://127.0.0.1:8004',
      '/get_phenotypes': 'http://127.0.0.1:8004',
      '/run_bids_conversion': 'http://127.0.0.1:8004',
      '/bids_report': 'http://127.0.0.1:8004',
    },
  },
})
