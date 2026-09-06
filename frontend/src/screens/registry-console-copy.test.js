import { describe, it, expect } from "vitest";
import { AUTOMATION_SCREENS } from "./registry/automation.js";
import { GOVERNANCE_SCREENS } from "./registry/governance.js";
import { PLATFORM_SCREENS } from "./registry/platform.js";
import { PEOPLE_ACTIVE_REF_LIST, PEOPLE_REF_LIST } from "./registry/shared.js";

/* 관리 콘솔 registry 의 남은 잔여 넷 — 폼·문구·후보 목록·형식기.
 *
 * 하나씩은 작지만 전부 「화면이 사실이 아닌 말을 한다」는 같은 종류다.
 */

const schedules = AUTOMATION_SCREENS.schedules;
const jobs = AUTOMATION_SCREENS.jobs;
const delegations = GOVERNANCE_SCREENS["approval-delegations"];

function editFieldsFor(row) {
  return schedules.edit.fields("system_admin", row);
}
const targetField = (row) => editFieldsFor(row).find((f) => f.name === "target_ref");

describe("실행 일정 수정 폼 — 저장된 대상을 후보에서 지우지 않는다 (ops-11)", () => {
  it("지금 값이 noop 이 아니면 그 값이 후보에 남는다 — 설명 한 줄을 고칠 수 있어야 한다", () => {
    const f = targetField({ target_type: "system", target_ref: "ai.summarize" });
    const values = f.options.map((o) => o.value);
    expect(values).toContain("ai.summarize");
    expect(values).toContain("noop");
    // 무엇을 고르는 것인지 이름표가 말한다.
    expect(f.options[0].label).toBe("ai.summarize (지금 값)");
    expect(f.help).toContain("지금 값을 그대로 두면");
  });

  it("반례 — 지금 값이 noop 이면 후보는 하나뿐이다(없는 대상을 권하지 않는다)", () => {
    const f = targetField({ target_type: "system", target_ref: "noop" });
    expect(f.options.map((o) => o.value)).toEqual(["noop"]);
    expect(f.help).toBe("지금 예약할 수 있는 대상은 시스템 작업 하나입니다.");
  });

  it("만드는 폼은 그대로다 — 새로 고를 수 있는 대상은 여전히 하나다", () => {
    const f = schedules.create.fields.find((x) => x.name === "target_ref");
    expect(f.options.map((o) => o.value)).toEqual(["noop"]);
  });
});

describe("실행 일정 미리보기 — 목록이 쉼표로 시작하지 않는다 (ops-15)", () => {
  const preview = schedules.actions.find((a) => a.label === "미리보기");

  it("각 줄이 글머리표로 시작한다 — 문장 부호는 줄 앞에 오지 않는다", () => {
    const text = preview.info({
      next_fire_times_utc: ["2026-09-07T00:00:00", "2026-09-14T00:00:00"],
      target_type: "system", target_ref: "noop", payload_preview: null,
    });
    const lines = text.split("\n");
    /* 글머리표는 하이픈이다. 가운뎃점은 이 제품이 화면 문구에서 쓰지 않기로 한 글자라
       (`scripts/check_user_text.py`) 같은 뜻을 하이픈으로 적는다. 이 시험이 지키는 성질은
       글자가 아니라 자리다 — 줄이 문장 부호(쉼표)로 시작하지 않는다. */
    const times = lines.filter((l) => /^[-,]/.test(l.trim()) || /^,/.test(l));
    expect(times.length).toBe(2);
    for (const l of times) expect(l.startsWith("- ")).toBe(true);
    expect(text).not.toContain("\n, ");
  });

  it("반례 — 예정된 실행이 없으면 예전 그대로 그 사실을 말한다", () => {
    const text = preview.info({ next_fire_times_utc: [], target_type: "system", target_ref: "noop" });
    expect(text).toContain("(예정된 실행 시각 없음)");
  });
});

describe("작업 취소 확인 문구 — 실제로 일어나는 일만 말한다 (ops-16)", () => {
  const cancel = jobs.actions.find((a) => a.label === "취소");

  it("없어진 잡 유형(티켓·문서)을 정리한다고 말하지 않는다", () => {
    expect(cancel.confirm).toBe(
      "대기 중인 이 작업을 취소할까요? 연결된 예약 실행이나 채팅 요청도 함께 종료됩니다."
    );
    expect(cancel.confirm).not.toContain("티켓");
    expect(cancel.confirm).not.toContain("문서");
  });
});

