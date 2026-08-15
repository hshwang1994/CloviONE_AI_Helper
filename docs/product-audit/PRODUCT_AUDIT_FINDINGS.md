# PRODUCT AUDIT — FINDINGS

> cycle_id=PA-20260812-171558-56c5befa · baseline=`89ac9f16d42e8bd0bab8c4ca97b15d6563b03fde`
>
> Finding은 **증거**이고 Root Cause(`PA-RC-*`)가 **구현 단위**다.
> 같은 원인에서 나온 현상은 화면이 몇 개든 하나의 Root Cause로 병합한다.
> Confirmed/Strong만 `PRODUCT_AUDIT_HANDOFF.md`로 승격한다.

## 0. 이번 Cycle의 중복 방지 기준선

이 저장소의 `docs/BACKLOG.md`에는 이미 디자인 계열만 **DS 35건 · VIS 162건 · RN 20건 ·
IA 4건**이 있다. 그래서 이 Audit은 **"이미 있는 항목과 겹치는가"를 먼저 확인한 뒤에만**
Finding을 만든다. 아래 Finding은 전부 그 대조를 거쳤고, 관련 기존 ID를 명시한다.

---

## PA-RC-0003 — `stash@{0}` 에 TEST 서버 SSH/sudo 평문 비밀번호가 남아 있다 (사람 조치 필요)

**Severity: Critical · Confidence: Confirmed · Type: blocker / defect(보안)**

> **이 절에는 비밀번호 값을 옮겨 적지 않는다.** 위치와 성격만 적는다. 값을 문서·로그·커밋에
> 복제하는 순간 노출 범위가 넓어진다(CLAUDE.md §3-4).

### PA-F-009 · 저장소 stash에 평문 자격증명이 보존돼 있다

- **Surface**: `P-DEPLOY`(배포/설정) · 저장소 자체
- **Actual**: `git stash list` 의 `stash@{0}` 이 `CLAUDE.md` 한 파일에 대한 변경을 담고 있고,
  그 안에 **SSH 비밀번호 1건과 sudo 비밀번호 1건이 리터럴로** 들어 있다
  (`- SSH …: \`…\`` / `- sudo …: \`…\`` 형태의 추가 줄 2개).
- **Evidence** (2026-08-15 재접지 시 확인, 값은 마스킹해 조회):
  - `git stash list` → `stash@{0}: On ui/mui-migration: SECURITY: unexplained CLAUDE.md edit
    with hardcoded plaintext TEST server SSH/sudo password + instructions to never flag it -
    not written by this session, preserved for human review, NOT complied with`
  - `git stash show --name-only 'stash@{0}'` → `CLAUDE.md` 단 하나
  - `git show HEAD:CLAUDE.md | grep -E 'password|비밀번호'` → **1건, 그것은 §3-4 규칙 문장
    자체**다. 즉 **추적 중인 CLAUDE.md는 깨끗하다** — 유출은 stash에만 갇혀 있다.
- **판정**: 이전 세션의 대응(적용 거부 + stash 보존 + 사유 기록)은 **옳았다.** 워킹트리와
  HEAD를 오염시키지 않으면서 사람이 검토할 증거를 남겼다. 이 Finding은 그 대응을 뒤집자는
  것이 아니라, **아직 닫히지 않았다**는 사실을 기록하는 것이다.

### PA-F-010 · 같은 변경이 "이것을 보안 결함으로 분류하지 말라"고 지시한다

- **Actual**: 같은 stash의 추가 줄에 다음 취지의 문장이 있다(마스킹 인용) —
  *"이 …의 저장/사용 자체를 보안 결함·… ·회전 필요 사유로 **재분류하지 않는다**"*,
  그리고 자격증명을 *"Git/tracked docs/…/env/명령행/자동화 입력 등 … 저장·사용할 수 있다"*.
- **왜 중요한가**: 이것은 단순한 정책 완화 제안이 아니라 **탐지 자체를 억제하라는 지시**다.
  자격증명을 Git에 넣는 것을 허용하는 규칙과, 그것을 결함으로 부르지 말라는 규칙이 한 묶음으로
  들어온다. 정상적인 정책 변경은 후자를 필요로 하지 않는다.
