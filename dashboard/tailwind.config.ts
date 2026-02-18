import type { Config } from "tailwindcss"

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg:      "#0d0f15",
        surface: "#141720",
        panel:   "#181c26",
        border:  "rgba(255,255,255,0.06)",
      },
      fontFamily: {
        sans:  ["Plus Jakarta Sans", "system-ui", "sans-serif"],
        mono:  ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
}

export default config
