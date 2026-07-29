import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/* CSP 준수 빌드 — 앱 미들웨어가 `script-src 'self'; style-src 'self'`를 강제한다
 * (app/core/middleware.py). 그래서 인라인 스크립트/스타일·데이터URI 스크립트가 모두 금지다.
 *   - assetsInlineLimit: 0  → 작은 자산을 data:로 인라인하지 않는다.
 *   - modulePreload.polyfill: false → Vite가 넣는 인라인 프리로드 폴리필 스크립트를 없앤다.
 *   - cssCodeSplit: false → CSS를 외부 단일 파일로(인라인 <style> 금지).
 * 결과물은 전부 외부 해시 파일(JS/CSS)이라 self-host + 기존 정적 서빙(/static)에 그대로 맞는다.
 * base: 산출물을 app/static/react/로 빌드해 FastAPI StaticFiles가 그대로 서빙한다. */
export default defineConfig({
  base: "/static/react/",
  plugins: [react()],
  build: {
    outDir: "../app/static/react",
    emptyOutDir: true,
    assetsInlineLimit: 0,
    cssCodeSplit: false,
    modulePreload: { polyfill: false },
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name].[hash].js",
        chunkFileNames: "assets/[name].[hash].js",
        assetFileNames: "assets/[name].[hash][extname]",
      },
    },
  },
});
