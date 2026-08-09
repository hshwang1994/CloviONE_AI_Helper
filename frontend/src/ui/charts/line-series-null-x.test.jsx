import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import { LineSeries } from "./LineSeries.jsx";
import { createClovirTheme } from "../theme.js";

/* LineSeries의 x좌표 계산은 (인덱스 * 너비) / (칸 수 - 1)이다. 이 컴포넌트가 원본
 * points 배열에서 null을 걸러낸 "값만 있는" 배열의 길이로 칸 수를 잡으면, null 하나가
 * 사라질 때마다 그 뒤의 점들이 전부 한 칸씩 당겨져 그려진다 — null이 있던 시점이
 * "압축돼 없던 일"이 되는 것이다. 실제 시계열에서는 null도 그 자리(시각/인덱스)를
 * 그대로 차지해야 한다 — 값이 비었을 뿐 그 인덱스의 점이 사라진 게 아니다.
 *
 * 지금 이 저장소의 두 호출부(MyStats.jsx, Sprint.jsx)는 null을 0으로 미리 치환해서
 * 넘기므로 이 버그가 실제 화면에 보이지는 않는다 — 그래서 이 테스트는 raw null을 그대로
 * 넘겨 컴포넌트 자체가 다음에 올 소비자를 위해 옳은 동작을 하는지 확인한다. */
function renderPathD(series) {
  const { container } = render(
    <ThemeProvider theme={createClovirTheme("light")}>
      <LineSeries series={series} />
    </ThemeProvider>,
  );
  const line = container.querySelector("path[stroke]");
  expect(line).not.toBeNull();
  return line.getAttribute("d");
}

// path의 d 속성은 "M0.00 24.40 L20.00 18.80 …" 형태다 — 값 토큰(y)은 문자 접두어가 없어
// M/L로 시작하는 좌표 토큰(command+x)만 정규식으로 골라낸다. 공백으로 그냥 split하면
// x와 y가 뒤섞여 버린다.
function commandsAndX(d) {
  return (d.match(/[ML][-\d.]+/g) || []).map((tok) => ({
    command: tok[0],
    x: Number(tok.slice(1)),
  }));
}

describe("LineSeries — null 값의 x좌표 보존", () => {
  it("가운데 null이 있어도 그 뒤 점은 압축되지 않고 원래 인덱스의 x좌표에 그려진다", () => {
    // 6칸(인덱스 0~5)짜리 배열에서 인덱스 3이 null이다. 6칸이면 x(i) = i * 100 / 5.
    // 압축(버그) 시나리오라면 null이 배열에서 통째로 빠져 [10,20,30,40,50] 5개 값이
    // 인덱스 0~4로 재배치되고, 그 x좌표는 각각 0,25,50,75,100 이 된다 — 특히 null
    // 다음 값(40)이 원래 자리(인덱스 4, x=80)가 아니라 x=75로 그려진다.
    // 올바른(고쳐진) 계산은 원래 인덱스를 그대로 써서 null(인덱스 3, x=60)만 빠지고
    // 나머지는 0,20,40,[gap],80,100 자리를 지킨다 — null 다음 값(40)은 x=80.
    const d = renderPathD([{ label: "테스트", points: [10, 20, 30, null, 40, 50] }]);
    const points = commandsAndX(d);
    const xs = points.map((p) => p.x);

    // 압축됐다면 나왔을 x=75(null 다음 점)가 없어야 하고, 올바른 자리인 x=80이 있어야 한다.
    expect(xs).not.toContain(75);
    const gapPoint = points.find((p) => Math.abs(p.x - 80) < 0.01);
    expect(gapPoint).toBeDefined();

    // null을 사이에 두고 선이 끊겨야 한다(값이 있었던 것처럼 이어 그리지 않는다) — null
    // 다음의 첫 유효 점(x=80)은 M(이동)으로 시작해야 하고, 그 앞의 연속 구간(인덱스 0~2)만
    // L(선 긋기)로 이어져야 한다.
    expect(gapPoint.command).toBe("M");

    // 마지막 점(원래 인덱스 5)도 자기 자리인 x=100에 그대로 남아야 한다.
    expect(xs[xs.length - 1]).toBeCloseTo(100, 1);

    // 전체 좌표 순서: 0, 20, 40(연속 구간, L로 이어짐) → 80(M으로 끊김) → 100(L로 이어짐).
    expect(xs).toEqual([0, 20, 40, 80, 100]);
    expect(points.map((p) => p.command)).toEqual(["M", "L", "L", "M", "L"]);
  });

  it("null이 없을 때는 기존과 동일하게 균등한 x좌표로 그려진다", () => {
    const d = renderPathD([{ label: "기준", points: [0, 10, 20, 30] }]);
    const xs = commandsAndX(d).map((p) => p.x);
    expect(xs).toEqual([0, 33.33, 66.67, 100]);
  });
});
