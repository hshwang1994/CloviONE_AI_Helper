import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Badge, Tag } from "./kit.jsx";

/* 지시 11 — **상태와 분류는 같은 모양을 쓰지 않는다.**
 *
 * 예전에는 `정상`·`활성`·`사용 중`·`미연결`·`아니요`·`전체 관리자`가 전부 같은 알약이었고,
 * 게시판 카테고리와 문서 종류까지 그 알약에 **값마다 다른 의미색**을 받았다:
 *   `"공지" → danger`(빨강 = 이 앱에서 "오류")
 *   `"맛집" → warn`(주황 = "조치 필요")
 * 점심 메뉴 글이 조치 필요로 보이는 화면이었다. 색 어휘는 예산이고, 분류가 그것을 다 쓰면
 * 정작 상태가 말할 색이 남지 않는다.
 *
 * 지금 규칙:
 *   **상태**(지금 무슨 일이 벌어지는가) → `Badge` — 표지 + 글자 + 의미색
 *   **분류**(이것이 무엇인가)           → `Tag`   — 중립 칩, 색으로 등급을 매기지 않는다
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "..");

function read(rel) {
  return fs.readFileSync(path.join(SRC, rel), "utf-8");
}

describe("Badge 와 Tag 는 다른 것을 말한다", () => {
  it("Badge 는 표지를 갖고 Tag 는 갖지 않는다", () => {
    const { container: b } = render(<Badge value="정상" kind="ok" />);
    const badge = b.querySelector(".k-badge");
    expect(badge, "Badge 구조가 바뀌었다 — 이 검사가 아무것도 안 보고 있다").toBeTruthy();
    // 색만으로 상태를 전하지 않는다(WCAG 1.4.1) — 표지가 색 + 모양을 함께 쓴다.
    expect(badge.querySelector('[aria-hidden="true"]'), "상태 표지가 없다").toBeTruthy();

    const { container: t } = render(<Tag label="회의록" />);
    const tag = t.querySelector(".k-tag");
    expect(tag).toBeTruthy();
    expect(tag.querySelector('[aria-hidden="true"]'), "분류에 상태 표지가 붙었다").toBeNull();
  });

  it("Tag 는 톤을 안 주면 중립이다", () => {
    const { container } = render(<Tag label="기획서" />);
    expect(container.querySelector(".k-tag").dataset.tone).toBe("neutral");
  });
});

describe("분류값에 의미색을 매기는 표가 남아 있지 않다", () => {
  it("lib/badges.js 에 카테고리·문서 종류 색 표가 없다", () => {
    const source = read("lib/badges.js");
    for (const gone of ["BOARD_CATEGORY_KIND", "DOC_TYPE_KIND", "boardCategoryKind", "docTypeKind"]) {
      expect(source, `분류 색 표가 되돌아왔다: ${gone}`).not.toContain(gone);
    }
    // 제안 상태는 진짜 상태라 남는다.
    expect(source).toContain("ideaStatusKind");
  });

  it("게시판·문서 화면이 분류를 Badge 로 그리지 않는다", () => {
    const CASES = [
      ["screens/Board.jsx", ["p.category"]],
      ["screens/BoardPost.jsx", ["post.category"]],
      // 옛 문서 화면 두 개는 사라졌다 (S14 · C2) — 문서는 `/knowledge` 한 화면이 그린다.
    ];
    for (const [rel, fields] of CASES) {
      const source = read(rel);
      for (const field of fields) {
        // `<Badge value={p.category}` 같은 모양이 다시 생기면 잡는다.
        const bad = new RegExp("<Badge[^>]*value=\\{\\s*" + field.replace(".", "\\.") + "\\s*\\}");
        expect(bad.test(source), `${rel}: ${field} 가 다시 상태 배지가 됐다`).toBe(false);
      }
    }
  });
});
