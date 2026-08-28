import React from "react";

/* ECharts 얇은 훅 (§15.2 재검수) — init · setOption · ResizeObserver · dispose · 테마 주입.
 *
 * ## 왜 `echarts-for-react` 를 안 쓰는가
 *
 * 유지되지 않는 3rd party 감싸개에 기대는 대신, 이 저장소가 이미 아는 관용(테마 토큰 주입,
 * 지연 로드, ResizeObserver)을 그대로 여기 한 곳에 적는다. 커밋된 번들에 넣는 코드라
 * 남의 패키지가 몇 달 업데이트를 멈춰도 이 저장소가 직접 고칠 수 있다.
 *
 * ## `echarts/core` + 트리셰이킹
 *
 * `import "echarts"` 전체를 받으면 컴포넌트당 200KB 가 넘는다. 이 파일은 **동적 import**로
 * 필요한 조각만 가져온다 — `check_bundle_size.sh` 가 재는 진입 번들에는 안 들어가고,
 * 문서를 열 때만 받는 편집기 청크와 같은 배치다(§15.8).
 *
 * ## `SVGRenderer` 를 명시적으로 고르는 이유
 *
 * 기본 렌더러는 canvas 다. 이 저장소의 대비·마스코트·캡처 프로브(`scripts/ui_qa/*.py`)가
 * DOM 을 읽는데, canvas 안 픽셀은 DOM 이 아니다 — 그대로 두면 그 프로브들이 그림을 아예
 * 못 본다. `SVGRenderer` 를 고르면 ECharts 가 진짜 `<svg>`/`<path>`/`<text>` 를 그린다.
 *
 * ## 글자는 여전히 바깥 HTML 이 낸다
 *
 * ECharts 자신의 축 눈금·범례는 **끈다**(옵션에서 `show:false`). 그 글자들은
 * SVG `<text>` 로 그려지는데, SVG 텍스트는 `font-size` 가 px 고정이라 `styles/root.css` 의
 * 4K 폰트 레버(16→18→20px)를 못 따른다 — 이 저장소가 손으로 그린 옛 차트가 처음부터
 * 그 이유로 모든 글자를 SVG 밖에 뒀다(`charts/base.jsx` 문서 참고). ECharts 로 옮긴 뒤에도
 * 그 규칙은 그대로다: ECharts 는 **선·막대·호(그림)** 만 그리고, 범례·직접 라벨·요약
 * 문장은 여전히 각 차트 컴포넌트의 HTML 오버레이가 낸다. dataZoom(§15.2 가 ECharts를
 * 고른 핵심 이유 하나)만 예외다 — 그 미니맵은 픽셀 몇 개짜리 UI 라 4K 레버 영향이
 * 실사용에 안 보이고, 끄면 이 라이브러리를 쓰는 이유 자체가 없어진다.
 *
 * ## 시험은 option 객체를 겨눈다 (§18.2)
 *
 * 이 훅 자체는 렌더링(부수효과)만 한다 — 무엇을 그릴지는 각 차트 파일이 순수 함수
 * (`lineSeriesOption`처럼)로 미리 계산해 그 **객체**를 여기 넘긴다. 시험은 그 순수 함수를
 * 직접 불러서 값만 본다 — jsdom 에서 실제 SVG 렌더를 기다리지 않는다.
 */

let echartsCorePromise = null;

/** 필요한 모듈만 한 번 모아 등록한다. 여러 차트 컴포넌트가 동시에 마운트돼도 등록은 한 번. */
function loadECharts() {
  if (!echartsCorePromise) {
    echartsCorePromise = Promise.all([
      import("echarts/core"),
      import("echarts/charts"),
      import("echarts/components"),
      import("echarts/renderers"),
    ]).then(([core, charts, components, renderers]) => {
      core.use([
        charts.LineChart, charts.BarChart, charts.PieChart, charts.GaugeChart,
        components.GridComponent, components.DataZoomComponent,
        components.TooltipComponent, components.LegendComponent,
        renderers.SVGRenderer,
      ]);
      return core;
    });
  }
  return echartsCorePromise;
}

