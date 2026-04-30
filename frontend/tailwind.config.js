/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        council: {
          slate: '#64748b',
          dark: '#1e293b',
          light: '#f1f5f9',
        },
      },
    },
  },
  plugins: [],
}
