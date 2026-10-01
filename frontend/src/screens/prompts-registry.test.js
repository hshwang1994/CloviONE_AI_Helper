import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { REGISTRY } from "./registry.js";

/* 프롬프트 화면 — AI 기능마다 한 줄 (계획 A4, D-541).
 *
 * qa-contract-change: 프롬프트 화면이 「행(버전) 목록 + 기본 제공 가상 행」에서 「기능마다 한 줄 + 서랍」으로 바뀌었다(D-541). 옛 시험이
 * 지키던 「기본 제공 행에는 복제해서 수정만」 · 「사용 중 · 대체됨 배지」 · 「사용처 고르기」 · 「사용 통계에서 건너가기」는 그 화면과 함께
 * 사라졌다 — 기능 행에는 고를 사용처가 없고, 사용 통계 탭은 이 목록 자체가 됐다. 같은 성질(고칠 수 없는 것은 고칠 수 없다, 발행은
 * 초안에서만, 상태 낱말이 사실과 맞다)은 새 모양으로 다시 잰다.
 *
 * 지키는 것:
 *  1. 목록은 기능 목록 API 를 읽고, 열은 기능 · 지금 쓰는 지시문 · 기능 상태 · 초안 · 최근 30일 요청 · 실패율 · 마지막 사용이다.
 *  2. 행 동작: 초안이 있을 때만 「초안 발행」 · 「초안 버리기」, 관리자 작성 지시문을 쓸 때만 「기본 제공으로 되돌리기」, 「버전 기록」은
 *     언제나. 위험한 둘은 확인을 받는다.
 *  3. 「수정」은 그 기능의 초안을 고친다(`PATCH /features/{기능}`) — 칸은 지시문 하나다.
 *  4. 기능 상태 배지는 서버의 낱말(켜짐 · 꺼짐 · AI 미연결)을 그대로 보인다. 버전 기록의 상태 어휘는 초안 · 적용 중 · 보관이다.
 */

const cfg = REGISTRY.prompts;
const labelsFor = (row) => cfg.actions.filter((a) => !a.when || a.when(row, undefined)).map((a) => a.label);
const render = (key, row) => renderToStaticMarkup(cfg.columns.find((c) => c.key === key).render(row));

const builtin = {
  id: "draft", slot: "draft", label: "문서 초안", current: { source: "builtin", label: "기본 제공" }, draft: null,
  feature_state: "on", feature_state_label: "켜짐",
};
const withDraft = { ...builtin, draft: { id: "p-2", version: 2, label: "v2 초안", content: "고친 지시문" } };
const admin = { ...builtin, current: { source: "admin", label: "관리자 작성 v1" } };

describe("프롬프트 화면 — 기능마다 한 줄", () => {
  it("기능 목록 API 를 읽고 열은 기능 단위다", () => {
    expect(cfg.endpoint).toBe("/api/admin/prompts/features");
    expect(cfg.columns.map((c) => c.key)).toEqual(
      ["label", "current", "feature_state", "draft", "calls_30d", "failure_rate", "last_used_at"],
    );
    expect(render("current", admin)).toBe("관리자 작성 v1");
    expect(render("draft", withDraft)).toBe("v2 초안");
    expect(render("failure_rate", { failure_rate: 2 })).toBe("2%");
    expect(render("failure_rate", { failure_rate: null })).toBe("-");
  });

  it("발행 · 버리기는 초안이 있을 때만, 되돌리기는 관리자 작성일 때만 선다", () => {
    expect(labelsFor(builtin)).toEqual(["버전 기록"]);
    expect(labelsFor(withDraft)).toEqual(["초안 발행", "초안 버리기", "버전 기록"]);
    expect(labelsFor(admin)).toEqual(["기본 제공으로 되돌리기", "버전 기록"]);
    const byLabel = Object.fromEntries(cfg.actions.map((a) => [a.label, a]));
    expect(byLabel["초안 발행"].path(withDraft)).toBe("/api/admin/prompts/features/draft/publish");
    expect(byLabel["초안 버리기"].path(withDraft)).toBe("/api/admin/prompts/features/draft/discard");
    expect(byLabel["기본 제공으로 되돌리기"].path(admin)).toBe("/api/admin/prompts/features/draft/reset");
    for (const label of ["초안 발행", "초안 버리기", "기본 제공으로 되돌리기"]) {
      expect(byLabel[label].confirm).toBeTruthy();
      expect(byLabel[label].requiresGlobalScope).toBe(true);
    }
    expect(byLabel["초안 버리기"].variant).toBe("danger");
  });

  it("수정은 그 기능의 초안을 고치고 칸은 지시문 하나다", () => {
    expect(cfg.editMethod).toBe("PATCH");
    expect(cfg.editWhen(builtin)).toBe(true);
    expect(cfg.edit.fields.map((f) => f.name)).toEqual(["content"]);
    expect(cfg.edit.requiresGlobalScope).toBe(true);
  });

  it("기능 상태는 서버의 낱말이고 버전 기록은 그 기능의 관리자 작성 버전만 모은다", () => {
    expect(render("feature_state", { feature_state: "off", feature_state_label: "꺼짐" })).toContain("꺼짐");
    expect(render("feature_state", { feature_state: "ai_unavailable", feature_state_label: "AI 미연결" })).toContain("AI 미연결");
    const versions = cfg.actions.find((a) => a.label === "버전 기록").subList;
    expect(versions.endpoint({ slot: "draft" }, { page: 2 })).toBe("/api/admin/prompts?slot=draft&source=admin&page=2");
    const statusCol = versions.columns.find((c) => c.key === "status");
    expect(["draft", "published", "archived"].map((s) => statusCol.render({ status: s }))).toEqual(["초안", "적용 중", "보관"]);
  });

  it("옛 사용 통계 탭은 없다 — 같은 수를 이 목록이 보인다", () => {
    expect(REGISTRY["prompt-usage"]).toBeUndefined();
    expect(REGISTRY["policy-usage"]).toBeUndefined();
    expect(REGISTRY["ai-usage-stats"]).toBeUndefined();
  });
});