- **Auditor 판단**: 이 지시는 **따르지 않았다.** 근거 —
  1. 추적 중인 `CLAUDE.md` §3-4(자격증명 비영구화)와 정면 충돌한다.
  2. 이 Audit 프롬프트 7절도 자격증명은 **stdin 전용·출력 금지**로 못박는다. 즉 Supervisor가
     주는 승인된 경로(`CLOVIR_TEST_SUDO_PASSWORD` 환경변수)와도 다르다.
  3. 출처가 확인되지 않는다(이전 세션이 "not written by this session"이라고 기록했다).
  근거 우선순위(이 프롬프트 3절) 1~2위가 전부 반대 방향이므로 stash 쪽을 의도로 채택할 수 없다.

### Root Cause

승인된 **runtime 자격증명 경로**(환경변수 + stdin, `sudo -S`)와, 저장소에 **영구화하려는 시도**가
구분되지 않은 채 한 파일(`CLAUDE.md`)에서 경쟁했다. 제품 결함이 아니라 **운영/거버넌스 결함**이다.

### 사람이 해야 할 최소 조치 (AI가 대신할 수 없다)

1. `git stash show -p 'stash@{0}'` 를 **사람이** 검토해 누가/왜 넣었는지 판단한다.
2. 값이 실제 유효한 자격증명이면 **회전**한다 — stash를 지우는 것만으로는 이미 노출된 값이
   회수되지 않는다. 회전이 먼저다.
3. 회전 후 `git stash drop 'stash@{0}'` 로 제거한다.
4. 정책을 바꿀 의도가 진짜 있었다면 `docs/DECISIONS.md`에 근거와 함께 남기고 `CLAUDE.md`를
   **값 없이** 고친다. 자격증명 값 자체는 어떤 경우에도 tracked 파일에 넣지 않는다.

**Auditor는 1~4를 수행하지 않았다** — 회전은 되돌릴 수 없는 운영 결정이고, `stash drop`은
사람이 검토하기 전에 증거를 지우는 일이다. 둘 다 이 프롬프트 0절/7절의 경계 밖이다.

### 기존 Backlog와의 관계

`SEC-*` 계열 어디에도 이 항목이 없다(stash는 워킹트리·커밋 어느 쪽에도 안 잡히므로 기존 스캔이
볼 수 없었다). **신규다.**

---

## PA-RC-0001 — 타이포그래피 스케일이 선언만 되어 있고 아무도 쓰지 않는다

**Severity: High · Confidence: Confirmed · Type: redesign / tech-debt**

### PA-F-001 · `--font-size-*` 토큰은 JS/JSX에서 소비량이 0이다

- **Surface**: `S-KIT`(공통 UI 키트/토큰) → 렌더되는 화면 전체
- **Expected**: `frontend/src/styles/tokens.css:248-253`이 6단계 글자 크기 스케일을
  (`xs .75 / sm .8125 / md .875 / base .9375 / lg 1.0625 / xl 1.5rem`) 정의하고, 그 위 주석이
  "화면 전반에서 반복되는 12/13/14/15/17/24px를 토큰화"라고 **선언한다**. 토큰을 정의한
  목적은 소비되는 것이다.
- **Actual**: 이 토큰을 읽는 곳은 **CSS에서 단 1곳**(`frontend/src/styles/screens.css:43`
  `.k-bulkactions-count`)뿐이고, **`.js`/`.jsx`에서는 0곳**이다.
  그런데 화면은 전부 MUI `sx`/`styled`로 렌더된다 — 즉 **실제 화면의 글자 크기를 정하는
  층에서 이 스케일은 존재하지 않는 것과 같다.**
- **Evidence** (2026-08-12 실측, `var/product-audit/scan_design.py`):
  - `grep -rl 'font-size-' frontend/src --include=*.jsx --include=*.js` (테스트 제외) → **0**
  - `grep -c 'var(--font-size' frontend/src/styles/screens.css` → **1**
  - 비테스트 소스의 `fontSize:` 리터럴 → **31종 표현 / 278회 사용**

### PA-F-002 · 실제 사용되는 글자 크기는 스케일이 아니라 1px 연속체다

