/* 타이포 스케일 — 가장 작은 글자는 **토큰이고, 12px 이 절대 하한이다** (`FONT_SIZE.micro`).
 *
 * ## 무엇이 바뀌었나
 *
 * PA-RC-0001 은 `0.6875rem`(11px) 13곳을 정리하면서 2곳을 "의도된 예외"로 남겼다 —
 * 6단계 스케일에 11px 슬롯이 없어서, 실측 근거가 있는 자리만 원시 리터럴을 허용한 것이다.
 *
 * D-141 에서 스케일을 역할 이름 7단계로 다시 짜면서 **`micro` 를 정식 슬롯으로 승격**했다.
 * 배지·표 안 보조 메타는 예외가 아니라 제 이름을 가진 단계다. 그래서 이 시험의 계약이
 * 바뀌었다: "예외 2곳이 그대로인가"가 아니라 **"이제 아무 데도 원시 리터럴이 없는가"** 를
 * 본다. 느슨해진 것이 아니라 반대다 — 예외가 0곳이 됐다.
 *
 * D-179 에서 한 번 더 강해진다. `micro` 의 값이 11px(`0.6875rem`)에서 **12px(`0.75rem`)**
 * 로 올라갔다 — 11px 은 한글에서 실제로 너무 작고, `tiny_text` 검사가 폭 2200 이상에서만
 * 도는 바람에 1920 에서 안 잡혔을 뿐이다. 그래서 이 시험은 이제 값 하나가 아니라 **하한을
 * 단언**한다: "가장 작은 슬롯이 12px 아래로 내려갈 수 없다"는 불변식이다. 옛 11px 리터럴이
 * 다시 스며드는 것도 계속 막는다 — 그 값은 이제 슬롯조차 아니다.
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

describe("타이포 스케일 — 가장 작은 글자는 토큰이고 12px 이 하한이다 (FONT_SIZE.micro)", () => {
  it("micro 슬롯이 12px 하한을 지킨다 (한글 가독 하한)", () => {
    expect(FONT_SIZE.micro).toBe("0.75rem");
    // 값이 아니라 **불변식**이 계약이다 — 누가 다시 내리면 여기서 걸린다.
    expect(parseFloat(FONT_SIZE.micro)).toBeGreaterThanOrEqual(0.75);
    // 그리고 micro 가 스케일에서 실제로 가장 작아야 한다.
    for (const k of ["caption", "bodySm", "body", "title", "pageTitle", "readout"]) {
      expect(parseFloat(FONT_SIZE[k]), k).toBeGreaterThan(parseFloat(FONT_SIZE.micro));
    }
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

  it("토큰 정의 파일에도 11px 은 더 이상 없다 (슬롯도 리터럴도)", () => {
    const text = readFileSync(TOKEN_DEFINITION, "utf8");
    // 스케일 선언 밖에서 `fontSize: "0.6875rem"` 로 쓰면 다시 리터럴이 퍼지기 시작한다.
    expect(text).not.toMatch(/fontSize:\s*["']0\.6875rem["']/);
    // 11px 은 이제 슬롯도 아니다 — 정의가 남아 있으면 소비처가 다시 생긴다.
    expect(text).not.toMatch(/micro:\s*["']0\.6875rem["']/);
    expect(text).toMatch(/micro:\s*["']0\.75rem["']/);
  });
});
