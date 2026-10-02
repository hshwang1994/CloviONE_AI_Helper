"""공통 부품의 **조합**을 실브라우저에서 잰다 (UI 3차 · 조합 계약 C-1 ~ C-7).

`kit_measure.py` 의 검사는 부품 **낱개의 치수**를 본다(칸 34 · 검색 320 · 머리 40 · 발 주인 하나).
그 검사가 전부 초록이어도 화면은 틀릴 수 있다 — 칩과 결과 줄이 필터 면 **밖**에 두 줄로 서고,
표가 여백 20 판 안에 한 번 더 들어가 머리가 판 가장자리에서 떨어지고, 발이 표 밖 가운데에 선다.
치수는 맞는데 **관계**가 틀린 상태다. 이 모듈은 그 관계를 잰다.

    filter_composition   조건 칩 · 결과 · 지우기가 필터 면 안 둘째 줄(조건 줄)에만 있는가,
                         조건 수 = 칩 수인가, 아래 실선이 있는가, 한 줄에 설 자리가 있는데 검색 혼자 줄을 쓰지 않는가
    filter_cell_anatomy  칸 종류가 달라도 접두 이름 들여쓰기 · 접두-값 간격 · 세로 중심 · 값 굵기가 같은가,
                         다중 선택이 칸 안에 칩을 그려 높이를 풀지 않는가, 칸 폭이 종류 표를 따르는가
                         (wide Entity 칸은 필터 면의 폭이 고른 계단인가). 문맥 줄(`[data-context-bar]` — 작업 보드 ·
                         스프린트 회의의 팀 · 회차)의 칸도 같은 칸이라 함께 잰다
    list_surface         주 목록이 목록 판(surface)인가, 머리 줄이 판 윗변 · 좌우 가장자리에 붙는가,
                         발이 판 안 마지막 줄인가, sticky 발 안에 무한 스크롤 센티널이 없는가
    list_wrapper         표마다 판 계약 표식이 있는가, 목록 판을 여백 판이 한 번 더 감싸지 않는가
    primary_budget       모달 밖 화면의 채움 단추가 하나 이하인가(입력 영역 · 카드 발 · 선택 발은 자기 몫), 행 안 채움 0
    row_actions          행 안 단추가 30 이고 칸마다 둘 이하인가
    table_head_glyph     머리 칸의 정렬 · 필터 표지가 16 이하이고 이름 옆 6 이내에 붙는가(표 머리 `thead th` 와 격자 머리
                         `[role=columnheader]` — 작업 보드 백로그)
    footer_alignment     카드 발의 끝 단추 오른쪽이 판 여백(20)에 맞는가
    editor_box           편집기가 상자 하나(도구 줄 함몰면 + 아래 선 · 도구 30 · 다시 실행 오른쪽 끝 · 본문 240 이상)인가
    page_fill            화면 아래까지 서야 하는 판이 화면 아래까지 서는가
    chat_composition     대화 로그가 위 정렬인가, 날짜선 폭 28rem 이하, 방 머리 두 줄, 입력 상자가 도킹 선 안에 있는가,
                         목록 시각이 긴 절대 형식이 아닌가
    table_empty_band     빈 표가 머리 아래 한 줄 띠인가(높이 56 ~ 72, 그림 없음)
    column_balance       열 배분(D-529) — 필수 열이 숨지 않았는가, 숨길 수 있는 열이 남았는데 표가 상자보다 넓지 않은가, 한 열이
                         남는 폭을 혼자 먹지 않는가(다른 늘어나는 열이 상한 전인데 62% 초과), 늘어나는 열에 120px 넘게 여유가 있는데
                         다른 칸이 말줄임되지 않는가, 값 길이로 폭을 정한 열(상태 · 종류 · 코드)이 말줄임되지 않는가
    control_row          같은 줄에 선 컨트롤(단추 · 아이콘 단추 · 입력 · 선택 · 세그먼티드)의 높이와 윗선이 같은가(D-526 — 한 줄은 한
                         밀도다). 깊이 제한이 없고 종류를 넘는다. 「줄」은 두 컨트롤의 가장 가까운 공통 조상이 가로 배치이고 그 높이가
                         컨트롤 넷을 넘지 않는 상자다 — 화면 격자에서 우연히 같은 높이에 선 것은 같은 줄이 아니다

## 판정 규율

- 표본 수(`checked`)를 같이 적는다. 표본 0 은 통과가 아니라 미실행이다.
- 새 표식(`data-condition-chip` · `data-table-placement` · `data-editor-box` …)이 없는 옛 화면도
  같은 기준으로 잰다 — 표식이 없으면 기하와 문구로 찾아 **실패로** 센다. 그래야 「현재 제품에서
  실패함」을 이 잣대로 먼저 기록할 수 있다.
- 화면마다 기대가 다른 것(목록 판이어야 하는 화면, 편집기 상자가 있어야 하는 화면)은 `ROUTE_EXPECT`
  가 말한다. 기대가 없는 화면에서 그 표식이 없다고 실패시키지 않는다.
- `selftest_html()` 의 맞는 견본은 하나도 걸리면 안 되고 틀린 견본은 `SELFTEST_EXPECT_BAD` 만큼 걸려야 한다.
"""

from __future__ import annotations

COMPOSITION_CHECKS = (
    "filter_composition", "filter_cell_anatomy", "list_surface", "list_wrapper",
    "primary_budget", "row_actions", "table_head_glyph", "footer_alignment",
    "editor_box", "page_fill", "chat_composition", "table_empty_band",
    "column_balance", "control_row",
)

# 조합 계약의 값. 여기 숫자를 바꾸는 것은 계약을 바꾸는 일이다(`docs/DECISIONS.md` D-488 ~ D-494).
COMPOSITION_CONTRACT = {
    "filterCell": 34,
    "prefixInset": 14,
    "prefixGap": 6,
    # 줄 칸 폭(rem). 늘어나지 않는다 — 최솟값 = 최댓값인 종류는 고정 폭이다.
    # `entityWide` 는 `data-filter-size="wide"` 인 Entity 칸이다(프로젝트 · 부서와 팀의 경로 · 회차 · 문서 공간 · 연결된 스케줄).
    # 범위 안의 어느 값이 맞는지는 아래 계단이 정한다.
    "rowKind": {
        "entity": [13, 13],
        "entityWide": [13, 20],
        "tag": [13, 13],
        # 닫힌 집합은 선택지로 폭을 잰다(D-530) — 8 ~ 16rem(S 8 · M 10 · L 13 · XL 16).
        "enum": [8, 16],
        "text": [11, 24],
        "date": [11, 11],
        "datetime": [18, 18],
        # 「기간」 칸 하나(`PeriodFilter`, D-530).
        "period": [13, 13],
    },
    # 검색 칸 계단 — [필터 면 내용 폭 rem 이상, 칸 폭 rem], 큰 계단부터. 어느 계단에도 못 미치면 제 줄 전체다(D-530).
    # 프런트 `FilterBar.jsx::SEARCH_SLOT_STEPS` 와 같은 수다(`test_composition_scan.py` 가 대조한다).
    "searchSlotSteps": [[64, 20], [44, 16]],
    # 표 안 빈 띠의 높이(px, 루트 16 기준) — 한 줄이면 56, 도움말이 접혀도 72 를 넘지 않는다(D-530).
    "emptyBand": [56, 72],
    # wide Entity 칸의 계단 — [필터 면 내용 폭 rem 이상, 칸 폭 rem], 큰 계단부터. 어느 계단에도 못 미치면 `rowKind` 바닥(13)이다.
    # 프런트 `filters.jsx::ROW_KIND.entityWide` 의 컨테이너 질의와 같은 수다(`test_composition_scan.py` 가 대조한다).
    "entityWideSteps": [[96, 20], [76, 16]],
    "rowAction": 30,
    "rowActionsPerCell": 2,
    "headGlyphMax": 16,
    "headGlyphGap": 6,
    "cardPadding": 20,
    "editorBodyMin": 240,
    "editorTool": 30,
    "listFooterMin": 44,
    "chatDateMaxRem": 28,
    # 열 배분(D-529): 한 열이 남는 폭에서 가져가도 되는 몫의 상한(비중 3 : 2 의 60% + 반올림 여유), 「여유 있는 열」의 문턱(px).
    "monopolyShare": 0.62,
    "slackPx": 120,
    # 같은 줄 컨트롤(D-526): 높이 · 윗선 허용 오차(px), 「줄」 상자 높이 상한(컨트롤 높이의 배수).
    "rowTol": 1.5,
    "rowBoxFactor": 4,
    "tol": 1,
}

