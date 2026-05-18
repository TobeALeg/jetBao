/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      colors: {
        ink: "#10231f",
        accent: "#0f766e"
      },
      boxShadow: {
        line: "0 1px 0 rgba(15, 23, 42, 0.06)"
      }
    }
  },
  plugins: []
};

