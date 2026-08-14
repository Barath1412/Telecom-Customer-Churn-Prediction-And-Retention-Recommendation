import type { Config } from 'tailwindcss'

/**
 * DESIGN TOKENS LIVE HERE AND NOWHERE ELSE.
 *
 * The visual brief is "a tool an operations team already uses", not "an AI
 * product". Practically that means: one accent colour, a warm neutral ramp
 * instead of pure grey, a 4px spacing grid, no gradients, no glass, no
 * rounded-3xl cards, no purple. Density over whitespace — an agent scans 40
 * rows before they make a call.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Warm neutrals. Pure #fff / #000 are deliberately absent: they read as
        // a template, and they blow out contrast on cheap office monitors.
        canvas: '#f7f7f5',
        surface: '#fcfcfb',
        raised: '#f0efec',
        line: '#dedcd6',
        'line-strong': '#c2c0b8',
        ink: '#0b0b0b',
        'ink-2': '#52514e',
        'ink-3': '#78776f',
        accent: '#2a78d6',
        // Risk bands. These four are semantic, not decorative — never reuse
        // them for anything that is not a risk level.
        critical: '#b3261e',
        high: '#c05621',
        medium: '#8a6d00',
        low: '#2f6f3e',
        ok: '#008300',
        warn: '#eda100',
        danger: '#e34948',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        // Every number on screen is tabular. Money that jitters between rows
        // is money an agent misreads.
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        micro: ['11px', { lineHeight: '15px', letterSpacing: '0.06em' }],
        xs: ['12px', { lineHeight: '17px' }],
        sm: ['13px', { lineHeight: '19px' }],
        base: ['15px', { lineHeight: '23px' }],
        lg: ['17px', { lineHeight: '25px' }],
        xl: ['21px', { lineHeight: '28px' }],
        '2xl': ['27px', { lineHeight: '33px' }],
      },
      borderRadius: { DEFAULT: '6px', md: '7px', lg: '9px' },
      spacing: { 18: '4.5rem', 88: '22rem' },
      boxShadow: {
        card: '0 1px 2px rgba(11,11,11,.04)',
        pop: '0 6px 24px rgba(11,11,11,.10)',
      },
    },
  },
  plugins: [],
} satisfies Config
