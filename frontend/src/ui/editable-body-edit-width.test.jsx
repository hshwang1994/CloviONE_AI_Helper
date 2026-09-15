import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* 티켓/문서 본문 편집(EditableBody) — 편집 중 표면은 78ch 산문 상한이 아니라 컨테이너
 * 폭을 따라간다.
 *
 * 왜 필요한가 — 예전엔 편집 모드(툴바+입력 상자+미리보기)를 읽기용 78ch 로 묶었다.
 * BodyEditor 안의 입력 상자는 애초에 fullWidth 인데, 바깥 Box 가 78ch 로 눌러 놓아
 * 넓은 화면에서 편집기 전체가 왼쪽으로 쏠려 보였다.
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
      bodyDoc={{ type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: "원래 본문" }] }] }}
      bodyVersion="v1"
      bodyIsLocal
      sourceView={<div>원래 본문</div>}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "본문 수정" }));
  const heading = screen.getByRole("heading", { name: "본문 수정" });
  // heading -> 제목 칸 -> 판 제목(SectionTitle) 줄 -> 편집 폭 Box. 머리 줄은 판 제목 정본이다(핸드오프 B-8).
  const widthBox = heading.parentElement.parentElement.parentElement;
  const container = widthBox.parentElement;
  return { widthBox, container };
}

describe("본문 수정 — 편집 중 표면 폭", () => {
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

describe("본문 수정 — 취소 · 저장은 판 발이다 (핸드오프 RULES §7 · 조합 계약 C-4 · C-5)", () => {
  it("머리 줄에는 단추가 없고, 발은 판 가장자리까지 편 따라오는 발이며 취소 → 저장이 오른쪽 끝이다", async () => {
    const { widthBox } = await openEditing();
    const heading = screen.getByRole("heading", { name: "본문 수정" });
    const headRow = heading.parentElement.parentElement;
    expect(headRow.querySelectorAll("button")).toHaveLength(0);
    const footer = widthBox.querySelector("[data-action-footer]");
    expect(footer, "판 발이 없다").not.toBeNull();
    expect(footer.getAttribute("data-action-footer")).toBe("card");
    expect(footer.hasAttribute("data-action-footer-sticky")).toBe(true);
    expect(getComputedStyle(footer).position).toBe("sticky");
    expect([...footer.querySelectorAll("button")].map((b) => b.textContent)).toEqual(["취소", "저장"]);
    // 발은 편집 표면의 마지막 줄이다 — 편집기 뒤에 선다.
    expect(widthBox.lastElementChild).toBe(footer);
    // 발의 단추는 34 다(카드 발) — 머리 줄에 있던 때의 30 이 아니다.
    for (const b of footer.querySelectorAll("button")) expect(b.className).not.toMatch(/MuiButton-sizeSmall/);
  });
});
