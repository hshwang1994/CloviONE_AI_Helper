import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

import { SETTING_LABELS, OBJECT_SCHEMA_HELP, summarizeSetting } from "./Settings.jsx";

/* 설정 화면의 손으로 유지하는 맵이 `registry.py` 와 어긋나지 않는다 (N6).
 *
 * `backup_schedule` 이 **세 맵에 전부 빠져 있어서** 관리자가 raw 영문 키를 보고 raw JSON 으로
 * cron·타임존을 편집했다. 백업은 **복원이 필요해진 날에야** 안 도는 것을 알게 되는 부류라
 * 이 화면이 사실을 말하지 못하면 대가가 크다.
 *
 * 더 나쁜 것: `Settings.jsx` 가 **이 드리프트를 예견해 경고를 심어 놨는데**
 * `import.meta.env.DEV` 게이트라 운영에서 침묵했다. 예견해 놓고 못 잡은 셈이다.
 * 그래서 안전망을 개발 콘솔이 아니라 **테스트**로 옮긴다 — 새 설정 키를 추가하면 여기서 깨진다.
 */

function registryKeys() {
  const file = path.resolve(__dirname, "../../../app/settings/registry.py");
  const src = fs.readFileSync(file, "utf-8");
  return [...src.matchAll(/SettingSpec\(\s*"([a-z0-9_]+)"/g)].map((m) => m[1]);
}

/* 유지보수 두 키는 전용 화면(/maintenance)에서만 다루므로 설정 표에서 숨긴다 —
 * 다만 라벨은 있어야 한다(감사 로그·딥링크에서 이름으로 나온다). */
const OBJECT_TYPES = new Set(["ui_branding", "password_policy", "session_policy",
  "allowed_email_domains", "backup_schedule", "retry_policy"]);

describe("설정 라벨 드리프트", () => {
  it("registry.py 의 모든 키에 한국어 라벨이 있다", () => {
    const missing = registryKeys().filter((k) => !SETTING_LABELS[k]);
    expect(missing, `라벨 없는 키는 표에 원시 영문으로 새어 나간다: ${missing}`).toEqual([]);
  });

  it("구조가 있는 object 설정에는 JSON 예시 안내가 있다", () => {
    const keys = registryKeys().filter((k) => OBJECT_TYPES.has(k));
    expect(keys.length, "object 설정을 하나도 못 찾았다 — 정규식이 낡았다").toBeGreaterThan(0);
    const missing = keys.filter((k) => !OBJECT_SCHEMA_HELP[k]);
    expect(missing, `비개발자 관리자가 raw JSON 을 추측하게 된다: ${missing}`).toEqual([]);
  });

  it("백업 일정을 사람 말로 요약한다", () => {
    expect(
      summarizeSetting("backup_schedule",
        { enabled: true, cron: "0 3 * * *", timezone: "Asia/Seoul", keep: 14 }),
    ).toBe("켜짐, 0 3 * * * (Asia/Seoul), 14개 보관");
    expect(summarizeSetting("backup_schedule", { enabled: false })).toBe("꺼짐");
  });
});
