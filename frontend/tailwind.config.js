export default {
  content: ['./index.html', './src/**/*.js'],
  
      theme: {
        extend: {
          fontFamily: {
            sans: ['"Plus Jakarta Sans"', 'sans-serif'],
            display: ['"Fredoka"', 'sans-serif'],
          },
          colors: {
            brand: {
              50: '#F0F7FF',
              100: '#E0EFFE',
              200: '#BAE0FD',
              300: '#7CC8FB',
              400: '#38BDF8',
              500: '#0EA5E9',
              600: '#2563EB',
              700: '#1D4ED8',
              800: '#1E40AF',
              900: '#0F172A',
            }
          },
          boxShadow: {
            'soft-blue': '0 20px 50px -12px rgba(37, 99, 235, 0.15)',
            'glow-blue': '0 10px 30px -5px rgba(14, 165, 233, 0.45)',
            'card-blue': '0 8px 30px rgba(37, 99, 235, 0.08)',
          }
        }
      }
    
};