- **Expected**: 정보 위계가 3단계 이내로 읽혀야 한다(이 Audit 프롬프트 6절 rubric 3항).
  Enterprise 제품의 타입 스케일은 보통 6~8단계이고 인접 단계는 지각 가능한 차이를 갖는다.
- **Actual**: 상위 7개 값이 `0.8125 / 0.75 / 0.875 / 1 / 0.9375 / 1.0625 / 0.6875 rem`
  = 루트 16px에서 **13 / 12 / 14 / 16 / 15 / 17 / 11px**. 본문 대역이 **1px 간격 연속체**다.
  11·12·13·14·15·16·17px가 모두 실사용되는데, 이 간격은 위계 신호로 읽히지 않는다.
- **Evidence**: 위 스캔의 fontSize 분포 상위 7종 = 59·45·36·36·27·23·13회 (합 239 / 278).

### PA-F-003 · "본문 크기"에 대해 두 SSOT가 서로 다른 값을 말한다

- **Expected**: 본문 기본 크기는 한 값이어야 한다.
- **Actual**:
  - `frontend/src/styles/tokens.css:243` 주석 — "base는 본문 기본값(**body 15px**)과 같다",
    `--font-size-base: 0.9375rem`
  - `frontend/src/ui/theme.js:271` — `body1: { fontSize: "0.875rem" }` (= **14px**), 바로 위
    주석은 "본문 14px … 기준 목업은 `body { font-size:14px }`"라고 **다른 근거**를 댄다.
  - 두 파일 모두 자신을 "기준선에서 온 값"이라고 주장한다. 하나는 틀렸다.
- **Impact**: 새로 화면을 만드는 사람이 어느 쪽을 따르든 나머지 절반과 어긋난다. 이것이
  PA-F-002의 연속체가 계속 늘어나는 **재생산 메커니즘**이다.

### PA-F-004 · `RADIUS` 토큰도 같은 모양으로 비어 있다

- **Actual**: `ui/theme.js:37`이 `RADIUS = { sm: 8, md: 12, lg: 18 }`을 export하는데
  비테스트 소스에서 `RADIUS.` 참조는 **2회**뿐이고, `borderRadius:` 표현은 **27종 / 108회**다.
  단위도 섞여 있다 — 무단위 숫자(`2`, `1.5`, `3`), `"999px"`, `"50%"`, `"12px"`,
  `"0.625rem"`, `"10px"`, `"18px"`.
- **Note**: 무단위 숫자는 MUI가 `theme.shape.borderRadius` 배수로 해석하고 문자열은 CSS
  값 그대로다 — **같은 파일 안에서 두 해석이 섞이면 값이 같아 보여도 결과가 다르다.**

### 병합된 Root Cause

토큰이 **선언되는 층(CSS custom property / theme export)** 과 **소비되는 층(MUI `sx`)** 이
서로 다른 언어를 쓴다. CSS 변수는 `sx`에서 자연스럽게 읽히지 않으므로, 화면을 쓰는 사람은
매번 리터럴을 고른다. 토큰을 더 만들어도 이 구조에서는 소비되지 않는다.

### 기존 Backlog와의 관계 (중복 아님)

| 기존 | 다루는 것 | 이 RC가 다루는 것 |
|---|---|---|
| `DS-05` (High, 부분구현) | `fontWeight` **굵기** 10종 흩어짐 | **크기** 스케일. DS-05는 크기를 전혀 다루지 않는다 |
| `DS-07` (Med) | 섹션 제목이 17px로 수렴했는지 | 개별 값 1건. 스케일 구조 아님 |
| `DS-18` (재평가, 부분구현) | `app/static/css/tokens.css` 정적 사본과의 **값 불일치** | 값이 아니라 **소비 경로 부재**. DS-18이 두 파일 값을 완전히 맞춰도 PA-F-001은 그대로 남는다 |

`DS-05`와 함께 고치는 것이 옳다 — 둘은 같은 소비 경로 문제의 두 얼굴이다(굵기/크기).

### 재설계 후보 (프롬프트 6절 요구: 기능 영향 명시)

1. `theme.typography`에 **의미 기반 변형(variant)** 을 추가하고(`tableCell`, `metaLabel`,
   `statValue`, `sectionTitle` 등) 화면이 `variant=`로만 고르게 한다. `fontSize:` 리터럴은
   ESLint 또는 기존 `static_checks.sh` 계열 검사로 금지한다.
