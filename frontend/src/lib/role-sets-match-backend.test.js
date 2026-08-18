import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  CONSOLE_OPS_ROLES,
  CONSOLE_READ_ROLES,
  CONSOLE_WRITE_ROLES,
  SENSITIVE_READ_ROLES,
  SYSTEM_ADMIN_ONLY,
} from "./roles.js";

/* 지시 21 · 55 — 화면의 역할 묶음이 **서버의 것과 같은가**.
 *
 * 프런트의 역할 목록은 권한이 아니라 표시 판단이다. 그래도 서버와 갈라지면 두 가지가
 * 동시에 나쁘다: 서버가 허용하는데 화면에 버튼이 없으면 기능이 사라진 것처럼 보이고,
 * 서버가 막는데 버튼이 있으면 눌러서 403 을 받는 막다른 길이 생긴다.
 *
 * 그래서 값 자체를 `app/core/authz.py` 에서 읽어 대조한다. 여기 상수를 손으로 옮겨 적으면
 * 그 사본이 또 하나 늘 뿐이고, 서버가 바뀐 날 이 시험도 같이 통과해 버린다.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const AUTHZ = path.resolve(HERE, "../../../app/core/authz.py");
// 역할 문자열 자체는 사용자 모델이 정의한다 — authz.py 는 그 이름을 import 해서 묶기만 한다.
const ROLE_SOURCE = path.resolve(HERE, "../../../app/users/models.py");

/** `NAME: tuple[str, ...] = (ROLE_A, ROLE_B)` 에서 역할 문자열을 뽑는다. */
function backendSet(name) {
  const source = fs.readFileSync(AUTHZ, "utf-8");
  const roleSource = fs.readFileSync(ROLE_SOURCE, "utf-8");
  const re = new RegExp(name + "\\s*:\\s*tuple\\[str, \\.\\.\\.\\]\\s*=\\s*\\(([^)]*)\\)");
  const m = source.match(re);
  if (!m) throw new Error(`${name} 을 app/core/authz.py 에서 못 찾았다 — 이름이 바뀌었는가?`);
  const names = m[1].split(",").map((s) => s.trim()).filter(Boolean);
  const values = names.map((n) => {
    const vm = roleSource.match(new RegExp("^" + n + '\\s*=\\s*"([^"]+)"', "m"));
    if (!vm) throw new Error(`${n} 의 값을 app/users/models.py 에서 못 찾았다`);
    return vm[1];
  });
  return values.sort();
}

describe("역할 묶음 — 화면과 서버가 같은 말을 한다", () => {
  const CASES = [
    ["CONSOLE_READ_ROLES", CONSOLE_READ_ROLES],
    ["CONSOLE_WRITE_ROLES", CONSOLE_WRITE_ROLES],
    ["CONSOLE_OPS_ROLES", CONSOLE_OPS_ROLES],
    ["SENSITIVE_READ_ROLES", SENSITIVE_READ_ROLES],
    ["SYSTEM_ADMIN_ONLY", SYSTEM_ADMIN_ONLY],
  ];

  for (const [name, front] of CASES) {
    it(name + " 가 서버와 같다", () => {
      expect([...front].sort()).toEqual(backendSet(name));
    });
  }

  it("auditor 는 쓰기 묶음 어디에도 없다", () => {
    // 감사자는 읽기 전용 가지다 — 이 한 줄이 무너지면 감사와 운영의 경계가 사라진다.
    expect(CONSOLE_WRITE_ROLES).not.toContain("auditor");
    expect(CONSOLE_OPS_ROLES).not.toContain("auditor");
    expect(SYSTEM_ADMIN_ONLY).not.toContain("auditor");
  });

  it("일반 사용자는 관리 콘솔 묶음 어디에도 없다", () => {
    for (const [, front] of CASES) expect(front).not.toContain("user");
  });
});
