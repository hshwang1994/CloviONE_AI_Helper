# ClovirAssist UI/UX 전면 리뉴얼 — 최종 실행 계획 (지시서 v7 + 보강 요구 R-85~R-96)

> **상태: 최종.** Phase 1 탐색 · Phase 2 설계(Brand/Design System · Product UX/IA · 실행/검증 아키텍처) · 사용자 보강 요구 13항 반영 완료.
> **이 계획은 "디자인 리뉴얼"이 아니라 "디자인 + 기능 정확성" 두 축의 계획이다.** 두 번째 축은 사용자가 티켓 Filter 오동작을 실제로 겪은 뒤 추가됐고, 그 경험이 말하는 것은 **"정상이라고 가정했던 기본 기능이 실제로는 틀려 있을 수 있다"**는 것이다. 그래서 이 계획은 화면이 렌더된다는 사실, API가 200이라는 사실, 테스트가 통과한다는 사실 중 어느 것도 기능 완료의 근거로 인정하지 않는다.
>
> **이번 세션의 실행 범위는 이 계획서와 인계 상태를 프로젝트 안에 기록하고 Gate로 검증하는 것까지다. 제품 코드는 이번 세션에서 구현하지 않는다** (→ 맨 끝 «이번 세션에서 할 일» 참조).

## Context — 왜 이 작업을 하는가

지시서: `C:\Users\hshwa\Downloads\ClovirAssist_UIUX_Renewal_Ultracode_Restart_Final_v7.txt` (3,712줄, 전문 읽음). 최상위 지시 0-0~0-22 + 요구사항 1~84.

이건 이전 리뉴얼의 보정이 아니라 **재작업**이다. 지시서 0번은 현재 구현을 완료 상태·올바른 Design Direction·재사용할 Visual Baseline으로 간주하지 말라고 못 박는다. 기능·데이터·권한·보안·업무 흐름·API 계약은 보존하되, **Visual Design / Layout / Component 표현 / Theme 방향은 처음부터 다시 판단한다.**

핵심 문제는 이것이다. 지난 사이클이 스스로 정한 Design Thesis — 커밋 `c8375ef5` "계측 전면", 커밋 메시지에 적힌 *"브랜드 인디고는 강조 세 자리에서만 나온다"* — 가 제품을 White/Gray Neutral 포털로 탈색시켰다. 지시서 0-1은 그 Thesis를 **사용자 명령으로 폐기**하고 Purple/Indigo Brand Identity를 **사용자 확정사항**으로 되돌린다. 동시에 지시서는 "Border/Radius/Spacing만 손보는 건 리뉴얼이 아니다"(요구 70)라고 못 박으므로, 색만 되돌리는 것으로는 완료가 아니다. Layout · 정보 위계 · Surface 구조 · Typography · Density · Component 표현 · Navigation · Data Visualization · Interaction까지 함께 올려야 한다.

목표 상태: **로고를 가려도 Design Language와 Purple/Indigo System만으로 ClovirAssist라고 느껴지는 제품**, 그리고 각 Page가 "기존 화면을 보기 좋게 정렬한 것"이 아니라 **Page 목적에 맞게 정보 구조·기능·Layout·Interaction이 함께 개선된 상태**.

---

## 사용자 확정사항 (이번 세션에서 직접 확인)

| 항목 | 결정 |
|---|---|
| Taste Skill | `design-taste-frontend`(내부명 tasteskill)를 Taste로 사용. 단 이 스킬은 스스로 "대시보드/데이터 테이블/다단계 제품 UI는 대상 아님"이라 밝히므로, **Typography·Spacing·Surface·비율·리듬·anti-slop 감도 렌즈로만** 쓰고 랜딩형 패턴을 데이터 밀집 화면에 강요하지 않는다. 충돌 시 지시서 우선(지시 49·486). |
| Canonical Hostname | 사용자가 **AD DNS A 레코드 생성 완료**. 검증: `clovirassist.gooddi.lab → 10.100.64.71`, `GET /readyz` = 200. 남은 건 **TLS 인증서만** (아직 `CN=clovirone-ai.gooddi.lab`). 즉 지시 73은 외부 Blocker 없이 100% 이행 가능. |
| `~/Downloads/clovirone_demo_v15_product_refined_final.html` | **보지 않는다.** 지시서에 없으므로 Design Source of Truth로 취급하지 않는다. |
| Legacy Identity 범위 (지시 72) | 사용자가 만든 **업무 데이터는 변경하지 않는다** — 실제 DB의 조직명·프로젝트명·티켓·문서·Notion 동기화 데이터. **저장소가 소유한 제품 데이터는 정리한다** — Source, Config, 배포 설정, 제품 기본 문구, Test Fixture, 개발 Seed, Mock Data. |
| 서버 설치명 rename | **전부 rename 확정.** systemd 유닛 4종, 시스템 사용자/그룹 `clovirone-web`, `/opt`·`/etc`·`/var/lib` 경로, DB 파일 경로, nginx conf 파일명, 계정 홈까지 `clovirassist` 기준으로 이전. 최고 위험 작업이므로 백업·검증·롤백을 갖춘 단일 Wave로 마지막에 수행. |
| `docs/` 삭제 처리 | **UI Renewal 기록만 삭제 확정, 제품/운영 문서는 복구.** 복구 9: `ARCHITECTURE` `CONSOLE_SCREENS` `DECISIONS` `KNOWN_LIMITATIONS` `MAINTENANCE_PLAYBOOK` `OPERATIONS` `RUNBOOK` `SECURITY` `UX_WRITING`. 삭제 확정 18: `BACKLOG` `BUILD_LOG` `DEPLOY_NOW` `PROGRESS_STATUS` `QA_COVERAGE` `RUNNER_HANDOFF` `SONNET_HANDOFF` `UI_INVENTORY` `UI_RENEWAL_TRACEABILITY` `WORK_STATE` + `product-audit/` 8종. 삭제본을 완료 근거로 쓰지 않는다(지시 0-4). |
| sudo 권한 | 사용자가 sudo 비밀번호를 제공하고 사용을 승인. **평문으로 어떤 파일에도 기록하지 않는다**(CLAUDE.md 불변규칙 3·4). 최초 특권 단계에서 `sudo -S`(stdin)로 한 번 사용해 이 작업에 필요한 명령만 허용하는 **scoped sudoers NOPASSWD 항목**을 설치하고, 이후에는 비밀번호 없이 자동화한다. 명령행·로그·프로세스 목록에 노출하지 않는다. |

필수 Skill 설치 확인(지시 49): `ui-ux-pro-max` ✓ (프로젝트 로컬 + 사용자 레벨), `impeccable` v4.0.4 ✓ (프로젝트 로컬 + 사용자 레벨), Taste = `design-taste-frontend` ✓ (사용자 레벨). 세 개 모두 실제 호출 가능.

---

## 확인된 현재 상태 (실측 — 문서가 아니라 소스·브라우저·네트워크)

### 실제 브라우저 캡처
오늘(2026-08-19) 찍힌 `dist/ui-qa/deploy3/` **288장**(70 route × light/dark × 1920/3840)을 Read 도구로 직접 확인했다. 지시서 0-2의 Finding이 그대로 재현된다.

- **Home(`/me`)** — KPI 5개가 `-`만 표시된 균등 Strip. "오늘 마감" 빈 Panel이 화면 중앙에 큰 공백. **4K에서 하단 40%가 완전 공백.** 티켓 동기화 실패 경고가 일반 사용자에게 전폭 노출.
- **문서(`/team-docs`)** — `주의 최근 동기화에 실패했습니다…` 전폭 Warning + **`지금 동기화` 버튼 그대로**(지시 1·9·29 미반영). Filter 5개 뒤 `즐겨찾기만` 하나만 다음 줄 고립(지시 76·80).
- **프로젝트(`/projects`)** — KPI Strip + Filter + Excel Table. 부서 Select는 일반 Dropdown(지시 76). 상태 Column이 짧은 값인데 폭을 크게 차지(지시 74).
- **티켓 상세** — Metadata **6칸 균등**: 긴 프로젝트명과 짧은 티켓번호가 같은 폭(지시 75). 본문 아래 대형 공백(지시 20).
- **채팅(`/chat`, `/chat-rooms`)** — 좌측 목록 + 거대한 빈 Canvas + Composer(지시 0-13).
- **기능 개선 제안(`/ideas`)** — 큰 흰 Filter Rectangle(내용은 좌측 절반만) + 작은 Empty Illustration, 나머지 전부 공백(지시 80·15).
- **자유게시판 상세(`/board/:id`)** — 본문이 좌측 71%만 사용, 우측 대형 공백. 이모지 Reaction 6종 노출(지시 81·28).
- **조직 관리(`/org-tree`)** — 상단 40%만 사용, 하단 공백(지시 0-2·11).
- **메일 발송(`/mail`)** — 같은 원인을 Alert + 요약 + 77행 Table에서 반복(지시 40).
- **기능 플래그** — `assistant_narrative_enabled` 같은 Raw Key가 첫 Column, 설명에 `app_settings 테이블`·`§23` 같은 내부 어휘(지시 39·36).
- **Global Chrome** — Header/Sidebar/Canvas 전부 White/Gray. Active는 얇은 Blue Rail. Brand는 Logo에만 존재(지시 13·0-1).
- **로그인 화면만 예외** — 이미 Deep Indigo→Purple Gradient + 큰 Clovi + 제품 정체성이 완성돼 있다. **제품 Brand Language의 정본은 이미 로그인 화면에 있고, 앱 내부가 그것을 배신하고 있는 상태다.** 이게 이번 Design Direction의 출발점이다.

### 캡처 자체의 결함 — Real Data 상태가 거의 없다
`deploy3` 캡처를 찍은 QA 계정 `ui-qa@goodmit.co.kr`은 **Notion 사용자 연결이 안 돼 있다.** 그래서 Home·내 티켓·내 업무량·Sprint 등 티켓 파생 화면이 전부 "연결 필요" 안내 + 빈 상태로 찍혔다(`user_my-stats.png`가 대표 사례 — KPI 6칸 전부 `-`, 본문은 안내 하나). 지시 0-6은 Empty뿐 아니라 **Real Data / Loading / Error / Permission / Long Text / Many Data** 상태를 모두 재현하라고 요구한다.

→ **Wave 0에서 반드시 해소**: 관리자 `Notion 사용자 연결`(`/admin#/notion-mapping`)로 QA 계정을 매핑하거나, 매핑된 실계정으로 캡처한다. `var/secrets/`에 `notion_docs_token`·`notion_report_token`이 이미 있으므로 토큰 자체는 확보돼 있다. 이걸 고치지 않으면 이번 Audit 전체가 "빈 화면 감사"가 되어 지시 0-6·13·60을 충족하지 못한다.

### 기계 검증은 이미 전부 PASS다 — 그래서 새 Gate가 필요하다
`deploy3/results.json` 요약(288페이지): `auth_ok`·`horizontal_overflow`·`console_errors`·`page_errors`·`broken_images`·`duplicate_ids`·`tiny_text`·`narrow_main`·`contrast`·modal 7종 **전부 fail 0**. 유일한 실패는 `vertical_text_collapse` 6건.

**현행 게이트는 지시서가 지적한 문제를 단 하나도 잡지 못한다.** 균등 Column, 고립 Filter, 대형 Blank, Brand 부재, 작은 Clovi를 잡는 **기하 Assertion을 새로 설계해야 한다.** (Phase 2 산출물)

### Brand — 결정적 발견
`frontend/src/ui/theme.js`에 `theme.palette.brand = { deep:"#17204D", mid:"#293B8D", purple:"#8E75E1", mint:"#62C7BD" }` 가 **존재하는데 프런트엔드 어디에서도 참조하지 않는다(consumer 0건).** 같은 hex는 `BrandLogo.jsx`의 inline SVG에 하드코딩돼 있을 뿐이다.

그리고 `primary.main`은 **사용자 선택 Accent**이고 기본값이 `#536CD6`(파랑)이다. `ACCENT_PRESETS = ["#536CD6" 기본 파랑, "#4058BD" 진한 파랑, "#6B5BC7" 보라, "#327C98" 청록]`. **기본 Accent가 파랑이라서 제품 전체가 파랑으로 읽힌다.** 지시 0-1이 요구하는 "Brand Identity와 Accent의 역할 분리"가 정확히 이 지점이다.

`c8375ef5` 이전 팔레트(참고): primary `#536CD6`, secondary `#8E75E1`(purple), background.default `#F3F6FF`(라벤더 틴트), divider `#DDE4F6`, topbar/sidebar `linear-gradient(135deg,#758AE1,accent,#4058BD)`.

### Hostname / TLS (지시 73)
- 현재 배포 `https://clovirone-ai.gooddi.lab` → 200. TEST SERVER **10.100.64.71** (hostname `ai-n8n-svr`).
- **새 Canonical `https://clovirassist.gooddi.lab` → 200, 10.100.64.71 확인 완료** (사용자가 AD DNS 등록).
- 남은 문제: TLS 인증서가 여전히 `CN=clovirone-ai.gooddi.lab`, SAN `DNS:clovirone-ai.gooddi.lab, IP:10.100.64.71` → **새 이름으로 접속 시 Hostname Mismatch.**
**서버 실측 (SSH로 직접 확인):**
- `ssh cloviradmin@10.100.64.71` **키 인증 성공**. `ssh-client` 존재, `known_hosts`에 등록됨 → 배포·검증 자동화 가능.
- nginx 실제 vhost: `listen 10.100.64.71:443 ssl; server_name clovirone-ai.gooddi.lab;`, `ssl_certificate /etc/clovirone-web-assistant/tls/clovirone-ai.gooddi.lab.crt`. 새 이름이 200을 주는 건 **이 IP:port의 유일한 server block이라 fallback으로 받는 것**이지 정식으로 서브하는 게 아니다 → `server_name`·인증서 교체 필요.
- 서비스 상태: `clovirone-web-assistant` · `clovirone-web-worker` · `clovirone-web-worker-conversational` · `clovirone-privhelper` 전부 running. `n8n.service`·`claude-work-assistant.service`도 running(공유 서비스 — 건드리지 않는다).
- **failed unit 3종 발견**: `clovir-ui-qa{,2,3}.service` — 2026-08-15 QA 세션이 남긴 일회성 `systemd-run` 잔재. 제품 서비스가 아니다. 정리 대상이며, 관리자 `진단` 화면이 이를 어떻게 보고하는지도 함께 확인한다(관리자 대시보드는 `서비스 정상 8/8`로 표시 중 — 실제 failed unit과의 정합성 점검 필요).
- `/etc/clovirone-web-assistant/tls/`는 비특권 사용자가 읽을 수 없음.

- 다행히 `deploy/nginx/clovirone-web-assistant.conf`는 `server_name __DNS_NAME__` 템플릿이고 `scripts/install-clovirone-web-assistant.sh`가 `DNS_NAME`/`BIND_IP`로 치환 + self-signed ECDSA P-256 인증서를 생성한다. 하드코딩이 아니므로 재발급 경로가 이미 있다. 런타임 교체 Action(`app/sysops/actions_service.py::cert.install`)도 존재한다.

### 이미 이행된 요구사항 (재확인 후 Evidence만 남기면 됨)
- **지시 64** — `design/` 디렉터리 자체가 없다. `preview-standalone` 참조는 `scripts/static_checks.sh`의 **금지 검사**와 `tokens-generated.test.js`의 **부재 단언**에만 남아 있다. 커밋 `c8375ef5`가 삭제하면서 4개 Vitest 파일을 속성 기반 후속 테스트(`theme-contract` 51건, `tokens-generated` 19건, `density-contract` 12건, `topbar-contract` 11건)로 **교체**했다. 복원하지 않는다.
- **지시 1(Header 전폭 알림 제거)** — 상시 안내/장애 Banner는 이미 제거됨. `Banners.jsx`는 대리보기 Strip만 남았고, 상태는 `StatusNotices.jsx`(칩+팝오버) + `NotificationBell.jsx`로 이동. **남은 누수는 Page 내부의 `MirrorNotice.jsx` 전폭 실패 배너와 `지금 동기화` 복구 버튼.**
- **자동 동기화** — `app/worker_main.py` 틱 루프가 매 틱 설정 캐시에서 4개 주기 키를 다시 읽어 동작한다(`notion_docs/tickets/projects_sync_interval_seconds`, `search_index_interval_seconds`). 관리자 설정 가능(`app/settings/registry.py` → `/api/admin/settings`). 즉 **지시 1의 Scheduler 요구는 Backend에서 이미 충족**, 남은 건 UI 노출 정책.
- **지시 29(문서 잠금 제거)** — 현재 소스에 **문서 잠금 기능 자체가 없다.** `is_locked`/`lock_owner` 컬럼·마이그레이션·UI 전무. 검색된 "lock"은 전부 (1) 계정 로그인 잠금, (2) SQLite busy/locked, (3) worker lease lock. 화면의 `열람 제한` 배지는 **접근 제어**이고 지시 55가 명시적으로 보존을 요구하는 대상이다. → 요구 29는 "제거"가 아니라 **"부재 확인 + Evidence 기록 + 동기화 UX 정리"**로 해소한다.
- **아이콘 라이브러리 단일화** — `lucide-react` 제거 완료, `@mui/icons-material` Outlined로 통일(barrel import 금지 static check 존재). 단 지시 79가 요구하는 1.5~1.75 시각 Stroke는 MUI 아이콘이 stroke 기반이 아니라 표현 방법을 다시 정해야 한다(Phase 2에서 결정).

---

## Route Inventory (Source 기준, 2026-08-19)

정본: `frontend/src/app/UserRoutes.jsx`, `frontend/src/app/AdminRoutes.jsx`, `frontend/src/app/navConfig.js`, `frontend/src/screens/registry.js`.
`HashRouter` + `<Routes>` (data router 아님). 사용자 콘솔 `/#/…`, 관리자 콘솔 `/admin#/…`.

- **사용자 Route 28**(catch-all 포함), **관리자 Route 48**(redirect·tab alias·catch-all 포함).
- 관리자 Nav **31항목 / 6그룹** (운영 · 설정 · 사용자와 권한 · 자동화와 연동 · AI · 감사).
- 사용자 Nav **18항목 / 4그룹** (내 업무 · 팀 업무 · 팀 공간 · 내 정보).
- **Dangling nav link 0건** — `nav-active.test.js`가 이미 지키는 불변식이다.
- Sidebar에 없지만 살아 있는 Route: 상세 7종, `/search`(Ctrl+K 전용), `/team-docs/trash`, `/my-display`(UserMenu), `/org-tree`·`/departments`(조직 관리로 병합), tab alias 6종(`/restore-drills`, `/approval-delegations`, `/audit-anomalies`, `/policy-usage`, `/prompt-usage`, `/scheduler-calendar`), legacy redirect 4종(`/system`, `/notion-console`, `/llm-console`, `/maintenance`).
- **Route는 아니지만 독립 화면** — Coverage에 별도 행이 없으면 반드시 누락된다: `SystemOps.jsx`(389), `NotionConsole.jsx`(433), `LlmConsole.jsx`(394), `ops/Maintenance.jsx`(271) — 전부 `/settings` 탭 내부, `system_admin` 전용. `UsersBulk.jsx`(261) — `/users` 내부. `ChatPane.jsx`(554) — `/chat-rooms` + Home 위젯. `AssistantPanel.jsx`(308), `WorkSummary.jsx` — Home 위젯.

### 공유 구현 집중점 — Root Cause가 모이는 곳
| 파일 | LOC | 영향 반경 |
|---|---|---|
| `frontend/src/ui/kit.jsx` | 1819 | PageHeader · DataTable · Modal · FormModal/FormDrawer · EmptyState · ErrorState · Skeleton · Badge · Tag · Card · Callout · MetricStrip · MetaBar · OverflowMenu · SectionTitle · Toast/Confirm — **전 화면** |
| `frontend/src/screens/DataScreen.jsx` | 1109 | `/notifications` + 관리자 단일 Route 16 + 모든 TabShell 탭 본문 ≈ **21 Route** (config는 `screens/registry/*.js` 7개) |
| `frontend/src/app/AppShell.jsx` | 861 | Topbar + Sidebar + CommandPalette — **전 Route** |
| `frontend/src/ui/theme.js` | 494 | Theme SSOT. `tokens.css`(+ `app/static/css/tokens.css`)는 `scripts/generate_design_tokens.mjs` **생성물**이고 `--check`가 CI Gate |
| `frontend/src/app/navConfig.js` / `navIcons.js` | — | 두 Nav + `SCREEN_ROLES`(Route Gate·Sidebar·CommandPalette가 같은 표를 읽음) + 아이콘 매핑 35키 |
| `frontend/src/ui/FilterBar.jsx` + `filters.jsx` | 82+145 | Search/Filter Bar 전체 |
| `frontend/src/ui/cells.jsx` · `bulkSelect.jsx` · `Pager.jsx` · `SavedViews.jsx` · `TabShell.jsx` · `adminKit.jsx` | — | Table/선택/페이지네이션/저장뷰/탭/관리자 Row·Tile |
| `frontend/src/ui/charts/*.jsx` | ~500 | 자체 SVG 차트 5종, 소비처 10파일 |
| `frontend/src/ui/Mascot.jsx` · `lib/assets.js` | 270 | Clovi 전 사용처 |
| `frontend/src/screens/MyTickets.jsx` / `Users.jsx` | 1169 / 1096 | 각각 3 Route / 2 Route |

### RBAC (표시 계층)
서버가 정본(`app/core/authz.py` — 5역할 + `CONSOLE_READ/WRITE/OPS_ROLES` 등, `Depends(require_roles(...))`로 라우트마다 강제). 프런트는 표시용 2계층: `RequireRole`(관리자 Route Gate) + `SCREEN_ROLES`(navConfig.js 단일 표) → Route Gate·Sidebar·CommandPalette가 **같은 표**를 읽는다. `frontend/src/lib/roles.js`는 서버 역할셋의 거울이고 `role-sets-match-backend.test.js`가 동기화를 지킨다. 사용자 콘솔은 Route Gate가 없다(세션 기준 서버 필터링). Feature Flag(`NAV_FEATURE_FLAG`)는 RBAC와 별개 축. 401(`UnauthorizedError`) vs 403(`ForbiddenError`)은 `app/core/errors.py`에서 이미 구분되고, 프런트 401 처리는 `lib/api.js` 한 곳 → `auth.jsx` → `sessionRedirect.js`로 중앙화돼 있다(지시 19의 기반은 이미 존재, 검증·보강 대상).

---

## 재사용할 검증 자산 — `scripts/ui_qa` 하네스 (5,305줄 / 24모듈)
실서버 로그인 → 전체 Route × light/dark × 8뷰포트(390/768/1366/1920/2560/3072/3840/1920@2x) 캡처 → assertion → 오프라인 HTML 리포트. `--fail-on`으로 CI Gate. 세션은 실제 `/login` 폼 통과(계정 없으면 `app.cli.user_cli add` → 실제 `/change-password` 통과). 테마는 localStorage 2키에 심고 `<html data-theme>`로 실제 확인. 전체 화면 캡처는 CSS 조작 없이 내부 스크롤만큼 뷰포트를 키워 다시 찍는다. 번들 지문(`build_before`/`build_after`)으로 실행 중 재빌드 오염을 감지한다.

기존 라벨: `dist/ui-qa/before-renewal/`(584장 — **이전 사이클 이전**의 상태), `deploy3`(288장 — **이번 재작업의 Before**). 둘을 혼동하지 않는다. 이번 사이클 Before는 `deploy3`이며, Notion 매핑을 고친 뒤 Real Data 포함 `before-v7` 라벨로 한 번 더 찍어 두 세트를 모두 Before 증거로 쓴다.

**Evidence 보존 문제**: `dist/`는 gitignore 대상이라 커버리지가 참조하는 Evidence가 커밋되지 않는다. → 전체 실행 결과는 `dist/`에 두되, **주요 Route의 Before/After 큐레이션 세트**(1920 light + 대표 4K)만 tracked `docs/ui-renewal/evidence/`로 복사하고 용량 상한을 둔다. Gate 스크립트는 Evidence 경로가 실제로 존재하는지 검사한다.

하네스는 이미 **Route Inventory를 소스에서 유도**해 `results.json`에 남긴다 — 74행, 필드 `id · hash_path · console · label · min_role · allowed_roles · is_detail · is_public`. `ROUTE_COVERAGE.json`을 손으로 관리하지 않고 **이 목록에서 생성**한 뒤 archetype·audit·evidence 필드를 덧붙인다. 그러면 Gate 규칙 1(소스에 있는데 Coverage에 없는 Route)이 구조적으로 성립한다. 라우터 등록 76건과 하네스 74건의 차이(catch-all·alias)도 Gate가 대조한다.

**새로 만들지 않는다. 여기에 기하/Brand/Clovi Assertion을 추가한다.** (단 테마 키 `clovirone_theme`는 Identity 마이그레이션 대상이므로 하네스도 함께 갱신)

---

## Legacy Product Identity 실측 (지시 72·73)
git-tracked 1,701파일 기준. `clovir` 포함 **254파일**. canonical `clovir[- ]?assist` 143회/57파일 vs legacy `clovir[- ]?one` **939회**.

표기 변형: `clovirone` 767 · `ClovirONE` 148 · `ClovirOne` 12 · `CLOVIRONE` 12.

**단순 치환이 위험한 항목**(런타임 결과가 있음):
- `clovirone_session` — **살아 있는 세션 쿠키 이름**(`app/core/sessions.py:24`). 그냥 바꾸면 배포 순간 전원 로그아웃.
- localStorage 키 5종+ — `clovirone_theme`, `clovirone_theme:<uid>`, `clovirone_accent`, `clovirone_login_welcome`, `clovirone_dismissed_status_notices_v1`, nav-collapsed.
- systemd 유닛 4종 · 시스템 사용자/그룹 `clovirone-web` · `/etc/clovirone-web-assistant/` · DB 경로 `/var/lib/clovirone-web-assistant/web.sqlite3` · nginx conf 파일명 · install/upgrade/rollback/validate/backup 스크립트 5종 · `/home/cloviradmin`.
- **`clovirone-work-assistant`** — n8n Webhook slug(18회). n8n은 **외부 공유 서비스**이고 CLAUDE.md 불변규칙이 임의 변경을 금지한다. 별도 취급.

**건드리지 않는 것**: 실제 DB 업무 데이터(사용자 확정), 고객 자체 시스템명 `ClovirSM`(7회, seed/test 데이터).

**즉시 정리 가능**: `app/static/img/clovirone-{wordmark,wordmark-dark,mark,mark-white,logo-white}.*` — 참조 **0건**인 고아 자산. 신규 `app/static/brand/…/clovirassist-*`로 대체됨.

