/* 화면 선언이 **서버와 같은 말을 하는가** — 백업 내려받기·감사 대상 이름표·전역 자원 쓰기.
 *
 * 여기서 못박는 것 넷:
 *   1. 「내려받기」는 `file_state` 를 다시 세지 않고 **서버가 낸 판정**(`downloadable`)을 쓴다.
 *      그 칸에 들어가는 값은 `present`/`removed` 둘뿐이라(app/backups/models.py) 예전 조건
 *      `file_state === "present"` 는 아무것도 거르지 못했다 — 실패한 백업에도, 디스크에서
 *      사라진 덤프에도 단추가 섰고 누르면 「백업 파일이 서버에 없습니다」로 끝났다.
 *   2. 감사 「대상」 필터에서 고르는 이름과 표에 찍히는 이름은 **같은 낱말**이다.
 *   3. 설정 화면의 좁은 탭으로 가는 딥링크는 그 탭에 들어갈 수 있는 역할에게만 뜬다.
 *   4. 서버가 전역 범위 관리자로 한정한 쓰기는 선언에도 그렇게 적혀 있다.
 *
 * 반례를 함께 둔다 — 고쳐야 할 것만 사라지고 멀쩡한 것은 그대로여야 한다.
 *
 * qa-contract-change: 프롬프트 화면이 기능마다 한 줄이 되며(D-541) 「만들기」 · 「발행」 · 「새 버전」 · 「보관」 · 「복제해서 수정」이 없어지고 그 자리에 「수정」(그 기능의 초안) · 「초안 발행」 · 「초안 버리기」 · 「기본 제공으로 되돌리기」가 섰다. 같은 성질 — 전사 지시문을 바꾸는 쓰기는 전역 범위만 — 을 새 동작 이름으로 계속 잰다. 정책 화면의 선언은 그대로다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */
import { describe, it, expect } from "vitest";

import {
  OBJTYPE_OPTS, canReachObjRoute, objTypeKo,
} from "./shared.js";
import { PLATFORM_SCREENS } from "./platform.js";
import { GOVERNANCE_SCREENS } from "./governance.js";
import { AUTOMATION_SCREENS } from "./automation.js";
import { AUTHORING_SCREENS } from "./authoring.js";

const backup = PLATFORM_SCREENS.backup;
const actionByLabel = (config, label) => config.actions.find((a) => a.label === label);
const colByKey = (config, key) => config.columns.find((c) => c.key === key);

describe("백업 「내려받기」는 서버의 판정을 쓴다 (R8-01)", () => {
  const download = actionByLabel(backup, "내려받기");

  it("디스크에서 사라진 덤프에는 단추가 서지 않는다 — file_state 는 여전히 present 다", () => {
    const row = {
      id: "b1", status: "succeeded", file_state: "present",
      downloadable: false, download_blocked_reason: "missing",
    };
    expect(download.when(row)).toBe(false);
  });

  it("실패한 백업에도 서지 않는다(서버가 받을 덤프가 없다고 답한다)", () => {
    expect(download.when({
      id: "b2", status: "failed", file_state: "present",
      downloadable: false, download_blocked_reason: "failed",
    })).toBe(false);
  });

  it("반례 — 서버가 받을 수 있다고 답한 행에는 그대로 뜬다", () => {
    expect(download.when({
      id: "b3", status: "succeeded", file_state: "present", downloadable: true,
      download_blocked_reason: null,
    })).toBe(true);
  });

  it("반례 — 그 필드를 안 싣는 옛 응답에서는 예전 조건 그대로 동작한다", () => {
    expect(download.when({ id: "b4", status: "succeeded", file_state: "present" })).toBe(true);
    expect(download.when({ id: "b5", status: "running", file_state: "present" })).toBe(false);
    expect(download.when({ id: "b6", status: "succeeded", file_state: "removed" })).toBe(false);
  });

  it("「검증」은 이 판정을 쓰지 않는다 — 실패한 세트를 다시 확인하는 것이 그 목적이다", () => {
    const verify = actionByLabel(backup, "검증");
    expect(verify.when({
      id: "b7", status: "failed", file_state: "present",
      downloadable: false, download_blocked_reason: "failed",
    })).toBe(true);
    // 서버에서 지운 백업에는 검증할 파일이 없다 — 그건 그대로 감춘다.
    expect(verify.when({ id: "b8", status: "succeeded", file_state: "removed" })).toBe(false);
  });

  it("「서버 파일」 열은 서버에 없는 파일을 「있음」이라고 말하지 않는다", () => {
    const col = colByKey(backup, "file_state");
    const value = (row) => col.render(row).props.value;
    expect(value({ file_state: "present", downloadable: false, download_blocked_reason: "missing" }))
      .toBe("서버에 없음");
    // 반례 둘 — 지운 것과 멀쩡한 것은 예전 그대로 말한다.
    expect(value({ file_state: "removed" })).toBe("삭제함");
    expect(value({ file_state: "present", downloadable: true })).toBe("있음");
    expect(value({ file_state: "present" })).toBe("있음");
  });
});

