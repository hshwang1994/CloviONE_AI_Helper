import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/* 「을(를)」 같은 괄호 조사가 화면 문구에 없다.
 *
 * 2026-09-06 배포 환경에서 관리자 폼의 필수 칸 오류가 「제목을(를) 입력하세요.」로 나오는
 * 것을 실측했다. 주어가 데이터(칸 이름, 문서 제목, 첨부 파일 이름)라 문장을 손으로 적어 둘
 * 수 없다는 이유로 두 조사를 나란히 적어 온 자리들이다. 그것은 한국어 문장이 아니라
 * 미결정 상태를 그대로 내보낸 것이고, CLAUDE.md §10 이 금지한다.
 *
 * 조사는 `lib/format.js` 가 받침을 보고 고른다. 이 시험은 그 규칙을 안 쓰고 다시 괄호로
 * 적는 자리가 생기지 않게 소스를 훑는다. 백엔드에도 같은 검사가 있다
 * (`tests/unit/test_korean_particles.py`).
 *
 * 주석과 문서화 문자열은 이 규칙을 **설명하려고** 그 표기를 인용한다 — 그것까지 막으면
 * 규칙을 적어 둘 자리가 없어진다. 그래서 인용 부호(「」) 가 있는 줄과 주석으로 시작하는
 * 줄은 넘긴다. 시험 파일도 같은 이유로 넘긴다.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "..");
const BRACKETED = /[을은이와를가]\([를는가과을이]\)/;

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (/\.(js|jsx)$/.test(entry.name) && !entry.name.includes(".test.")) out.push(full);
  }
  return out;
}

describe("화면 문구에 괄호 조사가 없다", () => {
  it("frontend/src 전체를 훑어도 남은 자리가 없다", () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      const lines = fs.readFileSync(file, "utf8").split("\n");
      lines.forEach((line, i) => {
        const s = line.trim();
        if (s.startsWith("//") || s.startsWith("*") || s.startsWith("/*")) return;
        if (s.includes("「") || s.includes("」")) return;
        if (BRACKETED.test(s)) offenders.push(`${path.relative(SRC, file)}:${i + 1}  ${s}`);
      });
    }
    expect(offenders).toEqual([]);
  });

  it("반례 — 검사 자체가 살아 있다", () => {
    expect(BRACKETED.test('fail(f.name, f.label + "을(를) 입력하세요.");')).toBe(true);
    expect(BRACKETED.test('throw new Error(`${f.name} 은(는) 10MB를 넘습니다.`);')).toBe(true);
    expect(BRACKETED.test('fail(f.name, f.label + objectParticle(f.label) + " 입력하세요.");')).toBe(false);
  });
});