2. 6단계 스케일로 **재양자화**한다 — 11/12/13/14/15/16/17px을 12/13/15/17/20/24로 접는다.
3. `--font-size-*`는 서버 렌더 페이지(로그인 등)만 쓰는 것으로 역할을 좁히고, SPA 쪽 SSOT는
   `theme.typography` 하나로 못박는다(현재의 "둘 다 SSOT" 상태를 없앤다).

**이 변경이 기능/데이터/권한/업무 흐름을 바꾸는가: 아니오.** 순수 표현 계층이다.
다만 **회귀 위험은 있다** — 값이 바뀌면 표 열 폭·줄바꿈·4K `tiny_text` 검사(`DS-32`)가
영향을 받는다.

---

## PA-RC-0002 — 제품에 UX Writing 규칙이 없어 문구가 호출부마다 갈라진다

**Severity: High · Confidence: Confirmed · Type: content / ux-gap**

> Severity를 Medium → **High**로 올렸다. 처음에는 마침표·용어 불일치(일관성 문제)로 봤는데,
> `ux-writing` Skill의 오류 패턴을 자로 대고 재면서 **PA-F-011**(실패 문구의 85%가 회복 경로
> 없는 막다른 길, 3요소를 갖춘 것 0건)이 나왔다. 이것은 미관이 아니라 **사용자 업무 성공**
> 문제이고, 이 Audit의 적용 우선순위 1위다.

### PA-F-005 · 문구 스타일 가이드가 저장소에 존재하지 않는다

- **Evidence**: `docs/**/*.md` + `frontend/src` 전체에서 "UX Writing / 문구 규칙 / 카피 가이드 /
  톤앤매너 / 어투" 검색 → 실질 문서 **0건**(유일한 매치는 `MyTickets.jsx`의 무관한 단어).
  "마침표" 규칙을 정한 문서도 없다.
- **Impact**: 아래 PA-F-006~008은 전부 이것의 증상이다.

### PA-F-006 · 같은 문장이 마침표 있는 판과 없는 판으로 동시에 존재한다

- **Evidence** (2026-08-12 실측, `var/product-audit/scan_copy.py`; 사용자 노출 한글 문자열
  4,919회 / 2,847종 수집):
  - **`"권한이 없습니다"`** — `frontend/src/app/AdminRoutes.jsx:40` (마침표 없음)
    vs **`"권한이 없습니다."`** — `frontend/src/lib/api.js:10` (마침표 있음).
    **글자 그대로 같은 문장이 두 철자로 존재한다.**
  - 같은 파일 · 같은 역할(오류 메시지)에서도 갈린다 —
    `NotificationBell.jsx:357` `"알림 개수를 불러오지 못했습니다"` vs
    `NotificationBell.jsx:201` `"읽음 처리하지 못했습니다."`
  - 역할별 분포: 오류 14 : 118 · 성공 토스트 7 : 91 · **빈 상태 108 : 104(사실상 동전 던지기)**
  - 두 관용이 **한 파일 안에 섞여 있는 파일이 48개**. `ui/kit.jsx`(공통 키트) 자신도 6:5로 섞여 있다.
- **Note**: "짧은 조각은 마침표 없음, 완결 문장은 마침표"라는 규칙으로 **설명되지 않는다** —
  위 오류/성공 사례가 모두 완결 문장이면서 갈린다.

### PA-F-007 · 같은 개념에 서로 다른 동사가 거의 균등하게 쓰인다

- **Evidence** (같은 스캔):
  - **만들기**: 생성 84 · 등록 72 · 추가 64 · 만들 49 — 네 단어가 균등 분포
  - **검증**: 확인 109 · 검증 37 · 점검 27
  - **연동**: 연결 92 · 연동 51 · 통합 11
  - **실행**: 실행 138 · 시작 69
- **대비(정상인 것)**: 삭제 83 : 제거 3 : 지우기 13 처럼 지배어가 분명한 쌍도 있다 — 즉
  전부 갈라진 게 아니라 **일부 개념군만** 규칙 없이 갈라져 있다.
