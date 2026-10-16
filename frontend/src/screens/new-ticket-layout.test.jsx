import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fillDateField } from "../test-helpers/dateField.js";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";

/* qa-contract-change: 새 티켓 바깥 2열이 뷰포트 lg(1200) 문턱의 화면 사본(NEW_TICKET_GRID)에서 정본 내용 폭 짝 트랙(본문 칸 64rem 컨테이너 질의, density.js::contentPairTracks — UI 3차 조합 계약 C-5)으로 옮겼다. 「lg 에서 기준선 two」 단언을 「컨테이너 질의로 기준선 two · 뷰포트 @media 0」으로 옮기고, 두 판이 화면 아래까지 서는 표식 · 폼 판 세로 흐름과 넘침 풀기 · 편집기 상자 · 따라오는 판 발 · FAB 여백 없는 발 끝을 더 잰다. 1200 실측 행은 레일 옆 1칸(502px)에서 레일이 폼 아래로 간 1열 본문 폭 12칸(862px)으로 옮기고, 좁은 칸 1칸 판정은 폭 값으로 남긴다.
 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */
/* qa-contract-change: 새 티켓 칸 격자가 화면 사본(NT_FIELD_GRID 1·2·3열, 제목은 격자 밖 노치 라벨)에서 정본 12칸 격자(density.js::FORM_FIELD_GRID_12 + kit FormFieldCell)로 옮겨(핸드오프 계획 C · 표 8), 열 수 · 칸 차지 · 칸 폭 하한 · 실측표 · 라벨 계약을 새 구조로 옮기고 검증 오류 줄과 저장 실패 상자의 수명 시험을 더한다. */

/* '새 티켓' 폼의 칸 격자가 **뷰포트가 아니라 자기가 놓인 칸의 폭**으로 열 수를 정하는지 본다.
 *
 * 왜 이 테스트가 필요한가 — 예전 격자는 `{ xs, sm:2열, xxl:3열 }` 이었다. sm(600)·xxl(2200)은
 * 뷰포트 폭인데 격자가 놓인 칸은 사이드바와 '작성 도움' 레일을 뺀 나머지라 훨씬 좁다. 뷰포트
 * 1200 에서 한 칸이 223px 로 짜부라졌던 것이 그 결과다.
 *
 * 지금 격자는 정본 12칸 격자다(핸드오프 RULES §7 · 계획 표 8): 칸 둘(16rem)이 들어가면 2칸, 칸 셋이
 * 들어가면 12칸이고, 칸마다 문턱별로 차지하는 칸 수를 따로 말한다(제목 12/2, 프로젝트 6/1, 짧은 값 넷 3/1,
 * 담당자 3/2). 칸 하나는 라벨 · 입력 · 도움말의 세 줄 트랙이다(`kit.jsx::FormFieldCell`).
 *
 * jsdom 은 컨테이너 질의를 **평가하지 않는다**. 그래서 '몇 열로 그려졌나'를 물어볼 수 없다.
 * 대신 emotion 이 실제로 내보낸 CSS 규칙을 읽어 **판정 규칙 자체**를 검사한다:
 *   1) 열 수와 칸 차지를 바꾸는 규칙이 전부 `@container` 인가(뷰포트 `@media` 가 하나라도 있으면 실패),
 *   2) 그 규칙을 아래 실측 폭에 적용한 열 수 · 칸 폭이 브라우저가 실제로 그린 값과 같은가,
 *   3) 어느 폭에서도 칸이 하한 밑으로 내려가지 않고 줄에 빈틈이 생기지 않는가.
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

/* 브라우저 실측(2026-09-15, `kit_measure --routes user_new-ticket` 의 `form_grids` — 격자 폭과 줄마다 칸 폭).
 * UI 3차 P4 에서 바깥 2열이 내용 폭 짝 트랙이 된 뒤 열 뷰포트를 다시 쟀다(`compose-p4-grids`) — 바뀐 것은 1200 하나다.
 * root 는 styles/root.css 의 루트 폰트사이즈(기본 16px, ≥2200px 18px, ≥3000px 20px)다.
 * 뷰포트 1710 은 격자 폭이 12칸 문턱(50.5rem = 808px)에 반올림으로 걸려(브라우저는 2칸) 표에서 뺐다. */