describe("감사 「대상」은 고른 이름과 보이는 이름이 같다 (R8-05)", () => {
  it("필터 선택지 전량이 표의 이름표와 한 글자도 다르지 않다", () => {
    const mismatched = OBJTYPE_OPTS
      .filter((o) => objTypeKo(o.value) !== o.label)
      .map((o) => o.value + ": 고른 이름 「" + o.label + "」 vs 보이는 이름 「" + objTypeKo(o.value) + "」");
    expect(mismatched).toEqual([]);
    // 표본이 실제로 있었는지 함께 본다 — 빈 목록을 도는 통과는 통과가 아니다.
    expect(OBJTYPE_OPTS.length).toBeGreaterThan(30);
  });

  it("가장 나빴던 짝 — 「문서 생성(옛 기능)」과 「문서」가 표에서 갈린다", () => {
    expect(objTypeKo("document_generation")).toBe("문서 생성(옛 기능)");
    expect(objTypeKo("document")).toBe("문서");
    expect(objTypeKo("document_generation")).not.toBe(objTypeKo("document"));
  });

  it("반례 — 선택지에 없는 값은 공용 사전이 받고, 둘 다 모르면 원문이 남는다", () => {
    expect(objTypeKo("conversation")).toBe("대화");
    expect(objTypeKo("nonexistent_kind")).toBe("nonexistent_kind");
    expect(objTypeKo(null)).toBe("-");
    expect(objTypeKo("")).toBe("-");
  });
});

describe("설정 탭 딥링크는 그 탭에 들어갈 수 있는 역할에게만 (R8-02)", () => {
  it("파일 저장소·AI 설정은 시스템 관리자만 닿는다", () => {
    for (const objType of ["storage_provider", "llm_config", "ai_config"]) {
      expect(canReachObjRoute(objType, "system_admin")).toBe(true);
      expect(canReachObjRoute(objType, "admin")).toBe(false);
      expect(canReachObjRoute(objType, "operator")).toBe(false);
      expect(canReachObjRoute(objType, "auditor")).toBe(false);
    }
  });

  it("반례 — 메일 발송 화면은 콘솔 읽기 역할이면 다 들어가므로 그대로 열린다", () => {
    expect(canReachObjRoute("mail_delivery", "auditor")).toBe(true);
    expect(canReachObjRoute("mail_delivery", "operator")).toBe(true);
  });
});

describe("승인 위임 폼은 서버가 거절할 값을 미리 말한다 (R1-04)", () => {
  const fields = GOVERNANCE_SCREENS["approval-delegations"].create.fields;
  const field = (name) => fields.find((f) => f.name === name);

  it("대리 승인자 칸이 감사자를 고를 수 없다는 사실을 적는다", () => {
    expect(field("delegate_user_id").help).toContain("감사자");
  });

  it("종료 칸이 「지금보다 뒤」라는 새 규칙을 적는다", () => {
    const help = field("ends_at").help;
    expect(help).toContain("지금보다 뒤");
    expect(help).toContain("90일");
    // 조각 문장을 쓰지 않는다(CLAUDE.md §10) — 마침표로 끝나는 완전한 문장이다.
    expect(help.trim().endsWith("다.")).toBe(true);
  });

  it("두 도움말 어디에도 줄바꿈 문자가 없다(CLAUDE.md §10)", () => {
    for (const name of ["delegator_user_id", "delegate_user_id", "ends_at"]) {
      expect(field(name).help).not.toContain("\n");
    }
  });
});

