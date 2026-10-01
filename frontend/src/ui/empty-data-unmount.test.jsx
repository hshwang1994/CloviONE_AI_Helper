import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "../screens/DataScreen.jsx";
import { ConfirmProvider, Skeleton, ToastProvider } from "./kit.jsx";
import { StatusKpiStrip } from "./StatusKpi.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";
import { BarSeries } from "./charts/BarSeries.jsx";
import { Donut } from "./charts/Donut.jsx";
import { LineSeries } from "./charts/LineSeries.jsx";
import { Sparkline } from "./charts/Sparkline.jsx";

/* qa-contract-change: 조건 때문에 0건인 목록은 표를 언마운트하지 않고 머리 아래 한 줄 띠로 「조건에 맞는 항목이 없습니다.」를 말한다(D-530 목록 상태 일곱 갈래 — 조건을 바꿔도 머리가 제자리에 있고 판을 흰 면으로 채우지 않는다). 조건 없이 정말 0건인 목록의 언마운트(머리 행 · 「0건 중 0건」을 남기지 않음)는 그대로 단언하고, 클라이언트 필터 예외는 「더 보기」가 남고 행이 없으며 띠가 머리 아래 줄이라는 단언으로 옮긴다. */
/* qa-contract-change: 판독 줄(MetricStrip)이 핸드오프 RULES §6 에 따라 걷혀, 그 부품의 「전부 비면 원인을 대신 그린다」 계약(emptyCause · data-metrics-empty — 제품 소비처 0)을 그 줄을 이은 측정값 줄(StatusKpiStrip)의 「항목이 없으면 그릇을 남기지 않는다」로 옮긴다. */

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

describe("측정값 줄은 항목이 없으면 그릇을 남기지 않는다 (판독 줄의 빈 줄 계약을 이은 자리)", () => {
  it("항목이 없으면 줄도, 칸 격자도 없다", () => {
    const { container } = render(ui(<StatusKpiStrip ariaLabel="지표" items={[]} />));
    expect(container.querySelector('[role="group"]')).toBeNull();
    expect(container.textContent).toBe("");
  });

  it("비어 있는 항목(null · false)은 칸이 되지 않는다 — 전부 비면 줄도 없다", () => {
    /* 반례. 화면이 조건부로 항목을 빼면서 `null` 을 남기는 일은 흔하다 — 그것을 칸으로 세면 이름 없는 빈 판이
       선다(「없는 데이터를 위한 컨테이너」). */
    const { container } = render(ui(<StatusKpiStrip ariaLabel="지표" items={[null, false]} />));
    expect(container.querySelector('[role="group"]')).toBeNull();
  });

  it("한 칸이라도 있으면 그대로 그린다", () => {
    render(ui(<StatusKpiStrip ariaLabel="지표" items={[{ key: "a", label: "오늘 마감", value: 3 }, null]} />));
    expect(screen.getByRole("group", { name: "지표" })).toBeInTheDocument();
    expect(screen.getByText("오늘 마감")).toBeInTheDocument();
  });

  it("값이 없는 칸(null · undefined)은 서지 않는다 — 이름만 든 판을 남기지 않는다 (D-501)", () => {
    /* 작업 큐의 「평균 처리 시간(24h)」은 잴 이력이 없을 때 숫자 없이 이름만 든 반폭 판으로 섰다. 모르는 값을 말해야
       하는 칸은 호출부가 `-` 를 값으로 준다 — 그 칸은 값이 있는 칸이다(반례). */
    render(ui(<StatusKpiStrip ariaLabel="지표" items={[
      { key: "a", label: "평균 처리 시간(24h)", value: null },
      { key: "b", label: "처리 요청", value: undefined },
      { key: "c", label: "성공률", value: "-" },
    ]} />));
    const group = screen.getByRole("group", { name: "지표" });
    expect(group.children).toHaveLength(1);
    expect(screen.queryByText("평균 처리 시간(24h)")).toBeNull();
    expect(screen.queryByText("처리 요청")).toBeNull();
    expect(screen.getByText("성공률")).toBeInTheDocument();
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

  it("목록 끝 줄이 사라진다 — 「0건 중 0건」을 남기지 않는다", async () => {
    apiMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
    renderScreen(config({ paginated: true }));
    await screen.findByText("표시할 항목이 없습니다");
    expect(document.querySelector("[data-list-footer]")).toBeNull();
    expect(screen.queryByRole("button", { name: "더 보기" })).toBeNull();
  });

  it("값이 있으면 둘 다 선다 — 언마운트가 조건부인지 확인한다", async () => {
    apiMock.mockResolvedValue({
      items: [{ id: "r1", name: "행 1" }], page: 1, page_size: 20, total: 9,
    });
    const { container } = renderScreen(config({ paginated: true }));
    await screen.findByText("행 1");
    expect(container.querySelector("table")).not.toBeNull();
    expect(screen.getByRole("button", { name: "더 보기" })).toBeInTheDocument();
  });

  it("클라이언트 필터가 있는 목록에서는 끝 줄만 남는다 — 더 받으면 값이 있을 수 있다", async () => {
    /* 문서화된 예외다. 서버가 묶음을 자르고 그 위에 화면이 다시 거르는 목록에서는 지금
       받아 둔 것이 통째로 걸러져도 다음 묶음에 일치 항목이 있을 수 있다. 그때 「더 보기」를
       치우면 사용자가 그 자리에 갇힌다 — 표는 사라지지만 더 받을 수단은 남는다. */
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
    await screen.findByRole("button", { name: "더 보기" });
    /* 조건 때문에 0건 — 머리는 서 있고 그 아래 한 줄 띠가 사실을 말한다(D-530). 받아 둔 행은 하나도 그려지지 않는다. */
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    const rows = [...table.querySelectorAll("tbody tr")];
    expect(rows).toHaveLength(1);
    expect(rows[0].hasAttribute("data-empty-band")).toBe(true);
    expect(within(rows[0]).getByRole("heading", { name: "조건에 맞는 항목이 없습니다." })).toBeInTheDocument();
    expect(screen.queryByText("행 1")).toBeNull();
  });
});
