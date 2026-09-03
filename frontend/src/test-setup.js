// @testing-library/jest-dom — toBeInTheDocument 등 DOM 매처를 expect에 등록한다.
import "@testing-library/jest-dom";

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
