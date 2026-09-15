"""공통 부품의 **조합**을 실브라우저에서 잰다 (UI 3차 · 조합 계약 C-1 ~ C-7).

`kit_measure.py` 의 검사는 부품 **낱개의 치수**를 본다(칸 34 · 검색 320 · 머리 40 · 발 주인 하나).
그 검사가 전부 초록이어도 화면은 틀릴 수 있다 — 칩과 결과 줄이 필터 면 **밖**에 두 줄로 서고,
표가 여백 20 판 안에 한 번 더 들어가 머리가 판 가장자리에서 떨어지고, 발이 표 밖 가운데에 선다.
치수는 맞는데 **관계**가 틀린 상태다. 이 모듈은 그 관계를 잰다.

    filter_composition   조건 칩 · 결과 · 지우기가 필터 면 안 둘째 줄(조건 줄)에만 있는가,
                         조건 수 = 칩 수인가, 아래 실선이 있는가, 한 줄에 설 자리가 있는데 검색 혼자 줄을 쓰지 않는가
    filter_cell_anatomy  칸 종류가 달라도 접두 이름 들여쓰기 · 접두-값 간격 · 세로 중심 · 값 굵기가 같은가,
                         다중 선택이 칸 안에 칩을 그려 높이를 풀지 않는가, 칸 폭이 종류 표를 따르는가
    list_surface         주 목록이 목록 판(surface)인가, 머리 줄이 판 윗변 · 좌우 가장자리에 붙는가,
                         발이 판 안 마지막 줄인가, sticky 발 안에 무한 스크롤 센티널이 없는가
    list_wrapper         표마다 판 계약 표식이 있는가, 목록 판을 여백 판이 한 번 더 감싸지 않는가
    primary_budget       모달 밖 화면의 채움 단추가 하나 이하인가(입력 영역 · 카드 발 · 선택 발은 자기 몫), 행 안 채움 0
    row_actions          행 안 단추가 30 이고 칸마다 둘 이하인가
    table_head_glyph     머리 칸의 정렬 · 필터 표지가 16 이하이고 이름 옆 6 이내에 붙는가
    footer_alignment     카드 발의 끝 단추 오른쪽이 판 여백(20)에 맞는가
    editor_box           편집기가 상자 하나(도구 줄 함몰면 + 아래 선 · 도구 30 · 다시 실행 오른쪽 끝 · 본문 240 이상)인가
    page_fill            화면 아래까지 서야 하는 판이 화면 아래까지 서는가
    chat_composition     대화 로그가 위 정렬인가, 날짜선 폭 28rem 이하, 방 머리 두 줄, 입력 상자가 도킹 선 안에 있는가,
                         목록 시각이 긴 절대 형식이 아닌가

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
    "editor_box", "page_fill", "chat_composition",
)

# 조합 계약의 값. 여기 숫자를 바꾸는 것은 계약을 바꾸는 일이다(`docs/DECISIONS.md` D-488 ~ D-494).
COMPOSITION_CONTRACT = {
    "filterCell": 34,
    "prefixInset": 14,
    "prefixGap": 6,
    # 줄 칸 폭(rem). 늘어나지 않는다 — 최솟값 = 최댓값인 종류는 고정 폭이다.
    "rowKind": {
        "entity": [13, 13],
        "tag": [13, 13],
        "enum": [8, 13],
        "text": [11, 11],
        "date": [11, 11],
        "datetime": [18, 18],
    },
    "rowAction": 30,
    "rowActionsPerCell": 2,
    "headGlyphMax": 16,
    "headGlyphGap": 6,
    "cardPadding": 20,
    "editorBodyMin": 240,
    "editorTool": 30,
    "listFooterMin": 44,
    "chatDateMaxRem": 28,
    "tol": 1,
}

# 화면마다 **있어야 하는 조합**. 키는 `scripts/ui_qa/routes.py` 의 route id 다.
#   listSurface  주 목록이 목록 판(`DataTable placement="surface"`)이어야 한다
#   editorBox    편집기 상자가 있어야 한다
#   pageFill     화면 아래까지 서는 판이 있어야 한다
#   chat         대화 로그가 있어야 한다
#   skipBudget   채움 단추 수를 세지 않는다(갤러리는 견본을 나란히 세우는 카탈로그다)
#   callerWidths 필터 칸 폭은 호출부가 정한다(보호 화면 두 줄 필터 — D-484)
#   filterExempt 필터 조합 검사를 하지 않는다(대장 예외 — 제출형 검색 · 달력 도구 줄 · 보호 화면)
#   footerExempt 목록 판 밖 `ListFooter` 를 허용한다(보호 화면 백로그)
ROUTE_EXPECT: dict[str, dict] = {
    "user_my-tickets": {"listSurface": True},
    "user_unassigned": {"listSurface": True},
    "user_team-tickets": {"listSurface": True},
    "user_knowledge": {"listSurface": True},
    "user_board": {"listSurface": True},
    "user_projects": {"listSurface": True},
    "user_team-docs-trash": {"listSurface": True},
    "user_my-approvals": {"listSurface": True},
    "admin_users": {"listSurface": True},
    "admin_audit": {"listSurface": True},
    "admin_jobs": {"listSurface": True},
    "admin_offboarding": {"listSurface": True},
    "user_new-ticket": {"editorBox": True, "pageFill": True},
    "user_chat-rooms": {"chat": True, "pageFill": True},
    "user_chat-room-detail": {"chat": True, "pageFill": True},
    "user_kit": {"skipBudget": True},
    "user_work-board": {"callerWidths": True, "filterExempt": True, "footerExempt": True},
    "user_sprint": {"callerWidths": True, "filterExempt": True},
    "user_search": {"filterExempt": True},
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
    if (problems.length) fail('filter_composition', { ...where(s), problems: problems.slice(0, 6) });
  }

  // ── 필터 칸 해부 ─────────────────────────────────────────────────────────
  out.filter_cell_kinds = {};
  if (!E.filterExempt) {
    for (const cell of all('[data-filter-surface] [data-filter-kind]')) {
      const kind = cell.getAttribute('data-filter-kind');
      if (kind === 'search' || kind === 'toggle' || kind === 'number' || cell.closest('[data-condition-line]')) continue;
      const box = cell.querySelector('.MuiInputBase-root');
      if (!box || !shown(box)) continue;
      check('filter_cell_anatomy').checked++;
      const problems = [];
      const br = rect(box);
      if (!near(br.height, C.filterCell)) problems.push('높이 ' + Math.round(br.height));
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
      const want = C.rowKind[kind];
      if (want && !E.callerWidths) {
        const w = rect(cell).width / rootPx;
        if (w < want[0] - 0.07 || w > want[1] + 0.07) problems.push('폭 ' + w.toFixed(2) + 'rem');
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
    if (!main && !listSurfaces.length) fail('list_surface', { problem: '주 목록을 찾지 못함' });
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
    if (px(cs.paddingTop) > 0.5 || px(cs.paddingLeft) > 0.5) problems.push('판 여백 ' + cs.paddingTop + '/' + cs.paddingLeft);
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
      if (rect(foot).height < C.listFooterMin - tol) problems.push('발 높이 ' + Math.round(rect(foot).height));
      if (getComputedStyle(foot).position === 'sticky') {
        const tiny = [...foot.querySelectorAll('*')].find((el) => { const r = rect(el); return r.width <= 1.5 && r.height <= 1.5 && getComputedStyle(el).display !== 'none'; });
        if (tiny) problems.push('sticky 발 안에 무한 스크롤 센티널');
      }
    }
    if (problems.length) fail('list_surface', { ...where(s), problems: problems.slice(0, 6) });
  }
  if (!E.footerExempt) {
    for (const f of all('[data-list-footer]')) {
      if (inOverlay(f) || f.closest('[data-list-surface]')) continue;
      check('list_surface').checked++;
      fail('list_surface', { ...where(f), problem: '목록 발이 판 밖' });
    }
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
    const bad = btns.filter((b) => !near(rect(b).height, C.rowAction, 1));
    if (bad.length) fail('row_actions', { ...where(td), problem: '행 단추 높이', h: [...new Set(bad.map((b) => Math.round(rect(b).height)))] });
    if (btns.length > C.rowActionsPerCell) fail('row_actions', { ...where(td), problem: '한 칸 단추 ' + btns.length });
  }

  // ── 머리 칸 표지 ─────────────────────────────────────────────────────────
  for (const th of all('thead th')) {
    if (inOverlay(th)) continue;
    const glyphs = [...th.querySelectorAll('svg, [data-head-glyph]')].filter(shown);
    if (!glyphs.length) continue;
    const label = [...th.querySelectorAll('span')].find((sp) => sp.children.length === 0 && (sp.textContent || '').trim().length > 1 && shown(sp));
    check('table_head_glyph').checked++;
    const problems = [];
    for (const g of glyphs) {
      const gr = rect(g);
      if (gr.width > C.headGlyphMax + 0.5 || gr.height > C.headGlyphMax + 0.5) problems.push('표지 ' + Math.round(gr.width) + 'px');
      if (label) {
        const lr = rect(label);
        const gap = gr.left >= lr.right ? gr.left - lr.right : lr.left - gr.right;
        if (gap > C.headGlyphGap + 0.5) problems.push('이름과 ' + Math.round(gap) + 'px');
      }
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
    if (!near(gap, C.cardPadding, 1)) fail('footer_alignment', { text: text(last), gap: Math.round(gap), want: C.cardPadding });
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
      const off = tools.filter((x) => !near(rect(x).height, C.editorTool, 1));
      if (off.length) problems.push('도구 단추 ' + [...new Set(off.map((x) => Math.round(rect(x).height)))].join(','));
      const redo = tb.querySelector('[aria-label="다시 실행"]');
      if (redo && shown(redo) && !near(rect(redo).right, rect(tb).right - px(ts.paddingRight), 2)) problems.push('다시 실행이 오른쪽 끝이 아님');
    }
    if (!body || !shown(body)) problems.push('본문 없음');
    else if (rect(body).height < C.editorBodyMin - tol) problems.push('본문 ' + Math.round(rect(body).height));
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
    if (window.scrollY < 2 && (gap > allowed || gap < -1)) fail('page_fill', { ...where(f), bottomGap: Math.round(gap), allowed: Math.round(allowed) });
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
  const cell = (kind, width, inset, gap, weight, chip) => `
    <div data-filter-kind="${kind}" style="width:${width}px;flex:0 0 auto">
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
  box.innerHTML = `
    <div id="compose-good">
      <div data-filter-surface="" style="display:grid;gap:12px;padding-bottom:16px;border-bottom:1px solid #dcdfec">
        <div data-filter-row="" data-search-slot="" style="display:flex;flex-wrap:wrap;gap:12px;width:100%">
          <div data-filter-kind="search" style="width:320px;height:34px;border:1px solid #ccc"></div>
          ${cell('enum', 160, 14, 6, 600, false)}
          ${cell('entity', 208, 14, 6, 600, false)}
        </div>
        <div data-condition-line="" style="display:flex;gap:8px;padding-top:12px;border-top:1px solid #e5e8f3">
          <span>조건 2개, 결과 5건</span>
          <span data-condition-chip="" class="MuiChip-root" style="display:inline-flex;height:26px">상태: 진행</span>
          <span data-condition-chip="" class="MuiChip-root" style="display:inline-flex;height:26px">검색: 로그</span>
          <button data-filter-clear="" style="height:30px;border:0;background:none">필터 지우기</button>
        </div>
      </div>
      ${table('surface', true, 0, true, false, '<svg width="12" height="12" style="margin-left:4px"></svg>', false)}
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
      <div data-result-line="">조건 1개, 결과 14건</div>
      <div class="MuiCard-root" style="background:#fff;border:1px solid #dcdfec;border-radius:8px;padding:20px">
        ${table('surface', true, 0, false, false, '<button style="height:30px;width:30px;margin-left:10px"><svg width="20" height="20"></svg></button>', true)}
      </div>
      ${table('surface', true, 0, true, true, '', false)}
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
    </div>`;
  document.body.appendChild(box);
  return true;
})()
"""


