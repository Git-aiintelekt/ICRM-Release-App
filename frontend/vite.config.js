import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
//   npm run dev          React dev server on :5173, /api and /admin proxied to Django on :8000
//   npm run build        dist/        the full app, served by Django at /
//   npm run build:ofbiz  dist-ofbiz/  the read-only viewer packaged into the OFBiz component
//                                    (assets served by OFBiz from /release-notes-resource/)
export default defineConfig(({ mode }) => {
  const ofbiz = mode === 'ofbiz'
  const django = 'http://127.0.0.1:8000'
  return {
    plugins: [react()],
    base: ofbiz ? '/release-notes-resource/' : '/',
    build: {
      outDir: ofbiz ? 'dist-ofbiz' : 'dist',
      emptyOutDir: true,
    },
    server: {
      proxy: {
        '/api': django,
        '/admin': django,
        '/static': django,
      },
    },
  }
})
