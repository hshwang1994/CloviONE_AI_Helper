import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ProjectSummaryCard } from "./ProjectSummaryCard.jsx";
import { ResultBlock } from "./ResultList.jsx";
import { ThemeModeProvider } from "../../../ui/ThemeModeProvider.jsx";

/* 프로젝트 현황 카드(AI 채팅 개선 회차) — 서버가 센 값 그대로다(모델이 옮겨 적은 수가 아니다). 진행률 · 건강도 · 열린 티켓 ·
 * 마감 지남 · 막힘 · 상태별 수 · 최근 끝낸 일 셋을 보이고, 앱 안 경로일 때만 「프로젝트 열기」가 선다. */

const PROJECT = {
  name: "SK하이닉스 클라우드 전환", code: "SFVHJG", status: "진행", route: "/projects/p1",
  progress: { percent: 82.76, done_tasks: 24, counted_tasks: 29 },
  health: { score: 71, reasons: ["마감 지난 티켓 2건"] },
  tickets: { open: 5, overdue_open: 2, blocked: 1, status_counts: { 완료: 24, 진행: 3, 계획: 2 } },
  recent_completed: [
    { key: "SFVHJG-31", title: "스토리지 이관 점검", route: "/tickets/t31", completed_at: "2026-10-14T03:00:00" },
    { key: "SFVHJG-30", title: "백업 정책 확정", route: "/tickets/t30", completed_at: "2026-10-13T03:00:00" },
    { key: "SFVHJG-29", title: "네트워크 분리", route: "/tickets/t29", completed_at: "2026-10-12T03:00:00" },
    { key: "SFVHJG-28", title: "넷째 항목은 보이지 않는다", route: "/tickets/t28", completed_at: "2026-10-11T03:00:00" },
  ],
  recent_completed_total: 7,
};

function renderCard(project) {
  return render(<ThemeModeProvider><ProjectSummaryCard project={project} /></ThemeModeProvider>);
}

describe("프로젝트 현황 카드", () => {
  it("진행률 · 건강도 · 티켓 수 · 상태별 수를 서버 값 그대로 보인다", () => {
    renderCard(PROJECT);
    const card = screen.getByRole("region", { name: "SK하이닉스 클라우드 전환 프로젝트 현황" });
    expect(card.textContent).toContain("82.8%");
    expect(card.textContent).toContain("(24/29)");
    expect(card.textContent).toContain("상태별 티켓 계획 2, 진행 3, 완료 24");
    expect(card.textContent).toContain("건강도 근거: 마감 지난 티켓 2건");
    for (const [label, value] of [["건강도", "71"], ["열린 티켓", "5"], ["마감 지남", "2"], ["막힘", "1"]]) {
      const name = screen.getByText(label);
      expect(name.nextSibling).toHaveTextContent(value);
    }
  });

  it("최근 끝낸 일은 셋까지이고 전체 수를 함께 말한다", () => {
    renderCard(PROJECT);
    expect(screen.getByText("최근 끝낸 일 (7건 중 3건)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "스토리지 이관 점검" })).toHaveAttribute("href", "#/tickets/t31");
    expect(screen.queryByText("넷째 항목은 보이지 않는다")).toBeNull();
  });

  it("연결 문서를 「N건 중 M건」과 함께 링크로 세운다 — 답이 표시했다고 말하는 그 목록이다", () => {
    renderCard({ ...PROJECT, documents: { total: 8, items: [
      { ref: "d1", title: "하이닉스", route: "/knowledge/d1", updated_at: "2026-09-04T00:00:00" },
      { ref: "d2", title: "포털 연동 가이드", route: "/knowledge/d2", updated_at: "2026-09-01T00:00:00" },
      { ref: "d3", title: "바깥 주소", route: "https://evil.example/d3" },
    ] } });
    expect(screen.getByText("연결 문서 (8건 중 3건)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "하이닉스" })).toHaveAttribute("href", "#/knowledge/d1");
    expect(screen.queryByRole("link", { name: "바깥 주소" })).toBeNull();
    expect(screen.getByText("바깥 주소")).toBeInTheDocument();
  });

  it("앱 안 경로일 때만 「프로젝트 열기」가 선다", () => {
    const { unmount } = renderCard(PROJECT);
    expect(screen.getByRole("link", { name: "프로젝트 열기" })).toHaveAttribute("href", "#/projects/p1");
    unmount();
    renderCard({ ...PROJECT, route: "https://evil.example/projects/p1" });
    expect(screen.queryByRole("link", { name: "프로젝트 열기" })).toBeNull();
  });

  it("도구가 싣지 않은 칸은 그리지 않는다 — 진행 요약(get_project_summary)에는 티켓 수가 없다", () => {
    renderCard({ name: "인프라 정비", code: "QRDNXF", status: "진행", progress: { percent: 25, done_tasks: 2, counted_tasks: 8 },
      health: { score: 33 }, starts_on: "2026-06-01", ends_on: "2026-12-31" });
    expect(screen.getByText("건강도").nextSibling).toHaveTextContent("33");
    expect(screen.queryByText("열린 티켓")).toBeNull();
    expect(screen.queryByText("막힘")).toBeNull();
    expect(screen.getByText("기간 2026-06-01 ~ 2026-12-31")).toBeInTheDocument();
    // 진행률 머리는 한 번이다(막대가 제 머리를 따로 그리지 않는다).
    expect(screen.getAllByText("진행률")).toHaveLength(1);
  });

  it("결과 블록의 project_summary 는 이 카드다", () => {
    render(<ThemeModeProvider><ResultBlock block={{ id: "r9", tool: "project_activity", kind: "project_summary", shown: true, items: [PROJECT] }} messageId="m1" /></ThemeModeProvider>);
    expect(screen.getByRole("region", { name: "SK하이닉스 클라우드 전환 프로젝트 현황" })).toBeInTheDocument();
  });
});
