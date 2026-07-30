import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import type { Plugin } from "vite";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;

/**
 * Production UI is served via custom protocol `fabric://` (swappable frontend/).
 * Absolute `/assets/...` + `crossorigin` breaks on Windows WebView2 custom
 * schemes (CORS / wrong origin) → blank white window. Relative base + no
 * crossorigin keeps scripts loadable from fabric:// and http://fabric.localhost.
 */
function stripCrossorigin(): Plugin {
  return {
    name: "strip-crossorigin",
    enforce: "post",
    transformIndexHtml(html) {
      return html.replace(/\s+crossorigin(?:="[^"]*")?/gi, "");
    },
  };
}

// https://vite.dev/config/
export default defineConfig(async () => ({
  plugins: [react(), tailwindcss(), stripCrossorigin()],

  // Relative asset URLs so custom-protocol pages resolve next to index.html.
  base: "./",

  // Ship UI as a replaceable `frontend/` pack (see tauri.conf frontendDist).
  build: {
    // Shipped: the shell forwards UI crashes into shell.log, and without maps
    // a stack from a user's machine is nothing but minified letters. ~1.3 MB
    // of .map next to a 290 KB bundle is worth being able to read a report.
    sourcemap: true,
    outDir: "frontend",
    emptyOutDir: true,
  },

  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
}));