주의: 빌드 산출물 `app/static/react/assets/*.js`가 **git-tracked**라 소스 rename 후 반드시 재빌드 + 번들 신선도 게이트(`scripts/check_bundle_fresh.py`) 통과가 필요하다.

---

## Clovi 자산 현황 (지시 71)
전부 이미 저장소에 있고 canonical이다. **새 이미지를 생성하지 않는다.**
- `app/static/brand/mascot/clovi-{idle,idle-blink,think,talking,happy,error,sleep,wave,love,avatar,button}.png` (각 ~1.7MB, 1024×1024, **투명 여백 포함**) + `character-sheet.png` + `frames/`·`layers/`(런타임 합성 금지, static check가 강제)
- `app/static/brand/login/clovi-canonical-{avatar,hero,eye-base,eyes-layer}.png` + `mascot-lock.json`(해시·크기·가시영역 계약)
- `app/static/brand/empty-states/*.png` 13종 (`empty-{tickets,docs,trash,chat,board,notify,search}`, `state-{404,500,no-permission,session-expired,offline,success}`)
- `app/static/brand/spot/*.png` 8종, `misc/*` 3종
- 배선: `frontend/src/lib/assets.js`(`MASCOT`/`ART`/`SPOT`/`MISC`) → `frontend/src/ui/Mascot.jsx`(`MascotPose`/`MascotMini`/`MascotTopButton`)
- `EmptyState`의 `art` prop은 **42개 호출부**에서 실제로 쓰이고 있다. `PageHeader`의 `spot`은 현재 no-op(`void spot`).
- 현재 렌더 크기: topbar 28px · sidebar 48 · FAB 58 · drawer 2.25~4rem · welcome 2.5~6rem · login handoff 132px · results rail 4.5rem · game 72px → **투명 여백 때문에 실제 캐릭터는 이보다 훨씬 작다.** 지시 71이 실패로 규정한 상태.
- 원본 `~/Downloads/신규 클로비 이미지.zip`(102MB, 01~10 폴더) 및 압축 해제본 존재 → 저장소 자산과 **diff 대조** 후 최신본 반영 여부 판단.

---

---

## Requirement ID 체계 (지시서 실측)

지시서를 기계적으로 세었다. Matrix가 추적해야 할 ID는 다음과 같고, 이 수가 Coverage Gate의 목표값이다.

| 범위 | 개수 | ID 형식 |
|---|---|---|
| `0. 이번 재작업의 절대 원칙` (하위 8항) | 1 + 8 | `R-0`, `R-0.1`~`R-0.8` |
| `0-1` ~ `0-22` 최상위 지시 | 22 | `R-0-1` ~ `R-0-22` |
| `0-2`의 확인된 Finding | 21 | `R-0-2.1` ~ `R-0-2.21` |
| 상세 요구사항 `1` ~ `84` | 84 | `R-1` ~ `R-84` |
| `84-1` ~ `84-12` 하위 절 | 12 | `R-84-1` ~ `R-84-12` |
| **사용자 보강 요구 (신규)** | **13** | **`R-85` ~ `R-97`** |
| **합계** | **161** | |

### 신규 요구사항 R-85 ~ R-97 — 기능 정확성 축

**ID 충돌 금지**: 지시서의 `R-64`(preview-standalone 폐기)·`R-65`(Design Direction 확정 전 Token 고정 금지)는 **변경하거나 재정의하지 않는다.** 아래는 전부 `R-85` 이후의 새 번호다.

| ID | 요구사항 | 담당 Wave | 주 Gate |
|---|---|---|---|
| **R-85** | Search·Filter·Sort·Pagination·Autocomplete/Combobox를 쓰는 **전체 화면**을 조사하고, 실제 데이터 기준으로 `UI 선택 상태 → Frontend State → URL Query/Route State → API Request Parameter → Backend Query → DB/실제 Data Relation → API Response → Total Count → Rendering된 목록` **사슬 전체가 일치**함을 End-to-End로 검증한다. Frontend에서 Filter 값만 바뀐 것을 정상 동작으로 판단하지 않는다 | W5 설계 · **W5B 조사·수정** · W14 검증 | `FUNCTIONAL_COVERAGE.json` C11 |
| **R-86** | 각 Filter를 **단독 조건과 복수 조건 조합** 모두 검증한다(프로젝트·상태·우선순위·난이도·기한·담당자 등 존재하는 축 전부). 다른 Resource와 연결된 Filter는 **표시 문자열이 아니라 실제 Relation과 안정적 Identifier** 기준으로 동작해야 한다. `미할당 티켓`처럼 Page 기본 Scope가 있는 화면은 **기본 Scope와 사용자 Filter의 결합**을 분리해 Known Data와 대조한다. 누락이 나오면 Frontend뿐 아니라 API Parameter·Backend Join/Relation·Permission Scope·Query Condition까지 추적해 Root Cause를 고친다 | W5B · W14 | C11 + Known-Data 대조 |
| **R-87** | Filter 변경 시 **Pagination이 이전 Page에 남아 0건처럼 보이는 문제**, 빠른 Filter 변경 시 **오래된 응답이 최신 조건을 덮어쓰는 Race Condition**, **Query Key/Cache 오류로 다른 Filter인데 같은 결과가 재사용되는 문제**를 검증하고 고친다. Refresh·Back/Forward 후 **표시된 조건과 실제 Query 조건이 일치**해야 한다 | W5B · W14 | C11 + `stale_data` 상태 |
| **R-88** | Filter UI를 균등 폭으로 기계적으로 배치하지 않는다. 프로젝트처럼 값이 길고 주요 탐색 조건인 항목은 충분한 공간 + 검색형 Combobox. **선택한 값이 무엇인지 알 수 없을 정도로 잘리지 않는다**(Ellipsis를 쓰더라도 Hover/Focus/Dropdown Open으로 전체 값 확인 가능, Dropdown 목록에서도 비슷한 긴 프로젝트명을 서로 구분 가능). `필터 지우기`·`초기화`가 Input/Select와 같은 Grid Cell처럼 보이지 않는다. **결과 건수**는 남는 자리에 놓지 말고 현재 조건에 대한 결과라는 관계가 보이게 배치한다. **데이터 자체가 없는 상태와 Filter 때문에 0건인 상태를 구분**하고, 후자는 적용 조건을 인지하고 쉽게 초기화할 수 있어야 한다 | W5 · W10 | Visual + C11 |
| **R-89** | 티켓 Grid의 **상태·우선순위를 상세 화면 이동 없이 Grid에서 직접 변경**한다. DataTable/Status Cell 스타일 변경만으로 완료 처리하지 않는다. 공통 **Property Editing Pattern**을 설계하고 `현재 값 → 변경 가능한 값 → 선택 → Saving → 성공 → 실패 → Rollback → 권한 없음 → 중복 요청 방지` 상태를 전부 포함한다. **Frontend State만 바꾸지 않고 Backend 저장을 확인하며 필요하면 재조회해 실제 값으로 갱신**한다. 실패 시 이전 값으로 안전 복구. Frontend의 변경 가능 여부와 Backend Authorization이 일치해야 한다 | **W6 공통 계층 · W9 티켓** | W14 실제 클릭·저장 E2E |
| **R-90** | Detail 상단 속성 영역을 **폭 조정으로 끝내지 않는다.** 긴 흰 Box에 모든 Label/Value를 동일 강도로 나열하는 구조를 유지하지 않고, **먼저 판단해야 하는 정보와 보조 Metadata를 구분**한다(티켓: 상태·프로젝트·담당자·우선순위·마감 vs 티켓번호·난이도·예상 WD). 모든 Property를 Card/Badge로 만들지 않고 Compact Strip·Property Group·Definition Layout 중 적절한 표현을 고른다. 넓은 화면에서 속성 간격만 늘어나 시선 이동이 커지지 않고, 좁은 화면에서 중요 값을 잘라내지 않는다. **긴 프로젝트명 실데이터로 FHD/QHD/4K/Zoom 검증.** 자주 바뀌는 Property는 Detail 상단 Inline Edit 적절성을 판단하되 **Grid·Detail Header·Form이 같은 값을 서로 다른 Interaction으로 중복 구현하지 않는다**(R-89의 공통 Model 사용). 같은 Metadata/Detail Pattern의 전체 Consumer 조사 | W7 · W9 | Visual + W14 |
| **R-91** | DataTable의 **동일 값 Column 자동 제거**를 현재 렌더된 행만 기준으로 적용하지 않는다. Pagination·Server-side Search/Filter에서는 현재 Page의 값이 같다고 전체 Result Set이 같은 게 아니다. **Page 이동·Filter 변경마다 Column이 생겼다 사라지는 불안정한 Layout을 만들지 않는다.** 제거는 값이 **Page Context 또는 Query Scope 때문에 구조적으로 동일**함이 확실할 때만(전용 View·명시적 Filter 적용·Backend Query Contract상 불변) | W6 | 단위 테스트 + C10 |
| **R-92** | W14의 범위를 "주요 Workflow"로 제한하지 않는다. 사용자·관리자 **전체 Route와 주요 Interactive Function을 Inventory**해 Functional Coverage Matrix를 만들고 27개 범주(Search·Filter·Sort·Pagination·Combobox·Create·Read·Edit·Delete·상태 변경·우선순위 변경·담당자 변경·Inline Edit·Form Validation·Modal/Drawer Action·Row Action·Context/Overflow Action·Navigation·Deep Link·Refresh·Back/Forward·첨부/다운로드·Notification Action·Approval Action·Settings Save/Apply/Test·관리자 운영 Action·권한별 노출/401/403/Session Expiry/Loading/Empty/Error/Long Text/Many Data)를 검증한다. **존재하는 기능만 검증하고 없는 기능을 테스트용으로 만들지 않는다.** 실데이터 영향 Action은 전용 QA Fixture 사용 후 정리 | W14 | C12 |
| **R-93** | **화면 간 데이터 정합성.** 한 화면 API가 200이라고 완료 처리하지 않는다. 티켓 상태를 바꿨다면 Grid·상세·내 티켓/팀 티켓/미할당 포함 여부·Dashboard/Home Count·Sprint/업무량 집계까지 실제로 일치하는지 확인한다. Dashboard·Home·Sprint·관리자 Overview의 Count/KPI/Chart도 렌더 여부가 아니라 **Source Data와 계산 결과**가 맞는지 검증하고, 같은 Resource/Derived Metric을 화면마다 다른 기준으로 계산해 숫자가 어긋나지 않는지 확인한다 | W14 | C13 |
| **R-94** | 죽은 UI·Backend 미연결을 **관리자뿐 아니라 사용자 영역까지** 전수조사한다: 눌러도 동작 없는 Button · Frontend만 바뀌는 기능 · Backend는 저장됐는데 화면이 갱신 안 되는 기능 · API는 있는데 UI 미연결 · UI는 있는데 Backend 없음 · 죽은 Route · 잘못된 Query Parameter · 관계 데이터 연결 누락 · 오래된 Cache · 중복 요청 · Race Condition · 권한 불일치. 발견한 문제가 이번 리뉴얼과 관련된 실제 제품 기능이면 **제보를 기다리지 않고 Root Cause를 고친다** | W5B · W12 · W14 | C12 + C14 |
| **R-95** | **Functional Coverage를 기계적으로 추적한다.** ROUTE_COVERAGE와 Requirement Matrix로 대신하지 않는다 — Route가 있고 Screenshot이 있다는 사실은 기능이 정상이라는 증거가 아니다. `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`에 각 Route의 주요 Action/Workflow를 `NOT_AUDITED / PASS / FAIL / BLOCKED`로 추적하고, **`PASS`는 실제 Browser Action + Network/API/Backend/Data 결과 Evidence를 요구**한다. 렌더 Evidence만으로 Functional PASS를 만들 수 없다. **최종 Gate에서 `NOT_AUDITED`가 남으면 완료가 아니다** | W0 신설 · 전 Wave 갱신 | C11~C14 |
| **R-96** | **계획 구조 무결성**: 이름 없는 Wave, 존재하지 않는 Phase/Wave 참조, 비어 있는 소유 파일/전제 항목, `작성 중` 같은 실제와 불일치하는 상태 표기가 0건이어야 한다. 각 Wave의 종료 내용은 별도 행이 아니라 해당 Wave의 **Exit Gate 안에** 있어야 한다. **최종 완료 조건에 R-85~R-95의 PASS 항목을 추가**한다 | W0 | Plan Gate `--stage plan` |
| **R-97** | 최종 실행 계획과 **대화 Context 없이 재개 가능한 인계 상태**를 프로젝트 내부 지속 문서에 기록한다: 최종 실행 계획 · Requirement Matrix · Route/Page/Archetype Coverage · Functional Coverage · 현재 Git 상태와 기준 Commit · 현재 Build Fingerprint · Before Evidence · Wave 순서와 Exit Criteria · 현재 Blocker · 다음 실행 명령. WORK_STATE의 압축 복구 구조와 **Gate 우선 원칙**을 유지한다 | W0 | Plan Gate + WORK_STATE 검사 |

최상위 지시(0-x)가 상세 요구사항(1~84)과 충돌하면 최상위가 우선한다(지시서 8행). 특히 Brand Color는 0-1이 요구 53·65를 덮어쓴다.

기존 `scripts/check_traceability.py`(174줄)가 이미 지시 56 Gate를 구현하고 있다 — 번호 누락 0건 / 빈 필드 0건 / 없는 Phase 참조 0건 / 자기모순 0건. 다만 대상이 삭제된 `docs/UI_RENEWAL_TRACEABILITY.md`이고 범위가 1~70이다. **새로 만들지 않고 이 스크립트를 새 Matrix(**161 ID**)와 `ROUTE_COVERAGE.json` 규칙 + `FUNCTIONAL_COVERAGE.json` 규칙까지, 총 14개 조건으로 확장한다.**

---

## Root Cause → 공통 Consumer (지시 84-2)

사용자가 캡처로 지적한 문제를 화면별 CSS 수정으로 계획하지 않는다. 각 증상의 공통 원인과 전체 소비처는 다음과 같다.

| # | 증상 (지시 번호) | Root Cause 위치 | 소비처 |
|---|---|---|---|
| R1 | Brand가 Logo에만 존재, Active가 얇은 Blue Rail (0-1·13·79) | `ui/theme.js`의 `BRAND` 상수가 **consumer 0건** + `primary`가 사용자 Accent(기본 파랑)와 동일 | 전 Route. `AppShell.jsx`(Topbar/Sidebar), `navIcons.js`, 모든 Primary Button, Chart, Focus |
| R2 | White Card 반복·거대 Blank (0-2·15·16·82) | `kit.jsx::Card`를 Layout 정렬 목적으로 사용 + `EmptyState`가 Page/Region 구분 없음 + `DataScreen.jsx`가 빈 데이터에도 Filter/SavedViews/Table shell/Pager 2개를 항상 렌더 | `DataScreen.jsx` → 21 Route. `Home.jsx`, `Sprint.jsx`, `MyStats.jsx`, `Board.jsx`, `Games.jsx`, `MyApprovals.jsx`, `OrgConsole.jsx` |
| R3 | 균등 Column·짧은 값 낭비·긴 값 줄바꿈 (18·74·75·77) | `kit.jsx::DataTable`에 **데이터 의미 기반 Column 계약이 없음**(`align`은 39곳만 지정, `identifier` 32곳). `MetaBar`는 `flex:1 1 9rem` 균등, `MetricStrip`은 의도적 균등 | `DataTable` 소비 24파일 + `registry/*.js` **컬럼 정의 ~216개** + 원시 `<Table>` 2곳(`DevReport.jsx`, `MyTickets.jsx`) |
| R4 | Header/Cell 정렬 불일치·숫자 비교 불가 (19) | 위와 같음. `DataTable`은 header/cell에 같은 `c.align`을 넘기므로 **구조는 맞고 값이 안 채워진 상태**. `NUMERIC`(tabular-nums)이 숫자 셀에 적용되지 않음 | 동일 |
| R5 | 고립된 Filter·큰 빈 Filter Rectangle (17·76·80) | Filter 영역을 `Card`로 감싸는 관행 + `FILTER_GRID_SX`의 `auto-fit` 트랙이 항목 수와 안 맞을 때 고아 줄 생성 + 의미 Grouping 부재 | `ui/FilterBar.jsx`, `ui/filters.jsx`, `DataScreen.jsx` filter 렌더 루프, `TicketFilterBar.jsx`, `Board.jsx`, `TeamDocs.jsx`, `Sprint.jsx` |
| R6 | 프로젝트/담당자가 일반 Dropdown (5·17·76) | `filters.jsx`에 `FilterSelect`만 있고 검색형 Entity Selector 없음(`type:"select"` 80+곳, Autocomplete는 `MyTickets.jsx` 1곳) | 13개 Route × 다수 필드 (프로젝트·담당자·부서·작성자·조직·직책·워크플로·템플릿·사용자) |
| R7 | Detail 한쪽 쏠림·큰 빈 공간 (20·75·81) | Detail 계약이 하나뿐 — `density.js::BASELINE_TRACKS.detail`을 Reading Page에도 그대로 사용. 보조 Rail에 넣을 **Context 자체가 없음**(티켓 활동 이력 API 부재) | `Ticket.jsx`, `TeamDoc.jsx`, `BoardPost.jsx`, `Project.jsx`, `Users.jsx` drawer |
| R8 | 일반 사용자에게 운영 정보·수동 동기화 (1·9·29·36·0-15) | `ui/MirrorNotice.jsx`가 전폭 실패 배너 + `지금 동기화` 복구 버튼을 role 구분 없이 렌더 | `TeamDocs.jsx`, `TeamTickets.jsx`, `MyTickets.jsx`, `Home.jsx`, `MyStats.jsx` |
| R9 | 긴 설명문이 본문 점유 (3·44·0-12) | `DataScreen`의 `emptySituation/emptyPrerequisite/emptySteps/emptyExpected`가 본문 인라인 렌더 + Page 상단 설명 단락 관행 | `registry/automation.js::documents` 등 registry 전반, `Projects.jsx`, `TeamDocs.jsx`, `Ideas`, `Games`, `Sprint.jsx`, `OrgConsole.jsx` |
| R10 | Alert가 전부 큰 Border Box (35·20·67) | `kit.jsx::Callout`이 사실상 한 가지 강도로만 사용됨. 참고 정보와 조치 필요 경고가 동일 표현 | `MailStatus.jsx`, `NotionConsole.jsx`, `LlmConsole.jsx`, `SettingsMain.jsx`, `DataScreen.jsx`, `MirrorNotice.jsx` |
| R11 | Raw Key·환경변수·내부 상태값 노출 (36·39·40·22) | 화면이 Backend 식별자를 1차 Column/문구로 사용 | `/feature-flags`, `/mail`, `/jobs`, `/documents`, `/integrations`, `/notion-mapping`, `/settings` |
| R12 | 작은 Clovi (71) | `ui/Mascot.jsx`가 **CSS box 기준**으로 크기를 주고 1024² PNG의 투명 여백을 보정하지 않음 | `AppShell`(topbar 28px), `AssistantDrawer`, `WelcomeStatus`, `ResultsRail`, `LoginHandoff`, `StageShared`, `EmptyState art` 42곳 |
| R13 | 관리자 Sidebar 과다 노출·중복 기능 (30·41·48·51) | `navConfig.js::NAV` 31항목이 기능 1:1. `AdminRoutes.jsx`의 `TAB_GROUPS`는 5쌍만 병합 | 관리자 48 Route 전체 |
| R14 | Legacy Product Identity (72·73) | 이름이 **런타임 식별자**로 쓰임 — 세션 쿠키, localStorage 키, systemd 유닛, 시스템 사용자, 경로, nginx conf, 스크립트명, 번들 | git-tracked 254파일 + 서버 설치본 |

### 기능 정확성 축의 Root Cause (R-85~R-95)

디자인 축과 **같은 방식으로** 다룬다 — 한 화면의 증상을 그 화면에서 고치지 않고 공통 원인과 전체 소비처를 찾는다. 아래는 실제 소스를 읽고 확인한 것이다.

| # | 증상 | Root Cause (실측) | 소비처 |
|---|---|---|---|
| **R15** | **프로젝트 Filter를 걸면 실제로 연결된 티켓이 누락된다**(사용자가 겪은 증상) | `app/tickets/repository.py:80`의 주석이 메커니즘을 말한다 — `TicketDTO.project_ids`는 **외부 relation을 캐시로 Portal id에 해석한 값**이고 "캐시가 준비되기 전에는 Portal id를 알 수 없다". `TicketFilters.matches:147`은 `self.project_id not in ticket.project_ids`로 거른다. 즉 **relation은 존재하는데 `project_ids`가 아직/영영 비어 있으면 그 티켓은 조용히 떨어진다.** 게다가 Filter의 **옵션 목록은 다른 소스**(`/api/tickets/projects` → `service.list_projects`)라 옵션에는 보이는 프로젝트가 티켓 쪽 식별자와 안 맞을 수 있다. `repository.py:168-170`의 `project_any_of`는 `len(project_ids) != 1`이면 탈락시키는 별도 경로까지 있다 | `/my-tickets` · `/unassigned` · `/team-tickets` · `/projects/:id` 티켓 탭 · `/sprint` · Home 위젯 |
| **R16** | Filter 조합·기본 Scope 결합이 검증된 적이 없다 | `TicketFilterBar.jsx:100-108 ticketQueryParams`는 `fields`를 그대로 서버로 보내고(서버 필터링), `matchesTicketFilters:120`은 **Sprint 전용 클라이언트 판정**이며 판정 불가 조건에서 **일부러 throw**한다(설계는 옳다). 문제는 이 두 경로와 **Page 기본 Scope**(`/unassigned`, `/mine`, `/team`)의 **결합**이 Known Data로 대조된 적이 없다는 것 | 위와 동일 + `SPRINT_FIELDS`·`SPRINT_REPORT_FIELDS` 경로 |
| **R17** | Filter 변경 시 Pagination·Cache·Race가 검증되지 않음 | `ticketQueryParams`는 `state.page > 1`이면 `page`를 그대로 싣는다 — **Filter를 바꿀 때 page를 1로 되돌리는 책임이 호출부에 있고 공통 계층에 없다.** react-query key가 조건 전체를 포함하지 않으면 다른 Filter에 같은 결과가 재사용되고, 포함하더라도 수동 fetch 경로에는 최신 응답 보장이 없다 | `useTicketList` 소비처 5곳 + `DataScreen.jsx`의 목록 전체 + `useQueryState.js` |
| **R18** | **Grid에서 상태·우선순위를 바꿀 수 없다** | 공통 **Property Editing Pattern이 존재하지 않는다.** 변경은 `MyTickets.jsx:493`의 상세 PATCH 뮤테이션 한 곳뿐이고 Grid에는 진입점이 없다. Grid·Detail Header·Form이 같은 값을 각자 구현할 여지가 그대로 열려 있다 | 티켓 Grid 3종 · 티켓 상세 · 관리자 `DataScreen` 목록의 상태성 컬럼 |
| **R19** | 화면 간 숫자가 어긋날 수 있다 | 같은 Resource를 화면마다 다른 소스에서 센다 — Home은 `/api/home/today`+`/work-dashboard`, 목록은 `/api/tickets/*`, Sprint는 `/api/sprint/summary`, 관리자는 `/api/admin/dashboard`(`app/health/router.py`). 무효화는 `cross-screen-invalidation.test.jsx`가 일부만 지킨다 | Home · Dashboard · Sprint · MyStats · 목록 3종 |

**두 축은 같은 Wave에서 만난다**: R18은 W6(공통 Table 계층)에서 Pattern을 만들고 W9(티켓)에서 배선한다. R15~R17은 W5B 전담 Wave에서 Root Cause를 고치고 W14에서 전수 검증한다. R19는 W14의 정합성 검증이 담당한다.

---

## 지금 결정된 실행 원칙

1. **공유 계층 먼저.** `kit.jsx`(R2·R3·R4·R7·R10) + `DataScreen.jsx`(R2·R5·R9) 두 파일이 21개 관리자 Route와 모든 사용자 목록 화면을 동시에 고친다. Page 파일을 한 장도 건드리기 전에 여기서 대부분이 해결된다.
2. **관리자 IA 병합은 마지막.** 공유 컴포넌트가 흔들리는 동안 Route를 합치면 diff를 검증할 수 없고, RBAC 동등성 검사(`sameRoles`)는 안정된 `SCREEN_ROLES` 위에서만 의미가 있다.
3. **역할 집합이 다르면 병합하지 않는다.** `/notion-mapping`(CONSOLE_READ)을 `/users`(CONSOLE_WRITE=admin+)에 합치면 권한이 깨진다 → 독립 Page 유지. Sidebar 숫자를 줄이려고 RBAC를 왜곡하지 않는다(지시 51).
4. **옛 주소는 Redirect가 아니라 제자리 렌더.** `AdminRoutes.jsx`가 이미 쓰는 패턴 — `<Navigate>`는 hash query를 버려 저장된 뷰/딥링크를 조용히 깨뜨린다.
5. **재사용할 것과 다시 설계할 것을 분리한다**(지시 50·70). 재사용: 데이터 처리, 권한 처리, 접근성 로직, `ui_qa` 하네스, 토큰 생성 파이프라인, `DataTable`의 `minWidth`/`identifier`/`hideNarrow`/카드뷰 fallback, `FilterBar`의 두 줄 분리(ToolbarRow/FilterBarGrid). 재설계: Brand/Theme, Chrome, Surface 사용, Column 계약, Empty 정책, Entity Selector, Detail/Reading 계약, 관리자 IA.

---

---

## Design Direction — 인디고 계측면 (Indigo Instrument)

> 제품은 운영 계측기이고, **그 계측기의 하우징이 ClovirAssist 인디고다.** Top bar와 Sidebar가 하나의 L자 Brand 오브젝트로 연결되고, 그 안에 차가운 인디고 계열 Work Canvas가 놓인다. 데이터는 흰 판 위에서 무채색·정밀하게 유지하고, Brand 채도는 바깥(Frame)으로 갈수록 강해지며 안쪽으로는 **제품이 곧 Brand인 세 자리** — Primary Action · 현재 선택 · Clovi/AI — 에서만 나타난다.

