import type { Config } from 'tailwindcss';

/**
 * Tokens for an operations console, not a marketing page.
 *
 * Light surface by deliberate choice: Tier-1 agents live in this for a full
 * shift, usually next to a bright ticket system. Severity colours are data —
 * they carry the SLA meaning defined in the triage rubric — so they are named
 * for what they mean, never reused for decoration.
 */
const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        paper: '#F4F6F8',      // app background — cool, not warm cream
        surface: '#FFFFFF',
        ink: '#0F151C',        // near-black with blue in it, not #000
        muted: '#5C6874',
        faint: '#8A95A1',
        line: '#E3E8ED',
        signal: '#1F4FD8',     // the one accent. actions only.
        'signal-soft': '#EDF2FE',
        // Severity = meaning. Mapped to the S1..S4 rubric in the triage prompt.
        s1: '#B3261E',
        s2: '#B45309',
        s3: '#1F4FD8',
        s4: '#5C6874',
        ok: '#0F7B4F',
        warn: '#B45309',
        danger: '#B3261E',
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        // IDs, scores, traces, chunk refs. This platform is trace-heavy; those
        // need to align in columns and be unambiguous to read aloud.
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        micro: ['11px', { lineHeight: '14px', letterSpacing: '0.04em' }],
      },
      borderRadius: { card: '6px' },
    },
  },
  plugins: [],
};
export default config;