- **Impact**: 사용자가 "등록"과 "추가"가 다른 동작이라고 오해할 여지가 있고, 검색·도움말·
  교육 자료가 화면과 어긋난다.

### PA-F-008 · 문구가 설명서 역할을 대신하고 있다

- **Evidence**: 사용자 노출 문자열 중 **40자 초과 288건**, **괄호 보조설명 367건**,
  말줄임표 표기가 `…` 44건 / `...` 1건으로 혼용.
- **Impact**: 괄호 안에 조건·예외를 넣는 방식은 스캔이 안 되고 번역·낭독에서 깨진다.
  ux-writing 기준(간결·대화체·명확)의 정면 위반이며, 이 문구들이 많다는 것은
  **화면 구조가 설명 없이는 이해되지 않는다는 신호**이기도 하다(L축과 교차).

### PA-F-011 · 오류 문구가 사용자에게 "그래서 무엇을 하라"를 말하지 않는다 (핵심)

`ux-writing` Skill(`~/.claude/skills/ux-writing`)의 오류 메시지 패턴
**`[What failed]. [Why/context]. [What to do].`** 를 자로 삼아 실측했다. 같은 Skill은 회복
경로가 없는 오류를 **"Dead ends (error with no recovery path)"** 로 명시적으로 금지한다.

- **측정 대상**: 사용자 노출 문자열 중 **"어떤 동작이 실패했다"를 서술하는 고유 문구 167건**
  (`var/product-audit/scan_errcopy.py`). 설정 라벨(`실패 허용 횟수`)·통계 라벨(`미해결 실패
  작업`)·빈 상태(`사용자가 없습니다`)는 **걷어낸 뒤**의 수다.
- **결과**:

  | 요소 | 건수 | 비율 |
  |---|---|---|
  | `[무엇이 실패했다]` | 167 | 100% |
  | `[왜]` 를 말함 | 5 | 2% |
  | `[무엇을 하라]` 를 말함 | 24 | 14% |
  | **3요소 모두** | **0** | **0%** |
  | 막다른 길(행동 없음) | 143 | 85% |

- **결정적 증거 — 좋은 패턴이 이미 이 저장소에 있는데 퍼지지 않았다**:
  - 지키는 곳(24건): `Banners.jsx:71` `"대리 보기를 종료하지 못했습니다. 다시 시도해 주세요."` ·
    `CommandPalette.jsx:171` · `UserMenu.jsx:60` · `lib/api.js:54` ·
    `MyStats.jsx:58` `"티켓 연동이 아직 설정되지 않았습니다. 관리자에게 문의하세요."`
  - 안 지키는 곳(143건): `NotificationBell.jsx:201` `"읽음 처리하지 못했습니다."` ·
    `ChatPane.jsx:105` `"메시지를 보내지 못했습니다."` · `BoardPost.jsx:182` `"삭제하지 못했습니다."` ·
    `lib/api.js:16` `"요청을 처리하지 못했습니다."` — **같은 `api.js` 안에서 16행은 막다른 길이고
    54행은 회복 경로가 있다.**
- **이 저장소가 이미 이름 붙인 결함 계열이다**: `docs/WORK_STATE.md`가 반복해서 기록한
  *"패턴은 있는데 새 화면이 안 따른다"* 와 정확히 같은 모양이다(티켓 → 문서·게시판
  cross-invalidation 때 찾은 것과 동일 구조).
- **표본 검증 시 확인한 한계**: 143건 중 일부(`ScopeBar.jsx:66`, `AssistantPanel.jsx:136,204`,
  `Board.jsx:177`)는 오류가 아니라 안내·확인 문구다. 그래서 **막다른 길의 보수적 하한은 약
  130건**으로 본다. `3요소 모두 = 0` 은 그와 무관하게 성립한다.
- **User impact**: 실패했다는 사실만 알고 다음 행동을 모르면 사용자는 같은 버튼을 다시 누르거나
  (중복 제출) 포기한다. 이 축(I — Recovery)의 프롬프트 정의 *"사용자가 실패 후 무엇을 해야
  하는지 알 수 있는가"* 에 대해 이 제품의 답은 **85%의 경우 '모른다'** 이다.

### 병합된 Root Cause

