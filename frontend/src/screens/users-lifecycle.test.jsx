import { describe, it, expect } from "vitest";
import { lifecycleBadge } from "./Users.jsx";

/* 계정 수명주기 배지 (X14).
 *
 * ## 왜 이 검사가 있나
 *
 * 보관(`archive_user`)은 **`active` 를 건드리지 않는다** — 복구했을 때 보관 전 상태로
 * 정확히 돌아가야 하기 때문이다(app/users/service.py). 그래서 보관된 계정은 대부분
 * `active=true` 인 채로 목록에 실려 오고, 예전 화면은 그 값만 보고 **초록 '사용 중'**
 * 배지를 그렸다. 로그인은 막혀 있는데(app/core/deps.py) 화면은 정상 계정이라고 말한 것이다.
 *
 * 이 표본이 핵심이다: `{ active: true, archived_at: "…" }`. 여기서 '사용 중' 이 나오면
 * 관리자는 목록을 훑어 보관된 계정을 찾을 수 없다.
 */

const ACTIVE = { active: true, archived_at: null };
const DISABLED = { active: false, archived_at: null };
// 보관은 active 를 그대로 둔다 — 이게 예전 화면이 틀린 답을 내던 그 표본이다.
const ARCHIVED = { active: true, archived_at: "2026-08-01T00:00:00" };
const ARCHIVED_WAS_DISABLED = { active: false, archived_at: "2026-08-01T00:00:00" };

describe("lifecycleBadge", () => {
  it("로그인이 되는 계정만 '사용 중'이다", () => {
    expect(lifecycleBadge(ACTIVE)).toEqual({ label: "사용 중", kind: "ok" });
  });

  it("보관된 계정을 '사용 중'으로 그리지 않는다 — active 가 참이어도", () => {
    expect(lifecycleBadge(ARCHIVED).label).toBe("보관됨");
    expect(lifecycleBadge(ARCHIVED).label).not.toBe("사용 중");
    // 보관 전에 비활성이었든 아니든 목록에서는 '보관됨' 하나로 읽힌다.
    expect(lifecycleBadge(ARCHIVED_WAS_DISABLED).label).toBe("보관됨");
  });

  it("비활성과 보관은 서로 다른 상태다 — 되돌리는 문이 다르다", () => {
    const disabled = lifecycleBadge(DISABLED);
    const archived = lifecycleBadge(ARCHIVED);
    expect(disabled.label).toBe("비활성");
    expect(archived.label).toBe("보관됨");
    // 라벨만 다르고 톤이 같으면 훑어볼 때 둘이 같은 것으로 읽힌다.
    expect(disabled.kind).not.toBe(archived.kind);
  });

  it("세 상태의 톤이 서로 겹치지 않는다", () => {
    const kinds = [ACTIVE, DISABLED, ARCHIVED].map((r) => lifecycleBadge(r).kind);
    expect(new Set(kinds).size).toBe(3);
  });
});
