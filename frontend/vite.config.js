import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [
    react({
      // Allow JSX in .js files (CRA was transpiling .js as JSX by default)
      include: '**/*.{jsx,js}',
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'build',
    sourcemap: false,
    chunkSizeWarningLimit: 2000,   // suppress false-positive warning (gzip ~455KB is fine for enterprise app)
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Core vendor libraries
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router-dom')) {
            return 'vendor';
          }
          // Chart library
          if (id.includes('node_modules/recharts') || id.includes('node_modules/d3-') || id.includes('node_modules/victory-')) {
            return 'charts';
          }
          // UI components
          if (id.includes('node_modules/lucide-react') || id.includes('node_modules/@radix-ui') || id.includes('node_modules/class-variance-authority')) {
            return 'ui';
          }
          // Toast notifications
          if (id.includes('node_modules/sonner')) {
            return 'sonner';
          }
          // html2canvas for PDF/print functions
          if (id.includes('node_modules/html2canvas')) {
            return 'html2canvas';
          }
          // DOMPurify
          if (id.includes('node_modules/dompurify')) {
            return 'purify';
          }
        },
      },
    },
  },

  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  // Tell esbuild to parse .js files as JSX
  esbuild: {
    loader: 'jsx',
    include: /src\/.*\.[jt]sx?$/,
    exclude: [],
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        '.js': 'jsx',
      },
    },
  },
})
