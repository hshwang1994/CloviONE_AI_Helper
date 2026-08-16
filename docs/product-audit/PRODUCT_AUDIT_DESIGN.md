# PRODUCT AUDIT — DEEP UI/UX DESIGN AUDIT

cycle_id=PA-20260816-120655-f103fb5b
baseline_sha=`70e264bf13110e7e61cdf96331bd92de48f2163d`
baseline_branch=`ui/mui-migration`

> 이 문서는 **일반 QA가 아니다.** HTTP 상태·콘솔 오류·overflow·heading 개수는 여기서 판정 근거가
> 되지 못한다(D-75). 여기서 묻는 것은 하나다 — **현재 UI를 하나도 보존할 필요가 없다면, 이 기능과
> 업무 요구사항만 가지고 2026 Enterprise SaaS / AI Product를 지금 새로 만들 때 어떤 화면이 나오는가.**
> 그 Target Design을 먼저 세우고, 그 다음에 현재 화면과의 격차로 판정한다.
>
> 판정 어휘: `KEEP` / `REFINE` / `REDESIGN` / `REBUILD`.
> 기능 계약(데이터 의미 · API 계약 · RBAC 경계 · 상태 전이 · 외부 연동)은 **전부 보존**한다.
> App Shell · IA · Navigation · Dashboard · Layout · Component 구조 · Typography · Density는
> **보존 의무가 없다**.

---

## 0. 이 감사를 수행한 방법

| | |
|---|---|
| 적용 Skill | `ui-ux-pro-max` · `redesign-existing-projects` · `impeccable` (§0-A) |
| 관측 대상 | 사용자 콘솔 10화면 + 관리자 콘솔 16화면 = **26 표면**, 역할 2종 |
| 뷰포트 | 1920×1080 (light·dark), QHD/4K/125·150·175% 배율/좁은 폭 |
| 스크린샷 | `var/product-audit/shots/` — 실제로 **Read로 열어서 눈으로 판정했다** |
| 계측 | `design_capture.py` · `probe_shell.py` · `verify_nav.py` · `verify_fab.py` · `verify_dark.py` |
| 원시 데이터 | `design_capture_admin.json` · `design_capture_user.json` · `probe_shell.json` · `verify_nav.json` · `verify_fab.json` · `verify_dark.json` |

### 0-A. Skill을 실제로 어디에 썼나

호출했다는 기록이 아니라 **판단 기준으로 실제 사용한 자리**다.

| Skill | 이 감사에서 실제로 쓴 기준 | 그 기준이 잡아낸 것 |
|---|---|---|
| `ui-ux-pro-max` | `--design-system`이 이 제품군에 지정한 **"Data-Dense Dashboard"** 스타일 — *minimal padding · grid layout · space-efficient · maximum data visibility*. 그리고 `--domain ux`의 Navigation Active State · Empty States · Heading Hierarchy | 대시보드가 data-dense가 아니라 **card-dense**라는 것(40장의 카드가 0행의 데이터를 감싼다) |
| `redesign-existing-projects` | 「Generic AI 패턴」 목록 — *purple/blue AI gradient* · *three equal card columns* · *generic card look(border+shadow+white bg)* · *dashboard always has a left sidebar* · *modals for everything* · *numbers in proportional font* | 헤더 보라 그라디언트, 40장 균일 카드 격자, 카드가 위계를 만들지 않고 위계를 **지우고** 있다는 것 |
| `impeccable` | Operate 모드 규범(*scanability · consistency · native expectation이 표현보다 우선*), Nielsen 10 heuristic 0–4 채점, **Cognitive Load 8항 체크리스트**, **Working Memory ≤4 / 최상위 메뉴 ≤5 / 형제 ≤4**, 페르소나 Alex(파워유저)·Sam(접근성) | 관리자 내비 8그룹·39목적지(≤5 위반), 한 화면 40개 결정지점(≤4 위반), 기본 동작(primary action) 부재 |

세 Skill 모두 이 저장소에 설치되어 있고 실제로 호출했다. `skill_gap` 없음.
`ux-writing`·`humanize-korean`은 P·R축 담당이며 이 문서의 판정에는 **문구가 IA를 대신하고 있는가**라는
한 가지 각도로만 참여했다(§2-G).

### 0-B. 이번 라운드에서 내가 스스로 철회한 판정 2건

증거를 세기 전에 표본을 열라는 이 저장소의 교훈(STATE §A-3)이 또 맞았다. **둘 다 내가 만든
측정 오류였고, 기록으로 남긴다.**

1. **「관리자 사이드바 하단 21개 항목에 도달할 수 없다」 — 철회.**
   `probe_shell.py`가 "드로어 내부에 스크롤 컨테이너 없음"이라고 보고했고, `/system`은 페이지 자체가
   스크롤되지 않으므로(docH == vpH == 1080) 하단 항목이 물리적으로 unreachable하다고 결론냈다.
   **틀렸다.** `verify_nav.py`로 조상 체인을 다 뽑으니 `<nav class="MuiList-root">` 자신이
   `overflow-y: auto` · `scrollHeight 1976` · `clientHeight 839`로 **스스로 스크롤한다.**
   내 탐지기가 `side.querySelectorAll('*')`로 찾았기 때문에 **자기 자신을 제외**한 것이 원인이다.
   → 도달 가능하다. Critical이 될 뻔한 것이 **밀도 문제(REDESIGN)** 로 정확히 내려앉았다.

2. **「AI 카드가 내비 항목을 가린다」 — 철회.**
   카드는 `y 959..1080`, 드로어 nav는 `y 120..959`로 **붙어 있을 뿐 겹치지 않는다.** 겹친 것처럼
   보인 이유는 내가 nav 항목 좌표에 `scrollY`를 더해 문서 좌표로 만들고 고정(fixed) 카드와 비교했기
   때문이다. 내부 스크롤된 항목은 nav 자신의 박스에 잘리는 것이지 카드 밑에 그려지는 것이 아니다.
   → **단, 본문 쪽 겹침은 진짜였다**(§2-D). 뷰포트 좌표 + `elementFromPoint` 히트테스트로 다시 재서
   확정했다. 같은 현상처럼 보이는 두 주장 중 하나만 사실이었다.

---

## 1. Target Design을 먼저 세운다 (Bottom-up 금지)

개별 화면을 보기 전에, **기능 계약만 남기고 제품을 다시 그리면 무엇이 나오는가**를 먼저 적는다.
아래 §2의 모든 판정은 현재 화면이 아니라 이 목표와의 격차로 내려졌다.

ClovirAssist가 실제로 하는 일은 셋이다 — **(a) 사내 업무(티켓·문서·게시판·채팅)를 한곳에서 처리하고,
(b) 자동화 플랫폼(n8n·Runner·Notion·LLM)의 상태를 운영자가 통제하며, (c) AI 어시스턴트가 그 둘을
가로지른다.** 즉 이 제품은 *두 개의 다른 제품이 한 셸에 들어 있는* 구조다. 사용자 콘솔은
**개인 업무 도구**이고 관리자 콘솔은 **인프라 운영 콘솔**이다. 지금 이 둘은 같은 셸·같은 카드·같은
배너·같은 밀도를 쓴다. 그것이 이 감사가 찾은 가장 큰 구조적 사실이다.

2026 기준으로 새로 만든다면:

| 영역 | Target |
|---|---|
| **셸** | 전역 크롬은 **높이 예산**을 가진다. 헤더 56–64px + 상태 요약 1줄. 장애/공지는 **개별 배너를 쌓지 않고** 헤더의 상태 칩 하나로 접힌다(`장애 2 · 공지 1`), 펼치면 패널. 본문은 언제나 첫 화면의 80% 이상을 갖는다 |
| **IA** | 관리자는 8그룹 39목적지가 아니라 **업무 기준 5영역**(운영 / 사용자·권한 / 자동화 / 연동 / 감사) + 영역 안 탭. 설정은 6화면에 흩어지지 않고 **한 화면 + 탭**(시스템 정책 / OS 동작 / 연동 / AI). 내비에 **필터 입력**이 있다 |
| **대시보드** | 카드 격자가 아니라 **결정 화면**. 최상단은 *지금 조치가 필요한 것*만(0건이면 "이상 없음" 한 줄로 접힘), 각 항목에 **조치 버튼**이 붙는다. 정상 지표는 **한 줄 요약 스트립**으로 접히고, 같은 수치는 화면에 한 번만 나온다 |
| **목록/표** | 표가 첫 화면에서 시작한다. 행 클릭이 상세를 열고 **행마다 「상세」 버튼을 두지 않는다**. 배지는 *예외 상태에만* 칠하고 정상값은 무채색. 숫자는 tabular-nums |
| **폼/모달** | 짧은 생성은 모달, 다단계·긴 편집은 전용 화면. 모달은 테마를 따른다 |
| **어시스턴트** | 이름 하나, 진입점 하나(전역 단축키 + 고정 위치). 본문 조작 요소를 **절대 덮지 않는다** |
| **시각 언어** | 보라 그라디언트를 브랜드 신호로 쓰지 않는다. 강조색 1개 + 의미색(위험/주의/정상)만. 카드는 *위계를 만들 때만* 쓰고 나머지는 여백·구분선으로 |

**금지선 확인**: 위 어느 항목도 데이터 의미·API 계약·RBAC 경계·상태 전이·외부 연동 계약을 바꾸지
않는다. 바뀌는 것은 배치·밀도·묶음·명명·진입 동선뿐이다.

---

## 2. 이번 라운드가 확정한 구조적 사실

각 항목은 **재현 가능한 계측**이다. 추정과 관측을 섞지 않았다.

