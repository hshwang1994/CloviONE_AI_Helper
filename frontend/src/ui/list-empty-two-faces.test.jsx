import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { ListEmptyState } from "./kit.jsx";

/* W5 — 0건에는 **두 얼굴**이 있다 (PLAN C1 · 지시 0-2.17 · F-W5D-122).
 *
 * 「데이터가 아예 없다」와 「필터 때문에 0건이다」는 다른 사실이고 다음 행동도 다르다 —
 * 앞은 만들어야 하고 뒤는 조건을 풀어야 한다. 실측에서 이 분기가 제품 안에 여섯 벌로
 * 갈라져 있었고, 셋은 조건을 푸는 **버튼이 아예 없었으며**, `/projects` 는 분기 자체가 없어
 * 부서 필터로 0건이 된 화면을 「프로젝트가 없습니다」라고 말했다. 반대로 `/offboarding` 은
 * 검색어가 없어도 언제나 「조건에 해당하는…」이라고 했다.
 */
describe("ListEmptyState — 0건의 두 얼굴", () => {
  it("🔴 조건이 없으면 화면 고유의 «정말 없다» 안내를 그대로 쓴다", () => {
    render(
      <ListEmptyState
        filtered={false}
        onClear={() => {}}
        title="프로젝트가 없습니다"
        help="보관한 프로젝트까지 보려면 위의 스위치를 켜세요."
        filteredTitle="조건에 맞는 프로젝트가 없습니다"
      />
    );
    expect(screen.getByText("프로젝트가 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("조건에 맞는 프로젝트가 없습니다")).toBeNull();
    // 조건이 없는데 조건을 지우라고 하지 않는다.
    expect(screen.queryByRole("button", { name: /지우기/ })).toBeNull();
  });

  it("🔴 조건이 있으면 그 사실을 말하고 **지울 버튼**을 준다", async () => {
    const onClear = vi.fn();
    const user = userEvent.setup();
    render(
      <ListEmptyState
        filtered
        onClear={onClear}
        title="프로젝트가 없습니다"
        filteredTitle="조건에 맞는 프로젝트가 없습니다"
      />
    );
    expect(screen.getByText("조건에 맞는 프로젝트가 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("프로젝트가 없습니다")).toBeNull();
    await user.click(screen.getByRole("button", { name: "필터 지우기" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("복구 수단을 못 주는 호출부는 버튼을 그리지 않는다 — 누르면 아무 일도 없는 버튼이 더 나쁘다", () => {
    render(<ListEmptyState filtered title="없음" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("문구를 안 주면 기본 문구가 «무엇을 하면 되는지»까지 말한다 (지시 18)", () => {
    render(<ListEmptyState filtered onClear={() => {}} title="없음" />);
    expect(screen.getByText("조건에 맞는 항목이 없습니다")).toBeInTheDocument();
    expect(screen.getByText(/조건을 지우면 전체를 볼 수 있습니다/)).toBeInTheDocument();
  });

  it("버튼 문구는 호출부가 바꿀 수 있다 — 조건이 검색어뿐이면 «필터»라는 말이 거짓이다", () => {
    render(<ListEmptyState filtered onClear={() => {}} clearLabel="검색어 지우기" title="없음" />);
    expect(screen.getByRole("button", { name: "검색어 지우기" })).toBeInTheDocument();
  });
});
