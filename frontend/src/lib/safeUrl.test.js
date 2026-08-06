/* 외부 링크 스킴 검사 (SEC1).
 *
 * 이 파일이 지키는 것: 공지 배너의 `link_url` 로 `javascript:` 를 넣어도 실행 링크가
 * 만들어지지 않는다. 배너는 audience=all 이면 **전 사용자에게** 뜨고, system_admin 이
 * 한 번 누르면 그 세션에서 실행된다 — admin → system_admin 권한 상승 경로였다.
 * (운영 실측 2026-08-05: 사용자 15명 중 admin 이 12명이라 노출면이 좁지 않다.)
 *
 * react-dom 18.3.1 의 `sanitizeURL` 은 개발 빌드 전용이라 운영에서는 아무 일도 안 하고,
 * CSP 에 `'unsafe-inline'` 이 들어가면서 `javascript:` URI 가 실행 가능해졌다.
 * 즉 화면에서 막는 것은 이 함수뿐이다(진짜 경계는 서버 app/core/safe_url.py). */

import { describe, expect, it } from "vitest";
import { safeExternal } from "./safeUrl.js";

// 제어문자를 소스에 리터럴로 넣으면 파일이 바이너리로 취급된다. 코드로 만든다.
const ctrl = (code) => String.fromCharCode(code);

describe("safeExternal", () => {
  it("http(s) 는 그대로 통과시킨다", () => {
    expect(safeExternal("https://notion.so/a")).toBe("https://notion.so/a");
    expect(safeExternal("http://intra/a")).toBe("http://intra/a");
    expect(safeExternal("HTTPS://UPPER/a")).toBe("HTTPS://UPPER/a");
  });

  it("javascript: 를 막는다 — 대소문자를 섞어도", () => {
    expect(safeExternal("javascript:alert(1)")).toBeNull();
    expect(safeExternal("JaVaScRiPt:alert(1)")).toBeNull();
  });

  it("선행 공백·제어문자로 우회할 수 없다", () => {
    // 브라우저는 이런 값을 관대하게 해석한다. 검사 전에 지워야 한다.
    expect(safeExternal("  javascript:alert(1)")).toBeNull();
    expect(safeExternal(ctrl(1) + "javascript:alert(1)")).toBeNull();
    expect(safeExternal(ctrl(9) + "javascript:alert(1)")).toBeNull();
    expect(safeExternal(ctrl(10) + "javascript:alert(1)")).toBeNull();
  });

  it("다른 실행 가능 스킴도 막는다", () => {
    expect(safeExternal("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(safeExternal("vbscript:msgbox(1)")).toBeNull();
    expect(safeExternal("file:///etc/passwd")).toBeNull();
  });

  it("상대경로·빈값·비문자열은 링크로 만들지 않는다", () => {
    expect(safeExternal("/relative")).toBeNull();
    expect(safeExternal("")).toBeNull();
    expect(safeExternal(null)).toBeNull();
    expect(safeExternal(undefined)).toBeNull();
    expect(safeExternal(123)).toBeNull();
  });

  it("앞뒤 공백은 다듬어서 돌려준다", () => {
    expect(safeExternal("  https://x/a  ")).toBe("https://x/a");
  });
});
