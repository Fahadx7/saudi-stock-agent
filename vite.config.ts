import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  // نُحمّل المتغيرات محلياً للاستخدام في الـ build فقط
  // ✅ FIX: لا نُمرّر GEMINI_API_KEY للـ client bundle أبداً
  // المفتاح يُستخدم فقط في server.ts من جهة الـ Backend
  const env = loadEnv(mode, '.', '');

  return {
    plugins: [react(), tailwindcss()],

    // ✅ نُعرّض فقط المتغيرات الآمنة غير السرية للـ Frontend
    define: {
      'import.meta.env.APP_URL': JSON.stringify(env.APP_URL || ''),
      'import.meta.env.FIREBASE_PROJECT_ID': JSON.stringify(
        env.FIREBASE_PROJECT_ID || 'gen-lang-client-0929071098'
      ),
    },

    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },

    server: {
      // HMR معطّل في AI Studio
      hmr: process.env.DISABLE_HMR !== 'true',

      // Proxy لتوجيه طلبات AI من الـ Frontend للـ Backend بأمان
      proxy: {
        '/api': {
          target: 'http://localhost:3000',
          changeOrigin: true,
        },
      },
    },
  };
});