# 틀린 견본이 반드시 걸려야 하는 검사와 기대 최소 실패 수.
SELFTEST_EXPECT_BAD = {
    "filter_composition": 1, "filter_cell_anatomy": 2, "list_surface": 2, "list_wrapper": 2,
    "primary_budget": 2, "row_actions": 1, "table_head_glyph": 1, "footer_alignment": 1,
    "editor_box": 1, "chat_composition": 1,
}

# 틀린 견본의 실패 사유 안에 반드시 나와야 하는 낱말 — 개수만 맞고 엉뚱한 이유로 걸리는 것을 막는다.
SELFTEST_EXPECT_REASONS = {
    "filter_composition": ["면 밖 결과 줄", "면 밖 조건 칩", "줄 끝 지우기", "아래 실선 없음", "검색 줄에 자리가 있는데"],
    "filter_cell_anatomy": ["칸 안 칩", "접두 들여쓰기", "접두-값 간격", "값 굵기", "폭 "],
    "list_surface": ["목록 발이 판 밖", "sticky 발 안에 무한 스크롤 센티널"],
    "list_wrapper": ["표 판 계약 표식 없음", "여백 판이 한 번 더 감쌈"],
    "primary_budget": ["화면 채움", "행 안 채움"],
    "row_actions": ["한 칸 단추"],
    "table_head_glyph": ["표지 20px", "이름과"],
    "footer_alignment": ["100"],
    "editor_box": ["테두리", "도구 줄이 함몰면이 아님", "도구 단추 34", "다시 실행이 오른쪽 끝이 아님", "본문 120"],
    "chat_composition": ["로그 아래 정렬", "날짜선 폭", "입력 도킹 영역 없음"],
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
