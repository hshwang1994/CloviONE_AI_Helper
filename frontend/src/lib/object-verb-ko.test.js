import { describe, it, expect } from "vitest";

import { objKo, actionKo, approvalTypeKo } from "./format.js";

/* organization/feature_flag는 OBJ_ROUTE(registry/shared.js)에 먼저 추가됐지만 표시용 사전
 * (OBJECT_KO/VERB_KO)엔 한 번도 안 들어와 있었다 — 감사 로그의 '대상'/'작업' 칸에 영어 원문이
 * 샜다. ai_quota/approval_delegation/announcement/offboarding(.run/.undo)도 MEGA CYCLE G의
 * 크로스링크 조사에서 같은 결함 부류로 함께 발견했다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */
describe("감사 로그 '대상' 칸 — 새로 채운 object_type 번역", () => {
  it.each([
    ["organization", "조직"],
    ["feature_flag", "기능 플래그"],
    ["ai_quota", "AI 사용 한도"],
    ["approval_delegation", "승인 위임"],
    ["announcement", "공지"],
    ["offboarding_run", "오프보딩"],
  ])("objKo('%s') === '%s' — 영어 원문이 새지 않는다", (raw, ko) => {
    expect(objKo(raw)).toBe(ko);
  });
});

/* qa-contract-change: 감사 동작은 쉼표로 이은 두 낱말(「오프보딩, 실행」)이 아니라 「대상 동작」 명사구(「오프보딩 실행」)다(계획 5절).
   같은 두 사례의 기대값만 새 모양으로 바꾸고, 승인 유형 사전이 서버 낱말과 같다는 단언을 더한다. */
describe("감사 로그 '작업' 칸 — offboarding.run/offboarding.undo", () => {
  it("offboarding.run은 '오프보딩 실행'으로 번역된다(예전엔 'offboarding, 실행')", () => {
    expect(actionKo("offboarding.run")).toBe("오프보딩 실행");
  });

  it("offboarding.undo는 '오프보딩 되돌리기'로 번역된다(예전엔 'offboarding, undo')", () => {
    expect(actionKo("offboarding.undo")).toBe("오프보딩 되돌리기");
  });

  it("두 낱말을 쉼표로 잇지 않는다 — 「스케줄 활성화」", () => {
    expect(actionKo("schedule.enable")).toBe("실행 일정 활성화");
    expect(actionKo("schedule.enable")).not.toMatch(/,/);
  });
});

describe("승인 요청 유형 — 서버와 같은 낱말", () => {
  it.each([
    ["user.role_change", "역할 변경"],
    ["integration.change_config", "연동 설정 변경"],
    ["schedule.enable", "실행 일정 활성화"],
    ["ai.document_create", "AI 문서 만들기"],
  ])("approvalTypeKo('%s') === '%s'", (raw, ko) => {
    expect(approvalTypeKo(raw)).toBe(ko);
  });

  it("사전에 없는 유형은 감사 동작 번역으로 대신하고 빈 값은 「-」다", () => {
    expect(approvalTypeKo("offboarding.run")).toBe("오프보딩 실행");
    expect(approvalTypeKo("")).toBe("-");
  });
});

/* r23 — 서버가 기록하는 감사 동작 · 대상 **전부**가 한국어 이름을 갖는가.
 *
 * 감사 로그 「작업」 칸에 「project 추가」 · 「board.post 수정」 · 「mail test_send」가 보였다 — 서버가 기록하는 동작 184 개 가운데
 * 113 개의 대상 낱말이 사전에 없었다(r23 화면 대장 67 · 30). 사전에 하나씩 더하는 것으로는 다음 동작에서 또 샌다. 그래서 서버
 * 소스(`app/**`)의 `action="대상.동작"` · `object_type="…"` 글자를 훑어, 번역 결과에 영문이 남는 것이 하나라도 있으면 실패한다.
 * 굳어진 영문 약어(AI · CLI · CSV · DKIM …)는 우리말 낱말이 없어 그대로 둔다. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../app");
function pyFiles(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) { if (entry.name !== "__pycache__" && entry.name !== "static") pyFiles(full, out); }
    else if (entry.name.endsWith(".py")) out.push(full);
  }
  return out;
}
function literalsOf(re) {
  const found = new Set();
  for (const file of pyFiles(APP_DIR)) {
    const text = fs.readFileSync(file, "utf8");
    for (const m of text.matchAll(re)) found.add(m[1]);
  }
  return found;
}
const LATIN_OK = /\b(AI|CLI|CSV|DKIM|DNS|TLS|SMTP|Notion|ChatGPT)\b/g;
const hasLatin = (s) => /[A-Za-z]/.test(String(s).replace(LATIN_OK, ""));

describe("서버가 기록하는 감사 동작 · 대상은 전부 한국어 이름이 있다", () => {
  it("action=\"대상.동작\" — 번역에 영문이 남지 않는다", () => {
    const actions = literalsOf(/action=["']([a-z_]+(?:\.[a-z_]+)+)["']/g);
    expect(actions.size, "서버 소스에서 감사 동작을 못 찾았다(훑는 경로가 틀렸다)").toBeGreaterThan(150);
    const bad = [...actions].filter((a) => hasLatin(actionKo(a))).map((a) => `${a} → ${actionKo(a)}`);
    expect(bad).toEqual([]);
  });

  it("object_type=\"…\" — 대상 칸에 영문 원문이 새지 않는다", () => {
    const objects = literalsOf(/object_type=["']([a-z_]+)["']/g);
    expect(objects.size).toBeGreaterThan(30);
    const bad = [...objects].filter((o) => hasLatin(objKo(o))).map((o) => `${o} → ${objKo(o)}`);
    expect(bad).toEqual([]);
  });

  it("대상 낱말을 겹쳐 쓰지 않는다 — 「문서 문서 보관」이 아니라 「문서 보관」", () => {
    expect(actionKo("knowledge.document_archive")).toBe("문서 보관");
    expect(actionKo("mail.test_send")).toBe("메일 시험 발송");
    expect(actionKo("project.create")).toBe("프로젝트 추가");
    expect(actionKo("board.post.update")).toBe("게시글 수정");
    expect(actionKo("mail.cancel")).toBe("메일 발송 취소");
  });
});

describe("잡 유형 — 워커가 받는 유형은 전부 한국어 이름이 있다", () => {
  it("서버의 잡 유형 상수(`…JOB_TYPE… = \"…\"`)를 전부 옮긴다 · 작업 큐 필터 후보와 이름이 같다", async () => {
    const { JOB_TYPE_KO, CURRENT_JOB_TYPES, jobTypeKo } = await import("./format.js");
    const types = literalsOf(/[A-Z_]*JOB_TYPE[A-Z_]*\s*=\s*["']([a-z_]+)["']/g);
    expect(types.size, "서버 소스에서 잡 유형 상수를 못 찾았다").toBeGreaterThan(4);
    const bad = [...types].filter((t) => !JOB_TYPE_KO[t] || hasLatin(jobTypeKo(t)));
    expect(bad).toEqual([]);
    for (const t of types) expect(CURRENT_JOB_TYPES, `${t} 가 작업 큐 유형 필터 후보에 없다`).toContain(t);
  });
});
