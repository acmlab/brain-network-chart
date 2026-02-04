/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
      },
      colors: {
        slate: {
          850: '#172033',
          950: '#0f1629',
        },
      },
      boxShadow: {
        'glow': '0 0 40px -12px rgba(99, 102, 241, 0.35)',
        'panel': '0 4px 24px -4px rgba(0,0,0,0.08), 0 8px 16px -8px rgba(0,0,0,0.04)',
      },
    },
  },
  plugins: [],
}