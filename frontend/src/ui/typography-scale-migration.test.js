/* 타이포 스케일 — 11px 은 이제 **토큰이다** (`FONT_SIZE.micro`).
 *
 * ## 무엇이 바뀌었나
 *
 * PA-RC-0001 은 `0.6875rem`(11px) 13곳을 정리하면서 2곳을 "의도된 예외"로 남겼다 —
 * 6단계 스케일에 11px 슬롯이 없어서, 실측 근거가 있는 자리만 원시 리터럴을 허용한 것이다.
 *
 * D-141 에서 스케일을 역할 이름 7단계로 다시 짜면서 **`micro`(11px) 를 정식 슬롯으로
 * 승격**했다. 배지·표 안 보조 메타는 예외가 아니라 제 이름을 가진 단계다. 그래서 이 시험의
 * 계약이 바뀐다: "예외 2곳이 그대로인가"가 아니라 **"이제 아무 데도 원시 리터럴이 없는가"**
 * 를 본다. 느슨해진 것이 아니라 반대다 — 예외가 0곳이 됐다.
 *
 * `0.9375rem`/`1rem` 같은 다른 단일값은 아이콘 크기·서체 본문·입력창처럼 다른 이유로
 * 정당하게 남아 있어(BACKLOG.md PA-01) 이 시험의 대상이 아니다.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { FONT_SIZE } from "./theme.js";

const SRC = join(process.cwd(), "src");

/* 토큰 정의 자신은 리터럴을 가질 수밖에 없다 — 스케일이 시작되는 곳이다. */
const TOKEN_DEFINITION = join(SRC, "ui", "theme.js");

function sourceFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if ((name.endsWith(".js") || name.endsWith(".jsx")) && !name.includes(".test.")) out.push(full);
  }
  return out;
}

describe("타이포 스케일 — 11px 은 토큰이다 (FONT_SIZE.micro)", () => {
  it("micro 슬롯이 실제로 11px 이다", () => {
    expect(FONT_SIZE.micro).toBe("0.6875rem");
  });

  it("토큰 정의 파일을 뺀 어디에도 11px 원시 리터럴이 없다 (예외 0곳)", () => {
    const offenders = [];
    for (const file of sourceFiles(SRC)) {
      if (file === TOKEN_DEFINITION) continue;
      const text = readFileSync(file, "utf8");
      if (/fontSize:\s*["']0\.6875rem["']/.test(text)) offenders.push(file.replace(SRC, "src"));
    }
    expect(offenders).toEqual([]);
  });

  it("토큰 정의 파일에서도 리터럴은 FONT_SIZE 선언 안에만 있다", () => {
    const text = readFileSync(TOKEN_DEFINITION, "utf8");
    // 스케일 선언 밖에서 `fontSize: "0.6875rem"` 로 쓰면 다시 리터럴이 퍼지기 시작한다.
    expect(text).not.toMatch(/fontSize:\s*["']0\.6875rem["']/);
    expect(text).toMatch(/micro:\s*["']0\.6875rem["']/);
  });
});