const MEASURED = [
  { viewport: 390, container: 316, root: 16, rows: [[316], [316], [316], [316], [316], [316], [316], [316]] },
  { viewport: 768, container: 678, root: 16, rows: [[678], [329, 329], [329, 329], [329, 329], [678]] },
  { viewport: 900, container: 562, root: 16, rows: [[562], [271, 271], [271, 271], [271, 271], [562]] },
  { viewport: 1024, container: 686, root: 16, rows: [[686], [333, 333], [333, 333], [333, 333], [686]] },
  { viewport: 1200, container: 862, root: 16, rows: [[862], [421, 201, 201], [201, 201, 201, 201]] },
  { viewport: 1366, container: 605, root: 16, rows: [[605], [292, 292], [292, 292], [292, 292], [605]] },
  { viewport: 1536, container: 700, root: 16, rows: [[700], [340, 340], [340, 340], [340, 340], [700]] },
  { viewport: 1920, container: 937, root: 16, rows: [[937], [459, 219, 219], [219, 219, 219, 219]] },
  { viewport: 2560, container: 1296, root: 18, rows: [[1296], [637, 307, 307], [307, 307, 307, 307]] },
  { viewport: 3840, container: 1440, root: 20, rows: [[1440], [708, 341, 341], [341, 341, 341, 341]] },
];

/* 칸 폭 하한 — 화면 코드에서 가져오지 않고 **일부러 여기 다시 적는다.** 화면이 문턱이나 칸 차지를
 * 몰래 바꾸면 이 시험이 잡아야 하므로, 화면에서 import 해 오면 검사가 무의미해진다.
 *   · 한 칸(1칸 · 2칸 격자의 칸, 12칸 격자의 절반 이상 칸) 16rem — 프로젝트 이름 · 사람 칩이 서는 폭이다.
 *   · 12칸 격자의 짧은 값 칸(span 3) — 12칸이 켜지는 문턱은 16rem 칸 셋과 틈 둘(50.5rem)이고, 그 폭을
 *     짧은 칸 넷이 틈 셋을 두고 나눈다: (50.5 − 3 × 1.25) / 4 = 11.6875rem(187px). 날짜(YYYY-MM-DD + 달력
 *     단추) · 진행상태 · 우선순위가 잘리지 않고 서는 폭이다. */
const MIN_FIELD_REM = 16;
const MIN_SHORT_FIELD_REM = 11.6875;

/* 칸 순서와 문턱별 칸 차지(계획 표 8). */
const FIELDS = [
  { label: "제목", wide: 12, mid: 2 },
  { label: "프로젝트", wide: 6, mid: 1 },
  { label: "진행상태", wide: 3, mid: 1 },
  { label: "우선순위", wide: 3, mid: 1 },
  { label: "난이도", wide: 3, mid: 1 },
  { label: "예상 WD", wide: 3, mid: 1 },
  { label: "마감일", wide: 3, mid: 1 },
  { label: "담당자", wide: 3, mid: 2 },
];

const CONTAINER_QUERY = /^@container\s+([\w-]+)\s+\(min-width:\s*([\d.]+)rem\)$/;

function apiOk() {
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/tickets/projects") return Promise.resolve({ projects: [{ id: "p-1", name: "인프라" }] });
    if (path === "/api/tickets/meta") return Promise.resolve({ statuses: ["계획", "진행"], priorities: ["high"], difficulties: ["중"] });
    if (String(path).startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [{ user_id: "me-1", name: "나" }] });
    if (path === "/api/tickets" && opts && opts.method === "POST") return Promise.resolve({ id: "t-9" });
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
  apiOk();
});

function renderNewTicket() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  /* 라우터 안에서 그린다 — 실제 앱이 그렇고(`app/UserRoutes.jsx`), 만든 뒤 그 티켓으로
     이동하는 것이 이 화면의 마지막 단계다(`navigate('/tickets/:id')`). 라우터 없이 그리면
     그 단계 자체를 시험이 못 본다. */
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={createClovirTheme()}>
        <MemoryRouter initialEntries={["/new-ticket"]}>
          <NewTicket />
        </MemoryRouter>
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

