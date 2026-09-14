import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { REGISTRY } from "./registry.js";
import { CONTROL, remPx } from "../ui/theme.js";
import { COLUMN_TYPES, resolveColumn } from "../ui/columnTypes.js";
import { pairTracks } from "../ui/density.js";

/* qa-contract-change: 표 머리글 조작기 토큰(tableCellDense)이 32 에서 작은 단추와 같은 30 으로 내려갔다(핸드오프 단추 크기 두 단계, 계획 B-7) — 그 값 단언을 옮기고 「작은 단추와 같은 값」 단언을 더한다.
 *
 * S22 Final UI Audit 이 실브라우저에서 잡은 시각 결함 넷을 **뿌리에서** 못 박는다.
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
    expect(want).toBe("1.875rem");
    // 표 안 조작기는 작은 단추와 같은 높이다 — 단추 높이는 34 와 30 두 단계뿐이다.
    expect(CONTROL.tableCellDense).toBe(CONTROL.buttonSm);
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

/* qa-contract-change: 내 프로필의 두 줄은 이제 같은 값으로 나눈다 — 예전 계약은 「줄마다 반대로 기울인다」였고 그 근거였던 2.88배는 폭이 아니라 줄당 글자 수였다(assertions.py demandOf, P-73 이 위양성으로 기록). 게다가 1.35 로 기울이면 그 검사는 assertions.py:955 에서 건너뛰므로 이 화면은 검사를 받은 적이 없다. 단언은 늘었다 — 죽어 있던 줄 하나를 살리고 「두 줄이 같은 이음매를 쓴다」를 새로 잰다. */
describe("내 프로필의 두 줄은 같은 자리에서 나눠진다 (equal_column_split)", () => {
  /* qa-contract-change: 설정 줄이 둘에서 **하나**가 됐다(5-3 시안 #5c — 신원 머리가 전폭으로
     빠지면서 계정 판이 두 열 밖으로 나갔다). 「두 자리가 같은 값을 쓴다」는 잴 대상이 하나뿐이라
     성립하지 않으므로, 지우지 않고 그 자리에 남은 성질을 잰다: 값은 여전히 반반이고, 기울인
     값으로 되돌아가지 않으며, 손으로 그린 격자가 그 자리를 대신하지 않는다. */
  it("설정 줄이 공용 반반 값을 쓴다 — 손으로 그린 격자가 그 자리를 대신하지 않는다", async () => {
    const src = await import("./Profile.jsx");
    expect(src).toBeTruthy();
    // 값 자체는 모듈 밖으로 안 나간다(내부 상수) — 소스에서 직접 확인한다.
    const text = PROFILE_SOURCE;
    expect(text).toContain('const TWO_COL_EVEN = pairTracks("minmax(0, 1fr) minmax(0, 1fr)")');
    // 두 열로 나누는 자리는 **하나**이고, 그 하나가 공용 값을 쓴다.
    expect(text.match(/sx=\{TWO_COL_EVEN\}/g) || []).toHaveLength(1);
    /* 🔴 반례 — 「두 열」을 손으로 다시 그리면 이 상수를 안 거치고 값이 갈린다. 두 칸짜리
       트랙 문자열이 소스에 직접 나타나면 안 된다(공용 값은 `pairTracks` 인자로만 나온다). */
    expect(text.match(/gridTemplateColumns:\s*"minmax\(0, 1fr\) minmax\(0, 1fr\)"/g) || []).toHaveLength(0);
    // 반례 — 줄마다 다른 가중치로 되돌아가면 이음매가 다시 어긋난다.
    expect(text).not.toContain("minmax(0, 0.85fr) minmax(0, 1.15fr)");
    expect(text).not.toContain("minmax(0, 1.15fr) minmax(0, 0.85fr)");
    // 신원 머리는 그 줄 **밖**이다 — 안으로 들어가면 한 열 폭으로 접힌다.
    expect(text).toContain("<IdentityHeader");
    expect(text.indexOf("<IdentityHeader")).toBeLessThan(text.indexOf("sx={TWO_COL_EVEN}"));
  });

  it("높이를 맞추는 결정은 그대로다 — 폭을 같게 했다고 바닥 정렬을 놓지 않는다", () => {
    /* 예전 주석이 적어 둔 것처럼 「줄 바닥을 맞추는 것」과 「폭을 반씩 주는 것」은 다른
       결정이다. 이번에 둘째를 바꿨으니 첫째가 따라 넘어가지 않았는지를 같은 자리에서 잰다. */
    expect(pairTracks("minmax(0, 1fr) minmax(0, 1fr)").alignItems).toBe("stretch");
  });

  it("반례 — 이 묶음이 실제로 깨질 수 있는 문자열을 본다", () => {
    /* 예전 세 번째 단언은 `lg: "minmax(0, 1fr) minmax(0, 1fr)"` 를 금했는데, `lg:` 는
       `pairTracks` 가 붙이는 것이고 Profile.jsx 에는 한 번도 안 나온다 — 어떤 소스에서도
       안 깨지는 죽은 줄이었다. 같은 실수를 반복하지 않게, 이 묶음이 읽는 소스가 실제로
       그 화면의 것이고 검사 대상 문자열을 담고 있는지 먼저 확인한다. */
    expect(PROFILE_SOURCE).not.toContain("lg:");
    expect(PROFILE_SOURCE).toContain("pairTracks(");
    expect(PROFILE_SOURCE).toContain("내 프로필");
  });
});

/* 소스 문자열은 번들러가 아니라 시험이 읽는다 — `?raw` 는 vite 가 준다. */
import PROFILE_SOURCE from "./Profile.jsx?raw";