# 화면마다 **있어야 하는 조합**. 키는 `scripts/ui_qa/routes.py` 의 route id 다.
#   listSurface  주 목록이 목록 판(`DataTable placement="surface"`)이어야 한다
#   editorBox    편집기 상자가 있어야 한다
#   pageFill     화면 아래까지 서는 판이 있어야 한다
#   chat         대화 로그가 있어야 한다
#   skipBudget   채움 단추 수를 세지 않는다(갤러리는 견본을 나란히 세우는 카탈로그다)
#   filterExempt 필터 줄 조합 검사를 하지 않는다(대장 예외 — 제출형 검색 · 달력 도구 줄). 칸 해부는 잰다
#   footerExempt 목록 판 밖 `ListFooter` 를 허용한다(대장 예외 — 끌어 옮기는 백로그 · 날짜 묶음 목록)
# 작업 보드 · 스프린트 회의는 예전에 칸 폭 면제(호출부 폭)와 필터 줄 면제를 받았다(D-484 ② 두 줄 필터). 이제 필터 바와
# 문맥 줄 부품을 써서 둘 다 없다(D-497).
ROUTE_EXPECT: dict[str, dict] = {
    "user_my-tickets": {"listSurface": True},
    "user_unassigned": {"listSurface": True},
    "user_team-tickets": {"listSurface": True},
    "user_knowledge": {"listSurface": True},
    "user_board": {"listSurface": True},
    "user_ideas": {"listSurface": True},
    "user_projects": {"listSurface": True},
    "user_team-docs-trash": {"listSurface": True},
    "user_my-approvals": {"listSurface": True},
    "admin_users": {"listSurface": True},
    "admin_audit": {"listSurface": True},
    "admin_jobs": {"listSurface": True},
    "admin_offboarding": {"listSurface": True},
    "admin_settings": {"listSurface": True},
    # 내 활동은 표가 아니라 날짜 묶음 목록이라 끝 줄이 목록 판 밖이다(대장 조합 예외).
    "user_activity": {"footerExempt": True},
    "user_new-ticket": {"editorBox": True, "pageFill": True},
    "user_chat-rooms": {"chat": True, "pageFill": True},
    "user_chat-room-detail": {"chat": True, "pageFill": True},
    "user_kit": {"skipBudget": True},
    # 작업 보드 백로그는 표가 아니라 끌어 옮기는 가상 목록이라 끝 줄이 목록 판 밖이다(대장 조합 예외).
    "user_work-board": {"footerExempt": True},
    "user_search": {"filterExempt": True},
    # 결과가 선 통합 검색도 같은 화면이다(`Search.jsx` — 대장 조합 예외: 제출형 검색 줄 + 결과 요약 문장).
    "user_search-results": {"filterExempt": True},
    "admin_schedules": {"filterExempt": True},
}


def expect_for(route_id: str) -> dict:
    return dict(ROUTE_EXPECT.get(route_id, {}))


