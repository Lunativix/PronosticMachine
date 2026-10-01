/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#071510",
        panel: "#10261c",
        line: "#1f4d38",
        lime: "#c6f54e",
        foam: "#e8f6ee",
      },
    },
  },
  plugins: [],
};
