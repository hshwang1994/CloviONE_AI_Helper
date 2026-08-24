import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "../screens/DataScreen.jsx";
import { ConfirmProvider, MetricStrip, Skeleton, ToastProvider } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";
import { BarSeries } from "./charts/BarSeries.jsx";
import { Donut } from "./charts/Donut.jsx";
import { LineSeries } from "./charts/LineSeries.jsx";
import { Sparkline } from "./charts/Sparkline.jsx";

/* 값이 0건일 때 **그리지 않는가** (PLAN «빈 데이터 규칙», 지시 0-10).
 *
 * 지시 0-10 이 묻는 첫 질문이 "데이터가 없을 때 Chart/Table/Card 자체가 필요한가" 다.
 * 필요 없는데 남겨 두면 화면에 **없는 데이터를 위한 컨테이너**가 생긴다 — 점선 상자, 머리
 * 행만 있는 표, 「1 / 1, 총 0건」이라고 적힌 페이저. 셋 다 실제로 있던 모양이다.
 *
 * 이 시험이 «화면에 무엇이 안 보인다» 가 아니라 **DOM 에서 언마운트됐는지**를 보는 이유:
 * `display:none` 이나 높이 0 으로 숨긴 컨테이너는 여전히 배치를 차지하고, 스크린리더는
 * 그것을 읽는다. 「필요 없으면 Collapse」는 «안 보이게» 가 아니라 «없애» 다.
 */

function ui(node) {
  return (
    <ThemeModeProvider>{node}</ThemeModeProvider>
  );
}

describe("값이 없으면 그림을 접는다", () => {
  it("도넛은 SVG 를 남기지 않고 한 줄만 남는다", () => {
    const { container } = render(ui(<Donut segments={[]} emptyLabel="이번 주 티켓 없음" />));
    expect(container.querySelector("svg")).toBeNull();
    expect(screen.getByText("이번 주 티켓 없음")).toBeInTheDocument();
  });

  it("막대·꺾은선·스파크라인도 같다", () => {
    for (const node of [
      <BarSeries key="b" rows={[]} emptyLabel="막대 없음" />,
      <LineSeries key="l" series={[]} emptyLabel="선 없음" />,
      <Sparkline key="s" values={[]} emptyLabel="추이 없음" />,
    ]) {
      const { container, unmount } = render(ui(node));
      expect(container.querySelector("svg")).toBeNull();
      unmount();
    }
  });

  it("접힌 자리에 점선 상자를 만들지 않는다", () => {
    /* 폐기한 형태를 못 박는다. 예전 `ChartEmpty` 는 차트 높이만큼 자리를 잡고 점선
       테두리를 둘렀다 — 값이 0건인데 화면은 9rem 을 그 사실에 썼다. */
    const { container } = render(ui(<Donut segments={[]} emptyLabel="없음" />));
    const boxed = [...container.querySelectorAll("*")].filter((el) => {
      const st = getComputedStyle(el);
      return st.borderStyle && st.borderStyle.includes("dashed");
    });
    expect(boxed).toEqual([]);
    expect(container.querySelector('[data-chart-collapsed="true"]')).not.toBeNull();
  });

  it("불러오는 중에는 **차트 모양**이라 「없다」와 구별된다", () => {
    const { container } = render(ui(<Skeleton kind="chart" />));
    const skeleton = container.querySelector(".k-skeleton-chart");
    expect(skeleton).not.toBeNull();
    // 막대가 여럿이라야 차트 «모양» 이다 — 줄 몇 개는 어느 화면에서나 같은 그림이다.
    expect(skeleton.querySelectorAll(".MuiSkeleton-root").length).toBeGreaterThan(4);
    // 그리고 접힌 상태와 달리 자리를 잡는다.
    expect(container.querySelector('[data-chart-collapsed="true"]')).toBeNull();
  });
});

