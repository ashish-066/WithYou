/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      // Old dashboard palette; removed with the old pages (rebuild step 7)
      colors: {
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
        // New UI: values live in src/ui/tokens.css and switch with [data-area]
        canvas: token('bg'),
        surface: token('surface'),
        sunken: token('sunken'),
        line: { DEFAULT: token('line'), strong: token('line-strong') },
        ink: token('ink'),
        muted: token('muted'),
        accent: { DEFAULT: token('accent'), on: token('on-accent') },
        good: token('good'),
        warn: token('warn'),
        bad: token('bad'),
      },
      fontFamily: {
        display: ['var(--font-display)'],
        ui: ['var(--font-ui)'],
        mono: ['var(--font-mono)'],
      },
      // 13 / 14 / 16 / 20 / 28 / 40
      fontSize: {
        meta: ['13px', { lineHeight: '18px' }],
        body: ['14px', { lineHeight: '21px' }],
        lead: ['16px', { lineHeight: '24px' }],
        h3: ['20px', { lineHeight: '26px', letterSpacing: '-0.005em' }],
        h2: ['28px', { lineHeight: '34px', letterSpacing: '-0.01em' }],
        h1: ['40px', { lineHeight: '44px', letterSpacing: '-0.015em' }],
      },
      borderRadius: { ui: 'var(--radius)' },
      maxWidth: { content: 'var(--content)' },
      width: { sidebar: 'var(--sidebar)' },
    },
  },
  plugins: [],
};