COMPOSITION_JS = r"""
(C) => {
  const scope = C.scope ? document.querySelector(C.scope) : null;
  if (C.scope && !scope) return { error: 'scope not found: ' + C.scope };
  const E = C.expect || {};
  const tol = C.tol;
  const out = {};
  const check = (name) => (out[name] = out[name] || { checked: 0, bad: [] });
  const fail = (name, sample) => { const c = check(name); if (c.bad.length < 12) c.bad.push(sample); c.failed = (c.failed || 0) + 1; };
  const shown = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  };
  const root = scope || document.querySelector('#main-content') || document.body;
  const all = (sel, base) => [...(base || root).querySelectorAll(sel)].filter(shown);
  const rect = (el) => el.getBoundingClientRect();
  const px = (v) => parseFloat(v) || 0;
  const near = (a, b, t) => Math.abs(a - b) <= (t == null ? tol : t);
  const text = (el) => ((el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '')
    .replace(/\s+/g, ' ').trim()).slice(0, 40);
  const where = (el) => { const r = rect(el); return { text: text(el), x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
  const transparent = (c) => !c || c === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(c);
  const inOverlay = (el) => !!el.closest('.MuiDialog-root, .MuiDrawer-root, .MuiPopover-root, .MuiMenu-root, [role=tooltip]');
  const inShell = (el) => !!el.closest('.MuiAppBar-root, #app-sidebar, nav');
  const rootPx = px(getComputedStyle(document.documentElement).fontSize) || 16;
  /* 계약값 가운데 제품이 rem 으로 그리는 치수(판 여백 · 칸 34 · 행 단추 30 · 머리 표지 16 · 목록 발 44 · 편집기 도구 30 · 본문 240)는 루트 글자
     크기를 따라 자란다 — 2200px 이상에서 루트가 18 · 20px 이면 판 여백은 22.5 · 25px 다(`styles/root.css`). 계약 숫자는 루트 16px 의
     값이라 그 비율로 잰다. 간격 · 들여쓰기(MUI spacing px)는 자라지 않으므로 그대로 둔다. */
  const R = rootPx / 16;
  const toHex = (c) => {
    const m = String(c || '').match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/);
    if (!m) return String(c || '').trim().toLowerCase();
    return '#' + [m[1], m[2], m[3]].map((n) => Number(n).toString(16).padStart(2, '0')).join('');
  };
  const primaryHex = String(getComputedStyle(document.documentElement).getPropertyValue('--color-primary') || '').trim().toLowerCase();

  // ── 필터 조합 ────────────────────────────────────────────────────────────
  const surfaces = E.filterExempt ? [] : all('[data-filter-surface]');
  for (const s of surfaces) {
    check('filter_composition').checked++;
    const problems = [];
    // (1) 조건 칩 · 결과 줄 · 지우기는 면 **안** 조건 줄에만 선다. 면 밖 형제로 서면 실패다.
    let sib = s.nextElementSibling;
    for (let hops = 0; sib && hops < 4; hops++, sib = sib.nextElementSibling) {
      if (!shown(sib)) continue;
      /* 목록 자리(표 · 목록 판 · 빈 상태 · 오류)에 닿으면 멈춘다 — 조건 0건 빈 상태의 「지우기」는 빈 상태의 동작이다(RULES §1). */
      if (sib.matches('table, [data-table-placement], [data-list-surface], .MuiTableContainer-root, .MuiCard-root, .k-empty, [data-empty-layout], [data-error-layout]')
        || sib.querySelector('table, [data-list-surface], .k-empty, [data-empty-layout], [data-error-layout]')) break;
      const chips = sib.querySelectorAll('.MuiChip-root, [data-condition-chip]').length;
      const result = sib.matches('[data-result-line], [data-condition-line]') || !!sib.querySelector('[data-result-line], [data-condition-line]');
      const clear = [...sib.querySelectorAll('button')].some((b) => shown(b) && /초기화|지우기/.test(b.textContent || ''));
      if (result) problems.push('면 밖 결과 줄: ' + text(sib));
      else if (chips) problems.push('면 밖 조건 칩 ' + chips);
      else if (clear) problems.push('면 밖 지우기');
    }
    // (2) 줄 끝 동작 묶음의 지우기 — 지우기는 조건 줄의 것이다.
    for (const a of all('[data-filter-actions]', s)) {
      if ([...a.querySelectorAll('button')].some((b) => shown(b) && /초기화|지우기/.test(b.textContent || ''))) problems.push('줄 끝 지우기(조건 줄 밖)');
    }
    // (3) 조건 줄 — 위 실선, 조건 수 = 칩 수, 면 안 마지막 줄.
    const lines = all('[data-condition-line]', s);
    for (const l of lines) {
      if (!(px(getComputedStyle(l).borderTopWidth) >= 1)) problems.push('조건 줄 위 실선 없음');
      const chipsIn = l.querySelectorAll('[data-condition-chip], .MuiChip-root').length;
      const m = (l.innerText || '').match(/조건\s*([\d,]+)\s*개/);
      if (m && Number(m[1].replace(/,/g, '')) !== chipsIn) problems.push('조건 ' + m[1] + '개 ≠ 칩 ' + chipsIn);
      const kids = [...s.children].filter(shown);
      const last = kids[kids.length - 1];
      if (last && last !== l && !last.contains(l)) problems.push('조건 줄이 면의 마지막 줄이 아님');
    }
    // (4) 조건 줄 밖에 선 조건 칩(칸 안 칩은 칸 해부 검사가 센다).
    const loose = all('.MuiChip-root, [data-condition-chip]', s).filter((c) => !c.closest('[data-condition-line]') && !c.closest('.MuiInputBase-root, .MuiAutocomplete-root'));
    if (loose.length) problems.push('조건 줄 밖 칩 ' + loose.length);
    // (5) 목록과 가르는 아래 실선. 서랍 안 면은 선을 긋지 않는다.
    if (!inOverlay(s) && !(px(getComputedStyle(s).borderBottomWidth) >= 1)) problems.push('아래 실선 없음');
    // (6) 한 줄에 설 자리가 있는데 검색(과 오른쪽 끝 묶음)만 한 줄을 쓴다.
    const sr = rect(s);
    const items = [];
    for (const row of all('[data-search-slot], [data-filter-row]', s)) {
      if (row.closest('[data-condition-line]')) continue;
      for (const k of row.children) if (shown(k) && !k.matches('[data-search-slot], [data-filter-row]')) items.push(k);
    }
    const vlines = [];
    for (const k of items) {
      const r = rect(k);
      const line = vlines.find((v) => Math.min(v.bottom, r.bottom) - Math.max(v.top, r.top) > Math.min(v.bottom - v.top, r.height) * 0.5);
      if (line) { line.items.push(k); line.top = Math.min(line.top, r.top); line.bottom = Math.max(line.bottom, r.bottom); }
      else vlines.push({ items: [k], top: r.top, bottom: r.bottom });
    }
    vlines.sort((a, b) => a.top - b.top);
    for (let i = 0; i + 1 < vlines.length; i++) {
      const v = vlines[i];
      const sorted = [...v.items].sort((a, b) => rect(a).left - rect(b).left);
      const search = sorted.find((k) => k.getAttribute('data-filter-kind') === 'search');
      if (!search) continue;
      const lastEl = sorted[sorted.length - 1];
      const endGroup = sorted.length > 1 && near(rect(lastEl).right, sr.right, 2) && rect(lastEl).left - rect(sorted[sorted.length - 2]).right > 24 ? lastEl : null;
      const content = sorted.filter((k) => k !== search && k !== endGroup);
      if (content.length) continue;
      const limit = endGroup ? rect(endGroup).left - 12 : sr.right;
      const free = limit - rect(search).right - 12;
      const nextFirst = [...vlines[i + 1].items].sort((a, b) => rect(a).left - rect(b).left)[0];
      if (nextFirst && rect(nextFirst).width <= free + tol) {
        problems.push('검색 줄에 자리가 있는데 필터가 다음 줄(' + Math.round(free) + 'px 비어 있음)');
        break;
      }
    }
    // (7) 검색 칸 계단(D-530) — 면 내용 폭 64rem 이상 20rem · 44 ~ 64rem 16rem · 그보다 좁으면 제 줄 전체. 검색은 남는 폭을 먹지 않는다.
    if (!E.callerWidths) {
      const sbox = all('[data-search-slot] > [data-filter-kind="search"]', s)[0];
      if (sbox) {
        const scs = getComputedStyle(s);
        const inner = (s.clientWidth - px(scs.paddingLeft) - px(scs.paddingRight)) / rootPx;
        const step = C.searchSlotSteps.find(([min]) => inner >= min);
        const rowW = rect(sbox.parentElement).width;
        const want = Math.min(step ? step[1] * rootPx : rowW, rowW);
        const got = rect(sbox).width;
        if (!near(got, want, 1.5)) problems.push('검색 칸 폭 ' + Math.round(got) + 'px(면 ' + inner.toFixed(1) + 'rem, 기대 ' + Math.round(want) + ')');
      }
    }
    if (problems.length) fail('filter_composition', { ...where(s), problems: problems.slice(0, 6) });
  }

  // ── 필터 칸 해부 ─────────────────────────────────────────────────────────
  out.filter_cell_kinds = {};
  /* 칸 해부는 조합 예외 화면(통합 검색 · 달력 도구 줄)에서도 잰다 — 예외는 줄의 조합이지 칸 모양이 아니다. 문맥 줄
     (`[data-context-bar]`)의 칸도 필터 칸과 같은 줄 칸이라 같이 잰다 — 그 줄은 필터 면이 아니라 위 조합 검사는 받지 않는다. */
  {
    for (const cell of all('[data-filter-surface] [data-filter-kind], [data-context-bar] [data-filter-kind]')) {
      const kind = cell.getAttribute('data-filter-kind');
      if (kind === 'search' || kind === 'toggle' || kind === 'number' || cell.closest('[data-condition-line]')) continue;
      const box = cell.querySelector('.MuiInputBase-root');
      if (!box || !shown(box)) continue;
      check('filter_cell_anatomy').checked++;
      const problems = [];
      const br = rect(box);
      if (!near(br.height, C.filterCell * R)) problems.push('높이 ' + Math.round(br.height));
      if (box.querySelector('.MuiChip-root')) problems.push('칸 안 칩');
      let prefix = box.querySelector('[data-prefix-label]');
      if (!prefix) {
        /* 표식이 없는 옛 칸 — 칸 안 이름은 칸의 **첫 글자 조각**이다(셀렉트는 값 줄의 첫 span,
           자동완성 · 자유 입력은 앞 장식의 span). 칩 안 글자는 이름이 아니다. */
        prefix = [...box.querySelectorAll('span')].find((el) => el.children.length === 0 && shown(el) && (el.textContent || '').replace(/\u200b/g, '').trim() && !el.closest('.MuiChip-root'));
      }
      let valueInfo = null;
      if (prefix) {
        let value = box.querySelector('[data-row-value]');
        if (!value || !shown(value)) {
          const sibVal = prefix.nextElementSibling;
          value = sibVal && shown(sibVal) && (sibVal.textContent || '').trim() ? sibVal : null;
        }
        if (value) {
          const vs = getComputedStyle(value);
          valueInfo = { r: rect(value), weight: vs.fontWeight, opacity: px(vs.opacity || '1') };
        } else {
          const input = [...box.querySelectorAll('input')].find((i) => shown(i) && i.type !== 'hidden' && !i.classList.contains('MuiSelect-nativeInput'));
          if (input) {
            const is = getComputedStyle(input);
            const r = rect(input);
            const ph = getComputedStyle(input, '::placeholder');
            valueInfo = {
              r: { left: r.left + px(is.paddingLeft), top: r.top, height: r.height, right: r.right },
              weight: is.fontWeight,
              opacity: input.value ? 1 : px(ph.opacity || '1'),
            };
          }
        }
        const pr = rect(prefix);
        const inset = pr.left - br.left;
        const rec = out.filter_cell_kinds[kind] = out.filter_cell_kinds[kind] || [];
        if (valueInfo) {
          const gap = valueInfo.r.left - pr.right;
          const centre = (valueInfo.r.top + valueInfo.r.height / 2) - (pr.top + pr.height / 2);
          if (rec.length < 3) rec.push({ inset: Math.round(inset * 10) / 10, gap: Math.round(gap * 10) / 10, centre: Math.round(centre * 10) / 10 });
          if (!near(inset, C.prefixInset, 1)) problems.push('접두 들여쓰기 ' + Math.round(inset));
          if (!near(gap, C.prefixGap, 1)) problems.push('접두-값 간격 ' + Math.round(gap));
          if (Math.abs(centre) > 1.5) problems.push('세로 중심 ' + centre.toFixed(1));
          if (String(valueInfo.weight) !== '600') problems.push('값 굵기 ' + valueInfo.weight);
          if (valueInfo.opacity < 0.99) problems.push('값 흐림 ' + valueInfo.opacity);
        } else problems.push('값 자리 없음');
      } else problems.push('칸 안 접두 이름 없음');
      /* 크기가 있는 종류(Entity)는 `data-filter-size="wide"` 이면 wide 표를 본다. */
      const wideKey = cell.getAttribute('data-filter-size') === 'wide' && C.rowKind[kind + 'Wide'] ? kind + 'Wide' : '';
      const want = C.rowKind[wideKey || kind];
      if (want) {
        const w = rect(cell).width / rootPx;
        if (w < want[0] - 0.07 || w > want[1] + 0.07) problems.push('폭 ' + w.toFixed(2) + 'rem');
        else if (wideKey) {
          /* wide 칸은 **필터 면의 폭**이 계단을 고른다(컨테이너 질의는 면의 내용 상자를 잰다). 범위 안이어도 면에 맞지 않는
             계단이면 실패다 — 컨테이너가 안 걸려 1920 에서도 13rem 에 머무는 칸이 이 자리에서 잡힌다. 문맥 줄의 칸은 그 줄이
             같은 이름의 크기 컨테이너다. */
          const surface = cell.closest('[data-filter-surface], [data-context-bar]');
          const ss = getComputedStyle(surface);
          const inner = (rect(surface).width - px(ss.paddingLeft) - px(ss.paddingRight)
            - px(ss.borderLeftWidth) - px(ss.borderRightWidth)) / rootPx;
          const step = (C.entityWideSteps || []).find((s) => inner >= s[0] - 0.01);
          const stepRem = step ? step[1] : want[0];
          if (Math.abs(w - stepRem) > 0.07) problems.push('wide 계단 ' + w.toFixed(2) + 'rem, 면 ' + inner.toFixed(1) + 'rem 이면 ' + stepRem + 'rem');
        }
      }
      if (problems.length) fail('filter_cell_anatomy', { ...where(cell), kind, problems: problems.slice(0, 6) });
    }
  }

  // ── 목록 판 ──────────────────────────────────────────────────────────────
  const plateOf = (el) => {
    let p = el.parentElement;
    while (p && p !== document.body) {
      const cs = getComputedStyle(p);
      if (!transparent(cs.backgroundColor) && px(cs.borderTopWidth) >= 1 && px(cs.borderTopLeftRadius) >= 4) return p;
      p = p.parentElement;
    }
    return null;
  };
  const tables = all('table.MuiTable-root').filter((t) => !inOverlay(t) && t.querySelector('thead') && t.querySelector('tbody tr'));
  for (const t of tables) {
    check('list_wrapper').checked++;
    const holder = t.closest('[data-table-placement]');
    const placement = holder ? holder.getAttribute('data-table-placement') : '';
    const plate = plateOf(t);
    const pad = plate ? px(getComputedStyle(plate).paddingLeft) : 0;
    if (!placement) { fail('list_wrapper', { ...where(t), problem: '표 판 계약 표식 없음', platePad: Math.round(pad) }); continue; }
    if (placement === 'surface') {
      const outer = holder.matches('[data-list-surface]') ? plateOf(holder) : plate;
      const outerPad = outer ? px(getComputedStyle(outer).paddingLeft) : 0;
      if (outer && outerPad >= 8) fail('list_wrapper', { ...where(t), problem: '목록 판을 여백 판이 한 번 더 감쌈', outerPad: Math.round(outerPad) });
    }
  }
  const listSurfaces = all('[data-list-surface]').filter((s) => !inOverlay(s));
  if (E.listSurface) {
    check('list_surface').checked++;
    const main = tables.slice().sort((a, b) => (rect(b).width * rect(b).height) - (rect(a).width * rect(a).height))[0];
    /* 화면 전체가 빈 상태(`EmptyState layout="page"`)면 목록이 없는 것이 맞다 — 담을 목록이 없는 화면에 판을 요구하지 않는다
       (핸드오프 RULES §1 「화면 전체가 비었다」). */
    const pageEmpty = !!root.querySelector('[data-empty-layout="page"]');
    if (!main && !listSurfaces.length && !pageEmpty) fail('list_surface', { problem: '주 목록을 찾지 못함' });
    else if (main && !main.closest('[data-list-surface]')) {
      const plate = plateOf(main);
      const head = main.querySelector('thead tr');
      fail('list_surface', {
        ...where(main), problem: '주 목록이 목록 판(surface)이 아님',
        headInset: plate && head ? Math.round(rect(head).top - rect(plate).top) : null,
        platePad: plate ? getComputedStyle(plate).paddingTop : null,
      });
    }
  }
  for (const s of listSurfaces) {
    check('list_surface').checked++;
    const problems = [];
    const sr = rect(s);
    const cs = getComputedStyle(s);
    const bw = px(cs.borderTopWidth);
    /* 표가 든 판은 여백 0(머리가 가장자리에 붙는다), 표가 없는 판(불러오는 중 · 빈 목록)은 판 여백 20 안에 선다. */
    const stateOnly = !s.querySelector('table');
    if (stateOnly) {
      if (!near(px(cs.paddingTop), C.cardPadding * R, 1) || !near(px(cs.paddingLeft), C.cardPadding * R, 1)) problems.push('빈 · 불러오는 판 여백 ' + cs.paddingTop + '/' + cs.paddingLeft);
    } else if (px(cs.paddingTop) > 0.5 || px(cs.paddingLeft) > 0.5) problems.push('판 여백 ' + cs.paddingTop + '/' + cs.paddingLeft);
    if (cs.overflowY !== 'visible') problems.push('판 overflow ' + cs.overflowY);
    const head = s.querySelector('thead tr');
    if (head && shown(head)) {
      const box = s.querySelector('.MuiTableContainer-root') || head;
      const hr = rect(head), xr = rect(box);
      if (!near(hr.top, sr.top + bw, 1.5) && window.scrollY < 2) problems.push('머리가 판 윗변에서 ' + Math.round(hr.top - sr.top - bw) + 'px 떨어짐');
      if (!near(xr.left, sr.left + bw, 1.5) || !near(xr.right, sr.right - bw, 1.5)) problems.push('머리 좌우 ' + Math.round(xr.left - sr.left - bw) + '/' + Math.round(sr.right - bw - xr.right));
      const th = head.querySelector('th');
      if (th) {
        const tb = getComputedStyle(th).backgroundColor;
        if (transparent(tb) || tb === cs.backgroundColor) problems.push('머리 면이 함몰면이 아님');
      }
    }
    const foot = s.querySelector('[data-list-footer]');
    if (foot && shown(foot)) {
      const kids = [...s.children].filter(shown);
      if (kids[kids.length - 1] !== foot) problems.push('발이 판의 마지막 줄이 아님');
      if (rect(foot).height < C.listFooterMin * R - tol) problems.push('발 높이 ' + Math.round(rect(foot).height));
      if (getComputedStyle(foot).position === 'sticky') {
        const tiny = [...foot.querySelectorAll('*')].find((el) => { const r = rect(el); return r.width <= 1.5 && r.height <= 1.5 && getComputedStyle(el).display !== 'none'; });
        if (tiny) problems.push('sticky 발 안에 무한 스크롤 센티널');
      }
    }
    if (problems.length) fail('list_surface', { ...where(s), problems: problems.slice(0, 6) });
  }
  if (!E.footerExempt) {
    for (const f of all('[data-list-footer]')) {
      /* 판 안 보조 표(`placement="card"`)의 발은 그 판의 마지막 줄이다 — 목록 판이 아니어도 판 밖이 아니다. */
      if (inOverlay(f) || f.closest('[data-list-surface], [data-table-placement="card"]')) continue;
      check('list_surface').checked++;
      fail('list_surface', { ...where(f), problem: '목록 발이 판 밖' });
    }
  }

  // ── 표 안 빈 띠 (D-530) ─────────────────────────────────────────────────
  /* 빈 표는 머리 아래 한 줄 띠다 — 높이 56 ~ 72(루트 비례), 그림 없음, 머리가 서 있다. 판을 흰 면으로 채우거나 큰 그림을 세우면 실패다. */
  for (const band of all('[data-empty-band]')) {
    if (inOverlay(band)) continue;
    check('table_empty_band').checked++;
    const problems = [];
    const h = rect(band).height;
    if (h < C.emptyBand[0] * R - 1 || h > C.emptyBand[1] * R + 1) problems.push('높이 ' + Math.round(h));
    if (band.querySelector('img')) problems.push('그림');
    const tbl = band.closest('table');
    const head = tbl && tbl.querySelector('thead tr');
    if (!head || !shown(head)) problems.push('머리 없음');
    if (problems.length) fail('table_empty_band', { ...where(band), problems });
  }

  // ── 채움 단추 수 ─────────────────────────────────────────────────────────
  if (!E.skipBudget) {
    const filled = [
      ...all('.MuiButton-containedPrimary, .MuiButton-containedError'),
      ...all('.MuiIconButton-root').filter((b) => primaryHex && toHex(getComputedStyle(b).backgroundColor) === primaryHex),
    ].filter((b) => !inOverlay(b) && !inShell(b));
    check('primary_budget').checked++;
    const scopeOf = (b) => b.closest('[data-form-scope], [data-action-footer], [data-list-selection]');
    const loose = filled.filter((b) => !scopeOf(b));
    if (loose.length > 1) fail('primary_budget', { problem: '화면 채움 ' + loose.length, buttons: loose.slice(0, 5).map(text) });
    const inRows = filled.filter((b) => b.closest('tbody'));
    if (inRows.length) fail('primary_budget', { problem: '행 안 채움 ' + inRows.length, buttons: inRows.slice(0, 3).map(text) });
    const perScope = new Map();
    for (const b of filled) { const sc = scopeOf(b); if (sc) perScope.set(sc, (perScope.get(sc) || 0) + 1); }
    for (const [sc, n] of perScope) if (n > 1) fail('primary_budget', { problem: '한 영역 채움 ' + n, where: text(sc) });
  }

  // ── 행 동작 ──────────────────────────────────────────────────────────────
  for (const td of all('tbody td')) {
    if (inOverlay(td)) continue;
    /* 행 **동작** 단추만 센다 — 제목 링크 · 값을 바로 고치는 칸(상태 점 + 낱말) · 체크박스는 동작 단추가 아니다. */
    const btns = [...td.querySelectorAll('.MuiButton-root, .MuiIconButton-root, [data-row-actions] button')].filter((b, i, arr) => shown(b) && !b.closest('.MuiChip-root') && arr.indexOf(b) === i);
    if (!btns.length) continue;
    check('row_actions').checked++;
    const bad = btns.filter((b) => !near(rect(b).height, C.rowAction * R, 1));
    if (bad.length) fail('row_actions', { ...where(td), problem: '행 단추 높이', h: [...new Set(bad.map((b) => Math.round(rect(b).height)))] });
    if (btns.length > C.rowActionsPerCell) fail('row_actions', { ...where(td), problem: '한 칸 단추 ' + btns.length });
  }

  // ── 머리 칸 표지 ─────────────────────────────────────────────────────────
  /* 표 머리(`thead th`)와 격자 머리(`[role=columnheader]` — 작업 보드 백로그)가 같은 머리 칸 부품을 쓴다. MUI 표 칸은 역할을
     속성으로 달지 않으므로 둘이 겹치지 않지만, 겹쳐도 한 번만 잰다. */
  for (const th of [...new Set(all('thead th, [role=columnheader]'))]) {
    if (inOverlay(th)) continue;
    const glyphs = [...th.querySelectorAll('svg, [data-head-glyph]')].filter(shown);
    if (!glyphs.length) continue;
    const label = [...th.querySelectorAll('span')].find((sp) => sp.children.length === 0 && (sp.textContent || '').trim().length > 1 && shown(sp));
    check('table_head_glyph').checked++;
    const problems = [];
    /* 표지는 **사슬**로 붙는다 — 이름 → 정렬 표지 → 필터 표지. 둘째 표지의 간격은 이름이 아니라 바로 앞 표지에서 잰다
       (이름에서 재면 정렬 · 필터를 함께 가진 열은 늘 멀다고 나온다). */
    const lr = label ? rect(label) : null;
    let prevRight = lr ? lr.right : null;
    for (const g of glyphs.slice().sort((a, b) => rect(a).left - rect(b).left)) {
      const gr = rect(g);
      if (gr.width > C.headGlyphMax * R + 0.5 || gr.height > C.headGlyphMax * R + 0.5) problems.push('표지 ' + Math.round(gr.width) + 'px');
      if (lr && gr.right <= lr.left) {
        if (lr.left - gr.right > C.headGlyphGap + 0.5) problems.push('이름과 ' + Math.round(lr.left - gr.right) + 'px');
        continue;
      }
      if (prevRight != null) {
        const gap = gr.left - prevRight;
        if (gap > C.headGlyphGap + 0.5) problems.push((prevRight === (lr && lr.right) ? '이름과 ' : '앞 표지와 ') + Math.round(gap) + 'px');
      }
      prevRight = gr.right;
    }
    if (problems.length) fail('table_head_glyph', { text: text(th), problems: [...new Set(problems)].slice(0, 4) });
  }

  // ── 카드 발 끝 단추 ──────────────────────────────────────────────────────
  for (const f of all('[data-action-footer="card"]')) {
    const btns = [...f.querySelectorAll('button')].filter(shown);
    if (!btns.length) continue;
    check('footer_alignment').checked++;
    const last = btns.sort((a, b) => rect(b).right - rect(a).right)[0];
    const gap = rect(f).right - rect(last).right;
    if (!near(gap, C.cardPadding * R, 1)) fail('footer_alignment', { text: text(last), gap: Math.round(gap), want: C.cardPadding * R });
  }

  // ── 편집기 상자 ──────────────────────────────────────────────────────────
  const editors = all('[data-editor-box]');
  if (E.editorBox) {
    check('editor_box').checked++;
    if (!editors.length) {
      const toolbar = all('[aria-label$="서식"]')[0];
      fail('editor_box', { problem: '편집기 상자 없음', toolbar: toolbar ? where(toolbar) : null });
    }
  }
  for (const b of editors) {
    check('editor_box').checked++;
    const problems = [];
    const bs = getComputedStyle(b);
    if (!near(px(bs.borderTopWidth), 1, 0.5)) problems.push('테두리 ' + bs.borderTopWidth);
    const tb = b.querySelector('[data-editor-toolbar]');
    const body = b.querySelector('[data-editor-body]');
    if (!tb || !shown(tb)) problems.push('도구 줄 없음');
    else {
      const ts = getComputedStyle(tb);
      if (transparent(ts.backgroundColor) || ts.backgroundColor === bs.backgroundColor) problems.push('도구 줄이 함몰면이 아님');
      if (!(px(ts.borderBottomWidth) >= 1)) problems.push('도구 줄 아래 선 없음');
      const tools = [...tb.querySelectorAll('button')].filter(shown);
      const off = tools.filter((x) => !near(rect(x).height, C.editorTool * R, 1));
      if (off.length) problems.push('도구 단추 ' + [...new Set(off.map((x) => Math.round(rect(x).height)))].join(','));
      const redo = tb.querySelector('[aria-label="다시 실행"]');
      if (redo && shown(redo) && !near(rect(redo).right, rect(tb).right - px(ts.paddingRight), 2)) problems.push('다시 실행이 오른쪽 끝이 아님');
    }
    if (!body || !shown(body)) problems.push('본문 없음');
    else if (rect(body).height < C.editorBodyMin * R - tol) problems.push('본문 ' + Math.round(rect(body).height));
    if (problems.length) fail('editor_box', { ...where(b), problems });
  }

  // ── 화면 아래까지 서는 판 ────────────────────────────────────────────────
  const fills = all('[data-page-fill]');
  if (E.pageFill) {
    check('page_fill').checked++;
    if (!fills.length) fail('page_fill', { problem: '화면 채움 판 없음' });
  }
  /* 판의 아래 끝과 화면 아래 사이에는 본문 열의 아래 여백(`.c-content` padding-bottom)만 남는다. */
  const column = document.querySelector('.c-content');
  const allowed = (column ? px(getComputedStyle(column).paddingBottom) : 32) + 8;
  for (const f of fills) {
    check('page_fill').checked++;
    const r = rect(f);
    const gap = innerHeight - r.bottom;
    /* 판이 화면보다 **짧아** 아래 캔버스가 비면 실패다. 넘치는 쪽은 판의 종류가 가른다(P4 교정).
       `data-page-fill="grow"` — 화면 높이가 **바닥**인 판(새 티켓 폼)이다. 폼이 더 길면 판이 자라고 페이지가 굴러가며 발이 따라온다(`ActionFooter sticky`).
       그 밖(`data-page-fill=""`) — 화면 높이가 **판 높이**인 판(채팅방)이다. 화면을 넘으면 페이지가 굴러가 입력창이 화면 아래를 벗어난다. */
    const grows = f.getAttribute('data-page-fill') === 'grow';
    if (window.scrollY < 2 && gap > allowed) fail('page_fill', { ...where(f), problem: '판 아래 캔버스가 빔', bottomGap: Math.round(gap), allowed: Math.round(allowed) });
    else if (window.scrollY < 2 && !grows && gap < -1) fail('page_fill', { ...where(f), problem: '높이 고정 판이 화면을 넘음', bottomGap: Math.round(gap) });
  }

  // ── 채팅 조합 ────────────────────────────────────────────────────────────
  const logs = all('[data-chat-log]');
  const logEls = logs.length ? logs : [...new Set(all('[data-chat-row]').map((r) => r.parentElement))].filter(Boolean);
  if (E.chat) {
    check('chat_composition').checked++;
    if (!logEls.length) fail('chat_composition', { problem: '대화 로그를 찾지 못함' });
  }
  for (const log of logEls) {
    if (log.closest('[data-chat-compact]')) continue;
    check('chat_composition').checked++;
    const problems = [];
    let scroller = log;
    for (let i = 0; scroller && i < 4 && !/(auto|scroll)/.test(getComputedStyle(scroller).overflowY); i++) scroller = scroller.parentElement;
    const jc = [getComputedStyle(log).justifyContent, scroller ? getComputedStyle(scroller).justifyContent : ''].join(' ');
    if (/flex-end|end/.test(jc)) problems.push('로그 아래 정렬');
    for (const d of all('[data-day-separator], [data-chat-date]', log)) {
      const w = rect(d).width;
      if (w > C.chatDateMaxRem * rootPx + 1) { problems.push('날짜선 폭 ' + Math.round(w)); break; }
    }
    const composer = all('[data-chat-composer]')[0];
    if (composer) {
      const dock = composer.closest('[data-chat-dock]');
      if (!dock) problems.push('입력 도킹 영역 없음');
      else if (!(px(getComputedStyle(dock).borderTopWidth) >= 1)) problems.push('도킹 위 실선 없음');
    }
    if (problems.length) fail('chat_composition', { problems });
  }
  for (const head of all('[data-room-head]')) {
    const title = head.querySelector('[data-room-head-group="title"]');
    const meta = [...head.querySelectorAll('*')].find((el) => el.children.length === 0 && /참여자\s*\d+\s*명/.test(el.textContent || '') && shown(el));
    if (!title || !meta) continue;
    check('chat_composition').checked++;
    if (rect(meta).top < rect(title).bottom - 2) fail('chat_composition', { problem: '방 머리 한 줄(참여자 요약이 제목 줄에 선다)' });
  }
  for (const list of all('[data-chat-layout] > .MuiCard-root:first-child')) {
    const longStamp = [...list.querySelectorAll('*')].find((el) => el.children.length === 0 && shown(el) && /\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*(오전|오후)/.test(el.textContent || ''));
    check('chat_composition').checked++;
    if (longStamp) fail('chat_composition', { problem: '목록 시각이 긴 절대 형식', text: text(longStamp) });
  }

  // ── 열 배분 (D-529) ──────────────────────────────────────────────────────
  /* 열 배분을 쓰는 표(`col[data-col-key]` — `DataTable` 이 배분 근거를 표식으로 남긴다)만 잰다. 폭 · 바닥 · 상한은 px 다. */
  for (const tbl of all('table')) {
    if (inOverlay(tbl)) continue;
    const cols = [...tbl.querySelectorAll(':scope > colgroup > col[data-col-key]')];
    if (!cols.length) continue;
    check('column_balance').checked++;
    const problems = [];
    const hidden = (tbl.getAttribute('data-hidden-cols') || '').split(',').filter(Boolean).map((s) => s.split(':'));
    const hiddenEssential = hidden.filter((h) => h[1] === 'essential').map((h) => h[0]);
    if (hiddenEssential.length) problems.push('필수 열 숨김 ' + hiddenEssential.join(','));
    const heads = [...tbl.querySelectorAll(':scope > thead > tr:first-child > th')];
    const info = cols.map((col, i) => ({
      key: col.getAttribute('data-col-key'),
      tier: col.getAttribute('data-col-tier') || 'essential',
      kind: col.getAttribute('data-col-kind') || 'fixed',
      content: col.hasAttribute('data-col-content'),
      min: px(col.getAttribute('data-col-min')),
      max: col.hasAttribute('data-col-max') ? px(col.getAttribute('data-col-max')) : null,
      w: heads[i] ? rect(heads[i]).width : 0,
    }));
    const scrolls = tbl.getAttribute('data-plan-scroll') === 'true';
    const box = tbl.parentElement;
    const over = box ? rect(tbl).width - box.clientWidth : 0;
    const hideable = info.filter((c) => c.tier !== 'essential');
    if (over > 2 && hideable.length) problems.push('숨길 수 있는 열이 남았는데 표가 넓음 ' + Math.round(over) + 'px(' + hideable.map((c) => c.key).join(',') + ')');
    const grows = info.filter((c) => c.kind === 'grow');
    const leftover = rect(tbl).width - info.reduce((s, c) => s + c.min, 0);
    if (!scrolls && leftover > 200 && grows.length >= 2) {
      for (const c of grows) {
        const share = (c.w - c.min) / leftover;
        const othersOpen = grows.some((o) => o !== c && o.max != null && o.w < o.max - 2);
        if (share > C.monopolyShare && othersOpen) problems.push('한 열이 남는 폭 독점 ' + c.key + ' ' + Math.round(share * 100) + '%');
      }
    }
    // 말줄임 — 칸 안에서 `text-overflow: ellipsis` 이고 넘치는 자리. 내용 폭은 글자 범위(Range)로 잰다(잘려도 배치 폭은 그대로다).
    const natural = (el) => { try { const r = document.createRange(); r.selectNodeContents(el); return r.getBoundingClientRect().width; } catch (e) { return 0; } };
    const truncated = new Map();
    const need = new Map();
    for (const tr of [...tbl.querySelectorAll(':scope > tbody > tr')].slice(0, 40)) {
      const tds = [...tr.children].filter((el) => el.tagName === 'TD');
      if (tds.length !== info.length) continue;
      tds.forEach((td, i) => {
        const c = info[i];
        const clipped = [td, ...td.querySelectorAll('*')].some((el) => getComputedStyle(el).textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 1);
        if (clipped) truncated.set(c.key, (truncated.get(c.key) || 0) + 1);
        const st = getComputedStyle(td);
        const used = natural(td) + px(st.paddingLeft) + px(st.paddingRight);
        need.set(c.key, Math.max(need.get(c.key) || 0, used));
      });
    }
    if (!scrolls && truncated.size) {
      const roomy = grows.filter((c) => need.has(c.key) && c.w - need.get(c.key) >= C.slackPx);
      for (const [key, n] of truncated) {
        const c = info.find((x) => x.key === key);
        if (c && c.content) problems.push('값 길이 열 말줄임 ' + key + ' ' + n + '칸');
        const other = roomy.filter((r) => r.key !== key);
        if (other.length) problems.push('말줄임 ' + key + ' ' + n + '칸, 옆 열 여유 ' + other.map((r) => r.key + ' ' + Math.round(r.w - need.get(r.key)) + 'px').join(','));
      }
    }
    if (problems.length) fail('column_balance', { ...where(tbl), problems: problems.slice(0, 6) });
  }

  // ── 같은 줄 컨트롤 (D-526) ────────────────────────────────────────────────
  /* 한 줄은 한 밀도다 — 같은 줄의 컨트롤은 높이와 윗선이 같다. 표 칸(행 동작 검사가 잰다) · 떠 있는 층 · 셸 · 여러 줄 입력 · 대화
     입력은 빼고, 다른 컨트롤 안의 것(입력 안 단추 · 세그먼티드 안 칸)은 바깥 상자로 잰다. */
  {
    const CTRL = '.MuiButton-root, .MuiIconButton-root, .MuiInputBase-root, .k-segmented';
    const ctrls = all(CTRL).filter((el) => !inOverlay(el) && !inShell(el)
      && !el.closest('td, th, [data-probe-skip], [data-chat-composer], .MuiChip-root')
      && !(el.parentElement && el.parentElement.closest(CTRL))
      && !el.classList.contains('MuiInputBase-multiline'));
    const nca = (a, b) => { const s = new Set(); for (let q = a; q; q = q.parentElement) s.add(q); for (let q = b; q; q = q.parentElement) if (s.has(q)) return q; return null; };
    const lines = new Map();
    for (let i = 0; i < ctrls.length; i++) {
      const a = ctrls[i], ra = rect(a);
      for (let j = i + 1; j < ctrls.length; j++) {
        const b = ctrls[j], rb = rect(b);
        const overlap = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
        if (overlap < Math.min(ra.height, rb.height) * 0.5) continue;
        if (ra.right > rb.left + 1 && rb.right > ra.left + 1) continue;
        const n = nca(a, b);
        if (!n || n === document.body || n === document.documentElement) continue;
        const st = getComputedStyle(n);
        const rowish = (/flex/.test(st.display) && !/column/.test(st.flexDirection)) || /grid/.test(st.display);
        if (!rowish) continue;
        if (rect(n).height > Math.max(ra.height, rb.height) * C.rowBoxFactor + 4) continue;
        if (!lines.has(n)) lines.set(n, []);
        lines.get(n).push([a, b]);
      }
    }
    /* 한 상자 안에서도 줄은 「서로 겹치는 짝」으로 이어진 묶음이다 — 두 줄로 접힌 필터 줄의 위 줄과 아래 줄은 같은 상자지만 다른
       줄이다(처음 구현은 둘을 한 묶음으로 세어 「윗선 46px」를 냈다: 감사 로그 · 내 티켓 필터 줄). */
    const groups = [];
    for (const [n, pairs] of lines) {
      const parent = new Map();
      const find = (x) => { while (parent.get(x) !== x) x = parent.get(x); return x; };
      for (const [a, b] of pairs) {
        if (!parent.has(a)) parent.set(a, a);
        if (!parent.has(b)) parent.set(b, b);
        parent.set(find(a), find(b));
      }
      const byRoot = new Map();
      for (const el of parent.keys()) { const r = find(el); if (!byRoot.has(r)) byRoot.set(r, []); byRoot.get(r).push(el); }
      for (const els of byRoot.values()) groups.push([n, els]);
    }
    for (const [n, els] of groups) {
      check('control_row').checked++;
      const items = els.map((el) => ({ el, r: rect(el) }));
      const hs = items.map((x) => x.r.height);
      const tops = items.map((x) => x.r.top);
      const problems = [];
      if (Math.max(...hs) - Math.min(...hs) > C.rowTol) problems.push('높이 ' + [...new Set(hs.map((h) => Math.round(h)))].join('/'));
      if (Math.max(...tops) - Math.min(...tops) > C.rowTol) problems.push('윗선 ' + Math.round(Math.max(...tops) - Math.min(...tops)) + 'px');
      if (problems.length) fail('control_row', { ...where(n), problems, controls: items.slice(0, 5).map((x) => text(x.el) + ' ' + Math.round(x.r.height)) });
    }
  }
  return out;
}
"""


