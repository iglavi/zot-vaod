import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#FAF7F1",
        paper: "#FFFFFF",
        ink: "#2B2B28",
        muted: "#6B665C",
        border: "#E4DED2",
        // "green" is a legacy key name - value ramp is now built around the
        // requested brand color #2F5F69 (700, the shade used for primary
        // buttons/links/active nav) - see Tikunim.txt item 21.
        green: {
          900: "#152B2F",
          800: "#21434A",
          700: "#2F5F69",
          600: "#4E7780",
          500: "#78979E",
          100: "#EAEFF0",
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
