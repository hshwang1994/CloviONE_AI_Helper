import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/* 로그인 뒤 **원래 가려던 곳**으로 간다 — 조각(fragment)까지.
 *
 * ## 무엇이 깨져 있었나
 *
 * 사람이 주소창의 `https://host/#/tickets/T-123` 을 복사해 카톡·메일로 보낸다. 받는 사람이
 * 로그인까지 마쳤는데 그 티켓이 아니라 자기 홈(`/me`)에 착지했다.
 *
 * 이 앱은 해시 라우터라 「어느 티켓·어느 문서」가 통째로 **조각**에 산다. 조각은 서버로
 * 전송되지 않으므로 `app/main.py` 의 `PageAuthRequired` 핸들러는 그것을 볼 수 없고 `next` 는
 * 언제나 `/` 다. 그런데 **브라우저는 그 조각을 버리지 않는다** — `Location` 에 조각이 없는
 * 3xx 를 따라갈 때 원래 조각을 물려준다(RFC 7231 §7.1.2). 즉 로그인 화면의 실제 주소는
 * `…/login?next=%2F#/tickets/T-123` 이고 값은 이미 이 페이지 손에 있었다.
 *
 * 그것을 버린 것은 마지막 한 줄이다: `window.location.href = "/"` 는 조각 없는 주소를
 * **명시적으로 대입**하므로 물려받은 조각이 그 순간 사라진다.
 *
 * ## 왜 이렇게 재는가
 *
 * jsdom 은 실제 문서 이동을 안 한다. `href = "/"` 든 `href = "/#/tickets/T-123"` 이든
 * `window.location` 은 **둘 다 안 바뀐다**(전자는 "not implemented", 후자는 경로가 달라
 * 역시 이동) — 그래서 `window.location` 을 관찰하면 고친 코드와 안 고친 코드가 똑같아 보인다.
 * 그 시험은 헛것이다.
 *
 * 그래서 `login.js` 에 **가짜 `window`** 를 주입해 그것이 실제로 무엇을 대입하는지 받아
 * 적는다. `document`·`fetch` 는 맨 전역이라 진짜를 그대로 쓴다 — 바꾸는 것은 `location` 하나다.
 */

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const LOGIN_JS = readFileSync(path.join(REPO, "app/static/js/login.js"), "utf8");

const FIXTURE = `
  <form id="login-form" action="/login" method="post" novalidate>
    <input id="email" name="email" type="email" />
    <input id="password" name="password" type="password" />
    <div id="login-error" role="alert"></div>
    <button id="login-submit" type="submit"><span id="login-submit-label">로그인</span></button>
  </form>
  <input type="hidden" id="login-next" name="next" value="" />
`;

/** login.js 가 대입한 주소를 받아 적는 가짜 창. 나머지는 전부 진짜 창으로 넘긴다. */
function bootWithHash(hash) {
  document.body.innerHTML = FIXTURE;
  const assigned = [];
  const location = {
    pathname: "/login",
    search: "?next=%2F",
    hash,
    get href() { return "http://localhost/login?next=%2F" + hash; },
    set href(v) { assigned.push(v); },
  };
  const fake = new Proxy(window, {
    get(target, prop) {
      if (prop === "location") return location;
      const value = Reflect.get(target, prop);
      return typeof value === "function" ? value.bind(target) : value;
    },
    set(target, prop, value) {
      if (prop === "location") { location.href = value; return true; }
      return Reflect.set(target, prop, value);
    },
  });
  // eslint-disable-next-line no-new-func
  new Function("window", LOGIN_JS)(fake);
  return { assigned };
}

function respondWith(payload) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
  globalThis.fetch = fetchMock;
  window.fetch = fetchMock;
}

const tick = (ms) => new Promise((r) => setTimeout(r, ms));

async function submitAndSettle() {
  document.getElementById("email").value = "hong@example.com";
  document.getElementById("password").value = "pw123456";
  document.getElementById("login-form")
    .dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  // 성공 경로는 연출을 최대 1.2초 기다린 뒤에 이동한다(CELEBRATE_CAP_MS).
  await tick(1400);
}

beforeEach(() => { window.sessionStorage.clear(); });
afterEach(() => { document.body.innerHTML = ""; delete globalThis.fetch; });

describe("로그인 뒤 딥링크 복귀", () => {
  it("🔴 서버가 next 로 「/」만 줘도 주소창의 조각을 이어 붙인다", async () => {
    const { assigned } = bootWithHash("#/tickets/T-123");
    respondWith({ ok: true, next: "/", must_change_password: false });

    await submitAndSettle();

    expect(assigned).toEqual(["/#/tickets/T-123"]);
  });

  it("서버가 준 next 에 이미 조각이 있으면 그쪽이 이긴다 — 두 번 붙이지 않는다", async () => {
    // SPA 안에서 세션이 끊긴 경로다. sessionRedirect.js 가 경로+질의+조각을 통째로 싣는다.
    const { assigned } = bootWithHash("#/tickets/T-999");
    respondWith({ ok: true, next: "/#/knowledge/abc", must_change_password: false });

    await submitAndSettle();

    expect(assigned).toEqual(["/#/knowledge/abc"]);
  });

  /* 반례 셋. 이 갈래가 없으면 「무조건 이어 붙인다」로 고쳐도 위 시험이 초록이다. */

  it("반례 — 비밀번호 강제 변경에는 안 붙인다. 거긴 SPA 가 아니다", async () => {
    const { assigned } = bootWithHash("#/tickets/T-123");
    respondWith({ ok: true, next: null, must_change_password: true });

    await submitAndSettle();

    expect(assigned).toEqual(["/change-password"]);
  });

  it("반례 — 조각이 없으면 아무것도 안 붙는다", async () => {
    const { assigned } = bootWithHash("");
    respondWith({ ok: true, next: "/", must_change_password: false });

    await submitAndSettle();

    expect(assigned).toEqual(["/"]);
  });

  it("반례 — 「#」·「#/」 는 갈 곳이 아니다. SPA 가 기본 화면을 스스로 정한다", async () => {
    const bare = bootWithHash("#");
    respondWith({ ok: true, next: "/", must_change_password: false });
    await submitAndSettle();
    expect(bare.assigned).toEqual(["/"]);

    const root = bootWithHash("#/");
    respondWith({ ok: true, next: "/", must_change_password: false });
    await submitAndSettle();
    expect(root.assigned).toEqual(["/"]);
  });
});