검토한 대안과 기각 사유:
1. **기존 밝은 Chrome에 보라 Tint만** (`#E7EAEE`→`#EDEAF6`) — 지시 70이 금지한 "색만 바꾸기". 로고를 가리면 여전히 아무 말도 안 한다.
2. **전면 Dark** — Print/Audit용 Light를 버리고, Dark ≠ ClovirAssist라 Brand 인식 문제를 못 푼다.
3. **`c8375ef5` 그대로 revert** — 방향의 조상이지만 그대로 되돌리지 않는다. 그때 잘못된 건 인디고가 아니라 **Gradient Chrome이 장식이고 미측정이었다는 것**(Sidebar는 flat 대비 1건, Topbar Gradient는 0건), 그리고 판에 그림자+18px 반경이 있어 데이터가 Frame만큼 시끄러웠다는 것이다. **인디고 재료는 그 커밋에서 가져오고, 현재 커밋이 벌어들인 계측 규율(tabular numerals, 선 위주 위계, 판에 그림자 없음, 선택 신호 하나, 모든 색쌍 실측)은 유지한다.**

**반증 가능한 판정 기준**: 로고를 가려도 화면이 ClovirAssist라고 말하는가. 이걸 희망이 아니라 **테스트**로 박는다 — `blue(chrome.shell) − red(chrome.shell) ≥ 24` (`#1E2758` → 88 ✓ / 현재 `#E7EAEE` → **7 ✗**). 이 단언이 없었기 때문에 지금 상태가 통과했다.

### Brand Identity vs 사용자 Accent — 역할 분리 (지시 0-1 핵심)

| | **Identity 계층 — `palette.brand` + `palette.chrome`** | **Interaction 계층 — `palette.primary` (사용자 Accent)** |
|---|---|---|
| 누가 정하나 | `theme.js` 고정. **사용자 입력으로 바꿀 수 없다.** | 사용자 (`/my-display` → `AccentPicker`) |
| 소유 범위 | Chrome Shell(Top bar+Rail), Brand Gradient, 로고 "Assist" 워드마크, Clovi Halo/Ring, AI 영역 Surface·Wash, Chart 주요 Series, Brand Tint, Onboarding/Hero | Contained/Text/Outlined Primary Button, Link, Canvas 위 Focus Ring, Tab Indicator, 선택 Row Wash, Checkbox/Switch/Slider, Form Focus |
| 막는 실패 | 사용자가 청록을 고르면 제품이 ClovirAssist가 아니게 되는 것 | 모두에게 같은 Accent를 강제하는 것 |

Accent 기능은 **보존하고 오히려 강화**된다 — 우연히 제품 정체성 전체가 되는 대신 명확한 역할을 갖는다. `AccentPicker` 문구에 이를 명시한다.

**새 기본 Accent**: `#5A4FCF` (색상각 ≈245°, 진짜 인디고-바이올렛). 흰 글자 대비 **6.08:1** (기존 기본값 4.68:1보다 개선). 기존 hex는 **하나도 제거하지 않는다** — 제거하면 그 색을 고른 사용자의 "선택됨" 표시가 사라진다(`theme.js:46-50`이 이미 경고).
`ACCENT_PRESETS = ["#5A4FCF" 브랜드 인디고(신규 기본), "#536CD6" 밝은 인디고(이름만 변경), "#4058BD" 진한 인디고, "#6B5BC7" 보라, "#327C98" 청록]`

### 토큰 (실측 대비값 포함)

**중립 램프 — 인디고 계열, 절대 따뜻하지 않게 (모든 항목 `B ≥ R`)**

| Token | Light | Dark |
|---|---|---|
| `background.canvas` | `#EEF0F7` | `#0A0C16` |
| `background.plate` | `#FFFFFF` | `#141829` |
| `background.inset` | `#F5F6FB` | `#1C2136` |
| `background.sunken` | `#E5E8F3` | `#0F1322` |
| `background.brandTint` **(신규)** | `#E9ECFA` | `#1E2244` |
| `divider` / `dividerStrong` | `#DCDFEC` / `#BCC2D9` | `#242A46` / `#333B5E` |
| `text.primary` / `.secondary` / `.faint` | `#161A2C` / `#565E7A` / `#5C6480` | `#E5E8F5` / `#9BA4C4` / `#8C96B8` |

**Chrome — `palette.chrome` (신규, Brand 고정)**

| Token | Light | Dark |
|---|---|---|
| `shellTop` / `shellMid` / `shellDeep` | `#28336F` / `#1E2758` / `#17204D` | `#232A5E` / `#1A2046` / `#141936` |
| `shell` (flat base = `sidebar.bg`) | `#1E2758` | `#1A2046` |
| `shellImage` (= `sidebar.bgImage`) | `linear-gradient(180deg,#28336F 0%,#1E2758 55%,#17204D 100%)` | `linear-gradient(180deg,#232A5E 0%,#1A2046 60%,#141936 100%)` |
| `aiWash` | `radial-gradient(120% 200% at 100% 0%, rgba(142,117,225,.26), transparent 60%)` | 동일 |
| `onShell` / `onShellMuted` / `onShellFaint` | `#EAEDFB` / `#AFBBE8` / `#98A5DC` | `#E4E8F8` / `#A3AEDC` / `#94A0CE` |
| `line` / `hover` / `selected` | `#2E3A7B` / `rgba(255,255,255,.06)` / `.10` | `#2A3162` / `.08` / `.12` |
| `rail` (**Brand 고정 — 더 이상 `primary.main`이 아니다**) | `#A9BAFF` | `#A9BAFF` |
| `focusRing` (Shell 위) | `#C3CEFF` | `#C3CEFF` |

**Brand — 기존 4키(`deep #17204D` · `mid #293B8D` · `purple #8E75E1` · `mint #62C7BD`)는 값 그대로 유지하고 6키 추가**: `core #4C58C8`/`#8E9BF2`, `indigoInk #3B47A8`/`#A9B6F5`, `violetInk #6A4FC4`/`#C0AEF7`, `mintInk #1F6F68`/`#7FD6C9`, `pinkInk #9E3A62`/`#F4A8C6`, `wordmark #5A4FCF`/`#B7C4FA`.
**상태색 계열은 그대로 둔다** — Accent와 섞이지 않는 독립 계열이라는 기존 계약을 유지(Light `success.bg`·`info.bg`만 새 Canvas에 맞춰 미세 조정).
Dark 파생 혼합비 `strongMix 0.72 → 0.62` — `brandTint`가 실제 텍스트 면이 되면서 0.72에서 링크색이 4.48:1/4.51:1로 떨어졌다. 0.62면 5개 Preset × 4개 Dark 면 최악값 **5.46:1**.

**실측 AA 대비 (전부 통과, `theme-contract.test.js`가 단언할 값)**
Light 잉크: `text.primary` 17.24~13.85 · `text.secondary` 6.41~5.15 · `text.faint` 5.85~4.78 (plate/inset/canvas/sunken/brandTint).
Dark 잉크: 14.42~12.57 / 7.13~6.22 / 6.01~5.24.
Chrome 위 글자(Gradient **모든 stop**): `onShell` 10.04~14.07 · `onShellMuted` 6.19~7.89 · `onShellFaint` 4.88~6.69 · `#FFFFFF` 11.71~17.18.
Hover/Selected Wash 합성 후: `onShell` 8.44/8.64, `onShellMuted` 5.20/4.85.
**AI Wash 합성 후**: `onShell` 7.35 통과, `onShellMuted` **4.53(L)/3.94(D)** → **하드 룰: AI Wash 영역 안에는 `onShellMuted`/`onShellFaint` 텍스트 금지, 전부 `onShell`.** 이것도 단언한다.
Focus Ring: Canvas `#4038B8` 6.93~8.48 / `#9FB0FF` 7.52~9.26. Shell 위 `#C3CEFF` 7.58~10.07. Active Rail `#A9BAFF` 6.22~9.13 (비텍스트 ≥3).

### Chrome 설계 — Header·Sidebar·Canvas를 하나의 Brand System으로

Top bar와 Sidebar는 **같은 재료**다. 만나는 모서리가 같은 색인 이유는 Top bar의 채움이 Sidebar Gradient의 **첫 stop**이기 때문이다.
- Top bar: `chrome.shellTop` + `chrome.aiWash`(우상단 앵커 — Clovi·종·아바타가 사는 자리). 높이 유지(52/60/68).
- Sidebar: `chrome.shell`(solid hex — 기존 "그라디언트 아님" 단언 유지) + `chrome.shellImage`(background-image).
- Canvas: `background.canvas`. 전체가 인디고 하우징 안의 계측면으로 읽힌다.
- Top bar 검색: Brand 위 inset — `rgba(255,255,255,.10)` fill, `.14` border, placeholder `onShellMuted`, 값 `onShell`.
- `ConsoleSwitch`(사용자/관리자): 인디고 위에서 반전 — track `rgba(255,255,255,.08)`, 선택 `.16` + `inset 0 0 0 1px rgba(255,255,255,.22)`.

**Navigation 상태 — 신호는 정확히 둘 (지시 79)**
현재 `AppShell.jsx:414-441`은 **넷을 겹친다**: 2px rail + `fontWeight 700 vs 600` + 색 + `icon opacity 1 vs .82`. 굵기 변경은 한글에서 실제 **레이아웃 흔들림**까지 만든다.

| 상태 | 위치 신호 | 색 신호 | 금지 |
|---|---|---|---|
| default | — | label+icon `onShellMuted` | |
| hover | — | row bg `chrome.hover`, 잉크 → `onShell` | rail·굵기 |
| **active** | **3px `chrome.rail` inline-start** | row bg `chrome.selected`, 잉크 → `onShell` | **굵기 변경·배경 알약·아이콘 fill 교체 금지** |
| focus-visible | — | `outline: 2px chrome.focusRing; outline-offset:-2px` | |

아이콘과 라벨은 **항상 같은 색으로 함께** 변한다 → 두 개가 아니라 **하나의 신호**. Nav 라벨 굵기는 제품 전체에서 `medium(500)` 고정.

**사용자 vs 관리자**: Shell·항목 해부구조·상태 계약·아이콘 규칙 **완전 동일**. 차이는 깊이 표현뿐 — 사용자는 그룹 펼침 기본, 관리자는 접힘 기본 + 메뉴 필터 노출.

### Surface 위계 (지시 82)

| Token | 담을 수 있는 것 | Border | Radius | Shadow |
|---|---|---|---|---|
| `canvas` | Section 제목·Divider·Grid gap. **맨 문단 금지.** | — | — | — |
| `plate` | 자기 생명주기를 가진 경계 객체 | `1px divider` | `md`(8) | 없음 |
| `inset` | Table head·읽기전용·code·diff·hover/selected row | 없음 | full-bleed 0 / 단독 `sm` | 없음 |
| `sunken` | track·skeleton·chart band | 없음 | `sm` | 없음 |
| `brandTint` | AI/Assistant/Brand 순간 | `3px brand.core` inline-start edge | `md` | 없음 |
| `shell` | Top bar + Sidebar **전용** | `chrome.line` | 0 | 없음 |
| overlay / modal | 메뉴·팝오버·툴팁 / 다이얼로그·드로어 | `1px divider` | `lg`(14) | `overlay` / `modal` |

**구획별 판정 체크리스트 (첫 Yes에서 멈춘다)**: ① 자체 Action이나 생명주기(save/cancel·독립 확장·독립 error/empty/loading)가 있나 → plate ② 페이지와 독립적으로 스크롤/오버플로하나 → plate ③ 떠 있나 → overlay/modal ④ 입력/읽기전용 함몰면인가 → inset ⑤ AI/Brand 순간인가 → brandTint band ⑥ 그 외 → **컨테이너 없음.** `SectionTitle` + `SECTION_GAP` + 목록이면 제목 아래 `1px divider`.

**하드 금지 (각각 현재 스크린샷의 무언가를 죽인다)**: plate 안의 plate 금지 / 판독 한 줄에 plate 금지(`MetricStrip`의 `<Card>` 제거 → `user_me.png`·`admin_dashboard.png`의 가장 큰 빈 흰 사각형이 사라진다) / 목록 하나뿐이고 Action 없는 plate는 divider group이다(`admin_dashboard.png`에서 plate 4장 제거) / 3줄 미만 내용의 plate는 row다 / **없는 데이터를 위한 컨테이너를 그리지 않는다.**

### Typography · Density (지시 14)

실제 스크린샷 판정: 문제는 "14px가 작다"가 아니라 **7단계 중 4단계가 3px 밴드 안에 몰려 있어(11/12/13/14) 위계 일을 전혀 안 한다**는 것. `body 14 → title 17`이 1.21배라 구획 제목이 제목으로 안 읽히고 화면 전체가 한 겹 질감이 된다. 그리고 **11px micro는 한글에 실제로 너무 작다** — `tiny_text` 검사가 폭 ≥2200에서만 돌아 1920에서 안 잡힐 뿐이다.

| 역할 | 현재 | **신규** | @16 root | line-height | 용도 |
|---|---|---|---|---|---|
| `micro` | 11 | **0.75rem** | 12 | 1.4 | 셀 내부 배지/메타. **절대 하한.** |
| `caption` | 12 | **0.8125rem** | 13 | 1.45 | 라벨·각주·breadcrumb·nav group |
| `bodySm` | 13 | **0.875rem** | 14 | 1.55 | 밀집 표 칸 |
| `body` | 14 | **0.9375rem** | 15 | 1.6 | 기본 본문·nav 라벨·입력값 |
| `title` | 17 | **1.1875rem** | 19 | 1.3 | 구획 제목 |
| `pageTitle` | 22 | **1.75rem** | 28 | 1.22 | 화면 제목 |
| `readout` | 28 | **2.5rem** | 40 | 1.05 | 그 화면을 지배하는 판독값 하나 |

슬롯 수 7 유지 → 기존 "7개 서로 다른 값" 단언 통과. 머리쪽이 1.27×/1.47×/1.43×로 열려 제목이 실제로 앞선다.
**Control 높이**: Button 32→**34**(small 28→30, large 38→40, 기존 28~36 단언 유지) · Input ~30→**36** · in-table dense **32** 신설 · IconButton 32→**34 시각 + 40 히트영역**(`::after{inset:-3px}`, WCAG 2.2) · nav item 34→**38** · table row **44**(compact 36) · Tab 38→**40**.
**Spacing**: `spacing()`은 손대지 않는다(4K rem 레버의 근거). `density.js`만 `cardPadding 20→24`, `sectionGap 24→32`, `gridGap 16→24`, `healthGridGap 12→16` — `density-contract.test.jsx`는 **관계만** 단언하므로 통과.
**Radius** `{4,6,10,999}` → `{6,8,14,999}` — 기존 4개 단언 전부 통과. 생성기가 `--radius-*`를 Jinja로도 내보내므로 로그인 카드가 자동으로 따라온다.

### Data Visualization

**자체 SVG vs 라이브러리 — 정직한 판정(지시 54)**: 7축 평가 결과 **자체 SVG를 기본 계층으로 유지하되 그대로 두지 않는다.** 자체 SVG가 이기는 두 축이 하필 제품이 **계약상 지켜야 하는** 두 축이다 — ⓐ **접근성**: `aria-hidden` svg + 모든 숫자를 다시 적는 텍스트 범례 → 키보드·스크린리더·색맹·흑백 인쇄에서 동작. Recharts는 기본이 hover tooltip. ⓑ **4K/rem**: SVG 안에 `<text>`가 **하나도 없어서** `root.css` 폰트 레버가 라벨까지 움직인다. Recharts는 축 텍스트를 px `<text>`로 그려 레버를 안 따르고 `tiny_text` 바닥 아래로 떨어진다. 지는 두 축(시각 품질·인터랙션)은 기존 500줄 안에서 고칠 수 있다.

**필수 업그레이드**(= "존재해서 유지"가 아니라는 근거): ① `background.sunken` 수평 grid 3~4선(`vectorEffect="non-scaling-stroke"`), 축 눈금 라벨은 **HTML로 SVG 바깥에** ② `LineSeries` 1번 시리즈 아래 14% alpha 영역 채움 ③ 시리즈 ≤3이면 **끝점 직접 라벨**(HTML 절대배치), 범례는 a11y fallback으로 유지 ④ `<circle>` 마커에 `tabindex="0"` + `aria-label` → hover 없이 키보드로 값 도달 ⑤ 단위는 축에 **한 번만**(`(단위: 인일)`) ⑥ 시리즈 상한 5, 초과분은 `기타`.

**Brand 고정 Chart 팔레트** — 1번 시리즈는 **항상 Brand 인디고**. 전부 plate/inset/canvas 대비 ≥3:1 실측.
`1 #4C58C8`(solid) · `2 #C0517E`(dash 4 3) · `3 #2C3684`(dot 1 3) · `4 #8158D8`(dash-dot) · `5 #2E9086`(long-dash) · `rest #5D6B93`. Dark: `#8E9BF2 · #F49CBE · #DDE3FF · #C0A2FF · #4FBFB2 · #7C88AE`.
인접 슬롯 휘도 분리의 **최대 달성치가 1.26:1**이다 — 즉 **색만으로는 2개 시리즈 이상을 절대 못 나른다.** 그래서 선 스타일 + 직접 라벨 + 숫자 범례가 선택이 아니라 필수다. 상태색은 절대 범주 시리즈로 쓰지 않는다. `Home.jsx:137`의 `남음 → "primary"`(사용자 Accent)를 `"brand"`로 바꾼다.

**빈 데이터 규칙 (지시 0-2·7, 0-10)** — `ChartEmpty`의 점선 상자를 폐기하고 3단계로: ⓐ Loading → **차트 모양** 스켈레톤(같은 높이, 점선 상자 아님) ⓑ 진짜 데이터 없음 → **차트를 통째로 접고** Canvas 위 `caption` 한 줄 ⓒ **고칠 수 있는 원인**(Notion 미연결 등) → Clovi 포함 전체 `EmptyState` + 다음 Action, 차트는 그리지 않음 ⓓ 로드 실패 → `ErrorState` + 재시도. **`MetricStrip`도 모든 칸이 `-`면 렌더하지 않고 원인을 렌더한다.**

### Icon System (지시 79)

**판정: `@mui/icons-material` `*Outlined` 유지 + 광학 정규화 계층.** 근거:
1. **증상의 원인이 stroke가 아니다 — 버그다.** `AppShell.jsx:437`이 MUI `SvgIcon`에 `size={18} strokeWidth={1.8}`을 넘기는데 `SvgIcon`에는 `size` prop이 없고(기본 `fontSize:'medium'` = **24px**) 모르는 prop은 `<svg>`로 흘려보내며, fill 기반 글리프라 `strokeWidth`는 무효다. 결과: **자식 아이콘 24px, 부모 그룹 아이콘 20px** — 자식이 부모보다 크다. Lucide 시절 잔재.
2. Barrel import 금지 static check가 존재하는 이유가 정확히 두 번째 아이콘 경로 비용이다. Nav 40여 글리프에 stroke 세트를 다시 넣으면 20px rail에서 아무도 분간 못 할 stroke를 위해 **비-nav 27파일 51글리프는 MUI로 남아** 한 화면 안에서 두 계열이 다시 만난다.
3. 지시 79의 실제 요구는 **더 가벼운 광학 무게**이고, 이 크기에서 광학 무게는 크기·잉크색·fill이 지배한다.

`ICON = { nav:20, inline:18, action:20, hero:24 }` 신설, `<NavIcon>` 래퍼가 `rem`으로 렌더(4K 레버 적용). **MUI 아이콘에 `size=`/`strokeWidth=` 사용 금지 static check 추가**(무효인데 이미 한 번 구현을 오도했다). 그룹 20 = 자식 20, 자식이 부모보다 크지 않게. `opacity: active?1:.82` 삭제(이미 muted인 글리프를 더 흐리면 가벼워지는 게 아니라 탁해진다). `AddRounded` 같은 **채워진 실루엣 글리프를 outlined로 교체**.

**라벨 시작선 계약**: `padding-inline-start 12` + 글리프 박스 `20` + gap `10` → **라벨 시작선 42px**, 그룹 헤더와 자식 항목이 **같은 42px**. 깊이는 그룹의 접힘 상태로 표현하고 들여쓰기로 중복 표현하지 않는다.
**자식 아이콘 규칙**: **그룹이 아이콘을 가지면 그 자식들은 아이콘을 갖지 않는다. 그룹 없는 최상위 항목은 아이콘을 갖는다.** → 관리자 rail은 글리프 **5개**(랜드마크 그룹당 1개) + 한 줄에 정렬된 35개 라벨. 사용자 rail은 flat 항목들이 글리프 유지. 규칙 하나, 결과 둘, 언어 하나.
**Active 아이콘 규칙**: 선택 시 아이콘의 **모양·variant·fill·크기·opacity 무엇도 바뀌지 않는다.** 라벨 색을 상속해 색만 바뀐다. outlined→filled 교체는 세 번째 신호이고 글리프 열을 깜빡이게 만든다.

### Clovi 계약 (지시 71)

**"보이는 캐릭터 크기"의 검사 가능한 정의**: 알파 ≥128 픽셀의 bounding box, 단 opaque 픽셀이 반대 차원의 0.5% 미만인 행/열은 버린다(부유 픽셀 제거). 저장소가 이미 같은 개념을 쓴다 — `app/static/brand/login/mascot-lock.json`의 `canonicalVisibleBounds:[44,70,985,935]`. 이걸 전 포즈로 확장한다.
부유 픽셀 제거는 필수다: `clovi-talking.png`는 저알파 픽셀이 캔버스 가장자리에 흩어져 있어 단순 `getbbox()`가 `1024×1024`, `hfrac=1.000`을 준다.

**실측 (Pillow, alpha≥128, 0.5% 제거, 전부 1024×1024)**

| Asset | `hfrac` | Asset | `hfrac` |
|---|---|---|---|
| `clovi-avatar` | **0.840** | `clovi-love` | 0.808 |
| `clovi-idle-blink` | 0.850 | `clovi-talking` | 0.817 |
| `clovi-idle` | **0.798** | `clovi-happy` | 0.793 |
| `clovi-think` | **0.772** | `clovi-canonical-hero` | 0.784 |
| `clovi-sleep` | 0.745 | `clovi-error` | 0.727 |
| `clovi-wave` | 0.715 | `clovi-button` | 0.666 |

**결과**: 40px 보이는 캐릭터를 만들려면 박스가 `40/hfrac` ≈ **48~52px**여야 한다. 현재 모든 호출부가 **박스**를 지정하므로 Clovi는 의도보다 15~25% 작게 나온다. 이것이 지시 71이 지적한 정확한 메커니즘이다.

| Context | Asset | 보이는 크기 | 박스 | 처리 |
|---|---|---|---|---|
| Top bar AI 진입 버튼 | **`clovi-avatar`** | 40px | 48 | 히트영역 ≥48. **흰 판 제거**(Shell이 인디고라 흰 몸체가 그대로 뜬다), ring `brand.violet` 36% |
| Sidebar 도우미 카드 | `clovi-idle`/`clovi-think` | 76px | 95 | `brandTint` 카드 + `3px brand.core` edge |
| AI Drawer 헤더 | `clovi-avatar` | 40px | 48 | 제목과 인라인 |
| AI Drawer Welcome / Assistant Home | `clovi-wave`(첫 진입)/`clovi-idle` | **144px** | 201 / 180 | `gradient.hero` 헤더 밴드 위 중앙 |
| 생각중 / 응답중 | `clovi-think`/`clovi-talking` | 40px | 52 / 49 | 스트리밍 줄 왼쪽 인라인 |
| Page-level Empty | `ART[...]` 또는 `clovi-sleep` | **132px** | ~177 | 텍스트 블록 왼쪽, `align-items:flex-start` |
| Inline Empty (compact) | — | 84px | ~112 | 현재는 art를 아예 제거 — 84px로 유지하도록 변경 |
| Error | `clovi-error` | 112px | 154 | Clovi에 빨간 tint 적용 금지 |
| Success | `clovi-happy` | 112px | 141 | toast/modal 성공 전용 |
| Login/Onboarding Hero | `clovi-canonical-hero` | 220~420 유동 | 280~536 | **손대지 않는다.** `mascot-lock.json`이 재크롭·재스케일 금지 |
| Game 축하 | `clovi-love` | 96px | 119 | |

**전역 규칙**: `object-fit: contain`, 머리·귀·몸체 **절대 자르지 않는다** — 투명 여백 때문에 작아 보이면 해법은 **더 큰 박스**지 크롭이 아니다(위 표가 이미 그 산수를 해 놓았다). Light 판 위에서는 판 대신 **접지 그림자**(`0 8px 20px rgba(22,26,44,.10)`), Dark Canvas·인디고 Shell 위에서는 판 없이 ≥100px일 때 `brandTint` 원반 40%. 현재 `MascotMini`의 무조건 `rgba(255,255,255,.95)` 판(`Mascot.jsx:214`)을 표면 조건부로 바꾼다. Halo가 하드코딩한 `rgba(83,108,214,.26)`(구 Accent)를 `brand.violet` 26%로 — Brand에서 절대 표류하지 않고 사용자 Accent를 절대 따르지 않게.
**발견된 버그**: `Mascot.jsx:243` 주석이 `clovi-idle.png`를 "이미 웃는 얼굴"이라 하지만 **실제로는 눈을 감은 졸린 얼굴**이다. 사용자가 우상단에 원한 웃는 얼굴은 `clovi-avatar.png`다. **상단바가 자는 로봇을 보여 주고 있었다.**
**Clovi 금지 구역**: 데이터 표, 설정 화면, 상세 본문, Page Header 장식. `PageHeader.spot`은 no-op 상태로 두지 말고 **죽은 prop과 13개 호출부를 삭제**한다.
**자동 검사**: `mascot-lock.json`을 `app/static/brand/mascot/mascot-bounds.json`으로 확장(`{file, sha256, size, visibleBounds, hfrac, wfrac}`) → ⓐ Python 회귀 테스트가 PNG에서 재계산해 lock과 대조(자산 재출력 시 여백 변화 감지) ⓑ vitest가 모든 호출부에 대해 `boxPx × hfrac`가 지시 71 밴드 안인지 단언.

### Gradient 정책 (지시 0-1)

**제품에 Gradient는 정확히 넷만 존재하고 전부 Theme 토큰이다. `frontend/src/screens/**`·`app/**`의 raw `linear-gradient(`/`radial-gradient(` 리터럴은 static check 실패다.**

| Token | 위치 | 장식이 아닌 이유 |
|---|---|---|
| `gradient.shell` | Sidebar `background-image` | rail은 하나의 객체다. 아래로 어두워지면서 하단(보조 항목·Clovi 카드)이 상단 주요 항목과 경쟁하지 않는다 |
| `gradient.ai` | Top bar 우상단 앵커 | Chrome에서 **보라가 나타나는 유일한 자리**. AI가 사는 곳을 표시한다. Clovi가 그 안에 앉는다 |
| `gradient.hero` | 로그인 패널·온보딩·AI Drawer 헤더 밴드 | **현재 `app/static/css/login.css:67` 값 그대로.** 생성 토큰으로 승격하는 것이 Jinja 로그인과 SPA가 하나의 제품임을 증명하는 방법 |
| `gradient.mark` | `BrandLogo.jsx` 내부 | 이미 존재 — 로고 자체 |