/* 한 속성을 바꾸는 규칙만 (조건, 값) 으로. 소스 순서를 유지한다 — 뒤에 온 규칙이 이긴다. */
function valueRules(el, prop, parse) {
  return rulesFor(el)
    .map((r) => ({ cond: r.cond, raw: declaration(r, prop) }))
    .filter((r) => r.raw)
    .map((r) => ({ cond: r.cond, value: parse(r.raw) }));
}
const columnRules = (el) => valueRules(el, "grid-template-columns", columnCount);
const spanRules = (el) => valueRules(el, "grid-column", (raw) => {
  const m = /^span\s+(\d+)$/.exec(raw);
  if (!m) throw new Error(`칸 차지가 span N 이 아니다: ${raw}`);
  return Number(m[1]);
});

/* 실제로 내보낸 CSS 를 그대로 해석해 '이 폭이면 무슨 값' 을 계산한다. 테스트가 임계값을
 * 따로 들고 있으면 CSS 와 어긋나도 초록으로 남는다 — 판정은 CSS 한 곳에서만 나온다.
 *
 * 모르는 조건을 만나면 **건너뛰지 않고 던진다.** 조용히 넘기면 뷰포트 @media 로 되돌려 놨을 때
 * '기본값 1열' 로만 계산돼 이 검사가 초록으로 남는다(되돌려 보고 실제로 그랬다). */
function valueAt(rules, containerPx, rootPx) {
  const base = rules.filter((r) => r.cond === "");
  if (base.length !== 1) throw new Error(`조건 없는 기본값이 ${base.length}개다 — 컨테이너 질의가 아니다`);
  let value = base[0].value;
  for (const r of rules) {
    if (r.cond === "") continue;
    const m = CONTAINER_QUERY.exec(r.cond);
    if (!m) throw new Error(`컨테이너 질의가 아닌 조건이 값을 바꾼다: ${r.cond}`);
    if (Number(m[2]) * rootPx <= containerPx) value = r.value;
  }
  return value;
}

/* 칸 차지를 줄로 흘린다(grid auto-flow row). 줄이 넘치면 다음 줄로 가고, 그때 앞줄이 덜 찼으면 빈틈이다. */
function packRows(spans, columns) {
  const rows = [];
  let row = [];
  let used = 0;
  const holes = [];
  for (const span of spans) {
    if (used + span > columns) {
      if (used < columns) holes.push(rows.length);
      rows.push(row);
      row = [];
      used = 0;
    }
    row.push(span);
    used += span;
  }
  rows.push(row);
  return { rows, holes };
}

/* 격자를 찾는 기준점은 **진행상태**(평범한 TextField)다 — 칸(`[data-form-field]`)의 부모가 격자다. */
async function fieldGrid() {
  const anchor = await waitFor(() => {
    const el = document.getElementById("nt-status");
    if (!el) throw new Error("nt-status 가 아직 없음");
    return el;
  });
  const grid = anchor.closest("[data-form-field]").parentElement;
  return { grid, container: grid.parentElement, cells: [...grid.children].filter((c) => c.hasAttribute("data-form-field")) };
}

const labelOf = (cell) => (cell.firstElementChild ? cell.firstElementChild.textContent : "").replace(/\s*필수$/, "").trim();

