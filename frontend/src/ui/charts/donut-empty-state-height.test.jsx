/* qa-contract-change: 이 파일이 지키던 계약이 D-296 으로 뒤집혔다 — 예전에는 «값이 0건이어도 도넛 높이(9rem)를 지켜 로딩→빈 전환에서 카드가 안 줄어든다» 를 단언했다.
   그건 결국 화면에
   «없는 데이터를 위한 9rem 짜리 컨테이너» 를 만드는 규칙이었다. PLAN «빈 데이터 규칙» 과
   지시 0-10 이 요구하는 것은 그 반대다 — 정말 값이 없으면 **차트를 통째로 접고** 한 줄만
   남긴다. 높이가 안 튀게 하는 몫은 이제 로딩 쪽이 진다: `Skeleton kind="chart"` 가 같은
   높이의 차트 «모양» 을 그리므로 「불러오는 중」과 「없다」가 서로 다르게 보인다. 그래서
   같은 자리에서 이제는 **반대**를 단언한다. */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { Donut } from "./Donut.jsx";
import { ThemeModeProvider } from "../ThemeModeProvider.jsx";

function renderDonut(props) {
  return render(
    <ThemeModeProvider>
      <Donut segments={[]} {...props} />
    </ThemeModeProvider>,
  );
}

describe("Donut 빈 상태", () => {
  it("도넛 높이를 지키지 않고 한 줄로 접힌다", () => {
    const { container } = renderDonut({ size: "14rem" });
    const line = screen.getByText("데이터 없음");
    expect(line.getAttribute("data-chart-collapsed")).toBe("true");
    // `size` 는 그려질 도넛의 치수다 — 접힌 자리에 그 치수가 남아 있으면 안 된다.
    expect(getComputedStyle(line).minHeight).not.toBe("14rem");
    expect(container.querySelector("svg")).toBeNull();
  });

  it("`size` 를 바꿔도 접힌 높이는 그대로다 — 치수가 빈 상태를 따라다니지 않는다", () => {
    const a = renderDonut({ size: "9rem" });
    const first = getComputedStyle(screen.getByText("데이터 없음")).minHeight;
    a.unmount();
    renderDonut({ size: "20rem" });
    expect(getComputedStyle(screen.getByText("데이터 없음")).minHeight).toBe(first);
  });

  it("값이 있으면 `size` 가 다시 도넛의 치수가 된다", async () => {
    const { container } = renderDonut({ segments: [{ label: "완료", value: 3 }], size: "14rem" });
    // ECharts는 `useEChart.js`가 지연 import(§15.8)한 뒤 붙는다 — 실제 사용자에게는
    // 감지 안 되는 지연이지만, 시험은 그 마운트를 기다려야 한다(값이 없을 때는 이 부품이
    // ECharts를 아예 안 부르므로 위 두 시험은 그대로 동기다). 치수는 ECharts가 그린
    // svg 자신이 아니라 그것을 감싼 `data-chart-frame` 상자가 받는다 — ECharts는 잰
    // 컨테이너 크기를 못 구하면(jsdom) 자기 루트에 임의의 기본 픽셀 크기를 매긴다.
    // 시간 제한은 기본(1000ms)보다 넉넉히 준다 — 전체 표적 검증처럼 차트 시험 여러 개가
    // 동시에 도는 동안에는 동적 import 자체가 시스템 부하를 받아 더 걸릴 수 있다.
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull(), { timeout: 5000 });
    const frame = container.querySelector('[data-chart-frame="donut"]');
    expect(frame).not.toBeNull();
    expect(getComputedStyle(frame).width).toBe("14rem");
  });
});
