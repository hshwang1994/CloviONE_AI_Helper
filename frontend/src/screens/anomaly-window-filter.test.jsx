import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { FilterSelect } from "../ui/filters.jsx";
import { REGISTRY } from "./registry.js";

/* 감사 이상 징후의 기간 필터에 「전체」가 없다 — 서버에 그런 상태가 없기 때문이다.
 *
 * 2026-09-06 배포 환경(clovirassist.gooddi.lab)에서 확인한 것: 「기간 전체」를 고르면
 * 요청에서 `window_hours` 가 빠지고, 서버는 그때 기본값 24시간으로 답한다
 * (`app/audit/anomalies.py::DEFAULT_WINDOW_HOURS`). 즉 「전체」는 「최근 24시간」이었다.
 * 그것을 고르고 0건을 본 관리자는 「징후가 없다」로 읽지만 실제로는 하루만 본 것이다.
 *
 * 고친 방향은 서버가 아니라 이름이다. 창을 두고 세는 것이 이 화면의 일이라 「전체」가
 * 답이 될 수 없다. 빈 값의 이름을 서버 기본값 그대로 「최근 24시간」이라 부르고, 같은 일을
 * 하는 항목이 목록에 둘 있지 않게 명시 항목에서는 24시간을 뺐다.
 *
 * 반례를 함께 잰다 — 「전체」가 답이 되는 다른 축(감사 로그의 대상)은 그대로 「… 전체」다.
 * 한쪽만 재면 「모든 select 에서 전체를 없앴다」도 통과한다.
 */

describe("감사 이상 징후 — 기간에 「전체」는 없다", () => {
  const cfg = REGISTRY["audit-anomalies"];
  const windowFilter = cfg.filters.find((f) => f.key === "window_hours");

  it("빈 값의 이름이 서버 기본값(최근 24시간)이다", () => {
    expect(windowFilter.allLabel).toBe("최근 24시간");
  });

  it("같은 일을 하는 항목을 둘 두지 않는다 — 명시 목록에 24시간이 없다", () => {
    expect(windowFilter.options.map((o) => o.value)).toEqual(["6", "168", "720"]);
  });

  it("화면 기본값을 따로 심지 않는다 — 빈 값이 곧 서버 기본값이다", () => {
    expect(windowFilter.value).toBeUndefined();
  });

  it("고르개에 「기간 전체」가 서지 않는다", () => {
    render(<FilterSelect label="기간" value="" onChange={() => {}}
      options={windowFilter.options} allLabel={windowFilter.allLabel} />);
    expect(screen.queryByText("기간 전체")).toBeNull();
    expect(screen.getByText("최근 24시간")).toBeInTheDocument();
  });

  it("반례 — 「전체」가 답이 되는 축은 그대로 「… 전체」다", () => {
    const objectType = REGISTRY.audit.filters.find((f) => f.key === "object_type");
    expect(objectType.allLabel).toBeUndefined();
    render(<FilterSelect label="대상" value="" onChange={() => {}} options={objectType.options || []} />);
    expect(screen.getByText("대상 전체")).toBeInTheDocument();
  });
});
