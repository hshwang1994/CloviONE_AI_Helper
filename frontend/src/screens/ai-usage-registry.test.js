import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";
import { TAB_GROUPS } from "../app/AdminRoutes.jsx";
import { SCREEN_ROLES } from "../app/navConfig.js";
import SORT_KEYS from "../generated/sortKeys.json";

/* AI 사용 통계(계획 A6, D-517 · D-543). 그릇의 두 탭이 AI 런타임이 남긴 호출 기록을 읽는다. 여기서 지키는 것:
 *
 * qa-contract-change: 프롬프트 · 정책 사용 탭을 걷었다(같은 수를 그 목록 화면이 보인다, D-541 · D-542). 「사용 통계」 탭은 레지스트리
 * 목록이 아니라 전용 화면(`screens/ai/AiUsageStats.jsx` — 조건 · 기간 · 보기 기준 → 지표 한 줄 → 나눔 표)이라 그 화면의 「묶음 기본값」
 * 단언은 그 화면의 시험(`screens/ai/ai-usage-stats.test.jsx`)으로 옮겼다. 호출 기록은 서버 검색 · 도구 열 · 은퇴한 기능 이름을 더했다.
 *
 *  1. 탭은 사용 통계 · 호출 기록 둘이고 사용 통계는 전용 화면이 그린다.
 *  2. 호출 기록은 서버 API 를 읽고 정렬 키는 서버가 받는 키와 같다(`sortKeys.json`). 검색은 서버가 한다.
 *  3. 역할은 관리 콘솔 읽기 역할과 같다 - 일반 사용자는 없다.
 *  4. 기능 이름은 서버의 액션 이름과 같다 - 은퇴한 기능은 「(이전 방식)」이 붙어 지난 기록을 볼 때만 쓴다.
 */

const group = () => TAB_GROUPS.find((g) => g.path === "/ai-usage");

describe("AI 사용 통계 화면", () => {
  it("탭은 사용 통계와 호출 기록 둘이고 사용 통계는 전용 화면이다", () => {
    expect(group().tabs.map((t) => [t.key, t.label])).toEqual([
      ["ai-usage-stats", "사용 통계"],
      ["ai-usage-records", "호출 기록"],
    ]);
    expect(typeof group().tabs[0].render).toBe("function");
    expect(REGISTRY["ai-usage-stats"]).toBeUndefined();
  });

  it("호출 기록은 서버 API 를 읽고, 정렬 키는 서버가 받는 키와 같으며, 검색은 서버가 한다", () => {
    const records = REGISTRY["ai-usage-records"];
    expect(records.endpoint).toBe("/api/admin/ai/usage/records");
    expect(records.paginated).toBe(true);
    expect(records.searchable).toBe(true);
    expect([...records.serverSort.keys].sort()).toEqual(SORT_KEYS["ai-usage-records"].keys);
    expect(records.serverSort.default).toEqual(SORT_KEYS["ai-usage-records"].default);
    const tools = records.columns.find((c) => c.key === "tools_label");
    expect(tools.render({ tools_label: "사내 문서 검색, 내 업무(2회)" })).toBe("사내 문서 검색, 내 업무(2회)");
    expect(tools.render({ tools_label: null })).toBe("-");
  });

  it("역할은 관리 콘솔 읽기 역할이고 일반 사용자는 없다", () => {
    for (const key of ["ai-usage-stats", "ai-usage-records"]) {
      expect(SCREEN_ROLES[key]).toEqual(["operator", "admin", "system_admin", "auditor"]);
    }
  });

  it("기능 이름은 서버의 액션 이름과 같다", () => {
    const options = REGISTRY["ai-usage-records"].filters.find((f) => f.key === "action").options;
    // app/ai/actions.py 의 ACTIONS 라벨과 같은 표다. 서버 쪽 이름을 바꾸면 이 표도 함께 바꾼다.
    expect(options.map((o) => [o.value, o.label])).toEqual([
      ["assistant.chat", "AI 도우미"],
      ["workspace.draft", "작업 공간 문서 초안"],
      ["report.weekly_summary", "프로젝트 주간 요약"],
      ["home.narrative", "홈 문장 요약"],
      ["game.quiz", "게임 퀴즈 만들기"],
      ["system.connection_test", "연결 확인"],
      ["chat.answer", "채팅 답변(이전 방식)"],
      ["workspace.ask", "작업 공간 질문(이전 방식)"],
    ]);
  });
});
