/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0a0a0c",
        card: "#121216",
        border: "#1d1d26",
        neonCyan: "#00f3ff",
        neonPurple: "#bc13fe",
        success: "#00ff9d",
        error: "#ff4d4d",
        warning: "#ffcc00",
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