**금지**: 버튼(기존 "기본 버튼은 그라디언트가 아니라 단색" 단언 유지)·카드·판·배지·칩·표 행·차트 채움(영역 채움은 14% alpha 단색)·페이지 배경·Empty State·모달·툴팁·아바타. 따라서 `login.css:342`의 버튼 그라디언트는 **단색 `primary`** 로 바꾼다 — 로그인 버튼과 SPA 버튼이 같은 컴포넌트가 된다.

### Theme 마이그레이션에서 깨지는 것과 처리법

| 대상 | 처리 |
|---|---|
| `node scripts/generate_design_tokens.mjs --check` (static_checks.sh) | `theme.js`를 고치면 **반드시 같은 커밋에서 생성기를 재실행**한다. 우회할 방법도 이유도 없다 — 이 Gate가 두 `tokens.css`의 재분기를 막는다 |
| `theme-contract.test.js` — `사이드바가 캔버스 계열이다`(`contrast < 2`) | **교체.** 폐기된 D-141 Thesis의 *방향* 단언이지 접근성 단언이 아니다. → Light `contrast(sidebar.bg, canvas) ≥ 4.5` ("Chrome은 자기 Brand 재료다") **+ 신규** `blue−red ≥ 24` ("Chrome이 Brand 색상을 나른다") |
| `theme-contract.test.js` — 나머지 | **전부 그대로 통과**(실측 확인): 사이드바 단색·FONT_SIZE 7역할·RADIUS 3단언·Button 28~36·Chip radius·버튼 단색·`body1 === FONT_SIZE.body`(리터럴 14가 아니라 토큰 비교)·타이포/모션/tabular |
| `theme-contract.test.js` — 확장 | `brandTint` 면 추가 · **Gradient 모든 stop 대비**(오늘은 flat만 검사 — 예전 Gradient Chrome이 미측정으로 배포된 경로) · Hover/Selected Wash 합성 대비 · **AI Wash 룰**(`onShellMuted` 금지를 숫자 근거로 단언) · `focusRingOnBrand ≥3` · Brand 잉크 ≥4.5 · `CHART_SERIES ≥3.0` · **지시를 테스트로**: `chrome.shell`·`sidebar.activeRail`·`brand.purple`·`brand.wordmark`·`chart[0]`이 Accent를 바꿔도 동일한지 → **사용자 Accent가 Brand Identity를 지울 수 없음** |
| `tokens-generated.test.js` 4개 chrome 리터럴 금지 | **색을 Theme에 두면 전부 그대로 통과** — AI Wash는 `palette.chrome.aiWash`, Hover/Selected는 `palette.sidebar.hover/.selected`, `bgcolor:"sidebar.bg"` 줄 유지 + `backgroundImage` 추가, `sidebar.activeRail` 이름 보존. (누가 인라인하면 테스트가 정확히 실패한다.) **추가**: `--gradient-hero`가 두 생성 파일에 **바이트 동일**하게 존재 — 로그인/SPA 재분기 가드 |
| `density-contract.test.jsx` | 관계만 단언 → 4개 값 변경 **통과** |
| `BrandLogo.jsx` | `accent = palette.brand.wordmark` (기존 `primary.main`). **테스트 추가: Accent를 바꿔도 워드마크 색이 변하지 않는다** |
| 신규 static check 3종 | ⓐ MUI 아이콘에 `size=`/`strokeWidth=` 금지 ⓑ screens/app에 raw gradient 리터럴 금지 ⓒ **`palette.brand`는 `theme.js` 밖에 consumer가 1개 이상 있어야 한다** — 이번 실패(consumer 0건)의 재발을 문자 그대로 막는 가드 |

---

---

## Page Archetype 계약 (지시 66·81·82·63)

모든 Archetype 공통: **바깥 폭은 Shell이 소유한다**(`CONTENT_MAX_WIDTH`). Archetype은 그 안의 Content Grid만 선언하고 자기 max-width를 정하지 않는다.
**넓은 화면 규칙(한 번만 선언)**: **≥2560에서 어떤 Archetype도 텍스트 측정폭이나 요약 칸을 넓히지 않는다. 남는 폭은 ① 추가 Rail ② 더 많은 행 ③ 여백 — 이 순서로 쓴다.**

| # | Archetype | 구조 | Search/Filter | 빈 데이터 | 넓은 화면 | 대표 Route |
|---|---|---|---|---|---|---|
| B1 | Dashboard/Home | `Signal`(조치 가능한 상태만, ≤1줄) → `Focus`(가장 중요한 목록 하나, ~55%) → `Context rail` → `Depth`(추이, fold 아래) | **없음.** Filter Bar가 있으면 그건 목록 화면이다 | 주 데이터원이 죽어도 **독립 구획은 정상 렌더**. 한 의존성 때문에 페이지를 비우지 않는다 | ≥1920 rail 2개, ≥2560 rail 3개. Focus 열은 900px 초과 금지 | `/me`, `/dashboard` |
| B2 | List + DataGrid | `PageHeader(+?)` → `Lead summary`(**진단적일 때만**) → `Toolbar row`(검색+보기+정렬) → `Filter row` → `Table` → `Pager(하단만)` | `ToolbarRow`=어떻게 볼지 / `FilterBarGrid`=무엇을 볼지. Filter 3줄째는 "필터 더보기"로 | 필터 없이 0행 → `PageHeader+EmptyState+주요 Action`만, **Filter·Table shell·Pager 언마운트**. 필터로 0행 → Filter 유지 + "필터 지우기" | 행이 늘어난다. Column은 C3으로 재분배 | `/projects`, `/my-tickets`, `/board`, `/team-docs`, 관리자 DataScreen 16종 |
| B3 | **Reading page** | 한 열. `Title block` → `Body` → `Reactions` → `Comments`. **사이에 Card 경계 없음** | 없음 | 댓글 0이면 Composer 한 줄로 축소 | 열 900~1200px 고정·중앙. ≥2560에서 얇은 sticky meta rail 선택적, 제목 ≥5개면 TOC rail | `/board/:id`, `/team-docs/:id`, 공지 상세 |
| B4 | Work detail | `PageHeader(+actions)` → `Identity/metadata row`(의미 가중, 균등 금지) → 2열 `Body+discussion` \| `Context rail(활동 이력·관련·첨부)` | 없음 | 첨부·댓글은 인라인 한 줄로 강등 | **Rail이 넓어지고 본문 측정폭은 그대로** | `/tickets/:id`, `/projects/:id`, `/users/:id` |
| B5 | Form | `PageHeader` → `Form 열(최대 640px)` → `Guidance rail` → sticky footer actions | Entity 필드는 검색형 Combobox | — | Form 열 고정, ≥1440에서 rail 등장. 입력을 늘리지 않는다 | `/new-ticket`, `FormModal` 본문, `/profile` |
| B6 | Workflow/Wizard | `Step rail`(의존성 표시) → `현재 단계` → `효과 미리보기` → `확인` | 없음. **PageHeader tab·Filter bar 금지** | — | 미리보기 pane이 넓어진다 | `/setup`, `/offboarding` |
| B7 | **Report / 회의 보드** | `Scope selector`(기간+부서, sticky) → `Verdict strip`(결론을 **말로**, 숫자 8개 아님) → 2-up `추이`\|`분포` → `비교 표` → `Backlog(기본 접힘, 가상화)` | Scope만 상단 sticky | **차트 언마운트**, verdict가 이유를 말함, backlog는 유지 | ≥2560에서 3-up. **회의 화면은 "투사기에 들어가는 것"을 최적화한다** | `/sprint`, `/my-stats`, `/dev-report`, `/ai-usage` |
| B8 | Operations console | `Health line`(한 줄, 카드 없음) → `Attention queue`(원인별 그룹, 펼침) → `전체 로그 표`(가상화) → detail drawer | **Filter Surface 아님, 평범한 Toolbar.** raw 내부 ID는 "고급" 뒤로 | "지금 확인할 것이 없습니다" + 마지막 확인 시각. 표 껍데기·Pager 없음 | ≥1920에서 Attention queue가 좌측 rail로 | `/jobs`, `/diagnostics`, `/mail`, `/backup`, `/integrity`, `/schedules`, `/runners` |
| B9 | **Chat** | `대화 목록(280~320)` \| `대화(참여자·Context 헤더, 메시지, Composer)` \| `Context rail(≥1600)` | 목록 자체 검색만 | 대화 미선택 → 목적 있는 시작 상태, **Composer 숨김**(대상 없는 입력창은 거짓말). 메시지 0 → 방 목적·참여자 + Composer 포커스 | **늘어나지 않는다.** 메시지 측정폭 최대 820px, 남는 폭은 rail과 여백 | `/chat`, `/chat-rooms`, `/games/:id` |
| B10 | Settings | `PageHeader+tabs` → `설정 목록`(라벨/현재값/출처/최근변경/Action을 **행+괘선**으로, 카드 아님) → `관련 Action`(시각적으로 분리) | **모든 탭을 가로지르는 검색 하나**, 일치 행으로 점프 | — | ≥1600 2열: 목록 \| 최근 변경+영향 범위 | `/settings`, `/feature-flags`, `/announcements`, `/my-display` |
| B11 | Admin console / Split view | `PageHeader` → 2~3 **전체 높이** pane. 좌=navigator(자체 검색), 중앙=선택 상세(**`PageHeader size="section"`** — 기존 메커니즘 존재), 우=관련 컬렉션 | navigator에만. **상세 pane은 자체 Filter bar·SavedViews 금지** | 미선택 → pane 크기에 맞는 선택 안내(900px 공백에 중앙 일러스트 금지) | ≥1920에서 3번째 pane | `/organizations`, `/users`(≥1600), `/rbac` |
| B12 | Empty-focused | 별도 Route 타입이 아니라 **모든 Archetype이 구현해야 하는 렌더 모드** | — | C1 절차 | — | — |

## Cross-cutting 계약

### C1 Empty State 정책 (지시 15·18·0-10) — **구획 단위로** 판정한다

| 질문 | 결과 |
|---|---|
| 이 구획이 없는 데이터를 보여주려고만 존재하나 (chart·table·pager·KPI strip) | **언마운트** |
| 사용자가 데이터를 *얻게* 해 주나 (생성 버튼·필터·scope) | 유지하되 Filter는 한 줄로 강등 |
| **다른 소스**의 데이터인가 (Home의 최근 문서, Sprint의 계획 backlog) | **그대로 유지** |
| 필터 때문에 비었나 | Filter 유지 + 간결 Empty + "필터 지우기" |
| **의존성 고장** 때문인가 (Notion 미연결, 동기화 미실행) | Empty가 아니라 **Blocked**: 상단 안내 하나, 독립 구획은 전부 정상 렌더 |

빈 페이지도 반드시 보여줄 것: 페이지 정체성 · 주요 생성/다음 Action · 비어 있는 이유 한 문장 · 독립 Context.
절대 보여주지 말 것: 빈 표 헤더 · `1/1, 총 0건` Pager · 차트 축 · `-` 뿐인 KPI Strip · SavedViews bar · 본문의 4단락 온보딩 설명.

**변경 대상**: `kit.jsx::EmptyState`(`layout="page"|"region"|"inline"` 추가 — page는 남은 높이에 중앙 정렬) · `kit.jsx::MetricStrip`(전 항목이 `-`면 `null`) · `kit.jsx::DataTable`(0행 & 비로딩이면 아무것도 렌더하지 않고 호출부 Empty에 공간을 양보 — 지금은 Empty 메시지가 **두 개** 나온다) · `ui/Pager.jsx`(`total===0`이면 `null`) · **`DataScreen.jsx`(최고 레버리지 — Filter bar·SavedViews·Table shell·Pager 2개를 `hasRows || hasActiveFilter`로 게이트)** · `charts/base.jsx::ChartEmpty`.

### C2 Search/Filter/Sort 그룹핑·정렬 (지시 17·76·80)

**Filter Surface가 정당한가** — 25행 이상 가능 & 직교 필터 2축 이상 → 전체 `FilterBarGrid` / 25행 이상 & 1축 → Toolbar만 / **25행 미만 유한집합**(feature flags 11, policies 2, integrations 4, RBAC 13, org 3) → **검색만 있는 Toolbar, Dropdown·SavedViews 없음** / 0행 & 필터 없음 → 아무것도 없음.

> **R-88 — 이 숫자를 절대 규칙으로 기계 적용하지 않는다.** `25행`은 출발점이지 UX 법이 아니다. **데이터 규모 · 사용 빈도 · 찾기 난이도 · Filter 축의 수 · 업무 목적**을 함께 판단한다. 행이 적어도 업무상 중요한 Filter는 유지할 수 있고(예: 소수지만 매번 쓰는 부서 축), 행이 많아도 가치 없는 Filter는 만들지 않는다. 각 화면의 판단 근거를 `ROUTE_COVERAGE.json`의 해당 Surface에 한 줄로 남긴다 — 그래야 다음 사람이 숫자를 다시 기계 적용하지 않는다.

**R-88 — Filter UI가 실제 데이터를 견디는가** (폭 계약은 위, 여기는 값 자체)

| 항목 | 규칙 |
|---|---|
| 폭 배분 | Filter를 **균등 폭으로 기계 배치하지 않는다.** 프로젝트처럼 값이 길고 주요 탐색 조건인 항목은 충분한 폭 + 검색형 Combobox |
| 선택된 값 식별성 | **어떤 값을 골랐는지 알 수 없을 정도로 잘리면 실패다.** Ellipsis는 쓸 수 있으나 Hover/Focus/Dropdown Open 중 하나로 전체 값을 확인할 수 있어야 한다 |
| Dropdown 목록 | 비슷하게 긴 프로젝트명끼리 **서로 구분 가능**해야 한다 — 앞부분이 같으면 뒤를 자르지 말고, 필요하면 2줄 또는 보조 식별자(부서·기간)를 함께 보인다 |
| `필터 지우기`·`초기화` | **Input/Select와 같은 Grid Cell처럼 보이지 않게** 한다(`/policies`의 250px 테두리 상자가 지우려는 필터보다 넓은 게 현재 상태) |
| 결과 건수 | Filter Box의 남는 자리에 임의 배치하지 않는다. **"이 조건에 대한 결과"라는 관계**가 보이도록 Filter 영역과 목록 사이의 결과 줄에 둔다 |
| 0건의 두 얼굴 | **데이터 자체가 없는 상태와 Filter 때문에 0건인 상태를 구분**한다. 후자는 지금 걸린 조건을 인지시키고 **그 자리에서 초기화**할 수 있어야 한다. 티켓은 `TicketFilterBar.jsx::TicketEmptyState`가 이미 이 분기를 갖고 있다 — **이 패턴을 공통화해 전체 목록 화면에 적용한다**(문서 목록도 이미 3갈래를 갖는다) |

**그룹 순서 고정**: ① Toolbar — 자유 검색(늘어남) … 오른쪽 끝 `ToolbarEnd`에 정렬·보기·밀도 ② Filter — scope(부서/프로젝트) → entity(담당자/작성자) → 분류(종류/카테고리/태그) → 상태 → 기간 ③ 필요할 때만 — boolean toggle을 **Chip 그룹**으로(현재 `/team-docs`의 `즐겨찾기만` 단독 3번째 줄이 위반) ④ `필터 지우기`는 **2번 줄 흐름 끝의 텍스트 버튼**, Grid 칸이 아니다(`/policies`에서 지우는 대상 필터보다 넓은 250px 상자다).

**높이/베이스라인**: 1~2번 줄 모든 컨트롤 `size="small"`(32) + `InputLabelProps={{shrink:true}}`. **한 줄에 높이는 하나, 라벨은 항상 바깥/위, 절대 안쪽 금지.** 현재 `/team-docs` 1번 줄은 라벨 없는 40px 검색 + 라벨 있는 정렬 select + 32px 토글 2개 = 한 줄에 베이스라인 3종.
**Wrapping**: `FILTER_GRID_SX`의 트랙 상한(16rem/18rem)과 `width:fit-content`는 **유지**. 추가 규칙 — `grid-auto-flow: row dense` 금지(의미 순서를 뒤집는다), **앞줄에 여유 트랙이 있는데 한 항목만 있는 줄을 만들지 않는다.**

**검색형 Combobox로 바꿔야 하는 Entity Selector** (현재 `type:"select"` 80+곳 중 Autocomplete는 `MyTickets.jsx` 1곳):

| Route | 필드 | 옵션 소스(이미 존재) |
|---|---|---|
| `/projects` | 부서 | `/api/projects` → `departments.options` |
| `/team-docs` | 프로젝트·부서·기술 태그 | `/api/team-docs/projects`, `/filters` |
| `/team-tickets`·`/unassigned`·`/my-tickets` | 담당자·프로젝트 | `/api/tickets/assignees`, `/projects` |
| `/sprint` | 담당자·프로젝트·부서 | `/api/sprint/summary` → `developers`, `department.options` |
| `/new-ticket` + 티켓 편집 | 프로젝트·담당자 | 위와 동일 |
| `/board`·`/ideas` | 작성자 | `/api/team-chat/directory` |
| `/chat-rooms` 새 그룹·멤버 추가 | 참여자 | `/api/team-chat/directory` (**이미 있는데 UI가 안 쓴다**) |
| `/users` | 부서·직책·조직 | `/api/admin/departments`, `/job-titles` |
| `/organizations` 상세 | 상위 부서·소속 사용자 | `/api/admin/departments`, `/users` |
| `/notion-mapping` | 사용자 ID (**현재 raw 텍스트 박스**) | `/api/admin/users` |
| `/documents` | 워크플로·템플릿 | `config.refLists` (이미 fetch, 평범한 select로 렌더) |
| `/approvals`·`/audit` | 대상 사용자·actor | `/api/admin/users` |
| `/jobs` | 스케줄/실행/문서 ID (**raw 텍스트 3개**) | `/api/admin/schedules`, `/documents` |

**변경 대상**: `ui/filters.jsx`(`EntityCombobox` 추가, `FilterSelect`는 닫힌 열거형 전용) · `ui/FilterBar.jsx`(`FilterGroup`·`ToggleChipGroup`) · `kit.jsx::FormField`(`type:"entity"`) · `DataScreen.jsx` filter 렌더 루프 · `TicketFilterBar.jsx`.

### C3 Table/Metadata 폭·정렬 계약 (지시 18·19·74·75·77)

`DataTable`은 이미 `width`·`minWidth`·`identifier`·`align`·`nowrap`·`hideNarrow`를 지원한다. 문제는 registry 컬럼 216개 중 `identifier` 32곳, 전체 `align` 39곳뿐이라는 것 — 그래서 `/notion-mapping`이 **빈 오류 컬럼에 470px**를 주면서 Notion 이메일을 자르고, `/projects`가 22행 내내 동일한 `상태` 한 단어에 `이름`과 같은 무게를 준다.

**컬럼별 magic number를 의미 `type`으로 교체한다:**

| `type` | 폭 | 정렬 | 숫자 | 넘침 |
|---|---|---|---|---|
| `title` | `minmax(16rem, 3fr)` — 표당 **최대 1개** | start | — | 2줄 wrap 후 ellipsis + `title` |
| `name`(사람/프로젝트/조직) | `minmax(9rem, 1.5fr)` | start | — | 1줄 ellipsis + tooltip |
| `identifier`(email/code/uuid/tid) | `minmax(12.5rem, 1fr)` | start | tabular | `overflow-wrap:anywhere`, 한글 음절 중간 금지 |
| `text`(설명/오류) | `minmax(12rem, 2fr)`, **전 행이 비면 0으로 수축** | start | — | 1줄 + 행 열기로 확장 |
| `status` | `max-content`, min 5rem | start(배지가 시각 앵커) | — | wrap 금지 |
| `count`/`number` | `max-content`, min 4rem | **end** | tabular | wrap 금지 |
| `percent`/`score` | `max-content`, min 5rem | **end** | tabular | wrap 금지 |
| `date`/`datetime` | `max-content`, min 8.5rem | 비교 대상이면 **end**, 라벨이면 start | tabular | wrap 금지 |
| `enum`(짧은 닫힌 집합) | `max-content` | start | — | wrap 금지 |
| `actions` | `max-content` | **end** | — | wrap 금지 |

**Header/Cell 정렬(지시 19)**: 헤더는 컬럼의 align을 상속한다. 규칙 하나, 예외 없음. (현재 `/users`는 최근 로그인 값만 우정렬하고 헤더는 좌정렬, `/rbac`은 셀을 중앙 정렬하고 역할 헤더 5개는 좌정렬.)
**Collapse 규칙 (지시 18 + R-91로 교정)** — 초안은 "현재 렌더된 행이 전부 같으면 컬럼을 뺀다"였다. **그건 틀렸다.** Pagination·Server-side Search/Filter를 쓰는 화면에서 현재 Page의 값이 같다고 전체 Result Set이 같은 건 아니고, Page를 넘기거나 Filter를 바꿀 때마다 **컬럼이 생겼다 사라지는 불안정한 Layout**이 된다. 교정된 규칙:

| 상황 | 동작 |
|---|---|
| 값이 **구조적으로** 동일함이 확실 — ⓐ 화면 자체가 특정 상태 전용 View이거나 ⓑ 사용자가 그 축의 Filter를 **명시적으로 적용**했거나 ⓒ Backend Query Contract상 그 Scope에서 값이 불변 | **컬럼 제거 + caption에 한 번 표기** (ⓑ는 Filter를 풀면 컬럼이 돌아온다 — 사용자가 유발한 변화라 예측 가능하다) |
| 현재 Page의 값이 **우연히** 같다 | **제거하지 않는다.** 폭만 `max-content`로 줄이고 `hideNarrow` 후보로 표시 |
| 전 행이 비어 있는데 서버가 전체를 주는 화면(클라이언트 페이징 없음) | 제거 가능 |
| 전 행이 비어 있는데 **서버 페이징** | 제거하지 않고 `max-content`로 축소만 |

판정 입력은 `DataTable`이 새로 받는 `resultScope: { serverPaged: bool, activeFilters: string[], fixedColumns: string[] }`다 — 호출부가 자기 Query 계약을 알려 주고, 표는 그것 없이는 제거하지 않는다. 이건 **공유 동작**이라 registry 28파일을 안 건드리고 216 컬럼에 적용된다. 단위 테스트로 "서버 페이징 + 우연한 동일 값 → 컬럼 유지"를 고정한다.
**Metadata(`MetaBar`, 지시 75)**: `flex:1 1 9rem` 균등을 같은 `type` 체계로 교체. `/tickets/:id`에서 프로젝트는 `2fr`, 상태·우선순위·마감은 `max-content`.
**MetricStrip(지시 77)**: 현재 코드는 균등 분할을 실측 근거로 방어한다 — *죽은 공간 회피*로는 옳았지만 *위계*로는 틀렸다. 새 계약: `primary` 판독값 하나가 `1.6fr` + 큰 타입, 나머지는 `max-content`+최소폭, **strip은 좌측 정렬로 packing하고 늘어나지 않는다**(Card를 벗겨 구획 안에 놓이므로 남는 폭이 비어도 괜찮다). **값이 0이거나 정보 가치가 낮은 Metric이 계속 큰 공간을 차지하지 않게 한다.**
**변경 대상**: `kit.jsx`(DataTable 컬럼 resolver·MetaBar·MetricStrip) · `ui/cells.jsx`(`NUMERIC`을 나르는 Number/Percent/Status Cell) · `screens/registry/*.js` 7파일 **216 컬럼에 `type:` 부여(기계적)** · `Projects/Users/Board/MyTickets/Sprint/MyApprovals/Activity.jsx` · **원시 `<Table>` 2곳**(`DevReport.jsx`, `MyTickets.jsx`)을 DataTable로 이관.

### C4 Page Header + Page Help `?` (지시 3·44)

`?`는 `<h1>` 옆에 둔다 — `kit.jsx:1768`이 이미 그렇게 한다. 유지.
**본문에서 Help로 옮길 것**: 제목과 첫 컨트롤 사이의 모든 설명 문단(`/projects`, `/team-docs`, `/ideas`, `/games`, `/board`, `/sprint`, `/organizations`), 그리고 가장 중요한 것 — `DataScreen`이 본문에 인라인 렌더하는 `emptySituation`/`emptyPrerequisite`/`emptySteps`/`emptyExpected` 블록(`registry/automation.js::documents`가 `admin_documents.png`의 200단어 에세이를 만든다). **`emptySteps`+`emptyPrerequisite`+`emptyExpected`는 `?` 패널로, Empty State에는 `emptyTitle`·한 문장 `emptySituation`·주요 Action·`emptyRelatedLink`만 남는다.**
**Help에 절대 넣지 말 것**: 지금 조치해야 하는 것(그건 Notice, C5) · 할 수 있는 일이 바뀌는 역할 의존 정보(그건 Permission 상태).
펼친 Help 패널은 전폭 `Callout` 상자를 그만두고 좌측 괘선이 있는 들여쓴 블록이 된다.
**PageHeader를 붙이면 안 되는 화면**(지시 66): `/chat`, `/chat-rooms`, `/games/:id`, `/login`, `/setup`, `OrgConsole` 우측 pane(`size="section"` 사용), 모든 TabShell 탭 본문.
**`?`가 필요한데 없는 화면**: `/settings`(탭 4개·정책 16개·도움말 0), `/jobs`, `/backup`, `/diagnostics`, `/sprint`, `/my-stats`, `/projects`.

### C5 Feedback/Alert 위계 (지시 20·35·67)

4단계, 그중 **상자는 둘뿐**: ① **Inline hint** — 컨트롤 아래 텍스트, 상자·아이콘 없음 ② **Section notice** — 해당 구획 안, 앞머리 괘선/아이콘 한 줄, **전폭 아님** ③ **Page warning** — 상단 테두리 블록, **반드시 Action을 포함** ④ **Critical/Blocking** — 해당 영역을 통째로 대체.
**절대 전폭 테두리 상자가 될 수 없는 것**: Action이 없는 것 · 정상 동작을 설명하는 것 · **UI 구현 한계를 설명하는 것**(`/documents`의 `'모드' 필터는 지금 보고 있는 페이지에만 적용됩니다` — 그건 사용자 문제가 아니라 고쳐야 할 서버 3줄이다) · 설명 산문(→ `?`).
**운영 vs 사용자 알림(지시 67)**: 운영 상태(동기화 실패·작업 실패·디스크·인증서 만료)는 `/dashboard`·`/diagnostics`·`admin-notifications`·관리자 `StatusNotices`. 사용자 알림(내게 배정된 티켓·대기 중 승인)은 `NotificationBell`+`/notifications`. **서로 넘나들지 않는다.** `StatusNotices.jsx`·`Banners.jsx`는 이미 옳고, **남은 위반은 `MirrorNotice.jsx` 하나다.**

