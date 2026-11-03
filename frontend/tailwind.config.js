/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        municipal: {
          50: '#f0f7ff',
          100: '#e0effe',
          200: '#bae0fd',
          300: '#7cc7fb',
          400: '#36a9f6',
          500: '#0c8de5',
          600: '#016ec3',
          700: '#02589e',
          800: '#064a82',
          900: '#0b3f6d',
          950: '#072848',
        },
        civicGold: {
          500: '#d97706',
          600: '#b45309',
        }
      },
    },
  },
  plugins: [],
};
