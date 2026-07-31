import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#FAF7F1",
        paper: "#FFFFFF",
        ink: "#2B2B28",
        muted: "#8A8478",
        border: "#E4DED2",
        green: {
          900: "#17332A",
          800: "#1E4438",
          700: "#295C4C",
          600: "#357561",
          500: "#4A9078",
          100: "#E4EEE8",
        },
      },
      fontFamily: {
        sans: ["var(--font-rubik)", "sans-serif"],
        display: ["var(--font-telaviv)", "var(--font-rubik)", "sans-serif"],
      },
      borderRadius: { xl2: "1rem" },
    },
  },
  plugins: [],
};
export default config;