### C6 일반 사용자 vs 운영 정보 경계 (지시 0-15·1·29·36)

**규칙**: 일반 사용자는 운영 사실을 (ⓐ) 눈앞의 데이터에 대한 믿음을 바꿀 때 **그리고** (ⓑ) *그가* 할 수 있는 조치가 있을 때만 본다. ⓐ만 있고 ⓑ가 없으면 배너가 아니라 **해당 숫자 옆 한 줄 주석**이 된다. 둘 다 없으면 그에게 보이지 않고 관리자 콘솔에 산다.

| # | 위치 | 위반 | 조치 |
|---|---|---|---|
| 1 | `MirrorNotice.jsx` + `TeamDocs.jsx:413` | 전폭 `주의 최근 동기화에 실패했습니다…` + **`지금 동기화` 버튼** | 비-operator에게 버튼 제거(자동 동기화가 정책이고 주기는 이미 관리자 설정). 배너는 결과 수 옆 인라인 주석으로 강등 — "마지막 갱신 8. 19. 07:42" |
| 2~5 | `Home.jsx:280`, `MyTickets.jsx:731,806`, `TeamTickets.jsx:151`, `MyStats.jsx:285` | 같은 배너가 Home·내 티켓·팀 티켓·내 업무량에도 | 동일. 팀 티켓 overflow의 수동 동기화는 `role==="user"`에게 제거 |
| 6 | `/team-docs` header overflow | `지금 동기화`가 기본 Action | operator+ 전용 |
| 7 | `/projects` 요약 | `계산이 끝난 20건만 셌습니다…`가 본문 산문 | 평균 진행률 숫자에 붙는 인라인 주석 |
| 8 | `/me` 내 업무 | raw `low_confidence` 문장 | health 판독값 위첨자 + `?` |
| 9 | `/documents` | `비활성화되어 있으면 생성이 409로 거절됩니다`, `#/settings에서 확인` | **HTTP 상태코드와 hash 경로는 사용자 문구에 절대 나오지 않는다** |
| 10 | `/feature-flags` | raw `snake_case` 키가 식별 컬럼, 설명에 `§23`·`app_settings 테이블`·`fail-closed` | 사람 라벨이 1차, 키는 `TechDetail`로 |
| 11 | `/jobs` | `requester가 없는 payload — 워커 또는 큐 손상`이 오류 컬럼 원문 | 사람 문장 + `TechDetail` |
| 12 | `/chat` | Runner job id가 대화 제목 | 서버에서 첫 사용자 메시지로 제목 유도 |

**지시 29 해소** — 확인 결과 **문서 잠금 기능은 존재하지 않는다**(`is_locked`/`lock_owner`/`locked_by` 컬럼·마이그레이션·UI 전무, 유일한 `is_locked`는 `app/users/router.py:131`의 계정 잠금). 존재하는 것은 **낙관적 동시성**이다 — `app/team_docs/router.py:402`가 `base_version`을 넘기고 `service.py:545`가 `body_version`을 계산해 오래된 쓰기는 409를 받는데, 프런트 대응은 `lib/api.js:14`의 **일반 토스트 한 줄**이고 사용자가 쓰던 내용은 누가 바꿨는지도 모른 채 버려진다.
→ **요구 29는 "잠금을 만들라"가 아니라 "이미 있는 동시성 제어의 UI 표현을 만들라"로 해소한다**: ⓐ 409에서 초안을 편집기에 유지하고 상대 편집자를 밝히며 "내 내용 복사 후 다시 열기" 제공 ⓑ 편집 중 `last_edited` 기반 "OO님이 방금 이 문서를 수정했습니다" 표시 ⓒ 실시간 Presence는 **새 기능**(테이블 필요)이므로 UI 리뉴얼에 몰래 끼워 넣지 않고 별도 범위로 둔다.

### C7 Search/Filter/Sort/Pagination **기능 정확성** 계약 (R-85·R-86·R-87)

C2가 "어떻게 보이는가"라면 C7은 **"결과가 맞는가"**다. 디자인 변경만으로 Search/Filter 개선을 완료 처리하지 않는다.

**검증 사슬 — 이 8단계가 전부 일치해야 통과다.** 어느 한 단계만 확인하고 넘어가지 않는다.
`UI 선택 상태 → Frontend State → URL Query / Route State → API Request Parameter → Backend Query → DB / 실제 Data Relation → API Response(+Total Count) → Rendering된 목록`

**대상 전수조사**: 특정 티켓 화면만 고치지 않는다. 같은 Search/Filter Component와 Query Pattern을 쓰는 **전체 Consumer**를 조사한다 — `TicketFilterBar` 소비처(`/my-tickets`·`/unassigned`·`/team-tickets`·`/projects/:id` 티켓 탭·`/sprint`), `DataScreen` 필터 루프(21 Route), `TeamDocs`·`Board`·`Ideas`·`Search`·`Activity`·`MyApprovals`, 관리자 전 목록.

| 검증 항목 | 방법 | 통과 기준 |
|---|---|---|
| **단독 조건** | 존재하는 축마다 하나씩 적용(프로젝트·상태·우선순위·난이도·기한·담당자·카테고리·검색어) | 결과 집합과 Total Count가 **Known Data**와 일치 |
| **복합 조건** | 축 2~4개 조합, 특히 프로젝트 × 상태, 프로젝트 × 담당자, 상태 × 기한 | 교집합이 정확. 한 축을 추가했을 때 결과가 늘어나면 실패 |
| **Relation 기반 축** | 프로젝트처럼 다른 Resource와 연결된 축은 **표시 문자열이 아니라 안정적 Identifier와 실제 Relation** 기준으로 동작하는지 | 티켓과 프로젝트가 실제로 연결돼 있는데 결과에서 빠지면 **Frontend에서 멈추지 말고** API Parameter → Backend Join/Relation → Permission Scope → Query Condition까지 추적해 Root Cause 수정 (R15의 `project_ids` 캐시 해석 경로가 1순위 용의자) |
| **Page 기본 Scope와의 결합** | `/unassigned`·`/my-tickets`·`/team-tickets`처럼 화면 자체의 Scope가 있는 경우 **기본 Scope 단독 / 사용자 Filter 단독 / 둘의 결합**을 분리 검증 | 세 결과의 포함관계가 논리적으로 성립 |
| **Pagination 결합** | Filter 변경 시 page 리셋 | **이전 Page에 남아 0건처럼 보이지 않는다.** 리셋 책임을 호출부가 아니라 공통 계층(`useQueryState`/`ticketQueryParams`)에 둔다 |
| **Race Condition** | Filter를 빠르게 연속 변경 | 오래된 응답이 최신 조건을 덮어쓰지 않는다 |
| **Cache / Query Key** | 다른 Filter로 전환 | 조건 전체가 Query Key에 포함돼 **같은 결과가 재사용되지 않는다** |
| **Refresh · Back/Forward** | 각 조건 상태에서 새로고침, 뒤로/앞으로 | **표시된 조건과 실제 Query 조건이 일치**한다 |
| **Sort** | 각 정렬 축 | 서버 페이징 목록에서 **클라이언트 정렬을 제공하지 않는다**(현재 `Projects.jsx:31`이 스스로 거부 중 — 서버 정렬을 구현해 해소) |

**Evidence는 별도로 남긴다** — `FUNCTIONAL_COVERAGE.json`의 `search_filter` Flow에 조건별 `{condition, expected_ids|expected_count, actual, source}` 형태로. W14와 최종 Completion Gate에 포함한다.

### C8 공통 Property Editing 계약 — Inline Edit (R-89·R-90)

**하나의 Model, 세 개의 표면**: Grid 셀 · Detail Header · Form. 같은 값을 서로 다른 Interaction으로 중복 구현하지 않는다.

**상태 기계** (전부 구현해야 완료):
`현재 값 → (권한 확인) → 변경 가능한 값 제시 → 선택 → Saving(중복 요청 차단) → 성공 | 실패 → 실패 시 Rollback → 필요 시 재조회로 실제 값 반영`

| 규칙 | 내용 |
|---|---|
| 대상 선별 | **Grid에서 빠르게 바꿀 가치가 있는 Property만.** 티켓은 상태·우선순위(+담당자는 검토). Inline Edit가 있다고 복합 티켓 수정 Workflow 전체를 Grid에 넣지 않는다 |
| 평상시 표현 | Grid 가독성을 해치지 않는다. **모든 Editable Value를 항상 Select Box로 노출하지 않는다.** Hover/Focus에서 변경 가능함이 드러나되 평상시엔 값 그대로 읽힌다 |
| 권한 | Frontend의 변경 가능 여부와 **Backend Authorization이 일치**해야 한다. 권한 없으면 편집 진입 자체가 없고, 이유를 알아야 하는 경우에만 이유를 보인다 |
| 저장 확인 | **Frontend State만 바꾸고 성공 처리하지 않는다.** Backend 저장을 확인하고, 서버가 파생값을 바꾸는 경우 재조회해 **실제 값 기준으로** UI를 갱신한다 |
| 실패 | 이전 값으로 안전 복구 + 사용자가 이해할 수 있는 사유. 낙관적 갱신을 쓰면 롤백 경로를 반드시 구현 |
| 정합성 | 변경 후 R-93의 화면 간 정합성(목록·상세·Home Count·Sprint 집계)이 함께 맞아야 한다 |

**연결**: Pattern은 **W6**(공통 Table/Grid 계층)에서 만들고, **W9**(티켓 Workflow)에서 배선하며, **W14**에서 실제 브라우저 클릭 → 저장 → 재조회 → 관련 화면까지 E2E로 검증한다. Detail 상단 Inline Edit(R-90)도 같은 Model을 쓴다.

### C9 Detail Metadata 정보 위계 계약 (R-90)

폭 배분(C3)은 **필요조건이지 충분조건이 아니다.** 상단 속성 영역을 "긴 흰 Box 안에 Label/Value를 동일 강도로 나열"하는 구조로 유지하지 않는다.

| 판단 | 규칙 |
|---|---|
| 위계 | **먼저 판단해야 하는 값**(티켓: 상태·프로젝트·담당자·우선순위·마감)과 **보조 Metadata**(티켓번호·난이도·예상 WD)를 구분한다. 동일한 시각적 강도로 기계 나열하지 않는다 |
| 표현 선택 | 모든 Property를 Card나 Badge로 만들지 않는다. **Compact Metadata Strip · Property Group · Definition Layout** 중 그 Page의 목적과 Workflow에 맞는 것을 고른다 |
| 넓은 화면 | 속성 사이 간격만 계속 늘어나 **시선 이동이 커지지 않게** 한다 — 남는 폭은 간격이 아니라 그룹 재배치나 보조 Context로 |
| 좁은 화면 | 중요한 값을 **잘라내지 않고** 자연스럽게 Wrap 또는 재배치 |
| 검증 | **긴 프로젝트명이 들어간 실제 데이터**로 FHD/QHD/4K × Zoom 100/125/150 확인 |
| Inline Edit | 자주 바뀌는 Property(상태·우선순위·담당자)는 Detail 상단에서도 Inline Edit가 업무 효율상 적절한지 판단하고, 적절하면 **C8의 같은 Model**을 쓴다 |
| 전수 | 티켓 한 화면만 고치지 않는다. 같은 Metadata Header / Detail Pattern을 쓰는 **전체 Consumer**(`Ticket.jsx`·`TeamDoc.jsx`·`Project.jsx`·`BoardPost.jsx`·`Users.jsx` drawer·`DataScreen` detail drawer)를 조사한다 |

---

## Page Purpose — Pilot 8종 (지시 84-4·0-9)

각 Page는 "왜 오는가 / 5초 안에 알 것 / 가장 중요한 Action / 지금 빠진 정보 / 중복 / 비었을 때 사라질 것 / 넓은 화면 사용법"을 답한 결과로 설계한다. **핵심은 "이미 API에 있는데 화면이 안 쓰는 정보"를 찾아낸 것이다.**

| Pilot | 지금 빠진 것 (그리고 **이미 있는** 데이터원) | 새 Backend 작업 |
|---|---|---|
| **Home `/me`** | 숫자만 보여주고 **항목을 버린다.** `/api/home/work-dashboard`가 `projects.troubled.items[]`(이름·코드·health·진행률·**`reasons[]`**)와 `milestones.overdue.items[]`, `completion_trend`를 이미 준다. `WorkSummary.jsx:77-110`은 `count` 두 개만 렌더. 승인 대기·미읽음도 `/api/home/today`의 `inbox`에 온다 | ⓐ `/api/home/today`에 `approvals:{todo_count}` ⓑ `recent`에 `changed_since` 커서 |
| **프로젝트 `/projects`** | **왜 위험한지**. `app/home/work.py::_trouble_reasons`가 `projects/health.py::trouble_reasons`로 이미 생성하고 `/api/projects/{id}/health/history`도 있는데 목록이 안 쓴다. `Health 59점`만 있고 무엇이 떨어뜨렸는지 없음. KPI Strip 2개(전체 22 = 진행 22), 22행 내내 동일한 `상태`·`부서 미지정` 컬럼 3개가 정보 0 | ⓐ `/api/projects` 행에 `reasons[]` (함수는 이미 있고 `_project_view`가 호출만 안 함, ~5줄) ⓑ **정렬 파라미터 부재** — 서버 페이지네이션 목록을 클라이언트 정렬하면 거짓말이라 파일이 스스로 거부 중. `sort=health\|progress\|due\|updated` 서버 구현 |
| **Sprint `/sprint`** | **비교**. `/api/sprint/summary`가 burndown·by_assignee·team·planned를 주지만 "지난주 대비"가 없다. 그리고 담당자 10명을 **큰 카드 10장 → 같은 10명 표 → 같은 10명 막대차트**로 세 번 쌓는다(1920에서 페이지 8828px) | `app/sprints/service.py`에 `compare=prev` — 이전 window의 `team` 집계 + 티켓 id 차집합(Scope 추가/제외). 같은 쿼리 경로에서 window만 shift. **제품 전체에서 지시 62 가치가 가장 큰 추가** — 주간 비교 없는 회의 화면은 회의 화면이 아니다 |
| **Chat `/chat-rooms`·`/chat`** | 참여자 목록·멤버·방 Context(어느 프로젝트/티켓)·미읽음 구분선·답장·방 내 검색. `/chat`은 제목이 raw job id이고 **AI 응답에 리터럴 `\n\n`이 렌더된다**(실제 버그). 제목을 breadcrumb·`<h1>`·pane 헤더 **3번** 표시 | ⓐ `/api/team-chat/rooms/{id}`가 이름 포함 멤버 목록 반환 ⓑ AI 대화 제목 서버 유도. `/api/team-chat/directory`는 **이미 있는데 UI가 안 쓴다** |
| **티켓 상세 `/tickets/:id`** | **활동 이력이 아예 없다.** 상태·담당자·마감 변경이 전부 `app/audit`에 기록되는데 화면에 없음. 관련 티켓·프로젝트 health·blocked 사유도 없음. 1920에서 우측 rail은 빈 드롭존 + 빈 댓글창 뒤 600px 공백 | `GET /api/tickets/{page_id}/history` — 감사 행의 사용자 가시 부분(상태/담당자/마감/본문 변경 + 행위자 이름)을 티켓 열람 권한자에게 스코프·검열해 제공. **이 페이지 최대 정보 공백** |
| **Reading `/board/:id`** | 구조적으로 빠진 건 없다 — **형태가 문제**다. 본문은 카드 안(x 280~1367), 댓글은 카드 **밖** → 읽기 흐름이 카드 경계로 두 동강. 이전/다음 글 없음 | 없음. 선택적으로 상세 응답에 `prev_id`/`next_id` |
| **관리자 조직/사용자** | 우측 pane이 트리 선택에 **상세로 반응하지 않고 자체 PageHeader·검색·SavedViews를 가진 1행짜리 DataScreen을 통째로 렌더**한다. 한 페이지에 PageHeader 2개, 같은 엔티티 검색창 2개, `/organizations`·`/departments`·`/org-tree` 3개 URL이 한 화면. 트리는 y≈490에서 끝나고 페이지는 1080 | **없음.** 필요한 엔드포인트가 전부 존재 — `/api/admin/users?department_id=` 포함. 전부 `OrgConsole.jsx` 재구성 |
| **관리자 Settings/Ops** | `/settings`: **누가 언제 바꿨는지**(감사 행은 있다), 탭 4개를 가로지르는 검색, 기본값과 다른 값 식별. 정책 탭이 16행 표 + 유지보수 모드(빨간 파괴 버튼) + 점검 공지를 한 스크롤에 쌓음. `/jobs`: 165행 중 실패 7건을 눈으로 찾아야 하고 Pager가 표 **위아래 둘 다** | ⓐ `/api/admin/settings` 행에 `updated_at`·`updated_by`(감사 행 join) ⓑ `/api/admin/jobs`에 `failure_summary` 또는 `group_by=error` |

## 관리자 IA 결정표 (지시 30·41·46·48·51)

**독립 Page 유지 (16)**: `/dashboard` · `/jobs` · `/diagnostics` · `/backup` · `/mail` · `/integrity` · `/users` · `/organizations` · `/rbac` · `/approvals` · `/audit` · `/settings` · `/setup` · `/offboarding` · `/schedules` · `/integrations` — 각각 고유 Resource + 고유 Workflow(또는 고유 위험 등급)를 갖는다.

**이미 올바르게 병합됨, 유지 (6)**: `/restore-drills`→`/backup` · `/approval-delegations`→`/approvals` · `/audit-anomalies`→`/audit` · `/policy-usage`·`/prompt-usage`→`/ai-usage` · `/scheduler-calendar`→`/schedules`.

**새로 병합 (9)**
| Route | → | 근거 |
|---|---|---|
| `/departments`, `/departments/:id`, `/org-tree` | `/organizations` split view의 pane/kind | 하나의 조직 트리에 URL 3개 |
| `/job-titles` | `/organizations` 3번째 pane | 직책은 조직 모델의 속성. `/organizations`가 진짜 split view가 되면 "탭 안의 탭" 반론이 사라진다 |
| `/templates`, `/policies` | **`/ai-authoring`** (프롬프트·정책·템플릿 탭) | 하나의 authoring Workflow의 세 재료, 형태·역할집합 동일 |
| `/runners`, `/workflows` | `/integrations` (연동·러너·워크플로 탭) | "우리가 부르는 외부 것" 레지스트리 3종. 실패 작업을 쫓는 operator가 셋을 다 지난다 — 지금은 사이드바 3클릭 + Filter Surface 3개 |
| `/feature-flags`, `/announcements` | `/settings` (기능·공지 탭) | 11행·3행짜리 설정 표. 같은 편집자·같은 대상·같은 저장 패턴 |
| `/ai-quotas` | `/ai-usage` (상한 탭) | 상한과 사용량은 "예산 안인가"라는 한 질문 |
| `/impersonation` | `/audit?tab=impersonation` + `/users/:id`의 시작 Action | 다른 곳에서 시작하는 것의 로그일 뿐 |

**병합하지 않는다 — RBAC 근거**: `/notion-mapping`(CONSOLE_READ)을 `/users`(CONSOLE_WRITE=admin+)에 합치면 권한이 깨진다. **독립 Page 유지.** Sidebar 숫자를 줄이려고 RBAC를 왜곡하는 것이 지시 51이 명시적으로 경고한 것이다.
**Sidebar에서만 제거**: `/dev-report` — Route는 유지하고 `/dashboard → 리포트`로 도달. 90일간 열람 0이면 그때 삭제 판단.
**최종 Sidebar: 6그룹 22항목** (현재 31). 탭을 부풀려 얻은 게 아니다 — 새 탭 Shell 2개(`/integrations` 3탭, `/ai-authoring` 3탭)는 각각 **하나의 Workflow와 하나의 역할집합을 공유하던 형제 Page 3개**를 대체하고, `/settings`는 11행·3행 설정표 둘을 흡수해 4→6탭이 된다. **어떤 Page도 6탭을 넘지 않고, 탭 Shell 안에 탭 Shell이 없다.**

**옛 주소 보존 — Redirect가 아니라 제자리 렌더.** `AdminRoutes.jsx`가 이미 쓰는 패턴이고 이유도 문서화돼 있다: `<Navigate>`는 hash query를 버려 저장된 뷰와 딥링크를 조용히 깨뜨린다. 병합된 옛 주소는 전부 해당 pane/탭이 선택된 채 제자리 렌더하고 query를 보존한다. `/system`·`/notion-console`·`/llm-console`·`/maintenance`는 구조상 query가 없으므로 기존 `<Navigate>` 유지.
**회귀 테스트 추가**(기존 `nav-features.test.js` 방식): `SCREEN_ROLES`에 등록된 적 있는 모든 경로가 일치하는 `<h1>`을 가진 화면으로 해석되고 404가 아니다. 병합 전 `sameRoles()` 역할집합 동등성 검사를 **반드시 통과**해야 한다.

## 지시서가 지목하지 않았지만 고쳐야 할 발견 (지시 61)

| # | Route | 문제 | 고칠 곳 |
|---|---|---|---|
| E1 | `/me`, `/my-tickets`, `/my-stats` | 동기화 실패 배너가 문서/티켓뿐 아니라 **Home에도** | `ui/MirrorNotice.jsx` |
| E2 | `/chat` | AI 응답에 **리터럴 `\n\n`이 그대로 렌더** | `screens/ChatBubbleText.jsx` |
| E3 | `/jobs`, `/notion-mapping`, `/documents` | Pager가 표 **위아래 둘 다**, 빈 페이지에서 `1/1, 총 0건` | `DataScreen.jsx::renderPager`, `ui/Pager.jsx` |
| E4 | `/jobs` | 165행 100/page 가상화 없음, 페이지 3932px, 모든 행이 동일 | `kit.jsx::DataTable` 윈도잉 |
| E5 | `/users` | 역할 컬럼이 배지 **2개**(관리자+전체 관리자)를 쌓아 전 행이 2배 높이. 역할과 Scope를 한 컬럼에 혼동 | `Users.jsx` + C3 |
| E6 | `/rbac` | `할 수 있는 일`이 `…중재(게시판, 문서, 휴지통, …`로 잘리는데 **툴팁도 없고 나머지를 볼 방법도 없다** — 읽을 수 없는 권한 표 | `kit.jsx::DataTable` (render 컬럼에도 넘침 공개 적용) |
| E7 | `/activity` | 68개 이벤트가 전부 같은 화살표 아이콘, 전부 `4시간 전, 내가 한 일`, 엔티티 그룹핑 없음, `열기`가 일부 행에만 이유 없이 | `Activity.jsx` + 공유 `Timeline` primitive(**없음, 만들어야 함**) |
| E8 | `/board/:id`, `/tickets/:id` | **파괴 Action(삭제)이 우상단에 밝은 빨강으로 `목록`과 같은 레벨**, 게시글 상세에서는 페이지 최우측 최대 요소 | `kit.jsx::PageHeader`에 `danger`/`overflow` 슬롯 (DataScreen의 `isRiskyHeader` 로직이 Page 레벨엔 없음) |
| E9 | 전 목록 화면 | 2·4·11·13행짜리 표에도 SavedViews + 링크복사 아이콘, 빈 페이지에도 | `ui/SavedViews.jsx` + `DataScreen.jsx` |
| E10 | `/team-docs/:id` | **17,076px 문서에 목차·sticky 헤더·읽기 진행 표시가 전무하고 우측 rail은 비어 있다** — 제품 최장 읽기 화면에 읽기 지원이 가장 적다 | `TeamDoc.jsx` → B3 |
| E11 | `/settings` | 값 하나 바꾸는 데 모달 하나씩, 기본값과 다른 값을 한눈에 볼 방법 없음(`적용 상태`가 2행만 `수정됨`), 탭 가로지르는 검색 없음 | `SettingsMain.jsx`, `adminKit.jsx` |
| E12 | `/policies`, `/integrations`, `/notion-mapping` | **전 행이 비어 있는 컬럼**(`용도`, `오류`)이 표 폭 25~35%를 먹고 식별자는 잘린다 | C3 Collapse 규칙 |
| E13 | `/documents` | `주의` 배너가 **프런트 구현 한계**를 설명(`'모드' 필터는 지금 보고 있는 페이지에만`). registry 주석이 스스로 "진짜 해법은 서버 3줄"이라 적어 둠 | `app/documents/router.py` + `registry/automation.js` |
| E14 | 전 3840 캡처 | `CONTENT_MAX_WIDTH.uhd=3080`까지 늘어나는데 본문은 `0.875rem` — 3m 폭 레이아웃에 14px, 하단 절반 공백 | `theme.js` FONT_SIZE(§Typography) + Archetype의 rail 전환 |
| E15 | `/me`, `/my-tickets`, `/my-stats` | 같은 "Notion 계정 미연결" 설명이 **5가지 다른 문구로 5번** | `kit.jsx`에 공유 `DependencyBlocked` 상태 |
| E16 | `/board` | 제목 컬럼이 4글자에 ~830px, 작성자는 이름+부서+직책을 300px에 욱여넣음. `공감`이 이모지 글리프를 데이터 값으로 사용 | C3 + `Board.jsx` |
| E17 | 온보딩 모달 | 3840에서 ~310×260px 고정 상자가 화면 중앙에 떠 있음 — root 폰트 레버를 안 따름 | `kit.jsx::Modal` |
| E18 | `/organizations` | 페이지에서 가장 가치 있는 숫자 `부서 미지정 12명`(회사 절반이 미배치)이 12px 회색 트리 부제인데, 1행짜리 표는 검색·저장뷰가 붙은 DataScreen을 통째로 받는다 | `OrgConsole.jsx`, `OrgTree.jsx` |

---

---

## Control Plane이 먼저 잡아야 할 네 가지 (실측 확인)

계획을 세우는 중에 **커버리지 자체가 거짓말을 하고 있다**는 것이 드러났다. 이건 Wave 0의 존재 이유다.

