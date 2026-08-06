"""기준 목업 ↔ 우리 화면 좌우 대조 (0단계 #2).

## 왜 이 파일이 생겼나

디자인 기준이 있는데 나는 기준 파일의 CSS 토큰과 우리 `theme.js` 를 **값으로만** 대조했다.
primary `#536CD6`, 카드 radius 18, chip 999, 버튼 높이 40 — 다 같아서 "테마는 이미 일치한다"고
결론 내리고 작업 범위를 셸 껍데기로 좁혔다. **기준 파일을 렌더해서 화면끼리 비교한 것은
지적을 받은 뒤가 처음이었다.** 토큰이 같은 것과 화면이 같은 것은 다른 얘기였다.

그래서 규칙을 도구로 만든다: **완료 판정은 이 시트로 한다.** 값이 같다고 맞다고 하지 않는다.

## 무엇을 재는가 — 그리고 무엇을 재지 않는가

**픽셀 diff 는 쓰지 않는다.** 기준은 목업이고 우리는 실제 데이터가 든 앱이다. 글자 수도
행 수도 다르므로 픽셀 비교는 100% 실패하거나 임계값을 아무렇게나 잡게 된다. 대신 **구조와
디자인 토큰**을 비교한다 — 사람이 "다르다"고 말할 때 실제로 가리키는 것들이다:

  * 뼈대 — 상단바/사이드바/본문의 존재와 폭, 본문 격자의 열 수
  * 카드 — 개수, 모서리 반지름의 종류 수, 그림자 유무
  * 색 — 배경/표면/강조색, 상단바 그라데이션 유무
  * 타이포 — 제목 크기 계단, 본문 크기
  * 컨트롤 — 버튼 높이·반지름, 입력 높이
  * 밀도 — 카드 사이 간격, 본문 좌우 여백

각 항목은 **허용 오차**를 갖는다(아래 TOLERANCE). 오차 안이면 통과, 밖이면 차이로 적는다.
결과는 JSON + 사람이 읽는 표 + 좌우 스크린샷 쌍으로 남긴다.

## 쓰는 법

    python -m scripts.ui_qa.baseline --out dist/baseline
    python -m scripts.ui_qa.baseline --routes home,my-tickets --out dist/baseline

기준 파일은 `design/baseline/preview-standalone.html` — 저장소 안에 있다. 원본은 16.3MB
단일 HTML 이었는데 99%가 임베드 이미지라 이미지를 `assets/` 로 뽑아 150KB 로 줄였다
(그래야 읽고 diff 할 수 있고, `.bak` 폴더 밖이라 CI 도 읽는다).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE_HTML = REPO / "design" / "baseline" / "preview-standalone.html"

# 목업 라우트 → 우리 앱의 해시 경로. None 이면 "우리에게 아직 대응 화면이 없다"는 뜻이고,
# 그 자체가 대조 결과다(기능이 빠졌거나 라우트 구조가 다르다).
ROUTE_MAP: dict[str, str | None] = {
    # 사용자
    #
    # ⚠️ 홈은 `#/me` 다. `#/` 가 아니다 — **콘솔은 경로로 정해진다**
    # (`App.jsx: useUserConsole = isUser || inUserSegment(pathname)`, `navConfig.js: USER_SEG_PATHS`).
    # `/` 는 사용자 세그먼트가 아니라서 **관리자 계정으로 열면 관리자 대시보드가 뜬다.**
    # QA 계정은 관리자다. 그래서 `home` 과 `admin/dashboard` 가 **둘 다 `#/`** 로 적혀 있던
    # 동안, 우리는 사용자 홈 목업을 **관리자 대시보드와 비교**하고 있었다(캡처로 잡았다 —
    # '우리' 스크린샷의 사이드바가 운영·감사 로그·백업이었다).
    # 관리자 화면을 `/admin` 셸에서 열게 고친 것과 **똑같은 종류의 실수**이고, 그때는
    # 사용자 쪽을 안 봤다.
    "home": "#/me",
    "my-tickets": "#/my-tickets",
    "unassigned-tickets": "#/unassigned",
    "team-tickets": "#/team-tickets",
    "new-ticket": "#/new-ticket",
    "sprint": "#/sprint",
    "docs": "#/team-docs",
    "docs-trash": "#/team-docs/trash",
    "chatrooms": "#/chat-rooms",
    "assistant": "#/chat",
    "games": "#/games",
    "board": "#/board",
    # 상세 화면은 실제 id 가 필요하다. `DETAIL_ROUTES` 가 하네스의 id 탐색을 재사용한다.
    "ticket": "",
    "chatroom": "",
    "board-post": "",
    # 관리자
    "admin/dashboard": "#/",
    "admin/notifications": "#/notifications",
    "admin/audit": "#/audit",
    "admin/report": "#/report",
    "admin/users": "#/users",
    "admin/settings": "#/settings",
    "admin/jobs": "#/jobs",
    "admin/backups": "#/backups",
    "admin/diagnostics": "#/diagnostics",
    "admin/maintenance": "#/ops",
    "admin/departments": "#/departments",
    "admin/job-titles": "#/job-titles",
    "admin/notion-mappings": "#/notion-mapping",
    "admin/integrations": "#/integrations",
    "admin/runners": "#/runners",
    "admin/workflows": "#/workflows",
    "admin/prompts": "#/prompts",
    "admin/policies": "#/policies",
    "admin/templates": "#/templates",
    "admin/schedules": "#/schedules",
    "admin/document-generation": "#/documents",
    "admin/approvals": "#/approvals",
}

# 상세 화면 → 하네스의 라우트 id. 목록 API 의 첫 항목 id 를 넣어 경로를 만든다
# (`capture.discover_detail_hash`). 여기서 하드코딩하면 하네스와 규칙이 두 벌이 된다.
DETAIL_ROUTES = {
    "ticket": "user_ticket-detail",
    "chatroom": "user_chat-room-detail",
    "board-post": "user_board-post",
}

# 허용 오차. 이 안이면 "같다"로 본다.
#
# 왜 오차를 두는가: 기준은 목업이고 우리는 MUI 다. 1px 을 맞추는 것은 목표가 아니고,
# 맞추려 들면 통과하지 못하는 시트가 되어 아무도 안 본다. 사람이 "다르다"고 느끼는
# 최소 단위를 기준으로 잡았다 — 반지름 2px, 색 12/255, 폭 5%.
TOLERANCE = {
    "radius_px": 2.0,
    "color_channel": 12,
    "ratio_pct": 5.0,
    "font_px": 1.5,
    "gap_px": 6.0,
    "height_px": 4.0,
}

# 화면에서 지문을 뜨는 스크립트. 기준과 우리 앱에 **같은 것**을 돌린다 —
# 서로 다른 프로브를 쓰면 비교가 아니라 두 개의 측정이 된다.
FINGERPRINT_JS = r"""
() => {
  const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
  const rgb = (s) => { const m = String(s).match(/[\d.]+/g); return m ? m.slice(0, 3).map(Number) : null; };
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
  };
  const pick = (...sels) => { for (const s of sels) { const e = document.querySelector(s); if (e && vis(e)) return e; } return null; };

  const out = {};
  const de = document.documentElement;
  out.viewport = { w: innerWidth, h: innerHeight };
  out.theme = de.dataset.theme || null;

  // ── 뼈대 ──────────────────────────────────────────────────────────────
  const topbar = pick('header', '.topbar', '.MuiAppBar-root');
  const side = pick('nav.sidebar', '.sidebar', 'aside', '.MuiDrawer-root .MuiPaper-root');
  const main = pick('#main-content', 'main', '.content');
  out.shell = {
    topbarH: topbar ? Math.round(topbar.getBoundingClientRect().height) : null,
    topbarGradient: topbar ? /gradient/i.test(getComputedStyle(topbar).backgroundImage) : null,
    sidebarW: side ? Math.round(side.getBoundingClientRect().width) : null,
    mainW: main ? Math.round(main.getBoundingClientRect().width) : null,
    mainPct: main ? Math.round(main.getBoundingClientRect().width / innerWidth * 100) : null,
  };

  // ── 색 ────────────────────────────────────────────────────────────────
  //
  // 강조색은 CSS 변수로 읽지 않는다. 목업은 `--primary: #536CD6` 처럼 **hex** 로 두는데
  // 우리 MUI 테마는 그 변수를 아예 두지 않는다. 변수를 읽으면 한쪽은 hex 문자열, 다른 쪽은
  // 빈 문자열이 나와 비교가 성립하지 않는다(실제로 `[536, 6]` vs `null` 이 나왔다).
  // 대신 **화면에 그려진 주 버튼의 배경색**을 잰다 — 사람이 "강조색"이라 부르는 그것이다.
  const body = getComputedStyle(document.body);
  const primaryBtn = [...document.querySelectorAll(
      'button, .btn, .MuiButton-root, .btn-primary, .MuiButton-containedPrimary')]
    .filter(vis)
    .map((b) => ({ el: b, bg: rgb(getComputedStyle(b).backgroundColor),
                   alpha: (getComputedStyle(b).backgroundColor.match(/[\d.]+/g) || [])[3] }))
    // 투명하거나 흰/검정에 가까운 것은 주 버튼이 아니다(텍스트 버튼·아이콘 버튼).
    .filter((x) => x.bg && x.alpha !== '0'
                && !(x.bg[0] > 240 && x.bg[1] > 240 && x.bg[2] > 240)
                && !(x.bg[0] < 24 && x.bg[1] < 24 && x.bg[2] < 24))[0];
  out.color = {
    bg: rgb(body.backgroundColor),
    text: rgb(body.color),
    accent: primaryBtn ? primaryBtn.bg : null,
  };

  // ── 카드 ──────────────────────────────────────────────────────────────
  //
  // `.MuiPaper-root` 는 상단바·서랍·메뉴·팝오버·대화상자까지 전부 Paper 다. 그대로 세면
  // 화면이 달라도 늘 같은 숫자가 나온다(실제로 네 화면 전부 '높이 편차 1031' 이 나왔다 —
  // 카드가 아니라 셸을 재고 있었다는 뜻이다). 본문 안에 있고, 셸 부품이 아닌 것만 센다.
  const SHELL = '.MuiAppBar-root, .MuiDrawer-root, .MuiMenu-root, .MuiPopover-root, ' +
                '.MuiDialog-root, .MuiTooltip-popper, header, nav, aside';
  const scope = main || document.body;
  const cards = [...scope.querySelectorAll('.card, .MuiCard-root, .MuiPaper-root')]
    .filter(vis)
    .filter((el) => !el.closest(SHELL))
    // 안내·경고 상자(`Callout` = MuiAlert)는 카드가 아니다. 테두리와 반지름이 있어서
    // 카드처럼 잡히지만 성격이 다르다(카드 앞에 놓이는 한 줄이고 그림자를 주지 않는다).
    // 이걸 카드로 세면 그림자 비율이 100% → 50% 로 떨어져 8화면이 어긋난 것처럼 보인다.
    .filter((el) => !el.matches('.k-callout, .MuiAlert-root') && !el.closest('.k-callout, .MuiAlert-root'))
    // 알약(완전히 둥근 것)도 카드가 아니다 — 칩·배지·컴포저 바의 모양이다. 카드로 세면
    // 그 화면의 '반지름 종류'가 통일 뒤에도 영원히 2 이상이라 검사가 절대 초록이 안 된다
    // (계획서가 알약 999 와 아바타 50% 를 규칙에서 **명시적으로 제외**하라고 적은 이유).
    .filter((el) => { const r = el.getBoundingClientRect();
                      const rad = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
                      return rad < r.height / 2 - 1; })
    // 다른 카드를 품고 있는 바깥 상자는 카드가 아니라 컨테이너다.
    .filter((el) => !el.querySelector('.card, .MuiCard-root'))
    // 높이 상한은 **전면 레이아웃 상자**를 걸러내려던 것인데, 그 일은 아래의 '반지름도
    // 테두리도 그림자도 없으면 카드가 아니다' 가 이미 한다. 상한이 낮으면 **긴 목록을 담은
    // 카드가 통째로 빠진다** — 팀 티켓(188행)의 표 카드가 8000px 이라 "카드 없음" 이 나왔다.
    .filter((el) => { const r = el.getBoundingClientRect();
                      return r.width > 120 && r.height > 40 && r.height < innerHeight * 12; })
    // 반지름도 테두리도 그림자도 없는 것은 카드가 아니라 **투명 레이아웃 상자**다.
    // (본문 폭 전체를 차지하는 `MuiPaper-elevation0` 이 28개 잡혀 그림자 비율을 끌어내렸다.)
    .filter((el) => { const cs = getComputedStyle(el);
                      return (parseFloat(cs.borderTopLeftRadius) || 0) > 0
                          || (parseFloat(cs.borderTopWidth) || 0) > 0
                          || (cs.boxShadow && cs.boxShadow !== 'none'); });
  const radii = new Set(), shadowed = [];
  const rects = [];
  for (const c of cards.slice(0, 60)) {
    const cs = getComputedStyle(c);
    radii.add(Math.round(num(cs.borderTopLeftRadius) ?? 0));
    shadowed.push(cs.boxShadow && cs.boxShadow !== 'none');
    const r = c.getBoundingClientRect();
    rects.push({ x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                 h: Math.round(r.height), parent: c.parentElement });
  }
  out.cards = {
    count: cards.length,
    radii: [...radii].sort((a, b) => a - b),
    radiusKinds: radii.size,
    shadowRatio: shadowed.length ? Math.round(shadowed.filter(Boolean).length / shadowed.length * 100) : null,
    // **같은 줄에 놓인** 카드들의 높이 편차. 화면 전체 최대-최소를 재면 안 된다 —
    // 세로로 쌓인 카드는 내용이 다르니 높이도 다른 게 당연하고, 그러면 관리자 화면이
    // 전부 똑같이 '161' 을 뱉는다(실제로 그랬다). 사용자가 지적한 것(Q5 "카드 크기가
    // 제각각")은 **나란히 놓인 카드가 서로 다른 높이**인 것이다.
    // 윗변이 12px 안쪽이면 같은 줄로 본다(테두리·그림자 반올림 여유).
    heightSpread: (() => {
      // 같은 부모 아래, 같은 줄. 부모를 안 보면 **다른 열**의 카드가 우연히 윗변을
      // 공유하는 것까지 잡힌다 — 홈에서 217px 짜리 요약 패널과 옆 열의 56px 상태 카드가
      // 그렇게 묶여 "편차 161px" 이 나왔다. 그 둘은 같은 격자의 형제가 아니다.
      const rows = [];
      for (const r of rects) {
        const row = rows.find((g) => g[0].parent === r.parent && Math.abs(g[0].y - r.y) <= 12);
        if (row) row.push(r); else rows.push([r]);
      }
      let worst = 0;
      for (const row of rows) {
        if (row.length < 2) continue;
        const hs = row.map((r) => r.h);
        worst = Math.max(worst, Math.max(...hs) - Math.min(...hs));
      }
      return worst;
    })(),
  };

  // ── 본문 격자 (열이 몇 개인가) ─────────────────────────────────────────
  //
  // "카드가 몇 열로 놓이는가"를 재려는 것이다. 표 안쪽 격자나 툴바 격자를 잡으면 화면과
  // 무관한 숫자가 나온다(표 기반 화면에서 '8열' 이 나왔다 — 표의 열 수였다).
  // 조건: 본문 폭의 절반 이상 + 자식이 열 수만큼 있음 + 표/툴바 안이 아님 + 자식이 카드류.
  let cols = null;
  if (main) {
    for (const el of main.querySelectorAll('div, section, ul')) {
      const cs = getComputedStyle(el);
      if (cs.display !== 'grid') continue;
      if (el.closest('table, thead, tbody, tr, .MuiTable-root, .toolbar, .MuiTableContainer-root')) continue;
      const n = cs.gridTemplateColumns.split(' ').filter(Boolean).length;
      if (n < 2 || n > 8) continue;
      if (el.getBoundingClientRect().width < innerWidth * 0.5) continue;
      const kids = [...el.children].filter(vis);
      // 자식이 열 수보다 적어도 **그 격자는 여전히 n 열이다**. 예전에는 여기서 걸러 버려
      // 무관한 격자를 대신 집었다 — 관리자 대시보드가 4열 격자에 카드 3장이라 건너뛰고,
      // 아래의 '본문+곁열' 2열을 KPI 열 수인 것처럼 보고했다. 모른다고 하는 것보다
      // **틀린 숫자를 자신 있게 말하는 것이 나쁘다.** 카드가 둘 이상이면 카드 격자로 본다.
      if (kids.length < 2) continue;
      // 자식이 카드류여야 '카드 격자'다. 라벨/입력이 늘어선 폼 격자는 세지 않는다.
      const cardish = kids.filter((k) =>
        k.matches('.card, .MuiCard-root, .MuiPaper-root') ||
        k.querySelector('.card, .MuiCard-root, .MuiPaper-root')).length;
      if (cardish < Math.min(n, 2)) continue;
      cols = n; break;
    }
  }
  out.grid = { columns: cols };

  // ── 내용이 있기는 한가 ────────────────────────────────────────────────
  //
  // 기준 목업은 표본 데이터가 가득 차 있고, 우리 QA 계정은 화면에 따라 **0건**이다.
  // 그 상태에서 "카드 0개 / 격자 없음" 을 디자인 불일치로 세면, 고칠 것이 없는 화면을
  // 고치러 가게 된다(내 티켓이 정확히 그랬다 — 캡처를 보니 "조건에 맞는 티켓이 없습니다").
  // 그래서 **내용이 없다는 사실을 지문에 싣고**, 비교 쪽에서 내용에 딸린 항목만 제외한다.
  out.content = {
    tableRows: main ? main.querySelectorAll('tbody tr').length : 0,
    emptyMarker: !!(main && [...main.querySelectorAll('.k-empty')].some(vis)),
  };

  // ── 타이포 ────────────────────────────────────────────────────────────
  const h1 = pick('h1, .page-title, .MuiTypography-h1, .MuiTypography-h4');
  out.type = {
    h1: h1 ? num(getComputedStyle(h1).fontSize) : null,
    h1Weight: h1 ? getComputedStyle(h1).fontWeight : null,
    body: num(body.fontSize),
    family: (body.fontFamily || '').split(',')[0].replace(/["']/g, ''),
  };

  // ── 컨트롤 ────────────────────────────────────────────────────────────
  // `button` 을 그냥 세면 안 된다 — StatCard 같은 **카드가 button 으로 렌더**되는 곳이 있어
  // (`k-stat`, 높이 110px) 평균 높이가 실제보다 낮게 나온다. 실제로 그래서 "버튼 높이 33px"
  // 이라는 오측정이 나왔고, 진짜 버튼은 40px 로 기준과 이미 맞아 있었다.
  // 조건: 버튼처럼 생긴 것만 — 60px 이하이고, 안에 카드를 품고 있지 않다.
  // 세 번을 잘못 쟀다. 그때마다 "버튼이 작다"는 결론이 나왔지만 실제 본문 버튼은 40px 로
  // 기준과 이미 같았다. 평균을 끌어내린 것들:
  //   * `Link component="button"` (본문 링크·티켓 제목) — <button> 이지만 19px 이다.
  //   * 상단바의 사용자/관리자 세그먼트(31px)와 브랜드 버튼(42px) — 셸이지 화면이 아니다.
  //   * `StatCard` (`k-stat`, 110px) — 카드가 button 으로 렌더된다.
  // 그래서 **본문 안의, 링크가 아닌, 카드를 품지 않은, 60px 이하** 만 센다.
  const btnScope = main || document.body;
  const btns = [...btnScope.querySelectorAll('button, .btn, .MuiButton-root')].filter(vis)
    .filter((b) => (b.textContent || '').trim().length > 1)
    .filter((b) => !b.matches('.MuiLink-root') && !b.closest('.MuiLink-root'))
    // 아이콘 버튼(원형, 아이콘 하나)은 **다른 부류의 컨트롤**이다. 글자 버튼과 크기 척도가
    // 달라(아이콘 크기로 정해진다) 같이 평균 내면 화면마다 값이 내려간다 — 새 티켓의
    // 본문 서식 도구 막대(32px 컨트롤 12개)가 표준 버튼 2개를 덮어 "33px" 이 나왔다.
    .filter((b) => !b.matches('.MuiIconButton-root') && !b.closest('.MuiIconButton-root'))
    // 칩도 마찬가지다. `Chip component="button"` 은 눌리지만 **버튼이 아니라 칩**이고
    // 자체 크기 척도(24/32px)를 갖는다 — 게시글의 반응 이모지 6개(24px)가 진짜 버튼
    // 5개(전부 40px)를 덮어 평균 31px 이 나왔다. 목업에는 반응 기능 자체가 없다.
    .filter((b) => !b.matches('.MuiChip-root') && !b.closest('.MuiChip-root'))
    .filter((b) => !b.querySelector('.card, .MuiCard-root, .MuiPaper-root'))
    .filter((b) => b.getBoundingClientRect().height <= 60);
  const bh = btns.map((b) => Math.round(b.getBoundingClientRect().height)).filter((h) => h > 16 && h < 80);
  const br = new Set(btns.slice(0, 40).map((b) => Math.round(num(getComputedStyle(b).borderTopLeftRadius) ?? 0)));
  // 숨은 native 입력(`MuiSelect-nativeInput`, 접근성용 프록시)은 높이가 16~21px 이라
  // 그걸 잡으면 "입력 높이 13px" 같은 값이 나온다. 실제로 보이는 것만 본다.
  const input = [...document.querySelectorAll(
      'input[type=text], input[type=search], .MuiInputBase-root, input')]
    .filter(vis).filter((el) => el.getBoundingClientRect().height >= 24)[0] || null;
  out.controls = {
    buttonCount: btns.length,
    buttonH: bh.length ? Math.round(bh.reduce((a, b) => a + b, 0) / bh.length) : null,
    buttonRadii: [...br].sort((a, b) => a - b),
    inputH: input ? Math.round(input.getBoundingClientRect().height) : null,
  };

  // ── 밀도 ──────────────────────────────────────────────────────────────
  /* 카드 **사이** 간격만 잰다 — 같은 부모 아래, 세로로 이어지는 두 카드.
   *
   * 예전에는 DOM 순서로 이웃한 두 카드의 거리를 그냥 셌다. 그러면 배너 더미(서로 붙어 있어
   * 0px)와 배너→본문 점프(118px)가 같이 섞여 평균이 44px 로 나왔다. 실제 카드 간격은
   * 16~20px 로 기준(18px)과 이미 같았는데, 그 오측정을 믿었으면 멀쩡한 28화면을 "고쳤을" 것이다.
   *
   * 조건: 같은 부모 + 같은 열(x 가 겹침) + 아래로 이어짐. 그리고 평균이 아니라 **중앙값**을
   * 쓴다 — 한 화면에 예외적으로 넓은 자리 하나가 있어도 전체 리듬을 대표하지 않는다. */
  let gaps = [];
  {
    const byParent = new Map();
    for (const c of cards) {
      const p = c.parentElement;
      if (!p) continue;
      if (!byParent.has(p)) byParent.set(p, []);
      byParent.get(p).push(c);
    }
    for (const sibs of byParent.values()) {
      const boxes = sibs.map((el) => el.getBoundingClientRect())
        .sort((a, b) => a.top - b.top);
      for (let i = 1; i < boxes.length; i++) {
        const prev = boxes[i - 1], cur = boxes[i];
        if (cur.top - prev.bottom < 0) continue;                 // 겹침
        if (cur.left >= prev.right || cur.right <= prev.left) continue;  // 다른 열
        const g = Math.round(cur.top - prev.bottom);
        if (g >= 0 && g <= 96) gaps.push(g);
      }
    }
    gaps.sort((a, b) => a - b);
  }
  out.density = {
    cardGap: gaps.length ? gaps[Math.floor(gaps.length / 2)] : null,   // 중앙값
    mainPadding: main ? Math.round(num(getComputedStyle(main).paddingLeft) ?? 0) : null,
  };

  out.textSample = (main || document.body).innerText.replace(/\s+/g, ' ').trim().slice(0, 160);
  return out;
}
"""


# 기준과 **의도적으로** 다른 것들. 기준은 하한선이지 상한선이 아니다 — 더 나은 답이 분명하면
# 개선하되, 그 판단을 여기 적어 둔다. 적지 않으면 시트가 영원히 빨갛고 아무도 안 보게 된다.
#
# 규칙: 이유를 한 줄로 못 쓰면 의도가 아니라 결함이다. 여기 넣지 말고 고쳐라.
# 화면별 의도된 차이. 항목 전체가 아니라 **그 화면에서만** 의도인 경우다.
INTENTIONAL_PER_ROUTE: dict[tuple[str, str], str] = {
    # 관리자 대량 목록은 표를 유지한다. 기준 목업은 카드 격자로 그렸지만, 목업의 표본은
    # 한 화면에 5~8행이고 실제 데이터는 수백 행이다 — 카드로 그리면 한 화면에 4~6건만
    # 보이고 정렬·비교가 불가능해진다. 표는 정보 밀도가 생명인 자리의 옳은 답이다.
    **{(f"admin/{k}", "격자/열 수"): "관리자 대량 목록은 표를 유지한다(수백 행을 카드로 그리면 비교가 불가능하다)"
       for k in ("users", "audit", "jobs", "backups", "diagnostics", "departments",
                 "job-titles", "notion-mappings", "integrations", "runners", "workflows",
                 "prompts", "policies", "templates", "schedules", "document-generation",
                 "approvals", "notifications", "maintenance", "settings")},

    # 버튼 높이 — **목업이 화면마다 다르고 우리는 하나다.** 실측 분포:
    #   기준 목업: 29·34·35·36(2)·37(5)·38(2)·39(18)·40(6)·42 — **9종**
    #   우리 앱  : 40 이 35화면 중 31 (나머지는 아래 두 줄에 이유가 있다)
    # 목업은 손으로 만든 화면 모음이라 화면마다 padding 이 조금씩 다르고, 우리 값은
    # 테마 토큰 하나에서 나온다. **한 값으로 고른 쪽이 낫다** — 목업의 최빈값 39 와도 1px
    # 차이다. 이 셋은 목업 자신의 바깥값이므로 우리를 거기에 맞추지 않는다.
    ("unassigned-tickets", "컨트롤/버튼 높이"): "목업의 바깥값(29px). 우리는 토큰 하나로 40px 고정 — 목업 최빈값 39와 1px 차",
    ("board", "컨트롤/버튼 높이"): "목업의 바깥값(34px). 우리는 토큰 하나로 40px 고정 — 목업 최빈값 39와 1px 차",

    # 새 티켓만 우리 쪽이 낮다(34px). 본문 서식 도구 막대(제목·글머리·번호·구분선)가
    # 32px 컨트롤이라 평균을 내린다 — **목업에는 그 도구 막대가 없다.** 기능을 빼서 숫자를
    # 맞추지는 않는다: 서식 도구가 있는 편이 티켓 본문을 쓰기에 낫다.
    ("new-ticket", "컨트롤/버튼 높이"): "본문 서식 도구 막대(32px)가 평균을 내린다 — 목업에는 없는 기능이고, 빼서 숫자를 맞추지 않는다",

    # 댓글 입력이 여러 줄이다(77px). 목업은 한 줄(41px)인데, 댓글은 한 줄로 끝나지 않는다 —
    # 실제로 이 저장소의 댓글에는 문단과 목록이 들어간다. 한 줄 입력은 쓰는 동안 앞이 안 보인다.
    ("board-post", "컨트롤/입력 높이"): "댓글은 여러 줄로 쓴다 — 한 줄 입력(41px)은 쓰는 동안 앞 내용이 안 보인다",

    # 지표 타일 격자 — 버튼 높이와 **같은 구조**다. 실측 분포:
    #   기준 목업: 2(4)·3(18)·4(3)·**5(1)** — 5열은 26화면 중 **딱 이 화면 하나**
    #   우리 앱  : 4 가 8화면 (공유 토큰 `STAT_GRID` 하나에서 나온다)
    # 목업이 이 화면에서만 5열을 쓴 것은 마침 머리 지표가 5개였기 때문이지 규칙이 아니다.
    # 우리는 토큰 하나로 전 화면이 같은 열 수를 쓴다 — 그쪽이 낫다.
    #
    # ⚠️ **다만 이 화면에는 진짜 차이가 따로 있다.** 기준은 머리 지표 다섯(러너·워크플로·
    # 성공률·지연 작업·디스크)을 **맨 위 한 줄에** 모으는데, 우리는 같은 값을 여섯 구역에
    # 흩어 놓아 스크롤해야 한다. 그건 열 수가 아니라 **정보 구조**의 문제이고 6단계에서
    # 다룬다 — 이 항목을 '의도' 로 적는 것이 그 사실을 지우지 않는다.
    ("admin/dashboard", "격자/열 수"): "지표 격자는 토큰 하나로 전 화면 4열. 목업의 5열은 26화면 중 하나뿐인 일회성(머리 지표 재배치는 6단계)",
}

INTENTIONAL: dict[str, str] = {
    "타이포/글꼴": (
        "목업은 시스템 글꼴 스택을 쓰고 우리는 Pretendard 를 자체 호스팅한다. "
        "한글 자간·굵기가 확연히 낫고, 사용자가 웹폰트를 허용했다(2026-08-04)."
    ),
}


@dataclass
class Diff:
    """한 항목의 차이. `ok` 면 허용 오차 안이거나 의도된 차이다."""

    key: str
    baseline: object
    ours: object
    ok: bool
    note: str = ""
    intentional: bool = False
    # 한쪽에 값이 없어 **비교 자체가 성립하지 않는** 경우. "다르다" 와 구분한다 —
    # 섞어 놓으면 고칠 것이 몇 개인지 알 수 없고, 실제로 그래서 없는 결함을 좇았다.
    incomparable: bool = False


@dataclass
class ScreenResult:
    route: str
    our_path: str | None
    diffs: list[Diff] = field(default_factory=list)
    error: str = ""

    @property
    def mismatches(self) -> list[Diff]:
        """고쳐야 할 차이만. 허용 오차 안·의도된 것·잴 수 없는 것은 뺀다."""
        return [d for d in self.diffs
                if not d.ok and not d.intentional and not d.incomparable]

    @property
    def incomparable(self) -> list[Diff]:
        return [d for d in self.diffs if d.incomparable and not d.ok]

    @property
    def intended(self) -> list[Diff]:
        return [d for d in self.diffs if d.intentional and not d.ok]


def _close(a, b, tol) -> bool:
    if a is None or b is None:
        return a == b
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def _color_close(a, b) -> bool:
    if not a or not b or len(a) < 3 or len(b) < 3:
        return a == b
    return all(abs(x - y) <= TOLERANCE["color_channel"] for x, y in zip(a[:3], b[:3]))


# 화면에 **내용이 없으면** 잴 수 없는 항목들. 기준 목업은 표본 데이터가 가득한데 우리
# QA 계정은 화면에 따라 0건이다 — 그 상태의 "카드 0개" 는 디자인이 아니라 데이터 얘기다.
# 버튼·입력·타이포·셸은 빈 화면에서도 그려지므로 여기 넣지 않는다(진짜 결함을 숨기게 된다).
CONTENT_DEPENDENT = frozenset({
    "카드/반지름 종류 수", "카드/반지름 값", "카드/그림자 비율%", "카드/높이 편차",
    "격자/열 수", "밀도/카드 간격", "컨트롤/버튼 반지름", "컨트롤/버튼 높이",
})


def _is_empty_screen(fp: dict) -> bool:
    """우리 화면이 '보여 줄 것이 없다' 고 말하고 있는가."""
    c = fp.get("content") or {}
    return bool(c.get("emptyMarker")) and not c.get("tableRows")


CARD_METRICS = frozenset({
    "카드/반지름 종류 수", "카드/반지름 값", "카드/그림자 비율%", "카드/높이 편차",
})


def compare(base: dict, ours: dict, route_id: str = "") -> list[Diff]:
    """지문 두 개를 항목별로 비교한다. 판정 규칙이 여기 한 곳에만 있어야 한다."""
    d: list[Diff] = []
    ours_empty = _is_empty_screen(ours)
    # 기준에 카드가 **하나도 없으면** 카드 항목은 비교 대상이 없다. `종류 수 0` 은 목표가
    # 아니라 부재다 — 그걸 상한으로 쓰면 "카드를 쓰지 마라" 가 되어, 우리 화면이 같은
    # 모양을 카드 마크업으로 그렸다는 이유만으로 영원히 실패한다(채팅방이 그랬다:
    # 목업의 대화 껍데기는 `div`, 우리 것은 `Card` — 캡처로 보면 둘이 같은 흰 둥근 판이다).
    base_has_no_cards = not (base.get("cards", {}) or {}).get("count")

    def add(key, b, o, ok, note=""):
        reason = INTENTIONAL.get(key) or INTENTIONAL_PER_ROUTE.get((route_id, key))
        # 한쪽에만 값이 없으면 "다르다" 가 아니라 "잴 수 없다" 다. 예: 기준의 카드들이
        # 형제가 아니라 간격을 못 재는 화면에서, 우리 20px 을 '틀렸다' 고 셀 수는 없다.
        # 단, `격자/열 수` 는 **없다는 사실 자체가 결과**다(우리는 표, 기준은 카드 격자 = R7).
        one_sided = (b is None) != (o is None)
        incomparable = one_sided and key != "격자/열 수"
        # 우리 화면이 빈 상태면 내용에 딸린 항목은 비교할 수 없다. 이걸 안 하면 데이터가
        # 없는 화면마다 "카드가 없다 / 버튼이 없다" 가 쌓여, 고칠 것이 없는 화면을 고치러 간다.
        empty_note = ""
        if ours_empty and key in CONTENT_DEPENDENT:
            incomparable = True
            empty_note = "우리 화면이 빈 상태다(표시할 데이터 없음) — 내용에 딸린 항목은 못 잰다"
        elif base_has_no_cards and key in CARD_METRICS:
            incomparable = True
            empty_note = "기준 화면에 카드가 없다 — 비교할 대상이 없다"
        d.append(Diff(
            key, b, o, ok,
            note or reason or empty_note or ("한쪽에 값이 없어 비교할 수 없다" if incomparable else ""),
            intentional=bool(reason), incomparable=incomparable,
        ))

    bs, os_ = base.get("shell", {}), ours.get("shell", {})
    add("셸/상단바 높이", bs.get("topbarH"), os_.get("topbarH"),
        _close(bs.get("topbarH"), os_.get("topbarH"), TOLERANCE["height_px"] * 2))
    add("셸/상단바 그라데이션", bs.get("topbarGradient"), os_.get("topbarGradient"),
        bs.get("topbarGradient") == os_.get("topbarGradient"))
    add("셸/사이드바 폭", bs.get("sidebarW"), os_.get("sidebarW"),
        _close(bs.get("sidebarW"), os_.get("sidebarW"), 16))
    add("셸/본문 비율%", bs.get("mainPct"), os_.get("mainPct"),
        _close(bs.get("mainPct"), os_.get("mainPct"), TOLERANCE["ratio_pct"]))

    bc, oc = base.get("color", {}), ours.get("color", {})
    add("색/배경", bc.get("bg"), oc.get("bg"), _color_close(bc.get("bg"), oc.get("bg")))
    add("색/본문 글자", bc.get("text"), oc.get("text"), _color_close(bc.get("text"), oc.get("text")))
    add("색/강조", bc.get("accent"), oc.get("accent"), _color_close(bc.get("accent"), oc.get("accent")))

    bk, ok_ = base.get("cards", {}), ours.get("cards", {})
    add("카드/반지름 종류 수", bk.get("radiusKinds"), ok_.get("radiusKinds"),
        (ok_.get("radiusKinds") or 0) <= (bk.get("radiusKinds") or 0),
        "우리가 기준보다 많으면 실패 — 한 화면에 여러 반지름이 섞여 있다는 뜻")
    add("카드/반지름 값", bk.get("radii"), ok_.get("radii"),
        bool(set(bk.get("radii") or []) & set(ok_.get("radii") or [])) or not bk.get("radii"))
    add("카드/그림자 비율%", bk.get("shadowRatio"), ok_.get("shadowRatio"),
        _close(bk.get("shadowRatio"), ok_.get("shadowRatio"), 34))
    add("카드/높이 편차", bk.get("heightSpread"), ok_.get("heightSpread"),
        (ok_.get("heightSpread") or 0) <= max((bk.get("heightSpread") or 0) * 1.5, 120),
        "같은 격자 안 카드 높이가 들쭉날쭉하면 실패")

    add("격자/열 수", base.get("grid", {}).get("columns"), ours.get("grid", {}).get("columns"),
        base.get("grid", {}).get("columns") == ours.get("grid", {}).get("columns"))

    bt, ot = base.get("type", {}), ours.get("type", {})
    add("타이포/제목 크기", bt.get("h1"), ot.get("h1"), _close(bt.get("h1"), ot.get("h1"), 4))
    add("타이포/본문 크기", bt.get("body"), ot.get("body"), _close(bt.get("body"), ot.get("body"), TOLERANCE["font_px"]))
    add("타이포/글꼴", bt.get("family"), ot.get("family"), bt.get("family") == ot.get("family"))

    bn, on = base.get("controls", {}), ours.get("controls", {})
    add("컨트롤/버튼 높이", bn.get("buttonH"), on.get("buttonH"), _close(bn.get("buttonH"), on.get("buttonH"), TOLERANCE["height_px"]))
    add("컨트롤/버튼 반지름", bn.get("buttonRadii"), on.get("buttonRadii"),
        bool(set(bn.get("buttonRadii") or []) & set(on.get("buttonRadii") or [])) or not bn.get("buttonRadii"))
    add("컨트롤/입력 높이", bn.get("inputH"), on.get("inputH"), _close(bn.get("inputH"), on.get("inputH"), TOLERANCE["height_px"] * 2))

    bd, od = base.get("density", {}), ours.get("density", {})
    add("밀도/카드 간격", bd.get("cardGap"), od.get("cardGap"), _close(bd.get("cardGap"), od.get("cardGap"), TOLERANCE["gap_px"]))
    add("밀도/본문 여백", bd.get("mainPadding"), od.get("mainPadding"), _close(bd.get("mainPadding"), od.get("mainPadding"), 12))

    return d


def render_sheet(results: list[ScreenResult]) -> str:
    """사람이 읽는 대조 시트."""
    lines: list[str] = []
    total = sum(len(r.diffs) for r in results)
    bad = sum(len(r.mismatches) for r in results)
    covered = [r for r in results if not r.error]
    lines.append("# 기준 대조 시트")
    lines.append("")
    skipped = sum(len(r.incomparable) for r in results)
    lines.append(
        f"화면 {len(covered)}/{len(results)} · 항목 {total}개 중 **{bad}개 불일치**"
        + (f" (그 밖에 {skipped}개는 한쪽에 값이 없어 비교 불가)" if skipped else "")
    )
    lines.append("")
    lines.append("판정은 허용 오차 기준이다(반지름 2px, 색 12/255, 폭 5%, 글자 1.5px).")
    lines.append("픽셀 diff 는 쓰지 않는다 — 기준은 목업이고 우리는 실제 데이터가 든 앱이다.")
    lines.append("")

    lines.append("## 화면별 요약")
    lines.append("")
    lines.append("| 화면 | 우리 경로 | 불일치 | 가장 큰 차이 |")
    lines.append("|---|---|---|---|")
    for r in sorted(results, key=lambda x: -len(x.mismatches)):
        if r.error:
            lines.append(f"| `{r.route}` | {r.our_path or '—'} | — | ⚠️ {r.error} |")
            continue
        worst = r.mismatches[0].key if r.mismatches else "—"
        mark = "✅" if not r.mismatches else f"**{len(r.mismatches)}**"
        lines.append(f"| `{r.route}` | `{r.our_path or '없음'}` | {mark} | {worst} |")
    lines.append("")

    intended = [(r, d) for r in results for d in r.intended]
    if intended:
        lines.append("## 기준과 다르지만 의도한 것")
        lines.append("")
        lines.append("기준은 하한선이다. 더 나은 답이 분명하면 개선하고 이유를 여기 남긴다.")
        lines.append("")
        lines.append("| 항목 | 기준 | 우리 | 이유 |")
        lines.append("|---|---|---|---|")
        seen_keys = set()
        for _, d in intended:
            if d.key in seen_keys:
                continue
            seen_keys.add(d.key)
            lines.append(f"| {d.key} | `{d.baseline}` | `{d.ours}` | {d.note} |")
        lines.append("")

    lines.append("## 불일치 상세")
    lines.append("")
    for r in results:
        if not r.mismatches:
            continue
        lines.append(f"### `{r.route}` → `{r.our_path}`")
        lines.append("")
        lines.append("| 항목 | 기준 | 우리 | 비고 |")
        lines.append("|---|---|---|---|")
        for d in r.mismatches:
            lines.append(f"| {d.key} | `{d.baseline}` | `{d.ours}` | {d.note} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔 기본 코드페이지(cp949)는 '—' 같은 글자를 못 찍어 UnicodeEncodeError 로
    # 죽는다. 결과 파일은 UTF-8 로 잘 써 놓고 **출력 한 줄 때문에 도구가 실패**하는 것은
    # 말이 안 되므로, 찍을 수 없는 글자는 대체 문자로 흘린다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="기준 목업 ↔ 우리 화면 대조")
    ap.add_argument("--out", default="dist/baseline", help="결과를 쓸 디렉터리")
    ap.add_argument("--base-url", default="http://127.0.0.1:8080", help="우리 앱 주소")
    ap.add_argument("--routes", default="", help="쉼표로 구분한 목업 라우트(비우면 전체)")
    ap.add_argument("--viewport", default="1920x1080")
    ap.add_argument("--theme", default="light", choices=("light", "dark"))
    ap.add_argument("--shots", action="store_true", help="좌우 스크린샷도 남긴다")
    args = ap.parse_args(argv)

    if not BASELINE_HTML.exists():
        print(f"기준 파일이 없다: {BASELINE_HTML}", file=sys.stderr)
        print("scripts/ui_qa/README.md 의 '기준 목업 들여오기' 참조.", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    from scripts.ui_qa import capture as capture_mod
    from scripts.ui_qa import routes as routes_mod
    from scripts.ui_qa.auth import ensure_session

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    shot_dir = out_dir / "shots"
    if args.shots:
        shot_dir.mkdir(exist_ok=True)

    wanted = [r.strip() for r in args.routes.split(",") if r.strip()] or list(ROUTE_MAP)
    w, h = (int(x) for x in args.viewport.split("x"))
    results: list[ScreenResult] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # 1) 기준 목업 — 로그인 불필요, 해시로 구동한다.
        base_ctx = browser.new_context(viewport={"width": w, "height": h}, locale="ko-KR")
        base_page = base_ctx.new_page()
        base_prints: dict[str, dict] = {}
        for route in wanted:
            try:
                base_page.goto(f"{BASELINE_HTML.as_uri()}#/{route}", wait_until="load", timeout=40000)
                base_page.evaluate("(t) => { document.documentElement.dataset.theme = t; }", args.theme)
                base_page.wait_for_timeout(700)
                base_prints[route] = base_page.evaluate(FINGERPRINT_JS)
                if args.shots:
                    base_page.screenshot(path=str(shot_dir / f"{route.replace('/', '_')}__기준.png"),
                                         full_page=True)
            except Exception as exc:  # noqa: BLE001 — 한 화면 실패가 전체를 멈추면 안 된다
                base_prints[route] = {"_error": f"{type(exc).__name__}: {exc}"}
        base_ctx.close()

        # 2) 우리 앱 — 로그인이 필요하다.
        session = ensure_session(browser, args.base_url, REPO / "dist" / "ui-qa", log=lambda *a: None)
        ctx = browser.new_context(storage_state=session.storage_state, viewport={"width": w, "height": h},
                                  locale="ko-KR")
        page = ctx.new_page()

        # 상세 화면 경로를 실제 데이터에서 해석한다. 데이터가 없으면 그 화면은 대조하지
        # 못하고 이유가 시트에 남는다 — 커버리지를 지어내지 않는다.
        detail_paths: dict[str, str | None] = {}
        by_id = {r.id: r for r in routes_mod.ALL_ROUTES}
        for mock_route, harness_id in DETAIL_ROUTES.items():
            hr = by_id.get(harness_id)
            if hr is None:
                detail_paths[mock_route] = None
                continue
            hash_path, _note = capture_mod.discover_detail_hash(
                ctx, args.base_url, hr, log=lambda *a: None)
            detail_paths[mock_route] = f"#{hash_path}" if hash_path else None

        for route in wanted:
            our = detail_paths.get(route) if route in DETAIL_ROUTES else ROUTE_MAP.get(route)
            base_fp = base_prints.get(route, {})
            if "_error" in base_fp:
                results.append(ScreenResult(route, our, error=f"기준 렌더 실패: {base_fp['_error']}"))
                continue
            if our is None:
                results.append(ScreenResult(route, None, error="우리 앱에 대응 라우트를 아직 정하지 않았다(상세 화면)"))
                continue
            try:
                # 관리자 화면은 **관리자 셸**(`/admin`)에서 열어야 한다. 사용자 셸(`/`)에
                # 관리자 해시를 붙이면 라우트가 안 맞아 빈 화면이나 다른 화면이 뜨고,
                # 그 지문을 기준과 비교하게 된다(실제로 관리자 화면의 입력이 전부
                # "없음" 으로 나왔다 — 화면 자체가 그 화면이 아니었다).
                shell = "/admin" if route.startswith("admin/") else "/"
                # ⚠️ **해시만 바뀌는 이동은 문서를 다시 읽지 않는다.** `page` 를 화면마다
                # 재사용하는데 HashRouter 라서, `goto()` 는 즉시 반환하고 React 가 라우트를
                # 갈아끼우는 동안 우리는 **이전 화면의 DOM 을 잰다**. 그래서 같은 화면이
                # 단독 실행에서는 불일치 0건인데 전체 실행에서는 "격자 없음 / 버튼 없음"
                # 으로 나왔다 — 측정이 **라우트 순서에 따라 달라졌다**.
                #
                # 그래서 ① 이동한 뒤 문서를 강제로 다시 읽고 ② 고정 대기 대신 하네스의
                # `_settle`(스켈레톤·networkidle·폰트)을 쓴다. 대조 도구만 고정 1400ms 를
                # 쓰고 있었다 — 같은 저장소 안에서 규율이 갈려 있었다.
                page.goto(f"{args.base_url}{shell}{our}", wait_until="domcontentloaded", timeout=40000)
                page.reload(wait_until="domcontentloaded", timeout=40000)
                capture_mod._settle(page, settle_ms=600, timeout_ms=20000)
                ours_fp = page.evaluate(FINGERPRINT_JS)
                if args.shots:
                    page.screenshot(path=str(shot_dir / f"{route.replace('/', '_')}__우리.png"), full_page=True)
                results.append(ScreenResult(route, our, diffs=compare(base_fp, ours_fp, route)))
            except Exception as exc:  # noqa: BLE001
                results.append(ScreenResult(route, our, error=f"우리 화면 렌더 실패: {type(exc).__name__}"))

        ctx.close()
        browser.close()

    payload = [
        {
            "route": r.route, "ourPath": r.our_path, "error": r.error,
            "diffs": [{"key": d.key, "baseline": d.baseline, "ours": d.ours, "ok": d.ok,
                       "note": d.note, "intentional": d.intentional,
                       "incomparable": d.incomparable}
                      for d in r.diffs],
        }
        for r in results
    ]
    (out_dir / "baseline_diff.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    sheet = render_sheet(results)
    (out_dir / "baseline_sheet.md").write_text(sheet, encoding="utf-8")

    print(sheet[:4000])
    bad = sum(len(r.mismatches) for r in results)
    print(f"\n결과: {out_dir / 'baseline_sheet.md'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
