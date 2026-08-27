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