const FALLBACK_FONT_STACK =
  '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, ' +
  '"Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", Roboto, Arial, sans-serif';

/** `--font-stack` 실제 값. CSS 변수는 SVG `<text>` 속성에서 안 풀릴 수 있어 계산값을 쓴다. */
function resolveFontStack() {
  if (typeof window === "undefined" || typeof getComputedStyle !== "function") {
    return FALLBACK_FONT_STACK;
  }
  const v = getComputedStyle(document.documentElement).getPropertyValue("--font-stack");
  return (v && v.trim()) || FALLBACK_FONT_STACK;
}

/** 이 차트가 항상 지키는 바탕 옵션 — 배경 투명(캔버스 색은 화면이 이미 칠한다), 글꼴,
 * 축 눈금·범례 SVG 글자는 끈다. 호버 툴팁만 HTML 로 켠다. 각 차트가 자기 옵션을
 * 여기에 덮어씌운다. */
export function baseOption() {
  const fontFamily = resolveFontStack();
  return {
    backgroundColor: "transparent",
    textStyle: { fontFamily },
    animationDuration: 400,
    animationEasing: "cubicOut",
    tooltip: {
      show: true,
      trigger: "item",
      confine: true,
      appendToBody: false,
      backgroundColor: "var(--color-card)",
      borderColor: "var(--color-border)",
      borderWidth: 1,
      textStyle: { color: "var(--color-ink)", fontFamily },
      extraCssText: "max-width:18rem;pointer-events:none;margin-inline-end:5rem;margin-block-end:5rem;",
    },
    legend: { show: false },
  };
}

/** ECharts 인스턴스 하나를 관리한다. `option` 이 바뀌면 다시 그린다(`notMerge:false` —
 * 이전 옵션과 병합해 시리즈 전체를 새로 만들지 않는다. 그래야 `revealKey` 류 트랜지션이
 * ECharts 자신의 업데이트 애니메이션과 자연스럽게 이어진다).
 *
 * `option` 이 `null`/`undefined` 면 아무것도 하지 않는다 — 호출부가 빈 데이터를 이미
 * `ChartNoData` 로 접었을 때(그림 자체를 안 그릴 때) 여기서 빈 차트를 새로 만들지 않는다. */
export function useEChart(option) {
  const containerRef = React.useRef(null);
  const chartRef = React.useRef(null);
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    let disposed = false;
    loadECharts().then(() => { if (!disposed) setReady(true); });
    return () => { disposed = true; };
  }, []);

  React.useEffect(() => {
    if (!ready || !option || !containerRef.current) return undefined;
    let core;
    let resizeObserver;
    let cancelled = false;
    loadECharts().then((mod) => {
      if (cancelled || !containerRef.current) return;
      core = mod;
      const chart = core.init(containerRef.current, null, { renderer: "svg" });
      chart.setOption(option, true);
      chartRef.current = chart;
      // 방어: jsdom(시험 환경)에는 `ResizeObserver` 가 없다. 없으면 크기 재조정 없이도
      // 차트 자체는 그려진다 — 못 그리는 것보다 "창 크기 변화에 못 따라가는 것"이 낫다.
      if (typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(() => chart.resize());
        resizeObserver.observe(containerRef.current);
      }
    });
    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
    // `option` 은 일부러 뺐다 — 초기화는 한 번뿐이고, 값이 바뀌는 갱신은 아래 두 번째
    // effect(`setOption`)가 맡는다. 여기서 `option` 을 넣으면 값이 바뀔 때마다 인스턴스를
    // 통째로 dispose/재생성해 `revealKey` 트랜지션이 매번 처음부터 다시 시작된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  React.useEffect(() => {
    if (chartRef.current && option) chartRef.current.setOption(option, true);
  }, [option]);

  return containerRef;
}
