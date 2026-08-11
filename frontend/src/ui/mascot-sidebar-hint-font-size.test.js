import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, it, expect } from "vitest";

/* DS-32류 회귀: Mascot.jsx 사이드바 "클로비에게 물어보기" 힌트가 fontSize="10px"(제목은
 * "12px")로 절대 px 지정돼 있어, 4K(>=3840px) 루트 글자 크기 레버(16→18→20px)가 커져도
 * 그대로 남아 QA 하네스의 tiny_text 검사(12px 하한)를 사용자 콘솔 66개 화면 전부에서
 * 실패시켰다 — 이 컴포넌트 하나가 거의 모든 화면의 사이드바에 떠 있기 때문이다.
 *
 * jsdom은 실제 레이아웃/계산된 스타일을 안정적으로 안 주므로(body-editor-toolbar-contrast.
 * test.jsx의 같은 이유) 렌더 대신 소스 텍스트로 절대 px 지정이 다시 새어 들어오지 않는지
 * 고정한다.
 */

const SRC = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "Mascot.jsx"),
  "utf-8",
);

function sidebarHintBlock() {
  const start = SRC.indexOf("클로비에게 물어보기");
  const end = SRC.indexOf("현재 화면을 기준으로 도와드려요");
  expect(start, "사이드바 힌트 텍스트를 못 찾았다").toBeGreaterThan(-1);
  expect(end, "사이드바 힌트 텍스트를 못 찾았다").toBeGreaterThan(start);
  // 앞뒤로 넉넉히 잡아 두 Typography의 fontSize 선언까지 포함시킨다.
  return SRC.slice(start - 200, end + 50);
}

describe("Mascot 사이드바 힌트 — 절대 px 글자 크기를 쓰지 않는다", () => {
  it("fontSize에 리터럴 px 값이 없다(rem이어야 4K 레버가 먹는다)", () => {
    const block = sidebarHintBlock();
    const pxFontSizes = [...block.matchAll(/fontSize=["']?(\d+)px/g)];
    expect(
      pxFontSizes.map((m) => m[0]),
      `절대 px fontSize가 남아 있다: ${block}`,
    ).toEqual([]);
  });

  it("두 Typography 모두 12px 상당(0.75rem) 이상이다", () => {
    const block = sidebarHintBlock();
    const remSizes = [...block.matchAll(/fontSize=["']?([\d.]+)rem/g)].map((m) =>
      parseFloat(m[1]),
    );
    expect(remSizes.length).toBeGreaterThanOrEqual(2);
    for (const rem of remSizes) {
      expect(rem, `${rem}rem은 12px 하한(0.75rem) 미만이다`).toBeGreaterThanOrEqual(0.75);
    }
  });
});