### 2-A. 전역 배너 스택이 모든 화면에서 첫 화면의 31%를 먼저 가져간다
`probe_shell.json` — 관리자 14라우트 **전부** 동일: 배너 5장, `y 64 → 395.5` = **331.5px**.
1080 뷰포트의 **30.7%**. 사용자 9라우트 전부: 배너 4장, `y 64 → 280` = **216px**(20.0%).
페이지 제목 `h1`이 관리자 `y=447`, 사용자 `y=308~332`에 온다. **닫을 수 있는 것은 관리자 5장 중 2장,
사용자 4장 중 1장뿐**이고 나머지는 상태가 풀릴 때까지 영구히 남는다.
게다가 첫 두 장은 같은 사건을 두 번 말한다 — 「지금 티켓 동기화가 멈춰 있습니다… 18050분」과
「지금 문서 동기화가 멈춰 있습니다… 18050분」.

### 2-B. 관리자 내비는 839px 창으로 1976px를 본다
`verify_nav.json` — 링크 39 + 그룹 헤더 8 = 46항목, nav 콘텐츠 **1976px**, 보이는 창 **839px**
= **42%만 보인다**. 1080에서 21개가 접힌다. 내부 스크롤로 **도달은 된다**(§0-B).
`impeccable` Working Memory 규범(최상위 ≤5, 형제 ≤4) 대비 **8그룹**, 「시스템 인프라」 7 · 「사용자」 7.
내비 안에 검색/필터가 없다. 사용자 콘솔은 23링크·접힘 0으로 **문제 없다** — 관리자만의 문제다.

### 2-C. 대시보드는 데이터가 아니라 카드가 빽빽하다
`design_capture_admin.json` + `probe_shell.json` — 최상위 카드 **39~40장**, `docHeight 2569`
= **2.38화면**, 표 행 **0**, **contained(기본) 버튼 0개**.
같은 수치가 여러 구역에 반복된다(자동 검출):

| 값 | 나타나는 구역 |
|---|---|
| `3` 미해결 실패 작업 | 「확인이 필요한 항목」 · 「지금 상태」 · 「현재 큐 상태」 — **3회** |
| `42.6%` 디스크 사용 | 「지금 상태」 · 「시스템 리소스」 |
| `0` 활성 워크플로 | 「지금 상태」 · 「인벤토리」 |

그리고 화면이 **자기 정보구조를 산문으로 설명한다** — 「이 줄은 요약입니다. 값을 누르면 그 화면으로
내려가고, 자세한 항목은 아래 구역에 있습니다.」 요약 줄이 아래 구역과 **같은 시각 무게**를 갖기
때문에 한 문장을 덧붙여야 했던 것이다. 레이아웃이 못 한 일을 문구가 대신하고 있다.

### 2-D. 어시스턴트 FAB이 표 화면의 행 조작 버튼을 덮는다 — 확정
`verify_fab.json` — FAB은 `fixed (1826, 986) 70×70 z-index 1050`. 관리자 10라우트 중 **9곳**,
사용자 5라우트 중 **1곳**에서 마지막 행의 「상세」 버튼과 겹치고, 겹침 중심점에서
`document.elementFromPoint()`가 **FAB을 반환**한다 — 즉 실제로 위에 있고 클릭을 가로챈다.

```
admin /users  /settings  /audit  /rbac  /departments  /feature-flags  /offboarding : BLOCKED 2 ['상세','상세']
admin /jobs   /integrations                                                        : BLOCKED 1 ['상세']
user  /notifications                                                               : BLOCKED 2 ['상세','상세']
```

### 2-E. 화면 대부분에 기본 동작이 없다
관리자 16화면 중 **10화면**, 사용자 10화면 중 **4화면**이 `contained` 버튼 0개다. 특히 「확인이
필요한 항목」이라는 제목을 단 대시보드에 **조치 버튼이 하나도 없다** — 전부 chevron 링크다.
반대로 잘된 대조군도 있다: `/users`는 `+ 사용자 추가`(filled) + `CSV 내보내기/가져오기`(outlined)로
위계가 정확하다. 즉 규범이 없는 것이 아니라 **퍼지지 않았다**.

### 2-F. 다크 테마는 잘 만들었고, 테마에 참여하지 않는 표면이 남았다
`verify_dark.json` — 토글 후 `body` 배경 `rgb(9,14,29)`(순흑이 아닌 틴티드 다크 — 좋다),
화면당 대비 실패 **1~2건**뿐. 그러나:

- **`prefers-color-scheme: dark`를 첫 로드에서 따르지 않는다.** OS가 다크여도 `rgb(245,247,252)`로
  칠하고, 헤더의 「다크 모드로 전환」을 눌러야 바뀐다.
- **온보딩 다이얼로그가 다크에서 흰색으로 남는다**(`shots/dark3_user_me.png`) — 어두운 앱 위에
  흰 카드 하나. `redesign-existing-projects`가 「a single … section breaking an otherwise
  consistent page looks like a copy-paste accident」로 지목하는 바로 그 패턴이다.
- 알림 배지: 흰 12px on `rgb(255,139,155)` = **2.23:1**(기준 4.5) — 전 화면 공통.
- `/me` 활성 탭 「오늘 브리핑」: `rgb(83,108,214)` on `rgb(17,24,45)` = **3.76:1**.
  브랜드 인디고 `#536CD6`을 다크 표면에 **밝기 재도출 없이** 그대로 썼다.

셋 다 화면 결함이 아니라 **토큰이 테마에 참여하지 않는다**는 한 가지 원인이다.

### 2-G. 화면이 스스로 설명하는 대신 산문으로 설명한다
`probe_shell.json` intro[] — 안내 패널이 붙은 화면: `/users` · `/settings`(4문단) · `/rbac`(260자)
· `/offboarding`(220자) · `/prompts`(162자) · `/system`(139자) · `/feature-flags`(135자)
· `/diagnostics`(183px + 218px 블록 2개).

가장 뚜렷한 것은 `/settings`다. 안내문이 **설정이 6개 화면에 나뉘어 있다는 사실을 알려주는 일**을
한다 — 「유지보수 모드, 점검 공지는 '유지보수' 화면에서」, 「노션 … 은 'Notion 관리' 화면에서, AI
설정은 'AI 관리' 화면에서」, 「서버 시간대, DNS, 서비스 재시작 … 은 '시스템 설정' 화면에서 따로
관리합니다(이 표의 값과 달리 되돌릴 수 없는 실행 동작이라 화면을 분리했습니다)」.
**IA 실패를 문구가 흡수하고 있다.** 같은 화면 하단에는 브라우저에만 저장되는 개인 설정
「화면 강조색」이 전역 시스템 정책 표와 **같은 화면에** 있고, 그 차이 역시 산문으로만 구분된다.

또 `/settings` 표는 `conversation_retention_days` · `ui_branding` · `lockout_policy` 같은
**백엔드 키를 사용자용 열로 노출**한다(`impeccable` heuristic 2 — Match System / Real World).

### 2-H. 잘 만든 것 (보존 대상)

판정이 재설계로 기울어도 **이것들은 근거 있게 잘 만든 것**이고, 재설계가 깨뜨리면 안 된다.

- **빈 상태의 회복 3요소.** `/me`의 Notion 미연결 카드는 *무엇이 일어났는가 → 무엇을 하라(1·2 번호)
  → 무엇을 기대하라(「기대 결과: 연결되면 내 담당 티켓이 이 자리에 표시됩니다」)*를 갖췄다.
  이전 Cycle `PA-RC-0002`가 세운 기준을 실제로 만족하는 화면이다.
- **AI 채팅 빈 상태.** 일러스트 + 「무엇을 도와드릴까요?」 + 실제로 동작하는 시작 프롬프트 7개 +
  「오늘 AI 사용량 0/200」 쿼터 표시. AI 제품다운 빈 화면이다.
- **정직한 결손 고지.** 「티켓 소스를 읽지 못해 이번 주 진척을 계산할 수 없습니다」처럼 *계산 불가*를
  0으로 위장하지 않고 말한다. 드문 미덕이다.
- **`/users`의 동작 위계**와 **다크 테마 팔레트**(§2-F).
- **`/chat`의 맥락 인지** — 채팅 화면에서는 헤더 어시스턴트 칩과 FAB이 사라진다.

---

## 3. 표면별 판정

