import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { DataTable, Skeleton } from "./kit.jsx";

/* 지시 20 — 로딩 자리표시자는 **들어올 것의 모양**을 한다.
 *
 * 예전에는 어느 화면에서나 회색 줄 N개였다. 그래서 두 가지가 무너졌다.
 *   1) 화면이 무엇을 준비 중인지 알 수 없다 — 표가 올 자리와 카드가 올 자리가 같아 보인다.
 *   2) 실제 내용이 도착하면 배치가 통째로 튄다 — 자리표시자가 자리를 안 잡아 준다.
 *
 * 그리고 표에서는 더 나쁜 혼동이 하나 더 있었다: **빈 목록과 아직 안 온 목록이 같아 보인다.**
 * "없다"와 "아직 모른다"는 다른 사실이고, 사용자의 다음 행동도 다르다.
 */

const COLUMNS = [
  { key: "name", label: "이름" },
  { key: "role", label: "역할" },
  { key: "at", label: "시각" },
];

describe("Skeleton — 모양이 셋이다", () => {
  it("스크린리더에는 어느 모양이든 '불러오는 중'이 낭독된다", () => {
    const { unmount } = render(<Skeleton />);
    expect(screen.getByText("불러오는 중…")).toBeInTheDocument();
    unmount();
    render(<Skeleton kind="table" />);
    expect(screen.getByText("불러오는 중…")).toBeInTheDocument();
  });

  it("표 모양은 열 수만큼 칸을 나눈다 — 회색 줄이 아니라 표처럼 보인다", () => {
    const { container } = render(<Skeleton kind="table" cols={3} rows={4} />);
    const table = container.querySelector(".k-skeleton-table");
    expect(table, "표 모양 자리표시자가 없다").toBeTruthy();
    const grids = Array.from(table.children);
    // 머리행 하나 + 본문 행들.
    expect(grids.length).toBe(5);
    for (const row of grids) {
      expect(row.children.length, "칸 수가 열 수와 다르다").toBe(3);
    }
  });

  it("화면 전체 모양은 제목 자리를 먼저 잡는다", () => {
    const { container } = render(<Skeleton kind="page" lines={2} />);
    const page = container.querySelector(".k-skeleton-page");
    expect(page).toBeTruthy();
    // 제목 묶음 + 판 하나 + 본문 묶음.
    expect(page.children.length).toBe(3);
  });

  it("기본(구역) 모양은 예전 동작 그대로 줄 수만큼 그린다", () => {
    const { container } = render(<Skeleton lines={4} />);
    expect(container.querySelector(".k-skeleton-table")).toBeNull();
    expect(container.querySelector(".k-skeleton-page")).toBeNull();
    const box = container.querySelector('[aria-hidden="true"]');
    expect(box.children.length).toBe(4);
  });
});

describe("DataTable — 빈 목록과 아직 안 온 목록을 구별한다", () => {
  it("loading 이면 빈 상태 문구가 아니라 표 모양을 그린다", () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={[]} loading empty="표시할 항목이 없습니다." />,
    );
    expect(screen.queryByText("표시할 항목이 없습니다.")).toBeNull();
    expect(container.querySelector(".k-skeleton-table")).toBeTruthy();
  });

  it("loading 이 아니고 행이 없으면 빈 상태 문구를 말한다", () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={[]} empty="표시할 항목이 없습니다." />,
    );
    expect(screen.getByText("표시할 항목이 없습니다.")).toBeInTheDocument();
    expect(container.querySelector(".k-skeleton-table")).toBeNull();
  });

  it("표 모양의 칸 수는 그 표의 열 수를 따른다", () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={[]} loading />);
    const first = container.querySelector(".k-skeleton-table").firstChild;
    expect(first.children.length).toBe(COLUMNS.length);
  });
});
