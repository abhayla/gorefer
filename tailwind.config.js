/** Tailwind config — compiles a purged CSS asset (no CDN runtime). ADR-003 mobile-first. */
module.exports = {
  content: ["./templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        pifs: {
          900: "#1b2e1f", 800: "#233d29", 700: "#2f5136", 600: "#3d6a45",
          500: "#4e8256", 400: "#6fa377", 100: "#eaf1ea", 50: "#f4f8f4",
        },
        gold: "#c8a24a",
      },
      fontFamily: { sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"] },
    },
  },
  // Utilities built dynamically (funnel bar widths, badge colours in {% if %}) —
  // safelisted so the purge keeps them.
  safelist: [
    { pattern: /^(bg|text|ring|border)-(pifs|gold|emerald|amber|blue|red|slate)-(50|100|200|300|400|500|600|700)$/ },
    { pattern: /^w-\[\d+%\]$/ },
  ],
  plugins: [],
};
