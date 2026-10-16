import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { Button, Card, DataTable, EmptyState, ErrorState, ListEmptyState, Section, StateRegion } from "./kit.jsx";
import { ListStateView } from "./ListStateView.jsx";
import { LIST_STATE_COPY } from "./listState.js";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 표 안 빈 상태는 머리 아래 한 줄 띠다 (F4 · D-530).
 *
 * 예전에는 빈 표가 머리 없이 판 안에 빈 상태 부품을 세웠고, 화면마다 큰 그림 · 긴 설명이 판을 흰 면으로 채웠다(조건을 바꾸면 머리가
 * 사라졌다 나타났다). 이제 머리는 그대로 서고, 그 아래 줄 하나가 「왜 비었는지 · 무엇을 하면 되는지」를 말한다. 빈 상태 · 오류
 * 상태의 기본 배치는 담는 쪽이 정한다 — 판 · 탭 판 · 모달 안이면 그 자리의 한 칸(region)이다. */

const COLS = [{ key: "name", label: "이름" }, { key: "state", label: "상태", type: "status" }];

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("빈 표 — 머리 아래 한 줄 띠", () => {
  it("머리는 서 있고 몸에는 띠 한 줄뿐이다", () => {
    const { container } = ui(<DataTable placement="surface" columns={COLS} rows={[]} rowKey={(r) => r.id} empty="검색 조건에 맞는 항목이 없습니다." />);
    expect(screen.getByRole("columnheader", { name: "이름" })).toBeInTheDocument();
    const rows = container.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveAttribute("data-empty-band");
    // 띠 칸은 모든 열에 걸친다.
    expect(rows[0].querySelector("td")).toHaveAttribute("colspan", String(COLS.length));
    const band = rows[0].querySelector('[data-empty-layout="band"]');
    expect(within(band).getByRole("heading", { name: "검색 조건에 맞는 항목이 없습니다." })).toBeInTheDocument();
    // 표가 판 가장자리에 붙는다 — 여백 안의 「상태만 든 판」이 아니다. 판은 빈 목록이라는 표식은 그대로 든다.
    const surface = container.querySelector("[data-list-surface]");
    expect(surface).toHaveAttribute("data-list-state", "empty");
    expect(surface.querySelector("table")).not.toBeNull();
  });

  it("띠의 높이 바닥은 56 이고(rem) 그림을 그리지 않는다 — 큰 그림은 화면 전체가 빈 page 상태에서만", () => {
    const { container } = ui(
      <DataTable
        columns={COLS} rows={[]} rowKey={(r) => r.id}
        emptyState={<EmptyState layout="region" art="search" title="조건에 해당하는 사용자가 없습니다" help="검색어를 지우세요." />}
      />,
    );
    const band = container.querySelector('[data-empty-layout="band"]');
    expect(band).not.toBeNull();
    expect(getComputedStyle(band).minHeight).toBe("3.5rem");
    expect(band.querySelector("img")).toBeNull();
    // 화면이 판 자리(region)를 말했어도 표 안에서는 띠다 — 판을 흰 면으로 채우지 않는다.
    expect(container.querySelector('[data-empty-layout="region"]')).toBeNull();
    expect(within(band).getByText("검색어를 지우세요.")).toBeInTheDocument();
  });

  it("동작은 띠 안 30 단추다 — `emptyAction`", () => {
    const onClear = vi.fn();
    ui(
      <DataTable
        columns={COLS} rows={[]} rowKey={(r) => r.id}
        empty="검색 조건에 맞는 항목이 없습니다."
        emptyAction={<Button size="sm" onClick={onClear}>필터 초기화</Button>}
      />,
    );
    const button = screen.getByRole("button", { name: "필터 초기화" });
    expect(button.closest("[data-empty-band]")).not.toBeNull();
    button.click();
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("조건 0건 빈 상태(ListEmptyState)도 표 안에서는 띠다", () => {
    const { container } = ui(
      <DataTable
        columns={COLS} rows={[]} rowKey={(r) => r.id}
        emptyState={<ListEmptyState filtered onClear={() => {}} filteredTitle="조건에 맞는 프로젝트가 없습니다" />}
      />,
    );
    const band = container.querySelector('[data-empty-band] [data-empty-layout="band"]');
    expect(within(band).getByRole("button", { name: "필터 초기화" })).toBeInTheDocument();
  });

  it("행이 있으면 띠가 없다", () => {
    const { container } = ui(<DataTable columns={COLS} rows={[{ id: "1", name: "가", state: "활성" }]} rowKey={(r) => r.id} />);
    expect(container.querySelector("[data-empty-band]")).toBeNull();
  });

  it("불러오는 중 뼈대는 300ms 뒤에 드러난다 — 자리는 처음부터 차지한다", () => {
    const { container } = ui(<DataTable placement="surface" columns={COLS} rows={[]} rowKey={(r) => r.id} loading />);
    const reveal = container.querySelector("[data-delayed-reveal]");
    expect(reveal).not.toBeNull();
    expect(reveal.querySelector(".k-skeleton-table")).not.toBeNull();
    const css = [...document.querySelectorAll("style")].map((s) => s.textContent).join(" ");
    expect(css).toMatch(/animation:[^;]*300ms/);
  });
});

describe("빈 상태 · 오류 상태의 기본 배치는 담는 쪽이 정한다", () => {
  const err = (props) => Object.assign(new Error("목록 서버가 응답하지 않았습니다."), props);

  it("화면 본문에 바로 선 오류는 화면 전체(page)다", () => {
    const { container } = ui(<ErrorState error={err({ status: 500 })} onRetry={() => {}} />);
    expect(container.querySelector("[data-error-layout]")).toHaveAttribute("data-error-layout", "page");
  });

  it("판 · 구획 · 상태 자리 안의 오류는 그 자리의 한 칸(region)이다", () => {
    for (const Wrap of [Card, Section, StateRegion]) {
      const { container, unmount } = ui(<Wrap><ErrorState error={err({ status: 500 })} onRetry={() => {}} /></Wrap>);
      expect(container.querySelector("[data-error-layout]")).toHaveAttribute("data-error-layout", "region");
      unmount();
    }
  });

  it("호출부가 자리를 말하면 그것이 이긴다", () => {
    const { container } = ui(<Card><ErrorState layout="page" error={err({ status: 500 })} /></Card>);
    expect(container.querySelector("[data-error-layout]")).toHaveAttribute("data-error-layout", "page");
  });
});

describe("ListStateView — 실패 넷은 서로 다른 말이다", () => {
  const err = (props) => Object.assign(new Error(props.message || "x"), props);

  it("권한 없음 — 다시 시도가 없다", () => {
    ui(<ListStateView state="forbidden" error={err({ status: 403 })} onRetry={() => {}} />);
    expect(screen.getByRole("heading", { name: LIST_STATE_COPY.forbidden.title })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull();
    expect(screen.queryByRole("link", { name: "홈으로" })).toBeNull();
  });

  it("기능 꺼짐 — 서버 문장이 어느 기능인지 말하고, 오류 표지가 없다", () => {
    const { container } = ui(
      <ListStateView
        state="disabled"
        error={err({ status: 404, message: "문서 기능이 비활성화되어 있습니다.", body: { error: { code: "feature_disabled" } } })}
        settingsHref="#/feature-flags"
      />,
    );
    expect(screen.getByRole("heading", { name: "문서 기능이 비활성화되어 있습니다." })).toBeInTheDocument();
    expect(screen.getByText(LIST_STATE_COPY.disabled.help)).toBeInTheDocument();
    expect(container.querySelector("[data-error-layout]")).toBeNull();
    expect(screen.queryByRole("img", { name: "오류" })).toBeNull();
    expect(screen.getByRole("link", { name: "기능 설정 열기" })).toHaveAttribute("href", "#/feature-flags");
  });

  it("연결 장애 · 서버 오류는 다시 시도가 있고 제목이 다르다", () => {
    const { unmount } = ui(<ListStateView state="unreachable" error={err({ kind: "network" })} onRetry={() => {}} />);
    expect(screen.getByRole("heading", { name: LIST_STATE_COPY.unreachable.title })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    unmount();
    ui(<ListStateView state="error" error={err({ status: 500, requestId: "req-42" })} onRetry={() => {}} />);
    expect(screen.getByRole("heading", { name: LIST_STATE_COPY.error.title })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    // 문의 번호가 있을 때만 그 번호를 가리키는 문장을 붙인다.
    expect(screen.getByText(/문의 번호를 관리자에게/)).toBeInTheDocument();
    expect(screen.getByText("문의 번호 req-42")).toBeInTheDocument();
  });
});
