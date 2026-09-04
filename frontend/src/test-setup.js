// @testing-library/jest-dom — toBeInTheDocument 등 DOM 매처를 expect에 등록한다.
import "@testing-library/jest-dom";
import { configure } from "@testing-library/react";

/* 🔴 `waitFor` 의 기본 한도는 **1초**다. 이 저장소의 무거운 화면 시험은 jsdom 여덟 개가
 * 동시에 도는 전량 실행에서 그 1초를 넘긴다 — 값이 틀린 것이 아니라 DOM 이 못 따라온
 * 것이고, 그래서 같은 시험이 단독으로는 초록이고 전량에서만 빨갛다(실측: `projects` ·
 * `sprint-meeting` 각 1건, 단독 79건 전부 초록).
 *
 * 그것을 「병렬 부하」로 넘기면 **게이트가 기계 속도로 판정한다.** 그 handwave 뒤에
 * 진짜 결함이 숨어 있던 것을 이 회차가 이미 한 번 봤다(처리되지 않은 오류 38건).
 *
 * 한도를 올리는 것은 단언을 약하게 하지 않는다 — 무엇을 재는지는 그대로이고, 정말로 안
 * 되는 시험은 여전히 실패한다(조금 늦게 실패할 뿐이다). BACKLOG P-75 가 같은 증상을
 * 적어 두었다. */
configure({ asyncUtilTimeout: 5000 });

// jsdom에는 `ResizeObserver`가 없다 — `@tanstack/react-virtual`(VirtualRows)과
// ECharts 감싸개(useEChart.js)가 둘 다 이 생성자를 부른다. 없으면 그 두 부품을 쓰는
// 화면 시험마다 "ResizeObserver is not defined"가 처리되지 않은 거부로 새어 나간다.
//
// 콜백을 한 번도 안 부르는 순수 no-op 이 아니라 관찰을 시작하면(비동기로, microtask)
// 한 번은 현재 크기를 알려준다 — 실제 크기가 바뀌는 경우(창 크기 변화 등)를 재는 시험이
// 있다면 그 시험이 이 mock 에 기대는 자리다. (별개로 겪은, 더 근본적인 결함은
// `ui/kit.jsx::DataTable` 의 콜백 ref 주석 참고 — 조상 DOM 노드를 자손이 첫 렌더에
// 못 보는 문제는 이 mock 이 아니라 그 패턴으로 고쳤다.)
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    constructor(callback) { this.callback = callback; }
    observe(target) {
      queueMicrotask(() => {
        const rect = { width: target.offsetWidth, height: target.offsetHeight, top: 0, left: 0, bottom: 0, right: 0, x: 0, y: 0 };
        this.callback([{ target, contentRect: rect, borderBoxSize: [{ inlineSize: rect.width, blockSize: rect.height }] }], this);
      });
    }
    unobserve() {}
    disconnect() {}
  };
}

/* jsdom 에는 `IntersectionObserver` 가 없다 — 무한 스크롤의 센티넬(`ui/InfiniteScroll.jsx`)이
 * 이 생성자를 부른다.
 *
 * 🔴 **자동으로 교차시키지 않는다.** 진짜로 교차하는 폴리필을 넣으면 목록을 그리는 시험
 * 전부가 마운트 즉시 끝까지 받아 「첫 묶음만 받는다」 자체를 아무도 못 본다 — 그러면 이
 * 기능의 핵심 계약을 검사하는 시험이 하나도 안 남는다.
 *
 * 시험은 둘 중 하나로 「끝까지 굴렸다」를 말한다:
 *   · `await user.click(screen.getByRole("button", { name: "더 보기" }))`  ← 정본.
 *     키보드·스크린리더 사용자가 실제로 쓰는 길이고 IO 가 아예 안 끼어든다.
 *   · `await act(async () => { globalThis.__intersect(); })`               ← 자동 경로. */