<!-- DESIGN-VERDICT-BEGIN app-shell -->
surface: app-shell
layout_family: shell
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: 헤더 64px + 좌측 고정 레일 264px + 본문 1656px(86.3%, 상한 없음 — 4K에서 3500px). 그 아래 전역 배너가 관리자 5장·331.5px, 사용자 4장·216px 쌓이고 26개 라우트 전부에서 동일하다. 페이지 h1은 관리자 y=447에 온다. 배너 중 닫을 수 있는 것은 관리자 2/5, 사용자 1/4. 첫 두 장은 같은 동기화 정지를 티켓/문서로 나눠 두 번 말한다.
user_problem: 어떤 화면을 열든 첫 화면의 3분의 1을 이미 읽은 공지가 먼저 차지한다. 배너는 상태가 풀릴 때까지 사라지지 않으므로 상시 표시가 되고, 그 결과 진짜 장애가 떴을 때도 배경으로 읽힌다. 표 화면에서는 이 비용이 그대로 데이터 행을 밀어낸다.
target_design: 전역 크롬에 높이 예산을 준다. 헤더(56~64px) 우측에 상태 칩 하나(`장애 2 · 공지 1`)를 두고 개별 배너를 쌓지 않는다. 칩을 누르면 패널이 열려 항목별 원인·경과·조치 링크를 보여준다. 심각도 Critical 1건만 헤더 바로 아래 한 줄(40px)로 남기고, 같은 원인의 다중 증상(티켓·문서 동기화)은 한 줄로 합쳐 「동기화 정지 · 12일째 · 자세히」로 요약한다. 결과적으로 본문이 첫 화면의 80% 이상을 갖는다.
rationale: 배너 높이가 화면 성격과 무관하게 고정 비용으로 붙는다는 점이 핵심이다. 개별 화면을 고쳐서는 없어지지 않고 셸 한 곳에서만 해결된다. 또한 impeccable Operate 모드는 scanability를 표현보다 우선하라고 요구하는데, 상시 배너 5장은 정반대로 작동해 경보 피로를 만든다.
browser_evidence: shots/fhd_admin_dashboard.png · shots/fhd_admin_users.png · shots/fhd_admin_settings.png · shots/fhd_user_me.png · shots/fhd_user_chat.png (1920x1080 light) 및 shots/dark3_user_me.png (dark). 계측 probe_shell.json — 관리자 14라우트 bannerTop=64 bannerBottom=395.5 h1y=447 전부 동일, 사용자 9라우트 64→280.
rc_ids: PA-RC-0016
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN global-header -->
surface: global-header
layout_family: shell
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REFINE
current_state: 높이 64px. 좌측 로고 「Clovir Assist / SMART WORKSPACE ASSISTANT」, 중앙 전역 검색(Ctrl K 힌트 포함), 우측에 어시스턴트 칩 「클로비」·테마 토글·알림 벨(배지 34)·사용자 칩. 배경은 보라~인디고 선형 그라디언트이고 그 위 텍스트 58개가 놓인다. /chat에서는 어시스턴트 칩이 사라진다.
user_problem: 구조와 기능 배치는 옳지만 두 가지가 걸린다. 하나는 어시스턴트 진입점이 헤더 칩·사이드바 카드·우하단 FAB 세 곳이라 무엇이 정본인지 알 수 없다는 것, 다른 하나는 보라 그라디언트가 브랜드 신호를 독점해 정작 위험 상태를 나타내야 할 색이 헤더와 경쟁한다는 것이다.
target_design: 높이와 구성(로고·전역 검색·상태·알림·계정)은 유지한다. 그라디언트를 단색 표면으로 바꾸고 보라는 강조색으로만 남긴다. 어시스턴트 진입점은 헤더 칩 하나로 통일하고(단축키 병기) 사이드바 카드와 FAB은 제거한다. 비워진 우측에 §app-shell의 상태 칩을 놓아 배너 스택을 흡수한다. 알림 배지는 다크에서도 4.5:1을 만족하는 값으로 재도출한다.
rationale: 헤더가 맡은 일 자체는 정확하고 Ctrl K 힌트 노출·테마 토글·역할 표시까지 Operate 모드가 요구하는 것을 갖췄다. 구조를 바꿀 이유가 없으므로 REDESIGN이 아니라 REFINE이다. 다만 redesign-existing-projects가 AI 제품의 가장 흔한 지문으로 지목하는 purple/blue gradient가 정확히 여기에 있고, 진입점 삼중화는 IA 문제라 여기서 함께 정리해야 한다.
browser_evidence: shots/fhd_admin_dashboard.png · shots/fhd_user_chat.png (1920x1080 light) — 칩·검색·벨·테마 토글 배치 확인. shots/dark3_user_me.png (dark) — 배지 흰 글자 on rgb(255,139,155). verify_dark.json 대비 2.23:1(기준 4.5), onGradient 58 노드.
rc_ids: PA-RC-0016, PA-RC-0020, PA-RC-0021
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN sidebar -->
surface: sidebar
layout_family: shell
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: 폭 264px 고정 레일. 관리자는 그룹 헤더 8 + 링크 39 = 46항목이고 nav 콘텐츠 1976px를 839px 창으로 본다(42% 가시, 1080에서 21개 접힘). 내부 overflow-y:auto로 스크롤은 된다. 최하단 121px(y 959~1080)를 「클로비에게 물어보기」 카드가 상시 점유한다. 상단에는 사용자/관리자 콘솔 전환 세그먼트가 있다. 내비 안 검색·필터 없음. 사용자 콘솔은 23링크로 접힘 0.
user_problem: 관리자가 목적지를 찾으려면 42%만 보이는 창을 스크롤하며 8개 그룹을 훑어야 한다. 그룹명이 「시스템 인프라」·「거버넌스」처럼 시스템 구현 기준이라 업무에서 출발한 사람이 어느 그룹인지 추론해야 하고, 실패하면 Ctrl K 전역 검색이 사실상 유일한 우회로가 된다.
target_design: 레일을 업무 기준 5영역(운영 / 사용자·권한 / 자동화 / 연동 / 감사)으로 접고 각 영역 안은 화면 상단 탭으로 내린다. 최상위 5개는 impeccable Working Memory 규범을 만족하고 스크롤 없이 다 보인다. 레일 상단에 내비 필터 입력을 두어 39목적지를 타이핑으로 좁힌다. 어시스턴트 카드는 헤더 칩으로 통합해 제거하고 그 121px를 내비에 돌려준다. 현재 활성 항목은 영역+탭 두 단계로 항상 표시한다. RBAC에 따른 노출 규칙은 그대로 유지한다.
rationale: 39목적지 자체가 과한 것이 아니라 39개를 한 평면에 나열한 것이 문제다. 8그룹은 impeccable 최상위 ≤5 규범을, 7개 형제를 가진 그룹 둘은 ≤4 규범을 넘는다. 항목을 지우지 않고 계층을 한 단 넣는 것만으로 가시율이 42%에서 100%가 되므로 구조 변경으로 해결 가능하며, 이는 색·간격 조정으로는 도달할 수 없다.
browser_evidence: shots/fhd_admin_dashboard.png · shots/fhd_admin_settings.png · shots/fhd_admin_users.png (1920x1080 light) — 그룹/항목/AI 카드 위치 육안 확인. verify_nav.json — nav scrollHeight 1976 / clientHeight 839, linkCount 39, linksBelowViewport 21, 카드 box (0,959,264,121). design_capture_admin.json navItems 46종.
rc_ids: PA-RC-0017, PA-RC-0020
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN navigation-ia -->
surface: navigation-ia
layout_family: shell
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: 관리자 목적지 39개가 8그룹으로 나뉜다. 설정 성격의 화면이 「설정」·「시스템 설정」·「초기 설정」·「유지보수」·「Notion 관리」·「AI 관리」 6곳에 흩어져 있고, /settings 안내 패널 4문단이 어느 설정이 어느 화면에 있는지를 산문으로 안내한다. 통계 화면도 「프롬프트 사용 통계」·「정책 사용 통계」로 콘텐츠 그룹 안에 분리돼 있다. breadcrumb은 「관리자 › 운영」 2단계로 존재한다.
user_problem: 운영자가 설정 하나를 바꾸려 할 때 어느 화면인지 메뉴만 보고 알 수 없다. /settings에 들어가 안내문을 읽고 다른 화면으로 이동하는 왕복이 기본 동선이 된다. impeccable이 말하는 The Hidden Navigation과 The Context Switch가 동시에 발생한다.
target_design: 목적지를 업무 기준 5영역으로 재편하고, 같은 대상을 다루는 화면을 한 화면의 탭으로 합친다. 설정은 「설정」 한 화면 아래 시스템 정책 / OS·서비스 동작 / 연동(Notion·외부) / AI 로 탭 분리하되, 되돌릴 수 없는 실행 동작 탭은 시각적으로 구분하고 확인 단계를 유지한다(현재 화면 분리가 지키려던 안전 의도를 탭 안에서 그대로 보존). 사용 통계 2종은 각 대상 화면의 탭으로 흡수한다. breadcrumb은 영역 › 화면 › 탭 3단계로 확장한다.
rationale: 안내 문구가 IA를 대신하고 있다는 것이 결정적 증거다. 화면을 나눈 이유(되돌릴 수 없는 동작의 분리)는 타당하지만 그 안전 의도는 탭 안의 확인 단계로도 보존되며, 지금은 그 대가로 6화면 탐색 비용을 사용자에게 전가하고 있다. 메뉴 이름과 그룹은 보존 의무가 없는 영역이므로 재편이 허용된다.
browser_evidence: shots/fhd_admin_settings.png (1920x1080 light) — 안내 4문단이 6개 화면 위치를 설명하는 것을 육안 확인. shots/fhd_admin_dashboard.png — 8그룹 레일. probe_shell.json intro[] — /settings·/rbac·/prompts·/system·/feature-flags·/offboarding·/users·/diagnostics에 안내 패널 존재.
rc_ids: PA-RC-0017, PA-RC-0022
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN dashboard -->
surface: dashboard
layout_family: dashboard
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REBUILD
current_state: /dashboard는 최상위 카드 39~40장, 문서 높이 2569px(2.38화면), 표 행 0, contained 버튼 0개다. 9개 구역(확인이 필요한 항목 4 · 지금 상태 5 · 서비스 상태 8 · 작업 지표 4 · 현재 큐 상태 3 · 인벤토리 3 · 시스템 리소스 2 · 백업 1 · 최근 주요 변경 · 내 업무 4)이 모두 같은 흰 카드로 렌더된다. `3` 미해결 실패는 3개 구역에, `42.6%` 디스크와 `0` 활성 워크플로는 각각 2개 구역에 중복된다. 값이 `0`·`-`인 카드도 실제 값과 동일한 크기·무게를 갖는다. 화면이 「이 줄은 요약입니다…」라는 문장으로 자기 정보구조를 설명한다. /my-stats도 카드 12장·CTA 0으로 같은 성격이다.
user_problem: 「확인이 필요한 항목」이라는 제목 아래 위험 4건이 있는데 그 자리에서 할 수 있는 조치가 하나도 없다. 모든 카드가 같은 무게라 「중단 워커 위험」과 「0 대기 작업」이 같은 크기로 보이고, 같은 숫자를 세 번 마주치면서도 그것이 같은 사건인지 판단할 단서가 없다. 결국 대시보드는 무엇을 해야 하는지 알려주지 않고 스크롤 2.4화면을 요구한다.
target_design: 현황판이 아니라 결정 화면으로 다시 만든다. 첫 화면 상단은 조치 대기 목록 하나만 갖는다 — 각 행은 「무엇이 · 언제부터 · 영향」 + 기본 조치 버튼(워커 다시 시작 / 실패 잡 보기 / 백업 실행)이며, 조치할 것이 없으면 「이상 없음」 한 줄로 접힌다. 정상 지표는 카드가 아니라 한 줄 요약 스트립(서비스 1/7 · 큐 0 · 디스크 42.6% · 백업 12일 전)으로 접고 클릭 시 해당 화면으로 간다. 같은 수치는 화면 전체에서 한 번만 등장하며 중복 구역(인벤토리·시스템 리소스·현재 큐 상태)은 상세 화면으로 내린다. 값이 0인 지표는 큰 숫자로 그리지 않고 스트립 안에서 무채색으로 축약한다. 결과적으로 첫 화면 안에서 판단이 끝나고 「이 줄은 요약입니다」 같은 설명문이 필요 없어진다.
rationale: 이것은 다듬어서 도달할 수 없다. 카드 40장이라는 구성 자체가 위계를 지우는 원인이고, 중복은 구역 분할 방식에서 나오며, 조치 버튼 부재는 카드가 링크로만 설계된 결과다. 셋 다 같은 구성 결정에서 나오므로 구성을 버려야 사라진다. ui-ux-pro-max가 이 제품군에 지정한 Data-Dense Dashboard 기준(space-efficient · maximum data visibility)과 비교하면 현재 화면은 카드 밀도는 높고 데이터 밀도는 0에 가깝다. impeccable Cognitive Load 체크리스트에서 Single focus · Chunking · Visual hierarchy · Minimal choices 4항이 동시에 실패한다.
browser_evidence: shots/fhd_admin_dashboard.png (1920x1080 light, 전체 페이지 1920x2569) — 9구역 40카드와 「이 줄은 요약입니다」 문장을 육안 확인. probe_shell.json dup 스캔 — 42.6%/0 활성 워크플로 2구역 중복, 값 3이 확인이필요한항목·지금상태·현재큐상태 3구역. design_capture_admin.json — topCards 40, contained 0, screensTall 2.38, rows 0.
rc_ids: PA-RC-0018, PA-RC-0023
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN home -->
surface: home
layout_family: dashboard
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: /me(h1 「오늘」)는 로그인 후 사용자·관리자 **양쪽의 착지 화면**이다(관리자도 /#/me로 착지). 카드 16장, 1.71화면, contained 버튼 0개. 한 화면에 7개 기능 표면이 모인다 — 상단 지표 5(오늘 마감·지연·…·안 읽은 알림·안 읽은 채팅), 「오늘 마감」 목록, AI 도우미(탭 4개 + 문장 요약 만들기), 팀 채팅(실제 입력창 포함), 이번 주 내 진척, 최근 문서, 게시판. 첫 방문 시 5단계 온보딩 모달이 뜬다(건너뛰기 가능).
user_problem: 착지 화면이 무엇을 위한 곳인지 정하지 않았다. 지표·목록·AI·채팅·문서·게시판이 동등한 카드로 병렬돼 있어 「오늘 무엇을 해야 하는가」가 3초 안에 읽히지 않고, 기본 동작도 없다. 관리자까지 같은 화면에 착지하므로 운영 업무를 시작하려면 먼저 다른 곳으로 이동해야 한다.
target_design: 「오늘 내가 할 일」 한 가지에 집중하는 화면으로 좁힌다. 상단은 내 담당 작업 목록(마감 임박 → 지연 → 진행 중) 하나이고 각 행에 기본 조치가 붙는다. 지표 5개는 목록 위 한 줄 스트립으로 접는다. 팀 채팅과 게시판은 카드에서 빼 사이드바 목적지로 되돌리고, 최근 문서는 목록 우측의 좁은 보조 열로 남긴다. AI 도우미는 카드가 아니라 화면 상단의 한 줄 제안(「오늘 마감 0건 · 요약 만들기」)으로 축소하고 본체는 /chat이 갖는다. 관리자는 /me가 아니라 /dashboard로 착지시킨다(RBAC 판정은 서버 정본을 그대로 사용).
rationale: 개별 카드는 잘 만들어져 있으나(특히 Notion 미연결 빈 상태) 화면 전체가 포털형 집합이라 우선순위가 없다. 카드를 다듬어도 7개 표면이 동등하다는 사실은 바뀌지 않으므로 배치와 소속을 바꿔야 한다. 반면 각 구성요소의 내용과 문구는 살아 있어 재사용 가능하므로 REBUILD가 아니라 REDESIGN이다.
browser_evidence: shots/fhd_user_me.png (1920x1080 light, 전체 1920x1845) · shots/dark3_user_me.png (dark) — 7개 표면 병렬과 온보딩 모달 육안 확인. design_capture_user.json — topCards 16, contained 0, screensTall 1.71. probe_shell.json — 관리자·사용자 모두 landed=/#/me.
rc_ids: PA-RC-0018, PA-RC-0023
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN admin-console -->
surface: admin-console
layout_family: admin
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: 운영 성격 화면들(/system 카드 9·CTA 0, /rbac 카드 8·CTA 0·안내 260자, /integrations 카드 8·CTA 1, /diagnostics 카드 30·2.65화면·설명 블록 2개, /llm-console 카드 10·CTA 2)이 공통 패턴을 공유한다 — 상단 안내 패널, 카드 격자, 기본 동작 부재. /diagnostics는 카드 30장에 문서 높이 2858px다.
user_problem: 운영 콘솔은 장애 상황에서 빠르게 판단하고 조치하는 곳인데, 화면마다 먼저 안내문을 읽어야 하고 조치 버튼이 카드 사이에 흩어져 있거나 아예 없다. /diagnostics처럼 카드 30장을 2.65화면에 걸쳐 스크롤하면 이상 항목이 정상 항목에 묻힌다.
target_design: 운영 화면의 공통 골격을 정한다 — (1) 화면 최상단은 상태 판정 한 줄(정상 / 주의 N / 위험 N), (2) 그 아래 이상 항목만 목록으로, 각 행에 기본 조치, (3) 정상 항목은 기본 접힘, (4) 안내문은 상시 패널이 아니라 제목 옆 도움말 토글로 이동. /diagnostics는 카드 격자를 점검 항목 목록으로 바꾸고 실패·경고만 펼친다. /rbac는 권한 표를 유지하되 안내를 열 헤더의 도움말로 내린다.
rationale: 다섯 화면이 같은 증상을 보이므로 화면별 수정이 아니라 운영 화면 템플릿 하나를 정하는 문제다. impeccable Operate 모드가 요구하는 scanability 기준에서, 정상 항목과 이상 항목이 같은 카드로 병렬되는 배치는 장애 대응 시 정확히 반대로 작동한다.
browser_evidence: shots/fhd_admin_system.png · shots/fhd_admin_rbac.png · shots/fhd_admin_diagnostics.png · shots/fhd_admin_integrations.png · shots/fhd_admin_llm-console.png (1920x1080 light). design_capture_admin.json — /diagnostics topCards 30 screensTall 2.65, /system contained 0, /rbac contained 0. probe_shell.json intro[] — /rbac 260자, /system 139자, /diagnostics 183px+218px.
rc_ids: PA-RC-0022, PA-RC-0023
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN table-screens -->
surface: table-screens
layout_family: table
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: /users(20행·28버튼) · /audit(100행·111버튼·5.94화면) · /jobs · /feature-flags · /settings가 같은 표 패턴을 쓴다. 행마다 「상세」 버튼이 붙어 행 클릭과 중복되고(안내문이 「행을 누르면 상세에서…」라고 명시), 역할·상태·Notion 연결이 모두 배지 열이라 한 행에 알약 3개가 나란히 놓인다. /users의 부서·직책 열은 대부분 「-」다. /audit은 한 페이지에 100행을 놓아 5.94화면이 된다. 페이지 크기 선택이나 점프 없이 이전/다음만 있다. 표 시작 위치는 배너 331.5px + 제목 + 안내 + 필터 뒤인 y≈982다.
user_problem: 스캔이 어렵다. 배지가 모든 상태값에 칠해져 있어 예외를 눈으로 고를 수 없고, 「상세」 버튼 20개가 우측 열을 채워 시선을 끌지만 행 클릭과 같은 일을 한다. /audit에서 특정 사건을 찾으려면 6화면을 스크롤해야 한다. 마지막 행의 「상세」는 어시스턴트 FAB에 덮여 클릭이 가로채인다.
target_design: 표를 첫 화면 안에서 시작시킨다(배너 축소는 app-shell에서 해결). 행 조작은 행 클릭으로 통일하고 「상세」 버튼 열을 제거하되, 키보드 접근을 위해 행에 focus/Enter를 유지한다. 배지는 예외 상태에만 칠하고 정상값(사용 중·기본값·미연결)은 무채색 텍스트로 낮춘다. 값이 전부 비는 열(부서·직책)은 기본 숨김 + 열 선택으로 내린다. 숫자·시각 열은 tabular-nums로 정렬한다. 페이지 크기 선택(20/50/100)과 총계 기준 점프를 추가하고 /audit 기본값은 50으로 낮춘다. 대량 선택 시 상단에 고정 액션 바를 띄운다.
rationale: 다섯 화면이 같은 표 컴포넌트를 공유하므로 이것은 화면 문제가 아니라 표 패턴 문제다. redesign-existing-projects의 「pill badge 남용」과 ui-ux-pro-max의 Data-Dense Dashboard 기준(space-efficient·maximum data visibility) 둘 다에서, 정보를 나르지 않는 배지와 중복 버튼이 실제 데이터 폭을 잠식하고 있다. 열 구성·배지 규칙·페이지네이션은 데이터 의미나 API 계약을 건드리지 않고 바꿀 수 있다.
browser_evidence: shots/fhd_admin_users.png (1920x1080 light, 전체 1920x2140) — 배지 3열·상세 20개·부서/직책 「-」 육안 확인. shots/fhd_admin_settings.png — FAB이 세션 정책 행의 상세 버튼을 덮는 장면. shots/fhd_admin_audit.png · shots/fhd_admin_jobs.png · shots/fhd_admin_feature-flags.png. verify_fab.json — /users·/settings·/audit·/rbac·/departments·/feature-flags·/offboarding BLOCKED 2, /jobs·/integrations BLOCKED 1. probe_shell.json — /users theadY 982 firstRowY 1019.
rc_ids: PA-RC-0019, PA-RC-0023, PA-RC-0016
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN list-screens -->
surface: list-screens
layout_family: list
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REFINE
current_state: /team-docs(카드 26·CTA 2) · /board(카드 6·CTA 1·행 5) · /departments(카드 10·CTA 1) · /prompts(카드 7·CTA 2) · /notifications(카드 8·CTA 0·행 12) · /my-tickets(카드 4·CTA 0). 목록 상태(검색·필터·페이지)는 이전 Cycle이 /team-docs·/board·/team-tickets·/audit에서 URL 보존을 확인했고 /users만 예외였다(PA-RC-0013). 기본 동작은 대체로 존재한다.
user_problem: 셸 비용(배너 216~331px)이 목록 첫 행을 밀어내는 것이 가장 큰 체감 문제이고, 그 다음이 카드 밀도다. /team-docs는 카드 26장으로 목록보다 카드가 많아 훑기 어렵다. /notifications는 12행에 기본 동작이 없어 「모두 읽음」 같은 일괄 조치가 눈에 띄지 않는다.
target_design: 목록 화면 골격을 유지한 채 밀도만 손본다. 카드 래핑을 줄여 항목이 목록으로 읽히게 하고(항목당 카드 대신 구분선), 필터 바는 한 줄로 압축한다. 기본 동작이 없는 목록(/notifications·/my-tickets)에 화면 목적에 맞는 기본 동작(모두 읽음 / 새 티켓)을 세운다. 배지 규칙은 table-screens와 공유한다. URL 상태 보존은 /users 예외(PA-RC-0013)를 닫아 전 목록이 동일하게 동작하게 한다.
rationale: 목록 화면은 구조적으로 옳다 — 필터·페이지네이션·빈 상태·URL 보존이 대부분 갖춰져 있고 기본 동작도 절반 이상 존재한다. 남은 것은 밀도와 일관성이라 구조 변경 없이 도달 가능하므로 REFINE이다. 실제로 이 감사가 본 가장 잘 만든 빈 상태 두 개가 이 계열에 있다.
browser_evidence: shots/fhd_user_team-docs.png · shots/fhd_user_board.png · shots/fhd_user_notifications.png · shots/fhd_admin_departments.png · shots/fhd_admin_prompts.png · shots/fhd_user_my-tickets.png (1920x1080 light). design_capture_user.json / design_capture_admin.json — topCards·contained 수치. probe_shell.json — /board theadY 603, /notifications theadY 758.
rc_ids: PA-RC-0016, PA-RC-0023
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN settings -->
surface: settings
layout_family: settings
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: /settings는 설정·키·값·상태·설명·상세 6열의 키-값 표 11행이다. 「키」 열이 conversation_retention_days·notification_retention_days·ui_branding·password_policy·session_policy·lockout_policy·allowed_email_domains·document_automation_enabled·backup_schedule·smtp 같은 백엔드 식별자를 그대로 노출한다. 상태 열은 「수정됨」 1개와 「기본값」 10개 배지다. 상단 안내 4문단이 나머지 설정이 유지보수·Notion 관리·AI 관리·시스템 설정 화면에 있다고 설명한다. 화면 하단에는 브라우저 로컬에만 저장되는 개인 설정 「화면 강조색」이 같은 페이지에 있고 그 차이도 산문으로만 구분된다. 사용자 쪽 /profile은 카드 9·2.42화면이다.
user_problem: 한 화면 안에 전역 시스템 정책과 개인 브라우저 설정이 섞여 있어 「내가 바꾸면 누구에게 적용되는가」를 문단을 읽어야 알 수 있다. 원하는 설정이 이 화면에 없을 확률이 높고, 그때 어디로 갈지도 문단을 읽어야 안다. 백엔드 키 열은 운영자에게 유용할 수 있으나 기본 노출로는 잡음이다.
target_design: 「설정」 한 화면 + 탭 구성으로 통합한다 — 시스템 정책 / OS·서비스 동작 / 연동(Notion·외부) / AI. 되돌릴 수 없는 실행 동작 탭은 시각적으로 구분하고 확인 단계를 유지해 현재 화면 분리가 지키던 안전 의도를 보존한다. 개인 설정(화면 강조색·테마)은 시스템 설정에서 떼어 계정 메뉴 아래 「내 화면 설정」으로 옮긴다. 표는 항목명·현재 값·적용 범위·마지막 변경으로 구성하고 백엔드 키는 상세 패널이나 열 토글로 내린다. 「기본값」 배지는 없애고 「수정됨」만 표시한다(정보량은 동일, 잉크는 1/10).
rationale: 설정이 6화면에 흩어진 것과 한 화면에 두 종류 스코프가 섞인 것은 같은 원인이다 — 화면 경계가 사용자의 의사결정 단위가 아니라 구현 단위로 그어졌다. 안내 4문단이 그 비용을 흡수하고 있다는 사실이 증거다. 탭 통합은 API·데이터·RBAC 계약을 건드리지 않고 화면 경계만 다시 긋는 작업이다.
browser_evidence: shots/fhd_admin_settings.png (1920x1080 light, 전체 1920x1669) — 키 열의 원시 식별자, 「기본값」 배지 10개, 안내 4문단, 하단 화면 강조색 섹션을 육안 확인. shots/dark3_admin_settings.png (dark). shots/fhd_user_profile.png. probe_shell.json — /settings theadY 704 firstRowY 740.
rc_ids: PA-RC-0017, PA-RC-0022, PA-RC-0023
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN ai-assistant-chat -->
surface: ai-assistant-chat
layout_family: chat
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REFINE
current_state: /chat은 3분할이다 — 셸 레일 264px + 대화 목록 288px + 대화 영역. 빈 상태에 일러스트·「무엇을 도와드릴까요?」·시작 프롬프트 7개가 있고, 입력창 위에 「오늘 AI 사용량 0/200」 쿼터가 표시된다. 이 화면에서는 헤더 어시스턴트 칩과 우하단 FAB이 사라진다(맥락 인지 동작). 문제는 명명이다 — 같은 화면에서 breadcrumb 「도우미 › AI 도우미」, 사이드바 「AI 도우미」, h1 「채팅」, 패널 제목 「채팅」이 동시에 쓰인다. 제품 전체로는 「클로비」(헤더 칩·온보딩·사이드바 카드)와 「업무 도우미」(관리자 서비스 상태)까지 더해진다.
user_problem: 사이드바에서 「AI 도우미」를 눌렀는데 도착한 화면 제목이 「채팅」이라 같은 곳인지 확신하기 어렵다. 어시스턴트에 들어가는 문도 헤더 칩·사이드바 카드·FAB 세 개라 무엇이 정본인지 모른다. 대화가 없을 때도 좌측 288px가 빈 목록으로 고정된다.
target_design: 이름을 하나로 확정한다 — 제품 안에서 어시스턴트를 부르는 말과 화면 제목·breadcrumb·사이드바 라벨을 일치시킨다(사람 이름 「클로비」는 어시스턴트의 인격 표시로만 남기고 목적지 라벨은 통일). 진입점은 헤더 칩 + 전역 단축키 하나로 모으고 사이드바 카드와 FAB은 제거한다(FAB 제거는 §table-screens의 가림 문제도 함께 닫는다). 대화 목록은 대화가 없을 때 접히고 첫 대화 생성 시 펼쳐진다. 시작 프롬프트는 4개를 기본 노출하고 나머지는 「더 보기」로 내린다(Working Memory ≤4).
rationale: 화면 구조 자체는 AI 제품으로서 적절하다 — 3분할, 빈 상태 품질, 쿼터 노출, 맥락 인지 숨김까지 갖췄다. 고쳐야 할 것은 명명 일관성과 진입점 중복이며 둘 다 레이아웃을 바꾸지 않고 해결되므로 REFINE이다. 다만 명명은 Q축 Root Cause로 제품 전역에 걸쳐 있어 이 화면 안에서만 고칠 수 없다.
browser_evidence: shots/fhd_user_chat.png (1920x1080 light) — breadcrumb 「도우미 › AI 도우미」와 h1 「채팅」이 한 화면에 동시 존재하는 것을 육안 확인, 시작 프롬프트 7개·쿼터 0/200·FAB 부재 확인. shots/dark3_user_chat.png (dark). shots/fhd_user_me.png — 「클로비에게 물어보기」 카드와 「AI 도우미」 섹션이 한 화면에 공존. design_capture_user.json — /chat topCards 5, contained 2.
rc_ids: PA-RC-0020, PA-RC-0019
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN key-workflows -->
surface: key-workflows
layout_family: workflow
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: /offboarding(카드 9·행 22·CTA 0·2.19화면·안내 220자) · /scheduler-calendar(카드 9·버튼 33·CTA 0) · /new-ticket(카드 6·CTA 1·1.24화면) · /search(카드 6·CTA 1)를 봤다. 다단계 업무인 오프보딩이 단계 표시 없이 안내문 + 목록 + 산재한 버튼 27개로 구성돼 있고 기본 동작이 없다. /scheduler-calendar는 버튼 33개에 기본 동작 0이다. 반면 /new-ticket은 폼 + 단일 기본 동작으로 정상이다.
user_problem: 퇴사 처리처럼 순서와 완료 조건이 있는 업무에서 지금 어느 단계인지, 다음에 무엇을 눌러야 하는지 화면이 말해주지 않는다. 버튼 27~33개가 위계 없이 놓여 있어 되돌릴 수 없는 조작과 조회 조작이 같은 무게로 보인다.
target_design: 순서가 있는 업무는 단계 골격을 갖는다 — 상단에 진행 표시(대상 선택 → 티켓·문서 이관 → 계정 비활성화 → 확인), 각 단계에 기본 동작 하나와 완료 판정, 되돌릴 수 없는 단계에는 확인 절차. 안내 220자는 각 단계의 도움말로 분해한다. /scheduler-calendar는 달력 조작(보기 전환·이동)과 일정 조작(생성·취소·재실행)을 분리해 후자만 강조 위계를 갖게 한다. /new-ticket의 폼+단일 CTA 구조는 그대로 두고 다른 워크플로 화면의 기준으로 삼는다.
rationale: 워크플로 화면은 개별 기능이 아니라 순서가 산출물인 화면이다. 현재는 그 순서가 화면 구조가 아니라 안내문에 들어 있어 사용자가 매번 읽어 재구성해야 한다. 단계 골격은 API·상태 전이 계약을 바꾸지 않고 표현만 바꾸는 작업이며, /new-ticket이 같은 저장소 안에 이미 좋은 대조군을 제공한다.
browser_evidence: shots/fhd_admin_offboarding.png (1920x1080 light, 전체 1920x2365) · shots/fhd_admin_scheduler-calendar.png · shots/fhd_user_new-ticket.png · shots/fhd_user_search.png. design_capture_admin.json — /offboarding topCards 9 buttons 27 contained 0 screensTall 2.19, /scheduler-calendar buttons 33 contained 0. probe_shell.json — /offboarding intro 220자 h=131px.
rc_ids: PA-RC-0022, PA-RC-0023
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN detail-screens -->
surface: detail-screens
layout_family: detail
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: 상세 보기가 콘솔에 따라 두 가지 다른 것으로 구현돼 있다. 사용자 콘솔은 실제 라우트다 — UserRoutes.jsx에 /tickets/:id · /projects/:id · /chat-rooms/:id · /board/:id · /team-docs/:id · /games/:id 6개가 선언돼 있고 딥링크·뒤로가기·not-found가 동작한다. 관리자 콘솔은 :id 라우트가 하나도 없고 행 클릭이 모달을 연다 — /users 992x887, /audit 992x896, /departments 992x560이며 셋 다 URL이 바뀌지 않는다(urlBefore == urlAfter). 그래서 /users/<uuid>를 직접 입력하면 미등록 라우트로 떨어져 h1 「대시보드」로 조용히 이동한다.
user_problem: 관리자가 특정 사용자·감사 항목을 동료에게 링크로 보낼 수 없고, 상세를 연 뒤 뒤로가기를 누르면 상세만 닫히는 게 아니라 이전 화면을 떠난다. 잘못된 상세 URL은 「없는 항목입니다」가 아니라 대시보드로 보내져 무슨 일이 일어났는지 알 수 없다. 같은 제품 안에서 게시글 상세는 링크가 되는데 사용자 상세는 안 되는 비일관도 학습을 방해한다.
target_design: 상세 보기 기제를 하나로 통일한다. 관리자 상세에도 /users/:id · /audit/:id · /departments/:id 라우트를 부여하고, 표현은 지금처럼 목록 위 오버레이(모달/드로어)를 유지하되 URL과 동기화해 딥링크·뒤로가기·새로고침이 성립하게 한다. 뒤로가기는 상세만 닫고 목록 상태(검색·필터·페이지)를 보존한다. 미등록 상세 id는 대시보드 이동이 아니라 사용자 콘솔이 이미 쓰고 있는 not-found 3요소(무엇이 없다 / 왜 그럴 수 있다 / 목록·홈으로)를 그대로 보여준다. RBAC 판정은 지금처럼 서버가 정본이고 라우트 추가가 권한 경계를 넓히지 않는다.
rationale: 이것은 화면 미관이 아니라 상세 보기라는 개념이 제품 안에서 두 개의 다른 것으로 구현돼 있다는 구조 문제다. 사용자 콘솔이 이미 옳은 구현을 갖고 있으므로 목표가 가설이 아니라 같은 저장소 안의 실물이다. 오버레이라는 표현을 버릴 필요가 없어 REBUILD가 아니고, URL 동기화는 배치 조정으로 도달할 수 없어 REFINE도 아니다.
browser_evidence: shots/detail_user-detail.png · shots/detail_audit-detail.png · shots/detail_dept-detail.png (1920x1080 light) — 행 클릭으로 열린 모달 육안 확인. design_capture2.json detail[] — 세 화면 모두 openedAs=dialog, urlBefore==urlAfter, aria-modal=true. states[] — /users/00000000-0000-0000-0000-000000000000 이 9초 후 h1 「대시보드」. frontend/src/app/UserRoutes.jsx:60-83 대비 AdminRoutes.jsx에 :id 라우트 0건.
rc_ids: PA-RC-0024
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN modal-drawer -->
surface: modal-drawer
layout_family: overlay
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: 오버레이가 두 용도로 쓰인다. 생성 폼 모달은 잘 만들어져 있다 — 「사용자 추가」 992x744(필드 8·라벨 8·필수 2), 「부서 추가」 720x344(필드 2·라벨 2·필수 1), 둘 다 aria-modal=true · aria-labelledby 있음 · Escape로 닫힘 · 포커스가 안에 있음 · 버튼은 취소(text) + 추가(primary) 하나씩. 반면 상세 모달의 동작 위계는 무너져 있다 — /users 상세는 버튼 10개에 contained(primary)가 「비활성화」·「보관」·「수정」 3개이고, /departments 상세는 「수정」·「비활성화」·「삭제」 3개가 전부 primary다. 즉 파괴적 동작이 기본 동작과 같은 강조를 쓴다. 상세 모달은 URL과 동기화되지 않는다(detail-screens 참조).
user_problem: 생성 흐름은 문제가 없다. 문제는 상세다 — 사용자를 열었을 때 화면이 강조하는 것이 「수정」인지 「비활성화」인지 「보관」인지 알 수 없고, 부서 상세에서는 「삭제」가 「수정」과 똑같은 채운 버튼이라 오조작 위험이 실제로 높다. impeccable의 Error Prevention(파괴적 동작 전 구분과 확인) 기준에서 강조 자체가 잘못돼 있다.
target_design: 오버레이 용도를 규범으로 나눈다. (1) 짧은 생성/편집은 모달 — 현재 「사용자 추가」 구조를 표준으로 삼는다(aria-modal · labelledby · Escape · 취소 text + 단일 primary). 첫 입력에 초기 포커스를 준다. (2) 상세 열람은 URL과 동기화된 드로어/오버레이로 하고 동작 위계를 강제한다 — primary 정확히 1개(수정), 나머지는 secondary, 파괴적 동작(삭제·비활성화·보관)은 위험 스타일 + 별도 그룹 + 확인 단계. (3) 긴 다단계 편집은 모달이 아니라 전용 화면으로 보낸다.
rationale: 오버레이 기반 자체는 건강하다 — 접근성 속성·Escape·포커스 관리가 이미 갖춰져 있어 버릴 이유가 없다. 그러나 「모달 안 동작 위계」와 「상세 모달의 URL 부재」는 배치 조정으로 못 고치는 규범 문제이고, 파괴적 동작이 primary로 칠해진 것은 미관이 아니라 안전 문제다. redesign-existing-projects의 「Modals for everything」 경고가 정확히 상세 용도에서 발생하고 있다.
browser_evidence: shots/modal_user-add.png · shots/modal_dept-add.png (1920x1080 light, 뷰포트 캡처) — 생성 모달 구조 육안 확인. shots/detail_user-detail.png · shots/detail_dept-detail.png — primary 버튼 3개 병렬 육안 확인. design_capture2.json modal[] — escapeCloses=true, labelledby=true, fields 8/labels 8. detail[] buttons[] — /users variant primary 3개(비활성화·보관·수정), /departments primary 3개(수정·비활성화·삭제).
rc_ids: PA-RC-0024, PA-RC-0023
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN forms -->
surface: forms
layout_family: form
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REFINE
current_state: 전용 폼 화면 /new-ticket은 카드 6·contained 1·1.24화면으로 단일 기본 동작 구조가 정확하다. 모달 폼 「사용자 추가」는 필드 8에 라벨 8(1:1), 필수 표시 2, aria-modal·labelledby, Escape 닫힘, 취소(text)+추가(primary)를 갖췄다. 이전 Cycle이 빈 필수값 제출을 네이티브 검증이 POST 0건으로 차단하는 것과 서버가 과길이를 422로 거절하는 것을 확인했다. 남은 결함은 두 가지다 — 모달을 열었을 때 초기 포커스가 첫 입력이 아니라 컨테이너 DIV에 있고, 서버 스키마 오류가 영문 Pydantic 문구로 노출되며 필드에 연결되지 않는다(PA-RC-0014, 기존).
user_problem: 키보드 사용자가 모달을 열면 Tab을 한 번 더 눌러야 첫 필드에 닿는다. 서버 검증에 걸리면 영문 메시지가 폼 위에 뜨고 어느 칸이 문제인지 표시되지 않아 스스로 찾아야 한다.
target_design: 구조는 그대로 두고 두 곳만 채운다. 모달이 열릴 때 첫 입력(또는 제목)에 초기 포커스를 주고 닫을 때 트리거로 되돌린다. 서버 검증 오류는 한국어로 번역해 해당 필드 아래 인라인으로 붙이고 aria-describedby로 연결한다(PA-RC-0014의 acceptance criteria와 동일 목표). 라벨·필수 표시·취소/제출 위계는 현재 형태를 표준으로 고정해 다른 폼이 이를 따르게 한다.
rationale: 폼은 이 감사가 본 표면 중 상태가 가장 좋다 — 라벨 1:1, 필수 표시, 접근성 속성, 단일 primary, Escape, 네이티브 검증까지 갖췄고 구조를 바꿀 이유가 없다. 남은 두 결함은 국소적이고 배치를 건드리지 않으므로 REFINE이 정확한 등급이다.
browser_evidence: shots/modal_user-add.png · shots/modal_dept-add.png (1920x1080 light) · shots/fhd_user_new-ticket.png (1920x1080 light, 전체 1920x1334). design_capture2.json modal[] — fields 8 / labels 8 / required 2, focusInside=true 이지만 activeEl=DIV. design_capture_user.json — /new-ticket contained 1.
rc_ids: PA-RC-0023
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN empty-state -->
surface: empty-state
layout_family: state
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REFINE
current_state: 빈 상태의 문구 품질은 좋다. /projects는 일러스트 + 「프로젝트가 없습니다」 + 원인 설명 + 다음 행동(「보관한 프로젝트까지 보려면 위의 스위치를 켜세요」)을 갖추고, /me의 Notion 미연결 카드는 무엇이·어떻게(1·2 번호)·기대 결과 3요소를 갖췄으며, /chat 빈 화면은 시작 프롬프트 7개를 준다. 문제는 그 위다 — /projects는 프로젝트가 0건인데도 값이 0 또는 「-」인 큰 지표 카드 8장을 빈 상태 위에 먼저 그린다. 계측상 /my-tickets·/projects·/team-docs/trash 는 contained 버튼 0개이고 /chat-rooms만 1개다.
user_problem: 아무것도 없는 화면에서 「0」이 8번 크게 반복된 뒤에야 진짜 안내가 나온다. 화면의 절반을 정보가 없다는 사실을 여덟 번 말하는 데 쓴다. 그 결과 잘 쓴 빈 상태 문구가 아래로 밀려 첫 화면에서 안 보이는 경우가 생긴다.
target_design: 데이터가 0건일 때 지표 카드 격자를 그리지 않는다. 지표는 한 줄 요약 스트립으로 접거나 아예 숨기고, 빈 상태 블록을 화면 상단으로 올려 첫 화면 안에서 읽히게 한다. 빈 상태에는 그 화면에서 실제로 가능한 다음 행동을 버튼으로 준다 — 생성이 가능한 화면(티켓·채팅방)은 생성 버튼을, 외부 소스를 비추기만 하는 화면(프로젝트)은 지금처럼 조건 변경(보관 포함 스위치)이나 연결 안내를 버튼 형태로 올린다. 문구 자체는 이미 좋으므로 바꾸지 않는다.
rationale: 이 표면은 내용이 아니라 배치 문제다. 회복 3요소·원인 설명·시작 프롬프트 같은 어려운 부분이 이미 되어 있고, 고칠 것은 0 지표를 빈 상태 위에 쌓지 않는 것과 다음 행동을 버튼으로 올리는 것뿐이라 구조 변경 없이 도달한다. 「0을 큰 숫자로 그린다」는 원인은 대시보드와 동일해 같은 Root Cause로 병합한다.
browser_evidence: shots/empty_projects.png (1920x1080 light) — 0/- 지표 카드 8장 위에 빈 상태가 놓인 배치를 육안 확인. shots/empty_my-tickets.png · shots/empty_trash.png · shots/empty_chat-rooms.png. shots/fhd_user_me.png — Notion 미연결 3요소. shots/fhd_user_chat.png — 시작 프롬프트 7개. design_capture2.json empty[] — contained 0/0/0/1.
rc_ids: PA-RC-0018, PA-RC-0023
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN error-state -->
surface: error-state
layout_family: state
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REFINE
current_state: 사용자 콘솔의 not-found는 잘 만들어져 있다 — /board/999999 는 9초 뒤 h1 「게시글」과 함께 정상적인 not-found 상태로 해소되고, 이전 Cycle이 상세 6화면에서 「찾을 수 없습니다 / 이미 삭제되었거나 이동했을 수 있습니다」 + 「목록」·「홈으로」 3요소를 확인했다(PA-F-052). 관리자 콘솔은 다르다 — /users/<uuid> 는 미등록 라우트라 9초 뒤 h1 「대시보드」로 조용히 이동하고 아무 설명이 없다. 화면 내 오류 배너는 전역 배너 스택과 같은 시각 언어를 써서 구분되지 않는다.
user_problem: 관리자가 잘못된 링크를 받거나 URL을 잘못 입력하면 오류 대신 대시보드에 도착한다. 무엇이 잘못됐는지, 그 항목이 삭제된 것인지 권한이 없는 것인지 알 수 없고 되돌아갈 곳도 안내받지 못한다. 반면 같은 제품의 사용자 콘솔은 이 경우를 정확히 처리하고 있어 일관성도 함께 깨진다.
target_design: 사용자 콘솔이 이미 쓰는 not-found 3요소를 제품 전역 규범으로 승격한다 — 무엇이 없는지 · 왜 그럴 수 있는지(삭제/이동/권한) · 되돌아갈 두 경로(목록·홈). 관리자 상세 라우트가 생기면(detail-screens) 그 라우트의 미해결 id가 이 화면을 쓰게 하고, 그때까지도 미등록 URL은 대시보드 이동 대신 not-found를 보여준다. 화면 내 오류는 전역 배너와 다른 시각 처리를 써서 「이 화면의 문제」와 「시스템 전체의 문제」를 구분한다.
rationale: 규범과 구현이 이미 저장소 안에 있고 관리자 콘솔이 그것을 쓰지 못하는 것이 문제라, 새 디자인을 발명할 필요 없이 적용 범위를 넓히는 작업이다. 구조 변경이 아니므로 REFINE이며, 관리자 라우트 부재라는 선행 조건은 detail-screens의 PA-RC-0024가 함께 닫는다.
browser_evidence: shots/state_error-badboard.png · shots/state_error-baduser.png (1920x1080 light, 뷰포트 캡처). design_capture2.json states[] — /board/999999 at9s h1=「게시글」 textLen 467, /users/00000000-... at9s h1=「대시보드」 textLen 1519(배너 텍스트뿐, 화면 고유 내용 없음).
rc_ids: PA-RC-0024, PA-RC-0022
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN loading-state -->
surface: loading-state
layout_family: state
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: KEEP
current_state: /board/999999 를 350ms 시점에 계측하면 스켈레톤 8개가 레이아웃 모양대로 그려져 있고 범용 원형 스피너는 0개다. 9초 시점에는 스켈레톤이 0으로 사라지고 최종 상태(not-found)로 해소된다. 이전 Cycle이 「/board/:id 가 영원히 로딩에 멈춘다」고 본 것은 2.4초 단일 스냅샷이 만든 오탐이었고 시계열로 재서 철회했다(PA-F-052). 전 라우트 sweep에서도 정착 후 남은 스피너로 인한 멈춤 사례는 보고되지 않았다.
user_problem: 로딩 표현 자체에서 사용자가 겪는 문제를 찾지 못했다. 남은 체감 문제는 표현이 아니라 소요 시간이며(not-found 판정 5~10초), 그것은 이 표면이 아니라 S축 성능 항목으로 따로 추적된다.
target_design: 현재 형태를 표준으로 고정한다 — 비동기 영역은 레이아웃 모양과 일치하는 스켈레톤으로 자리를 예약하고 범용 원형 스피너로 대체하지 않으며, 해소되면 스켈레톤을 0으로 만든다. 새로 만드는 화면(대시보드 재구축·관리자 상세 라우트)도 같은 규칙을 따르게 하고, 재설계 과정에서 스켈레톤이 스피너로 후퇴하지 않도록 회귀 검증에 포함한다.
rationale: redesign-existing-projects가 명시적으로 요구하는 「범용 스피너 대신 레이아웃 모양의 스켈레톤」을 이미 충족하고, 콘텐츠 점프를 막기 위한 자리 예약도 되어 있다. 바꿀 근거가 없으므로 KEEP이며, 이 판정은 「안 봤다」가 아니라 시계열 계측으로 확인한 결과다.
browser_evidence: shots/state_loading_error-badboard.png (1920x1080 light, goto 후 350ms 시점 캡처) — 스켈레톤 8개 육안 확인. shots/state_error-badboard.png (9초 시점) — 스켈레톤 0. design_capture2.json states[] — /board/999999 at350ms skeletons 8 spinners 8 textLen 416 → at9s spinners 0 textLen 467.
rc_ids: 해당 없음 — KEEP이라 구현 대상이 아니다. 재설계 시 이 형태를 유지해야 한다는 제약은 PA-RC-0018 의 constraints 에 명시했다.
<!-- DESIGN-VERDICT-END -->

---

## 3-A. 뷰포트 / Windows 배율 (N축, 전 표면 공통)

`design_capture2.json viewports[]` — `/users` 기준.

| 조건 | 본문 폭 | 활용률 | 가로 넘침 |
|---|---|---|---|
| FHD 1920×1080 | 1656px | 86.3% | 없음 |
| QHD 2560×1440 | 2260px | 88.3% | 없음 |
| 4K 3840×2160 | 3500px | 91.1% | 없음 |
| 125% (1536×864) | 1272px | 82.8% | 없음 |
| 150% (1280×720) | 1016px | 79.4% | 없음 |
| **175% (1097×617)** | 833px | 75.9% | **있음** |
| 좁은 폭 1280×800 | 1016px | 79.4% | 없음 |

두 가지가 나오는데 **성격이 다르다.**

**175% 가로 넘침은 신규가 아니다.** BACKLOG 전수 대조에서 기존 `RESP-01`이 이 결함을 같은
숫자까지 이미 기록하고 있었다 — *"배율 175%면 CSS 폭이 1097로 줄어 26px 넘친다(100/125/150%는
정상). `/users`가 요구하는 최소 폭이 1123px"*, 근거 `PA-F-030`·`PA-F-033`. 내 관측은 그것의
**재확인**이다. 신규 Root Cause로 올렸다면 같은 결함이 BACKLOG에 두 번 존재하게 됐을 것이라
`PA-RC-0016`의 신규 범위에서 뺐다.

