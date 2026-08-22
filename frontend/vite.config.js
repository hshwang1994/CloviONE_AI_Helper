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
          /* 공용 UI 부품은 **자기 청크**를 갖는다.
           *
           * 이게 없으면 `ui/kit.jsx` 가 아래 `datascreen` 청크로 빨려 들어간다 — 셸(초기
           * 로드)과 설정 주도 화면(지연)이 둘 다 kit 을 쓰기 때문이다. 그러면 셸이 kit 을
           * 받으려고 `datascreen` 청크 전체(DataScreen + registry 셋, gzip 37KB)를 함께
           * 받는다. 실측으로 초기 예산 280KB 를 넘긴 원인이 정확히 이것이었다.
           *
           * kit 은 셸이 어차피 첫 화면에 쓰므로 초기 로드에 남는 것이 맞다 — 함께 끌려오던
           * 관리자 설정 스물여덟 화면분 설정만 떼어 낸다. */
          if (
            id.includes("/src/ui/kit.jsx") ||
            id.includes("/src/ui/theme.js") ||
            id.includes("/src/ui/density.js") ||
            id.includes("/src/ui/cells.jsx") ||
            id.includes("/src/ui/motion.js") ||
            /* 셸이 첫 화면에 쓰는 배선(내비 표·역할 표·포맷). 이것도 이름이 없으면 아래
               `datascreen` 으로 빨려 들어간다 — 지연 화면들과 공유되기 때문이다. */
            id.includes("/src/app/navConfig.js") ||
            id.includes("/src/app/navIcons.js") ||
            id.includes("/src/lib/roles.js") ||
            id.includes("/src/lib/format.js")
          ) return "kit";
          if (
            id.includes("/src/screens/registry/shared.js") ||
            id.includes("/src/screens/registry/actions.js") ||
            id.includes("/src/screens/registry/notifications.js")
          ) return "datascreen";
          if (!id.includes("node_modules")) return undefined;
          /* react·emotion·query 만 이름을 준다 — 셋 다 **첫 화면이 어차피 쓰고** 거의 안
             바뀌는 것들이라, 이름을 고정해 두면 앱 코드만 바뀌는 배포에서 브라우저 캐시가
             살아남는다.
             나머지 node_modules 는 이름을 주지 않는다. 예전에는 `return "vendor"` 로 전부
             한 덩어리였고, MUI 도 `"mui"` 한 덩어리였다 — 그러면 셸이 MUI 의 일부(Drawer·
             AppBar)를 쓴다는 이유로 **표·모달·차트까지 포함한 전부**가 초기 로드에 들어온다.
             실측: 초기 gzip 288KB(예산 280KB) 중 MUI 만 110KB. 이름을 안 주면 rollup 이
             쓰는 화면 쪽으로 갈라 준다. */
          if (id.includes("@emotion")) return "emotion";
          /* ⚠️ **패키지 경로로 정확히 짚는다.** 예전에는 `id.includes("/react/")` 였고,
             그것은 이름에 `react` 가 들어간 **모든 패키지**를 초기 청크로 끌어왔다.
             S7 이 `@tiptap/react` 를 들이자 그 한 줄이 TipTap 과 ProseMirror 전부를
             `react` 청크에 넣었다 — 편집기를 `React.lazy` 로 뺀 것이 아무 소용이 없어졌고,
             초기 예산이 gzip 348KB(예산 280KB)로 넘어갔다. **오류는 안 났다.**
             `node_modules/react/` 는 그 패키지 자신만 맞는다(중첩 설치도 같은 모양이다). */
          if (
            id.includes("node_modules/react-dom/")
            || id.includes("node_modules/react/")
            || id.includes("node_modules/scheduler/")
          ) return "react";
          if (id.includes("@tanstack")) return "query";
          return undefined;
        },
      },
    },
  },
});
