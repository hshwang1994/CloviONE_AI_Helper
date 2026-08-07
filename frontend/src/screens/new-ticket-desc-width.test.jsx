import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";

/* '새 티켓' 설명 편집기 블록의 폭이 컨테이너를 따라가는가(고정 60rem 캡이 아닌가).
 *
 * 왜 필요한가 — 이 블록만 `maxWidth: "60rem"` 을 손으로 박아 뒀었다. 바로 위 짧은 값
 * 격자(NT_FIELD_GRID)와 그 격자를 감싼 폼 자체는 컨테이너 폭(폼의 72rem 상한)을 그대로
 * 받는데, 설명 블록만 그보다 좁은 60rem 에서 한 번 더 멈춰 4K 등 넓은 화면에서 편집기+
 * 미리보기가 폼의 다른 부분보다 눈에 띄게 좁게, 왼쪽으로 쏠려 보였다.
 *
 * jsdom 은 컨테이너 질의를 평가하지 않으므로(new-ticket-layout.test.jsx 의 같은 이유),
 * emotion 이 실제로 낸 CSS 규칙 텍스트를 읽어 판정 규칙 자체를 검사한다: 기본(무조건) 규칙에
 * 고정 rem 상한이 없고, 상한이 있다면 반드시 컨테이너 질의 뒤에서만 걸리는가.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "me-1" } }),
}));

import { NewTicket } from "./MyTickets.jsx";
import { createClovirTheme } from "../ui/theme.js";

function apiOk() {
  apiMock.mockImplementation((path) => {
    if (path === "/api/tickets/projects") return Promise.resolve({ projects: [] });
    if (path === "/api/tickets/meta") return Promise.resolve({ statuses: ["계획"], priorities: [], difficulties: [] });
    if (path === "/api/tickets/assignees") return Promise.resolve({ assignees: [] });
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
  apiOk();
});

function renderNewTicket() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={createClovirTheme()}>
        <NewTicket />
      </ThemeProvider>
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

async function descNodes() {
  const label = await waitFor(() => {
    const el = document.querySelector('label[for="nt-desc"]');
    if (!el) throw new Error("nt-desc 라벨이 아직 없음");
    return el;
  });
  const widthBox = label.parentElement;
  const container = widthBox.parentElement;
  return { widthBox, container };
}

describe("새 티켓 — 설명 편집기 폭은 고정 캡이 아니라 컨테이너를 따라간다", () => {
  it("설명 블록을 감싸는 조상에 컨테이너가 선언돼 있다", async () => {
    renderNewTicket();
    const { container } = await descNodes();
    const containerRule = rulesFor(container).find((r) => r.cond === "");
    expect(containerRule, "컨테이너를 여는 조상 규칙이 없다").toBeTruthy();
    expect(declaration(containerRule, "container-type")).toBe("inline-size");
    expect(declaration(containerRule, "container-name")).toBeTruthy();
  });

  it("기본(무조건) 규칙에는 고정 rem 상한이 없다 — 좁으면 그만큼만 채운다", async () => {
    renderNewTicket();
    const { widthBox } = await descNodes();
    const base = rulesFor(widthBox).filter((r) => r.cond === "");
    expect(base).toHaveLength(1);
    expect(declaration(base[0], "max-width")).not.toBe("60rem");
  });

  it("고정 캡이 있다면 반드시 컨테이너 질의 뒤에서만 걸린다(뷰포트 매체쿼리 아님)", async () => {
    renderNewTicket();
    const { widthBox } = await descNodes();
    const capRules = rulesFor(widthBox).filter((r) => declaration(r, "max-width") != null && r.cond !== "");
    for (const r of capRules) {
      expect(CONTAINER_QUERY.test(r.cond), `뷰포트 조건으로 폭을 제한하고 있다: ${r.cond}`).toBe(true);
    }
  });
});
