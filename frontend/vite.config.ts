import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    watch:{usePolling: true,
      interval: 1000,},
    proxy: {
      '/upload': 'http://127.0.0.1:8005',
      '/list_files': 'http://127.0.0.1:8005',
      '/delete_file': 'http://127.0.0.1:8005',
      '/run_correlation': 'http://127.0.0.1:8005',
      '/run_group_comparison': 'http://127.0.0.1:8005',
      '/apply_fdr_correction': 'http://127.0.0.1:8005',
      '/detect_outliers': 'http://127.0.0.1:8005',
      '/run_cfc_wavelet_analysis': 'http://127.0.0.1:8005',
      '/run_hub_detection': 'http://127.0.0.1:8005',
      '/get_growth_curve': 'http://127.0.0.1:8005',
      '/run_normative_analysis': 'http://127.0.0.1:8005',
      '/parse_csv': 'http://127.0.0.1:8005',
      '/roi_figs': 'http://127.0.0.1:8005',
      '/visualize_bold_adj': 'http://127.0.0.1:8005',
      '/get_phenotypes': 'http://127.0.0.1:8005',
      '/run_bids_conversion': 'http://127.0.0.1:8005',
      '/run_bids_conversion_stream': 'http://127.0.0.1:8005',
      '/bids_report': 'http://127.0.0.1:8005',
      '/run_command_stream': 'http://127.0.0.1:8005',
      '/health': 'http://127.0.0.1:8005',
      '/sse': 'http://127.0.0.1:8005',
      '/messages': 'http://127.0.0.1:8005',
    },
  },
})
