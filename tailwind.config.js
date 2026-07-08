/** Tailwind config — compiles a purged CSS asset (no CDN runtime). ADR-003 mobile-first.
 *
 * Visual language = "Variant C · Cobalt Clean-Fintech" (DA DESIGN LOCKED 2026-07-08).
 * Colours are wired to CSS variables (see static/css/input.css :root) so DF-10 runtime
 * theming is a LATER config layer (swap the variables / a data-theme attribute), NOT a
 * rewrite. Utilities reference the tokens by name (bg-cobalt-600, text-ink-500, …).
 */
const withVar = (name) => `var(${name})`;

module.exports = {
  // Scan templates AND the JS that builds markup at runtime (the Referral Profile
  // Clicks table + rings), so classes emitted from JS aren't purged.
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        // Ink (text) ramp.
        ink: {
          900: withVar("--c-ink-900"),
          700: withVar("--c-ink-700"),
          500: withVar("--c-ink-500"),
          300: withVar("--c-ink-300"),
        },
        // Surfaces / lines.
        line: withVar("--c-line"),
        bg: withVar("--c-bg"),
        // Primary accent — cobalt.
        cobalt: {
          600: withVar("--c-cobalt-600"),
          500: withVar("--c-cobalt-500"),
          50: withVar("--c-cobalt-50"),
        },
        // Semantic tokens (accounts=positive, leads=pending, bot/error).
        positive: withVar("--c-positive"),
        pending: withVar("--c-pending"),
        danger: withVar("--c-danger"),
      },
      boxShadow: {
        // The Variant C card shadow token.
        card: "0 1px 2px rgba(16,23,41,.04), 0 8px 24px -12px rgba(16,23,41,.12)",
      },
      fontFamily: { sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"] },
    },
  },
  // Utilities built dynamically (funnel bar widths, ring/badge colours chosen in
  // {% if %}) are safelisted so the purge keeps them.
  safelist: [
    {
      pattern:
        /^(bg|text|ring|border)-(cobalt|ink|line|bg|positive|pending|danger|emerald|amber|sky|indigo|rose|slate|green)-(50|100|200|300|400|500|600|700)$/,
    },
    { pattern: /^(bg|text|border)-(line|bg|positive|pending|danger)$/ },
    { pattern: /^rounded-(full|2xl|xl)$/ },
  ],
  plugins: [],
};
