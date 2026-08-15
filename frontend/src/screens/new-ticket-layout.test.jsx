import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";

/* '새 티켓' 폼의 짧은 값 입력 격자가 **뷰포트가 아니라 자기가 놓인 칸의 폭**으로 열 수를
 * 정하는지 본다.
 *
 * 왜 이 테스트가 필요한가 — 예전 격자는 `{ xs, sm:2열, xxl:3열 }` 이었다. sm(600)·xxl(2200)은
 * 뷰포트 폭인데 격자가 놓인 칸은 사이드바(264)와 '작성 도움' 레일(22rem)을 뺀 나머지라
 * 훨씬 좁다. 실측(scripts/ui_qa 세션을 재사용한 크로미움 10폭 측정, 2026-08-06):
 *
 *   뷰포트   격자 폭   고친 뒤 열/칸        고치기 전 열/칸
 *      390      308    1열 / 308            1열 / 308
 *      768      670    2열 / 325            2열 / 325
 *      900      538    2열 / 259            2열 / 259
 *     1024      662    2열 / 321            2열 / 321
 *     1200      466    1열 / 466        ←   2열 / 223   ← 뷰포트 390(1열 308)보다 좁았다
 *     1366      632    2열 / 306            2열 / 306
 *     1536      786    2열 / 383            2열 / 383
 *     1920     1152    3열 / 371        ←   2열 / 566
 *     2560     1296    3열 / 419            3열 / 417
 *     3840     1440    3열 / 463            3열 / 463
 *
 * jsdom 은 컨테이너 질의를 **평가하지 않는다**. 그래서 '몇 열로 그려졌나'를 물어볼 수 없다.
 * 대신 emotion 이 실제로 내보낸 CSS 규칙을 읽어 **판정 규칙 자체**를 검사한다:
 *   1) 열 수를 바꾸는 규칙이 전부 `@container` 인가(뷰포트 `@media` 가 하나라도 있으면 실패),
 *   2) 그 임계값을 위 실측 폭에 적용했을 때 한 칸이 절대 16rem 밑으로 안 내려가는가.
 * 실제 브라우저에서의 열 수·픽셀은 위 표대로 별도 실측했다(테스트가 대신하지 못한다).
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
import { BASELINE_TRACKS } from "../ui/density.js";

/* 실측표(위 주석)의 컨테이너 폭. root 는 styles/root.css 의 루트 폰트사이즈
 * (기본 16px, ≥2200px 18px, ≥3000px 20px) — rem 임계값이 이 값으로 픽셀이 된다.
 *
 * ⚠️ 이 표는 2026-08-06 에 **레일이 22rem 고정이던 때** 브라우저로 잰 값이다. 2026-08-07 에
 * 바깥 2열이 기준선 `.grid.two`(1.45 : 0.8 비율)로 바뀌면서 폼 열이 좁아졌다. 계산해 보면
 * 1920 에서 격자 폭이 1152 → 약 976px(3열이면 한 칸 312px = 19.5rem)이라 아래 16rem 하한은
 * 여전히 여유가 있고, 2560·3840 은 폼의 72rem 상한이 먼저 걸려 값이 그대로다. 다만
 * **다시 재지는 않았다** — 브라우저 실측은 서버를 띄워야 해서 이 세션에서 못 했다.
 * 표를 지우지 않는 이유: 지우면 이 검사가 무엇을 근거로 하는지가 사라진다. */
const MEASURED = [
  { viewport: 390, container: 308, root: 16 },
  { viewport: 768, container: 670, root: 16 },
  { viewport: 900, container: 538, root: 16 },
  { viewport: 1024, container: 662, root: 16 },
  { viewport: 1200, container: 466, root: 16 },
  { viewport: 1366, container: 632, root: 16 },
  { viewport: 1536, container: 786, root: 16 },
  { viewport: 1920, container: 1152, root: 16 },
  { viewport: 2560, container: 1296, root: 18 },
  { viewport: 3840, container: 1440, root: 20 },
];

/* 한 칸이 이보다 좁아지면 프로젝트 이름·'예상 WD' 같은 라벨이 잘린다. 화면 코드의
 * NT_FIELD_MIN_REM 과 같은 값이지만 **일부러 여기 다시 적는다** — 화면이 이 하한을 몰래
 * 낮추면 테스트가 잡아야 하므로, 화면에서 import 해 오면 검사가 무의미해진다. */
const MIN_FIELD_REM = 16;

const CONTAINER_QUERY = /^@container\s+([\w-]+)\s+\(min-width:\s*([\d.]+)rem\)$/;