/* 서버가 `require_global_management`(또는 같은 뜻의 `management.is_global` 검사)로 막는 쓰기는
 * 화면 선언도 같은 축을 말해야 한다 — 안 그러면 부서 범위 관리자에게 **반드시 403 이 되는
 * 단추**가 그려진다. 짝은 서버 코드에서 직접 확인한 것만 적는다. */
describe("전역 자원의 쓰기 선언이 서버 게이트와 같다 (xa-07)", () => {
  const ann = PLATFORM_SCREENS.announcements;
  const sched = AUTOMATION_SCREENS.schedules;

  it("공지 배너 — 만들기·고치기·사용 여부·삭제 전부", () => {
    expect(ann.create.requiresGlobalScope).toBe(true);
    expect(ann.edit.requiresGlobalScope).toBe(true);
    for (const label of ["사용", "사용 안 함", "삭제"]) {
      expect(actionByLabel(ann, label).requiresGlobalScope).toBe(true);
    }
  });

  it("실행 일정 — 만들기·고치기·활성화·비활성화", () => {
    expect(sched.create.requiresGlobalScope).toBe(true);
    expect(sched.edit.requiresGlobalScope).toBe(true);
    expect(actionByLabel(sched, "활성화").requiresGlobalScope).toBe(true);
    expect(actionByLabel(sched, "비활성화").requiresGlobalScope).toBe(true);
  });

  it("반례 — 「지금 실행」·「미리보기」는 서버가 운영 역할에 열어 두었으므로 가리지 않는다", () => {
    expect(actionByLabel(sched, "지금 실행").requiresGlobalScope).toBeUndefined();
    expect(actionByLabel(sched, "미리 보기").requiresGlobalScope).toBeUndefined();
  });

  it("프롬프트·정책 — 만들기·고치기·상태 전이·새 버전", () => {
    const policies = AUTHORING_SCREENS.policies;
    expect(policies.create.requiresGlobalScope).toBe(true);
    expect(policies.edit.requiresGlobalScope).toBe(true);
    // 생명주기는 초안 → 발행 → 보관이다(D-518) - 「테스트로」 · 「검토로」 · 「초안으로 되돌리기」는 없다.
    for (const label of ["발행", "새 버전", "보관"]) {
      expect(actionByLabel(policies, label).requiresGlobalScope).toBe(true);
    }
    // 프롬프트는 기능마다 한 줄이라 만들기가 없다(D-541). 「수정」은 그 기능의 초안을 고치고, 발행 · 버리기 · 기본 제공으로
    // 되돌리기는 모두 전사 지시문을 바꾸는 쓰기라 같은 문을 지난다.
    const prompts = AUTHORING_SCREENS.prompts;
    expect(prompts.create).toBeUndefined();
    expect(prompts.edit.requiresGlobalScope).toBe(true);
    for (const label of ["초안 발행", "초안 버리기", "기본 제공으로 되돌리기"]) {
      expect(actionByLabel(prompts, label).requiresGlobalScope).toBe(true);
    }
    // 반례 — 버전 기록은 읽기라 범위 선언이 없다.
    expect(actionByLabel(prompts, "버전 기록").requiresGlobalScope).toBeUndefined();
  });

  it("AI 상한은 **행마다** 다르다 — 전역 행만 가리고 사용자 행은 그대로 둔다", () => {
    const del = actionByLabel(PLATFORM_SCREENS["ai-quotas"], "삭제");
    // 선언 한 줄로 가리면 부서 범위 관리자가 자기 사람들의 상한까지 못 지운다.
    expect(del.requiresGlobalScope).toBeUndefined();
    const deptAdmin = { role: "admin", managementScope: "dept", isGlobalAdmin: false };
    const globalAdmin = { role: "admin", managementScope: "global", isGlobalAdmin: true };
    expect(del.when({ scope_type: "global" }, deptAdmin)).toBe(false);
    expect(del.when({ scope_type: "user" }, deptAdmin)).toBe(true);
    expect(del.when({ scope_type: "global" }, globalAdmin)).toBe(true);
    // 반례 — 범위를 안 싣는 옛 맥락에서는 예전처럼 그대로 보인다.
    expect(del.when({ scope_type: "global" }, undefined)).toBe(true);
  });
});
