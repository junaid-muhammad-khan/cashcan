import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Everything goes through the Vite origin (5173) so the session cookie and the Auth0 callback
// share one origin. Django runs on 8000.
const django = { target: "http://localhost:8000", changeOrigin: false };

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": django, "/auth": django, "/admin": django, "/static": django } },
});
