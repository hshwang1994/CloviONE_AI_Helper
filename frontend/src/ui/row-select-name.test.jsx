import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { DataTable } from "./kit.jsx";
import { selectionColumn, useRowSelection } from "./bulkSelect.jsx";

/* 표 행 체크박스의 접근 이름 (접근성 감사 1).
 *
 * 감사가 본 상태: 스크린리더로 목록을 훑으면 "이 항목 선택" 이 스무 번 들린다. 어느 줄을
 * 고르는지 알 방법이 없어서, 표에서 선택해 일괄 삭제하는 흐름 자체를 쓸 수 없다.
 *
 * 여기서 못박는 것은 **두 가지**다:
 *   1) 이름에 그 행을 구별하는 값(제목, 이름)이 들어간다.
 *   2) 어느 열에서 그 값을 가져올지는 **열 정의**가 정한다(`rowName`). 화면마다 라벨
 *      문자열을 손으로 적으면 다음에 만드는 화면에서 반드시 빠진다.
 *
 * 질의는 DOM 속성이 아니라 접근 이름(getByRole(..., { name }))으로 한다 - 속성을 직접 보면
 * 실제로 낭독되는 이름과 다를 수 있다.
 */

const ROWS = [
  { id: "t-1", tid: 4101, title: "로그인 실패 조사" },
  { id: "t-2", tid: 4102, title: "배포 스크립트 정리" },
];

function Harness({ dataCols }) {
  const selection = useRowSelection();
  const columns = [selectionColumn(selection, ROWS.map((r) => r.id)), ...dataCols];
  return <DataTable columns={columns} rows={ROWS} rowKey={(r) => r.id} />;
}

// 실제 화면들처럼 식별 열이 render() 를 쓴다(제목이 링크나 굵은 글씨다).
const MARKED_COLS = [
  { key: "tid", label: "티켓", render: (r) => "GIT-" + r.tid },
  { key: "title", label: "제목", rowName: true, render: (r) => <b>{r.title}</b> },
];

// 표식이 없으면 render 없는 첫 열로 떨어진다(사용자 화면의 '이메일' 열이 이 경우다).
const PLAIN_COLS = [
  { key: "tid", label: "티켓", render: (r) => "GIT-" + r.tid },
  { key: "title", label: "제목" },
];

describe("표 행 체크박스 이름", () => {
  it("열 정의의 rowName 이 가리키는 값이 이름에 들어간다", () => {
    render(<Harness dataCols={MARKED_COLS} />);
    expect(screen.getByRole("checkbox", { name: "로그인 실패 조사 선택" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "배포 스크립트 정리 선택" })).toBeInTheDocument();
  });

  it("표식이 없으면 값을 그대로 쓰는 첫 열로 떨어진다", () => {
    render(<Harness dataCols={PLAIN_COLS} />);
    expect(screen.getByRole("checkbox", { name: "로그인 실패 조사 선택" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "배포 스크립트 정리 선택" })).toBeInTheDocument();
  });

  it("같은 이름이 행마다 반복되지 않는다", () => {
    render(<Harness dataCols={MARKED_COLS} />);
    expect(screen.queryAllByRole("checkbox", { name: "이 항목 선택" })).toHaveLength(0);
    // 머리글의 전체 선택은 그대로 하나 남는다.
    expect(screen.getAllByRole("checkbox", { name: "전체 선택" })).toHaveLength(1);
  });

  it("선택 열 자신은 이름의 출처가 되지 않는다", () => {
    // 선택 열이 columns[0] 이라, 그 열을 걸러내지 못하면 이름이 통째로 비어 예전 문구로 돌아간다.
    render(<Harness dataCols={PLAIN_COLS} />);
    const boxes = screen.getAllByRole("checkbox");
    const names = boxes.map((b) => b.getAttribute("aria-label"));
    expect(new Set(names).size).toBe(names.length);
  });
});
