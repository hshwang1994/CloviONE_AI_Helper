/* W5 — Entity 를 **손으로 옮겨 적게** 하는 자리가 남아 있는가.
 *
 * ## 무엇이 문제였나
 *
 * 이 제품은 여러 화면에서 「‘사용자’ 화면에서 ID를 복사해 붙여 넣으세요」라고 적어 두고
 * `type: "text"` 상자를 줬다. 사람이 UUID 를 화면 사이로 나르는 것은 기능이 아니라 결함이다
 * (R-5 · 지시 0-2.17 · PLAN C2 «Entity Selector»). 실측에서 raw text entity 필드 12 선언 ·
 * 필터 9 선언이 나왔고, 그중 어느 것도 `plain_dropdown_for_entity` 에 **보이지 않았다** —
 * 그 프로브가 `select`/`combobox` 만 순회했기 때문이다(F-W5D-131).
 *
 * ## 왜 이 시험인가
 *
 * 브라우저 프로브는 **그려진 것**만 본다. 모달 안, 권한이 없어 안 그려지는 폼, 조건부 필드
 * (`showIf`)는 어느 실행에서도 렌더되지 않을 수 있다. 선언을 읽는 이 시험은 그 사각을 덮는다
 * — 둘은 경쟁이 아니라 짝이다.
 *
 * ## 규칙
 *
 * 라벨이 Entity 어휘에 걸리는 필드·필터는 `type: "text"` 일 수 없다. 예외는 **여기 이름으로**
 * 적는다 — 예외가 코드 주석에만 있으면 다음 사람이 그 줄을 복사해 새 결함을 만든다.
 */

import { describe, it, expect } from "vitest";
import { REGISTRY } from "./registry.js";

/* 기수가 무한히 자라는 대상. `scripts/ui_qa/assertions.py::ENTITY_TERMS` 와 같은 어휘다 —
   한쪽만 늘리면 프로브와 시험이 서로 다른 제품을 검사하게 된다. */
const ENTITY_TERMS = [
  "프로젝트", "담당자", "사용자", "부서", "조직", "직책", "티켓", "문서", "게시글",
  "러너", "워크플로", "프롬프트", "정책", "템플릿", "일정", "연동", "채팅방",
  "승인자", "요청자", "작성자", "대상자", "후임", "소속", "행위자", "참여자", "멤버",
];
/* 어휘에 걸려도 그 대상 자체가 아니라 **그 대상의 속성**을 가리키는 자리다.
   두 갈래가 있다.
     ① 값 집합이 닫힌 분류축 — 「문서 **종류**」(고정 8개)는 문서를 고르는 자리가 아니다.
     ② 지금 만들고 있는 것의 **속성** — 「부서 **이름**」·「러너 **버전**」은 기존 부서/러너를
        가리키는 참조가 아니라 새로 적는 값이다. 여기에 선택기를 놓으라고 하면 «부서를 만들려면
        먼저 부서를 골라야 한다» 는 말이 된다. */
const ATTRIBUTE_LABEL = /(종류|유형|분류|모드|등급|상태|결과|수준|단계|이름|버전|제목|설명|사유|주소|경로)/;

/* 자유 텍스트로 남는 것이 옳은 자리도 있다 — 전역 후보 목록이 **존재하지 않는** 값이다
   (외부 시스템 식별자, 모든 object_type 을 가로지르는 대상 ID, 콤마로 여러 값을 받는 딥링크).
   그때는 선언이 `freeTextReason` 으로 **왜 그런지** 말한다.

   이유를 이 시험 파일의 예외 표에 두지 않는 이유: 코드를 읽는 사람은 시험을 안 읽는다.
   선언 옆에 두면 그 줄을 복사하는 사람이 이유까지 함께 읽고, 같은 값이 DOM 에
   `data-entity-select="closed"` 로 나가 브라우저 프로브도 같은 판단을 공유한다 —
   **끄는 것이 아니라 이유를 남기는 것**이다. */

function entityTermOf(label) {
  const s = String(label || "");
  if (!s || ATTRIBUTE_LABEL.test(s)) return null;
  return ENTITY_TERMS.find((t) => s.indexOf(t) >= 0) || null;
}

/* 한 화면 설정 안의 **모든** 필드 선언을 모은다 — 필터 · create · edit · 행 액션 · 헤더 액션.
   한 갈래만 훑으면 그 갈래 밖에서 결함이 자란다(실측: 헤더 액션의 「대상 사용자 ID」). */