function apiOk() {
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/tickets/projects") return Promise.resolve({ projects: [{ id: "p-1", name: "인프라" }] });
    if (path === "/api/tickets/meta") return Promise.resolve({ statuses: ["계획", "진행"], priorities: ["high"], difficulties: ["중"] });
    if (path === "/api/tickets/assignees") return Promise.resolve({ assignees: [{ user_id: "me-1", name: "나" }] });
    if (path === "/api/tickets" && opts && opts.method === "POST") return Promise.resolve({ id: "t-9" });
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

/* emotion 이 <style> 에 넣은 규칙 중 이 요소의 클래스에 걸린 것만 (감싼 at-rule, 선언) 으로
 * 뽑는다. 중괄호 짝을 세며 훑어야 `@media{ .css-x{…} }` 같은 한 겹 중첩을 놓치지 않는다. */
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

function columnCount(track) {
  const repeat = /^repeat\(\s*(\d+)\s*,/.exec(track);
  if (repeat) return Number(repeat[1]);
  // `minmax(0, 1fr)` 처럼 괄호 안 쉼표가 있으므로 최상위 공백만으로 트랙을 센다.
  return track.replace(/\([^)]*\)/g, "x").split(/\s+/).filter(Boolean).length;
}

/* 열 수를 바꾸는 규칙만 (조건, 열 수) 로. 소스 순서를 유지한다 — 뒤에 온 규칙이 이긴다. */
function columnRules(el) {
  return rulesFor(el)
    .map((r) => ({ cond: r.cond, track: declaration(r, "grid-template-columns") }))
    .filter((r) => r.track)
    .map((r) => ({ cond: r.cond, columns: columnCount(r.track) }));
}

/* 실제로 내보낸 CSS 를 그대로 해석해 '이 폭이면 몇 열' 을 계산한다. 테스트가 임계값을
 * 따로 들고 있으면 CSS 와 어긋나도 초록으로 남는다 — 판정은 CSS 한 곳에서만 나온다.
 *
 * 모르는 조건을 만나면 **건너뛰지 않고 던진다.** 조용히 넘기면 뷰포트 @media 로 되돌려 놨을 때
 * '기본값 1열' 로만 계산돼 이 검사가 초록으로 남는다(되돌려 보고 실제로 그랬다). */
function columnsAt(rules, containerPx, rootPx) {
  const base = rules.filter((r) => r.cond === "");
  if (base.length !== 1) throw new Error(`조건 없는 기본 열 수가 ${base.length}개다 — 컨테이너 질의가 아니다`);
  let columns = base[0].columns;
  for (const r of rules) {
    if (r.cond === "") continue;
    const m = CONTAINER_QUERY.exec(r.cond);
    if (!m) throw new Error(`컨테이너 질의가 아닌 조건이 열 수를 바꾼다: ${r.cond}`);
    if (Number(m[2]) * rootPx <= containerPx) columns = r.columns;
  }
  return columns;
}

async function fieldGrid() {
  const proj = await waitFor(() => {
    const el = document.getElementById("nt-proj");
    if (!el) throw new Error("nt-proj 가 아직 없음");
    return el;
  });
  const grid = proj.closest(".MuiFormControl-root").parentElement;
  return { grid, container: grid.parentElement };
}

describe("새 티켓 — 필드 격자는 컨테이너 폭으로 열 수를 정한다", () => {
  it("열 수를 바꾸는 규칙이 전부 @container 이고, 뷰포트 @media 는 하나도 관여하지 않는다", async () => {
    renderNewTicket();
    const { grid, container } = await fieldGrid();

    // 컨테이너가 되는 조상이 실제로 선언돼 있어야 @container 가 아무 일도 안 하는 걸 막는다.
    const containerRule = rulesFor(container).find((r) => r.cond === "");
    expect(declaration(containerRule, "container-type")).toBe("inline-size");
    const name = declaration(containerRule, "container-name");
    expect(name).toBeTruthy();

    const rules = columnRules(grid);
    expect(rules.length).toBeGreaterThan(1);
    const base = rules.filter((r) => r.cond === "");
    expect(base).toHaveLength(1);
    expect(base[0].columns).toBe(1); // 컨테이너 질의를 못 알아듣는 브라우저가 받을 값

    const conditional = rules.filter((r) => r.cond !== "");
    expect(conditional.length).toBeGreaterThan(0);
    for (const r of conditional) {
      const m = CONTAINER_QUERY.exec(r.cond);
      expect(m, `열 수를 뷰포트 조건으로 바꾸고 있다: ${r.cond}`).not.toBeNull();
      expect(m[1]).toBe(name);
    }
    // 임계값과 열 수가 같이 커져야 columnsAt 의 '뒤가 이긴다' 가 뜻이 통한다.
    const thresholds = conditional.map((r) => Number(CONTAINER_QUERY.exec(r.cond)[2]));
    expect([...thresholds].sort((a, b) => a - b)).toEqual(thresholds);
    expect([...conditional.map((r) => r.columns)].sort((a, b) => a - b)).toEqual(conditional.map((r) => r.columns));
  });

  it("실측한 10개 폭 어디에서도 한 칸이 16rem 밑으로 내려가지 않는다", async () => {
    renderNewTicket();
    const { grid } = await fieldGrid();
    const rules = columnRules(grid);
    const gapRem = Number(/^([\d.]+)rem$/.exec(declaration(rulesFor(grid).find((r) => r.cond === ""), "gap"))[1]);

    const narrow = [];
    for (const m of MEASURED) {
      const columns = columnsAt(rules, m.container, m.root);
      const field = (m.container - (columns - 1) * gapRem * m.root) / columns;
      if (field < MIN_FIELD_REM * m.root) {
        narrow.push(`뷰포트 ${m.viewport}: 격자 ${m.container}px → ${columns}열 → 한 칸 ${Math.round(field)}px`);
      }
    }
    expect(narrow).toEqual([]);
  });

  it("레일이 붙는 lg(1200)에서 1열로 떨어진다 — 예전엔 2열이라 한 칸이 223px 였다", async () => {
    renderNewTicket();
    const { grid } = await fieldGrid();
    const rules = columnRules(grid);
    expect(columnsAt(rules, 466, 16)).toBe(1);
  });

  /* 오탐 방지 — '전부 1열' 로 만들어 놓고 위 검사를 통과시키는 퇴행을 막는다. */
  it("폭이 남는 화면에서는 여전히 여러 열로 편다(1열로 뭉개지 않는다)", async () => {
    renderNewTicket();
    const { grid } = await fieldGrid();
    const rules = columnRules(grid);
    expect(columnsAt(rules, 670, 16)).toBe(2);   // 뷰포트 768
    expect(columnsAt(rules, 1152, 16)).toBe(3);  // 뷰포트 1920
    expect(columnsAt(rules, 1440, 20)).toBe(3);  // 뷰포트 3840
  });
});

describe("새 티켓 — 폼과 레일은 그대로다(오탐 방지)", () => {
  /* Q5(카드 높이 편차) 재발 방지. 이 화면은 레일과 폼의 바닥을 stretch 로 맞춰 뒀고,
   * start 로 되돌렸다가 474px 편차로 잡힌 이력이 있다. 격자를 건드리는 김에 같이 지킨다. */
  /* 2026-08-07: 레일 폭이 `22rem` 고정에서 기준 목업 `.grid.two` 의 비율 트랙으로 바뀌었다.
   * 고정 폭은 폭 자체는 채웠지만 넓은 화면에서 레일만 얇은 띠로 남았고, 무엇보다 이 저장소가
   * 화면마다 손으로 정한 폭이 기준선과 어긋나던 자리다. 값은 `ui/density.js` 한 곳에서 온다. */
  it("바깥 2열은 lg 에서 기준선 .grid.two 트랙이고 바닥을 stretch 로 맞춘다", async () => {
    renderNewTicket();
    const { grid } = await fieldGrid();
    const outer = grid.closest("form").parentElement.parentElement;
    const rules = rulesFor(outer);
    const base = rules.find((r) => r.cond === "");
    expect(declaration(base, "align-items")).toBe("stretch");
    const rail = rules.find((r) => /min-width:\s*1200px/.test(r.cond));
    expect(rail, "lg 에서 레일을 세우는 규칙이 사라졌다").toBeTruthy();
    expect(declaration(rail, "grid-template-columns")).toBe(BASELINE_TRACKS.two);
  });

  it("여섯 개 입력이 모두 그려지고, 제목을 채워 제출하면 티켓을 만든다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    for (const label of ["프로젝트", "진행상태", "우선순위", "난이도", "예상 WD", "마감일"]) {
      expect(await screen.findByLabelText(new RegExp(label))).toBeInTheDocument();
    }
    await user.type(screen.getByLabelText(/제목/), "서버 등록 IP 중복 방지");
    // 프로젝트는 후보가 있으면 필수다 — 고르지 않으면 제출이 막힌다(그 검증도 함께 지킨다).
    await user.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await user.click(await screen.findByRole("option", { name: "인프라" }));
    await user.click(screen.getByRole("button", { name: "티켓 추가" }));
    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith("/api/tickets", expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({ title: "서버 등록 IP 중복 방지" }),
      }));
    });
  });
});
