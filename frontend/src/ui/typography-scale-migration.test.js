/* PA-RC-0001 — 6단계 스케일 밖 원시 리터럴 정리(2026-08-16, "5차 확장"과 짝인 코드 회귀).
 *
 * `0.6875rem`(11px) 13곳을 전부 file:line이 아니라 실제 소스 문맥으로 대조했다 — 11곳은
 * 형제 패턴 증거(같은 파일 안에 이미 FONT_SIZE.caption을 쓰는 구조적으로 동일한 라벨이
 * 있음)를 확인하고 토큰으로 옮겼다. 남은 2곳(`ui/kit.jsx`의 StatCard 심각도 배지,
 * `ui/theme.js`의 MuiTableCell head)은 각자 자리에 실측 근거를 남긴 **의도된 예외**다 —
 * 하나는 QAH-02가 12px에서 줄바꿈 결함을 실측했고, 하나는 기준선 파일(`th{font-size:11px}`)과
 * 정확히 일치한다. 이 시험은 그 11곳이 다시 원시 리터럴로 되돌아가지 않는지만 본다 —
 * `0.9375rem`/`1rem`/그 외 단일값 클러스터는 아이콘 크기·서체 본문·입력창·자격증명 표시 같은
 * 다른 이유로 이미 정당하게 남아 있어(BACKLOG.md PA-01 상세) 이 시험의 대상이 아니다. */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

// 값을 실측·문서화해 둔 의도된 예외 — 이 두 파일만은 리터럴이 있어도 통과한다.
const ALLOWED_RAW_LITERAL_FILES = new Set([
  join(SRC, "ui", "kit.jsx"),
  join(SRC, "ui", "theme.js"),
]);

function sourceFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if ((name.endsWith(".js") || name.endsWith(".jsx")) && !name.includes(".test.")) out.push(full);
  }
  return out;
}

describe("타이포 스케일 — 0.6875rem(11px) 원시 리터럴 (PA-RC-0001)", () => {
  it("의도된 예외 2곳을 뺀 나머지는 전부 FONT_SIZE 토큰을 쓴다", () => {
    const offenders = [];
    for (const file of sourceFiles(SRC)) {
      if (ALLOWED_RAW_LITERAL_FILES.has(file)) continue;
      const text = readFileSync(file, "utf8");
      if (/fontSize:\s*["']0\.6875rem["']/.test(text)) offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });

  it("의도된 예외 2곳은 여전히 정확히 그 파일들이다(회귀 확인용 — 값이 사라지면 이 시험이 실패해 알려준다)", () => {
    for (const file of ALLOWED_RAW_LITERAL_FILES) {
      const text = readFileSync(file, "utf8");
      expect(text, `${file}에 더 이상 예외 리터럴이 없다 — 위 목록에서 빼도 되는지 확인하라`).toMatch(/fontSize:\s*["']0\.6875rem["']/);
    }
  });
});