**신규분은 반대쪽 끝이다** — 폭이 커질수록 활용률이 올라간다(86.3 → 88.3 → **91.1%**).
상한(max-width)이 없어 4K에서 본문이 **3500px**까지 늘어난다. 표에는 받아들일 만하지만
폼·본문 텍스트는 한 줄이 지나치게 길어진다. `RESP-01`·`RESP-02`가 **좁은 폭**만 다루고 있어
이 축은 이제까지 아무도 보지 않았다. 이 절반만 `PA-RC-0016`에 넣는다.

같은 대조에서 `RESP-04`도 확인했다 — 1024~1200에서 사이드바가 264px를 계속 쓰며 "축소 레일이라는
세 번째 상태가 필요하다"고 이미 진단돼 있다. `PA-RC-0017`(내비 밀도)과 같은 방향이므로 그 RC의
구현이 `RESP-04`를 함께 닫아야 한다. 별도 항목을 만들지 않았다.

---

## 4. 판정 요약

| Surface | Verdict | 주된 Root Cause |
|---|---|---|
| app-shell | `REDESIGN` | PA-RC-0016 |
| global-header | `REFINE` | PA-RC-0016 · 0020 · 0021 |
| sidebar | `REDESIGN` | PA-RC-0017 · 0020 |
| navigation-ia | `REDESIGN` | PA-RC-0017 · 0022 |
| dashboard | `REBUILD` | PA-RC-0018 · 0023 |
| home | `REDESIGN` | PA-RC-0018 · 0023 |
| admin-console | `REDESIGN` | PA-RC-0022 · 0023 |
| table-screens | `REDESIGN` | PA-RC-0019 · 0023 · 0016 |
| list-screens | `REFINE` | PA-RC-0016 · 0023 |
| settings | `REDESIGN` | PA-RC-0017 · 0022 · 0023 |
| ai-assistant-chat | `REFINE` | PA-RC-0020 · 0019 |
| key-workflows | `REDESIGN` | PA-RC-0022 · 0023 |
| detail-screens | `REDESIGN` | PA-RC-0024 |
| modal-drawer | `REDESIGN` | PA-RC-0024 · 0023 |
| forms | `REFINE` | PA-RC-0023 |
| empty-state | `REFINE` | PA-RC-0018 · 0023 |
| error-state | `REFINE` | PA-RC-0024 · 0022 |
| loading-state | `KEEP` | — |

