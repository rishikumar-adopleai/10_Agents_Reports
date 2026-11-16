/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f7ff',
          100: '#e0effe',
          200: '#b9ddfd',
          300: '#7cc2fb',
          400: '#36a3f7',
          500: '#0d86eb',
          600: '#026ac9',
          700: '#0354a2',
          800: '#074885',
          900: '#0c3d6e',
          950: '#08274a',
        },
      },
    },
  },
  plugins: [],
}