1. **리다이렉트를 화면으로 세고 있다.** `AdminRoutes.jsx:216-219`가 `/system`·`/notion-console`·`/llm-console`·`/maintenance`를 `<Navigate>`로 바꿨는데, `scripts/ui_qa/routes.py:210,286,288,289`는 아직 넷을 화면으로 등록한다. **PNG 4장이 실제로는 2화면이고, 23개 Assertion이 전부 리다이렉트 도착지에서 통과한다.** `tests/regression/test_ui_qa_route_registry_completeness.py`는 `AdminRoutes ⊆ harness`만 보므로 이걸 못 본다.
2. **사용자 Route 2개는 한 번도 캡처된 적이 없다.** `/my-approvals`(`MyApprovals.jsx`, 164줄)와 `/my-display`(`DisplaySettings.jsx`, 27줄)가 `routes.py`에 **0건**. 사용자 콘솔에는 완전성 테스트 자체가 없다.
3. **`/settings` 탭 본문 1,487줄이 직접 캡처된 적이 없다.** `SettingsShell.jsx:50-55`의 `TAB_DEFS = [policy, os, integration, ai]` 중 `os`/`integration`/`ai`가 `SystemOps`(389) / `NotionConsole`(433) / `LlmConsole`(394)를 그리는데 `routes.py`에는 `/settings` 하나뿐이고 그건 `policy`에 떨어진다.
4. **`scripts/static_checks.sh`가 지금 빨갛다.** `check_traceability.py`가 삭제된 `docs/UI_RENEWAL_TRACEABILITY.md`를 요구하며 `[FAIL]`을 낸다. **"static checks green"을 조건으로 쓰는 모든 Wave 종료 기준이 지금은 도달 불가**다. → 이 스크립트를 새 Gate로 흡수하고 `static_checks.sh:332` 단계를 교체한다. Gate가 둘이면 갈라진다.

---

## Control Plane — 세 Artifact + 하나의 Gate

### `docs/ui-renewal/ROUTE_COVERAGE.json`
단위는 Route가 아니라 **Surface**다. Route만으로 키를 잡으면 `/settings?tab=os`(Route 없음), `WorkSummary`(Home 위젯), `UsersBulk`(`/users` 내부), `ChatPane`(pane) 같은 2,961줄이 **구조적으로 표현 불가능**해지고, 다른 화면을 가리키는 행이 "커버됐다"고 말하게 된다. `route` 필드는 모든 Surface에 필수로 남는다(탭 본문은 query string, 위젯은 host route).

Surface 필드: `id · kind(route|tab|widget|modal|state_variant) · route · console · host_surface · component · render_engine · registry_key · alias_of · major(파생) · archetype(13종) · role · requirements[] · states_checked[](12종) · visual_audit · functional_audit · responsive_audit(profile 교차곱) · before_capture · after_capture · status(8종) · wave · findings[] · suppressions[] · entity_selectors[] · evidence{}`.

**Wave 이름의 정본은 이 파일이다.** 최상위에 `"waves": ["W0","W1","W2","W3","W4","W5","W5B","W6","W7","W8","W9","W10","W11","W12","W13","W14","W15"]` (17개)를 선언하고, `REQUIREMENT_MATRIX.md`의 `Wave:`와 Surface·Flow의 `wave` 필드가 전부 이 배열에 대해 검증된다 — 지시 56의 "존재하지 않는 Phase 참조 0건"을 Wave로 재정의한 것이다.

**Evidence는 자유 텍스트가 아니라 참조 토큰**(`ev:<kind>:<locator>`)이고 Surface마다 해석 테이블을 가진다. 이게 이런 파일이 썩는 가장 큰 경로를 막는다.

| kind | Gate가 검증하는 것 |
|---|---|
| `screenshot` | `thumb`이 존재·PNG·4KB~400KB·**git-tracked**. `sha256_full` 기록 필수. **`build_index_sha256`이 그 실행의 `results.json` 지문과 일치** — 낡은 번들 캡처를 증거로 못 쓰게 한다 |
| `qa_run` | `results.json` 파싱되고 `page_key`(`route\|theme\|viewport`) 레코드가 존재하며 그 스크린샷 파일이 실재 |
| `test` | 파일 존재 + 테스트 이름이 파일 안에 그대로 존재(`grep -F`) |
| `commit` | `git cat-file -e <sha>^{commit}` |
| `cmd` | tracked 텍스트 파일, 비어 있지 않고 **첫 줄이 명령 자체**(산문이 아니라 전사임을 증명) |
| `note` | **visual_audit·functional_audit·DONE의 단독 근거로 인정되지 않는다** |

**증거 보존**: `dist/`는 gitignore라 거기에만 있는 증거는 그 머신 밖에서 검증 불가다. → 전체 해상도는 `dist/`에, **주요 Surface의 Before/After 썸네일**(light, ≤1400px)만 `docs/ui-renewal/captures/{before,after}/`에 커밋. 약 30 Surface × 2 × ~150KB ≈ **9MB** — 이미 `app/static/react/assets/*.js`를 커밋하는 저장소에서 수용 가능하다. `scripts/ui_qa/collect_evidence.py`가 복사·축소·해시를 자동화한다(손으로 하지 않는다).

**`major`는 파일이 아니라 Gate가 파생한다** — 자기 신고 `major:false`가 명백한 탈출구이기 때문이다. 판정: `navConfig.js`의 `NAV`/`USER_NAV` 항목 `to:`에 나타나거나 / archetype이 8종 주요 유형이거나 / 250줄 이상 탭 본문. 파일 값이 다르면 Gate가 실패시킨다.

### `docs/ui-renewal/REQUIREMENT_MATRIX.md`
요구사항당 `##` 블록 하나, 필드 9개 고정. **폐기하는 `check_traceability.py`의 파서 형식을 그대로 쓴다**(`^##\s+(\d+)\.`, `^-\s+\*\*(.+?)\*\*\s*:\s*(.*)$`) — 검증된 파서에 더 엄격한 필드를 얹는다.

| 필드 | Gate 규칙 |
|---|---|
| `Wave` | `ROUTE_COVERAGE.json.waves`의 원소여야 한다. **"존재하지 않는 Phase 참조 0건"(지시 56)을 Wave로 재정의** |
| `Requirement` | ≥40자, **제목의 재진술이면 실패**(제목과의 정규화 편집거리 >0.4 또는 구체 명사+당위 표현 포함). "제목만 있는 항목" 금지 규칙의 직접 구현 |
| `Affected` | 각 토큰이 Surface `id` / `ARCHETYPE:<enum>` / `CONSOLE:user\|admin` / `ALL` / `NONE (사유≥40자)`로 해석돼야 한다 |
| `Implementation` | 백틱 감싼 `path[::symbol][:line]` 1개 이상, 경로가 실재. 순수 검증 요구는 `NONE (사유≥40자)` |
| `Verification` | **실행 가능한 것**을 1개 이상 명명 — `assertions.CLASSES`의 클래스명 / 실재하는 테스트 경로 / 알려진 러너로 시작하는 명령. 산문만이면 실패 |
| `Status` | `NOT_STARTED/IN_PROGRESS/DONE/BLOCKED/DEFERRED`. `DEFERRED`는 나중 Wave 지정 + 사유 필수 |
| `Evidence` | `DONE`이면 1개 이상, 각 토큰이 해석되고 디스크에 실재 |
| `Findings` | 실재하는 finding id + 상태. `DONE`인데 Critical/High가 `OPEN`이면 실패 |
| `Depends on` | 실재하는 요구사항 id, 순환 없음, **의존 대상의 Wave가 이 Wave보다 앞서야 한다**(W6에서 닫았는데 W11 의존인 상황을 잡는다) |

ID 체계는 앞의 실측 148개(`R-0`, `R-0.1~8`, `R-0-1~22`, `R-0-2.1~21`, `R-1~84`, `R-84-1~12`). Gate가 기대 집합을 만들어 누락·중복·범위 밖을 잡는다.

### `docs/ui-renewal/WORK_STATE.md`
삭제된 옛 `docs/WORK_STATE.md`가 반면교사다 — 보안 사후분석·날짜별 사이클 표 5개·배포 로그까지 자라 있었다. 새 파일은 **자라는 것이 기계적으로 불가능하도록** 설계한다.

`## CHECKPOINT` / `## NOW` / `## NEXT` / `## BLOCKERS` **정확히 이 넷, 이 순서**. Gate가 강제: ≤120줄·≤8KB / **다섯 번째 heading이 있으면 실패**(이게 "## 2026-08-19 이 세션에서 닫은 것"을 죽인다) / 날짜형 heading·`(완료|이력|history|log|사이클)` 금지 / CHECKPOINT 키 전부 존재·타입 검사 / `NEXT`는 실행 가능한 명령 / `BLOCKERS`는 정해진 형식이거나 `- 없음.`

**CHECKPOINT의 핵심**: `head`(실재 commit) · **`build_index_sha256`**(`capture.build_fingerprint()`와 일치 — 불일치면 그 QA 결과는 다른 번들 것이라 믿을 수 없다) · `route_coverage_sha256` · `requirement_matrix_sha256` · `coverage_gate` 마지막 판정. **해시를 기록하기 때문에 "동기화됨"이 증명 가능해지고, 낡은 체크포인트는 오도하는 대신 Gate에서 실패한다.**

### `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` (R-95) — **신규, 네 번째 Artifact**

**ROUTE_COVERAGE와 Requirement Matrix로 기능 검증을 대신하지 않는다.** Route가 존재하고 Screenshot이 있다는 사실은 그 화면의 기능이 정상이라는 증거가 **아니다.** 사용자가 겪은 티켓 Filter 오동작이 바로 그 증명이다 — 그 화면은 288페이지 Assertion을 전부 통과했고 스크린샷도 멀쩡했다.

Surface마다 **Flow 배열**을 갖는다. Flow는 그 화면에서 사용자가 실제로 실행할 수 있는 기능 하나다.

```jsonc
{
  "surface": "user_my-tickets",
  "flows": [
    {
      "id": "FF-0031",
      "category": "filter",              // R-92의 27개 범주 중 하나
      "name": "프로젝트 단독 Filter",
      "exists": true,                    // 이 화면에 실제로 존재하는 기능인가
      "status": "PASS",                  // NOT_AUDITED | PASS | FAIL | BLOCKED
      "chain": {                         // C7의 8단계 — 확인한 단계만 채운다
        "ui_state":     "project_id=proj_7f3a",
        "frontend_state":"qs.project_id=proj_7f3a",
        "url":          "#/my-tickets?project_id=proj_7f3a",
        "api_request":  "GET /api/tickets/mine?project_id=proj_7f3a",
        "backend_query":"TicketFilters.matches → project_id in ticket.project_ids",
        "data_relation":"tickets.project_ids ⊇ {proj_7f3a} (Notion relation → portal id 캐시)",
        "api_response": {"total": 14, "ids_sample": ["GIT-57","GIT-61"]},
        "rendered":     {"rows": 14, "total_shown": 14}
      },
      "expected": {"source": "known-data", "total": 14,
                   "note": "QA fixture 프로젝트 proj_7f3a 에 연결된 티켓 14건"},
      "evidence": ["ev:e2e:dist/ui-qa/w14-filter/results.json#user_my-tickets.filter.project",
                   "ev:cmd:docs/ui-renewal/evidence/w14-filter-project.txt"],
      "findings": [],
      "audited_at": "2026-08-27", "by": "functional-e2e"
    }
  ]
}
```

규칙:
- **`PASS`는 실제 Browser Action + Network/API/Backend/Data 결과 Evidence를 요구한다.** 렌더 Evidence(`screenshot`)만으로는 `PASS`가 될 수 없다 — Gate가 `evidence`에 `e2e`/`qa_run`/`cmd`/`test` 종류가 최소 1개 있는지 검사한다.
- **`exists: false`**(그 화면에 그 기능이 없음)는 검증 대상에서 빠지되 **사유가 필요**하다. 없는 기능을 테스트용으로 새로 만들지 않는다(R-92).
- **`BLOCKED`**는 외부 원인만. `FAIL`은 Finding을 만들고 Root Cause 수정 후 재검증.
- Flow는 Requirement와 연결된다(`R-85`~`R-89`, `R-92`~`R-94`).
- 실데이터에 영향을 주는 Flow(Create/Edit/Delete/상태 변경/시스템 Action)는 **전용 QA Fixture**를 쓰고 검증 후 정리한다. 위험 Action은 기존 백업·원상복구 정책(지시 68)을 그대로 따른다.

### `scripts/check_ui_renewal_coverage.py` — 14개 조건

**소스 진실은 5개 리더에서 만든다. 어느 것도 `ROUTE_COVERAGE.json`을 믿지 않는다.**
① `UserRoutes.jsx`+`AdminRoutes.jsx`의 `<Route path="…">` (+ 같은 요소의 `element={<Navigate to="…"` 을 잡아 **alias로 분류**) ② `AdminRoutes.jsx::TAB_GROUPS` ③ `SettingsShell.jsx::TAB_DEFS` ④ **REGISTRY 키는 정규식이 아니라 Vitest**(`registry-surface-parity.test.js`가 `REGISTRY`를 import해 대조 — JS 진실은 JS가 증명한다. Python 정규식으로 7개 도메인 파일을 훑었을 때 28개 중 1개를 조용히 놓쳤다) ⑤ `scripts/ui_qa/routes.py::ALL_ROUTES`(역방향 검사용).
위젯(`ChatPane`·`AssistantPanel`·`WorkSummary`·`UsersBulk`)은 선언하되 **`host_surface`의 컴포넌트가 실제로 import하는지 확인** — 엉뚱한 host 밑에 주차할 수 없다.

| # | 조건 | 판정 방법 |
|---|---|---|
| C1 | 소스에 있는데 Coverage에 없는 Route | `SOURCE \ COVERAGE ≠ ∅`. `file:line`과 컴포넌트 LOC까지 보고해 누락 규모가 보이게 |
| **C1b** | **Coverage/harness는 화면이라는데 소스는 리다이렉트** | `alias_of` + `kind:"state_variant"`가 없으면 실패. **위 발견 1을 잡는 조건** |
| C2 | `UNKNOWN/TODO/NOT_AUDITED` 상태 | 항상 치명. `--stage wave`에서는 현재 Wave 이하 Surface에 대해 |
| C3 | Matrix에 매핑 안 된 요구사항 | 161 기대집합 대조 + `Affected`가 0 Surface로 해석되는데 `NONE(사유)`가 없음 + `major`인데 `requirements` 비어 있음 + Wave 미존재 |
| C4 | 완료인데 Evidence 없음 | 토큰 해석 실패·`note` 단독·썸네일 부재·`page_key` 부재·테스트 이름 부재·commit 부재. **`build_index_sha256` 불일치는 `EVIDENCE_STALE_BUILD`로 실패** |
| C5 | Visual/Functional Audit이 비어 있음 | `PENDING`·키 없음이면 실패. `PASS`는 non-`note` 증거 + `by` + `at` 필수. major는 `flows` 1개 이상. `responsive_audit.matrix`가 profile 교차곱을 전부 덮어야 함 |
| C6 | 주요 Route인데 Before/After 없음 | `major`는 Gate가 파생. 둘 다 tracked 썸네일로 해석되고 **두 캡처의 `build_index_sha256`이 서로 달라야** 한다(같은 번들의 before/after는 before/after가 아니다) |
| C7 | Critical/High Finding 잔존 | `--stage complete`. `ACCEPTED`는 사유 ≥60자 **+ 그 finding id가 `DEFERRED` 요구사항의 `Findings`에 등장** — 수용이 항상 결정에 추적된다 |
| C8 | 검색형 Entity Selector가 필요한데 평범한 Dropdown | 정적 후보(registry `refLists`/`optionsFromRefList`/entity 어휘의 `type:"select"`, 수작업 화면은 한글 entity 어휘의 `FilterSelect`) **와** 런타임 `plain_dropdown_for_entity`가 **둘 다** 일치해야 통과. 어휘는 **기수가 무한히 자라는 entity 타입만** 담은 닫힌 목록이라 옵션 개수를 셀 필요가 없다(상태·역할·우선순위 select는 애초에 후보가 아니다) |
| C9 | Column Width/Alignment 검수 Evidence 없음 | `list_table` Surface(46개)마다 `qa_run` 증거에 `column_width_vs_content`·`header_cell_alignment_mismatch`·`numeric_alignment`가 **`skip`이 아닌** 판정으로 폭 ≥1366에서 존재. **`skip`은 증거로 치지 않는다** — 지금 `narrow_main`의 "144 pass / 144 skip"이 커버리지로 읽히는 것과 같은 함정 |
| C10 | 완료된 주요 화면에 Layout Finding 잔존 | 7개 Layout 클래스가 `CLOSED`가 아니면 실패. **추가로 Gate가 최신 after `results.json`을 다시 읽어, Coverage에 finding이 없어도 해당 Assertion이 fail이면 실패** — 행을 지워서 finding을 닫을 수 없게 |
| **C11** | **Search/Filter 기능 검증 누락 또는 실패** (R-85·R-86·R-87·R-88) | Search/Filter/Sort/Pagination/Combobox가 **존재하는** 모든 Surface에 대해 `FUNCTIONAL_COVERAGE.json`에 `category ∈ {search, filter, sort, pagination, combobox}` Flow가 있어야 하고, 각 Flow가 `PASS`이며 `chain`의 8단계 중 **최소 `api_request`·`backend_query`·`api_response`·`rendered`가 채워져** 있어야 한다. Relation 기반 축(프로젝트·담당자·부서 등)은 `data_relation`도 필수. 단독 조건과 **복합 조건 Flow가 각각** 존재해야 하고, Page 기본 Scope가 있는 화면은 `scope_combined` Flow가 추가로 필요하다. `race`·`cache_key`·`page_reset`·`back_forward` Flow가 없으면 실패 |
| **C12** | **Functional Coverage에 `NOT_AUDITED` 잔존** (R-92·R-94·R-95) | `--stage complete`에서 `exists: true`인 Flow 중 `NOT_AUDITED`가 하나라도 있으면 실패. `--stage wave`에서는 현재 Wave가 담당하는 Surface에 대해 적용. **Route Inventory에서 파생한 27개 범주 중 그 화면에 실재하는 범주가 Flow로 만들어지지 않았으면 그것도 실패**(범주 누락 = 검증하지 않은 것) |
| **C13** | **화면 간 정합성 검증 누락** (R-93) | 상태 변경·생성·삭제처럼 파생 지표에 영향을 주는 Flow는 `cross_surface` 배열로 **영향받는 다른 Surface와 그 확인 결과**를 가져야 한다(티켓 상태 변경 → Grid·상세·내/팀/미할당 포함 여부·Home Count·Sprint 집계). Dashboard·Home·Sprint·관리자 Overview의 Count/KPI/Chart Flow는 `expected.source`가 `known-data` 또는 `derived-check`여야 하고 `rendered` 값과 일치해야 한다. **같은 Metric을 두 Surface가 다른 값으로 보고하면 실패** |
| **C14** | **죽은 Action / Backend 미연결 잔존** (R-94) | 사용자·관리자 양쪽에서 `category ∈ {row_action, overflow_action, modal_action, settings_apply, admin_op, notification_action, approval_action}` Flow 중 `status: FAIL`이면서 `finding.class ∈ {dead_action, frontend_only_state, not_persisted, missing_backend, missing_ui, dead_route, bad_query_param, stale_cache, duplicate_request, race_condition, permission_mismatch}`인 것이 `CLOSED`가 아니면 실패 |

**Plan 단계 조건 (R-96·R-97, `--stage plan`)** — 구현 전에 계획 자체를 검증한다: 이름 없는 Wave 0건 · 존재하지 않는 Wave/Phase 참조 0건 · Wave마다 `소유 파일`과 `전제`가 비어 있지 않음 · 모든 Wave에 Exit Gate가 있음 · Requirement 161개가 전부 Matrix에 존재하고 각자 `Wave`가 `waves`의 원소 · `R-64`/`R-65`가 원래 의미로 남아 있고 신규 요구가 `R-85` 이상 · `docs/ui-renewal/`의 4개 Artifact + WORK_STATE가 존재하고 파싱됨 · 계획 문서에 미완 상태 표기가 없음.

> **이 Gate의 오탐 두 가지를 미리 막는다** (계획서에 시제품 검사기를 돌려 실제로 겪었다).
> ① **"이름 없는 행" 검사는 Wave 표에만 적용한다.** 비교표의 좌상단 빈 모서리 셀(`| | A | B |`)은 정상적인 Markdown이다. 표 전체를 훑으면 정상 표가 걸린다.
> ② **미완 상태 표기 검사는 규칙 문장 자체를 제외한다.** R-96과 이 조건문이 금지 대상 문자열을 **인용**하고 있으므로, 인용을 세면 Gate가 자기 자신 때문에 영원히 실패한다.
> 이건 저장소가 이미 배운 규율이다 — 측정값이 이상하면 대상을 고치기 전에 **프로브를 먼저 의심한다**(`scripts/ui_qa/README.md`가 같은 교훈을 기록하고 있다).

종료 코드: `0` 통과 · `1` 조건 위반 · `2` **정직하게 실행 불가**(Artifact 없음/파싱 불가/소스 파일 없음 — 조용히 통과하지 않는다) · `3` `--stage complete`인데 증거 Artifact가 이 머신에 없음(`dist/` 정리됨). **`3`을 `0`으로 접지 않는다.** `--stage`는 `plan | wave | complete`.
성공 줄에도 **항상 억제 개수를 찍는다** — 초록 실행이 얼마나 침묵시켰는지 숨기지 못하게.

---

## 새 Assertion 13종 (`scripts/ui_qa/assertions.py`)

전부 `assertions.CLASSES`에 등록(그 튜플이 `--fail-on` 검증과 요약 출력의 정본이다). 11개는 기존 단일 `PROBE_JS` 패스에 들어가고, 2개는 `contrast`가 이미 쓰는 패턴(지연 import + 같은 page에 두 번째 `evaluate`, 실패 시 record 폐기 대신 `skip`)을 따른다 — `brand.py`(gradient stop 파싱 + sRGB→HSL), `mascot.py`(PNG 알파 bbox를 `<canvas>`+`getImageData`로 **실행당 1회** 계산, `dist/ui-qa/<label>/mascot-ink.json`에 캐시 — 새 Python 의존성 없음).

공용 헬퍼 3개를 `PROBE_JS`에 추가: `rowsOf()`(`Range.getClientRects()`의 top을 8px 버킷으로 — `vertical_text_collapse`가 이미 쓰는 기법) · `inkGrid(el, cell)`(padding box를 격자로 나눠 보이는 잎 노드가 닿는 칸 표시. 겹치는 사각형 합집합 면적보다 싸고 ±cell 정밀도면 충분. cell = `max(24, floor(vpW/60))`) · `demandOf(el)`(한 줄이면 Range 실측 잉크 폭, 여러 줄이면 `(글자수/줄수) × 실측 1ch`).

| Assertion | 판정 규칙 (요약) | 오탐 분리의 핵심 |
|---|---|---|
| `equal_column_split` | 트랙 ≥2 · 모두 ≥160px · **used 폭 비 ≤1.02** · **demand 비 ≥2.5** · 한 트랙은 `lines≥2`인데 다른 트랙은 `freeRatio≥0.5` | **트랙이 content-sized였다면 폭이 같다는 건 demand가 같다는 뜻이다. 따라서 "폭 동일 + demand 비 ≥2.5"가 그 자체로 `1fr` 강제의 증거다.** 7일 달력(`SchedulerCalendar.jsx:351`)·게임판(`LadderBoard.jsx:39`)만 `data-equal-grid` 옵트아웃 |
| `column_width_vs_content` | A열 `wrapRate≥0.5` **그리고** B열 `fill≤0.45`·`slackPx≥96`·`slackPx ≥ 0.5×width_A` | 폭 ≥1200에서만(900 미만은 카드 모드, 900~1200은 한글이 원래 접힌다). fill을 **셀 잉크와 헤더 잉크의 max**로 재 헤더가 길어서 넓은 컬럼을 slack이라 부르지 않는다 |
| `header_cell_alignment_mismatch` | `th`의 `textAlign` ≠ 그 컬럼 `td`들의 최빈 `textAlign` | 항상 결함이다. **억제 불가.** `kit.css:43`이 둘 다 left인데 `kit.jsx:1036/1124`가 head/body에 `align`을 따로 넘기므로 한쪽만 설정하는 경로가 실제로 존재 |
| `numeric_alignment` | 숫자 컬럼(비-빈 셀 80%가 숫자 패턴, 날짜형 제외)이 우정렬이 아니거나 `tabular-nums`가 없음 | 식별자형 숫자(티켓번호·포트·버전)는 `identifier:true`가 이미 있어 `data-col-role="identifier"`로 면제. 전화·버전은 엄격한 정규식이 배제. **억제 불가** |
| `isolated_control_row` | 한 컨트롤(또는 폭 <40%)만 있는 줄 R **그리고** 직전 줄 P가 `freeWidth_P ≥ usedWidth_R + gap` 이고 `≥120px` | "위 줄에 실제로 들어갔는데 밀려났다"를 증명한다. 좁은 화면의 정상 wrap은 slack이 없어 발화 안 함. `ToolbarEnd`의 의도적 2번째 줄(`FilterBar.jsx:55-62`에 문서화된 설계 결정)은 `data-control-row="separate"` |
| `control_baseline_mismatch` | 한 줄 안에서 **같은 kind끼리** 높이 차 >4px, 또는 **kind 무관** centerY 차 >3px | 2부 규칙이 옳은 모델이다 — 높이는 kind 안에서, 중심은 kind를 넘어. **내부 박스**(`.MuiInputBase-root`)를 재 검증 메시지로 늘어나는 wrapper를 피한다 |
| `oversized_empty_surface` | `coverage<0.18` & 빈 면적 ≥200,000px², **또는** `contentBBox.width/paddingBox.width < 0.45` & 폭 >700 | 두 번째 분기가 "큰 사각형 좌측에 컨트롤 3개"를 직격한다. canvas/svg는 bbox 전체를 잉크로 셈. 스켈레톤 제외. `EmptyState` 하위는 여기서 제외하고 `dead_blank_region`이 담당 — 지시는 빈 화면이 **완성돼 보이길** 원하지 빽빽하길 원하지 않는다 |
| `dead_blank_region` | 페이지가 스크롤되지 않고 (하단 공백비 ≥0.35/0.30 & `inkRatio≤0.45` & **`unsatisfiedDemand`**) 또는 (우측 공백비 ≥0.30 & …) 또는 **극단**(하단 ≥0.55 & `inkRatio≤0.25`) | **`unsatisfiedDemand`가 짧은 페이지를 살린다** — 줄바꿈·활성 ellipsis·2페이지 이상 pager·내부 스크롤 중 하나라도 있어야 발화. 필드 3개짜리 설정 폼은 하단 공백비가 커도 굶주린 게 없어 앞 두 분기 불가, `inkRatio`도 0.25 초과라 극단 분기 불가. 반대로 4K 대시보드(줄바꿈된 KPI 라벨 + 페이지네이션 + 60% 공백)는 첫 분기에서 발화 |
| `brand_presence` | 7개 role(header·nav_active·primary_action·ai_surface·highlight·selected_state·focus_ring) 중 **4개 미만이면 실패**, `nav_active`나 `primary_action`이 무채색(S<0.08)이면 **무조건 실패**. Brand 계열 = 색상각 222~278°(`#536CD6`≈230°, `#8E75E1`≈257°가 안에 있다), S≥0.25(L)/0.18(D), 배경 role은 Canvas와 ΔE>10 | Gradient는 stop 파싱, 못 읽으면 `unknown`이고 **통과로 치지 않는다**(`contrast.py`의 "모르면 모른다고 한다" 규율). **이 Assertion은 현재 빌드에서 실패한다 — 그게 요점이다.** `AppShell.jsx:678-687`이 "chrome 은 발광하지 않는다"는 주석과 함께 AppBar를 `sidebar.bg`로 두고 있고, 그 결정이 새 지시와 정면 충돌한다. 측정이 그 충돌을 논쟁 대신 가시화한다. **억제 불가** |
| `mascot_visible_size` | `visibleH = boxH_rendered × (inkH/natH)`가 context별 최소치 미만이면 실패 (topbar ≥22 · fab ≥40 · sidebar ≥36 · avatar ≥24 · empty_state ≥96 & ≤컨테이너 40% · hero ≥140 · inline ≥28) | 실패 노트가 원인을 구분한다 — `inkFrac<0.45`면 자산 여백 문제(재프레이밍), 아니면 렌더 박스 문제. `Mascot.jsx:261`의 topbar `size={28}`은 **보이는 캐릭터가 22px에 한참 못 미친다** — 박스 크기 검사로는 절대 안 보였을 결함 |
| `plain_dropdown_for_entity` | entity 어휘에 해당하는 `select`/`[role=combobox]`가 검색 가능(내부 input 또는 `aria-autocomplete="list"`)하지 않으면 실패 | **옵션 개수를 세지 않는다** — MUI 메뉴는 열기 전엔 DOM에 없고, 더 중요하게는 어휘 자체가 기수 무한 타입의 닫힌 목록이다. **억제 불가** |
| `detail_side_imbalance` | 2열 그리드에서 `min(inkArea)/max(inkArea) ≤0.15` **그리고** 빈 쪽 빈 면적 ≥250,000px² **그리고** 높이 차 ≥0.5×max | 기존 `railRatio` 프로브(`assertions.py:211-237`) 확장. `rail_wider_than_prose`가 "레일이 본문보다 넓다"를 잡고 이건 "한쪽이 동나고 그 공간이 회수되지 않았다"를 양방향으로 잡는다. 폭 ≥1366에서만 |
| `surface_repetition` | 동일 tone signature 그룹이 임계(6/8/10, 뷰포트별) 이상 & 합계 면적 ≥35% & **구조적**일 때 | **목록 vs 구조 판별자**가 핵심 — `<li>`·`role="list"` 하위·행 열기 affordance를 가지면 **목록**(정상 패턴), 각자 고유 heading을 갖고 내비게이션이 없으면 **구조**("동일 형태 흰 카드 8개" 결함). `Games` 카드 그리드·`ChatRooms` 목록에서 안 터진다 |