def selftest_html() -> str:
    """맞는 견본(`#compose-good`)과 틀린 견본(`#compose-bad`)을 문서에 붙이는 스크립트."""
    return r"""
(() => {
  const box = document.createElement('div');
  box.id = 'compose-selftest';
  box.style.cssText = 'position:absolute;left:0;top:0;width:1200px;background:#fff;z-index:99999;padding:16px;display:grid;gap:16px;font-size:14px';
  const cell = (kind, width, inset, gap, weight, chip, size) => `
    <div data-filter-kind="${kind}"${size ? ` data-filter-size="${size}"` : ''} style="width:${width}px;flex:0 0 auto">
      <div class="MuiInputBase-root" style="display:flex;align-items:center;height:${chip ? 44 : 34}px;padding-left:${inset}px;box-shadow:inset 0 0 0 1px #ccc;box-sizing:border-box">
        <span data-prefix-label="" style="color:#666;white-space:nowrap">상태</span>
        ${chip ? '<span class="MuiChip-root" style="display:inline-flex;height:24px;margin-left:6px">칩</span>' : `<span data-row-value="" style="margin-left:${gap}px;font-weight:${weight}">전체</span>`}
      </div>
    </div>`;
  const table = (placement, surface, pad, footInside, stickyFoot, headGlyph, filled) => `
    <div ${surface ? 'data-list-surface="" ' : ''}data-table-placement="${placement}" style="background:#fff;border:1px solid #dcdfec;border-radius:8px;padding:${pad}px;overflow:visible">
      <div class="MuiTableContainer-root" style="overflow-x:auto">
        <table class="MuiTable-root" style="width:100%;border-collapse:collapse">
          <thead><tr style="height:40px"><th style="background:#f5f6fb;text-align:start"><span>제목</span>${headGlyph}</th><th style="background:#f5f6fb">상태</th></tr></thead>
          <tbody><tr style="height:48px"><td>문서</td><td><button class="MuiButton-root" style="height:30px">보기</button>${filled ? '<button class="MuiButton-root MuiButton-containedPrimary" style="height:30px">배정</button><button class="MuiIconButton-root" style="height:30px">셋째</button>' : ''}</td></tr></tbody>
        </table>
      </div>
      ${footInside ? `<div data-list-footer="" style="height:44px;${stickyFoot ? 'position:sticky;bottom:0;' : ''}background:#f5f6fb"><span>2건 중 2건을 받았습니다.</span>${stickyFoot ? '<i style="display:block;width:1px;height:1px"></i>' : ''}</div>` : ''}
    </div>
    ${footInside ? '' : '<div data-list-footer="" style="height:44px;text-align:center">2건 중 2건을 받았습니다.</div>'}`;
  /* wide Entity 칸 하나가 선 면. 면의 폭이 계단을 고른다 — 루트 16px 에서 1600px 는 100rem 이라 20rem, 1300px 는 81.25rem 이라
     16rem 이다. 틀린 견본은 100rem 면에서 13rem 에 머문 칸이다(컨테이너가 안 걸린 상태). 면을 폭 0 상자에 담는다 — 1200 상자보다
     넓은 면이 견본 격자의 열을 넓혀 옆 견본의 면 폭까지 바꾸지 않게 한다. */
  const wideSurface = (surfacePx, cellPx) => `
    <div style="width:0;overflow:visible">
      <div data-filter-surface="" style="width:${surfacePx}px;display:grid;gap:12px;padding-bottom:16px;border-bottom:1px solid #dcdfec">
        <div data-filter-row="" data-search-slot="" style="display:flex;flex-wrap:wrap;gap:12px;width:100%">
          ${cell('entity', cellPx, 14, 6, 600, false, 'wide')}
        </div>
      </div>
    </div>`;
  /* 문맥 줄(작업 보드 · 스프린트 회의의 팀 · 회차)의 wide 칸 — 필터 면이 아니어도 같은 칸이라 같은 해부 · 같은 계단으로 잰다.
     줄이 계단의 크기 컨테이너다. 틀린 견본은 100rem 줄에서 13rem 에 머문 칸이다. */
  const wideContext = (barPx, cellPx) => `
    <div style="width:0;overflow:visible">
      <div data-context-bar="" style="width:${barPx}px;display:flex;flex-wrap:wrap;align-items:center;gap:12px">
        ${cell('entity', cellPx, 14, 6, 600, false, 'wide')}
      </div>
    </div>`;
  /* 격자 머리 칸(`role="columnheader"` — 끌어 옮기는 백로그 머리). 표지가 이름 옆 4px 이면 맞고, 14px 떨어지면 틀리다. */
  const gridHead = (label, glyphGap) => `
    <div role="row" style="display:flex;gap:8px;height:40px;align-items:center;background:#f5f6fb">
      <div role="columnheader" style="display:flex;align-items:center;justify-content:center;width:120px"><span>${label}</span><svg width="12" height="12" style="margin-left:${glyphGap}px"></svg></div>
    </div>`;
  /* 열 배분 표식을 단 표(`DataTable` 이 내보내는 모양). cols = [키, 종류, 등급, 바닥, 상한, 폭, 값 길이 열]. clip 이 참인 칸은 말줄임으로 그린다. */
  const planTable = ({ width, box, scroll, hidden, cols, cells, clip }) => `
    <div style="width:${box || width}px;overflow-x:auto">
      <table data-plan-scroll="${scroll ? 'true' : 'false'}"${hidden ? ` data-hidden-cols="${hidden}"` : ''} style="table-layout:fixed;width:${width}px;border-collapse:collapse">
        <colgroup>${cols.map((c) => `<col data-col-key="${c[0]}" data-col-kind="${c[1]}" data-col-tier="${c[2]}" data-col-min="${c[3]}"${c[4] != null ? ` data-col-max="${c[4]}"` : ''}${c[6] ? ' data-col-content=""' : ''} style="width:${c[5]}px">`).join('')}</colgroup>
        <thead><tr style="height:40px">${cols.map((c) => `<th style="padding:0 8px;text-align:start">${c[0]}</th>`).join('')}</tr></thead>
        <tbody><tr style="height:48px">${cells.map((v, i) => `<td style="padding:0 8px${clip && clip[i] ? ';white-space:nowrap;overflow:hidden;text-overflow:ellipsis' : ''}">${v}</td>`).join('')}</tr></tbody>
      </table>
    </div>`;
  box.innerHTML = `
    <div id="compose-good">
      <div data-filter-surface="" style="display:grid;gap:12px;padding-bottom:16px;border-bottom:1px solid #dcdfec">
        <div data-filter-row="" data-search-slot="" style="display:flex;flex-wrap:wrap;gap:12px;width:100%">
          <div data-filter-kind="search" style="width:320px;height:34px;border:1px solid #ccc"></div>
          ${cell('enum', 160, 14, 6, 600, false)}
          ${cell('entity', 208, 14, 6, 600, false)}
          ${cell('entity', 208, 14, 6, 600, false, 'wide')}
        </div>
        <div data-condition-line="" style="display:flex;gap:8px;padding-top:12px;border-top:1px solid #e5e8f3">
          <span>조건 2개에 맞는 결과가 5건입니다.</span>
          <span data-condition-chip="" class="MuiChip-root" style="display:inline-flex;height:26px">상태: 진행</span>
          <span data-condition-chip="" class="MuiChip-root" style="display:inline-flex;height:26px">검색: 로그</span>
          <button data-filter-clear="" style="height:30px;border:0;background:none">필터 지우기</button>
        </div>
      </div>
      ${wideSurface(1600, 320)}
      ${wideSurface(1300, 256)}
      ${wideContext(1600, 320)}
      ${gridHead('우선순위', 4)}
      ${table('surface', true, 0, true, false, '<svg width="12" height="12" style="margin-left:4px"></svg><svg width="12" height="12" style="margin-left:4px"></svg>', false)}
      <div data-list-surface="" data-table-placement="surface" data-list-state="empty" style="background:#fff;border:1px solid #dcdfec;border-radius:8px;padding:20px;overflow:visible"><div>조건에 맞는 항목이 없습니다</div></div>
      <div data-table-placement="plain"><table class="MuiTable-root" style="width:100%;border-collapse:collapse"><thead><tr style="height:40px"><th style="background:#f5f6fb">이름</th></tr></thead><tbody><tr data-empty-band=""><td style="padding:0"><div class="k-empty" data-empty-layout="band" style="min-height:56px;display:flex;align-items:center">조건에 맞는 항목이 없습니다.</div></td></tr></tbody></table></div>
      <div class="MuiCard-root" style="background:#fff;border:1px solid #dcdfec;border-radius:8px;padding:20px"><div data-table-placement="card" style="margin:0 -20px"><div class="MuiTableContainer-root"><table class="MuiTable-root" style="width:100%;border-collapse:collapse"><thead><tr style="height:40px"><th style="background:#f5f6fb">이름</th></tr></thead><tbody><tr style="height:48px"><td>항목</td></tr></tbody></table></div><div data-list-footer="" style="height:44px;border-top:1px solid #dcdfec">2건 중 2건을 받았습니다.</div></div></div>
      <div data-action-footer="card" style="display:flex;justify-content:flex-end;padding:12px 20px;background:#f5f6fb;border-top:1px solid #e5e8f3"><button style="height:34px">티켓 추가</button></div>
      <div data-editor-box="" style="border:1px solid #dcdfec;border-radius:6px">
        <div data-editor-toolbar="" style="display:flex;background:#f5f6fb;border-bottom:1px solid #dcdfec;padding:0 4px"><button aria-label="굵게" style="height:30px;width:30px"></button><span style="flex:1"></span><button aria-label="되돌리기" style="height:30px;width:30px"></button><button aria-label="다시 실행" style="height:30px;width:30px"></button></div>
        <div data-editor-body="" style="min-height:240px;background:#fff"></div>
      </div>
      <div data-chat-log="" style="display:flex;flex-direction:column;justify-content:flex-start;overflow-y:auto;height:200px">
        <div data-chat-date="" style="width:400px;margin:0 auto">8월 24일</div>
        <div data-chat-row="theirs">안녕하세요</div>
      </div>
      <div data-chat-dock="" style="border-top:1px solid #dcdfec;padding-top:12px"><div data-chat-composer="" style="border:1px solid #ccc;border-radius:10px;height:48px"></div></div>
      <div data-page-fill="grow" style="height:120vh;border:1px solid #dcdfec">화면보다 긴 폼 판(바닥 판)</div>
      ${planTable({ width: 900, cols: [['title', 'grow', 'essential', 224, 576, 480], ['name', 'grow', 'essential', 144, 288, 324], ['state', 'fixed', 'essential', 96, null, 96, true]], cells: ['배포 일정 정리', '황형섭', '진행'] })}
      ${planTable({ width: 600, scroll: true, cols: [['title', 'grow', 'essential', 300, 576, 300], ['email', 'grow', 'essential', 400, 400, 400]], cells: ['제목', 'a@b.c'] })}
      <div style="display:flex;align-items:center;gap:8px"><div class="MuiInputBase-root" style="height:34px;width:200px;box-shadow:inset 0 0 0 1px #ccc"></div><button class="MuiButton-root" style="height:34px">불러오기</button></div>
      <div style="display:flex;align-items:center;gap:8px"><button class="MuiButton-root" style="height:30px">보기</button><button class="MuiIconButton-root" style="height:30px;width:30px"></button></div>
      <div style="display:flex;flex-wrap:wrap;gap:12px;width:430px"><div class="MuiInputBase-root" style="height:34px;width:200px;box-shadow:inset 0 0 0 1px #ccc"></div><div class="MuiInputBase-root" style="height:34px;width:200px;box-shadow:inset 0 0 0 1px #ccc"></div><div class="MuiInputBase-root" style="height:34px;width:200px;box-shadow:inset 0 0 0 1px #ccc"></div><div class="MuiInputBase-root" style="height:34px;width:200px;box-shadow:inset 0 0 0 1px #ccc"></div></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;min-height:400px"><div><button class="MuiButton-root" style="height:34px">왼쪽 판 단추</button></div><div><button class="MuiButton-root" style="height:30px">오른쪽 판 단추</button></div></div>
    </div>
    <div id="compose-bad">
      <div data-filter-surface="" style="display:grid;gap:12px;padding-bottom:16px">
        <div data-search-slot="" style="display:flex;flex-wrap:wrap;gap:12px;width:100%">
          <div data-filter-kind="search" style="width:320px;height:34px;border:1px solid #ccc"></div>
        </div>
        <div data-filter-row="" data-search-slot="" style="display:flex;flex-wrap:wrap;gap:12px;width:100%">
          ${cell('enum', 160, 6, 14, 400, false)}
          ${cell('entity', 384, 14, 6, 600, true)}
          <div data-filter-actions=""><button style="height:34px">필터 지우기</button></div>
        </div>
      </div>
      <div><span class="MuiChip-root" style="display:inline-flex;height:26px">종료 제외(기본값)</span></div>
      <div data-result-line="">조건 1개에 맞는 결과가 14건입니다.</div>
      <div class="MuiCard-root" style="background:#fff;border:1px solid #dcdfec;border-radius:8px;padding:20px">
        ${table('surface', true, 0, false, false, '<button style="height:30px;width:30px;margin-left:10px"><svg width="20" height="20"></svg></button><svg width="12" height="12" style="margin-left:12px"></svg>', true)}
      </div>
      ${table('surface', true, 0, true, true, '', false)}
      <div data-list-surface="" data-table-placement="surface" data-list-state="empty" style="background:#fff;border:1px solid #dcdfec;border-radius:8px;padding:0;overflow:visible"><div>여백 없는 빈 판</div></div>
      <table class="MuiTable-root"><thead><tr><th>이름</th></tr></thead><tbody><tr><td>표식 없음</td></tr></tbody></table>
      <div data-action-footer="card" style="display:flex;justify-content:flex-end;padding:12px 100px 12px 20px"><button style="height:34px">티켓 추가</button></div>
      <button class="MuiButton-root MuiButton-containedPrimary" style="height:34px">새 그룹</button>
      <button class="MuiButton-root MuiButton-containedPrimary" style="height:34px">적용</button>
      <div data-editor-box="" style="border:0">
        <div data-editor-toolbar="" style="display:flex;padding:0 4px"><button aria-label="되돌리기" style="height:34px;width:34px"></button><button aria-label="다시 실행" style="height:34px;width:34px"></button><span style="flex:1"></span></div>
        <div data-editor-body="" style="min-height:120px"></div>
      </div>
      <div data-chat-log="" style="display:flex;flex-direction:column;justify-content:flex-end;overflow-y:auto;height:200px">
        <div data-chat-date="" style="width:1000px">8월 24일</div>
        <div data-chat-row="theirs">안녕하세요</div>
      </div>
      <div data-chat-composer="" style="border:1px solid #ccc;border-radius:10px;height:48px"></div>
      <div data-page-fill="" style="height:120vh;border:1px solid #dcdfec">화면을 넘는 높이 고정 판</div>
      ${wideSurface(1600, 208)}
      ${wideContext(1600, 208)}
      ${gridHead('난이도', 14)}
      <div style="width:0;overflow:visible">
        <div data-filter-surface="" style="width:600px;display:grid;gap:12px;padding-bottom:16px;border-bottom:1px solid #dcdfec">
          <div data-filter-row="" data-search-slot="" style="display:flex;flex-wrap:wrap;gap:12px;width:100%">
            <div data-filter-kind="search" style="width:320px;height:34px;border:1px solid #ccc"></div>
          </div>
        </div>
      </div>
      <div data-table-placement="plain"><table class="MuiTable-root" style="width:100%;border-collapse:collapse"><thead><tr style="height:40px"><th style="background:#f5f6fb">이름</th></tr></thead><tbody><tr data-empty-band=""><td style="padding:0"><div class="k-empty" style="height:120px"><img alt="" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" style="width:80px;height:80px"></div></td></tr></tbody></table></div>
      ${planTable({ width: 900, hidden: 'email:essential', cols: [['title', 'grow', 'essential', 224, 576, 480], ['name', 'grow', 'essential', 144, 288, 324], ['state', 'fixed', 'essential', 96, null, 96, true]], cells: ['배포 일정 정리', '황형섭', '진행'] })}
      ${planTable({ width: 800, box: 600, cols: [['title', 'grow', 'essential', 224, 576, 400], ['job', 'fixed', 'secondary', 104, null, 104], ['name', 'grow', 'essential', 144, 288, 296]], cells: ['제목', '직책', '이름'] })}
      ${planTable({ width: 940, cols: [['title', 'grow', 'essential', 224, 900, 700], ['name', 'grow', 'essential', 144, 288, 144], ['state', 'fixed', 'essential', 96, null, 96, true]], cells: ['제목', '이름', '진행'] })}
      ${planTable({ width: 900, cols: [['title', 'grow', 'essential', 224, 576, 500], ['email', 'grow', 'essential', 176, 352, 304], ['state', 'fixed', 'essential', 96, null, 96, true]], cells: ['짧음', 'a-very-long-mailbox-name-for-testing@goodmit.co.kr', '아주 긴 상태 낱말이 칸을 넘칩니다'], clip: [false, true, true] })}
      <div style="display:flex;align-items:center;gap:8px"><div class="MuiInputBase-root" style="height:36px;width:200px;box-shadow:inset 0 0 0 1px #ccc"></div><button class="MuiButton-root" style="height:34px">불러오기</button></div>
      <div style="display:flex;align-items:flex-start;gap:8px"><div class="MuiInputBase-root" style="height:34px;width:200px;box-shadow:inset 0 0 0 1px #ccc"></div><button class="MuiButton-root" style="height:34px;margin-top:6px">떠 있는 단추</button></div>
    </div>`;
  document.body.appendChild(box);
  return true;
})()
"""


