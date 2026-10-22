import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
//   npm run dev          React dev server on :5173, /api and /admin proxied to Django on :8000
//   npm run build        dist/        the full app, served by Django at /
export default defineConfig(() => {
  const django = 'http://127.0.0.1:8000'
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': django,
        '/admin': django,
        '/static': django,
      },
    },
  }
})