**Gate vs Advisory**: `header_cell_alignment_mismatch`·`numeric_alignment`·`plain_dropdown_for_entity`는 W0부터 `--fail-on`. `brand_presence`·`mascot_visible_size`는 W1부터. `isolated_control_row`·`control_baseline_mismatch`는 W5, 4개 Table 계열은 W6(288페이지 보정 실행 1회 후), `detail_side_imbalance`는 W9.
**`oversized_empty_surface`·`dead_blank_region`·`surface_repetition`은 영구 Advisory** — 임계값이 취향을 인코딩하기 때문이다. 대신 각 `fail`이 **Finding이 되고 C10이 완료 시점에 막는다.** 이 결합이 임계값 수정을 초록으로 가는 가장 싼 길로 만들지 않는다 — 그게 이 설계 전체가 막으려는 실패 모드다. `run.py`에 `--findings-out` 한 줄을 추가해 fail을 finding stub으로 뽑는다.

**억제 규율** — `docs/ui-renewal/QA_SUPPRESSIONS.md` 한 파일, 행마다 `id · assertion · marker · surface · 사유(≥40자) · owner · opened · expires · evidence`. Gate가 강제: ① **양방향 정합**(소스의 `data-*` 마커와 행이 1:1, 어느 쪽 고아든 실패) ② **만료 ≤60일** — 억제는 결정이 아니라 **날짜 있는 약속**이다 ③ 예산 총 15개·클래스당 2개 ④ **금지 클래스 4종** ⑤ 사유에 `임시·나중에·TODO·일단` 금지("일단"은 억제가 아니라 `DEFERRED`다) ⑥ `run.py` 요약에 `억제` 열 추가 + **억제 수가 실패 수보다 많으면 경고 마커**.

---

## Wave 계획 (지시 84-7) — 17 Wave (W0 · W1~W5 · W5B · W6~W15)

**Wave 종료 조건 7개**(모든 Wave 동일): **E1** 건드린 Surface 전부 재캡처 + `visual_audit ≠ PENDING` · **E2** 배정 요구사항이 `DONE` 또는 사유 있는 `DEFERRED` · **E3** 그 Wave에 새로 Gate가 된 Assertion이 초록, Advisory fail은 Finding으로 기록, `DONE` 처리한 Surface에 Critical/High 미해결 0 · **E4** 건드린 공유 파일과 **명명된 소비처**의 focused test 초록 + 옛 구조를 고정하던 Contract Test를 **삭제·약화가 아니라 재작성**(`scripts/check_test_strength.py`가 검증) · **E5** `static_checks.sh` 초록(새 Coverage Gate 포함) · **E6** `npm run build` + `check_bundle_fresh.py` + `generate_design_tokens.mjs --check` 초록, QA 라벨과 `build_index_sha256`이 CHECKPOINT에 기록 · **E7** **구현하지 않은 에이전트**의 독립 Visual Reviewer + Requirement Reviewer 서명.

| Wave | 내용 | 소유 공유 파일 | 전제 | Wave 고유 Exit Gate (E1~E7에 더해) |
|---|---|---|---|---|
| **W0** | Baseline & Control Plane — **제품 코드 변경 없음.** **4개** Artifact(`REQUIREMENT_MATRIX.md`·`ROUTE_COVERAGE.json`·**`FUNCTIONAL_COVERAGE.json`**·`WORK_STATE.md`) + `QA_SUPPRESSIONS.md` + Gate 신설, `routes.py` 수정(누락 2 Route + `/settings` 탭 4 + TabShell 본문 5 추가, `<Navigate>` 4개를 alias로 재분류), Assertion 13종 전부 Advisory로 추가, `brand.py`/`mascot.py`/`collect_evidence.py`, 완전성 테스트 양방향 확장, **Notion 매핑 수리(Real Data 캡처 전제)**, `check_traceability.py` 흡수·교체 | `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`, `scripts/check_ui_renewal_coverage.py`(신규), `scripts/static_checks.sh` | 없음 (프로그램 시작점) | ① **전 Surface × light/dark × 9뷰포트 `--label before-renewal` 완전 실행 + 썸네일 커밋 — 존재할 유일한 "Before"다. 제품 코드가 바뀌기 전에 끝낸다** ② 지시 84-9 Plan Gate의 1번(161 Requirement 전부 Matrix 매핑)과 3번(전 Route가 Archetype으로 분류)을 **기계적으로** 충족 — 계획서에 손으로 표를 적는 것보다 소스에서 파생되고 Gate가 계속 검사하는 Artifact가 강하다 ③ **R-92의 27개 범주로 전 Route Functional Flow Inventory 생성**(전부 `NOT_AUDITED` 초기값) ④ `check_ui_renewal_coverage.py --stage plan` **및** `--stage wave` PASS. 통과 전에는 W1을 시작하지 않는다 |
| **W1** ⚠️ | Brand Foundation — `theme.js` → 생성기 → 두 `tokens.css` → 두 Contract Test 재작성. **한 에이전트, 한 커밋 시퀀스** | `frontend/src/ui/theme.js` | W0 | `brand_presence ≥5/7`이 smoke set × 두 테마에서 측정되고, `theme-contract.test.js`의 대비 단언이 원래 강도로 통과 |
| **W2** ⚠️ | Global Shell — AppBar·main padding·content width, `TopBrand`/`TopSearch`/`Banners`/`ScopeBar`, `root.css` | `frontend/src/app/AppShell.jsx`(셸부) | W1 | `narrow_main`·`dead_blank_region`을 3840에서 측정, `topbar-contract.test.jsx` 재작성 완료 |
| **W3** ⚠️ | Navigation & Icon — `navConfig.js`·`navIcons.js`·`AppShell` 사이드바부(W2 커밋 **뒤**)·`CommandPalette` | `frontend/src/app/navConfig.js`, `navIcons.js` | W2 | Nav 라벨 시작선 42px 단언 + `nav-active`·`nav-features`·`registry-area-matches-nav-group` 통과 |
| **W4** ⚠️ | 공유 Layout Primitive — `kit.jsx`(Card/Section/Panel 분리·PageHeader·MetricStrip·MetaBar·EmptyState·ErrorState·Skeleton), `kit.css`, `adminKit.jsx`, `density.js`, `screens.css` | `frontend/src/ui/kit.jsx` | W1 + W2 | Surface 판정 체크리스트가 코드로 표현되고 `surface_repetition`·`oversized_empty_surface` Advisory 수치가 Surface별로 기록됨 |
| **W5** ⚠️ | Search/Filter/Form **설계** — `FilterBar.jsx`·`filters.jsx`(+`EntityCombobox`)·`SavedViews.jsx`, 소비처 4곳을 정해진 순서로. **C2 + R-88의 UI 규칙**(값 식별성·Dropdown 구분·초기화 표현·결과 건수 위치·0건 두 얼굴) 포함 | `frontend/src/ui/FilterBar.jsx`, `frontend/src/ui/filters.jsx` | W4 | `isolated_control_row`·`control_baseline_mismatch`가 `--fail-on`으로 승격되어 초록. `plain_dropdown_for_entity`가 `entity_selectors`를 선언한 전 Surface에서 초록 |
| **W5B** | **Search/Filter 기능 정확성 (R-85·R-86·R-87·R-94 일부)** — **디자인 Wave가 아니라 버그 수정 Wave다.** C7의 8단계 사슬을 전 Consumer에서 실측하고 어긋난 지점의 Root Cause를 고친다. 1순위 용의자: `app/tickets/repository.py`의 `project_ids` relation 해석 경로(R15) · `TicketFilters.matches:147/168` · Filter 옵션 소스(`service.list_projects`)와 티켓 식별자의 정합 · `ticketQueryParams`의 page 리셋 책임(R17) · react-query key 구성 · `DataScreen` 필터 루프. **Frontend에서 멈추지 않고 API Parameter → Backend Join/Relation → Permission Scope → Query Condition까지 추적한다** | `frontend/src/screens/TicketFilterBar.jsx`, `frontend/src/lib/useQueryState.js`, `app/tickets/repository.py`, `app/tickets/router.py`, `frontend/src/screens/DataScreen.jsx`(필터 루프만) | W5 | **C11 통과** — Search/Filter가 존재하는 전 Surface에 단독·복합·Scope결합·page리셋·race·cache key·back/forward Flow가 `PASS`이고 각 `chain`이 최소 4단계 채워짐. Known Data 대조 결과가 Evidence로 남음 |
| **W6** ⚠️ | Table/Grid/Metadata/Alignment + **공통 Property Editing Pattern(C8·R-89)** — `kit.jsx::DataTable`(W4 뒤)·`cells.jsx`·`registry/shared.js`·`DataScreen.jsx:1036,1124`. Column `type` 계약, **R-91로 교정한 Collapse 규칙**(`resultScope` 입력), Inline Edit 상태 기계를 공통 계층에 만든다(배선은 W9) | `frontend/src/ui/kit.jsx::DataTable`, `frontend/src/screens/registry/shared.js` | W4 + W5 | 4개 Table Assertion이 `--fail-on`으로 승격되어 초록. **C9 통과**(`list_table` 46 Surface 전부 non-skip 판정 증거). `resultScope` 없이는 컬럼을 제거하지 않는다는 단위 테스트 존재 |
| **W7** | Empty/Loading/Error/Feedback + Clovi 크기 + **Detail Metadata 위계(C9·R-90)** — `EmptyState`/`ErrorState`/`Skeleton`(W4·W6 뒤), `lib/assets.js`, `Mascot.jsx`, `MetaBar` 위계 재설계 | `frontend/src/ui/kit.jsx::EmptyState/ErrorState/MetaBar`, `frontend/src/ui/Mascot.jsx` | W4 + W6 | `mascot_visible_size` 초록. 빈 데이터에서 차트·표·Pager가 실제로 언마운트됨을 렌더 테스트로 고정. Detail Metadata가 **긴 프로젝트명 실데이터**로 FHD/QHD/4K × Zoom 3단계 캡처됨 |
| **W8** | **Pilot 8종 end-to-end**(지시 0-7·84-6이 명명한 집합 — 서로 다른 Archetype을 대표해야 한다): `/me` **B1 Dashboard** · `/projects` **B2 List+DataGrid** · `/sprint` **B7 Report/회의** · `/chat-rooms` **B9 Chat** · `/tickets/:id` **B4 Work detail** · `/board/:id` **B3 Reading** · `/organizations`+`/users` **B11 Split view** · `/settings`(+`?tab=os`) **B10 Settings / `/jobs` B8 Ops**. **공유 파일 무변경** — 여기서 공유 계약이 첫 정직한 시험을 받는다. 필요한 공유 변경이 나오면 그건 W4~W7의 결함이고 거기로 되돌린다 | 없음 (Pilot Page 파일만) | W7 (+ Pilot 화면이 Filter를 쓰면 W5B) | **Pilot Exit Gate.** 8쌍 Before/After에 대해 지시 0-7의 검수 순서를 그대로 수행: ① `ui-ux-pro-max` 구조·사용성 Audit ② `impeccable` Critique ③ `design-taste-frontend`로 Typography·Spacing·Surface·비율·리듬 검수 ④ **독립** Visual Reviewer가 옛/새 화면 비교 ⑤ **독립** Requirement Reviewer가 누락 확인. 지시 0-7의 **9개 Pilot 질문**에 전부 답이 나와야 한다 — Purple/Indigo가 명확한가 · White/Gray 포털 인상에서 충분히 벗어났는가 · 정보 구조가 목적에 맞는가 · 이유 없는 대형 Blank가 없는가 · Empty State가 완성된 Layout인가 · Typography와 Control 크기가 실제 브라우저에서 읽기 좋은가 · MUI 기본 느낌/Legacy가 지배하지 않는가 · Responsive에서 정보 우선순위가 유지되는가 · 기능·권한·데이터가 보존되는가. **추가로 Pilot 화면의 Functional Flow가 `PASS`여야 한다**(디자인만 통과한 Pilot은 Pilot이 아니다). 하나라도 부족하면 Theme과 Composition을 고쳐 재검수하고 **W9 이후 전체 롤아웃을 시작하지 않는다.** 사용자 승인 Gate를 만들려고 멈추지는 않는다 — Workflow 내부 Reviewer로 수렴한 뒤 계속한다(지시 0-7 말미·0-21) |
| **W9** | 핵심 사용자 Workflow — 티켓 / 문서 / 채팅. **3에이전트 병렬 안전.** 일반 사용자 수동 동기화 제거 + **C8 Inline Edit를 티켓 Grid·Detail Header에 배선(R-89·R-90)** | 없음 (화면 파일만, 공유 계층은 W6·W7이 소유) | W8 + W6(Pattern) | 티켓 상태·우선순위 Inline Edit의 9개 상태가 전부 렌더 테스트로 고정. 변경 후 목록·상세·Home Count가 함께 갱신됨(C13 예비 확인) |
| **W10** | 나머지 사용자 Route — Home·Projects·Sprint·Board·Games·Search·Profile·MyStats·Activity·MyApprovals·DisplaySettings·AssistantPanel·WorkSummary. **화면군당 1에이전트 완전 병렬** | 없음 (화면 파일만) | W8 | 각 화면의 Functional Flow가 `NOT_AUDITED`에서 최소 `IN_PROGRESS`로 이동하고 Filter가 있는 화면은 W5B의 계약을 따름이 확인됨 |
| **W11** ⚠️ | 관리자 IA — `navConfig.js`(W3 뒤)·`AdminRoutes.jsx::TAB_GROUPS`·`SettingsShell.jsx`·`TabShell.jsx`. **여기서 alias/탭 본문 커버리지 부채를 갚는다** | `frontend/src/app/navConfig.js`, `frontend/src/app/AdminRoutes.jsx` | W3 + W10 | 병합 전 `sameRoles()` 역할집합 동등성 통과. **옛 주소 전부가 제자리 렌더 + query 보존**(`<Navigate>` 아님)을 회귀 테스트로 고정. C1b 초록 |
| **W12** | 관리자 Console — `DataScreen.jsx`(W5·W6 뒤, ⚠️) → **registry 7개 도메인 파일 병렬**(설계상 disjoint — `registry.js`가 쪼개진 이유가 이것이다) + OrgConsole·Users·Offboarding·SystemOps·NotionConsole·LlmConsole·Maintenance·MailStatus·Diagnostics·Integrity·DevReport·SchedulerCalendar·SetupWizard. **지시 42의 관리자 기능 전수검증 + R-94의 죽은 Action 조사를 여기서 시작** | `frontend/src/screens/DataScreen.jsx` | W11 | 관리자 Surface의 Functional Flow가 전부 생성되고, 발견한 죽은 Action·미연결이 Finding으로 등록됨 |
| **W13** | **Identity + Hostname + TLS** — Backend·배포 중심이라 **W9~W12와 병렬**. 단 localStorage 키를 만지는 프런트 5파일(`theme-store.js`·`ThemeModeProvider.jsx`·`AppShell.jsx:68`·`LoginHandoff.jsx`·`StatusNotices.jsx`)과 `capture.py:87-99`는 ⚠️ W2 창과 순서 조정 | 위 5파일 + `app/core/sessions.py`, `deploy/nginx/*`, `scripts/install-*.sh` | W1 | §Hostname 런북 8단계 검증 명령이 전부 통과하고 `ssl_verify_result=0`. 옛 빌드 로그인 → 배포 → 새로고침 시 **로그인·테마 유지** E2E 통과 |
| **W14** | **Functional E2E — 전체 기능 Inventory 기반 (R-92·R-93·R-94)**. 새 UI 없음. "주요 Workflow"로 범위를 제한하지 **않는다** — 사용자·관리자 전 Route의 **실재하는** Interactive Function을 27개 범주로 전수 검증한다. 사슬은 `Screen → User Action → Network → API → Backend → DB/Data → UI Result → 관련 화면 → Reload → RBAC` 전체. **화면 간 정합성(R-93)**과 **죽은 Action/미연결(R-94)**을 함께 닫는다. + Zoom 100/125/150 + 5역할 매트릭스. 실데이터 영향 Action은 전용 QA Fixture, 위험 Action은 상태 저장·원상복구(지시 68) | `scripts/ui_qa/*_e2e.py` (신규 flow 모듈 포함) | W12 + W13 | **C11·C12·C13·C14 전부 통과.** `exists:true` Flow에 `NOT_AUDITED` 0건 |
| **W15** | Whole-product 재감사 — `--label w15-final` 전체 실행, `collect_evidence --into after`, `check_ui_renewal_coverage --stage complete`, 전 Before/After 쌍 독립 Reviewer, 완료 조건 확인 | 없음 (검증 전용) | W14 | 아래 «완료 조건» 전 항목 충족 |

**충돌 위험 파일 소유·순서**: `theme.js` W1(+W13 rename은 별도 커밋) · `AppShell.jsx` W2→W3→W13 · `navConfig.js` W3→W11 · `kit.jsx` W4→W6→W7 · `DataScreen.jsx` **W5→W5B(필터 루프만)→W6→W12** · `registry/shared.js` W6→W12 · `TicketFilterBar.jsx` **W5→W5B** · `app/tickets/repository.py` **W5B 단독** · `assertions.py` W0이 구조 소유, 이후 Wave는 상수만 조정(각각 보정 실행을 첨부한 자기 커밋으로).
**안전 병렬**: 개별 leaf 화면 · registry 7 도메인 파일 · 모든 Backend(W5B가 만지는 티켓 repository 제외) · 모든 배포/스크립트 · `*_e2e.py` · 문서.
**W5B의 위치가 중요한 이유**: Filter 기능 버그를 W14(검증 Wave)까지 미루면, W9·W10에서 각 화면을 고치는 에이전트들이 **틀린 결과를 정상으로 보고 그 위에 디자인을 얹는다.** 그래서 공통 Filter 계약(W5) 직후, 화면 작업(W8~W10) **전에** 둔다.

---

## Product Identity + Hostname 런북 (지시 72·73)

### (a) 저장소 rename — 3분류

**분류 규칙**: 이 커밋 밖의 프로세스가 이 문자열을 읽는가? 배포를 가로질러 이걸 담은 무언가가 존속하는가? 둘 다 아니오 → **A**. 하나라도 예 → **B**. 그 읽는 주체가 우리 것이 아니면 → **C**.

**Class A — 순수 텍스트, 영역별 한 커밋**: UI 문구·`documentTitle.js`·메일 표시명·`README.md`·`PRODUCT.md`·`docs/*`·주석·Fixture 표시명·`seed_content.py`·**`ClovirTheme`/`createClovirTheme()` 90건**(내부 심볼, 기계적이지만 `theme.js`에 살아서 W1 창을 탄다)·**고아 자산 `app/static/img/clovirone-*.svg`+`clovirone-logo-white.png` → rename이 아니라 삭제**(참조 0, `assets.js`는 이미 `clovirassist-*`를 본다). git-tracked 번들의 문자열은 `npm run build`가 재생성하고 `check_bundle_fresh.py`가 강제.

**Class B — 런타임 결과 있음, 호환 창 필요**

