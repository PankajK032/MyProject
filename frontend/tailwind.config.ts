import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './components/**/*.{js,ts,jsx,tsx,mdx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        base: {
          bg: '#14161A',
          surface: '#1C1F26',
          surface2: '#242832',
          border: '#2E333D',
        },
        ink: {
          primary: '#EDEEF0',
          muted: '#8B909C',
          faint: '#5B6070',
        },
        signal: {
          green: '#22C08E',
          greenMuted: '#1A8F6B',
          rust: '#E8604C',
          rustMuted: '#B44835',
          gold: '#E8B339',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui'],
      },
    },
  },
  plugins: [],
};

export default config;
