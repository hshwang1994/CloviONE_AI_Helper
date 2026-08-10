import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { AUTOMATION_SCREENS } from "./automation.js";

/* 백엔드(app/jobs/router.py::_link_ids, round30 감사 E)는 이미 schedule_run/document_generate
 * 작업의 참조 ID(schedule_id/schedule_run_id/generation_id)를 응답에 내려주고 있었는데,
 * 프런트 작업 큐 화면이 그 값을 하나도 그리지 않아 '작업 큐 → 스케줄/문서로 돌아갈 길'이
 * idempotency_key 문자열 파싱뿐이었다(IA-02). detailFields에 크로스링크를 더한다.
 */
function field(key) {
  return AUTOMATION_SCREENS.jobs.detailFields.find((f) => f.key === key);
}

describe("작업 큐 상세 — 스케줄/문서 생성으로 돌아가는 링크", () => {
  it("schedule_id가 있으면 스케줄 상세로 가는 링크를 그린다", () => {
    render(field("schedule_id").render({ schedule_id: "sched-123" }));
    const link = screen.getByRole("link", { name: "sched-123" });
    expect(link).toHaveAttribute("href", "#/schedules?id=sched-123");
  });

  it("schedule_id가 없는(다른 유형) 작업은 링크 대신 대시를 보인다", () => {
    render(field("schedule_id").render({}));
    expect(screen.getByText("-")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("generation_id가 있으면 문서 생성 상세로 가는 링크를 그린다", () => {
    render(field("generation_id").render({ generation_id: "gen-456" }));
    const link = screen.getByRole("link", { name: "gen-456" });
    expect(link).toHaveAttribute("href", "#/documents?id=gen-456");
  });

  it("schedule_run_id는 여는 화면이 없어 링크 없이 참조값만 보인다(가짜 링크를 걸지 않는다)", () => {
    render(field("schedule_run_id").render({ schedule_run_id: "run-789" }));
    expect(screen.getByText("run-789")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });
});

/* 반대 방향(FN-13이 IA-02에 남겨 둔 나머지 절반) — 스케줄 실행 이력·문서 생성·실행 달력이
 * "이 실행을 처리한 작업"으로 갈 길이 아예 없었다. 백엔드에 job_id 컬럼을 새로 만드는 대신
 * (마이그레이션 없이) GET /api/admin/jobs가 payload_json 안의 schedule_id/schedule_run_id/
 * generation_id로 걸러 찾는 필터를 새로 받는다 — jobs.filters/onQuery가 그 필터를 소비한다.
 */
describe("스케줄 실행 이력 → 작업 큐로 가는 링크", () => {
  it("실행 이력 목록에 그 실행을 처리한 작업으로 가는 컬럼이 있다", () => {
    const runsSubList = AUTOMATION_SCREENS.schedules.actions
      .find((a) => a.label === "실행 이력").subList;
    const col = runsSubList.columns.find((c) => c.key === "job_link");
    render(col.render({ id: "run-abc" }));
    const link = screen.getByRole("link", { name: "보기" });
    expect(link).toHaveAttribute("href", "#/jobs?schedule_run_id=run-abc");
  });
});

describe("문서 생성 → 작업 큐로 가는 링크", () => {
  it("문서 생성 화면에 '작업 큐에서 보기' 액션이 그 문서의 generation_id로 이동한다", () => {
    const action = AUTOMATION_SCREENS.documents.actions.find((a) => a.label === "작업 큐에서 보기");
    expect(action).toBeTruthy();
    expect(action.navigate({ id: "gen-xyz" })).toBe("#/jobs?generation_id=gen-xyz");
  });
});

describe("작업 큐 — 스케줄/문서 생성 딥링크로 목록을 미리 거른다", () => {
  it("filters에 schedule_id/schedule_run_id/generation_id 텍스트 필터가 있다", () => {
    const keys = AUTOMATION_SCREENS.jobs.filters.map((f) => f.key);
    expect(keys).toEqual(expect.arrayContaining(["schedule_id", "schedule_run_id", "generation_id"]));
  });

  it("?schedule_run_id=로 들어오면 목록을 그 값으로 거른다(특정 행 하나를 여는 게 아니다)", () => {
    const intent = AUTOMATION_SCREENS.jobs.onQuery({ schedule_run_id: "run-789" });
    expect(intent).toEqual({ open: "filter", values: { schedule_id: undefined, schedule_run_id: "run-789", generation_id: undefined } });
  });

  it("?job_id=는 여전히 특정 작업 하나를 곧바로 연다(회귀 없음)", () => {
    const intent = AUTOMATION_SCREENS.jobs.onQuery({ job_id: "job-1" });
    expect(intent).toEqual({ open: "select", id: "job-1" });
  });

  it("아무 크로스링크 쿼리도 없으면 아무 것도 하지 않는다", () => {
    expect(AUTOMATION_SCREENS.jobs.onQuery({})).toBeNull();
  });
});