# 틀린 견본이 반드시 걸려야 하는 검사와 기대 최소 실패 수. 칸 해부의 넷째는 문맥 줄의 wide 칸, 머리 표지의 둘째는 격자
# 머리 칸이다 — 선택자가 그 자리를 안 보면 수가 모자라 실패한다.
SELFTEST_EXPECT_BAD = {
    "filter_composition": 1, "filter_cell_anatomy": 4, "list_surface": 3, "list_wrapper": 2,
    "primary_budget": 2, "row_actions": 1, "table_head_glyph": 2, "footer_alignment": 1,
    "editor_box": 1, "chat_composition": 1, "page_fill": 1, "table_empty_band": 1,
    "column_balance": 4, "control_row": 2,
}

# 틀린 견본의 실패 사유 안에 반드시 나와야 하는 낱말 — 개수만 맞고 엉뚱한 이유로 걸리는 것을 막는다.
SELFTEST_EXPECT_REASONS = {
    "filter_composition": ["면 밖 결과 줄", "면 밖 조건 칩", "줄 끝 지우기", "아래 실선 없음", "검색 줄에 자리가 있는데", "검색 칸 폭"],
    "filter_cell_anatomy": ["칸 안 칩", "접두 들여쓰기", "접두-값 간격", "값 굵기", "폭 ", "wide 계단"],
    "list_surface": ["목록 발이 판 밖", "sticky 발 안에 무한 스크롤 센티널", "빈 · 불러오는 판 여백"],
    "list_wrapper": ["표 판 계약 표식 없음", "여백 판이 한 번 더 감쌈"],
    "primary_budget": ["화면 채움", "행 안 채움"],
    "row_actions": ["한 칸 단추"],
    "table_head_glyph": ["표지 20px", "이름과", "앞 표지와"],
    "footer_alignment": ["100"],
    "editor_box": ["테두리", "도구 줄이 함몰면이 아님", "도구 단추 34", "다시 실행이 오른쪽 끝이 아님", "본문 120"],
    "chat_composition": ["로그 아래 정렬", "날짜선 폭", "입력 도킹 영역 없음"],
    "page_fill": ["높이 고정 판이 화면을 넘음"],
    "table_empty_band": ["높이", "그림"],
    "column_balance": ["필수 열 숨김", "숨길 수 있는 열이 남았는데", "독점", "옆 열 여유", "값 길이 열 말줄임"],
    "control_row": ["높이 36/34", "윗선 6px"],
}


def selftest_verdict(good: dict, bad: dict) -> list[str]:
    """맞는 견본 · 틀린 견본 실측을 받아 문제 목록을 돌려준다(빈 목록이면 통과)."""
    import json

    problems: list[str] = []
    for name, want in SELFTEST_EXPECT_BAD.items():
        got = (bad.get(name) or {}).get("failed", 0)
        if got < want:
            problems.append(f"틀린 견본을 못 잡음: {name} (실패 {got} < {want})")
    for name, words in SELFTEST_EXPECT_REASONS.items():
        blob = json.dumps((bad.get(name) or {}).get("bad", []), ensure_ascii=False)
        for w in words:
            if w not in blob:
                problems.append(f"틀린 견본의 사유가 빠짐: {name} «{w}»")
    for name in COMPOSITION_CHECKS:
        got = good.get(name) or {}
        if got.get("failed"):
            problems.append(f"맞는 견본을 잘못 잡음: {name} → {got.get('bad', [])[:2]}")
    checked_good = sum((good.get(n) or {}).get("checked", 0) for n in COMPOSITION_CHECKS)
    if checked_good < 8:
        problems.append(f"맞는 견본 표본이 너무 적다({checked_good})")
    return problems