describe("승인 위임 — 없는 수정 경로로 보내지 않는다 (perm-05)", () => {
  it("「수정」 단추가 어떤 행에서도 뜨지 않는다(백엔드에 PATCH 가 없다)", () => {
    expect(typeof delegations.editWhen).toBe("function");
    expect(delegations.editWhen({ state: "active" })).toBe(false);
    expect(delegations.editWhen({ state: "scheduled" })).toBe(false);
    expect(delegations.edit).toBeUndefined();
  });

  it("반례 — 실제로 있는 두 동작은 그대로 남는다", () => {
    const labels = delegations.actions.map((a) => a.label);
    expect(labels).toContain("위임 거두기");
    expect(delegations.createLabel).toBe("위임 추가");
  });
});

describe("사람 후보 — 만드는 폼은 보관된 계정을 권하지 않는다 (xb-10)", () => {
  it("AI 사용 상한과 승인 위임은 활성 계정만 후보로 받는다", () => {
    expect(PLATFORM_SCREENS["ai-quotas"].refLists).toEqual([PEOPLE_ACTIVE_REF_LIST]);
    expect(delegations.refLists).toEqual([PEOPLE_ACTIVE_REF_LIST]);
    expect(PEOPLE_ACTIVE_REF_LIST.endpoint).toBe("/api/admin/people?include_archived=false");
  });

  it("반례 — 옛 기록을 거르는 화면(감사·대리 보기)은 보관된 사람도 계속 고를 수 있다", () => {
    expect(GOVERNANCE_SCREENS.audit.refLists).toEqual([PEOPLE_REF_LIST]);
    expect(GOVERNANCE_SCREENS.impersonation.refLists).toEqual([PEOPLE_REF_LIST]);
    expect(PEOPLE_REF_LIST.endpoint).toBe("/api/admin/people");
  });
});

describe("한 화면 안의 시각은 한 형식이다 (ops-14)", () => {
  /* `dateCol` 은 `DateCell`(fmtDateTimeCompact) 이라 「2026-09-06 01:53」이고, 손으로 적은
     `render` 가 `fmtDateTime` 이면 「2026. 9. 7. 오전 9:00」이다. 두 형식이 한 행에 섞이면
     이웃한 두 칸을 눈으로 대조할 수 없다. */
  const ISO = "2026-09-07T00:00:00";
  const COMPACT = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

  it("실행 일정의 「다음 실행」이 옆 칸(dateCol)과 같은 모양이다", () => {
    const col = schedules.columns.find((c) => c.key === "next_run_at");
    expect(col.render({ enabled: true, next_run_at: ISO })).toMatch(COMPACT);
  });

  it("작업 큐 상세의 「실행 예정」도 같은 모양이다", () => {
    const f = jobs.detailFields.find((c) => c.key === "available_at_full");
    expect(f.render({ available_at: ISO })).toMatch(COMPACT);
  });

  it("복구 리허설 상세 제목의 시각도 같은 모양이다", () => {
    const col = PLATFORM_SCREENS["restore-drills"].columns.find((c) => c.key === "source_label");
    expect(col.rowName({ source_label: "20260823-020000", started_at: ISO }))
      .toBe("20260823-020000 / " + "2026-09-07 09:00");
  });

  it("승인의 「만료」와 위임의 「종료」도 같은 모양이다", () => {
    const expires = GOVERNANCE_SCREENS.approvals.columns.find((c) => c.key === "expires_at");
    expect(expires.render({ status: "pending", expires_at: ISO })).toMatch(COMPACT);
    const ends = delegations.columns.find((c) => c.key === "ends_at");
    expect(ends.render({ state: "active", ends_at: ISO })).toMatch(COMPACT);
  });

  it("반례 — 값이 없으면 예전 그대로 '-' 다(빈 값을 시각처럼 그리지 않는다)", () => {
    const col = schedules.columns.find((c) => c.key === "next_run_at");
    expect(col.render({ enabled: false, next_run_at: ISO })).toBe("-");
    const f = jobs.detailFields.find((c) => c.key === "available_at_full");
    expect(f.render({ available_at: null })).toBe("-");
  });
});
