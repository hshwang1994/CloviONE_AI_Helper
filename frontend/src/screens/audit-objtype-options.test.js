import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { OBJTYPE_OPTS, OBJTYPE_KO, objTypeKo } from "./registry/shared.js";
import { GOVERNANCE_SCREENS } from "./registry/governance.js";

/* 감사 로그 「대상」 드롭다운은 **백엔드가 실제로 기록하는 값**과 맞는다 (xe-03).
 *
 * 실측으로 무엇이 틀렸나:
 *   * 「문서」라는 이름표가 `document_generation` 에 붙어 있었다. 그 값을 쓰는 코드는
 *     저장소에 한 줄도 없고, 실제 문서 감사 기록은 `object_type="document"` 다 — 「문서」를
 *     고른 관리자는 문서 기록 3건을 눈앞에 두고 「검색 결과가 없습니다」를 봤다.
 *   * 이 설치가 실제로 기록 중인 `board_post`(5건)·`document`(3건)·`llm_config`(1건)·
 *     `notion_task`(6건)는 드롭다운에 아예 없어서, 주소창에 손으로 `?object_type=…` 을
 *     적어야만 볼 수 있었다.
 *
 * 이 파일은 목록을 손으로 베끼지 않는다 — `app/` 의 `record_audit*(object_type="…")` 호출을
 * 직접 읽어 대조한다. 그래야 새 감사 대상이 생겼을 때 여기가 먼저 빨간불이 된다.
 * 관측 이벤트(`record_usage`)는 감사 로그가 아니라 세지 않는다.
 */

const APP_DIR = resolve(__dirname, "../../../app");

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) { walk(full, out); continue; }
    if (full.endsWith(".py")) out.push(full);
  }
  return out;
}

/** `record_audit*` 호출에 실린 object_type 리터럴 전량. `record_usage` 는 뺀다. */
function auditObjectTypes() {
  const found = new Set();
  for (const file of walk(APP_DIR)) {
    const src = readFileSync(file, "utf8");
    const re = /object_type\s*=\s*"([a-z_]+)"/g;
    let m;
    while ((m = re.exec(src)) !== null) {
      const head = src.slice(Math.max(0, m.index - 700), m.index);
      const usage = head.lastIndexOf("record_usage(");
      const audit = Math.max(head.lastIndexOf("record_audit("), head.lastIndexOf("record_audit_from_request("));
      if (audit > usage) found.add(m[1]);
    }
  }
  return found;
}

/* 값이 코드에서 계산되는 것들(`object_type=kind` · 모듈 상수) — 위 정규식이 못 잡는다.
   각각 어디서 오는지 적어 둔다. */
const DYNAMIC = {
  prompts: "app/prompts/router.py — object_type=kind",
  policies: "app/prompts/router.py — object_type=kind",
  department: "app/org/router.py — object_type=audit_type",
  job_title: "app/org/router.py — object_type=audit_type",
  app_setting: "app/settings/service.py — OBJECT_TYPE",
  system_setting: "app/sysops/router.py — OBJECT_TYPE",
  llm_config: "app/llm_console/service.py — OBJECT_TYPE",
  integration: "app/integrations/service.py — OBJECT_TYPE",
};

/* 없어진 기능의 옛 기록 — 새로 쌓이지 않지만 지난 기록이 남아 있어 고를 수는 있어야 한다.
   그래서 「고를 수 있는 값」이 「지금 기록되는 값」보다 넓은 것은 정상이고, 그 사실이
   이름표에 적혀 있어야 한다. */
const RETIRED = ["runner", "workflow", "template", "document_generation", "user_notion_mapping"];

const values = OBJTYPE_OPTS.map((o) => o.value);

describe("감사 로그 대상 필터 — 고를 수 있는 값이 기록되는 값과 같다", () => {
  it("백엔드가 감사 기록으로 남기는 object_type 이 하나도 빠지지 않는다", () => {
    const recorded = auditObjectTypes();
    // 표본이 진짜 있는지 먼저 본다 — 0건이면 정규식이 죽은 것이지 통과가 아니다.
    expect(recorded.size).toBeGreaterThan(30);
    const missing = [...recorded].filter((t) => !values.includes(t)).sort();
    expect(missing).toEqual([]);
  });

  it("코드에서 계산되는 대상(프롬프트·부서·설정 등)도 고를 수 있다", () => {
    const missing = Object.keys(DYNAMIC).filter((t) => !values.includes(t)).sort();
    expect(missing).toEqual([]);
  });

  it("🔴 죽은 값에 살아 있는 이름표를 붙이지 않는다 — 「문서」는 실제 문서 기록을 거른다", () => {
    expect(OBJTYPE_KO.document).toBe("문서");
    expect(OBJTYPE_KO.document_generation).toBe("문서 생성(옛 기능)");
    // 실제로 기록되는 넷이 목록에 있다(실측에서 하나도 못 고르던 값들이다).
    expect(values).toContain("board_post");
    expect(values).toContain("document");
    expect(values).toContain("llm_config");
    expect(values).toContain("notion_task");
  });

  it("없어진 기능은 목록에 남되 이름표가 그 사실을 말한다(필터는 역사도 봐야 한다)", () => {
    for (const t of RETIRED) {
      expect(values).toContain(t);
      expect(OBJTYPE_KO[t]).toContain("(옛 기능)");
    }
  });

  it("같은 값이 두 번 들어 있지 않다", () => {
    expect(new Set(values).size).toBe(values.length);
  });

  it("감사 화면의 드롭다운이 그 한 벌을 그대로 쓴다 — 두 벌로 갈라지면 다시 어긋난다", () => {
    const filter = GOVERNANCE_SCREENS.audit.filters.find((f) => f.key === "object_type");
    expect(filter.options).toBe(OBJTYPE_OPTS);
  });
});

describe("objTypeKo — 표의 「대상」 칸도 같은 낱말을 쓴다 (xe-10)", () => {
  it("공용 사전이 모르는 값도 한국어로 나온다", () => {
    expect(objTypeKo("board_post")).toBe("게시글");
    expect(objTypeKo("storage_provider")).toBe("파일 저장소");
    expect(objTypeKo("llm_config")).toBe("AI 모델 설정");
  });

  it("반례 — 사전 어디에도 없는 값은 원문을 그대로 둔다(정보를 지우지 않는다)", () => {
    expect(objTypeKo("something_new")).toBe("something_new");
    expect(objTypeKo(null)).toBe("-");
    expect(objTypeKo("")).toBe("-");
  });
});