/* jsdom 은 `window.scrollTo` 를 «구현 안 됨» 으로 던진다(콘솔에 스택을 통째로 뱉는다).
 * 창 가상화기가 스크롤 보정에서 이것을 부르고(`virtual-core::scrollWithAdjustments`),
 * 조건이 바뀌면 목록 머리로 되돌리는 훅(`lib/useInfiniteList.js`)도 부른다. 실제 스크롤은
 * jsdom 에 레이아웃이 없어 어차피 뜻이 없으므로 **조용한 no-op** 으로 둔다 — 그래야 목록
 * 시험의 출력이 이 스택으로 덮이지 않고, 「되돌렸는가」를 재려는 시험은 이것을 spy 로 감쌀 수
 * 있다(`ResizeObserver` 를 여기서 대신 주는 것과 같은 이유). */
if (typeof window !== "undefined") {
  window.scrollTo = () => {};
}

const __ioInstances = new Set();
if (typeof globalThis.IntersectionObserver === "undefined") {
  globalThis.IntersectionObserver = class IntersectionObserver {
    constructor(callback) { this.callback = callback; this.targets = new Set(); __ioInstances.add(this); }
    observe(target) { this.targets.add(target); }
    unobserve(target) { this.targets.delete(target); }
    disconnect() { this.targets.clear(); __ioInstances.delete(this); }
    takeRecords() { return []; }
  };
}
/** 지금 관찰 중인 센티넬이 전부 「보인다」고 알린다. 시험이 스크롤을 대신하는 손잡이다. */
globalThis.__intersect = () => {
  for (const io of [...__ioInstances]) {
    const entries = [...io.targets].map((target) => ({ target, isIntersecting: true, intersectionRatio: 1 }));
    if (entries.length) io.callback(entries, io);
  }
};

/* jsdom 은 레이아웃이 없어 `offsetWidth`/`offsetHeight` 가 항상 0 이다 — `VirtualRows`/
 * `VirtualTableBody`(`@tanstack/react-virtual`)의 초기 측정과 `measureElement` 재측정이
 * 이 값을 그대로 읽어, 손대지 않으면 가상화 계산이 항상 빈 뷰포트(0px)로 떨어져 화면에
 * 아무 행도 없는 것처럼 보인다(REAUDIT §15.1 — WorkBoard 백로그·판 열에 실제로 얹은 뒤
 * 기존 시험 여럿이 이 이유로 카드를 못 찾았다). 시험 파일마다 각자 값을 주게 두면 백로그·
 * 판·티켓 표를 함께 렌더하는 시험마다 이 mock 을 반복해야 한다 — 한 곳에서 대신 준다.
 * `data-index` 가 붙은 요소(가상 목록의 각 행)는 40px, 그 밖(스크롤 창 자신 등)은
 * 400px — 실제 값은 화면마다 다르지만, 시험에서 중요한 것은 «몇 픽셀인가» 가 아니라
 * «0 이 아니어서 가상화기가 보이는 범위를 실제로 계산하는가» 다. */
Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
  configurable: true,
  get() { return this.hasAttribute("data-index") ? 40 : 400; },
});
Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
  configurable: true,
  get() { return this.hasAttribute("data-index") ? 800 : 800; },
});

/* jsdom 에는 **캔버스 2D 컨텍스트가 없다.** `getContext` 를 부르면 「Not implemented」를
 * 콘솔에 뱉고 `null` 을 돌려준다. 축포(`ui/celebrate.js` → canvas-confetti)가 그 null 에
 * `clearRect` 를 부르는 순간 **처리되지 않은 오류**가 나고, 그것이 rAF 타이머 안이라
 * 어느 시험이 낸 것인지도 안 보인다(실제로 「98건 초록 + 오류 1」로 나타났다).
 *
 * 축포를 **재는** 시험은 각자 `vi.mock("canvas-confetti")` 로 모듈을 통째로 대신하므로 이
 * stub 을 안 지난다. 여기서 채우는 것은 축하를 재지 않는 화면(문서 목록 등)이 축하를 부르는
 * 코드를 그냥 지나가게 하려는 것이다 — `ResizeObserver` 를 여기서 대신 주는 것과 같은 이유다.
 *
 * 그림을 검사하는 시험이 없으므로 **아무것도 그리지 않는** no-op 이면 충분하다. 메서드를
 * 하나씩 적지 않고 Proxy 로 받는다: 라이브러리가 부르는 목록이 판마다 다르고, 하나 빠지면
 * 증상이 다시 「타이머 안의 정체불명 오류」이기 때문이다. 값을 쓰는 자리(fillStyle 등)는
 * 그대로 저장된다. */
