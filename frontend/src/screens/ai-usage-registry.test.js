import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";
import { TAB_GROUPS } from "../app/AdminRoutes.jsx";
import { SCREEN_ROLES } from "../app/navConfig.js";
import SORT_KEYS from "../generated/sortKeys.json";

/* AI 사용 통계(계획 3.11, D-517). 예전 「AI 사용 통계」는 스케줄이 이름을 참조하는가를 보여 주는 설정 개요였고,
 * 실제 호출은 어디에도 없었다. 이제 첫 두 탭이 AI 런타임이 남긴 호출 기록을 읽는다. 여기서 지키는 것:
 *
 *  1. 탭 순서는 실제 호출(사용 통계, 호출 기록)이 먼저이고 설정 개요(프롬프트, 정책)가 뒤다.
 *  2. 두 화면은 서버 API 를 읽고, 호출 기록의 정렬 키는 서버가 받는 키와 같다(`sortKeys.json`).
 *  3. 역할은 관리 콘솔 읽기 역할과 같다 - 일반 사용자는 없다.
 *  4. 기능 이름은 서버의 액션 이름과 같다 - 화면이 이름을 따로 지어 두 이름이 갈리지 않게 한다.
 */

const group = () => TAB_GROUPS.find((g) => g.path === "/ai-usage");

describe("AI 사용 통계 화면", () => {
  it("실제 호출 탭이 먼저 온다", () => {
    expect(group().tabs.map((t) => [t.key, t.label])).toEqual([
      ["ai-usage-stats", "사용 통계"],
      ["ai-usage-records", "호출 기록"],
      ["prompt-usage", "프롬프트"],
      ["policy-usage", "정책"],
    ]);
  });

  it("두 탭은 호출 기록 API 를 읽고, 정렬 키는 서버가 받는 키와 같다", () => {
    expect(REGISTRY["ai-usage-stats"].endpoint).toBe("/api/admin/ai/usage/stats");
    const records = REGISTRY["ai-usage-records"];
    expect(records.endpoint).toBe("/api/admin/ai/usage/records");
    expect(records.paginated).toBe(true);
    expect([...records.serverSort.keys].sort()).toEqual(SORT_KEYS["ai-usage-records"].keys);
    expect(records.serverSort.default).toEqual(SORT_KEYS["ai-usage-records"].default);
  });

  it("묶음의 기본값은 기능이고, 묶음 결과에는 저장된 뷰를 두지 않는다", () => {
    const stats = REGISTRY["ai-usage-stats"];
    expect(stats.filters.find((f) => f.key === "group_by").value).toBe("action");
    expect(stats.smallSet).toBe(true);
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
      ["chat.answer", "채팅 답변"],
      ["workspace.ask", "작업 공간 질문"],
      ["workspace.draft", "작업 공간 문서 초안"],
      ["report.weekly_summary", "프로젝트 주간 요약"],
      ["home.narrative", "홈 문장 요약"],
      ["game.quiz", "게임 퀴즈 만들기"],
      ["system.connection_test", "연결 확인"],
    ]);
  });
});