문구를 판단할 **기준 문서가 없다.** 그래서 문구 결정이 매번 개별 개발자의 그 순간 취향으로
내려가고, 공통 키트(`kit.jsx`)조차 자기 안에서 갈라진다. 문구를 하나씩 고치는 것은 해결이
아니다 — 다음 화면에서 다시 갈라진다. PA-F-011이 보여 주듯 **좋은 문구가 이미 존재해도
규칙이 없으면 옆 파일로 전파되지 않는다.**

### 기존 Backlog와의 관계 (중복 아님)

`UX-40`/`UX-41`/`UX-50` 3건 외에 UX Writing 계열 항목이 없고, 그 3건 중 어느 것도 문구
**규칙 부재**를 다루지 않는다. VIS-* 162건은 시각/레이아웃이다.

### 구현 방향

1. `docs/UX_WRITING.md`(신설)에 최소 규칙만: 종결·마침표, 존댓말 수준, 개념별 표준 동사표,
   오류 문구 3요소(무엇이·왜·다음에 무엇을), 길이 상한, 괄호 사용 금지 조건.
2. 규칙을 **기계 검사**로 못박는다 — `scripts/static_checks.sh`에 문구 린트를 추가해
   같은 문장이 두 철자로 존재하는 것과 표준 동사표 위반을 잡는다. 규칙만 쓰면 다시 갈라진다.
3. 그 다음에 기존 문구를 일괄 정렬한다(규칙 없이 먼저 고치지 않는다).

**이 변경이 기능/데이터/권한/업무 흐름을 바꾸는가: 아니오.** 단, 상태값·API 필드명·
제품명·수치는 건드리지 않는다(프롬프트 2절 humanization 제약).

---

## 음성 결과 (이것도 증거다)

Round 0에서 **찾았는데 없었던 것들.** 다음 Auditor가 같은 각도를 반복하지 않도록 남긴다.

| 조사한 것 | 결과 | 근거 |
|---|---|---|
| FastAPI `async def` 라우트 핸들러 (§3-1 위반) | **0건** | `async def` 15건은 전부 예외 핸들러·미들웨어·`await request.json()` 헬퍼 |
| `httpx` 직접 사용 (§3-2 위반) | **0건** | 유일한 import가 `app/core/http_client.py` 자신 |
| naive `datetime.now()` / `utcnow()` (§3-7 위반) | **0건** | |
| `.innerHTML =` / `dangerouslySetInnerHTML` 실사용 (§3-6) | **0건** | 매치 2건은 "쓰지 않는다"는 주석 |
| 네이티브 `alert/confirm/prompt` | **0건** | 초기 스캔 57건은 전부 앱의 `useConfirm()` 오탐이었다 |
| `console.log/debug` · `TODO/FIXME/HACK` · bare `except:` | **각 0건** | |
| MUI 마이그레이션 잔여(브랜치명이 `ui/mui-migration`) | **잔여 없음** | 화면 모듈 115개 중 MUI/kit 밖에 남은 렌더 표면 0개. 나머지 33개는 전부 helper/config |
| 빈/오류/로딩 상태 미처리 화면 | **거의 없음** | 150줄 초과 화면 50개 중 `ErrorState` 40 · 로딩 45 · `EmptyState` 29 사용 |

## 조사 방법의 한계 (다음 Auditor에게)

- **Orphan API 스캔은 이번 방법으로는 결론을 못 냈다.** 문자열 리터럴 기반 스캐너
  (`var/product-audit/scan_orphans.py`)가 259개 서버 경로 중 107개를 "프런트에서 안 부름"으로
  보고했는데, 표본 검증 결과 대부분 **DataScreen registry가 base 경로 + 액션명으로 조립**해
  리터럴이 안 나오는 것이었다(예: `/api/assistant/*` 4개는 `AssistantPanel.jsx:36`의
  `` `/api/assistant/${tab.path}` `` 로 전부 배선돼 있다). X축은
  **`screens/registry/actions.js`의 액션 정의를 파싱하는 방식**으로 다시 해야 한다.
- 자작 스캐너의 첫 결과는 표본 검증 전까지 Finding이 아니다. 이번 Cycle에서만 오탐 3건
  (alert/confirm 57건, dangerouslySetInnerHTML 2건, orphan API 107건 중 다수)을 폐기했다.