**18/18 판정 완료.** `REBUILD` 1 · `REDESIGN` 10 · `REFINE` 6 · `KEEP` 1.

`KEEP`은 `loading-state` 하나다. 그리고 그 하나는 「안 봤다」가 아니라 350ms/9s 시계열로 재서
스켈레톤 8개가 레이아웃 모양대로 자리를 예약하고 정상 해소되는 것을 확인한 결과다.

나머지 17개가 `KEEP`이 아닌 이유는 개별 화면이 못 만들어져서가 아니다. §2-H가 근거와 함께
기록한 대로 빈 상태 회복 3요소, AI 채팅 빈 화면, 생성 모달의 접근성, 정직한 결손 고지,
`/users`의 동작 위계, 다크 팔레트, 스켈레톤 로딩은 실제로 잘 만들어졌다. 문제는 **전역 원인
넷**(셸 비용 · 내비 밀도 · 동작 위계 부재 · 상세 기제 분열)이 거의 모든 표면을 동시에 통과한다는
것이고, 그래서 판정이 표면 개수만큼이 아니라 Root Cause 9건으로 수렴한다.

---

## 5. Root Cause로 내려간 것

| RC | 한 줄 | 판정 근거가 된 표면 |
|---|---|---|
| `PA-RC-0016` | 전역 배너 스택이 모든 화면 첫 화면의 31%(관리자)·20%(사용자)를 고정 비용으로 가져간다 | app-shell · global-header · table-screens · list-screens |
| `PA-RC-0017` | 관리자 IA가 8그룹 39목적지 평면이고 설정이 6화면에 흩어져 안내문이 IA를 대신한다 | sidebar · navigation-ia · settings |
| `PA-RC-0018` | 대시보드/홈이 결정 화면이 아니라 균일 카드 벽이고 같은 수치를 최대 3회 반복한다 | dashboard · home |
| `PA-RC-0019` | 어시스턴트 FAB(z=1050)이 표 화면 마지막 행의 「상세」를 실제로 덮어 클릭을 가로챈다 | table-screens · ai-assistant-chat |
| `PA-RC-0020` | 어시스턴트가 이름 4종(클로비·AI 도우미·도우미·업무 도우미)·진입점 3개로 존재한다 | ai-assistant-chat · sidebar · global-header |
| `PA-RC-0021` | 색 토큰이 다크 테마에 참여하지 않는다(온보딩 모달 흰색·배지 2.23:1·활성 탭 3.76:1·prefers-color-scheme 무시) | global-header (+ 전 표면 공통) |
| `PA-RC-0022` | 화면이 자기 IA를 산문으로 설명한다(안내 패널 8화면) — 문구가 구조 결함을 흡수한다 | navigation-ia · admin-console · settings · key-workflows |
| `PA-RC-0023` | 동작 위계 규범이 없다 — 한쪽은 primary 0개(관리자 10/16·사용자 4/10), 다른 쪽은 primary 3개에 파괴적 동작(삭제·비활성화)까지 primary | dashboard · home · admin-console · table-screens · list-screens · settings · key-workflows · modal-drawer · forms · empty-state |
| `PA-RC-0024` | 상세 보기가 콘솔별로 다른 것이다 — 사용자는 `:id` 라우트 6개, 관리자는 URL 없는 모달이라 딥링크·뒤로가기가 없고 미등록 상세 URL은 대시보드로 조용히 이동한다 | detail-screens · modal-drawer · error-state |