describe("새 티켓 — 칸 격자는 컨테이너 폭으로 열 수와 칸 차지를 정한다", () => {
  it("열 수를 바꾸는 규칙이 전부 @container 이고, 뷰포트 @media 는 하나도 관여하지 않는다", async () => {
    renderNewTicket();
    const { grid, container } = await fieldGrid();

    // 컨테이너가 되는 조상이 실제로 선언돼 있어야 @container 가 아무 일도 안 하는 걸 막는다.
    const containerRule = rulesFor(container).find((r) => r.cond === "");
    expect(declaration(containerRule, "container-type")).toBe("inline-size");
    const name = declaration(containerRule, "container-name");
    expect(name).toBeTruthy();

    const rules = columnRules(grid);
    const base = rules.filter((r) => r.cond === "");
    expect(base).toHaveLength(1);
    expect(base[0].value).toBe(1); // 컨테이너 질의를 못 알아듣는 브라우저가 받을 값

    const conditional = rules.filter((r) => r.cond !== "");
    expect(conditional.map((r) => r.value)).toEqual([2, 12]);
    for (const r of conditional) {
      const m = CONTAINER_QUERY.exec(r.cond);
      expect(m, `열 수를 뷰포트 조건으로 바꾸고 있다: ${r.cond}`).not.toBeNull();
      expect(m[1]).toBe(name);
    }
    // 임계값과 열 수가 같이 커져야 valueAt 의 '뒤가 이긴다' 가 뜻이 통한다.
    const thresholds = conditional.map((r) => Number(CONTAINER_QUERY.exec(r.cond)[2]));
    expect([...thresholds].sort((a, b) => a - b)).toEqual(thresholds);
  });

  it("칸 여덟이 표 8 순서로 서고, 칸마다 문턱별 차지가 표 8 과 같다(같은 컨테이너 질의로)", async () => {
    renderNewTicket();
    const { grid, cells } = await fieldGrid();
    expect(cells.map(labelOf)).toEqual(FIELDS.map((f) => f.label));
    const columnConds = columnRules(grid).filter((r) => r.cond !== "").map((r) => r.cond);
    cells.forEach((cell, i) => {
      const rules = spanRules(cell);
      expect(rules.filter((r) => r.cond === "").map((r) => r.value), `${FIELDS[i].label} 기본 차지`).toEqual([1]);
      const conditional = rules.filter((r) => r.cond !== "");
      // 칸 차지의 문턱은 열 수의 문턱과 같은 질의다 — 따로 놀면 2칸 격자에 span 6 이 들어가 칸이 밀린다.
      expect(conditional.map((r) => r.cond), `${FIELDS[i].label} 차지 문턱`).toEqual(columnConds);
      expect(conditional.map((r) => r.value), `${FIELDS[i].label} 차지`).toEqual([FIELDS[i].mid, FIELDS[i].wide]);
    });
  });

  it("실측한 폭마다 CSS 로 계산한 줄 · 칸 폭이 브라우저가 그린 값과 같다", async () => {
    renderNewTicket();
    const { grid, cells } = await fieldGrid();
    const columns = columnRules(grid);
    const spans = cells.map(spanRules);
    const gapRem = Number(/^([\d.]+)rem$/.exec(declaration(rulesFor(grid).find((r) => r.cond === ""), "gap"))[1]);

    const mismatch = [];
    for (const m of MEASURED) {
      const cols = valueAt(columns, m.container, m.root);
      const gap = gapRem * m.root;
      const track = (m.container - (cols - 1) * gap) / cols;
      const { rows } = packRows(spans.map((r) => valueAt(r, m.container, m.root)), cols);
      const widths = rows.map((row) => row.map((span) => Math.round(span * track + (span - 1) * gap)));
      const same = widths.length === m.rows.length
        && widths.every((row, i) => row.length === m.rows[i].length && row.every((w, j) => Math.abs(w - m.rows[i][j]) <= 1));
      if (!same) mismatch.push(`뷰포트 ${m.viewport}: 계산 ${JSON.stringify(widths)} ≠ 실측 ${JSON.stringify(m.rows)}`);
    }
    expect(mismatch).toEqual([]);
  });

  it("어느 폭에서도 줄에 빈틈이 없고, 칸이 하한 밑으로 내려가지 않는다", async () => {
    renderNewTicket();
    const { grid, cells } = await fieldGrid();
    const columns = columnRules(grid);
    const spans = cells.map(spanRules);
    const gapRem = Number(/^([\d.]+)rem$/.exec(declaration(rulesFor(grid).find((r) => r.cond === ""), "gap"))[1]);

    const problems = [];
    const rowCounts = {};
    for (const m of MEASURED) {
      const cols = valueAt(columns, m.container, m.root);
      const gap = gapRem * m.root;
      const track = (m.container - (cols - 1) * gap) / cols;
      const cellSpans = spans.map((r) => valueAt(r, m.container, m.root));
      const { rows, holes } = packRows(cellSpans, cols);
      if (holes.length) problems.push(`뷰포트 ${m.viewport}: ${cols}칸 격자의 줄 ${holes.join(", ")} 에 빈틈`);
      rowCounts[cols] = rows.length;
      cellSpans.forEach((span, i) => {
        const width = span * track + (span - 1) * gap;
        const short = cols === 12 && span < 6;
        const floor = (short ? MIN_SHORT_FIELD_REM : MIN_FIELD_REM) * m.root;
        if (width + 0.5 < floor) {
          problems.push(`뷰포트 ${m.viewport}: ${FIELDS[i].label} ${Math.round(width)}px < ${floor}px`);
        }
      });
    }
    expect(problems).toEqual([]);
    // 표 8 의 줄 수 — 1칸 8줄, 2칸 1 + 3 + 1줄, 12칸 1 + 1 + 1줄.
    expect(rowCounts).toEqual({ 1: 8, 2: 5, 12: 3 });
  });

  it("좁은 칸(레일 옆 502px)은 1칸으로 서고, 1200 은 레일이 폼 아래로 가서 폼이 본문 폭을 받아 12칸이다", async () => {
    renderNewTicket();
    const { grid } = await fieldGrid();
    const rules = columnRules(grid);
    // 예전 뷰포트 격자는 1200 레일 옆 칸에서 한 칸이 223px 로 짜부라졌다 — 폭이 좁으면 1칸이 맞다.
    expect(valueAt(rules, 502, 16)).toBe(1);
    // 바깥 2열이 본문 칸 64rem 문턱이 된 뒤 1200 뷰포트의 폼 격자는 862px 이고 12칸이다(짧은 칸 201px ≥ 187px 하한).
    expect(valueAt(rules, 862, 16)).toBe(12);
    expect(MEASURED.find((m) => m.viewport === 1200).rows[2]).toHaveLength(4);
  });

  /* 오탐 방지 — '전부 1열' 로 만들어 놓고 위 검사를 통과시키는 퇴행을 막는다. */
  it("폭이 남는 화면에서는 여전히 여러 칸으로 편다(1칸으로 뭉개지 않는다)", async () => {
    renderNewTicket();
    const { grid } = await fieldGrid();
    const rules = columnRules(grid);
    expect(valueAt(rules, 605, 16)).toBe(2);    // 뷰포트 1366
    expect(valueAt(rules, 937, 16)).toBe(12);   // 뷰포트 1920
    expect(valueAt(rules, 1440, 20)).toBe(12);  // 뷰포트 3840
  });
});