if (typeof HTMLCanvasElement !== "undefined") {
  HTMLCanvasElement.prototype.getContext = function getContext() {
    const store = new Map();
    return new Proxy(
      { canvas: this },
      {
        get(target, key) {
          if (key === "canvas") return target.canvas;
          if (store.has(key)) return store.get(key);
          /* 🔴 `measureText` 만은 no-op 이면 안 된다. ECharts 의 zrender 가 돌려받은
             값에서 곧바로 `.width` 를 읽어(`ensureFontMeasureInfo`) `undefined` 면
             처리되지 않은 거부가 난다 — 전량 실행에서 25건이 그것이었고, 시험은 하나도
             안 깨진 채 vitest 만 exit 1 이 됐다. 이 Proxy 를 둔 이유가 바로 그
             「하나 빠지면 타이머 안의 정체불명 오류」다(위 머리말).

             jsdom 에는 글꼴이 없어 진짜 폭을 잴 수 없다. 글자 수에 비례한 값을 준다 —
             그림을 검사하는 시험이 없으므로 「0 이 아니고 글자가 길수록 크다」면 충분하다. */
          if (key === "measureText") {
            return (text) => ({
              width: String(text ?? "").length * 8,
              actualBoundingBoxAscent: 8,
              actualBoundingBoxDescent: 2,
            });
          }
          // 모르는 이름은 전부 no-op 함수다 — 그리기 호출이 조용히 지나간다.
          return () => undefined;
        },
        set(target, key, value) {
          store.set(key, value);
          return true;
        },
      }
    );
  };
}

/* jsdom 에는 **`Range` 의 레이아웃 API 가 없다** — `Range.prototype.getClientRects` 와
 * `getBoundingClientRect` 둘 다 `undefined` 다(Element 쪽에는 있다). 그런데 ProseMirror 가
 * 커서 위치를 재려고 그것을 부른다:
 *
 *   singleRect(target) → target.getClientRects()   ← prosemirror-view/dist/index.js
 *   coordsAtPos → scrollToSelection → updateStateInner → Editor.dispatchTransaction
 *
 * 그래서 본문 편집기를 그리는 시험이 **처리되지 않은 오류**를 남긴다. 전량 실행에서 38건이
 * 났고 시험은 하나도 안 깨졌다 — 오류가 편집기 트랜잭션 뒤 타이머에서 나기 때문에 어느
 * 시험의 것인지도 안 보인다(파일 단독 실행에서는 그 타이머가 정리 전에 끝나 안 난다).
 * 그 38건이 vitest 를 exit 1 로 만들어 **전량 게이트가 실패 0 인데도 빨갛다.**
 *
 * 🔴 이 stub 이 무엇을 숨기지 않는 이유: jsdom 에는 레이아웃 엔진이 자체가 없어서
 * Element 쪽 `getBoundingClientRect` 도 이미 전부 0 을 돌려준다. 여기서 0 을 돌려주는 것은
 * 거짓말이 아니라 **같은 사실을 같은 모양으로** 말하는 것이다. 커서 좌표를 재는 시험은
 * 없다(있다면 jsdom 이 아니라 실브라우저에서 재야 한다).
 *
 * `elementFromPoint` 도 같은 이유로 없다 — ProseMirror 의 `posAtCoords` 가 부른다. */
if (typeof Range !== "undefined" && !Range.prototype.getClientRects) {
  const emptyRect = () => ({
    x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0,
    toJSON() { return this; },
  });
  Range.prototype.getClientRects = function getClientRects() {
    const list = [];
    list.item = (i) => list[i] ?? null;
    return list;
  };
  Range.prototype.getBoundingClientRect = emptyRect;
}
if (typeof document !== "undefined" && !document.elementFromPoint) {
  document.elementFromPoint = () => null;
}
