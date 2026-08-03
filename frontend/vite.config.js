import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/* CSP 준수 빌드 — 앱 미들웨어가 `script-src 'self'`를 강제한다(app/core/middleware.py).
 * 그래서 인라인 스크립트·데이터URI 스크립트가 금지다.
 *   - assetsInlineLimit: 0  → 작은 자산을 data:로 인라인하지 않는다.
 *   - modulePreload.polyfill: false → Vite가 넣는 인라인 프리로드 폴리필 스크립트를 없앤다.
 *   - cssCodeSplit: false → CSS를 외부 단일 파일로.
 * (style-src는 MUI/Emotion 때문에 'unsafe-inline'을 허용하지만, 빌드 산출물 자체는 계속
 *  외부 파일만 쓴다 — 완화에 기대지 않는다.)
 * base: 산출물을 app/static/react/로 빌드해 FastAPI StaticFiles가 그대로 서빙한다.
 *
 * manualChunks: MUI를 들이면서 단일 번들이 900kB에 육박했다. 사내 LAN이라 절대 크기보다
 * '배포마다 전부 다시 받는' 게 문제다 — react/mui는 거의 안 바뀌므로 분리해 두면 앱 코드만
 * 바뀌는 배포에서 브라우저 캐시가 살아남는다. */
export default defineConfig({
  base: "/static/react/",
  plugins: [react()],
  build: {
    outDir: "../app/static/react",
    emptyOutDir: true,
    assetsInlineLimit: 0,
    cssCodeSplit: false,
    modulePreload: { polyfill: false },
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name].[hash].js",
        chunkFileNames: "assets/[name].[hash].js",
        assetFileNames: "assets/[name].[hash][extname]",
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("@mui") || id.includes("@emotion")) return "mui";
          if (id.includes("react-dom") || id.includes("/react/") || id.includes("scheduler")) return "react";
          if (id.includes("@tanstack")) return "query";
          return "vendor";
        },
      },
    },
  },
});
