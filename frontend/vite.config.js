import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', // accesible desde fuera del contenedor (y desde el celular por WiFi)
    port: 5173,
    watch: {
      usePolling: true, // necesario en Windows para detectar cambios dentro de Docker
    },
    // La pantalla le pide todo a /api de esta misma dirección y Vite se lo pasa al backend por la red
    // interna de Docker. Así funciona igual desde la PC (localhost) y desde un celular por WiFi
    // (http://IP-de-la-PC:5173), sin cambiar nada cuando cambia la IP y con un solo puerto abierto.
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        // Django solo acepta pedidos dirigidos a «localhost» (DJANGO_ALLOWED_HOSTS)
        headers: { Host: 'localhost' },
      },
    },
  },
})