| # | 대상 | 기법 |
|---|---|---|
| B1 | **세션 쿠키 `clovirone_session`** (`app/core/sessions.py:24`) | **read-both / write-new.** 새 이름 우선 읽고 legacy fallback, legacy로 통과하면 새 쿠키를 심고 `delete_cookie("clovirone_session")` — **강제 로그아웃 없는 사용자별 무음 회전.** 제거 시점: 절대 세션 수명 2회(8h) + 배포 1주기 뒤, `user_sessions where created_at < cutover`가 0일 때. 기존 테스트는 새 이름 단언 + **legacy가 아직 받아들여진다는 새 테스트** 추가 |
| B2 | **localStorage 키 7종 / 6파일** (`clovirone_theme`, `:<id>`, `_accent`, `_nav_collapsed`, `_login_welcome`, `_dismissed_status_notices_v1`) | boot 시 1회 migrate 후 새 이름만 읽기. `lib/storage-migrate.js`를 `applyTheme(initialTheme())`보다 **먼저** 실행. **같은 6줄을 `app/static/js/theme.js`에도 복제**해야 한다 — Jinja 로그인이 SPA보다 먼저 돌아 legacy 키를 다시 쓴다. **치명적 결합: `scripts/ui_qa/capture.py:87-99`가 `add_init_script`로 이 키들을 심는다. 창 동안 둘 다 심지 않으면 288페이지 전부 `theme_applied` 실패하고 그게 테마 버그처럼 보인다** |
| B3 | systemd 유닛 4종 | install-new → `daemon-reload` → `systemd-analyze verify` → 구 유닛 stop/disable → 신 유닛 enable/start → `is-active` ×4 확인 → 구 유닛 파일 rm → `daemon-reload`. 롤백은 0단계 백업에서 복원. 앱 쪽 하드코딩 목록(`actions_service.py:87` 등)은 `CLOVIR_UNIT_PREFIX` 파생 상수 하나로, legacy fallback 1릴리스 유지 |
| B4 | **시스템 사용자/그룹 `clovirone-web`** | **가장 위험 — UI 작업과 절대 묶지 않는 독립 단계, 전체 백업 후에만.** 신규 계정 생성 → `/etc`·`/var/lib`·DB·WAL `chown -R` → 4개 유닛 `User=`/`Group=` → `/etc/sudoers.d/*` → `daemon-reload`+restart → 4개 active & DB 쓰기 확인 → `userdel`. `MIGRATE_SYSTEM_USER=1` 가드 |
| B5 | 경로 `/etc`·`/var/lib`·`/var/backups`·nginx 로그·`/etc/ssl/clovirone` | 새 경로 생성 → `mv` → **구→신 심링크를 1릴리스 유지**(이전 패키지로 롤백해도 파일을 찾게). `TLS_CERT_PATH`·백업 cron·logrotate 갱신. **logrotate는 중복 항목이 생기면 전체가 실패하므로** 설치 스크립트의 "배포판 logrotate가 이미 `/var/log/nginx/*.log`를 덮는다" 처리를 깨지 않게 |
| B6 | nginx conf 파일명 | `sites-available`에 새 파일 → `ln -sf` → `nginx -t` → reload → 구 심링크·파일 제거. **둘 다 enable된 상태를 절대 만들지 않는다** — 같은 `server_name` 두 블록은 `conflicting server name` 경고와 함께 첫 번째가 조용히 이긴다 |
| B7 | 스크립트 5종 | `git mv` + 옛 이름에 deprecation 출력 후 `exec`하는 2줄 shim을 1릴리스(문서·cron·운영자 런북이 옛 이름을 참조) |
| B8 | 패키지 메타데이터 | `package.json` name, `site.webmanifest`의 `name`/`short_name`/**`id`**(설치된 PWA가 재설치를 물어본다 — 발견하지 말고 릴리스 노트에 적는다), favicon 파일명 |

**Class C — 바꾸지 않는다**: ① **DB 업무 데이터**(사용자 확정). 강제 수단 — Identity 검사는 git-tracked 소스/설정/fixture만 읽고, 이 프로그램의 어떤 Alembic 마이그레이션도 identity 목적으로 업무 테이블을 `UPDATE`하지 않는다는 리뷰 규칙 ② **`ClovirSM`**(고객 자체 시스템명, 7건) → 사유와 함께 allow-list ③ **n8n Webhook slug `clovirone-work-assistant`**(18건) — **외부 공유 n8n의 경로다. 우리 쪽을 먼저 바꾸면 연동이 즉시, 조용히 깨진다.** 처리: 이번 범위에서 rename 금지 / 모든 등장을 계약이 적힌 상수 하나로 승격(`N8N_WEBHOOK_SLUG = os.environ.get(..., "clovirone-work-assistant")  # 외부 n8n 경로 — 바꾸려면 n8n 워크플로를 먼저 바꾼다`) / env 설정화로 미래의 rename을 코드 변경이 아닌 설정 변경으로 / **그 한 파일에 한정한 allow-list** 등재라 다른 곳의 새 등장은 실패 / 나중에 바꾼다면 유일한 안전 순서는 **n8n에 새 경로 생성 → 상수 전환 → 실제 호출 end-to-end 확인 → 구 경로 삭제** ④ git history(범위 밖).

**강제 도구** — 신규 `scripts/check_product_identity.py`를 `static_checks.sh`에 연결. `git ls-files`를 훑어(`dist/`·`var/`·`.claude/worktrees/`의 낡은 사본 수십 개가 **구조적으로** 제외된다) `app/static/react/`(빌드 산출물)를 건너뛰고 allow-list 밖의 legacy 표기에서 실패한다. **Class B 항목은 만료일을 함께 적어** legacy 쿠키명·localStorage 키·유닛 fallback을 일정대로 제거하지 않으면 빌드가 빨개진다.
참고: `check_tenant_defaults.py`의 `SCAN_GLOBS`가 비재귀 `("scripts","*.py")`라 **`scripts/ui_qa/*.py`의 하드코딩된 `clovirone-ai.gooddi.lab` 12건이 지금 안 보인다.** 아래 6단계 후 재귀로 바꿔 구멍을 막는다.

### (b) Hostname / TLS — `clovirassist.gooddi.lab`을 정본으로

**0. 바꾸기 전에 진실을 기록** — `getent hosts`, `openssl s_client … | openssl x509 -noout -subject -issuer -dates -ext subjectAltName`, `nginx -T | grep -A3 server_name`, `systemctl is-active` ×4 → `docs/ui-renewal/evidence/w13-before.txt` (R-73의 "before" 증거).
**1. 백업** — `backup-*.sh` + nginx conf `.bak` + `/etc/…/tls` 사본.
**2. 이중 이름 인증서 발급** — 설치 스크립트의 기존 openssl 호출에 legacy alias를 더한다:
`SAN="DNS:$DNS_NAME,IP:$BIND_IP"; [ -n "$LEGACY_DNS_NAME" ] && SAN="DNS:$DNS_NAME,DNS:$LEGACY_DNS_NAME,IP:$BIND_IP"` — CN은 `clovirassist.gooddi.lab`. 파일명은 `clovirassist.gooddi.lab.{crt,key}`(`_resolve_tls_paths`가 cert 경로의 **stem**에서 key를 유도하므로 둘이 stem을 공유해야 한다). **디렉터리는 지금 위치에 둔다** — 경로 이전(B5)과 엉키지 않게. 설치는 런타임 관리 Action `cert.install`로(이미 `.staged` 후 교체하는 검증된 경로이고 root 소유 파일 손편집을 피한다).
**3. nginx가 두 이름을 서브** — 템플릿에 `__DNS_ALIASES__` 추가, `:80`·`:443` 모두 `server_name __DNS_NAME__ __DNS_ALIASES__;`, `ssl_certificate`를 새 쌍으로. `:80`의 `return 301 https://$host$request_uri`는 요청된 이름을 이미 보존한다. `nginx -t && systemctl reload`.
**4. `APP_BASE_URL`** — env에 새 값. `app/core/config.py`의 기본값은 `http://127.0.0.1:8080` 유지(`check_tenant_defaults.py`가 고객 호스트명을 금지하는 게 옳다). `git grep -n app_base_url`로 생성 절대 URL(알림 메일·Notion 역링크·공유·딥링크) 전수.
**5. Allowed host / Origin / Cookie** — 세션 쿠키는 `SameSite=Strict`에 `Domain` 미지정이라 **host-only**다. 즉 옛 이름에서 로그인해 있던 사용자는 새 이름에서 **한 번 다시 로그인해야 한다.** 이걸 `Domain=.gooddi.lab`으로 "고치지 않는다" — 그러면 공유 n8n을 포함한 도메인 전체 호스트에 세션 쿠키가 뿌려진다. 1회 재로그인을 문서화한다. WS/SSE는 이 앱이 폴링이라 별도 Origin이 없다 — 가정하지 말고 확인한다.
**6. QA 하네스 base URL** — 12개 모듈이 `BASE = "https://clovirone-ai.gooddi.lab"`를 하드코딩(+`ai_e2e.py:230` argparse 기본값). `scripts/ui_qa/config.py::DEFAULT_REMOTE_BASE = os.environ.get("CLOVIR_QA_BASE_URL", "https://clovirassist.gooddi.lab")` 하나로 교체. `run.py --base-url` 기본값은 로컬 유지. **그리고 QA 세션 캐시를 지운다** — `auth.py`가 재사용하는 `storage_state.json`은 옛 origin에 묶여 있어, cutover 후 `--rebuild-auth` 없이 돌리면 전 Route가 `/login`으로 튕겨 `auth_ok`가 288번 실패하고 그게 인증 회귀처럼 보인다.
**7. Health/테스트** — `verify_deploy.sh`·`validate-*.sh`·문서의 curl 대상. 설계상 옛 이름을 고정한 테스트 2개 갱신(`test_health_worker_hardening.py:130` commonName, `test_sysops_tls_paths.py:27-42` cert 경로). `test_deploy_wiring.py:135`의 "소스 기본값에 `gooddi.lab`이 새지 않는다" 단언은 **유지**하고 새 이름에서도 통과해야 한다.
**8. 검증** — `openssl s_client -servername clovirassist.gooddi.lab … -subject -dates -ext subjectAltName` / **`curl --resolve … --cacert … -w '%{ssl_verify_result}'`가 0** (`curl -k`는 아무것도 증명하지 않는다) / 옛 이름도 살아 있는지 / `curl -sSI http://…/ | grep -i location`으로 80→443이 이름을 보존하는지 / `nginx -T | grep -B2 -A2 server_name.*clovirassist`로 **두 이름이 한 server 블록**인지(중복 블록이면 첫 번째가 조용히 이긴다) / `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth --routes smoke --fail-on auth_ok theme_applied console_errors page_errors`. 출력은 `docs/ui-renewal/evidence/w13-{openssl,curl}.txt`로.
**9. 옛 이름 퇴역** — 사용자가 북마크/연동 의존 없음을 확인한 뒤에만: legacy `:443` 블록을 영구 리다이렉트로, SAN은 인증서 잔여 수명 동안 유지하고 다음 갱신에서 제거.
**롤백**: 9단계 전까지 옛 이름을 절대 제거하지 않으므로 모든 단계에서 안전. conf `.bak` 복원 → `nginx -t` → reload → 인증서/키 복원 → `APP_BASE_URL` 복원 → 앱 유닛 재시작 → 0단계 명령 재실행해 기록된 "before"와 일치 확인.

**sudo 취급**: 첫 특권 단계에서 사용자가 제공한 비밀번호를 `sudo -S`(stdin)로 **한 번만** 사용해 이 작업에 필요한 명령만 허용하는 scoped `sudoers.d` 항목을 설치하고, 이후는 비밀번호 없이 진행한다. 비밀번호를 명령행·로그·저장소·문서 어디에도 남기지 않는다(CLAUDE.md 불변규칙 3·4).

---

## 테스트 계획 (지시 84-8)

**변경 영역별 검증**(요약): Brand/Theme → `theme-contract.test.js` 재작성(역할별 Brand 색상 + AA 대비 유지) · `tokens-generated.test.js` 재생성 · `brand_presence` ≥5/7 · 4개 Accent × 2모드. Shell/Nav → `topbar-contract`·`sidebar-*`·`nav-*` 재작성, `user-segment-routes`·`settings-route-redirects`, 390/768/860 drawer 경계 + 3840, skip-link·`route-change-focus`. 공유 Layout → `kit.test.jsx`·`skeleton-shapes`·`density-contract` 재작성 + primitive별 대표 소비처. Search/Filter → `filter-bar-grid`·`datascreen-search`·신규 `entity-combobox`, URL state 생존(`users-url-state`·`saved-views`), Combobox ARIA 1.2 키보드, **필터가 scope를 넓히지 않음**(`check_scope_gates.py`). Table → `DataTable` 단위 + 0/1/100/1000행 + 760px 카드모드 경계 양쪽 + 4개 Assertion Gate. Empty/Feedback → 12개 상태 열거 + alert로 포커스 이동 + `mascot_visible_size`. 사용자 Workflow → 화면별 + `cross-screen-invalidation` + share-scope 부정 케이스 + `hostile_data.py`의 Long/Many. 관리자 → `admin-tab-groups`·`registry-*` + 탭 딥링크와 `?tab=` 보존 + `rbac-matrix` + 5역할 하네스. Identity → 신규 `storage-migrate.test.js` + 쿠키 테스트 갱신 + **legacy 수용 테스트 신설** + "옛 빌드에서 로그인 → 배포 → 새로고침 → 로그인 유지·테마 유지" E2E. Hostname/TLS → 위 8단계 명령 + 3개 테스트 갱신.

**주기**: focused test는 상시. Wave 종료마다 `bash scripts/run_full_regression.sh` + `cd frontend && npm test`(312파일) + runner 테스트. 전체 9뷰포트 × 2테마 하네스 실행은 W0·W8·W15 + 공유 파일 Wave 직후.

**설계상 깨질 테스트 — 삭제·약화가 아니라 재작성**
프런트 Contract: `theme-contract.test.js`(D-141 고정 — "chrome 은 발광하지 않는다"가 새 지시와 정면 충돌) · `tokens-generated.test.js`(**재생성, 손편집 금지**) · `density-contract.test.jsx`(`sx`에서 `gridTemplateColumns` 파싱 — 균등 격자가 내용 비례로 바뀌는 순간 깨진다) · `topbar-contract.test.jsx` · **`theme-link-contrast.test.js`(가장 취약한 종류 — 소스 텍스트를 정규식으로 매칭한다, 314·335줄)**.
`getComputedStyle` 사용 19파일이 최고 위험(`command-palette`·`sidebar-logo-center`·`sidebar-scroll-affordance`·`topbar-contract`·`chat-bubble`·`chat-card-chrome`·`chatpane`·`chatroom-scroll-layout`·`chatrooms-list-grid-rows`·`datascreen`·`llm-console`·`new-ticket-writing-aid-contrast`·`org-console`·`project-wbs-indent`·`scheduler-grid-rows`·`donut-empty-state-height`·`kit`·`ko-wordbreak`·`theme-link-contrast`).
Backend/배포: `test_auth_login.py:21`·`test_auth_sessions.py:32`(쿠키명) · `test_sysops_tls_paths.py:27-42` · `test_health_worker_hardening.py:130` · `test_deploy_wiring.py:135` · `test_sysops_hostname_fallback.py`.
확장(깨지지 않음): `test_ui_qa_route_registry_completeness.py`(UserRoutes + `<Navigate>` 분류 추가) · `test_ui_qa_harness_honesty.py` · `test_ui_qa_contrast.py`.

**재작성 규칙** — 허용 3가지: ① 기대값 변경(`toBe(6)`→`toBe(8)`, 단언은 살아남는다) ② **메커니즘 강화**(소스 텍스트 정규식 → 렌더 후 `getComputedStyle`. 엄격히 더 강하고 리팩터에 견딘다) ③ 고정된 구조를 그것이 지키던 **불변식**으로 교체("로고가 정확히 이 스타일을 갖는다" → "브랜드 마크의 광학 중심이 3가지 rail 폭 모두에서 rail 중심의 2px 이내"). **금지**: 파일 삭제 · `it.skip` · `toBe`→`toBeDefined/toBeTruthy` · 단언 제거 · 사유 없는 허용오차 확대.
강제: 신규 `scripts/check_test_strength.py` — 이번 작업에서 수정된 모든 테스트 파일의 `expect(`/`assert ` 개수를 `git show HEAD:<file>`과 비교해 **감소하면 실패**. 예외는 파일 헤더의 `qa-contract-change: <사유 ≥60자>`(기존 `clovi-allow-glyph` 관용과 같은 "이유를 적어라" 규약). 테스트 파일 삭제는 대체 파일을 명명하지 않으면 무조건 실패.

---

## Context 압축 복구 절차 (지시 83)

**압축 전** — `WORK_STATE.md`를 **덮어쓴다**(append 아님): `checkpoint_at` · `head`(+워킹트리 상태) · `wave`+`wave_goal` 한 문장 · **`build_index_sha256`**(`python -c "from scripts.ui_qa.capture import build_fingerprint; print(build_fingerprint()['index_sha256'])"` — **이게 닻이다.** 다음 세션 값이 다르면 여기 참조된 모든 QA 결과는 다른 번들 것이라 믿기 전에 재실행해야 한다) · `last_qa_label/results/fail_classes` · `coverage_gate` 판정과 시각 · 두 Artifact의 sha256 · `surfaces_total/done/open_findings_critical_high` · `## NOW`(편집 중 파일과 줄 범위, 절반 끝난 것, **끝낼 때 깨면 안 되는 불변식** — 신선한 에이전트가 diff로 복원할 수 없는 유일한 것) · `## NEXT`(문자 그대로의 명령, 순서대로) · `## BLOCKERS`(외부 원인만).
그런 다음 **세 Artifact를 함께 커밋**해 체크포인트의 해시가 워킹트리가 아니라 커밋에서 도달 가능하게 한다.

**압축 후 복구 순서**: ① `CLAUDE.md` §0~§2 ② `WORK_STATE.md` — **유일한 서사 원천**, 대화를 기억하려 하지 않는다 ③ **`python scripts/check_ui_renewal_coverage.py --stage wave` — 그 출력이 할 일 목록이다.** 소스에서 파생되므로 어떤 문서가 뭐라 주장하든 참이다 ④ `git status/diff/log`를 `CHECKPOINT.head`와 대조 ⑤ 빌드 지문 재계산 — 다르면 `npm run build` 후 마지막 QA 라벨을 재실행하기 전까지 캡처 기반 증거를 믿지 않는다 ⑥ 두 Artifact sha256 재계산 — 다르면 체크포인트가 낡은 것이니 **코드를 만지기 전에 WORK_STATE부터 정정** ⑦ `status != DONE && wave == CHECKPOINT.wave`인 Surface ⑧ 같은 조건의 요구사항 행 ⑨ 그제서야 `## NOW`가 지목한 소스를 연다 ⑩ `## NEXT`를 순서대로 실행.

**동점 규칙: WORK_STATE와 Gate가 다르면 Gate가 이긴다** — Gate는 소스를 읽고 WORK_STATE는 주장이다. WORK_STATE를 정정하고 그 정정을 커밋한 뒤 계속한다. 둘이 어긋난 채로 작업하지 않는다 — 이후 모든 판단이 거짓 그림 위에서 내려지기 때문이다.

---

## 검증 — 어떻게 끝났음을 증명하는가

**단계별 실행 명령**

| 목적 | 명령 |
|---|---|
| Frontend focused | `cd frontend && npx vitest run <경로…>` |
| Frontend 전체 (312파일) | `cd frontend && npm test` |
| Backend focused | `.venv/Scripts/python -m pytest <path-or-nodeid>` |
| Backend 전체 회귀 | `bash scripts/run_full_regression.sh` |
| Runner | `RUNNER_TOKEN=test .venv/Scripts/python -m pytest runner/claude-work-assistant/test_assistant.py` |
| Static + 모든 Gate | `bash scripts/static_checks.sh` |
| Coverage Gate | `.venv/Scripts/python scripts/check_ui_renewal_coverage.py --stage wave\|complete` |
| Build + 신선도 | `cd frontend && npm run build && .venv/Scripts/python scripts/check_bundle_fresh.py` |
| Token 드리프트 | `node scripts/generate_design_tokens.mjs --check` |
| 시각 QA (로컬) | `.venv/Scripts/python -m scripts.ui_qa.run --label <label> --routes all --fail-on <classes>` |
| 시각 QA (테스트 서버) | `… --base-url https://clovirassist.gooddi.lab --rebuild-auth` |
| 배포 | `ssh cloviradmin@10.100.64.71` → `sudo bash scripts/update-from-git.sh --ref <sha>` |
| TLS 검증 | `openssl s_client -connect 10.100.64.71:443 -servername clovirassist.gooddi.lab </dev/null \| openssl x509 -noout -subject -ext subjectAltName` + `curl --resolve … --cacert … -w '%{ssl_verify_result}'`(0이어야 함) |

**End-to-end 확인 흐름**(주요 Workflow마다): `Screen → User Action → Network Request → API → Backend → DB/Data → UI Result → 관련 화면 → Reload → Permission/RBAC`. 위험 Action은 실행 전 상태를 기록하고 검증 후 원상복구하며, 삭제는 실데이터가 아니라 테스트 Fixture로 한다(지시 68).

### 완료 조건 (지시 0-20 + CLAUDE.md §13 + R-96 강화)

**A. 디자인·범위 축** — 전 Route가 Coverage에 존재 · 전 Route Visual Audit 완료 · **161** 요구사항 전부 Matrix에 매핑 · UNKNOWN/TODO/NOT_AUDITED 0 · Critical/High Finding 0 · 일반 사용자 수동 동기화 제거 확인 · **Purple/Indigo가 Header/Nav/Primary/AI/Data Highlight에서 실제로 측정됨**(`brand_presence`) · Clovi 검수 PASS(`mascot_visible_size`) · 주요 Page Before/After 독립 Visual Review PASS · 거대 Blank 잔존 Route 0 · FHD/QHD/4K + Zoom 검증 · 401/403·Loading·Error·Permission·Long Text·Many Data 검증 · Frontend/Backend/Runner/Static/Build 회귀 PASS · **Coverage Gate `--stage complete` PASS** · 독립 Visual Reviewer PASS · 독립 Requirement Reviewer PASS · `https://clovirassist.gooddi.lab` 기준 Browser E2E PASS · **TLS CN/SAN 일치 + `ssl_verify_result=0`** · Product-owned Source/Config/Artifact에 Legacy Identity 0.

**B. 기능 정확성 축 (신규 — R-85~R-95)**

1. **Search/Filter 실제 데이터 정합성 PASS** — C7의 8단계 사슬이 전 Consumer에서 일치.
2. **Filter 단독/조합 조건 검증 PASS** — 각 축 단독 + 복합 조합 + Page 기본 Scope 결합이 Known Data와 일치.
3. **티켓 상태/우선순위 Inline Edit Browser E2E PASS** — 실제 클릭 → 저장 → 재조회 → 관련 화면 반영까지.
4. **Detail Metadata의 실제 데이터·긴 데이터·Responsive 검수 PASS** — 긴 프로젝트명 실데이터로 FHD/QHD/4K × Zoom.
5. **전체 주요 Interactive Function Functional Coverage 완료** — 27개 범주 중 각 화면에 실재하는 범주가 전부 Flow로 존재하고 검증됨.
6. **화면 간 Resource 및 Derived Metric 정합성 PASS** — 같은 Metric을 두 화면이 다른 값으로 보고하지 않음.
7. **Frontend State와 Backend 실제 상태 불일치 0**.
8. **죽은 Action 및 Broken Workflow Critical/High 0**.
9. **Race Condition·중복 요청 주요 Flow 검증 완료**.
10. **`FUNCTIONAL_COVERAGE.json`의 `NOT_AUDITED` 0** (`exists: true` Flow 기준).
11. **Pagination·Cache/Query Key·Back/Forward 일관성 PASS**.

**C. 판정 원칙** — `전체 테스트 PASS` · `API 200` · `화면 렌더 성공` · `Visual Audit PASS` **중 어느 하나만으로 기능 완료를 판단하지 않는다.** 네 가지는 서로 다른 것을 증명하며, 사용자가 겪은 Filter 오동작은 앞의 세 가지를 전부 통과한 상태에서 발생했다.

---

## 이번 세션에서 할 일 (R-97) — 계획과 인계 상태를 프로젝트에 기록하고 멈춘다

**제품 코드는 이번 세션에서 한 줄도 고치지 않는다.** 이번 세션의 산출물은 **다음 세션이 대화 Context 없이 이어받을 수 있는 상태**다. W0의 문서 산출물을 미리 만들어 두는 것이며, W0의 나머지(하네스 수정·Assertion 추가·Before 전량 캡처)는 다음 세션의 첫 작업이다.

**만들 파일**

| 경로 | 내용 |
|---|---|
| `docs/ui-renewal/PLAN.md` | 이 실행 계획 전문. 저장소 안의 정본 |
| `docs/ui-renewal/REQUIREMENT_MATRIX.md` | 161개 요구사항. 각 항목 9필드. 초기 `Status`는 `NOT_STARTED`, `Wave`·`Affected`·`Implementation`·`Verification`은 이 계획에서 유도해 채운다 |
| `docs/ui-renewal/ROUTE_COVERAGE.json` | `UserRoutes.jsx`·`AdminRoutes.jsx`·`TAB_GROUPS`·`TAB_DEFS`·`registry.js`·`routes.py`에서 파생한 전 Surface. 초기 `status`는 `NOT_AUDITED`, `wave` 배정 완료. **§Control Plane이 지적한 네 가지 부채(리다이렉트 4·미캡처 Route 2·탭 본문 4·`static_checks` 적색)를 Finding으로 등재한 상태로 시작** |
| `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` | 전 Surface × 실재하는 27개 범주의 Flow. 전부 `NOT_AUDITED`. **사용자가 겪은 티켓 Filter 건은 이미 알려진 `FAIL` Finding으로 등재** |
| `docs/ui-renewal/WORK_STATE.md` | CHECKPOINT / NOW / NEXT / BLOCKERS 4절. 기준 commit·Build Fingerprint·Artifact 해시·다음 실행 명령 포함 |
| `docs/ui-renewal/QA_SUPPRESSIONS.md` | 헤더와 규칙만, 행 0 |
| `scripts/check_ui_renewal_coverage.py` | Gate. **이번 세션에서는 `--stage plan` 경로를 동작 가능한 수준까지** 구현한다(구조 무결성 · Requirement 161 대조 · Wave 참조 · Artifact 파싱 · 빈 필드). `--stage wave/complete`의 C1~C14는 스켈레톤 + 명확한 `NOT_IMPLEMENTED` 종료로 두고 W0에서 완성한다 — 있는 척하는 Gate가 없는 Gate보다 나쁘다 |
| `docs/DECISIONS.md` (복구 후 추가) | 이번 Design Direction 전환을 **D-141 "계측 전면"을 대체하는 새 결정**으로 기록. 코드 주석이 D-141을 참조하고 있으므로 그 참조가 가리킬 곳이 있어야 한다 |

**함께 처리할 저장소 상태**: `docs/` 삭제 27건 중 **제품·운영 문서 9개 복구**(`ARCHITECTURE`·`CONSOLE_SCREENS`·`DECISIONS`·`KNOWN_LIMITATIONS`·`MAINTENANCE_PLAYBOOK`·`OPERATIONS`·`RUNBOOK`·`SECURITY`·`UX_WRITING`), **UI Renewal 기록 18건 삭제 확정 commit**. `scripts/check_traceability.py`는 이 세션에서 제거하지 않는다 — 교체 Gate가 `--stage wave`까지 완성되는 W0에서 함께 처리한다. 다만 `static_checks.sh`가 지금 적색이라는 사실을 WORK_STATE의 BLOCKERS가 아니라 **W0의 첫 NEXT 항목**으로 적는다(우리가 고칠 수 있으므로 외부 Blocker가 아니다).

**끝내기 전 검증**: `python scripts/check_ui_renewal_coverage.py --stage plan` 이 **통과**해야 한다 — 이름 없는 Wave 0 · 없는 Wave 참조 0 · 빈 필드 0 · 요구사항 161 전부 존재 · `R-64`/`R-65` 원형 보존 · 신규 요구가 `R-85` 이상 · 4개 Artifact 파싱 성공. 통과 후 커밋하고 **거기서 멈춘다.**

**다음 세션의 첫 5개 명령** (WORK_STATE의 `## NEXT`에 그대로 적는다)
1. `git log --oneline -3 && git status --short`
2. `.venv/Scripts/python scripts/check_ui_renewal_coverage.py --stage plan`
3. `bash scripts/static_checks.sh` — 적색 원인(`check_traceability.py`) 확인 후 교체 Gate로 대체
4. `.venv/Scripts/python -m scripts.ui_qa.run --list` — `routes.py`와 소스 Route 대조, 누락 6종 추가
5. Notion 사용자 매핑 수리 → `--label before-renewal` 전량 캡처

---

## 이 계획에서 명시적으로 하지 않는 것

- `design/baseline/preview-standalone.html`을 복원하거나 새로 쓰지 않는다(지시 64, 이미 이행됨).
- `~/Downloads/clovirone_demo_v15_product_refined_final.html`을 보지 않는다(사용자 확정).
- 실제 DB 업무 데이터(조직명·프로젝트명·티켓·문서·Notion 동기화분)를 바꾸지 않는다(사용자 확정).
- n8n Webhook slug를 우리 쪽에서 먼저 바꾸지 않는다(외부 공유 서비스).
- 사용자 Accent 기능을 제거하지 않는다 — Brand와 역할을 분리해 **보존하고 강화**한다.
- 대비 테스트를 약화하거나 테스트를 삭제해 초록을 만들지 않는다.
- 실시간 문서 Presence 같은 새 기능을 UI 리뉴얼에 몰래 끼워 넣지 않는다(요구 29는 이미 있는 낙관적 동시성의 UI 표현으로 해소).
- Sidebar 숫자를 줄이려고 RBAC를 왜곡하지 않는다(`/notion-mapping` 독립 유지).
- **기존 `R-64`·`R-65`를 새 요구사항으로 덮어쓰거나 재정의하지 않는다.** 보강 요구는 전부 `R-85` 이상의 새 번호다.
- **없는 기능을 검증하려고 새로 만들지 않는다**(R-92). Functional Coverage는 실재하는 기능만 대상으로 하고, 없으면 `exists: false` + 사유로 남긴다.
- 실시간 문서 Presence처럼 **새 기능**을 Inline Edit/동시성 작업에 묶어 끼워 넣지 않는다.
- **현재 렌더된 행이 우연히 같다는 이유로 Table Column을 지우지 않는다**(R-91) — 서버 페이징 화면에서 Layout이 흔들린다.
- **이번 세션에서 제품 코드를 구현하지 않는다.** 계획과 인계 상태 기록 + `--stage plan` Gate 통과까지만 하고 멈춘다(R-97).