describe("새 티켓 — 폼과 레일은 그대로다(오탐 방지)", () => {
  /* Q5(카드 높이 편차) 재발 방지. 이 화면은 레일과 폼의 바닥을 stretch 로 맞춰 뒀고,
   * start 로 되돌렸다가 474px 편차로 잡힌 이력이 있다. 격자를 건드리는 김에 같이 지킨다. */
  /* 2026-08-07: 레일 폭이 `22rem` 고정에서 기준 목업 `.grid.two` 의 비율 트랙으로 바뀌었다.
   * 고정 폭은 폭 자체는 채웠지만 넓은 화면에서 레일만 얇은 띠로 남았고, 무엇보다 이 저장소가
   * 화면마다 손으로 정한 폭이 기준선과 어긋나던 자리다. 값은 `ui/density.js` 한 곳에서 온다. */
  it("바깥 2열은 본문 칸 컨테이너 질의로 기준선 two 트랙이 되고 바닥을 stretch 로 맞춘다 — 뷰포트 문턱이 아니다", async () => {
    renderNewTicket();
    const { grid } = await fieldGrid();
    const plate = grid.closest("form").parentElement;
    const outer = plate.parentElement;
    const rules = rulesFor(outer);
    const base = rules.find((r) => r.cond === "");
    expect(declaration(base, "align-items")).toBe("stretch");
    expect(declaration(base, "grid-template-columns")).toBe("minmax(0, 1fr)");
    // 2열로 바꾸는 규칙은 컨테이너 질의 하나뿐이고, 뷰포트 @media 는 트랙을 건드리지 않는다.
    const columnConds = rules.filter((r) => r.cond !== "" && declaration(r, "grid-template-columns"));
    expect(columnConds).toHaveLength(1);
    expect(columnConds[0].cond).toBe("@container content-pair (min-width: 64rem)");
    expect(declaration(columnConds[0], "grid-template-columns")).toBe(BASELINE_TRACKS.two);
    expect(rules.some((r) => /@media/.test(r.cond) && declaration(r, "grid-template-columns"))).toBe(false);
    // 질의가 보는 컨테이너는 격자의 부모다(컨테이너 질의는 자기 자신이 아니라 조상 폭을 본다).
    const containerRule = rulesFor(outer.parentElement).find((r) => r.cond === "");
    expect(declaration(containerRule, "container-type")).toBe("inline-size");
    expect(declaration(containerRule, "container-name")).toBe("content-pair");
  });

  it("두 판은 화면 아래까지 서는 판이고, 폼 판은 세로 흐름에 넘침을 자르지 않는다(따라오는 발이 서야 한다)", async () => {
    renderNewTicket();
    const { grid } = await fieldGrid();
    const plate = grid.closest("form").parentElement;
    const outer = plate.parentElement;
    const plates = [...outer.children];
    expect(plates).toHaveLength(2);
    // 화면 높이는 두 판의 **바닥**이다(`grow`) — 폼이 더 길면 판이 자라고 발이 따라온다. 채팅방 판은 높이 고정이라 값이 없다.
    for (const p of plates) expect(p.getAttribute("data-page-fill")).toBe("grow");
    const cs = getComputedStyle(plate);
    expect(cs.display).toBe("flex");
    expect(cs.flexDirection).toBe("column");
    expect(cs.overflow).toBe("visible");
    const form = grid.closest("form");
    expect(getComputedStyle(form).flexGrow).toBe("1");
    // 바닥 높이는 넓은 화면(md 이상)에서만 건다 — 뷰포트 높이에서 머리 몫을 뺀 값이다.
    const minRule = rulesFor(plate).find((r) => /@media/.test(r.cond) && declaration(r, "min-height"));
    expect(minRule, "판 바닥 높이 규칙이 없다").toBeTruthy();
    // 판 윗변 161px + 본문 열 아래 여백 32px = 193px ≈ 12rem(1920 실측 — 13rem 은 판 아래가 47px 비었다).
    expect(declaration(minRule, "min-height")).toBe("calc(100vh - 12rem)");
    // 레일은 바닥 높이를 따로 걸지 않는다 — 2열에서는 격자 stretch 가 폼 판에 맞추고, 1열(레일이 폼 아래)에서는 내용 높이다.
    const rail = plates.find((p) => p !== plate);
    expect(rail.textContent).toContain("작성 도움");
    expect(rulesFor(rail).some((r) => declaration(r, "min-height"))).toBe(false);
  });

  it("설명 편집기는 상자 하나이고 남는 높이를 채우며, 판 발은 따라오고 오른쪽 끝이 판 여백이다(FAB 여백이 없다)", async () => {
    renderNewTicket();
    await fieldGrid();
    const box = await waitFor(() => {
      const el = document.querySelector("[data-editor-box]");
      if (!el) throw new Error("편집기 상자가 아직 없음");
      return el;
    });
    expect(box.querySelector("[data-editor-toolbar]")).toHaveAttribute("role", "toolbar");
    expect(box.querySelector("[data-editor-toolbar]")).toHaveAttribute("aria-label", "설명 서식");
    expect(box.querySelector("[data-editor-body] .ProseMirror")).toBeTruthy();
    expect(getComputedStyle(box).flexGrow).toBe("1");
    // 되돌리기 · 다시 실행은 도구 줄의 마지막 묶음이다(빈 공간 뒤 오른쪽 끝).
    const tools = [...box.querySelectorAll("[data-editor-toolbar] button")].map((b) => b.getAttribute("aria-label"));
    expect(tools.slice(-2)).toEqual(["되돌리기", "다시 실행"]);

    const footer = document.querySelector('[data-action-footer="card"]');
    expect(footer.hasAttribute("data-action-footer-sticky")).toBe(true);
    expect(getComputedStyle(footer).position).toBe("sticky");
    // 발은 판 가장자리까지 편 면이고 오른쪽 안쪽 여백이 판 여백과 같다 — 걷힌 마스코트 FAB 자리를 비우지 않는다.
    const pr = rulesFor(footer).map((r) => declaration(r, "padding-right")).filter(Boolean);
    expect(pr.length).toBeGreaterThan(0);
    // 판 여백(CARD_PADDING 1.25rem) 한 값뿐이다 — 예전 넓은 화면 규칙은 `calc(1.25rem + 5rem)` 이었다.
    expect(pr.every((v) => v === "1.25rem")).toBe(true);
    expect(screen.getByRole("button", { name: "티켓 추가" }).closest("[data-action-footer]")).toBe(footer);
  });

  it("여덟 칸이 모두 그려지고, 필수를 채워 제출하면 티켓을 만든다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    for (const { label } of FIELDS) {
      /* `getAllByLabelText` + `waitFor` — "마감일"(`DateField`)은 지연 로드라 초기에는
         자리표시만 있고(§15.5), 청크가 온 뒤에는 라벨 하나에 걸리는 요소가 둘(구간 그룹 +
         숨은 입력)이라 단수 `find/getByLabelText` 는 부하가 큰 전량 실행에서 "여럿 걸림"으로
         떨어지거나, `find` 가 잡은 자리표시 참조가 이후 실제 필드로 바뀌며 끊겨 있을 수
         있다 — 매번 새로 질의해 "지금 이 순간 하나 이상 있다"만 본다. */
      await waitFor(() => {
        expect(screen.getAllByLabelText(new RegExp(label)).length).toBeGreaterThan(0);
      });
    }
    await user.type(screen.getByLabelText(/^제목( 필수)?$/), "서버 등록 IP 중복 방지");
    // 프로젝트는 후보가 있으면 필수다 — 고르지 않으면 제출이 막힌다(그 검증도 함께 지킨다).
    await user.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await user.click(await screen.findByRole("option", { name: "인프라" }));
    /* 예상 WD 와 마감일도 필수다 (지시 10) — 서버가 같은 요구를 한다(`TicketCreate`). */
    await user.type(screen.getByLabelText(/예상 WD/), "2");
    await fillDateField(user, /마감일/, "2026-09-30");
    await user.click(screen.getByRole("button", { name: "티켓 추가" }));
    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith("/api/tickets", expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          title: "서버 등록 IP 중복 방지", est_wd: 2, due_date: "2026-09-30",
        }),
      }));
    });
  });

  it("🔴 예상 WD 나 마감일이 비면 **보내지 않는다** — 서버까지 다녀와 422 를 보이지 않는다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await user.type(await screen.findByLabelText(/^제목( 필수)?$/), "예상 WD 없는 티켓");
    await user.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await user.click(await screen.findByRole("option", { name: "인프라" }));
    /* 재는 것은 **안 보냈다**이다. 문구가 아니라 요청을 본다 — 문구는 아래 칸 오류 시험이 잰다. */
    await user.click(screen.getByRole("button", { name: "티켓 추가" }));
    expect(apiMock).not.toHaveBeenCalledWith("/api/tickets", expect.anything());

    // 예상 WD 만 채워도 아직 안 보낸다 — 마감일이 남았다.
    await user.type(screen.getByLabelText(/예상 WD/), "3");
    await user.click(screen.getByRole("button", { name: "티켓 추가" }));
    expect(apiMock).not.toHaveBeenCalledWith("/api/tickets", expect.anything());

    // 둘 다 채우면 그때 나간다.
    await fillDateField(user, /마감일/, "2026-10-01");
    await user.click(screen.getByRole("button", { name: "티켓 추가" }));
    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith("/api/tickets", expect.objectContaining({
        body: expect.objectContaining({ est_wd: 3, due_date: "2026-10-01" }),
      }));
    });
  });
});

