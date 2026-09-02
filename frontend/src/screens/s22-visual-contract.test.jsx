import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { REGISTRY } from "./registry.js";
import { CONTROL, remPx } from "../ui/theme.js";
import { COLUMN_TYPES, resolveColumn } from "../ui/columnTypes.js";

/* S22 Final UI Audit 이 실브라우저에서 잡은 시각 결함 넷을 **뿌리에서** 못 박는다.
 *
 * 넷 다 「눌러 보면 되는데 보기가 틀린」 종류라 기능 시험이 잡을 수 없었다. 전량 캡처
 * (81 화면 × 2 테마 × 9 뷰포트)가 처음 봤고, 여기서는 그 캡처 없이도 되돌아오지 않게
 * 각 결함의 **원인 값**을 직접 확인한다.
 */

describe("개수 열은 가운데 정렬 + 자릿수 고정이다 (numeric_alignment)", () => {
  /* 부서·직책의 인원 열만 어휘를 안 쓰고 있었다 — 42페이지에서 실패했다.
     (부서 표는 조직 콘솔 재구성으로 registry 를 떠났다 — 규칙은 남은 직책이 진다.) */
  it.each([
    ["job-titles", "user_count"],
  ])("%s 의 %s 열이 count 어휘를 쓴다", (key, colKey) => {
    const cfg = REGISTRY[key];
    expect(cfg, `레지스트리에 ${key} 가 없다`).toBeTruthy();
    const col = (cfg.columns || []).find((c) => c.key === colKey);
    expect(col, `${key} 에 ${colKey} 열이 없다`).toBeTruthy();
    expect(col.type).toBe("count");
    const resolved = resolveColumn(col);
    expect(resolved.align).toBe("center");
    expect(resolved.numeric).toBe(true);
  });

  it("반대 방향 — 어휘 자체가 가운데 정렬·자릿수 고정을 함께 준다", () => {
    // 이 사례가 없으면 위 둘은 «count 라고 적었다» 까지만 증명한다.
    // 우정렬에서 가운데로 옮긴 것은 지시 6·13 이고, 자릿수 고정은 그대로 남는다.
    expect(COLUMN_TYPES.count.align).toBe("center");
    expect(COLUMN_TYPES.count.numeric).toBe(true);
  });
});

describe("표 머리글의 두 조작기는 같은 높이로 선다 (control_baseline_mismatch)", () => {
  it("정렬 단추와 필터 단추가 같은 토큰 높이를 갖는다", async () => {
    const { TableHeaderCell } = await import("../ui/TableHeaderCell.jsx");
    const column = { key: "status", label: "상태", sortable: true, filter: { type: "text" } };
    render(
      <table><thead><tr>
        <TableHeaderCell
          column={column}
          sort={{ key: "", dir: "" }}
          onSort={() => {}}
          onFilter={() => {}}
          filterValue=""
        />
      </tr></thead></table>,
    );
    const sortButton = screen.getByRole("button", { name: "상태" });
    const filterButton = screen.getByRole("button", { name: "상태 필터" });
    const want = remPx(CONTROL.tableCellDense);
    expect(want).toBe("2rem");
    // 🔴 **둘이 같은 값이어야 한다.** 한쪽만 재면 「둘 다 안 걸렸다」와 구별되지 않으므로
    // 값이 실제로 그 토큰인지도 함께 본다.
    expect(getComputedStyle(sortButton).minHeight).toBe(want);
    expect(getComputedStyle(filterButton).minHeight).toBe(want);
    expect(getComputedStyle(filterButton).height).toBe(want);
  });
});

describe("게시글 반응 칩은 px 가 아니라 토큰으로 선다 (4K 레버)", () => {
  it("작은 버튼 높이가 rem 이라 루트 폰트사이즈를 함께 탄다", () => {
    // 🔴 S18 은 이 값을 `30`(px)이라고 적었고, 그래서 3072·3840 에서 옆 버튼만 자라
    // 7.5px 이 다시 어긋났다. 토큰은 rem 이라 같이 자란다.
    expect(remPx(CONTROL.buttonSm)).toMatch(/rem$/);
    expect(remPx(CONTROL.buttonSm)).toBe("1.875rem");
  });
});

describe("내 프로필의 두 칸은 똑같이 나누지 않는다 (equal_column_split)", () => {
  it("두 줄이 서로 다른 쪽으로 기울어 있다", async () => {
    const src = await import("./Profile.jsx");
    expect(src).toBeTruthy();
    // 값 자체는 모듈 밖으로 안 나간다(내부 상수). 계약은 «두 줄의 가중치가 서로 다르고
    // 어느 쪽도 1:1 이 아니다» 이고, 그것을 소스에서 직접 확인한다.
    const text = PROFILE_SOURCE;
    expect(text).toContain("minmax(0, 0.85fr) minmax(0, 1.15fr)");
    expect(text).toContain("minmax(0, 1.15fr) minmax(0, 0.85fr)");
    expect(text).not.toContain('lg: "minmax(0, 1fr) minmax(0, 1fr)"');
  });
});

/* 소스 문자열은 번들러가 아니라 시험이 읽는다 — `?raw` 는 vite 가 준다. */
import PROFILE_SOURCE from "./Profile.jsx?raw";