describe("판독 줄은 전부 비면 원인을 대신 그린다", () => {
  const EMPTY = [
    { key: "a", label: "오늘 마감", value: "-" },
    { key: "b", label: "처리 요청", value: null },
  ];

  it("원인을 주면 줄 대신 원인이 선다", () => {
    const { container } = render(ui(
      <MetricStrip ariaLabel="지표" items={EMPTY} emptyCause={<p>연동이 끊겼습니다</p>} />
    ));
    expect(container.querySelector(".k-metrics")).toBeNull();
    expect(screen.getByText("연동이 끊겼습니다")).toBeInTheDocument();
  });

  it("원인을 안 주면 줄은 남되 **셀 수 있게** 표시된다", () => {
    /* 반례. 원인 없이 줄만 지우면 화면이 구획 정체성까지 잃는다("오늘 마감" 이라는 이름
       자체가 사라진다) — 그래서 지우지 않고 표식을 남긴다. 그 표식의 개수가 곧 «아직
       원인을 안 넘긴 자리» 의 수다. */
    const { container } = render(ui(<MetricStrip ariaLabel="지표" items={EMPTY} />));
    expect(container.querySelector('.k-metrics[data-metrics-empty="true"]')).not.toBeNull();
  });

  it("한 칸이라도 값이 있으면 그대로 그린다", () => {
    const items = [{ key: "a", label: "오늘 마감", value: 3 }, { key: "b", label: "처리 요청", value: "-" }];
    const { container } = render(ui(
      <MetricStrip ariaLabel="지표" items={items} emptyCause={<p>연동이 끊겼습니다</p>} />
    ));
    expect(container.querySelector(".k-metrics")).not.toBeNull();
    expect(screen.queryByText("연동이 끊겼습니다")).toBeNull();
  });
});

// ── 표와 페이저 ────────────────────────────────────────────────────────────

const COLUMNS = [{ key: "name", label: "이름" }];

function config(extra) {
  return {
    key: "probe", title: "검사 화면", endpoint: "/api/admin/probe",
    columns: COLUMNS, detailFields: [], ...extra,
  };
}

function renderScreen(cfg) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter><DataScreen config={cfg} /></MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("0건이면 표와 페이저를 언마운트한다", () => {
  it("표가 통째로 사라진다 — 머리 행만 남지 않는다", async () => {
    apiMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
    const { container } = renderScreen(config({ paginated: true }));
    await screen.findByText("표시할 항목이 없습니다");
    expect(container.querySelector("table")).toBeNull();
    expect(screen.queryByText("이름")).toBeNull();
  });

  it("페이저가 사라진다 — 「총 0건」짜리 페이저를 남기지 않는다", async () => {
    apiMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
    renderScreen(config({ paginated: true }));
    await screen.findByText("표시할 항목이 없습니다");
    expect(screen.queryByRole("navigation", { name: /페이지 이동/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "다음" })).toBeNull();
  });

  it("값이 있으면 둘 다 선다 — 언마운트가 조건부인지 확인한다", async () => {
    apiMock.mockResolvedValue({
      items: [{ id: "r1", name: "행 1" }], page: 1, page_size: 20, total: 1,
    });
    const { container } = renderScreen(config({ paginated: true }));
    await screen.findByText("행 1");
    expect(container.querySelector("table")).not.toBeNull();
    expect(screen.getByRole("button", { name: "다음" })).toBeInTheDocument();
  });

  it("클라이언트 필터가 있는 목록에서는 페이저만 남는다 — 다른 쪽에 값이 있을 수 있다", async () => {
    /* 문서화된 예외다. 서버가 페이지를 자르고 그 위에 화면이 다시 거르는 목록에서는
       이번 페이지가 통째로 걸러져도 다음 페이지에 일치 항목이 있을 수 있다. 그때 페이저를
       치우면 사용자가 그 페이지에 갇힌다 — 표는 사라지지만 이동 수단은 남는다. */
    apiMock.mockResolvedValue({
      items: [{ id: "r1", name: "행 1", kind: "b" }], page: 1, page_size: 1, total: 9,
    });
    const { container } = renderScreen(config({
      paginated: true,
      filters: [{
        key: "kind", label: "종류", clientFilter: true, value: "a",
        options: [{ value: "a", label: "가" }, { value: "b", label: "나" }],
      }],
    }));
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    await screen.findByRole("button", { name: "다음" });
    expect(container.querySelector("table")).toBeNull();
  });
});
