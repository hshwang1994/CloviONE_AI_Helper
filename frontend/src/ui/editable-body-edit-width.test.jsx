import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* 티켓/문서 본문 편집(EditableBody) — 편집 중 표면은 78ch 산문 상한이 아니라 컨테이너
 * 폭을 따라간다.
 *
 * 왜 필요한가 — 읽기 모드는 산문이라 PROSE_MAX_WIDTH(78ch)에서 멈추는 게 맞지만, 예전엔
 * 편집 모드(툴바+입력 상자+미리보기)도 같은 78ch 로 묶었다. BodyEditor 안의 입력 상자는
 * 애초에 fullWidth 로 설계돼 있는데(BodyEditor.jsx 의 BodyPreview wide 설명 참고), 그
 * 바깥 Box 가 78ch 로 눌러 놓아 4K 등 넓은 화면에서 편집기 전체가 왼쪽으로 쏠려 보였다.
 *
 * jsdom 은 컨테이너 질의를 평가하지 않으므로(new-ticket-layout.test.jsx 의 같은 이유),
 * emotion 이 실제로 낸 CSS 규칙 텍스트를 읽어 판정 규칙 자체를 검사한다.
 */

vi.mock("../lib/api.js", () => ({ api: vi.fn(() => Promise.resolve({})), setCsrf: () => {} }));

import { EditableBody } from "./EditableBody.jsx";
import { ConfirmProvider, ToastProvider } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

function wrap(node) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>{node}</ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function rulesFor(el) {
  const classes = [...el.classList].filter((c) => c.startsWith("css-"));
  const css = [...document.querySelectorAll("style")].map((s) => s.textContent || "").join("\n");
  const found = [];
  const scan = (text, cond) => {
    let i = 0;
    while (i < text.length) {
      const open = text.indexOf("{", i);
      if (open === -1) break;
      const head = text.slice(i, open).trim();
      let depth = 1;
      let j = open + 1;
      while (j < text.length && depth > 0) {
        if (text[j] === "{") depth += 1;
        else if (text[j] === "}") depth -= 1;
        j += 1;
      }
      if (head.startsWith("@")) scan(text.slice(open + 1, j - 1), cond ? `${cond} && ${head}` : head);
      else if (head.split(",").some((s) => classes.includes(s.trim().replace(/^\./, "")))) {
        found.push({ cond, body: text.slice(open + 1, j - 1) });
      }
      i = j;
    }
  };
  scan(css, "");
  return found;
}

function declaration(rule, prop) {
  const m = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`).exec(rule.body);
  return m ? m[1].trim() : null;
}

const CONTAINER_QUERY = /^@container\s+([\w-]+)\s+\(min-width:\s*([\d.]+)rem\)$/;

async function openEditing() {
  wrap(
    <EditableBody
      editorId="ticket-body-1"
      endpoint="/api/tickets/1/body"
      bodyMarkdown="원래 본문"
      bodyVersion="v1"
      bodyIsLocal
      sourceView={<div>원래 본문</div>}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "본문 편집" }));
  const heading = screen.getByRole("heading", { name: "본문 편집" });
  const widthBox = heading.parentElement.parentElement; // heading -> Stack -> 편집 폭 Box
  const container = widthBox.parentElement;
  return { widthBox, container };
}

describe("본문 편집 — 편집 중 표면 폭", () => {
  it("편집 표면을 감싸는 조상에 컨테이너가 선언돼 있다", async () => {
    const { container } = await openEditing();
    const containerRule = rulesFor(container).find((r) => r.cond === "");
    expect(containerRule, "컨테이너를 여는 조상 규칙이 없다").toBeTruthy();
    expect(declaration(containerRule, "container-type")).toBe("inline-size");
    expect(declaration(containerRule, "container-name")).toBeTruthy();
  });

  it("기본(무조건) 규칙은 78ch 산문 상한을 쓰지 않는다", async () => {
    const { widthBox } = await openEditing();
    const base = rulesFor(widthBox).filter((r) => r.cond === "");
    expect(base).toHaveLength(1);
    expect(declaration(base[0], "max-width")).not.toBe("78ch");
  });

  it("고정 캡이 있다면 반드시 컨테이너 질의 뒤에서만 걸린다(뷰포트 매체쿼리 아님)", async () => {
    const { widthBox } = await openEditing();
    const capRules = rulesFor(widthBox).filter((r) => declaration(r, "max-width") != null && r.cond !== "");
    for (const r of capRules) {
      expect(CONTAINER_QUERY.test(r.cond), `뷰포트 조건으로 폭을 제한하고 있다: ${r.cond}`).toBe(true);
    }
  });
});
