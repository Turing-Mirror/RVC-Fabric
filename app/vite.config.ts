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
    // 不发 sourcemap。以前是发的，理由是「用户机器上的崩溃栈没有 map 就是
    // 一堆压缩后的字母」—— 那个理由本身没错，但 1.4 MB 的 .map 会跟着界面
    // 补丁一起推给每个用户，而补丁本体才 290 KB。
    //
    // 要重新拿回可读的崩溃栈，别直接改回 true：把 map 留在本地构建产物里、
    // 只在 pack_gui_patch 的打包清单里排除 *.map，两头都能要。
    sourcemap: false,
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