function declaredFields(cfg) {
  const out = [];
  /* 일부 폼은 `fields` 가 역할에 따라 달라지는 함수다(DataScreen::resolveFields). 가장 넓게
     보는 역할로 펼친다 — 좁은 역할만 보면 관리자 전용 필드가 검사에서 사라진다. */
  const arrOf = (v) => {
    if (Array.isArray(v)) return v;
    if (typeof v === "function") { try { return v("system_admin", null) || []; } catch { return []; } }
    return [];
  };
  const push = (arr, where) => arrOf(arr).forEach((f) => f && out.push({ ...f, where }));
  push(cfg.filters, "filter");
  push(cfg.create && cfg.create.fields, "create");
  push(cfg.edit && cfg.edit.fields, "edit");
  (cfg.actions || []).forEach((a) => push(a.fields, "action:" + a.label));
  (cfg.headerActions || []).forEach((a) => push(a.fields, "headerAction:" + a.label));
  return out;
}

describe("Entity 는 고르는 것이지 옮겨 적는 것이 아니다 (W5 · R-5)", () => {
  const offenders = [];
  for (const [key, cfg] of Object.entries(REGISTRY)) {
    if (!cfg || typeof cfg !== "object") continue;
    for (const f of declaredFields(cfg)) {
      if (f.type !== "text") continue;
      const label = f.label != null ? f.label : f.name;
      const term = entityTermOf(label);
      if (!term) continue;
      if (f.freeTextReason) continue;
      offenders.push(`${key}.${f.where}.${f.name || f.key} — 라벨 「${label}」 (어휘: ${term})`);
    }
  }

  it("🔴 Entity 어휘의 필드·필터에 raw text 상자가 남아 있지 않다", () => {
    expect(offenders).toEqual([]);
  });

  it("Entity 로 선언한 필드는 후보 목록을 실제로 갖는다 — 빈 선택기는 text 보다 나쁘다", () => {
    const dangling = [];
    for (const [key, cfg] of Object.entries(REGISTRY)) {
      if (!cfg || typeof cfg !== "object") continue;
      const declared = new Set((cfg.refLists || []).map((r) => r.key));
      for (const f of declaredFields(cfg)) {
        if (!f.optionsFromRefList) continue;
        if (!declared.has(f.optionsFromRefList)) {
          dangling.push(`${key}.${f.where}.${f.name || f.key} → refList 「${f.optionsFromRefList}」 미선언`);
        }
      }
    }
    expect(dangling).toEqual([]);
  });

  it("자유 텍스트 예외는 **왜 그런지**를 문장으로 말한다 — 빈 표시는 예외가 아니다", () => {
    const thin = [];
    for (const [key, cfg] of Object.entries(REGISTRY)) {
      if (!cfg || typeof cfg !== "object") continue;
      for (const f of declaredFields(cfg)) {
        if (!f.freeTextReason) continue;
        if (typeof f.freeTextReason !== "string" || f.freeTextReason.trim().length < 20) {
          thin.push(`${key}.${f.where}.${f.name || f.key} — 이유가 너무 짧다`);
        }
      }
    }
    expect(thin).toEqual([]);
  });

  it("자유 텍스트 예외는 자유 텍스트 자리에만 붙는다 — 선택기에 붙은 이유는 아무것도 안 지킨다", () => {
    /* 어휘에 «걸리는 자리에만» 을 요구하지 않는 이유: 「실행 건 ID」·「대상 ID」·「발행 위치:
       DB ID」처럼 어휘에는 안 걸리지만 ID 를 손으로 적는 자리가 실재한다. 그 자리에 이유를
       적어 두는 것은 낭비가 아니라 다음 사람에게 남기는 답이다("왜 여기만 선택기가 아닌가").
       막아야 할 것은 **선택기가 된 필드에 예외가 남는 것**이다 — 그러면 표시는 거짓이 된다. */
    const misplaced = [];
    for (const [key, cfg] of Object.entries(REGISTRY)) {
      if (!cfg || typeof cfg !== "object") continue;
      for (const f of declaredFields(cfg)) {
        if (!f.freeTextReason) continue;
        if (f.type !== "text") {
          misplaced.push(`${key}.${f.where}.${f.name || f.key} — type=${f.type} 인데 자유 텍스트 예외가 남아 있다`);
        }
      }
    }
    expect(misplaced).toEqual([]);
  });
});