describe("새 티켓 — 칸 이름 · 도움말 · 오류는 칸의 세 줄에 선다(핸드오프 계획 C)", () => {
  it("노치 라벨이 없고, 입력은 칸 위 이름과 칸 밖 도움말 줄을 가리킨다", async () => {
    renderNewTicket();
    const { grid } = await fieldGrid();
    expect(grid.querySelectorAll(".MuiInputLabel-root")).toHaveLength(0);

    expect(screen.getByLabelText(/^제목( 필수)?$/)).toHaveAttribute("aria-describedby", "nt-title-help");
    const project = screen.getByRole("combobox", { name: /프로젝트/ });
    expect(project).toHaveAttribute("aria-labelledby", "nt-proj-label");
    expect(project).toHaveAttribute("aria-describedby", "nt-proj-help");

    const wd = screen.getByLabelText(/예상 WD/);
    expect(wd).toHaveAttribute("aria-describedby", "nt-wd-help");
    expect(document.getElementById("nt-wd-help")).toHaveTextContent("사람 한 명이 며칠 동안 할 일인지 입력합니다. 0도 입력할 수 있습니다.");

    // 날짜 조각 묶음 — 낭독기가 실제로 들어가는 자리에도 이름과 도움말 줄이 이어진다.
    await waitFor(() => {
      const group = document.querySelector('#nt-due-help').parentElement.querySelector('[role="group"]');
      expect(group).toBeTruthy();
      expect(group).toHaveAttribute("aria-labelledby", "nt-due-label");
      expect(group).toHaveAttribute("aria-describedby", "nt-due-help");
    });

    // 담당자는 프로젝트를 고르기 전에는 꺼진 고르개이고, 이유는 칸 밖 도움말이 말한다(예전 문장 그대로).
    const assignee = screen.getByRole("combobox", { name: /담당자/ });
    expect(assignee).toBeDisabled();
    expect(assignee).toHaveAttribute("aria-describedby", "nt-assignee-help");
    expect(document.getElementById("nt-assignee-help"))
      .toHaveTextContent("프로젝트를 먼저 고르세요. 그 프로젝트에 접근할 수 있는 사람만 담당자가 될 수 있습니다.");
  });

  it("검증에 걸리면 그 칸 아래 오류 줄이 서고 포커스가 그 칸으로 가며, 칸을 고치면 걷힌다(토스트였다)", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    const title = await screen.findByLabelText(/^제목( 필수)?$/);
    /* 공백만 친 제목 — 입력의 `required` 는 통과하지만 화면 검사(`trim`)에서 걸린다. 나머지 필수는 채운다. */
    await user.type(title, "   ");
    await user.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await user.click(await screen.findByRole("option", { name: "인프라" }));
    await user.type(screen.getByLabelText(/예상 WD/), "1");
    await fillDateField(user, /마감일/, "2026-09-30");
    await user.click(screen.getByRole("button", { name: "티켓 추가" }));

    const help = document.getElementById("nt-title-help");
    await waitFor(() => expect(help.querySelector('[role="alert"]')).toHaveTextContent("제목을 입력하세요."));
    expect(title).toHaveFocus();
    expect(title).toHaveAttribute("aria-invalid", "true");
    expect(apiMock).not.toHaveBeenCalledWith("/api/tickets", expect.anything());

    await user.type(title, "고친 제목");
    await waitFor(() => expect(help.querySelector('[role="alert"]')).toBeNull());
    expect(title).toHaveAttribute("aria-invalid", "false");
  });

  it("저장이 실패하면 발 바로 위 메시지 박스가 말하고, 다시 보내면 걷힌다", async () => {
    const user = userEvent.setup();
    let calls = 0;
    let release;
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/tickets/projects") return Promise.resolve({ projects: [{ id: "p-1", name: "인프라" }] });
      if (path === "/api/tickets/meta") return Promise.resolve({ statuses: ["계획"], priorities: [], difficulties: [] });
      if (String(path).startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
      if (path === "/api/tickets" && opts && opts.method === "POST") {
        calls += 1;
        if (calls === 1) return Promise.reject(new Error("이 프로젝트에는 지금 티켓을 만들 수 없습니다."));
        return new Promise((resolve) => { release = () => resolve({ id: "t-10" }); });
      }
      return Promise.resolve({});
    });
    renderNewTicket();
    await user.type(await screen.findByLabelText(/^제목( 필수)?$/), "실패하는 티켓");
    await user.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await user.click(await screen.findByRole("option", { name: "인프라" }));
    await user.type(screen.getByLabelText(/예상 WD/), "1");
    await fillDateField(user, /마감일/, "2026-09-30");
    await user.click(screen.getByRole("button", { name: "티켓 추가" }));

    const message = await screen.findByText("이 프로젝트에는 지금 티켓을 만들 수 없습니다.");
    const footer = document.querySelector('[data-action-footer="card"]');
    expect(footer).toBeTruthy();
    // 상자는 발보다 앞(위)에 선다 — 발 안이나 페이지 머리로 가지 않는다.
    expect(message.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(footer.contains(message)).toBe(false);

    await user.click(screen.getByRole("button", { name: "티켓 추가" }));
    await waitFor(() => expect(screen.queryByText("이 프로젝트에는 지금 티켓을 만들 수 없습니다.")).toBeNull());
    release();
  });
});