상세 계약(Target Design 필드 일습 포함)은 `PRODUCT_AUDIT_HANDOFF.md`에 있다.

### 이 9건이 실제로 몇 개의 병인가

`PA-RC-0016`(셸 비용)·`0017`(IA 밀도)·`0022`(산문이 IA를 대신함)는 **같은 병의 세 증상**이다 —
*구조가 해야 할 일을 다른 것에 떠넘긴다*. 배너는 우선순위 판단을 사용자에게, 8그룹 평면은 분류를
사용자에게, 안내 4문단은 화면 경계 설명을 문구에 떠넘긴다. 셋을 따로 고치면 서로를 되살린다
(예: 배너만 접고 IA를 그대로 두면 안내문이 여전히 필요하다). 구현 순서를 `0016 → 0017 → 0022`로
묶은 이유가 이것이다.

`PA-RC-0018`(카드 벽)·`0023`(동작 위계)은 **위계의 두 축** — 정보 위계와 동작 위계다. 대시보드
재구축은 둘을 동시에 만족해야 하므로 `0018`의 acceptance criteria가 `0023`을 참조한다.

`PA-RC-0019`(FAB 가림)·`0020`(어시스턴트 이름·진입점)은 **어시스턴트 표면 하나**에서 나온다.
진입점을 헤더 칩 하나로 모으면 FAB이 사라져 가림도 함께 닫힌다 — 그래서 `0019`를 단독 z-index
수정으로 처리하지 말라는 제약을 걸었다.

`PA-RC-0021`(테마 토큰)과 `0024`(상세 기제)는 독립이며 다른 것과 순서 의존이 없다.
