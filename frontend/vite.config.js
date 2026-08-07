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
          /* 두 콘솔이 **같이** 쓰는 설정 주도 화면 부품에 이름을 준다.
           *
           * 이름이 필요한 이유는 크기가 아니라 예산 검사다. 이 조각은 사용자·관리자 라우트가
           * 둘 다 import 해서 rollup 이 알아서 공용 청크로 뺀다 — 그런데 그때 붙는 이름은
           * 그 안의 아무 모듈 이름(`notifications`)이고, 모듈이 하나 늘고 줄 때마다 바뀐다.
           * 그러면 `scripts/check_bundle_size.sh` 가 이 청크를 '초기 로드'로 잘못 세어
           * 예산이 20KB 넘게 부풀어 보인다(실제로는 라우트에 들어갈 때 받는다).
           *
           * registry 의 **나머지** 도메인 파일은 여기 넣지 않는다. 그것들이 다시 한 덩어리가
           * 되는 순간 PF7 이 되돌아온다 — 사용자 콘솔이 관리자 설정을 통째로 받는다. */
          if (
            id.includes("/src/screens/registry/shared.js") ||
            id.includes("/src/screens/registry/actions.js") ||
            id.includes("/src/screens/registry/notifications.js")
          ) return "datascreen";
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
