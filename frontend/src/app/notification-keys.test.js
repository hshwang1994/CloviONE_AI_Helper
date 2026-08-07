import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { QueryClient } from "@tanstack/react-query";
import {
  NOTI_LIST, NOTI_ROOT, NOTI_SCREEN, NOTI_UNREAD, invalidateNotifications, notiListKey,
} from "./notification-keys.js";

/* 알림 캐시가 **한 뿌리 아래** 있다 (PF9).
 *
 * 예전에는 세 네임스페이스(`noti-unread` · `noti-list` · `notifications`)로 흩어져 있었다.
 * 접두어가 달라 한 번의 무효화로 함께 갱신할 수 없었고, 그래서 읽음 처리를 하는 자리마다
 * 세 줄을 손으로 적었다 — 한 줄이 빠지면 "목록에서 읽었는데 벨 숫자가 그대로"가 됐고,
 * 반대로 필요 없는 것까지 무효화해 알림과 무관한 재조회를 만든 자리도 있었다.
 *
 * 아래 첫 묶음은 **실제 QueryClient 로** 그 성질을 확인한다(문자열 비교가 아니라 동작).
 * 두 번째 묶음은 새 네임스페이스가 다시 생기지 않는지 소스를 훑는다 — 규칙은 코드로
 * 강제하지 않으면 다음 화면에서 반드시 깨진다.
 */

const APP = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(APP, "..");

describe("한 번의 무효화가 알림 캐시 전부를 덮는다", () => {
  it("벨·팝오버 목록·전체 화면이 함께 무효화된다", () => {
    const qc = new QueryClient();
    // 값이 실제로 들어 있어야 '무효화됐다'가 뜻을 갖는다.
    qc.setQueryData(NOTI_UNREAD, { unread: 2 });
    qc.setQueryData(notiListKey("unread"), { items: [] });
    qc.setQueryData([...NOTI_SCREEN, "", 1, "{}"], { items: [] });
    // 알림과 무관한 캐시 — 이것까지 무효화되면 '겹침'이다.
    qc.setQueryData(["tickets"], { items: [] });

    for (const key of [NOTI_UNREAD, notiListKey("unread"), [...NOTI_SCREEN, "", 1, "{}"], ["tickets"]]) {
      expect(qc.getQueryState(key).isInvalidated).toBe(false);
    }

    invalidateNotifications(qc);

    expect(qc.getQueryState(NOTI_UNREAD).isInvalidated, "벨 배지").toBe(true);
    expect(qc.getQueryState(notiListKey("unread")).isInvalidated, "팝오버 목록").toBe(true);
    expect(qc.getQueryState([...NOTI_SCREEN, "", 1, "{}"]).isInvalidated, "전체 알림 화면").toBe(true);
    expect(qc.getQueryState(["tickets"]).isInvalidated, "알림과 무관한 캐시").toBe(false);
  });

  it("세 키가 서로 다르면서 같은 뿌리를 쓴다", () => {
    const all = [NOTI_UNREAD, NOTI_LIST, NOTI_SCREEN];
    // 같은 뿌리
    for (const k of all) expect(k[0]).toBe(NOTI_ROOT[0]);
    // 서로 다름 — 하나라도 같으면 캐시가 뒤섞인다
    expect(new Set(all.map((k) => JSON.stringify(k))).size).toBe(3);
  });
});

describe("네 번째 네임스페이스가 생기지 않는다", () => {
  function sourceFiles(dir) {
    const out = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) out.push(...sourceFiles(full));
      else if (/\.(js|jsx)$/.test(entry.name) && !/\.test\./.test(entry.name)) out.push(full);
    }
    return out;
  }

  const files = sourceFiles(SRC).filter((f) => !f.endsWith("notification-keys.js"));

  it("검사할 소스를 실제로 찾는다", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it("옛 키를 손으로 적는 곳이 없다", () => {
    // 문자열 리터럴로 된 캐시 키만 본다. CSS 클래스(`noti-unread-dot`)는 캐시가 아니다.
    const bad = [];
    for (const f of files) {
      const text = fs.readFileSync(f, "utf8");
      for (const re of [/queryKey:\s*\[\s*["']noti-(unread|list)["']/, /queryKey:\s*\[\s*["']notifications["']/]) {
        if (re.test(text)) bad.push(path.relative(SRC, f));
      }
    }
    expect(
      [...new Set(bad)],
      "알림 캐시 키는 app/notification-keys.js 에서 받아 써라 — 손으로 적으면 뿌리가 갈라진다",
    ).toEqual([]);
  });
});
