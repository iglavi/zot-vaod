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
          900: "#0C2626",
          800: "#103636",
          700: "#154545",
          600: "#1C5D5D",
          500: "#257979",
          100: "#E0F5F5",
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
