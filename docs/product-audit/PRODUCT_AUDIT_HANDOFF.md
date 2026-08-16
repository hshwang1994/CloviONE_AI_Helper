cycle_id=PA-20260816-120655-f103fb5b

# PRODUCT AUDIT — IMPLEMENTATION HANDOFF

<!-- HANDOFF-SUMMARY
cycle_id=PA-20260816-120655-f103fb5b
actionable_root_causes=13
redesign_root_causes=9
deferred_for_human_approval=0
-->

> 이 문서는 **구현 Phase(`autonomous_runner.ps1`)로 넘기는 계약**이다.
> `docs/BACKLOG.md`의 한 줄만 보고 구현하지 말고, 해당 `PA-RC-*` 블록 전체를 읽어라.
> 원본 증거는 `PRODUCT_AUDIT_FINDINGS.md`, 의도 근거는 `PRODUCT_AUDIT_FEATURE_CONTRACTS.md`.
> UI 계열 9건의 판정 근거와 Target Design은 `PRODUCT_AUDIT_DESIGN.md`가 정본이다.

## 이 Cycle(`PA-20260816-120655-f103fb5b`)이 넘기는 것

baseline `70e264bf`. 이 Cycle은 D-75가 신설한 **L축 Deep Design Audit**을 처음으로 수행했고,
그 결과 신규 Root Cause **9건**(`PA-RC-0016`~`0024`)을 추가했다. 앞선 Cycle이 남긴 4건
(`PA-RC-0012`~`0015`)은 **현재 HEAD에서 여전히 미해결**이므로 그대로 승계한다. 합계 **13건**.

| 그룹 | RC | 성격 |
|---|---|---|
| 구조가 할 일을 다른 것에 떠넘김 | `0016` 셸 배너 비용 · `0017` 관리자 IA 밀도 · `0022` 산문이 IA를 대신함 | **순서 의존** — 0016 → 0017 → 0022 |
| 위계 | `0018` 대시보드 카드 벽 · `0023` 동작 위계 규범 부재 | 0018의 완료 판정이 0023을 참조 |
| 어시스턴트 표면 | `0019` FAB이 본문 버튼을 가림 · `0020` 이름 4종·진입점 3개 | 0020이 0019를 함께 닫는다 |
| 독립 | `0021` 다크 테마 토큰 · `0024` 상세 기제 분열 | 순서 의존 없음 |
| 이전 Cycle 승계 | `0012` 제목 계층 · `0013` `/users` URL 상태 · `0014` 영문 422 · `0015` 배너 경과 단위 | 그대로 유효 |

**`0015`는 `0016`과 같은 배너를 건드린다.** 배너를 상태 칩으로 접는 작업(0016)이 문구 생성
지점(`app/observability/router.py`)을 바꾸지 않으므로 충돌하지 않지만, **0015를 먼저 처리하면
0016의 요약 칩이 이미 올바른 단위를 쓴다.** 그 순서를 권한다.

## 이전 Cycle(`PA-20260812-171558-56c5befa`) 잔여분 — **전부 닫혔다. 재확인함**

`IMPLEMENTATION_CONSUMED`의 기록을 그대로 믿지 않고 이번 Cycle이 현재 HEAD(`64ef571`)에서
각 항목을 **다시 측정**했다.

| 이전 RC | 이번 Cycle 재측정 | 판정 |
|---|---|---|
| `PA-RC-0001` 타이포 토큰 미소비 | `scripts/check_typography_literals.py` 존재하고 `static_checks.sh:150`에 배선됨. 실행 결과 `TYPOGRAPHY_LITERALS_OK` (예외 16종 등재) | ✅ 닫힘 |
| `PA-RC-0002` UX Writing 규칙 부재 | `docs/UX_WRITING.md`(7,428B) 존재. `scan_errcopy.py` 재실행 → **회복 절 비율 100%**, 진짜 막다른 길 **0건**(기준은 90%) | ✅ 닫힘 — 기준 초과 달성 |
| `PA-RC-0003` 저장소 위생 검사 공백 | `scripts/check_git_secrets.py` 존재하고 `static_checks.sh:79`에 배선됨 | ✅ 닫힘(검사 공백 기준). 검사가 잡아내는 `stash@{0}` 자격증명 **회전 자체는 여전히 미수행** — 내 권한 밖 외부 행위라 `REPORT` §7-B에 사실만 적는다 |

즉 **이 Handoff의 실행 대상은 이번 Cycle이 새로 찾은 3건**(`PA-RC-0012`·`PA-RC-0013`·`PA-RC-0014`)**이다.**

| 신규 RC | 한 줄 요약 | 성격 |
|---|---|---|
| `PA-RC-0012` | `variant="h6"`이 시각 선택이면서 DOM 구조까지 결정해 관리자 화면 5개가 `h1 → h6`으로 네 단계를 건너뛴다 | 접근성/의미 |
| `PA-RC-0013` | `/users`만 자기 목록 상태(검색·필터·페이지)를 URL에 싣지 않아 새로고침에 잃는다 | 기능 일관성 |
| `PA-RC-0014` | Pydantic 스키마 422가 영문 그대로 나오고 어느 필드인지도 표시되지 않는다 | UX Writing/접근성 |

**셋을 관통하는 모양**: 이 제품은 공유 인프라(`DataScreen`·`FormField`·생성된 `fieldLimits`)를
잘 만들어 두었고 그 경로는 전부 옳다. **틀어지는 곳은 언제나 그 인프라 밖에 있는 손으로 쓴
화면**이다. 구현 Phase는 세 건 모두 **새 메커니즘을 만들지 말고 이미 있는 것을 그 화면까지
넓히는 방향**으로 처리하라 — 각 블록의 `implementation_direction`이 그렇게 쓰여 있다.

<!-- PA-RC-BEGIN PA-RC-0012 -->
rc_id: PA-RC-0012
severity: Medium
priority: P2
confidence: Confirmed
problem: 화면의 **문서 제목 계층이 시각 스타일 API에 종속돼 있다.** MUI에서 `variant="h6"`은 "20px 굵은 글자"라는 시각 선택이면서 동시에 `<h6>` 엘리먼트를 결정한다. 이 저장소에는 그 둘을 분리하는 `variantMapping`이 **없어서**(전체 0건), 개발자가 시각적 이유로 `variant="h6"`을 고르면 문서 구조가 조용히 따라간다. 그 결과 손으로 쓴 관리자 화면 5개가 `h1` 바로 다음에 `h6`을 놓아 **네 단계를 건너뛴다** — `/system`·`/mail`·`/llm-console`·`/notion-console`·`/offboarding`. `/setup`은 `SetupWizard.jsx:97`이 `component="h3"`을 명시해 `h1 → h3`으로 두 단계를 건너뛴다. 추가로 `ui/BodyEditor.jsx:229`는 **사용자가 문서 본문에 넣은 `h1` 블록을 `<h6>`으로** 그린다(사용자 저작 콘텐츠의 의미가 바뀌는, 성격이 다른 사례). 그리고 이 계열의 재유입을 막는 장치가 **하나도 없다** — `scripts/static_checks.sh`에 heading 규칙이 0건이고 heading 순서를 보는 공용 테스트도 없다.
expected: 문서 제목은 건너뛰지 않고 순차적이어야 한다(`h1 → h2 → h3`). 시각적 크기와 문서 구조는 **독립적으로** 지정할 수 있어야 한다. 이 저장소는 이미 그 옳은 관용을 알고 있고 실제로 쓰고 있다 — `ui/adminKit.jsx:52`의 `<Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle }}>`가 정본이며, `variant="h6"` 47회 중 **27회는 이미 `component=`로 의미를 따로 지정**한다. 기대 동작은 외부에서 들여온 기준이 아니라 이 저장소가 스스로 보여 준 관용이다.
actual: 20회가 `component=` 없이 쓰여 `<h6>`이 그대로 나간다. 브라우저 실측(`probe_a11y.py` → `verify_a11y.py`)과 소스 추적이 1:1로 대응한다 — `LlmConsole.jsx`(201·238·332·357) · `NotionConsole.jsx`(153·316·353·380) · `MailStatus.jsx`(110·122·145) · `Offboarding.jsx`(259·343·442) · `SystemOps.jsx`(234·251·265) · `BodyEditor.jsx`(229) · `LoginHandoff.jsx`(137). 대조군으로 `DataScreen.jsx` 기반 화면은 이번 sweep 60라우트에서 전부 `h1 → h2`로 정상이다 — 즉 공유 셸을 거치는 경로는 이미 옳고, 손으로 쓴 화면만 갈라져 있다.
intent_evidence: ⑤ 서로 일치하는 구현 관용 — `ui/adminKit.jsx:52`·`ui/EditableBody.jsx:144,206`이 `component="h2" variant="h6"` 형태로 시각과 의미를 분리한다(27회). ④ 신뢰할 수 있는 테스트가 표현하는 계약 — `SEM-02`/`SEM-03`/`PA-F-031` 수정 배치가 `home.test.jsx`·`my-stats.test.jsx`·`datascreen.test.jsx` 등에 "h1 1개 + h2 N개"를 **명시적으로 못박는 회귀 테스트**를 남겼다. 즉 "제목 계층은 순차적이어야 한다"는 의도는 이미 테스트로 표현돼 있고, 이번 5개 화면이 그 계약의 사정권 밖이었을 뿐이다. ② `docs/BACKLOG.md`의 `SEM` 절이 접근성 시맨틱을 제품의 강점으로 명시하고 유지 대상으로 삼는다.
findings: PA-F-043, PA-F-047, PA-F-044(같은 프로브에서 나온 오탐 — 승격하지 않는 근거로 함께 읽을 것)
feature_contracts: 해당 없음 — 기능 계약이 아니라 전 화면 공통 표현/의미 계층이다. 어떤 Feature Contract의 입력·출력·상태 전이도 바뀌지 않는다.
routes: `/system` · `/mail` · `/llm-console` · `/notion-console` · `/offboarding` · `/setup` (직접 확인). 추가로 `BodyEditor`를 쓰는 문서·게시글 본문 렌더 경로 전체(`/team-docs/:id` · `/board/:id`), `LoginHandoff`가 뜨는 로그인 인계 화면.
frontend: `frontend/src/ui/theme.js`(`variantMapping` 부재 — 근본 처방 자리) · `frontend/src/screens/LlmConsole.jsx` · `NotionConsole.jsx` · `MailStatus.jsx` · `Offboarding.jsx` · `SystemOps.jsx` · `SetupWizard.jsx` · `frontend/src/ui/BodyEditor.jsx` · `frontend/src/app/LoginHandoff.jsx` · 정본 관용은 `frontend/src/ui/adminKit.jsx:52`
api: 해당 없음 — 네트워크 계약은 바뀌지 않는다. 렌더 결과의 DOM 태그만 바뀐다.
backend: 해당 없음 — 서버 코드와 무관하다. 서버 렌더 페이지(`app/templates_html/**`)는 이 RC의 SPA 범위 밖이며, 이번 Cycle은 그쪽 heading을 재지 않았다(`COVERAGE` M축에 미측정으로 남김).
data: 해당 없음 — DB/데이터 구조 변화 없음. 단 `BodyEditor`의 경우 **저장된 데이터는 그대로**이고(블록 `type: "h1"` 유지) 렌더 태그만 교정한다 — 데이터 마이그레이션을 하지 말 것.
rbac: 해당 없음 — 권한 경계와 무관하다.
integration: 해당 없음 — 외부 연동과 무관하다.
state_transition: 해당 없음 — 상태 전이와 무관하다.
user_impact: 스크린리더 사용자는 heading 목록으로 페이지를 훑는다. `h1` 다음이 `h6`이면 목차에서 네 단계가 비어 그 구역이 최상위인지 하위 절인지 판별할 수 없고, 구역 단위 점프(대부분의 스크린리더가 제공하는 `h2` 순회)가 아예 걸리지 않는다. 영향이 가장 큰 곳은 `/system`(서비스 재시작)과 `/offboarding`(퇴사 처리 실행)처럼 **되돌릴 수 없는 조작**을 담은 화면이다 — 어느 구역에 있는지 모른 채 버튼을 누르는 비용이 다른 화면보다 크다. 시각 사용자에게는 영향이 없고 기능도 정상이다(그래서 High가 아니라 Medium이다). `BodyEditor` 건은 영향 대상이 다르다 — 사용자가 쓴 문서의 제목 위계가 화면에서 뒤집힌다.
implementation_direction: (1) **먼저 `theme.js`에 `variantMapping`을 준다** — 이것이 근본 처방이다. `MuiTypography.defaultProps.variantMapping`에서 `sectionTitle`·`pageTitle` 같은 **의미 variant는 올바른 태그로**, 그리고 `h6`은 시각 전용임을 분명히 한다. 값을 눈대중으로 고르지 말고 기존 `FONT_SIZE.sectionTitle`(17px)/`pageTitle`(20px) 단계를 그대로 쓴다. (2) **`kit.jsx`에 `SectionTitle`류 의미 컴포넌트를 쓰게 한다** — 이미 `SectionTitle`이 존재하고 `component` prop을 받는다(`SEM-02` 배치가 `Home.jsx`·`MyStats.jsx`·`Profile.jsx`에서 이 경로로 해결했다). 5개 화면을 이 경로로 옮기면 개별 파일에 `component="h2"`를 흩뿌리는 것보다 재발이 적다. (3) 5개 화면의 17개 호출부를 `h2`로 교정한다. 각 화면은 `PageHeader`가 `h1`이므로 카드 제목은 전부 `h2`가 맞다. **단순 치환이 아니다** — `Offboarding.jsx:259`는 `{user.display_name}, {user.email}`이라 구역 제목이 아니라 선택된 대상 표시일 수 있으니 그 자리는 heading이 맞는지부터 판단할 것(heading이 아니라면 `component="p"`가 옳다). (4) `SetupWizard.jsx:97`은 `h3` → `h2`로 올린다(위에 h2가 없으므로 h3일 이유가 없다). (5) `BodyEditor.jsx:229`는 `variant="h6"`은 시각적으로 유지하되 `component="h2"`를 준다 — 저장 데이터는 건드리지 않는다. 본문 안 `h2`/`h3` 블록도 같은 규칙으로 한 단계씩 내려 순서를 유지할 것. (6) **재유입 방지 게이트를 넣는다** — `scripts/static_checks.sh`에 `component=` 없는 `variant="h[3-6]"`를 잡는 검사를 추가한다. 규칙만 두면 반드시 다시 갈라진다(이 저장소가 `PA-RC-0001`·`0002`·`0008`에서 세 번 겪은 패턴이고, `PA-RC-0001`의 `FONT_SIZE` 일급 API + `check_typography_literals.py` 조합이 실제로 성공한 처방이다 — **같은 모양으로 하라**). 예외가 정당한 자리(`LoginHandoff.jsx:137` 등)는 `check_typography_literals.py`가 이미 쓰는 **예외 등재 방식**을 그대로 재사용한다.
constraints: `ui/kit.jsx`의 **export 이름과 prop 시그니처를 바꾸지 말 것**(화면 다수가 의존, 파일 주석이 명시) · **시각적 크기를 바꾸지 말 것** — 이 RC는 의미 층위만 고친다. `fontSize`가 달라지면 `PA-RC-0001`이 세운 `FONT_SIZE` 스케일과 `check_typography_literals.py`를 건드리게 되고 회귀 범위가 폭발한다 · `BodyEditor`의 저장 데이터 형식(블록 `type`)을 바꾸지 말 것 · CLAUDE.md §3-6(서버 데이터 `innerHTML` 주입 금지) 유지 · `EmptyState`는 `role="heading" aria-level={2}`로 레벨을 **고정**하고 있어(`PA-F-031` 배치가 남긴 함정) DOM heading 순서 검사가 이것을 오탐으로 잡지 않게 할 것.
regression_risk: (a) 제목 태그가 바뀌면 **텍스트/역할로 조회하는 기존 테스트가 깨진다** — `getAllByRole("heading", {level: N})`을 쓰는 스위트가 이미 여럿 있다(`home.test.jsx`·`my-stats.test.jsx`·`assistant-panel.test.jsx`·`datascreen.test.jsx`·`chat-page-heading.test.jsx`). 바꾼 화면의 스위트를 반드시 함께 돌릴 것. (b) `h6` → `h2`는 MUI 기본 CSS 상속이 아니라 `variant`가 크기를 주므로 **시각 변화는 없어야 한다** — 만약 보이면 그 화면이 태그 기본 스타일에 의존하고 있었다는 뜻이므로 그 자체를 결함으로 기록할 것. (c) 범위는 프런트 전용이며 **백엔드 회귀는 불필요하다**. (d) 새 static check는 정당한 예외를 잡을 수 있으므로 켜기 전에 전수 목록을 먼저 뽑을 것.
acceptance_criteria: (1) `/system`·`/mail`·`/llm-console`·`/notion-console`·`/offboarding`·`/setup` 여섯 화면에서 heading 열이 건너뛰지 않는다 — 재측정은 `.venv/Scripts/python var/product-audit/probe_a11y.py` 이고 `headingSkips`가 **6개 화면 모두 빈 배열**이어야 한다. (2) 비테스트 소스에서 `component=` 없는 `variant="h[3-6]"`가 0건이거나, 남은 것마다 예외 목록에 사유와 함께 등재돼 있다. (3) `frontend/src/ui/theme.js`에 `variantMapping`이 존재하고, 의미 variant가 올바른 태그로 매핑된다. (4) `BodyEditor`가 그리는 본문 `h1` 블록이 `<h2>`로 렌더되고, 저장 데이터의 블록 `type`은 `"h1"` 그대로다. (5) `scripts/static_checks.sh`가 이 계열의 재유입을 실제로 잡는다 — **revert-to-verify**로 확인한다(위반 코드를 넣으면 실패하고 지우면 통과). (6) 프런트 전체 vitest green. (7) 여섯 화면의 **시각적 렌더가 변하지 않았다** — 글자 크기·굵기 측정값이 수정 전후 동일(같은 프로브의 `fontSizes` 비교).
required_tests: **신규**: heading 순서를 검사하는 공용 회귀 테스트 — 대표 화면들을 렌더해 heading 레벨 열이 1씩만 증가하는지 확인한다(화면별로 흩어 놓지 말고 한 파일에 모아 새 화면이 추가돼도 걸리게 할 것). **신규**: `static_checks.sh`의 새 heading 검사가 실제로 위반을 잡는지(revert-to-verify). **신규**: `BodyEditor`의 `h1` 블록이 `<h2>`로 렌더되고 저장 형식은 불변인지. **기존**: 수정한 5개 화면의 스위트 전부 + `getAllByRole("heading")`에 의존하는 기존 스위트(`home.test.jsx`·`my-stats.test.jsx`·`assistant-panel.test.jsx`·`datascreen.test.jsx`·`chat-page-heading.test.jsx`·`teamdoc.test.jsx`·`board-post-kind-crumb.test.jsx`·`ticket-detail.test.jsx`) · 프런트 전체 회귀.
qa_gaps: `docs/QA_COVERAGE.md`에 **heading 계층(문서 구조) 축이 없다.** 기존 `SEM` 축은 2026-08-08 8화면 실측 1회로 끝났고 그 뒤 추가된 화면은 아무도 재지 않았다 — 이번 5개 화면이 정확히 그 사각지대로 들어왔다. 화면별 시각·기능 검증 축은 있으나 "이 화면의 제목 열이 건너뛰지 않는가"를 **모든 화면에 대해 반복 측정**하는 칸이 없다. 이 축을 추가하고 `probe_a11y.py`를 그 축의 재측정 수단으로 등재할 것.
quality_rubric: `ui-ux-pro-max` — 이번 Cycle에서 **실제로 호출**했다(`.claude/skills/ui-ux-pro-max/scripts/search.py`). `--domain ux`의 **Heading Hierarchy** 항목: *"Screen readers use headings for navigation. Do: use sequential heading levels h1-h6. Don't: skip heading levels **or misuse for styling**."*(Severity Medium) — 이 규칙이 이 결함의 실패 모드를 이름 그대로 지목한다("스타일 목적의 heading 오용"). `--domain web` 및 `--stack react`의 **Use semantic HTML before ARIA**(Severity **High**) — 의미에 맞는 엘리먼트를 먼저 고르고 ARIA로 때우지 말라는 것으로, `aria-level`을 덧붙이는 우회가 아니라 태그 자체를 고치라는 근거다. 추가로 이 Audit 프롬프트 6절 내장 rubric **3)**(정보 위계가 3단계 이내로 읽히는가) · **4)**(같은 의미가 같은 component/pattern으로 표현되는가 — `DataScreen` 경로는 h2인데 손으로 쓴 화면은 h6인 것이 정확히 이 위반이다). 구현 Phase는 개별 화면 적용 시 같은 `ui-ux-pro-max` 항목으로 재확인할 것.
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-043`·`PA-F-044`·`PA-F-047` 절 · 브라우저 실측 `var/product-audit/probe_a11y.json`(59라우트 heading outline)과 `var/product-audit/verify_a11y.json`(DOM 원본 확인) · 스캐너 `var/product-audit/probe_a11y.py`·`verify_a11y.py` · `frontend/src/ui/adminKit.jsx:52`(정본 관용) · `frontend/src/ui/theme.js:57-62,300`(`variantMapping` 부재) · `frontend/src/screens/SetupWizard.jsx:97` · `frontend/src/ui/BodyEditor.jsx:229` · 대조군 `var/product-audit/sweep_all.json`(`DataScreen` 화면은 전부 h1→h2)
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0013 -->
rc_id: PA-RC-0013
severity: Medium
priority: P2
confidence: Confirmed
problem: **`/users`만 자기 목록 상태를 URL에 싣지 않는다.** 이 제품의 목록 화면은 검색·필터·페이지를 URL 해시에 실어 새로고침과 공유에 견디는 것이 확립된 관용이다 — 실측으로 `/team-docs`·`/board`·`/team-tickets`(전부 손으로 쓴 화면)가 `#/...?q=a`를 만들고 새로고침 후 복원되며, 공유 셸 `DataScreen`도 `#/audit?page=2`로 같은 일을 한다. `/users`만 예외다: 「다음」을 눌러 2페이지(20행→1행)로 가도 hash가 `#/users` 그대로이고 새로고침하면 1페이지로 돌아간다. 검색도 20행→3행으로 걸리지만 hash는 변하지 않고 새로고침하면 입력칸이 비며 전체 목록으로 돌아간다. 원인은 **단방향 URL 상태**다 — `Users.jsx`는 `useSearchParams`를 쓰지만(198행) `q`(199·227행)와 `department_id`(208·228행)를 **읽기만** 하고 되쓰지 않으며, `page`(245행)·`roleFilter`(200)·`activeFilter`(201)·`lockedFilter`(204)·`showArchived`(205)는 URL과 아예 무관한 `useState`다. 유일한 `setSearchParams`(242행)는 `id` 파라미터를 지우는 용도다.
expected: 목록 화면의 검색·필터·페이지 상태는 URL에 실려 (a) 새로고침 후 복원되고 (b) 링크로 공유 가능해야 한다. 이것은 외부에서 들여온 기준이 아니라 **이 저장소가 네 화면에서 이미 지키고 있는 관용**이다. 특히 `DataScreen.jsx`는 50행에서 hash를 읽고 462-464행에서 `history.replaceState`로 되써 양방향을 완성한다.
actual: `/users`는 링크를 **받을 수는 있으나 만들지 못한다.** 다른 화면이 `#/users?q=...&department_id=...`로 걸어 오는 딥링크는 읽기 절반이 있어 동작한다. 그래서 이 결함은 "딥링크가 없다"가 아니라 **"절반만 있다"** 이고, 기능이 있는 것처럼 보이기 때문에 더 함정이다.
intent_evidence: ⑤ 서로 일치하는 구현 관용 — `/team-docs`·`/board`·`/team-tickets`·`/audit` 네 화면이 실측으로 같은 동작을 한다(`var/product-audit/probe_deeplink2.json`). ② `docs/BACKLOG.md`의 `USE-08`이 "저장된 뷰는 필터를 URL에 싣고"를 제품의 잘 만든 기능으로 서술한다. ⑥ `DataScreen.jsx:462-464`의 코드와 주석이 딥링크 지원을 명시적 목적으로 밝힌다. ④ `datascreen.test.jsx`가 마운트 시 `window.location.hash`를 읽는 계약을 테스트로 고정하고 있다(`SEM-02` 배치 기록에 그 사실이 남아 있다).
findings: PA-F-048, PA-F-051(같은 화면의 인접 관측 — 정렬 부재. 등급 보류이므로 이 RC의 필수 범위는 아니다)
feature_contracts: 해당 없음 — 사용자 관리 기능의 입력·출력·권한 계약은 바뀌지 않는다. 바뀌는 것은 화면 상태의 표현 위치(React state → URL)뿐이다.
routes: `/users` (단독). 대조군으로 동작을 맞출 기준 화면은 `/team-docs`·`/board`·`/team-tickets`·`/audit`.
frontend: `frontend/src/screens/Users.jsx`(198·199·200·201·204·205·208·227·228·242·245행) · 참조 구현은 `frontend/src/screens/DataScreen.jsx`(50·411·418·462-464행) · 보조로 `frontend/src/screens/TeamDocs.jsx`·`Board.jsx`(손으로 쓴 화면이면서 올바르게 하는 예)
api: 해당 없음 — `/api/admin/users` 호출 파라미터는 이미 이 상태들로부터 만들어진다. 네트워크 계약 변화 없음.
backend: 해당 없음 — 서버 코드와 무관하다.
data: 해당 없음 — DB/데이터 구조 변화 없음.
rbac: 해당 없음 — 권한 경계와 무관하다. 단 공유된 URL을 여는 사람의 권한은 서버가 그대로 판정하므로(기존 게이트 유지) 필터가 URL에 실려도 권한 우회가 생기지 않는다는 점을 구현 시 확인할 것.
integration: 해당 없음 — 외부 연동과 무관하다.
state_transition: 해당 없음 — 도메인 상태 전이와 무관하다. 화면 로컬 상태의 저장 위치만 바뀐다.
user_impact: `/users`는 관리자가 가장 자주 쓰는 화면이고 필터가 5종(역할·활성·잠김·부서·보관)이다. 필터를 걸어 대상을 찾고 → 상세를 열고 → 새로고침하거나 뒤로 오면 **조건을 처음부터 다시 걸어야 한다.** 동료에게 "이 조건으로 걸린 사람들"을 URL로 보낼 수도 없다. 데이터 손실이나 권한 문제는 없고 순수한 업무 흐름 마찰이다 — 그래서 High가 아니라 Medium이다.
implementation_direction: (1) **새 메커니즘을 만들지 마라.** `DataScreen.jsx`가 이미 `parseView`/`withHashQuery`/`hashQuery` + `history.replaceState` 조합으로 이 문제를 풀어 두었다. 그 헬퍼를 공용으로 끌어올려 `Users.jsx`가 같은 것을 쓰게 하는 것이 가장 작은 변경이고, 다음에 같은 화면이 또 생겨도 재사용된다. `TeamDocs`/`Board`가 쓰는 방식도 함께 보고 **셋 중 이미 가장 널리 쓰이는 하나로 수렴**시킬 것 — 네 번째 방식을 새로 만들면 이 저장소가 반복해 온 분기 패턴이 그대로 재현된다. (2) `q`와 `department_id`는 **읽기가 이미 있으므로 쓰기만 붙이면 된다**(227·228행의 동기화 `useEffect`와 충돌하지 않게 할 것 — 220-224행 주석이 무한 루프를 피하려고 `searchParams.toString()`을 key로 쓰는 이유를 이미 설명한다. 그 주석을 반드시 읽고 같은 함정을 피할 것). (3) `page`·`roleFilter`·`activeFilter`·`lockedFilter`·`showArchived`를 URL 파라미터로 승격한다. **기본값은 URL에 쓰지 마라** — 빈 필터까지 실으면 주소가 지저분해지고 `DataScreen`의 기존 동작과도 어긋난다. (4) `history.replaceState`를 쓰고 `pushState`를 쓰지 마라 — 필터를 한 글자씩 고칠 때마다 뒤로가기 이력이 쌓이면 뒤로가기가 망가진다(`DataScreen`이 `replaceState`를 고른 이유가 그것이다). (5) `id` 파라미터를 지우는 기존 동작(242행)이 새 파라미터들을 함께 날리지 않는지 확인할 것.
constraints: `Users.jsx`의 기존 인바운드 딥링크 계약(`?q=`·`?department_id=`·`?id=`)을 **깨지 말 것** — 다른 화면이 이 주소로 걸어 온다(`registry/org.js`의 부서→사용자 이동 등). CLAUDE.md §3-5(권한 판단은 서버가 정본) 유지 — 필터가 URL에 실린다고 클라이언트 필터를 신뢰하지 말 것. 220-224행의 무한 루프 회피 주석이 설명하는 함정을 재도입하지 말 것. `useSearchParams`는 HashRouter 아래에서 hash 내부 쿼리를 다루므로 `window.location.search`와 혼동하지 말 것.
regression_risk: (a) URL 동기화는 **렌더 루프를 만들기 쉽다** — `searchParams` 변경 → state 변경 → `setSearchParams` → 무한 반복. 이 파일은 이미 그 함정을 한 번 만났고(220-224행 주석) 같은 실수를 반복할 위험이 가장 크다. (b) 기존 인바운드 딥링크를 쓰는 화면이 깨질 수 있다 — 부서/조직 콘솔에서 사용자로 넘어오는 경로를 반드시 함께 확인할 것. (c) `users*.test.jsx` 계열이 초기 URL 상태를 가정하고 있으면 깨진다. `DataScreen` 배치가 남긴 교훈대로 **테스트 파일 전역에서 `window.location.hash`를 초기화**하지 않으면 한 테스트의 필터가 다음 테스트로 샌다(실제로 `datascreen.test.jsx`에서 발생했던 순서 의존 결함이다). (d) 범위는 프런트 전용, 백엔드 회귀 불필요.
acceptance_criteria: (1) `/users`에서 검색어를 넣으면 hash가 `#/users?q=...` 형태로 바뀐다. (2) 필터(역할·활성·잠김·부서·보관)와 페이지를 바꾸면 각각 URL에 반영된다. (3) 그 상태에서 **새로고침하면 목록이 그대로 복원된다** — 재측정은 `.venv/Scripts/python var/product-audit/probe_interact.py` 이고 `pagination_reload.page_restored`와 `search_reload.rows_restored`가 **둘 다 true**여야 한다. (4) 그 URL을 새 탭에 붙여넣으면 같은 목록이 나온다. (5) 기존 인바운드 딥링크(`?q=`·`?department_id=`·`?id=`)가 여전히 동작한다. (6) 필터를 여러 번 바꿔도 **뒤로가기 한 번에 이전 화면으로 나간다**(이력이 쌓이지 않는다). (7) 기본값(빈 필터)은 URL에 나타나지 않는다. (8) 프런트 전체 vitest green.
required_tests: **신규**: `/users`의 검색·필터·페이지가 URL에 반영되는지, 그리고 그 URL로 마운트하면 상태가 복원되는지(양방향 각각). **신규**: 필터를 연속 변경해도 history 항목이 늘지 않는지(`replaceState` 사용 확인) — 이것이 (6)의 회귀 방어다. **신규**: 기존 인바운드 딥링크 3종이 여전히 동작하는지(회귀). **기존**: `users*.test.jsx` 전부 + `users-bulk.test.jsx` · 부서/조직에서 사용자로 넘어가는 크로스링크 테스트 · 프런트 전체 회귀. 모든 신규 테스트는 파일 전역 `beforeEach`에서 `window.location.hash = ""`로 초기화할 것.
qa_gaps: `docs/QA_COVERAGE.md`에 **"목록 상태가 새로고침·공유에 견디는가" 축이 없다.** 이 제품은 목록 화면이 20개가 넘는데 검증 축은 화면별 렌더·기능 중심이고, "필터를 걸고 F5를 눌렀을 때"를 모든 목록 화면에 대해 반복 측정하는 칸이 없다. 그래서 네 화면이 올바르게 하고 한 화면이 빠진 상태를 아무도 못 봤다. 이 축을 추가하고 `probe_deeplink2.py`를 재측정 수단으로 등재할 것.
quality_rubric: 이 Audit 프롬프트 6절 내장 rubric **4)** — *"같은 의미가 같은 component/pattern으로 표현되는가(다르면 Root Cause 후보)"*. 판정은 미적 판단이 아니라 **동일 제품 내 5개 화면의 실동작 대조**로 했고, 기준은 외부 표준이 아니라 이 저장소 자신의 관용이다. `ui-ux-pro-max`는 이 RC에 **적용하지 않았다** — 이 결함은 시각 품질이 아니라 상태 보존 동작이고, 그 도메인의 규칙(색·타이포·레이아웃·접근성)이 판정에 기여하지 않는다. 억지로 갖다 붙이지 않는다.
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-048` 절 · `var/product-audit/probe_interact.json`(`/users` 페이지네이션·검색 실조작) · `var/product-audit/probe_deeplink.json`(`/users` vs `/audit` 대조) · `var/product-audit/probe_deeplink2.json`(`/team-docs`·`/board`·`/team-tickets` 대조군 3건) · 스캐너 `probe_interact.py`·`probe_deeplink.py`·`probe_deeplink2.py` · `frontend/src/screens/Users.jsx:198-245` · `frontend/src/screens/DataScreen.jsx:50,462-464`
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0014 -->
rc_id: PA-RC-0014
severity: Medium
priority: P2
confidence: Confirmed
problem: **스키마 검증 실패가 영문 그대로 사용자에게 나온다.** `/users` 「사용자 추가」에서 이름을 500자(서버 상한 120)로 제출하면 화면에 `Invalid request data String should have at most 120 characters` 가 뜬다 — 한국어 제품에 영어 문장이고, `aria-invalid`가 붙은 필드가 **0개**라 8개 필드 중 어디가 문제인지 알 수 없다. 원인은 두 겹이다. (1) `app/core/errors.py:259,285`의 두 validation 핸들러가 `message="Invalid request data"`를 **영문 상수로 하드코딩**하고 `details[].msg`에 Pydantic의 영어 문구를 그대로 싣는다(한국어 매핑이 저장소 전체에 없다). (2) `PA-04`/`PA-RC-0005`가 등록 화면 13개에 `maxLength`를 배선해 **사용자가 스키마 상한에 도달하는 것 자체를 막아** 이 영문 문구를 가려 왔는데, `frontend/src/generated/fieldLimits.json`에 `users` 키가 없고(생성기가 registry 화면만 훑는다) `Users.jsx`·`Offboarding.jsx`에는 `maxLength`가 **0건**이라 그 가림막이 없다. 즉 영문 문구는 줄곧 있었고 가림막이 없는 화면에서 원래 모습이 드러난다.
expected: 검증 실패는 **해당 필드 옆에 한국어 인라인 오류**로 표시되어야 하고, 스크린리더가 필드 이름과 오류를 함께 읽도록 프로그래밍적으로 연결(`aria-invalid` + `aria-describedby`)되어야 한다. 문구는 `[필드] [구체적 요건]` 형태여야 한다(예: "이름은 120자까지 입력할 수 있습니다"). 이 기대는 이 저장소가 이미 세운 기준이기도 하다 — `PA-RC-0002`가 실패 문구의 회복 절 비율을 100%로 끌어올렸고(`scan_errcopy.py` 재실행으로 이번 Cycle에 확인), `app/auth/change_password.js:492-501` 주석이 *"RequestValidationError 핸들러는 영어 문구를 그대로 싣는다… 서버 메시지를 믿지 않고 정적 한국어로 대체한다"* 고 **이미 같은 처방을 적어 두었다**(그 판단이 React SPA로 전파되지 않았을 뿐이다).
actual: 영문 봉투 문구와 영문 Pydantic 문구가 이어 붙어 한 줄로 나온다. 필드 연결이 없다(`aria-invalid` 0개). 다만 서버는 정확히 `422`로 거절했고 계정을 **만들지 않았으며**(CLI `show`로 확인) 제출값을 응답에 되돌려주지 않았다 — 데이터 경계와 값 유출 방지는 정상이다. 사용자가 입력한 500자도 폼에 남아 다시 입력할 필요는 없다.
intent_evidence: ② `app/auth/change_password.js:492-501` 주석이 영문 문구 문제와 그 처방("정적 한국어로 대체")을 명시한다 — 서버 렌더 경로에는 이미 적용돼 있고 SPA에만 없다. ② `docs/UX_WRITING.md`(`PA-RC-0002` 산출물)가 오류 3요소 패턴을 제품 규칙으로 정한다. ⑤ 등록 화면 13개가 `maxLength`로 같은 문제를 회피하는 구현 관용. ② `docs/BACKLOG.md`의 `PA-04` 본문이 *"남은 범위: `Users.jsx`(공용 FormModal/FormField를 안 타는 손수 제작 화면, 별도 처리 필요)"* 라고 **이 잔여를 스스로 지목**한다.
findings: PA-F-054, PA-F-055(같은 폼의 중복 경로가 한국어로 잘 나온다는 대조 증거 — 영문 문제가 스키마 계층에 한정됨을 확증하고, 그 좋은 문구조차 aria-invalid가 0이라 필드 연결 결여는 더 넓다는 것도 보인다)
feature_contracts: 해당 없음 — 특정 기능 계약이 아니라 전 폼 공통의 오류 표현 계층이다. 검증 규칙 자체(상한 120 등)는 하나도 바뀌지 않는다.
routes: `/users`(직접 확인) · `/offboarding`(`maxLength` 0건, 같은 처지) · 그리고 스키마 계층 422가 발생할 수 있는 **모든 폼 경로** — 영문 핸들러가 전역이므로 등록 화면 13개도 `maxLength`로 못 막는 검증(형식·enum·필수·상호 의존 규칙)에서는 같은 문구를 낸다.
frontend: `frontend/src/lib/api.js:74-86`(봉투 문구 + `details[].msg` 결합 지점 — `UX-40`이 만든 곳) · `frontend/src/screens/Users.jsx`(폼 필드에 `maxLength` 0건) · `frontend/src/screens/Offboarding.jsx` · `frontend/src/ui/kit.jsx:783,880`(`FormField`가 `maxLength`를 이미 수용한다 — 재사용할 것) · `frontend/src/lib/fieldLimits.js` · `frontend/src/generated/fieldLimits.json`(`users` 키 없음)
api: `POST /api/admin/users`(재현 경로). 응답 계약 자체는 유지한다 — `error.code`·`error.details[].loc` 구조를 바꾸지 말고 사람이 읽는 문구만 한국어화한다.
backend: `app/core/errors.py:247-288`(두 validation 핸들러) · `app/core/field_limits.py`(`FORM_SCHEMAS` — registry key → 스키마 매핑, 여기에 `users`가 없다) · `scripts/generate_field_limits.py` · `scripts/check_field_limits_fresh.py`
data: 해당 없음 — DB/데이터 구조 변화 없음. 서버 검증 규칙과 상한 값도 그대로 둔다(문구와 전달 방식만 바꾼다).
rbac: 해당 없음 — 권한 경계와 무관하다. 오류 문구를 한국어화할 때 **권한 관련 실패에 내부 정보를 덧붙이지 말 것**(현재도 안 한다).
integration: 해당 없음 — 외부 연동과 무관하다.
state_transition: 해당 없음 — 상태 전이와 무관하다.
user_impact: 관리자가 8개 필드짜리 폼에서 영어 한 줄을 받고 **어느 칸이 문제인지 모른 채** 추측해야 한다. 한국어 제품에서 영어 오류는 읽히지 않고, 필드 연결이 없어 스크린리더 사용자는 오류와 필드를 연결할 방법이 아예 없다. `PA-RC-0002`가 회복 절 100%를 달성한 뒤에도 **이 경로만 그 기준 밖**이다. 데이터 손실은 없다(입력값이 폼에 남는다).
implementation_direction: (1) **서버에서 한국어로 만든다** — `app/core/errors.py`의 두 핸들러가 쓰는 `message="Invalid request data"`를 한국어로 바꾸고, Pydantic `err["type"]`(`string_too_long`·`missing`·`value_error` 등 안정된 식별자)을 한국어 문구로 매핑하는 표를 둔다. **`msg` 문자열을 파싱하지 마라** — Pydantic 버전이 올라가면 문구가 바뀐다. `type` + `ctx`(예: `max_length`)로 만들 것. `loc`는 이미 필드를 가리키므로 그대로 유지한다. (2) **필드에 연결한다** — `details[].loc`의 마지막 요소가 필드명이므로, 폼이 그것으로 해당 입력에 `aria-invalid="true"`와 `aria-describedby`를 붙이게 한다. `kit.jsx`의 `FormModal`이 이미 `details`를 다루던 코드 경로가 있었으므로(그 결합은 `UX-40`이 `lib/api.js`로 옮겼다) **결합된 문자열이 아니라 구조화된 `details`를 폼까지 전달**하는 길을 복원해야 한다 — `lib/api.js`가 `err.message`만이 아니라 `err.details`도 함께 실어 보내면 기존 130여 호출부는 그대로 두고 폼만 추가로 소비할 수 있다. (3) **`/users`·`/offboarding`을 `maxLength` 경로에 넣는다** — `app/core/field_limits.py`의 `FORM_SCHEMAS`에 `users` 스키마를 추가하면 생성기·드리프트 검사·`FormField`가 이미 있으므로 배선만 하면 된다(`PA-04`가 만든 기계를 재사용하는 것이지 새로 만드는 것이 아니다). `Users.jsx`가 공용 `FormField`를 안 쓰므로 그 폼이 `maxLengthFor("users", ...)`를 읽게 하거나 공용 폼으로 옮긴다. (4) **`PA-04` 행의 자기모순을 정정한다** — 본문이 "남은 범위: Users.jsx"라고 적는데 상태는 완료다. 이 RC가 그 잔여를 닫으면 그때 완료로 만든다.
constraints: 검증 규칙과 상한 값을 바꾸지 말 것 — 이 RC는 **표현 계층만** 고친다(상한을 늘려 오류를 없애는 것은 금지). `errors.py:252` 주석의 원칙 **"never echo submitted values back"** 을 반드시 유지할 것 — 한국어 문구를 만들면서 제출값을 문구에 끼워 넣지 마라(CLAUDE.md §3-3). `error.code`·`details[].loc` 등 기계가 읽는 응답 구조를 바꾸지 말 것(`UX-40`이 만든 결합 로직과 그 회귀 테스트 `api.test.js` 3건이 의존한다). CLAUDE.md §3-1(sync 일관성) 유지 — 핸들러는 기존 형태를 따른다. `docs/UX_WRITING.md`의 종결·표준 동사 규칙을 따르고, `static_checks.sh`의 문구 린트를 통과할 것.
regression_risk: (a) `lib/api.js`는 **저장소에서 가장 넓게 공유되는 계층**이다 — `UX-40` 수정 때 프런트 전체(221파일/1510건)를 돌린 이유가 그것이다. `err.message` 형식이 바뀌면 문구를 문자열로 조회하는 테스트가 깨진다. (b) `api.test.js`의 기존 3건(details 포함/객체배열 안전성/details 없을 때 무변화)이 직접 걸린다. (c) 백엔드 오류 문구를 바꾸면 그 문구를 기대하는 백엔드 테스트가 깨진다 — `tests/` 전체에서 `Invalid request data`를 찾아 함께 갱신할 것. (d) `FORM_SCHEMAS`에 `users`를 추가하면 `check_field_limits_fresh.py`가 즉시 드리프트를 보고하므로 생성 파일도 함께 갱신해야 한다(그 검사가 `static_checks.sh`에 배선돼 있다). (e) 범위는 프런트+백엔드 양쪽이며 이 Cycle의 다른 두 RC보다 회귀 반경이 넓다.
acceptance_criteria: (1) `/users`에서 이름 500자를 제출하면 **한국어** 오류가 나온다 — 재현은 `.venv/Scripts/python var/product-audit/probe_limits.py` 이고 `result.messages`에 영문 `Invalid request data` 와 `String should have at most` 가 **둘 다 없어야** 한다. (2) 같은 실험에서 `result.aria_invalid >= 1` 이고, 문제 필드가 `aria-describedby`로 오류 문구와 연결된다. (3) `/users` 폼 필드가 서버 상한과 같은 `maxLength`를 갖는다 — 같은 프로브의 `users_form.fields[].maxLength`가 이메일 255·이름 120이어야 한다(현재 전부 `-1`). (4) `Offboarding.jsx`도 같은 처리를 받는다. (5) Pydantic 문구 매핑이 `msg` 문자열 파싱이 아니라 `err["type"]` 기반이다. (6) 오류 응답에 제출값이 여전히 들어가지 않는다(revert-to-verify로 확인). (7) `scripts/check_field_limits_fresh.py` green, `static_checks.sh` 전체 green. (8) 프런트 전체 vitest green + 백엔드 관련 스위트 green.
required_tests: **신규**: 스키마 위반 422가 한국어 문구를 반환하는지(백엔드 단위 — `string_too_long`·`missing` 최소 2종). **신규**: 오류 응답에 제출값이 포함되지 않는지(회귀 — 기존 원칙을 못박는다). **신규**: `/users` 폼이 상한 초과 입력에서 `aria-invalid`와 `aria-describedby`를 붙이는지(프런트). **신규**: `users` 필드 상한이 `fieldLimits.json`에 생성되고 `check_field_limits_fresh.py`가 드리프트를 잡는지(revert-to-verify). **기존**: `frontend/src/lib/api.test.js` 3건 · `tests/` 중 `Invalid request data`를 문자열로 기대하는 것 전수 · 프런트 전체 회귀(`lib/api.js`가 공유 계층이라 필수).
qa_gaps: `docs/QA_COVERAGE.md`에 **"검증 실패 시 사용자가 무엇을 보는가" 축이 없다.** 화면별 렌더·기능 축은 있으나 상한 초과·형식 오류를 실제로 제출해 보는 칸이 없어서, 영문 문구가 두 Cycle의 QA를 전부 통과했다. 최소 두 축을 추가할 것: `스키마 위반 오류가 한국어인가` · `오류가 해당 필드에 연결되는가`. 재측정 수단으로 `var/product-audit/probe_limits.py`를 등재할 것.
quality_rubric: `ux-writing` — 이번 Cycle에서 **실제로 호출**했다. 적용한 구체 항목: **Validation Errors (Inline)** — *"Pattern: `[Field] [specific requirement]`"*, *"Location: Below or beside the field"*, *"Timing: Real-time or on field exit"* (현재는 제출 후 폼 상단 한 줄이라 위치·시점 둘 다 어긋난다). **What to Avoid** — *"Robotic tone ('An error has occurred')"* 와 *"Vague causes"* 에 `Invalid request data`가 정확히 해당한다. **Accessibility** — *"Structure error messages to work with screen readers (error + field label read together)"* 가 `aria-invalid` 0개를 결함으로 만드는 근거다. **Benchmarks** — 오류 문구 12~18단어. 추가로 `ui-ux-pro-max`의 `--stack react` **"Label form controls / htmlFor matching input id"**(Severity High). `humanize-korean`은 **적용하지 않았다** — 아직 한국어 문구가 존재하지 않아 다듬을 대상이 없다. 구현 Phase가 한국어 문구를 만든 **뒤에** 그 문구에 `humanize-korean`을 적용할 것(프롬프트 2절의 순서: UX Writing → 한국어).
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-054` 절 · 실측 `var/product-audit/probe_limits.json`(422 응답·화면 문구·`aria_invalid` 0·계정 미생성) · 프로브 `var/product-audit/probe_limits.py` · `app/core/errors.py:247-288` · `app/users/schemas.py:38-39` · `frontend/src/lib/api.js:74-86` · `frontend/src/generated/fieldLimits.json`(`users` 키 부재) · `docs/BACKLOG.md` `PA-04`(자기모순 상태) · `UX-40`(선행 수정)
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0015 -->
rc_id: PA-RC-0015
severity: Low
priority: P3
confidence: Confirmed
problem: **장애 배너의 경과 시간이 항상 '분' 단위라 오래될수록 읽을 수 없어진다.** `app/observability/router.py:87`이 `minutes = int(age // 60)` 하나로 모든 경우를 찍는데, 이 문구를 쓰는 심각도가 둘이다 — `늦어지고 있습니다`(WARNING, ≥15분)와 `멈춰 있습니다`(CRITICAL, **≥1시간이고 상한이 없다**). 분 단위는 앞쪽에는 맞지만 뒤쪽에는 맞지 않는다. 현재 이 인스턴스에서 실제로 렌더되는 문구는 **"마지막으로 정상 갱신된 지 17976분 지났습니다"**(=12.5일)이고, 인증된 화면 **8/8**에서 동일하게 보인다. 즉 **가장 심각한 배너가 가장 안 읽힌다.**
expected: 경과 시간은 크기에 맞는 단위로 표시되어야 한다(분 → 시간 → 일). 이것은 외부 기준이 아니라 **이 저장소가 다른 두 곳에서 이미 지키는 관용**이다 — `app/backups/service.py:355` *"마지막으로 성공한 백업이 {int(stale_days)}일 전입니다"*, `app/projects/health.py:361` *"마지막 작업 변경이 {days}일 전입니다"*. 같은 제품 안에서 같은 개념(마지막 성공 이후 경과)을 한 곳은 '일'로, 한 곳은 '분'으로 말한다.
actual: 항상 분이다. 12.5일이 "17976분"으로 나온다. 사용자가 1,440으로 나눠야 의미를 안다.
intent_evidence: ⑤ 서로 일치하는 구현 관용 2건(`backups/service.py:355`·`projects/health.py:361`)이 '일 전' 표기를 쓴다. ② `docs/UX_WRITING.md`(`PA-RC-0002` 산출물)가 사용자 문구의 명확성을 제품 규칙으로 정한다. ⑥ `app/observability/router.py:5`의 모듈 주석이 이 배너의 목적을 *"티켓 미러가 30분째 안 돌면 사용자 화면에는 30분 전 목록이 아무 표시 없이 떠 있다"* 로 적는다 — **설계 시 상정한 크기가 '30분'** 이었음을 보여 주고, 그래서 분 단위가 선택된 경위와 그것이 CRITICAL 구간까지 확장된 것이 의도가 아님을 뒷받침한다.
findings: PA-F-056
feature_contracts: 해당 없음 — 기능 계약이 아니라 사용자 알림 문구다. 배너를 띄우는 조건·임계·심각도는 하나도 바뀌지 않는다.
routes: 인증된 **전 화면**(배너는 앱 셸에서 그려진다). 실측은 `/me`·`/my-tickets`·`/team-docs`·`/board`·`/notifications`·`/profile`·`/sprint`·`/activity` 8개에서 8/8 확인.
frontend: 해당 없음(문구 생성 위치가 아니다) — 다만 프런트가 `since`로 절대 시각 `(마지막 정상: …)`을 덧붙이므로 표기를 바꿀 때 **두 값이 서로 모순되지 않는지** 확인할 것. 렌더는 `frontend/src/app/Banners.jsx`.
api: `GET /api/observability/notices`(이 문구를 실어 보내는 응답). 응답 **구조**는 바꾸지 말 것 — `message` 문자열 내용만 바뀐다.
backend: `app/observability/router.py:64-95`(`_notice_for`) — 수정 지점. 상수 `LATE_AFTER_SECONDS`(:50)·`STALLED_AFTER_SECONDS`(:52)는 그대로 둔다.
data: 해당 없음 — DB/데이터 구조 변화 없음. `SyncStatus.last_success_at` 읽기만 한다.
rbac: 해당 없음 — 권한 경계와 무관하다. 배너 노출 대상도 바뀌지 않는다.
integration: 이 문구가 말하는 대상이 외부 연동(Notion 티켓·문서 동기화)이다. **연동 동작 자체는 건드리지 않는다** — 상태를 사람에게 전달하는 방식만 바꾼다.
state_transition: 해당 없음 — WARNING/CRITICAL 판정 로직과 임계값을 바꾸지 않는다. 같은 상태를 다른 문구로 말할 뿐이다.
user_impact: 장애 중 모든 화면 상단에 뜨는 문구의 핵심 숫자를 사용자가 즉시 해석할 수 없다. 영향이 제한적인 이유는 **같은 문장이 읽을 수 있는 절대 시각을 함께 주기 때문**이다(`(마지막 정상: 2026. 8. 3. 오후 11:22)`) — 정보가 아예 없는 것이 아니라 중복된 한 조각이 안 읽히는 것이다. 그래서 Low다. 업무를 막지 않고 막다른 길도 아니다.
implementation_direction: (1) **경과 시간 포맷터를 하나 만들고 `_notice_for`가 그것을 쓰게 한다** — 60분 미만은 "N분", 24시간 미만은 "N시간", 그 이상은 "N일"로 승급한다. 경계에서 "1일"과 "24시간"이 왔다 갔다 하지 않도록 규칙을 하나로 못박을 것. (2) **새로 만들기 전에 재사용할 것이 있는지 먼저 본다** — `app/backups/service.py:355`와 `app/projects/health.py:361`이 이미 '일 전'을 계산한다. 셋이 같은 헬퍼를 쓰게 만드는 것이 이 RC의 실제 가치다(문구 하나 고치는 것보다). 공용 위치는 기존 관용을 따를 것. (3) 문구는 `docs/UX_WRITING.md`의 종결·표현 규칙을 따른다. (4) **임계값과 심각도 판정은 건드리지 마라** — 이 RC는 표기만 바꾼다. (5) 프런트가 덧붙이는 절대 시각과 중복되므로, 상대 시간을 유지할지 절대 시각만 남길지 판단할 것 — 둘 다 남긴다면 서로 어긋나 보이지 않아야 한다.
constraints: `GET /api/observability/notices`의 응답 **구조**(`id`·`level`·`message`·`since`)를 바꾸지 말 것 — 프런트 `Banners.jsx`와 `banners.test.jsx`가 그 모양에 의존한다. CLAUDE.md §3-1(sync 일관성) 유지. CLAUDE.md §3-7(UTC 저장, 표시만 Asia/Seoul) 유지 — 경과 시간 계산에 로컬 시간대를 끌어들이지 말 것(현재 `now`는 이미 tz-aware로 들어온다). 배너 임계·심각도·노출 조건을 바꾸지 말 것.
regression_risk: (a) `frontend/src/app/banners.test.jsx`가 문구를 **문자열로 고정**하고 있다(`:102`의 "22분 지났습니다") — 표기를 바꾸면 이 테스트가 깨진다. 깨지는 것이 정상이므로 함께 갱신할 것. (b) 백엔드에 이 문구를 기대하는 테스트가 있으면 같이 갱신한다 — `tests/`에서 "분 지났습니다"를 전수 검색할 것. (c) `backups`/`projects`의 기존 '일 전' 문구를 공용 헬퍼로 옮기면 그 두 모듈의 테스트도 범위에 들어온다. 범위를 (1)+(2)로 잡으면 3개 모듈, (1)만 잡으면 1개 모듈이다. (d) 제품 동작·데이터·권한 변화 없음.
acceptance_criteria: (1) 경과가 60분 미만이면 "N분", 24시간 미만이면 "N시간", 그 이상이면 "N일"로 표시된다. (2) 현재 인스턴스처럼 12일 이상 멈춘 상태에서 배너에 **네 자리 이상의 분 숫자가 나타나지 않는다** — 재측정은 `.venv/Scripts/python var/product-audit/verify_banner.py` 이고 `matches`에 `\d{4,}분`이 **0건**이어야 한다. (3) WARNING 구간(15~60분)의 표기는 기존과 동일하다(회귀 없음). (4) 경계값(59분/60분/23시간/24시간)에서 표기가 일관된다. (5) `backups`·`projects`의 '일 전' 문구가 같은 헬퍼를 쓰거나, 안 쓴다면 그 이유가 주석에 있다. (6) 관련 백엔드·프런트 테스트 green.
required_tests: **신규**: 포맷터 단위 테스트 — 경계값 5종(1분·59분·60분·23시간59분·24시간) 각각의 표기를 고정한다. **신규**: `_notice_for`가 CRITICAL 구간(예: 12일)에서 '일' 표기를 내는지(이 결함의 revert-to-verify). **기존 갱신**: `frontend/src/app/banners.test.jsx`(문구 문자열 고정) · `tests/`에서 "분 지났습니다"를 기대하는 것 전수. **주의**: 기존 테스트가 WARNING 크기 값만 고정하고 있어서 이 결함이 통과했다 — 새 테스트는 **반드시 CRITICAL 크기 값을 포함**할 것.
qa_gaps: `docs/QA_COVERAGE.md`에 **"장애/열화 상태에서 사용자가 무엇을 보는가" 축이 없다.** 이 제품은 외부 연동(Notion·n8n·Runner)에 의존하는데 검증 축은 정상 경로 중심이고, 연동이 멈춘 상태의 화면 문구를 보는 칸이 없다. 이번 발견도 dev 인스턴스가 **우연히** 12일째 멈춰 있어서 관측된 것이다. 축을 추가하고, 재측정 수단으로 `var/product-audit/verify_banner.py`를 등재할 것.
quality_rubric: `ux-writing` — 이번 Cycle에서 실제로 호출했다. 적용 항목: **Clarity** *"Use plain language"* 와 *"Choose meaningful, specific verbs / unambiguous"* — 1,440으로 나눠야 뜻을 아는 숫자는 plain language가 아니다. **Conciseness** *"Front-load important information"* — 배너의 핵심은 "얼마나 오래됐나"인데 그 값이 해석 불가능하면 앞세운 의미가 없다. **Notifications** 패턴 *"verb-first title + contextual description"*. 추가로 이 Audit 프롬프트 6절 내장 rubric **4)**(같은 의미가 같은 pattern으로 표현되는가 — 같은 제품이 '일 전'과 '분'을 섞어 쓴다). `humanize-korean`은 **적용하지 않았다** — 기존 문구의 한국어 자체는 자연스럽고 번역투가 아니다. 문제는 문체가 아니라 단위 선택이라 그 Skill의 판정 대상이 아니다.
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-056` 절 · 실측 `var/product-audit/verify_banner.json`(8/8 라우트, "17976분") · 프로브 `var/product-audit/verify_banner.py` · `app/observability/router.py:50,52,87,93`(포맷터와 임계) · 대조 관용 `app/backups/service.py:355` · `app/projects/health.py:361` · 테스트 공백 `frontend/src/app/banners.test.jsx:102`
<!-- PA-RC-END -->

---

# 신규 — L축 Deep Design Audit 산출 (PA-RC-0016 ~ PA-RC-0024)

> 아래 9건은 `PRODUCT_AUDIT_DESIGN.md`의 18표면 판정에서 나왔다. **화면 미관 요청이 아니라
> 구조 계약**이며, 각 블록의 `target_design`이 구현의 정본이다. Bottom-up으로 현재 화면을
> 조금씩 손보는 방식은 이 Root Cause들을 닫지 못한다 — 그것이 판정이 REFINE이 아니라
> REDESIGN/REBUILD인 이유다.
>
> **공통 절대 금지선**: 기능 정확성 · 데이터 의미 · API 계약 · RBAC 경계 · 상태 전이 규칙 ·
> 외부 연동 계약을 바꾸면서 시각만 화려하게 만드는 변경은 하지 않는다. 각 블록의
> `data_impact` · `api_impact` · `rbac_impact`가 전부 "계약 불변"인지 확인하고 시작하라.

<!-- PA-RC-BEGIN PA-RC-0016 -->
rc_id: PA-RC-0016
severity: High
priority: P1
confidence: Confirmed
problem: **전역 배너 스택이 모든 화면에서 첫 화면의 3분의 1을 고정 비용으로 가져간다.** 앱 셸이 장애·설정·점검·신기능 공지를 각각 독립 배너로 세로로 쌓고, 그 높이가 화면 성격과 무관하게 항상 붙는다. 관리자 14라우트 **전부** 배너 5장 `y 64 → 395.5` = **331.5px**(1080 뷰포트의 30.7%), 사용자 9라우트 **전부** 배너 4장 = **216px**(20.0%)로 측정값이 라우트별 편차 없이 동일하다. 페이지 `h1`이 관리자에서 `y=447`에 온다. 닫을 수 있는 것은 관리자 5장 중 2장·사용자 4장 중 1장뿐이고 나머지는 상태가 풀릴 때까지 영구히 남는다. 게다가 첫 두 장은 **같은 사건을 두 번** 말한다(「티켓 동기화가 멈춰 있습니다… 18050분」/「문서 동기화가 멈춰 있습니다… 18050분」). 같은 셸 레이아웃에서 **본문에 상한(max-width)이 없어** 폭이 커질수록 활용률이 올라가고(86.3 → 88.3 → **91.1%**) 4K에서 본문이 **3500px**까지 늘어난다. 175% 배율(1097×617)의 가로 넘침도 실측됐으나 **그것은 기존 `RESP-01`이며 이 RC의 신규분이 아니다** — `RESP-01`이 이미 *"배율 175%면 CSS 폭이 1097로 줄어 26px 넘친다 … 최소 폭 1123px"* 까지 기록하고 있다. 두 축(좁은 폭 = `RESP-01`, 넓은 폭 = 상한 부재)은 같은 셸 레이아웃에서 나오므로 **함께 고치되 중복 계상하지 않는다.**
expected: 전역 크롬은 **높이 예산**을 가져야 하고, 개별 화면의 본문이 첫 화면의 대부분을 차지해야 한다. 이것은 외부 기준이 아니라 이 저장소가 스스로 세운 방향이다 — CLAUDE.md §5가 "Layout/max-width/density"와 "FHD/QHD/4K"를 필수 완료 범위로 적고, D-75(`docs/DECISIONS.md`)가 App Shell을 "전면 재설계 가능" 영역으로 명시한다. 지원 배율 구간(125/150/175%) 안에서 가로 넘침은 없어야 한다.
actual: 배너 5장이 331.5px를 상시 점유하고, 그 결과 표 화면에서 데이터 행이 뷰포트 경계까지 밀린다(`/users` thead `y=982`, 첫 행 `y=1019`). 4K에서 본문 상한이 없어 3500px까지 늘어난다. (175% 가로 넘침도 재현되나 그것은 기존 `RESP-01`이다.)
intent_evidence: ② CLAUDE.md §5(Layout/max-width/density·FHD/QHD/4K를 필수 범위로 규정) · ② `docs/DECISIONS.md` D-75(App Shell·Layout을 보존 의무 없는 재설계 대상으로 확정) · ⑤ 제품 자신의 반증 — 배너 5장 중 2장에만 닫기 버튼을 붙였다는 것은 "영구 표시가 바람직하지 않다"는 판단이 이미 코드에 있다는 뜻이고, 그 판단이 나머지 3장에는 적용되지 않았다.
findings: PA-F-058, PA-F-067 (PA-F-067의 가로 넘침 절반은 기존 `RESP-01`과 동일 결함이므로 이 RC의 신규 범위에서 제외했다 — 중복 계상 방지)
feature_contracts: FC-배너알림(장애·공지 노출 조건과 심각도) — **판정 조건·임계·심각도·대상 사용자는 하나도 바뀌지 않는다.** 바뀌는 것은 같은 정보를 화면에 배치하는 방식뿐이다.
routes: 인증된 **전 라우트**(셸에서 그려진다). 실측은 관리자 14(`/dashboard`·`/users`·`/audit`·`/jobs`·`/settings`·`/system`·`/departments`·`/rbac`·`/integrations`·`/prompts`·`/feature-flags`·`/offboarding`·`/diagnostics`·`/org-tree`) + 사용자 9(`/me`·`/my-tickets`·`/team-docs`·`/board`·`/notifications`·`/chat`·`/new-ticket`·`/projects`·`/search`).
frontend: `frontend/src/app/Banners.jsx`(배너 렌더) · `frontend/src/app/AppShell.jsx`(셸 레이아웃·본문 폭) · 헤더 컴포넌트(상태 칩이 들어갈 자리) · 본문 컨테이너의 max-width 정의 위치.
api: `GET /api/observability/notices` — **응답 구조를 바꾸지 않는다.** 요약 칩은 지금 받는 배열을 그대로 집계해서 만든다. 새 엔드포인트를 만들 필요가 없다.
backend: 없음. 이 RC는 프런트 표현 계층만 바꾼다. `app/observability/router.py`는 `PA-RC-0015`가 담당하며 이 RC에서 건드리지 않는다.
data: 해당 없음 — DB/데이터 구조 변화 없음.
rbac: 해당 없음 — 배너 노출 대상과 권한 판단은 그대로다. 요약 칩도 지금 그 사용자에게 오는 항목만 센다.
integration: 배너가 말하는 대상이 외부 연동(Notion 동기화) 상태다. **연동 동작·폴링·임계는 건드리지 않는다.**
state_transition: 해당 없음 — WARNING/CRITICAL 판정과 전이는 불변.
user_impact: 모든 사용자가 모든 화면에서 첫 화면의 20~31%를 이미 읽은 공지에 쓴다. 상시 노출이라 경보 피로가 생겨 **진짜 장애가 떴을 때도 배경으로 읽힌다**. 표 화면에서는 이 비용이 그대로 데이터 행을 밀어내 스크롤을 강제한다.
implementation_direction: (1) **헤더에 상태 칩 하나를 만들고 개별 배너 스택을 없앤다.** 칩은 `장애 2 · 공지 1`처럼 심각도별 개수만 보이고, 누르면 패널이 열려 항목별 원인·경과·조치 링크를 준다. (2) **심각도 CRITICAL 1건만** 헤더 바로 아래 한 줄(≤40px)로 남긴다. (3) **같은 원인의 다중 증상을 합친다** — 티켓·문서 동기화 정지는 둘 다 `SyncStatus` 정지이므로 「동기화 정지 · 12일째 · 자세히」 한 줄로 요약한다. 합치는 기준은 문구 매칭이 아니라 notice의 원인 식별자를 쓸 것. (4) 닫기는 전부에 제공하고 닫은 상태를 사용자별로 기억하되, 심각도가 올라가면 다시 뜬다. (5) 본문 컨테이너에 max-width를 도입한다(표는 넓게, 폼·본문 텍스트는 제한). (6) **175% 가로 넘침은 이 RC가 새로 만든 항목이 아니라 기존 `RESP-01`이다** — 같은 셸 레이아웃을 건드리므로 함께 처리하되, `RESP-01`의 기존 진단(`DataTable` 열 폭 계산, 최소 폭 1123px)을 먼저 읽고 그 위에서 이어갈 것. 새로 조사하지 마라. 마찬가지로 `RESP-04`(1024~1200에서 사이드바가 264px를 계속 씀, "축소 레일이라는 세 번째 상태가 필요하다")는 `PA-RC-0017`이 함께 닫아야 한다.
constraints: CLAUDE.md §3-6(서버 데이터를 `innerHTML`로 주입 금지, inline script/`onclick` 금지) — 배너 문구는 텍스트 노드로만 렌더한다. `connect-src 'self'` 유지. 배너 판정 조건·임계·심각도·노출 대상을 바꾸지 않는다. `GET /api/observability/notices` 응답 구조를 바꾸지 않는다. 접힌 상태에서도 스크린리더가 심각도와 개수를 읽을 수 있어야 한다(`role="status"` 또는 동등). `PA-RC-0015`(경과 단위)와 같은 배너를 다루므로 0015를 먼저 처리하는 편이 낫다.
regression_risk: **범위가 전 라우트라 회귀 반경이 가장 크다.** (1) 배너가 사라지면 기존 테스트 중 배너 텍스트를 DOM에서 찾는 것이 깨진다(`frontend/src/app/banners.test.jsx`). (2) 셸 레이아웃 변경은 모든 화면의 스크롤·고정 요소·모달 위치에 영향을 준다. (3) max-width 도입은 표 화면에서 열 폭을 바꿔 기존 스크린샷/레이아웃 기대를 흔든다. (4) 상태 칩 집계 로직이 틀리면 장애를 **덜** 보여주게 되므로, 개수 집계는 반드시 테스트로 고정할 것. (5) 175% 수정이 다른 배율을 깨뜨리지 않는지 6개 뷰포트 전부 재측정.
acceptance_criteria: (1) 관리자·사용자 각 5개 이상 라우트에서 `h1`의 `y`좌표가 1080 뷰포트 기준 **200px 이하**다. (2) 배너로 인한 상시 점유 높이가 **80px 이하**다(CRITICAL 1줄 + 여백). (3) 티켓·문서 동기화 정지가 동시에 있을 때 화면에 나타나는 관련 줄이 **1개**다. (4) 상태 칩이 표시하는 심각도별 개수가 `/api/observability/notices` 응답의 실제 개수와 일치한다(단위 테스트). (5) 모든 공지에 닫기가 있고, 닫은 뒤 새로고침해도 닫힌 채이며, 심각도 상승 시 다시 나타난다. (6) 6개 뷰포트(1920/2560/3840/125%/150%/175%/1280) 전부에서 `scrollWidth <= clientWidth + 1`이다 — 175% 구간은 `RESP-01`의 완료 판정과 **같은 기준**을 쓴다(중복 기준을 새로 만들지 마라). (7) 4K에서 본문 텍스트/폼 영역이 max-width로 제한되고 표는 넓게 유지된다. (8) 접힌 상태에서 스크린리더가 「장애 2건, 공지 1건」을 읽는다.
required_tests: `frontend/src/app/banners.test.jsx` 갱신·확장 — 심각도별 집계, 동일 원인 병합, 닫기 영속, 심각도 상승 시 재노출. 새 셸 레이아웃 테스트 — `h1` 위치 예산, max-width 적용 대상. 뷰포트 회귀는 `var/product-audit/design_capture2.py`의 viewports 절차를 `scripts/ui_qa/`에 정식 편입해 6개 조건에서 `overflowX=false`를 검증. 대표 소비자 회귀: `/dashboard`·`/users`·`/chat`·`/me` 렌더 테스트.
qa_gaps: `QA_COVERAGE.md`에 「전 라우트 공통 셸 높이 예산」과 「125/150/175% 배율 가로 넘침」 항목이 없다. 배율 축은 이번 Cycle이 처음 실측했다.
quality_rubric: `ui-ux-pro-max` — Data-Dense Dashboard 기준(space-efficient · maximum data visibility)과 `--domain ux`의 Layout & Responsive(horizontal-scroll: 콘텐츠가 뷰포트 폭에 맞아야 함). `impeccable` — Operate 모드(scanability 우선), heuristic 8(Aesthetic and Minimalist Design: 모든 요소가 자기 픽셀값을 해야 한다), Cognitive Load의 Visual Noise Floor. `redesign-existing-projects` — "No max-width container" 및 "Content padding: 고정 요소 뒤로 콘텐츠가 숨지 않게".
current_state: 헤더 64px + 좌측 레일 264px + 본문 1656px(86.3%). 배너가 관리자 5장 331.5px·사용자 4장 216px으로 26라우트 전부 동일하게 쌓이고 h1은 관리자 y=447에 온다. 닫기는 관리자 2/5·사용자 1/4에만 있다. 175% 배율에서 가로 넘침, 4K에서 본문 3500px.
user_problem: 어떤 화면을 열든 첫 화면의 3분의 1을 이미 읽은 공지가 먼저 차지하고, 영구 표시라 진짜 장애도 배경으로 읽힌다. 표 화면에서는 데이터 행이 화면 밖으로 밀린다.
design_verdict: REDESIGN
target_state: 사용자가 어느 화면을 열어도 본문이 첫 화면의 80% 이상을 차지하고, 장애가 있으면 헤더의 상태 칩과 CRITICAL 한 줄로 즉시 알 수 있으며, 자세한 내용은 칩을 눌러 확인한다.
target_design: 헤더(56~64px) 우측에 상태 칩 하나(`장애 2 · 공지 1`). 개별 배너 스택 제거. 칩 클릭 시 패널이 열려 항목별로 원인·경과 시간·조치 링크를 목록으로 보여준다. 심각도 CRITICAL 1건만 헤더 바로 아래 한 줄(≤40px)로 상시 노출하고 나머지는 칩 안으로 접는다. 같은 원인의 다중 증상(티켓·문서 동기화)은 원인 식별자 기준으로 한 줄로 병합한다. 모든 공지에 닫기를 제공하고 사용자별로 기억하되 심각도 상승 시 재노출. 본문 컨테이너에 max-width를 도입해 표는 넓게, 폼·본문 텍스트는 제한한다.
visual_change_required: true
target_visual_delta: 모든 화면의 상단 331.5px(관리자)·216px(사용자) 배너 띠가 사라지고 헤더 우측에 작은 상태 칩이 생긴다. 페이지 제목이 y≈447에서 y≈150 부근으로 올라오고 표 화면은 첫 화면 안에서 데이터 행이 보이기 시작한다. 4K에서 폼과 본문 텍스트가 화면 끝까지 늘어나지 않는다.
affected_surfaces: app-shell · global-header · table-screens · list-screens (그리고 배너가 그려지는 인증된 전 라우트)
affected_components: `frontend/src/app/Banners.jsx` · `frontend/src/app/AppShell.jsx` · 헤더 컴포넌트 · 본문 컨테이너/레이아웃 래퍼
workflow_change: 없음 — 사용자가 수행하는 업무 절차는 바뀌지 않는다. 공지를 읽는 경로가 "항상 보임"에서 "칩 + CRITICAL 한 줄, 나머지는 펼쳐 보기"로 바뀔 뿐이다.
navigation_impact: 없음 — 라우트·메뉴·이동 경로 불변. 헤더 우측에 요소 하나가 추가된다.
data_impact: 없음 — 데이터 의미·저장 구조 불변. 닫음 상태만 사용자별 클라이언트/서버 설정으로 저장되며 이는 표시 상태이지 업무 데이터가 아니다.
api_impact: 없음 — `GET /api/observability/notices` 응답 구조 불변. 집계는 클라이언트에서 한다.
rbac_impact: 없음 — 노출 대상 판단은 서버 정본 그대로. 요약 칩은 그 사용자에게 이미 내려온 항목만 센다.
browser_verification: 1920×1080 light·dark에서 `/dashboard`·`/users`·`/chat`·`/me` 4화면의 `h1` y좌표가 200 이하이고 배너 점유가 80px 이하임을 스크린샷과 계측으로 확인. 2560×1440·3840×2160·1536×864@1.25·1280×720@1.5·**1097×617@1.75**·1280×800 6개 뷰포트에서 `/users` 가로 넘침 0을 확인(현재 175%만 실패). 티켓·문서 동기화가 동시에 정지한 상태에서 관련 줄이 1개인 스크린샷.
evidence_refs: `PRODUCT_AUDIT_DESIGN.md` §2-A·§3 app-shell·§3-A · `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-058`·`PA-F-067` · 계측 `var/product-audit/probe_shell.json`(bannerTop/bannerBottom/h1y, 관리자 14 + 사용자 9라우트) · `var/product-audit/design_capture2.json` viewports[] · 스크린샷 `var/product-audit/shots/fhd_admin_dashboard.png`·`fhd_admin_users.png`·`fhd_user_me.png`·`fhd_user_chat.png`·`dark3_user_me.png` · 프로브 `var/product-audit/probe_shell.py`·`design_capture2.py`
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0017 -->
rc_id: PA-RC-0017
severity: High
priority: P1
confidence: Confirmed
problem: **관리자 정보구조가 39개 목적지를 8그룹 한 평면에 늘어놓았고, 그 결과 내비가 자기 내용의 42%만 보여준다.** 계측하면 링크 39 + 그룹 헤더 8 = 46항목, nav 콘텐츠 **1976px**를 **839px** 창으로 본다. 1080에서 21개가 접힌다(내부 `overflow-y:auto`로 도달은 된다). `impeccable`의 Working Memory 규범(최상위 ≤5, 형제 ≤4) 대비 **8그룹**이고 「시스템 인프라」·「사용자」는 형제가 각 7이다. 그룹명이 「시스템 인프라」·「거버넌스」처럼 시스템 구현 기준이라 업무에서 출발한 사람이 어느 그룹인지 추론해야 한다. 가장 뚜렷한 증상은 **설정이 6개 화면에 흩어진 것**이다 — 「설정」·「시스템 설정」·「초기 설정」·「유지보수」·「Notion 관리」·「AI 관리」. 제품은 이 비용을 `/settings` 상단 **안내 4문단**으로 흡수하고 있다. 내비 안에 검색·필터가 없어 Ctrl K 전역 검색이 사실상 유일한 우회로다. **사용자 콘솔은 23링크·접힘 0으로 문제가 없다 — 관리자만의 문제다.**
expected: 최상위 선택지는 작업기억 안에 들어와야 하고(≤5), 같은 대상을 다루는 화면은 한 곳에 모여야 하며, 목적지 이름만 보고 목적을 알 수 있어야 한다. 근거: ② D-75(`docs/DECISIONS.md`)가 "메뉴 구조/그룹"과 "Information Architecture 재편"을 보존 의무 없는 재설계 대상으로 명시 · ② CLAUDE.md §5가 "Navigation/IA"를 필수 완료 범위로 규정 · ⑤ 사용자 콘솔이 같은 저장소 안에서 23링크·접힘 0으로 성립하는 대조군을 제공한다.
actual: 8그룹 39목적지 평면. 42%만 보이고 21개가 접힌다. 설정이 6화면에 분산되어 안내 4문단이 그 사실을 설명한다.
intent_evidence: ② `docs/DECISIONS.md` D-75 · ② CLAUDE.md §5 · ⑤ 사용자 콘솔의 대조 구현(동일 셸·동일 컴포넌트로 23링크가 스크롤 없이 성립) · ⑤ `/settings` 안내문 자체가 "설정이 흩어져 있다"는 사실을 제품이 인지하고 있음을 보여주는 1차 증거.
findings: PA-F-059, PA-F-064
feature_contracts: FC-관리자권한범위(어느 역할에게 어느 화면이 보이는가) — **RBAC 노출 규칙은 그대로 유지한다.** 메뉴 구조가 바뀌어도 각 목적지의 권한 요구는 불변이고, 서버 authorization이 정본이라는 것도 불변이다.
routes: 관리자 전 라우트(39 목적지). 재편 대상 핵심은 `/settings`·`/system`·`/setup`·`/maintenance`·`/notion-console`·`/llm-console`(설정 6종), `/prompt-usage`·`/policy-usage`(통계 2종), 그리고 8개 그룹 전체.
frontend: 관리자 내비 정의(`frontend/src/app/AdminRoutes.jsx`와 그것이 참조하는 메뉴/레지스트리 — `frontend/src/screens/registry/*.js`) · 사이드바 컴포넌트 · 각 통합 대상 화면의 컨테이너(탭 도입 지점) · breadcrumb 생성부.
api: 없음 — 화면 경계 재편이며 엔드포인트는 그대로다. 탭 통합 시 한 화면이 여러 엔드포인트를 부르게 되지만 **엔드포인트 자체를 합치거나 바꾸지 않는다**.
backend: 없음.
data: 해당 없음 — 데이터 구조·의미 불변.
rbac: **영향 있으나 경계는 불변.** 탭으로 합칠 때 탭마다 권한 요구가 다를 수 있으므로, 화면 단위 게이트를 탭 단위 게이트로 정확히 옮겨야 한다. 권한 없는 탭은 표시하지 않고, 서버는 지금처럼 각 엔드포인트에서 독립적으로 판단한다(프런트 게이트는 보조).
integration: 「Notion 관리」·「AI 관리」·「외부 연동」이 통합 대상에 포함되지만 **연동 동작·자격증명 처리·연결 테스트 기능은 그대로 옮긴다**.
state_transition: 해당 없음 — 다만 되돌릴 수 없는 실행 동작(서비스 재시작·DNS·시간대)을 탭 안으로 옮길 때 **현재 화면 분리가 지키던 안전 의도를 확인 단계로 반드시 보존**해야 한다.
user_impact: 운영자가 설정 하나를 바꾸려 할 때 어느 화면인지 메뉴만 보고 알 수 없어, `/settings`에 들어가 안내문을 읽고 다른 화면으로 이동하는 왕복이 기본 동선이 된다. 장애 대응처럼 시간이 중요한 상황에서 이 비용이 그대로 지연이 된다.
implementation_direction: (1) **목적지를 업무 기준 5영역으로 접는다** — 운영 / 사용자·권한 / 자동화 / 연동 / 감사. 최상위 5개가 스크롤 없이 다 보이게 한다. (2) **영역 안은 화면 상단 탭으로 내린다.** 목적지를 지우지 않고 계층을 한 단 넣는 것이 핵심이다. (3) **설정 6화면을 「설정」 한 화면 + 탭으로 통합한다** — 시스템 정책 / OS·서비스 동작 / 연동 / AI. 되돌릴 수 없는 실행 동작 탭은 시각적으로 구분하고 **확인 단계를 유지**한다. (4) 사용 통계 2종은 각 대상 화면의 탭으로 흡수한다. (5) **레일 상단에 내비 필터 입력**을 둔다. (6) breadcrumb을 영역 › 화면 › 탭 3단계로 확장한다. (7) 재편 후 `/settings` 안내 4문단은 **없앤다** — 없애도 길을 잃지 않는 것이 이 작업의 성공 판정이다. (8) 기존 URL은 새 위치로 리다이렉트해 북마크/딥링크를 깨뜨리지 않는다.
constraints: RBAC 노출 규칙과 서버 authorization 불변(CLAUDE.md §3-5). 기존 라우트 URL은 제거하지 말고 리다이렉트로 보존한다. 되돌릴 수 없는 동작의 확인 단계를 탭 통합 과정에서 잃지 않는다. CLAUDE.md §3-8(제품 기능 경계) — 범용 shell 실행이나 secret 평문 표시를 이 재편을 빌미로 추가하지 않는다. 사용자 콘솔 내비는 **건드리지 않는다**(이미 정상이다).
regression_risk: **가장 큰 위험은 RBAC다.** 화면 게이트를 탭 게이트로 옮기는 과정에서 권한 없는 사용자에게 탭이 보이거나, 반대로 권한 있는 사용자가 기능을 잃을 수 있다. 역할 4종(user·operator·auditor·system_admin) × 새 탭 전체의 allow/deny를 반드시 검증할 것. 그 다음 위험은 딥링크 — 기존 39개 URL이 전부 새 위치로 도달하는지. 세 번째는 되돌릴 수 없는 동작의 확인 단계 유실.
acceptance_criteria: (1) 관리자 레일의 최상위 항목이 **5개 이하**이고 1080 뷰포트에서 **스크롤 없이 전부 보인다**. (2) 어떤 그룹도 형제가 **7개를 넘지 않는다**. (3) 설정 성격 화면이 **1개 화면 + 탭**으로 도달 가능하고, `/settings`의 안내 4문단이 **삭제**되어 있다. (4) 기존 관리자 URL 39개 전부가 새 위치로 도달한다(404·대시보드 리다이렉트 0건). (5) 역할 4종 × 전체 탭의 접근 허용/거부가 재편 전과 **정확히 동일**하다(자동 테스트). (6) 되돌릴 수 없는 동작(서비스 재시작·DNS·시간대·복구)이 확인 단계 없이 실행되지 않는다. (7) 레일 필터에 두 글자를 입력하면 목적지가 좁혀진다. (8) breadcrumb이 영역 › 화면 › 탭을 보여준다.
required_tests: RBAC 회귀 — 역할 4종 × 신규 탭 전체 allow/deny(백엔드 authorization과 프런트 게이트 양쪽). 라우트 리다이렉트 테스트 — 기존 39 URL → 새 위치. 되돌릴 수 없는 동작의 확인 단계 테스트. 내비 필터 컴포넌트 테스트. `var/product-audit/probe_rbac_gate.py`를 재편 후 재실행해 프런트 게이트와 백엔드 판정이 계속 일치하는지 확인.
qa_gaps: `QA_COVERAGE.md`에 「관리자 IA 구조(최상위 개수·형제 수·스크롤 없는 도달)」 항목이 없고, 「기존 URL 리다이렉트 보존」도 없다. 탭 단위 RBAC은 아직 존재하지 않는 구조라 커버리지 자체가 신설 대상이다.
quality_rubric: `impeccable` — Working Memory 규범(최상위 ≤5, 형제 ≤4, 8+ 항목은 과부하), Cognitive Load의 The Hidden Navigation과 The Context Switch, heuristic 4(Consistency and Standards)·6(Recognition Rather Than Recall). `ui-ux-pro-max` `--domain ux` — Navigation Active State, Breadcrumbs(3단계 이상 깊이에서 사용). `redesign-existing-projects` — 메뉴가 업무 기준인가 시스템 구현 기준인가.
current_state: 관리자 목적지 39개가 8그룹 한 평면에 있다. nav 콘텐츠 1976px를 839px 창으로 보여 42%만 보이고 21개가 접힌다(내부 스크롤로 도달은 됨). 설정이 6화면에 흩어져 있고 `/settings` 안내 4문단이 어느 설정이 어디 있는지 설명한다. 내비 검색 없음. 사용자 콘솔은 23링크·접힘 0으로 정상.
user_problem: 운영자가 목적지를 찾으려면 42%만 보이는 창을 스크롤하며 시스템 구현 기준 그룹명 8개를 훑어야 한다. 설정 하나를 바꾸려면 `/settings`에 들어가 안내문을 읽고 다른 화면으로 다시 이동하는 왕복이 기본 동선이다.
design_verdict: REDESIGN
target_state: 관리자가 레일에서 최상위 5영역을 스크롤 없이 전부 보고, 목적지 이름만으로 어디로 갈지 판단하며, 설정은 한 화면의 탭에서 끝난다. 안내문을 읽지 않아도 길을 잃지 않는다.
target_design: 레일을 업무 기준 5영역(운영 / 사용자·권한 / 자동화 / 연동 / 감사)으로 접고 영역 안은 화면 상단 탭으로 내린다. 최상위 5개는 스크롤 없이 전부 보인다. 레일 상단에 내비 필터 입력. 설정 6화면은 「설정」 한 화면 + 4탭(시스템 정책 / OS·서비스 동작 / 연동 / AI)으로 통합하되 되돌릴 수 없는 실행 동작 탭은 시각 구분 + 확인 단계 유지. 사용 통계 2종은 각 대상 화면 탭으로 흡수. breadcrumb은 영역 › 화면 › 탭 3단계. 기존 39 URL은 새 위치로 리다이렉트.
visual_change_required: true
target_visual_delta: 좌측 레일이 46항목 스크롤 목록에서 5개 영역 + 필터 입력으로 바뀌어 스크롤이 사라진다. 각 화면 제목 아래 탭 줄이 생긴다. `/settings`에서 안내 4문단 박스가 사라지고 대신 탭 4개가 보인다.
affected_surfaces: sidebar · navigation-ia · settings · admin-console (관리자 전 화면의 상단 탭 줄)
affected_components: `frontend/src/app/AdminRoutes.jsx` · `frontend/src/screens/registry/*.js` · 사이드바 컴포넌트 · breadcrumb 생성부 · 통합 대상 화면 6종의 컨테이너
workflow_change: 설정 변경 동선이 「메뉴에서 6개 중 고르기 → 틀리면 안내문 읽고 이동」에서 「설정 → 탭 선택」으로 짧아진다. 업무 자체의 순서·권한·결과는 바뀌지 않는다.
navigation_impact: **이 RC의 본체가 Navigation/IA 변경이다.** 최상위 8그룹 → 5영역, 목적지 39개는 유지하되 탭 계층으로 내려간다. 기존 URL은 리다이렉트로 보존한다.
data_impact: 없음 — 데이터 의미·구조 불변.
api_impact: 없음 — 엔드포인트 불변. 한 화면이 여러 엔드포인트를 부르게 될 뿐이다.
rbac_impact: **경계 불변, 적용 지점 이동.** 화면 단위 게이트를 탭 단위 게이트로 정확히 옮긴다. 권한 없는 탭은 표시하지 않고 서버 authorization은 지금처럼 엔드포인트별로 독립 판단한다. 역할 4종 × 전체 탭의 allow/deny가 재편 전과 동일해야 한다.
browser_verification: 1920×1080 light에서 관리자 레일 스크린샷 — 최상위 5개가 스크롤 없이 전부 보이고 nav `scrollHeight <= clientHeight`. `/settings` 스크린샷 — 안내 4문단 없음, 탭 4개 존재. 역할 4종으로 각각 로그인해 레일과 탭 노출을 스크린샷으로 대조. 기존 39 URL 직접 입력 후 도달 확인.
evidence_refs: `PRODUCT_AUDIT_DESIGN.md` §2-B·§2-G·§3 sidebar·§3 navigation-ia·§3 settings · `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-059`·`PA-F-064` · 계측 `var/product-audit/verify_nav.json`(nav scrollHeight 1976 / clientHeight 839, linkCount 39, linksBelowViewport 21) · `var/product-audit/design_capture_admin.json` navItems 46종 · 스크린샷 `var/product-audit/shots/fhd_admin_settings.png`(안내 4문단)·`fhd_admin_dashboard.png`(8그룹 레일) · 프로브 `var/product-audit/verify_nav.py`
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0018 -->
rc_id: PA-RC-0018
severity: High
priority: P1
confidence: Confirmed
problem: **대시보드가 의사결정 화면이 아니라 균일한 카드 벽이고, 같은 수치를 최대 3회 반복한다.** `/dashboard`는 최상위 카드 **39~40장**, 문서 높이 **2569px(2.38화면)**, 표 행 **0**, **contained(기본) 버튼 0개**다. 9개 구역이 전부 같은 흰 카드로 렌더되어 「중단 워커 위험」과 「0 대기 작업」이 같은 시각 무게를 갖는다. 자동 검출된 중복: `3`(미해결 실패 작업)이 「확인이 필요한 항목」·「지금 상태」·「현재 큐 상태」 **3구역**에, `42.6%`(디스크)와 `0`(활성 워크플로)이 각 **2구역**에 나온다. 값이 `0`·`-`인 카드도 실제 값과 같은 크기·무게를 갖는다. 결정적으로 화면이 **자기 정보구조를 산문으로 설명한다** — 「이 줄은 요약입니다. 값을 누르면 그 화면으로 내려가고, 자세한 항목은 아래 구역에 있습니다.」 요약 줄이 아래 구역과 같은 무게라 한 문장을 덧붙여야 했던 것이다. 같은 병이 `/my-stats`(카드 12·CTA 0), `/me`(카드 16·CTA 0·7개 기능 표면 병렬), `/projects`(프로젝트 0건인데 값이 0·-인 지표 카드 8장을 빈 상태 위에 먼저 그림)에도 있다.
expected: 대시보드는 "지금 무엇을 해야 하는가"를 첫 화면에서 답하고, 조치가 필요한 항목에는 조치 수단이 붙어야 하며, 같은 수치는 한 번만 나와야 한다. 근거: ② D-75가 "Dashboard 재설계"를 보존 의무 없는 영역으로 명시하고 "단순 현황판인가 실제 의사결정 화면인가"를 판정 질문으로 규정 · ② CLAUDE.md §5가 Dashboard를 필수 개선 범위로 규정 · ⑤ 화면 최상단 구역명이 「확인이 필요한 항목」이라는 것 자체가 조치 화면을 의도했다는 증거다.
actual: 카드 40장·기본 동작 0개·2.38화면. 같은 숫자가 최대 3번. 0인 지표가 실제 값과 같은 크기. IA를 설명하는 문장이 화면 안에 있다.
intent_evidence: ② `docs/DECISIONS.md` D-75(Dashboard를 처음부터 다시 설계하는 관점으로 평가하라고 규정, "정상 정보와 이상 정보의 시각적 우선순위가 다른가"·"Primary Action이 분명한가"를 판정 항목으로 명시) · ② CLAUDE.md §5 · ⑤ 구역명 「확인이 필요한 항목」이 표현하는 설계 의도 · ⑤ 제품 자신의 자백 — 「이 줄은 요약입니다…」 문장은 배치만으로 요약임이 전달되지 않는다는 것을 개발자가 이미 알고 있었다는 뜻이다.
findings: PA-F-060
feature_contracts: FC-대시보드지표(각 지표의 계산 정의와 출처) — **지표의 계산식·의미·출처는 하나도 바꾸지 않는다.** 특히 「최근 24시간에 종료된 작업 대비이며 대기·실행 중은 분모에서 제외」 같은 현재의 정직한 정의는 그대로 보존한다. 바뀌는 것은 어떤 지표를 어디에 어떤 크기로 놓느냐다.
routes: `/dashboard`(주), `/my-stats`·`/me`(같은 패턴), `/projects`(0 지표 + 빈 상태 배치). 중복 구역이 상세로 내려가면서 `/jobs`·`/system`·`/backup`·`/workflows`가 수신 화면이 된다.
frontend: `frontend/src/screens/` 아래 대시보드 화면 모듈과 그것이 쓰는 통계 카드 컴포넌트 · `/my-stats`·`/me`·`/projects` 화면 모듈 · 공용 stat 카드/섹션 컴포넌트(있다면 그것이 수정 지점, 없다면 신설이 이 RC의 산출물).
api: 대시보드가 부르는 기존 엔드포인트 그대로. **응답 구조를 바꾸지 않는다.** 중복 제거는 프런트에서 어떤 값을 어디에 그리느냐의 문제이지 API가 덜 주는 문제가 아니다. 조치 버튼은 이미 존재하는 조치 엔드포인트(러너 재시작·잡 재시도·백업 실행)를 호출한다 — **새 엔드포인트를 만들기 전에 기존 것을 먼저 찾을 것.**
backend: 원칙적으로 없음. 조치 버튼이 필요로 하는 엔드포인트가 실제로 없을 때만 추가하되, 그 경우에도 RBAC·상태 전이 규칙을 기존 화면과 동일하게 따른다.
data: 해당 없음 — 데이터 구조·의미 불변.
rbac: 조치 버튼은 **그 조치에 대한 권한이 있는 역할에게만** 보이고, 서버가 정본으로 다시 판단한다. 이전 Cycle이 확인한 사실(`PA-F-053`: `operator`에게 쓰기 컨트롤이 10화면 전부에서 안 보인다)과 모순되지 않게 할 것 — 대시보드에 조치 버튼을 추가하면서 권한 없는 역할에게 노출하면 그 성질이 깨진다.
integration: 서비스 상태 구역이 외부 연동(n8n·Runner·Notion) 상태를 보여준다. **연동 판정·health 계산·폴링을 건드리지 않는다.**
state_transition: 조치 버튼이 상태를 바꾸는 경우(러너 재시작·잡 재시도) **기존 화면과 동일한 전이 규칙과 확인 절차**를 따른다. 대시보드에서 실행한다는 이유로 확인 단계를 생략하지 않는다.
user_impact: 운영자가 「확인이 필요한 항목」 아래 위험 4건을 보고도 그 자리에서 할 수 있는 일이 없어 다른 화면으로 이동해야 한다. 모든 카드가 같은 무게라 위험과 정상이 구분되지 않고, 같은 숫자를 세 번 마주치면서 그것이 같은 사건인지 판단할 단서가 없다. 결국 2.4화면을 스크롤하고도 무엇을 해야 할지 모른다.
implementation_direction: (1) **첫 화면 상단을 조치 대기 목록 하나로 만든다** — 각 행은 「무엇이 · 언제부터 · 영향」 + 기본 조치 버튼. 조치할 것이 없으면 「이상 없음」 한 줄로 접는다. (2) **정상 지표는 카드가 아니라 한 줄 요약 스트립**으로 접고 클릭 시 해당 화면으로 보낸다. (3) **같은 수치는 화면 전체에서 한 번만** 등장하게 하고 중복 구역(인벤토리·시스템 리소스·현재 큐 상태)은 상세 화면으로 내린다. (4) **값이 0인 지표를 큰 숫자로 그리지 않는다** — 스트립 안 무채색으로 축약한다. 이 규칙은 `/projects`의 0 지표 8장에도 적용한다. (5) 재구축 후 「이 줄은 요약입니다…」 설명문을 **삭제한다** — 삭제해도 이해되는 것이 성공 판정이다. (6) `/me`는 「오늘 내가 할 일」 하나로 좁히고 팀 채팅·게시판은 카드에서 빼 사이드바 목적지로 되돌린다. (7) 관리자 착지를 `/me`에서 `/dashboard`로 바꾼다. (8) 조치 버튼의 위계는 `PA-RC-0023`의 규범을 따른다.
constraints: 지표의 계산 정의와 정직한 결손 고지(「티켓 소스를 읽지 못해 … 셀 수 없습니다」)를 **삭제하거나 0으로 위장하지 않는다** — 이것은 이 제품의 미덕이고 재구축이 잃기 쉬운 것이다. 조치 버튼은 기존 RBAC과 확인 절차를 따른다. 비동기 영역은 `loading-state` 판정이 KEEP으로 확정한 형태(레이아웃 모양의 스켈레톤, 범용 스피너 금지)를 **유지**한다 — 재구축 과정에서 스피너로 후퇴하지 말 것. API 응답 구조 불변. CLAUDE.md §3-6(innerHTML 금지) 준수.
regression_risk: (1) 지표 정의를 옮기다 계산이 바뀌면 운영 판단이 틀어진다 — 값은 반드시 재구축 전후로 동일해야 한다. (2) 중복 제거 과정에서 필요한 지표를 통째로 잃을 수 있다 — 어느 화면으로 갔는지 추적표를 남길 것. (3) 조치 버튼 추가는 권한 노출 회귀 위험이다(`PA-F-053` 참조). (4) `/me` 재편은 사용자 콘솔 착지 화면이라 영향 반경이 크고, 관리자 착지 변경은 로그인 흐름 테스트를 건드린다. (5) 스켈레톤 로딩이 스피너로 후퇴하는 조용한 회귀.
acceptance_criteria: (1) `/dashboard` 첫 화면(1080) 안에서 **조치가 필요한 항목과 그 조치 수단이 모두 보인다**. (2) 문서 높이가 **1.5화면 이하**다(현재 2.38). (3) 화면 전체에서 **같은 (값, 의미) 쌍이 2회 이상 나타나지 않는다**(자동 검사로 고정 — `probe_shell.py`의 dup 스캔을 회귀 테스트로 편입). (4) 조치가 필요한 항목마다 **기본 동작 버튼이 정확히 1개** 있다. (5) 조치할 것이 없을 때 최상단이 한 줄로 접힌다. (6) 값이 `0`/`-`인 지표가 **큰 숫자 카드로 렌더되지 않는다**(`/dashboard`·`/projects` 양쪽). (7) 「이 줄은 요약입니다…」 문장이 **삭제**되어 있다. (8) 모든 지표의 계산 결과가 재구축 전과 **동일**하다(단위 테스트로 값 대조). (9) 정직한 결손 고지 문구가 **보존**되어 있다. (10) 비동기 영역이 스켈레톤으로 로딩되고 범용 원형 스피너가 0개다. (11) 관리자 로그인 착지가 `/dashboard`다. (12) 조치 버튼이 권한 없는 역할(`operator` 등)에게 보이지 않는다.
required_tests: 지표 값 동등성 테스트(재구축 전후 동일 입력 → 동일 출력). 중복 검출 회귀 테스트(같은 값+라벨이 2회 이상 렌더되면 실패). 0 값 렌더 규칙 테스트. 조치 버튼 RBAC 테스트(역할 4종 × 조치 종류). 스켈레톤 존재/스피너 부재 테스트. 로그인 착지 라우팅 테스트(관리자 → `/dashboard`, 사용자 → `/me`). `/me`·`/my-stats`·`/projects` 렌더 회귀.
qa_gaps: `QA_COVERAGE.md`에 「대시보드 정보 중복」·「0 값 지표 렌더 규칙」·「조치 버튼 권한 노출」 항목이 없다. 대시보드는 지금까지 열리는지만 검증됐고 무엇을 보여주는지는 검증된 적이 없다.
quality_rubric: `ui-ux-pro-max` — Data-Dense Dashboard 기준(minimal padding · space-efficient · maximum data visibility)과 `--domain ux` Empty States(도움되는 메시지 + 행동). `impeccable` — Cognitive Load 8항 중 Single focus · Chunking · Visual hierarchy · Minimal choices(현재 4항 동시 실패), Working Memory ≤4, The Wall of Options와 The Visual Noise Floor, heuristic 1(Visibility of System Status)·8(Aesthetic and Minimalist Design). `redesign-existing-projects` — "Generic card look(border+shadow+white bg): 카드는 elevation이 위계를 전달할 때만 존재해야 한다", "Three equal card columns", 데이터 UI의 tabular-nums.
current_state: `/dashboard` 최상위 카드 39~40장, 2569px(2.38화면), 표 행 0, contained 버튼 0개. 9구역이 모두 같은 흰 카드. `3`이 3구역, `42.6%`와 `0`이 각 2구역에 중복. 0·- 값도 실제 값과 같은 크기. 「이 줄은 요약입니다…」 문장이 IA를 설명한다. `/my-stats` 카드 12·CTA 0, `/me` 카드 16·CTA 0·7표면 병렬, `/projects` 0건인데 0/- 지표 카드 8장.
user_problem: 「확인이 필요한 항목」 아래 위험 4건이 있는데 그 자리에서 할 수 있는 조치가 없다. 모든 카드가 같은 무게라 위험과 정상이 구분되지 않고, 같은 숫자를 세 번 만나도 같은 사건인지 알 수 없다. 2.4화면을 스크롤하고도 무엇을 해야 할지 모른다.
design_verdict: REBUILD
target_state: 운영자가 대시보드를 열면 첫 화면 안에서 지금 조치가 필요한 것과 그 조치 수단을 보고, 조치할 것이 없으면 「이상 없음」 한 줄을 본다. 같은 수치를 두 번 만나지 않는다.
target_design: 현황판이 아니라 결정 화면으로 다시 만든다. 상단은 조치 대기 목록 하나 — 각 행 「무엇이 · 언제부터 · 영향」 + 기본 조치 버튼 1개(워커 다시 시작 / 실패 잡 보기 / 백업 실행), 조치할 것이 없으면 「이상 없음」 한 줄로 접힘. 정상 지표는 한 줄 요약 스트립(서비스 1/7 · 큐 0 · 디스크 42.6% · 백업 12일 전)으로 접고 클릭 시 해당 화면으로. 중복 구역(인벤토리·시스템 리소스·현재 큐 상태)은 상세 화면으로 내려 같은 수치가 화면에 한 번만 나오게 한다. 0 값 지표는 큰 숫자 카드로 그리지 않고 스트립 안 무채색으로 축약. 설명문 「이 줄은 요약입니다…」 삭제. `/me`는 「오늘 내가 할 일」 하나로 좁히고 채팅·게시판은 사이드바 목적지로 환원, 관리자 착지는 `/dashboard`.
visual_change_required: true
target_visual_delta: 흰 카드 40장의 격자가 사라지고 상단에 조치 목록 하나 + 그 아래 한 줄 지표 스트립이 남는다. 페이지 높이가 2569px에서 1600px 이하로 줄어 스크롤이 거의 사라진다. 위험 항목만 색을 갖고 정상 지표는 무채색이 된다. 「0」이 크게 반복되던 자리가 비워진다.
affected_surfaces: dashboard · home · empty-state (`/projects`의 0 지표), 중복 지표를 넘겨받는 admin-console/table-screens
affected_components: 대시보드 화면 모듈과 stat 카드 컴포넌트 · `/my-stats`·`/me`·`/projects` 화면 모듈 · 로그인 후 착지 라우팅
workflow_change: 조치 동선이 「대시보드에서 발견 → 다른 화면으로 이동 → 조치」에서 「대시보드에서 발견하고 그 자리에서 조치」로 짧아진다. 조치 자체의 권한·확인 절차·결과는 바뀌지 않는다. 관리자 착지가 `/me`에서 `/dashboard`로 바뀐다.
navigation_impact: 관리자 로그인 착지 라우트가 바뀐다. 중복 구역이 상세 화면으로 내려가면서 대시보드 → 상세 링크가 늘어난다. 메뉴 구조 자체는 이 RC에서 바꾸지 않는다(`PA-RC-0017`이 담당).
data_impact: 없음 — 지표의 계산 정의·출처·의미 전부 불변. 값이 재구축 전후 동일해야 하는 것이 완료 조건이다.
api_impact: 없음 — 기존 엔드포인트와 응답 구조 불변. 조치 버튼은 이미 있는 조치 엔드포인트를 호출한다.
rbac_impact: 경계 불변. 조치 버튼은 해당 권한이 있는 역할에게만 보이고 서버가 정본으로 재판단한다. `PA-F-053`이 확인한 「operator에게 쓰기 컨트롤이 보이지 않는다」는 성질을 깨뜨리지 않아야 한다.
browser_verification: 1920×1080 light·dark에서 `/dashboard` 스크린샷 — 첫 화면 안에 조치 항목 + 버튼, 문서 높이 1.5화면 이하, 「이 줄은 요약입니다」 부재. 중복 검사 재실행으로 (값,라벨) 중복 0건. `/projects`·`/me`·`/my-stats` 스크린샷으로 0 값 카드 부재 확인. 역할 4종 로그인 스크린샷으로 조치 버튼 노출 대조. 로딩 중 스크린샷으로 스켈레톤 유지 확인.
evidence_refs: `PRODUCT_AUDIT_DESIGN.md` §2-C·§2-E·§3 dashboard·§3 home·§3 empty-state · `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-060` · 계측 `var/product-audit/probe_shell.json` dup 스캔(값 `3` 3구역 / `42.6%`·`0` 각 2구역) · `var/product-audit/design_capture_admin.json`(topCards 40, contained 0, screensTall 2.38, rows 0) · `design_capture_user.json`(/me topCards 16 contained 0, /my-stats 12/0) · `design_capture2.json` empty[](/projects contained 0) · 스크린샷 `var/product-audit/shots/fhd_admin_dashboard.png`·`fhd_user_me.png`·`empty_projects.png`
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0019 -->
rc_id: PA-RC-0019
severity: Medium
priority: P2
confidence: Confirmed
problem: **어시스턴트 플로팅 버튼이 표 화면 마지막 행의 「상세」 버튼을 실제로 덮어 클릭을 가로챈다.** FAB은 `position: fixed`, `(1826, 986)`, `70×70`, `z-index 1050`이다. 표의 행 조작 버튼 열이 우측 끝(x≈1787~1852)에 있어 뷰포트 하단에서 겹친다. 겹침 중심점에서 `document.elementFromPoint()`를 호출하면 **FAB이 반환된다** — 즉 시각적 근접이 아니라 실제로 위에 있고 히트테스트를 가져간다. 관리자 10라우트 중 **9곳**(`/users`·`/settings`·`/audit`·`/rbac`·`/departments`·`/feature-flags`·`/offboarding` 각 2건, `/jobs`·`/integrations` 각 1건), 사용자 5라우트 중 **1곳**(`/notifications` 2건)에서 재현된다. 겹치지 않는 것은 표가 없는 `/dashboard`뿐이다.
expected: 상시 떠 있는 보조 컨트롤은 본문의 조작 요소를 가리지 않아야 한다. 근거: ② CLAUDE.md §5가 Accessibility와 Keyboard/Focus를 필수 완료 범위로 규정 · ⑤ 제품 자신이 이미 이 원칙을 알고 있다 — `/chat`에서는 FAB과 헤더 어시스턴트 칩이 **사라진다**(맥락 인지 동작). 즉 "이 화면에서는 방해가 된다"는 판단 로직이 이미 존재하고, 표 화면에는 적용되지 않았을 뿐이다.
actual: FAB이 마지막 행의 「상세」 위에 그려지고 그 지점의 클릭을 가져간다. 사용자는 해당 행의 상세를 열려면 스크롤하거나 행 자체를 눌러야 한다(행 클릭이 같은 동작을 하지만 화면은 그 사실을 버튼으로만 광고한다).
intent_evidence: ② CLAUDE.md §5(Accessibility·Keyboard/Focus 필수) · ⑤ `/chat`의 맥락 인지 숨김 구현 — 같은 코드베이스가 이미 조건부 숨김을 한다 · ⑥ `z-index 1050`이라는 값 선택 자체가 "본문 위"를 의도한 것이지 "본문 컨트롤 위"를 의도한 것은 아님을 시사(MUI drawer는 1200, FAB 관례는 1050).
findings: PA-F-061
feature_contracts: FC-어시스턴트진입(어시스턴트를 어디서 어떻게 여는가) — 어시스턴트의 기능·컨텍스트 전달·권한은 바뀌지 않는다. 진입점의 위치와 개수만 바뀐다.
routes: 표가 있는 전 라우트. 실측 확인: `/users`·`/settings`·`/audit`·`/rbac`·`/departments`·`/feature-flags`·`/offboarding`·`/jobs`·`/integrations`·`/notifications`.
frontend: 어시스턴트 FAB 컴포넌트(우하단 고정 버튼) · 그 노출 조건을 결정하는 셸 로직(`/chat`에서 숨기는 기존 분기가 있는 곳) · 표 화면의 행 조작 열(`PA-RC-0023`이 이 열을 없애면 겹칠 대상 자체가 사라진다).
api: 없음.
backend: 없음.
data: 해당 없음.
rbac: 해당 없음 — FAB 노출은 권한과 무관하고 이 변경도 권한을 건드리지 않는다.
integration: 해당 없음 — 어시스턴트가 호출하는 Runner/LLM 경로는 불변.
state_transition: 해당 없음.
user_impact: 표 화면에서 마지막으로 보이는 행의 상세를 버튼으로 열 수 없다. 클릭이 어시스턴트를 여는 것으로 오작동해 사용자가 의도하지 않은 패널이 뜬다. 빈도는 표 화면 전부이므로 낮지 않고, 마우스 사용자와 확대 사용자에게 특히 자주 발생한다.
implementation_direction: **단독으로 z-index만 낮추거나 위치만 옮기지 말 것.** 그렇게 하면 다른 화면에서 다른 것을 가리게 되고 근본 원인(어시스턴트 진입점이 3개)이 남는다. 권장 순서는 (1) `PA-RC-0020`을 먼저 처리해 진입점을 헤더 칩 하나로 모으고 **FAB을 제거**한다 — 그러면 이 RC는 원인 소멸로 닫힌다. (2) `PA-RC-0020`보다 이 건을 먼저 내보내야 한다면, 임시로 FAB이 본문 조작 요소와 겹치지 않도록 하단 여백을 확보하거나(본문 컨테이너에 FAB 높이만큼 padding-bottom) `/chat`에 이미 있는 조건부 숨김을 표 화면으로 확장한다. (3) 어느 쪽이든 **완료 판정은 히트테스트로** 한다 — 시각적으로 안 겹쳐 보이는 것이 아니라 `elementFromPoint`가 본문 컨트롤을 반환해야 한다.
constraints: `/chat`의 기존 맥락 인지 숨김 동작을 깨뜨리지 않는다. 어시스턴트 자체의 접근성(키보드 도달·포커스)을 유지한다. FAB을 제거하는 경우 어시스턴트로 가는 경로가 최소 하나(헤더 칩 + 단축키) 반드시 남아야 한다. `PA-RC-0023`이 「상세」 버튼 열을 제거하면 겹침 대상이 바뀌므로 두 작업의 순서를 확인하고 완료 검증을 재실행할 것.
regression_risk: FAB 제거는 어시스턴트 진입 경로를 줄이므로 어시스턴트 진입 테스트가 깨질 수 있다. z-index 조정 방식을 택하면 모달·드로어·팝오버와의 쌓임 순서가 흔들릴 수 있어 오버레이 전반을 재확인해야 한다. 하단 padding 방식은 표 화면의 스크롤 끝 위치를 바꾼다.
acceptance_criteria: (1) 표가 있는 전 라우트에서 뷰포트 하단 조작 요소 위의 `elementFromPoint`가 **본문 컨트롤을 반환**한다(FAB이 아니다). (2) 실측된 10라우트에서 `blocked` 건수가 **0**이다. (3) 어시스턴트로 가는 경로가 최소 하나 남아 있고 키보드로 도달 가능하다. (4) `/chat`에서 어시스턴트 중복 진입점이 나타나지 않는다(기존 숨김 동작 유지). (5) 모달·드로어가 열렸을 때 쌓임 순서가 정상이다.
required_tests: `var/product-audit/verify_fab.py`의 히트테스트 절차를 `scripts/ui_qa/`에 정식 편입해 표 라우트 전체에서 `blocked=0`을 검증하는 회귀 테스트로 만든다. 어시스턴트 진입 경로 테스트(칩·단축키). 오버레이 쌓임 순서 테스트(FAB·모달·드로어 동시 존재 시).
qa_gaps: `QA_COVERAGE.md`에 「고정 요소와 본문 컨트롤의 겹침」 축이 없다. 이 축은 이번 Cycle이 처음 계측했고, 시각 검사로는 놓치기 쉬워 히트테스트가 필요하다.
quality_rubric: `impeccable` — heuristic 3(User Control and Freedom: 사용자가 의도한 대상을 조작할 수 있어야 한다)·5(Error Prevention), 페르소나 Sam(접근성: 클릭 전용 상호작용과 가려진 타깃). `ui-ux-pro-max` `--domain ux` — Touch & Interaction의 touch-target-size와 z-index-management(z-index 스케일을 정의하라). `redesign-existing-projects` — "Arbitrary z-index values / Content padding: 고정 요소 뒤로 콘텐츠가 숨지 않게".
current_state: 어시스턴트 FAB이 `fixed (1826,986) 70×70 z-index 1050`으로 상시 떠 있고, 표 화면 우측의 행 「상세」 버튼(x≈1787~1852)과 뷰포트 하단에서 겹친다. 관리자 9/10 라우트, 사용자 1/5 라우트에서 `elementFromPoint`가 FAB을 반환한다. `/chat`에서만 FAB이 사라진다.
user_problem: 표 마지막 행의 상세를 버튼으로 열 수 없고, 누르면 어시스턴트가 열린다. 사용자는 왜 버튼이 안 먹는지 알 수 없다.
design_verdict: REDESIGN
target_state: 표 화면 어디에서도 본문 조작 요소가 상시 컨트롤에 가려지지 않는다. 어시스턴트는 헤더에서 열고 표 위에는 아무것도 떠 있지 않다.
target_design: 어시스턴트 진입점을 헤더 칩 하나 + 전역 단축키로 통합하고 우하단 FAB을 제거한다(`PA-RC-0020`과 함께 수행). FAB을 유지해야 하는 경우에는 `/chat`에 이미 있는 조건부 숨김 로직을 표 화면으로 확장하거나 본문 컨테이너에 FAB 높이만큼의 하단 여백을 확보해 겹침 자체를 만들지 않는다. 완료 판정은 시각이 아니라 `elementFromPoint` 히트테스트로 한다.
visual_change_required: true
target_visual_delta: 모든 화면 우하단의 로봇 원형 버튼이 사라지고(또는 표 영역과 겹치지 않는 위치로 이동해) 표의 마지막 행 우측이 온전히 보인다. 헤더의 어시스턴트 칩이 유일한 진입점이 된다.
affected_surfaces: table-screens · ai-assistant-chat · global-header · list-screens(`/notifications`)
affected_components: 어시스턴트 FAB 컴포넌트 · 셸의 FAB 노출 조건 분기 · 헤더 어시스턴트 칩 · 본문 컨테이너 하단 여백
workflow_change: 없음 — 어시스턴트를 여는 클릭 위치가 바뀔 뿐 어시스턴트 사용 절차와 컨텍스트 전달은 동일하다.
navigation_impact: 없음 — 라우트 불변. 어시스턴트 진입점 개수만 3 → 1로 줄어든다.
data_impact: 없음.
api_impact: 없음.
rbac_impact: 없음 — FAB 노출은 권한과 무관하며 변경도 권한 경계를 건드리지 않는다.
browser_verification: 1920×1080 light에서 `/users`·`/settings`·`/audit`·`/rbac`·`/departments`·`/feature-flags`·`/offboarding`·`/jobs`·`/integrations`·`/notifications` 10라우트 스크린샷과 히트테스트 — `blocked=0`. `/chat` 스크린샷으로 중복 진입점 부재 확인. 모달 열린 상태 스크린샷으로 쌓임 순서 확인.
evidence_refs: `PRODUCT_AUDIT_DESIGN.md` §2-D·§3 table-screens·§3 ai-assistant-chat · `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-061` · 계측 `var/product-audit/verify_fab.json`(fab 박스·z-index·라우트별 blocked 수, elementFromPoint 확인) · 프로브 `var/product-audit/verify_fab.py` · 스크린샷 `var/product-audit/shots/fhd_admin_settings.png`(세션 정책 행의 상세를 덮은 장면)·`fhd_admin_users.png`
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0020 -->
rc_id: PA-RC-0020
severity: Medium
priority: P2
confidence: Confirmed
problem: **AI 어시스턴트가 제품 안에서 이름 3종과 진입점 3개로 존재한다.** 한 화면(`/chat`) 안에서만 봐도 breadcrumb은 「도우미 › AI 도우미」, 사이드바 항목은 「AI 도우미」, `h1`은 「채팅」, 패널 제목도 「채팅」이다 — **내비 라벨과 페이지 제목이 다르다.** 제품 전체로 넓히면 헤더 칩 「클로비」, 사이드바 카드 「클로비에게 물어보기」, 온보딩 「클로비가 안내합니다」, `/me`의 섹션 「AI 도우미」가 더해진다. 진입점은 헤더 칩 · 사이드바 카드(264×121, 레일 하단 상시 점유) · 우하단 FAB 셋이고 어느 것이 정본인지 화면이 말하지 않는다. (처음에는 관리자 서비스 상태의 「업무 도우미」를 4번째 이름으로 셌으나, 추적 결과 표시명이 아니라 **DB 조회 키**여서 제외했다 — `constraints`를 반드시 읽어라.)
expected: 하나의 개념은 제품 전체에서 한 이름으로 불려야 하고, 내비 라벨과 도착 화면의 제목이 일치해야 하며, 진입점은 예측 가능한 곳에 하나 있어야 한다. 근거: ② CLAUDE.md §5가 Navigation/IA와 Typography를 필수 범위로 규정 · ② `docs/UX_WRITING.md`(이전 Cycle `PA-RC-0002`의 산출물)가 사용자 문구 규칙을 제품 규칙으로 정한다 · ⑤ 같은 제품의 다른 목적지들은 내비 라벨과 `h1`이 일치한다(「사용자」→「사용자」, 「감사 로그」→「감사 로그」).
actual: 이름 3종(클로비 / AI 도우미 / 도우미), 진입점 3개, 내비 라벨 「AI 도우미」와 페이지 제목 「채팅」 불일치.
intent_evidence: ② CLAUDE.md §5 · ② `docs/UX_WRITING.md` · ⑤ 같은 제품 내 다른 목적지의 라벨-제목 일치 관용 · ✅ **이전에 미확정이던 「업무 도우미」를 확정했다** — 표시명이 아니라 **식별자**다. `app/jobs/handlers/chat_message.py:39`의 `CHAT_WORKFLOW_NAME = "ClovirONE AI 업무 도우미"`가 `:60`에서 `select(Workflow).where(Workflow.name == CHAT_WORKFLOW_NAME)`로 **DB 조회 키**로 쓰이고, `app/integrations/discovery.py:33`의 `clovirone-work-assistant`는 `:8789`에서 도는 **별개의 기존 HTTP 서비스**다. 따라서 이름 통일 대상이 **아니고** 실제 이름은 3종이다.
findings: PA-F-062
feature_contracts: FC-어시스턴트진입 · FC-AI대화(대화 생성·컨텍스트 전달·쿼터) — **기능·컨텍스트·쿼터·권한은 전부 불변.** 부르는 이름과 들어가는 문만 바뀐다.
routes: `/chat`(주), `/me`(AI 도우미 섹션), 어시스턴트 칩·카드·FAB이 보이는 인증된 전 라우트, 관리자 서비스 상태가 보이는 `/dashboard`·`/system`.
frontend: 사이드바 항목 라벨 · breadcrumb 생성부 · `/chat` 화면의 `h1`과 패널 제목 · 헤더 어시스턴트 칩 · 사이드바 어시스턴트 카드 · FAB · 온보딩 모달 문구 · `/me`의 AI 섹션 제목.
api: 없음 — 표시 문자열만 바뀐다. 서비스 상태 응답의 서비스 키는 **바꾸지 않는다**(표시명만 매핑).
backend: 원칙적으로 없음. 관리자 서비스 상태의 표시명이 백엔드에서 오는 경우에만 그 문자열을 조정하되 **서비스 식별자는 불변**이다.
data: 해당 없음 — 데이터 구조·의미 불변.
rbac: 해당 없음 — 어시스턴트 접근 권한과 노출 대상 불변.
integration: 어시스턴트가 Runner/LLM을 호출하는 경로 불변. 서비스 상태가 감시하는 대상 불변.
state_transition: 해당 없음.
user_impact: 사이드바에서 「AI 도우미」를 눌렀는데 도착 화면 제목이 「채팅」이라 같은 곳인지 확신할 수 없다. 문의·문서·교육에서 어떤 이름을 써야 할지 정해지지 않아 조직 내 용어가 갈린다. 진입점 3개는 화면 공간을 낭비하고(사이드바 카드 121px) 본문을 가리며(FAB, `PA-RC-0019`) 무엇이 정본인지 모르게 한다.
implementation_direction: (1) **이름을 하나로 확정한다.** 「클로비」는 어시스턴트의 인격 이름으로 남기고(인사·온보딩·말풍선), **목적지 라벨·breadcrumb·페이지 제목은 한 단어로 통일**한다. 어느 단어를 고르든 상관없으나 **세 곳이 반드시 같아야 한다** — 사이드바 항목 = breadcrumb 마지막 = `h1`. (2) `/me`의 섹션 제목도 같은 단어를 쓴다. (3) **진입점을 헤더 칩 + 전역 단축키 하나로 모으고** 사이드바 카드와 FAB을 제거한다(`PA-RC-0019`가 함께 닫힌다). 사이드바 카드가 사라지면 레일 하단 121px이 내비로 돌아간다(`PA-RC-0017`에 도움). (4) **「업무 도우미」는 이미 확인했고 대상이 아니다** — 다시 조사하지 말고 손대지도 마라(`constraints`의 빨간 항목). (5) 이름 변경은 `docs/UX_WRITING.md`에 용어 규칙으로 등재해 다음 화면이 다시 갈라지지 않게 한다.
constraints: **🔴 `"ClovirONE AI 업무 도우미"` 문자열을 절대 바꾸지 마라.** 표시명이 아니라 `app/jobs/handlers/chat_message.py:39`의 `CHAT_WORKFLOW_NAME` 상수이고 `:60`에서 `select(Workflow).where(Workflow.name == CHAT_WORKFLOW_NAME)`로 **DB 조회 키**로 쓰인다 — 바꾸면 조회가 실패해 **채팅 전체가 멈춘다**(`ChatWorkflowMisconfiguredError`). `app/schedules/router.py:262`도 같은 상수를 참조한다. `app/integrations/discovery.py:33`의 `clovirone-work-assistant`(`:8789` 기존 서비스)도 손대지 않는다(CLAUDE.md §3-9 — 공유 n8n/기존 서비스를 이 작업 때문에 바꾸지 않는다). 그 외 기술 용어·서비스 식별자·API 필드명·상태값도 바꾸지 않는다. 어시스턴트로 가는 경로가 최소 하나 남아야 하고 키보드로 도달 가능해야 한다. `/chat`의 맥락 인지 숨김 동작을 유지한다.
regression_risk: 라벨 변경은 라벨 텍스트로 요소를 찾는 기존 테스트와 `scripts/ui_qa/` 시나리오를 깨뜨린다(전역 검색·명령 팔레트 포함). 진입점 제거는 어시스턴트 진입 경로 테스트를 깨뜨린다. 명령 팔레트/전역 검색이 옛 이름으로 색인하고 있으면 검색 결과가 사라질 수 있으므로 함께 갱신할 것.
acceptance_criteria: (1) 사이드바 항목 라벨 · breadcrumb 마지막 · `/chat`의 `h1` **세 문자열이 동일**하다. (2) `/me`의 AI 섹션 제목이 같은 단어를 쓴다. (3) 어시스턴트 진입점이 **정확히 1개**(헤더 칩)이고 전역 단축키로도 열린다. (4) 사이드바 어시스턴트 카드와 우하단 FAB이 **존재하지 않는다**. (5) 전역 검색/명령 팔레트에서 새 이름으로 어시스턴트를 찾을 수 있다. (6) `"ClovirONE AI 업무 도우미"` 문자열이 소스에서 **바뀌지 않았고**(`chat_message.py`·`schedules/router.py`·`discovery.py`) 채팅 잡이 정상 동작한다. (7) `docs/UX_WRITING.md`에 어시스턴트 용어 규칙이 등재되어 있다.
required_tests: 라벨 일치 테스트(사이드바·breadcrumb·h1 세 문자열 동등성을 단언). 어시스턴트 진입 테스트(헤더 칩·단축키). 전역 검색/명령 팔레트 색인 테스트. `frontend/src/app/command-palette.test.jsx` 갱신. 기존 UI QA 시나리오에서 옛 라벨 참조 제거. **채팅 잡 경로 회귀** — `CHAT_WORKFLOW_NAME`으로 Workflow 행을 찾는 기존 테스트를 이 작업 전후로 반드시 돌려 조회가 계속 성공하는지 확인한다(이 RC가 만들 수 있는 최악의 회귀다).
qa_gaps: `QA_COVERAGE.md`에 Q축(같은 개념이 화면마다 다른 용어로 불리는가) 항목이 없다. 이번 Cycle이 Q축을 처음 정면으로 다뤘고, 어시스턴트 외 다른 개념의 용어 일관성은 **아직 미조사**다.
quality_rubric: `ux-writing` — 라벨은 도착지를 예고해야 한다(내비 라벨과 페이지 제목 일치), 하나의 개념에 하나의 용어. `impeccable` — heuristic 2(Match System / Real World)·4(Consistency and Standards)·6(Recognition Rather Than Recall), 페르소나 Jordan(용어가 사전 지식을 요구하는가). `humanize-korean` — 이름 후보의 한국어 자연스러움 검토에만 적용하고 기술 용어·서비스 식별자는 건드리지 않는다.
current_state: 한 화면(`/chat`)에서 breadcrumb 「도우미 › AI 도우미」, 사이드바 「AI 도우미」, h1 「채팅」이 동시에 쓰인다. 제품 전체로는 「클로비」·「AI 도우미」·「도우미」 3종. 진입점은 헤더 칩·사이드바 카드(264×121)·우하단 FAB 3개. (「업무 도우미」는 표시명이 아니라 워크플로 조회 키라 이 목록에서 제외했다.)
user_problem: 사이드바에서 「AI 도우미」를 눌렀는데 도착 화면 제목이 「채팅」이라 같은 곳인지 확신하기 어렵다. 어시스턴트에 들어가는 문이 3개라 무엇이 정본인지 모른다.
design_verdict: REFINE
target_state: 어시스턴트가 제품 전체에서 한 이름으로 불리고, 사이드바에서 누른 라벨과 도착 화면 제목이 같으며, 진입점은 헤더 한 곳(+단축키)이다.
target_design: 목적지 라벨·breadcrumb 마지막·페이지 `h1`·`/me` 섹션 제목을 한 단어로 통일한다(「클로비」는 인격 이름으로만 유지). 진입점은 헤더 칩 + 전역 단축키 하나로 모으고 사이드바 카드와 FAB을 제거한다 — 카드 제거로 레일 하단 121px이 내비로 돌아가고 FAB 제거로 `PA-RC-0019`의 가림이 원인 소멸한다. 「업무 도우미」는 워크플로 조회 키이므로 그대로 둔다. 확정한 용어를 `docs/UX_WRITING.md`에 규칙으로 등재한다.
visual_change_required: true
target_visual_delta: 사이드바 하단의 「클로비에게 물어보기」 카드(264×121)와 우하단 로봇 FAB이 사라진다. `/chat`의 페이지 제목이 「채팅」에서 사이드바 라벨과 같은 단어로 바뀐다. 레일 하단에 내비 항목이 두 개 더 보이게 된다.
affected_surfaces: ai-assistant-chat · sidebar · global-header · home
affected_components: 사이드바 항목 라벨 · breadcrumb 생성부 · `/chat` 화면 제목 · 헤더 어시스턴트 칩 · 사이드바 어시스턴트 카드 · FAB · 온보딩 모달 문구 · `/me` AI 섹션 · 전역 검색/명령 팔레트 색인
workflow_change: 없음 — 어시스턴트 사용 절차와 컨텍스트 전달은 동일하다. 여는 위치와 부르는 이름만 바뀐다.
navigation_impact: 사이드바 어시스턴트 카드가 사라져 레일 하단 121px이 내비 항목으로 돌아간다. 목적지 라벨 문자열이 바뀌므로 전역 검색·명령 팔레트 색인을 함께 갱신한다. 라우트는 불변.
data_impact: 없음 — 데이터 구조·의미 불변. 서비스 식별자는 표시명만 매핑하고 키는 그대로 둔다.
api_impact: 없음 — 표시 문자열만 바뀐다. 응답의 서비스 키 불변.
rbac_impact: 없음 — 어시스턴트 접근 권한과 노출 대상 불변.
browser_verification: 1920×1080 light에서 `/chat` 스크린샷 — 사이드바 라벨·breadcrumb·h1 세 문자열이 화면에서 동일함을 육안 확인. 전 라우트에서 FAB·사이드바 카드 부재 확인. `/me` 스크린샷으로 섹션 제목 일치 확인. 전역 검색에 새 이름 입력 후 결과 확인.
evidence_refs: `PRODUCT_AUDIT_DESIGN.md` §3 ai-assistant-chat·§3 sidebar·§3 global-header · `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-062` · 스크린샷 `var/product-audit/shots/fhd_user_chat.png`(breadcrumb 「도우미 › AI 도우미」와 h1 「채팅」 동시 존재)·`fhd_user_me.png`(「클로비에게 물어보기」 카드와 「AI 도우미」 섹션 공존)·`fhd_admin_dashboard.png`(서비스 상태의 「업무 도우미」) · 계측 `var/product-audit/verify_nav.json` card box (0,959,264,121) · `verify_fab.json` fab (1826,986,70,70)
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0021 -->
rc_id: PA-RC-0021
severity: Medium
priority: P2
confidence: Confirmed
problem: **색 토큰과 일부 표면이 다크 테마에 참여하지 않는다.** 다크 팔레트 자체는 잘 만들어져 있다 — 토글하면 `body`가 `rgb(9,14,29)`(순흑이 아닌 틴티드 다크)가 되고 화면당 대비 실패가 1~2건뿐이다. 문제는 참여하지 않는 것들이다. (1) **온보딩 다이얼로그가 다크에서 흰색으로 남는다** — 어두운 앱 위에 흰 카드 하나가 떠 있다. (2) **알림 배지**가 흰 12px on `rgb(255,139,155)` = **2.23:1**(기준 4.5)로 전 화면 공통 실패다. (3) `/me` **활성 탭** 「오늘 브리핑」이 `rgb(83,108,214)` on `rgb(17,24,45)` = **3.76:1** — 브랜드 인디고 `#536CD6`을 다크 표면에 밝기 재도출 없이 그대로 썼다. (4) **`prefers-color-scheme: dark`를 첫 로드에서 따르지 않는다** — OS가 다크여도 `rgb(245,247,252)`로 칠하고 헤더의 「다크 모드로 전환」을 눌러야 바뀐다. 넷 중 (1)~(3)은 같은 원인이다: 브랜드·의미 색과 일부 surface가 테마별로 재도출되지 않고 라이트 값을 재사용한다.
expected: 테마를 전환하면 모든 표면과 색이 함께 전환되어야 하고, 텍스트 대비는 두 테마 모두에서 WCAG AA(일반 4.5:1, 큰 글자 3:1)를 만족해야 하며, OS 선호를 첫 로드에서 존중해야 한다. 근거: ② CLAUDE.md §5가 "Light/Dark"와 Accessibility를 필수 완료 범위로 규정 · ② D-75가 "더 완성도 높은 Light/Dark Theme"를 목표로 명시 · ⑤ 같은 제품의 나머지 표면이 이미 정확히 전환된다 — 즉 규범은 존재하고 일부가 빠졌을 뿐이다.
actual: 온보딩 모달이 다크에서 흰색. 알림 배지 2.23:1. `/me` 활성 탭 3.76:1. OS 다크 선호를 첫 로드에서 무시.
intent_evidence: ② CLAUDE.md §5 · ② `docs/DECISIONS.md` D-75 · ⑤ 다크 팔레트의 나머지 구현 품질 자체가 의도의 증거다(틴티드 다크 선택, 카드/보더/본문 텍스트 전부 정상 전환).
findings: PA-F-063
feature_contracts: 해당 없음 — 기능 계약이 아니라 표현 계층이다. 테마 전환 기능 자체의 동작(토글·저장)은 바뀌지 않는다.
routes: 인증된 전 라우트(배지·테마는 셸에서 그려진다). 온보딩 모달은 첫 방문 시 `/me`. 활성 탭은 `/me` 및 같은 탭 컴포넌트를 쓰는 화면 전체.
frontend: 테마 정의/토큰 파일(브랜드·의미 색의 라이트/다크 값) · 온보딩 다이얼로그 컴포넌트(테마 밖에서 색을 지정하고 있을 가능성이 높으나 **확인 후 판단할 것**) · 알림 배지 컴포넌트 · 탭 컴포넌트의 활성 색 · 테마 초기값 결정 로직(`prefers-color-scheme` 반영 지점).
api: 없음.
backend: 없음.
data: 해당 없음.
rbac: 해당 없음.
integration: 해당 없음.
state_transition: 해당 없음 — 테마 상태의 저장/복원 규약은 그대로 두고 초기값만 OS 선호를 반영한다.
user_impact: OS를 다크로 쓰는 사용자가 로그인 직후 밝은 화면을 맞고 매번 토글해야 한다(저장되면 1회). 다크로 쓰는 동안 알림 개수가 잘 안 읽히고, 첫 방문 온보딩에서 흰 카드가 튀어 완성도가 낮아 보인다. 대비 실패 2건은 저시력 사용자에게 실제 판독 문제다.
implementation_direction: (1) **브랜드·의미 색을 테마별로 재도출한다** — 다크에서는 배경 대비 4.5:1을 만족하도록 명도를 올린 값을 쓴다. 색을 하나씩 고치지 말고 **토큰 층에서** 고쳐야 같은 색을 쓰는 다른 자리가 함께 낫는다. (2) **온보딩 다이얼로그가 왜 테마 밖에 있는지 먼저 확인한다** — 하드코딩된 흰 배경인지, 테마 프로바이더 밖에 마운트되는지 확인하고 원인에 맞게 고친다(추정으로 색만 덮어쓰지 말 것). (3) **테마 초기값이 `prefers-color-scheme`를 반영하게 한다.** 사용자가 명시적으로 선택한 값이 있으면 그것이 우선이고, 없을 때만 OS 선호를 따른다. 첫 페인트에서 밝은 화면이 번쩍이지 않도록 초기 스크립트 단계에서 결정할 것. (4) 수정 후 **두 테마 모두**에서 대비를 재측정한다 — 다크만 고치다 라이트를 깨뜨리는 것이 흔한 회귀다.
constraints: 라이트 테마의 현재 대비를 낮추지 않는다. 브랜드 색의 정체성을 유지하되 다크에서는 명도만 조정한다(색상 자체를 바꾸지 않는다). 색만으로 의미를 전달하지 않는다는 원칙을 유지한다(배지는 숫자를 함께 보여준다 — 이미 그렇다). `docs/DECISIONS.md`의 CSP 정책상 인라인 스타일 주입 방식이 제약될 수 있으므로 테마 초기화 방식은 기존 관례를 따를 것.
regression_risk: 토큰 층 수정은 **두 테마 전 화면**에 퍼지므로 반경이 크다. 다크 대비를 올리려 명도를 높이면 라이트에서 같은 토큰이 흐려질 수 있다 — 반드시 테마별로 분리된 값을 쓸 것. `prefers-color-scheme` 반영은 기존 테마 저장/복원 테스트와 로그인 흐름 스냅샷을 흔든다. 온보딩 모달 수정이 다른 다이얼로그의 마운트 위치를 건드리면 포커스 관리가 깨질 수 있다.
acceptance_criteria: (1) 다크에서 온보딩 다이얼로그의 배경이 **다크 표면 색**이고 텍스트 대비가 4.5:1 이상이다. (2) 알림 배지가 **두 테마 모두** 4.5:1 이상이다. (3) `/me` 활성 탭이 **두 테마 모두** 4.5:1 이상이다. (4) 대표 5화면 × 2테마에서 대비 실패가 **0건**이다(그라디언트 위 텍스트는 별도 측정). (5) OS가 다크일 때 로그인 직후 첫 화면이 **다크로 렌더**된다. (6) 사용자가 명시적으로 고른 테마가 있으면 OS 선호보다 우선한다. (7) 라이트 테마의 대비가 수정 전보다 나빠지지 않는다.
required_tests: 대비 계산 테스트를 `scripts/ui_qa/contrast.py`(이미 존재) 기반으로 두 테마 × 대표 화면에 대해 회귀로 고정. 테마 초기값 결정 로직 단위 테스트(OS 선호 / 저장된 선택 / 우선순위). 온보딩 다이얼로그 렌더 테스트(두 테마). `var/product-audit/verify_dark.py`의 절차를 정식 QA로 편입하되 **그라디언트 배경 처리 버그를 고친 버전**을 쓸 것(§0-B 참조).
qa_gaps: `QA_COVERAGE.md`의 O축(Light/Dark)이 "동작 확인" 수준이고 **대비 수치 기준이 없다**. `prefers-color-scheme` 초기값 축은 아예 없다. 온보딩 모달은 다크에서 검증된 적이 없다.
quality_rubric: `ui-ux-pro-max` — Accessibility 최우선 항목 color-contrast(일반 텍스트 4.5:1) 및 Light/Dark Mode Contrast 체크리스트(두 모드 모두 테스트, 경계 가시성). `impeccable` — heuristic 4(Consistency and Standards), 페르소나 Sam(대비 4.5:1, 색만으로 의미 전달 금지). `redesign-existing-projects` — "Random dark sections in a light mode page (or vice versa) … looks like a copy-paste accident"(온보딩 모달이 정확히 이 패턴의 반전), "Pure #000000 배경 대신 틴티드 다크"(이미 충족).
current_state: 토글 시 `body`가 `rgb(9,14,29)`로 정상 전환되고 화면당 대비 실패 1~2건. 그러나 온보딩 다이얼로그는 다크에서 흰색으로 남고, 알림 배지는 2.23:1, `/me` 활성 탭은 3.76:1이며, `prefers-color-scheme: dark`는 첫 로드에서 무시된다(`rgb(245,247,252)`).
user_problem: OS를 다크로 쓰면 로그인 직후 밝은 화면을 맞고, 다크로 쓰는 동안 알림 개수가 잘 안 읽히며, 첫 방문 온보딩에서 흰 카드가 튄다.
design_verdict: REFINE
target_state: 테마를 전환하면 온보딩 모달을 포함한 모든 표면이 함께 전환되고, 두 테마 모두에서 텍스트 대비가 WCAG AA를 만족하며, OS가 다크면 첫 화면부터 다크다.
target_design: 브랜드·의미 색을 토큰 층에서 테마별로 재도출한다(다크는 배경 대비 4.5:1을 만족하도록 명도 상향, 색상은 유지). 온보딩 다이얼로그가 테마 밖에 있는 원인을 확인해 테마에 편입한다. 테마 초기값은 사용자의 명시적 선택 > `prefers-color-scheme` 순으로 결정하고, 첫 페인트에서 밝은 화면이 번쩍이지 않도록 초기화 단계에서 정한다. 수정 후 두 테마 모두 재측정한다.
visual_change_required: true
target_visual_delta: 다크 모드에서 온보딩 다이얼로그가 흰 카드에서 어두운 카드로 바뀐다. 알림 배지의 분홍 배경이 흰 글자와 충분히 대비되는 값으로 짙어진다. `/me` 활성 탭의 인디고 밑줄·글자가 다크 배경에서 또렷해진다. OS가 다크인 사용자는 로그인 직후 화면이 어둡다.
affected_surfaces: global-header(배지) · modal-drawer(온보딩) · home(활성 탭) · 전 표면(토큰 층 변경의 파급)
affected_components: 테마 토큰 정의(브랜드·의미 색의 라이트/다크 값) · 온보딩 다이얼로그 · 알림 배지 · 탭 컴포넌트 활성 상태 · 테마 초기값 결정 로직
workflow_change: 없음 — 업무 절차 불변. OS 다크 사용자가 매번 토글하던 동작이 사라진다.
navigation_impact: 없음.
data_impact: 없음.
api_impact: 없음.
rbac_impact: 없음.
browser_verification: 1920×1080에서 대표 5화면(`/dashboard`·`/users`·`/settings`·`/me`·`/chat`)을 light·dark 양쪽으로 스크린샷하고 대비 실패 0건을 계측. 첫 방문 상태로 `/me`를 다크에서 열어 온보딩 다이얼로그가 어두운 스크린샷. `color_scheme=dark` 컨텍스트로 로그인해 토글 없이 첫 화면이 다크인지 확인.
evidence_refs: `PRODUCT_AUDIT_DESIGN.md` §2-F·§3 global-header · `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-063` · 계측 `var/product-audit/verify_dark.json`(prefersDarkHonoredOnLoad=rgb(245,247,252), 토글 후 rgb(9,14,29), 배지 2.23:1, 활성 탭 3.76:1) · 프로브 `var/product-audit/verify_dark.py` · 스크린샷 `var/product-audit/shots/dark3_user_me.png`(다크 앱 위 흰 온보딩 모달)·`dark3_admin_dashboard.png`·`dark3_admin_settings.png`·`dark3_user_chat.png`
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0022 -->
rc_id: PA-RC-0022
severity: Medium
priority: P2
confidence: Confirmed
problem: **화면이 스스로 설명하는 대신 상단 안내 문단으로 자기 구조를 설명한다.** 안내 패널이 붙은 화면이 최소 8개다 — `/settings`(4문단) · `/rbac`(260자) · `/offboarding`(220자) · `/prompts`(162자) · `/system`(139자) · `/feature-flags`(135자) · `/users`(5줄 블록) · `/diagnostics`(183px + 218px 두 블록). 가장 뚜렷한 것은 `/settings`인데, 안내문이 하는 일이 **설정이 6개 화면에 나뉘어 있다는 사실을 알려주는 것**이다(「유지보수 모드, 점검 공지는 '유지보수' 화면에서」 / 「AI 설정은 'AI 관리' 화면에서」 / 「(이 표의 값과 달리 되돌릴 수 없는 실행 동작이라 화면을 분리했습니다)」). 같은 화면 하단에는 **브라우저에만 저장되는 개인 설정 「화면 강조색」이 전역 시스템 정책 표와 같은 화면에** 있고, 그 차이 역시 산문으로만 구분된다(「지금 쓰는 브라우저에만 저장되는 개인 설정이라… (위 표의 시스템 설정과 다릅니다)」). 대시보드에도 같은 패턴이 있다(「이 줄은 요약입니다…」, `PA-RC-0018`). 덧붙여 `/settings` 표는 `conversation_retention_days`·`ui_branding`·`lockout_policy` 같은 **백엔드 키를 사용자용 열로 노출**한다.
expected: 화면 구조가 스스로 의미를 전달해야 하고, 도움말은 상시 패널이 아니라 필요할 때 꺼내는 것이어야 하며, 서로 다른 적용 범위(전역 정책 / 개인 설정)는 배치로 구분되어야 한다. 근거: ② `docs/UX_WRITING.md`(이전 Cycle `PA-RC-0002` 산출물)가 사용자 문구 규칙을 제품 규칙으로 정한다 · ② D-75가 IA/Page 구조/Component 구조 재편을 보존 의무 없는 영역으로 명시 · ⑤ 안내문이 없어도 성립하는 화면이 같은 제품에 다수 존재한다(`/board`·`/team-docs`·`/audit`).
actual: 8화면에 상시 안내 패널이 있고, 그중 `/settings`의 것은 IA 결함(6화면 분산 + 스코프 혼재)을 문구가 흡수하는 형태다. 백엔드 키가 사용자용 열로 노출된다.
intent_evidence: ② `docs/UX_WRITING.md` · ② `docs/DECISIONS.md` D-75 · ⑤ 안내문 없이 성립하는 동일 제품 내 화면들 · ⑥ 안내문의 괄호 문장 「(이 표의 값과 달리 되돌릴 수 없는 실행 동작이라 화면을 분리했습니다)」는 **개발자가 화면 분리의 이유를 사용자에게 변명하고 있다는** 1차 증거다 — 구조가 자명했다면 쓸 필요가 없는 문장이다.
findings: PA-F-064
feature_contracts: FC-시스템설정(각 설정 항목의 의미·적용 시점·되돌리기 가능 여부) — **설정 항목의 의미·검증·적용 시점·버전 기록은 전부 불변.** 되돌릴 수 없는 동작의 안전 절차도 불변이다. 바뀌는 것은 어디에 어떻게 놓느냐다.
routes: `/settings`(주) · `/rbac` · `/offboarding` · `/prompts` · `/system` · `/feature-flags` · `/users` · `/diagnostics`. `PA-RC-0017`의 설정 통합이 완료되면 대상 화면 목록이 줄어든다.
frontend: 각 화면의 안내 패널 컴포넌트 · `/settings`의 설정 표(키 열)와 「화면 강조색」 섹션 · 열 토글/상세 패널 컴포넌트 · 제목 옆 도움말 토글(신설 대상) · 개인 설정이 이사 갈 계정 메뉴 영역.
api: 없음 — 설정 조회/변경 엔드포인트와 응답 구조 불변. 키 열을 숨기는 것은 표시 문제이지 API가 덜 주는 문제가 아니다.
backend: 없음.
data: 해당 없음 — 설정 값의 저장 구조·의미 불변. 개인 설정(강조색)의 저장 위치(브라우저 로컬)도 그대로 유지한다.
rbac: 설정 화면의 권한 요구 불변. 개인 설정을 계정 메뉴로 옮길 때 **모든 역할이 자기 개인 설정에 접근할 수 있어야** 한다(현재는 관리자 설정 화면 안에 있어 사실상 관리자만 쓸 수 있다 — 이 이동은 접근을 넓히지만 그것은 개인 표시 설정이므로 권한 경계 위반이 아니다. 다만 **의도한 변경임을 명시**한다).
integration: 「Notion 관리」·「AI 관리」 안내가 가리키는 연동 화면은 `PA-RC-0017`이 탭으로 통합한다. 연동 동작 자체는 불변.
state_transition: 되돌릴 수 없는 실행 동작(서비스 재시작·DNS·시간대·복구)의 확인 절차를 **반드시 보존**한다. 안내문을 없앤다고 안전장치를 없애는 것이 아니다.
user_impact: 사용자가 화면을 이해하려면 매번 문단을 읽어야 하고, `/settings`에서는 문단을 읽고도 다른 화면으로 이동해야 한다. 「화면 강조색」을 바꾸면 다른 사람 화면도 바뀌는지 알려면 괄호 문장을 찾아 읽어야 한다 — 전역 정책과 개인 설정이 한 화면에 있는 것 자체가 오조작 위험이다.
implementation_direction: (1) **안내문을 상시 패널에서 제목 옆 도움말 토글로 옮긴다** — 내용을 지우는 것이 아니라 기본 접힘으로 바꾼다. (2) **`/settings`의 안내 4문단은 `PA-RC-0017`의 탭 통합으로 없앤다** — 탭이 생기면 "어디에 있는지" 설명할 필요가 사라진다. 두 RC는 함께 처리하는 것이 자연스럽다. (3) **개인 설정(화면 강조색·테마)을 시스템 설정 화면에서 분리해 계정 메뉴 아래 「내 화면 설정」으로 옮긴다.** (4) **백엔드 키 열을 기본 숨김**으로 내리고 상세 패널이나 열 토글로 제공한다 — 운영자에게 유용하므로 없애지 말고 접을 것. (5) 대시보드의 「이 줄은 요약입니다…」는 `PA-RC-0018`이 담당한다. (6) **완료 판정 기준**: 안내문을 접었을 때 사용자가 화면을 이해하지 못한다면 그것은 안내문이 아니라 구조를 고쳐야 한다는 신호다 — 접기만 하고 끝내지 말 것.
constraints: 안내문의 **내용을 삭제하지 않는다**(접거나 이동시킨다). 되돌릴 수 없는 동작의 확인 절차 보존. 설정 항목의 의미·검증·버전 기록 불변. 백엔드 키를 **완전히 제거하지 않는다**(운영 디버깅 가치가 있다). 개인 설정의 저장 위치와 범위를 바꾸지 않는다(브라우저 로컬 유지). `docs/UX_WRITING.md`의 기존 규칙과 충돌하지 않게 하고, 새로 정한 원칙은 그 문서에 등재한다.
regression_risk: 안내문을 접으면 그 텍스트를 DOM에서 찾는 기존 테스트가 깨진다. 개인 설정 이동은 강조색 저장/복원 경로를 건드리므로 테마·강조색 영속성 회귀 위험이 있다. 키 열 숨김은 그 열을 참조하는 UI QA 시나리오를 깨뜨린다. `PA-RC-0017`과 동시에 진행하면 `/settings` 화면이 크게 바뀌므로 두 작업의 완료 검증을 합쳐서 할 것.
acceptance_criteria: (1) 대상 8화면에서 상시 안내 패널이 **기본 접힘**이고 제목 옆 도움말로 펼칠 수 있다. (2) 안내문의 **내용이 보존**되어 있다(문자열 대조). (3) `/settings`에서 "다른 설정이 어느 화면에 있는지" 설명하는 문장이 **불필요해졌다**(탭 통합 완료 시). (4) 개인 설정(화면 강조색·테마)이 시스템 설정 화면에 **없고** 계정 메뉴에서 접근된다. (5) 모든 역할이 자기 개인 설정에 접근할 수 있다. (6) 백엔드 키가 기본 표시에서 **빠져 있고** 열 토글/상세로 접근 가능하다. (7) 되돌릴 수 없는 동작이 확인 절차 없이 실행되지 않는다. (8) 강조색 선택이 새로고침 후에도 유지된다.
required_tests: 안내 패널 접힘/펼침 컴포넌트 테스트와 내용 보존 단언. 개인 설정 이동 후 강조색·테마 영속성 테스트(역할 4종). 키 열 토글 테스트. 되돌릴 수 없는 동작의 확인 절차 테스트. `/settings`·`/rbac`·`/offboarding` 렌더 회귀.
qa_gaps: `QA_COVERAGE.md`에 「화면이 안내문 없이 이해되는가」를 판정하는 축이 없고, 「전역 설정과 개인 설정의 분리」도 없다. 개인 설정의 적용 범위(브라우저 로컬 vs 전역)는 검증된 적이 없다.
quality_rubric: `ux-writing` — 도움말은 필요한 순간에 제공하고 상시 노출로 화면을 채우지 않는다, 라벨과 구조가 먼저 설명하고 문구는 보조한다. `impeccable` — heuristic 2(Match System / Real World: 백엔드 키는 사용자 언어가 아니다)·8(Aesthetic and Minimalist Design)·10(Help and Documentation: 맥락 도움말), Cognitive Load의 The Jargon Barrier와 Progressive Disclosure. `ui-ux-pro-max` `--domain ux` — 정보 위계와 Progressive Disclosure.
current_state: 8화면에 상시 안내 패널이 있다(`/settings` 4문단 · `/rbac` 260자 · `/offboarding` 220자 · `/prompts` 162자 · `/system` 139자 · `/feature-flags` 135자 · `/users` 5줄 · `/diagnostics` 2블록). `/settings` 안내문은 설정이 6화면에 흩어져 있다는 사실을 설명하고, 같은 화면에 브라우저 로컬 개인 설정 「화면 강조색」이 전역 정책 표와 함께 있으며 그 차이도 산문으로만 구분된다. 설정 표는 백엔드 키를 사용자용 열로 노출한다.
user_problem: 화면을 이해하려면 매번 문단을 읽어야 하고, `/settings`에서는 읽고도 다른 화면으로 이동해야 한다. 「화면 강조색」이 나만 바뀌는 건지 전체가 바뀌는 건지 괄호 문장을 찾아 읽어야 안다.
design_verdict: REDESIGN
target_state: 사용자가 안내문을 읽지 않고도 화면의 목적과 조작 방법을 파악하고, 필요할 때만 도움말을 펼친다. 전역 정책과 개인 설정이 서로 다른 곳에 있어 적용 범위를 착각하지 않는다.
target_design: 상시 안내 패널을 제목 옆 도움말 토글로 옮겨 기본 접힘으로 만든다(내용은 보존). `/settings`의 안내 4문단은 `PA-RC-0017`의 탭 통합으로 불필요해져 삭제한다. 개인 설정(화면 강조색·테마)을 시스템 설정에서 떼어 계정 메뉴 아래 「내 화면 설정」으로 옮긴다. 설정 표의 백엔드 키 열은 기본 숨김 + 열 토글/상세 패널로 내리고 사용자용 열은 항목명·현재 값·적용 범위·마지막 변경으로 구성한다. 「기본값」 배지 10개는 없애고 「수정됨」만 표시한다.
visual_change_required: true
target_visual_delta: 8화면 상단의 파란 안내 박스가 사라지고 제목 옆에 작은 도움말 아이콘이 생긴다. `/settings`에서 4문단 박스와 하단 「화면 강조색」 섹션이 사라지고 탭 줄이 그 자리에 온다. 설정 표에서 `conversation_retention_days` 같은 키 열이 사라지고 「기본값」 알약 10개가 없어져 「수정됨」 1개만 남는다.
affected_surfaces: settings · navigation-ia · admin-console · key-workflows · table-screens · error-state
affected_components: 각 화면의 안내 패널 · `/settings` 설정 표(키 열·상태 배지)와 「화면 강조색」 섹션 · 제목 옆 도움말 토글(신설) · 계정 메뉴
workflow_change: 개인 표시 설정을 바꾸는 경로가 「관리자 설정 화면 하단」에서 「계정 메뉴 → 내 화면 설정」으로 바뀐다. 시스템 정책 변경 절차와 권한은 불변이다.
navigation_impact: 개인 설정이 계정 메뉴로 이동한다. `/settings`의 안내문 제거는 `PA-RC-0017`의 탭 통합에 의존한다. 라우트 자체는 이 RC에서 바꾸지 않는다.
data_impact: 없음 — 설정 값의 저장 구조·의미 불변. 개인 설정의 저장 위치(브라우저 로컬)도 그대로다.
api_impact: 없음 — 설정 조회/변경 엔드포인트와 응답 구조 불변. 키 열 숨김은 표시 계층 변경이다.
rbac_impact: 시스템 설정의 권한 요구 불변. 개인 설정이 계정 메뉴로 옮겨가면서 모든 역할이 자기 표시 설정에 접근하게 되는데, 이는 **의도한 변경**이며 전역 정책 권한과는 무관하다.
browser_verification: 1920×1080 light·dark에서 8화면 스크린샷 — 상시 안내 박스 부재, 도움말 토글 존재, 펼쳤을 때 내용 동일. `/settings` 스크린샷 — 4문단 부재, 키 열 부재, 「기본값」 배지 부재, 「화면 강조색」 섹션 부재. 계정 메뉴에서 「내 화면 설정」 스크린샷을 역할 4종으로 확인.
evidence_refs: `PRODUCT_AUDIT_DESIGN.md` §2-G·§3 settings·§3 navigation-ia·§3 admin-console · `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-064` · 계측 `var/product-audit/probe_shell.json` intro[](8화면의 안내 패널 위치·높이·글자수) · 스크린샷 `var/product-audit/shots/fhd_admin_settings.png`(4문단·키 열·기본값 배지 10개·화면 강조색 섹션)·`fhd_admin_users.png`·`fhd_admin_rbac.png`·`fhd_admin_diagnostics.png`
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0023 -->
rc_id: PA-RC-0023
severity: High
priority: P1
confidence: Confirmed
problem: **동작 위계 규범이 제품에 퍼지지 않아 양쪽 극단이 동시에 존재한다.** 한쪽 끝: **기본 동작이 아예 없는 화면**이 관리자 16개 중 **10개**, 사용자 10개 중 **4개**다(`contained` 버튼 0개). 특히 최상단 구역명이 「확인이 필요한 항목」인 `/dashboard`에 조치 버튼이 하나도 없고, `/scheduler-calendar`는 버튼 33개에 기본 동작 0개, `/offboarding`은 버튼 27개에 0개다. 빈 상태도 마찬가지여서 `/my-tickets`·`/projects`·`/team-docs/trash`가 전부 `contained` 0이다. 반대쪽 끝: **상세 모달 안에 기본 동작이 3개**이고 그중 파괴적 동작이 섞여 있다 — `/users` 상세는 「비활성화」·「보관」·「수정」 3개가 전부 `contained`, `/departments` 상세는 「수정」·「비활성화」·**「삭제」** 3개가 전부 `contained`다. 셋째 증상: 표 화면의 행마다 붙은 「상세」 버튼이 **행 클릭과 같은 일을 한다**(`/users` 안내문이 「행을 누르면 상세에서…」라고 명시). 즉 잉크는 쓰는데 정보를 더하지 않는다.
expected: 화면마다 기본 동작이 정확히 하나이고 시각적으로 그렇게 보여야 하며, 파괴적 동작은 기본 동작과 구분되는 처리를 받아야 한다. 근거: ② D-75가 "Primary Action이 분명한가"와 "Button hierarchy"를 판정 항목으로 명시 · ② CLAUDE.md §5가 "Action hierarchy"를 필수 개선 범위로 규정 · ⑤ **같은 제품이 이미 옳게 하고 있다** — `/users` 목록은 `+ 사용자 추가`(contained) + `CSV 내보내기/가져오기`(outlined)로 정확하고, 생성 모달은 「취소」(text) + 「추가」(contained) 하나씩이다. 규범이 없는 것이 아니라 퍼지지 않았다.
actual: 14개 화면에 기본 동작 0개, 상세 모달에 기본 동작 3개(파괴적 동작 포함), 표에 중복 「상세」 버튼 열.
intent_evidence: ② `docs/DECISIONS.md` D-75 · ② CLAUDE.md §5 · ⑤ `/users` 목록과 생성 모달의 올바른 대조 구현 — 같은 컴포넌트 체계로 정확한 위계가 이미 성립한다.
findings: PA-F-065
feature_contracts: FC-사용자관리 · FC-부서관리 · FC-오프보딩(각 동작의 권한·확인 절차·결과) — **동작의 존재·권한·확인 절차·결과는 전부 불변.** 바뀌는 것은 어떤 버튼이 어떤 강조를 받고 어디에 놓이는가다.
routes: 기본 동작 0개인 14화면 — 관리자 `/dashboard`·`/audit`·`/jobs`·`/settings`·`/system`·`/rbac`·`/feature-flags`·`/offboarding`·`/scheduler-calendar`·`/diagnostics`(일부), 사용자 `/me`·`/my-tickets`·`/notifications`·`/my-stats`. 상세 모달 — `/users`·`/departments`·`/audit`. 중복 「상세」 열 — 표가 있는 전 라우트.
frontend: 버튼 variant 규범을 정의할 공용 위치(디자인 토큰/컴포넌트 층) · 각 화면의 액션 영역 · 상세 모달 컴포넌트의 액션 그룹 · 표 컴포넌트의 행 조작 열 · 위험 동작용 버튼 변형(신설 대상).
api: 없음 — 동작이 호출하는 엔드포인트 불변.
backend: 없음.
data: 해당 없음.
rbac: **경계 불변이며 회귀 위험이 높다.** 화면에 기본 동작을 세울 때 그 동작의 권한이 없는 역할에게 버튼이 보이면 안 된다. 이전 Cycle이 확인한 성질(`PA-F-053`: `operator`에게 쓰기 컨트롤이 10화면 전부에서 보이지 않는다)이 유지되어야 한다. 서버 authorization은 지금처럼 정본이다.
integration: 해당 없음.
state_transition: 파괴적 동작(삭제·비활성화·보관)의 **확인 절차와 상태 전이 규칙을 그대로 유지**한다. 시각 처리만 바꾼다.
user_impact: 화면 절반에서 "지금 무엇을 하면 되는가"가 시각적으로 표시되지 않아 사용자가 버튼을 찾아 훑어야 한다. 반대로 상세 모달에서는 「삭제」가 「수정」과 똑같은 채운 버튼이라 **오조작 위험이 실제로 높다**. 표의 중복 「상세」 버튼 20개는 시선을 끌면서 행 클릭 이상의 것을 주지 않는다.
implementation_direction: (1) **버튼 위계 규범을 한 곳에 정의한다** — 화면/오버레이당 `contained` 정확히 1개, 보조는 `outlined`, 나머지는 `text`, 파괴적 동작은 **위험 스타일 + 별도 그룹 + 확인 단계**. 규범을 문서가 아니라 **컴포넌트와 정적 검사로** 강제하는 편이 이 저장소의 관례에 맞다(`scripts/check_typography_literals.py`가 같은 방식으로 타이포 토큰을 강제한 선례가 있다 — `PA-RC-0001`). (2) **기본 동작이 없는 14화면에 그 화면의 목적에 맞는 기본 동작을 세운다** — 예: `/notifications` 「모두 읽음」, `/my-tickets` 「새 티켓」, `/dashboard`는 `PA-RC-0018`의 조치 버튼. 억지로 만들지 말고 **그 화면에서 실제로 가능한 것**을 고를 것. (3) **상세 모달의 `contained`를 1개로 줄인다** — 「수정」만 primary, 「비활성화」·「보관」·「삭제」는 위험 스타일 별도 그룹. (4) **표의 행 「상세」 버튼 열을 제거**하고 행 클릭으로 통일하되 **키보드 도달을 반드시 유지**한다(행에 `tabindex`와 Enter 처리). 이 제거는 `PA-RC-0019`의 FAB 겹침 대상도 없앤다. (5) 빈 상태에 그 화면에서 가능한 다음 행동을 버튼으로 올린다(`PA-RC-0018`과 공유).
constraints: 파괴적 동작의 확인 절차를 **절대 제거하지 않는다** — 시각 강조를 낮추는 것과 안전장치를 없애는 것은 다르다. 행 「상세」 버튼 제거 시 **키보드·스크린리더 사용자의 도달 경로를 반드시 보존**한다(이것이 이 작업의 최대 위험이다). 권한 없는 역할에게 새 기본 동작 버튼이 노출되지 않아야 한다. 기존에 올바른 화면(`/users` 목록·생성 모달)의 위계를 **바꾸지 말 것** — 그것이 표준이다. CLAUDE.md §3-8(제품 기능 경계)을 넘는 새 동작을 이 작업을 빌미로 추가하지 않는다.
regression_risk: (1) **접근성 회귀가 가장 크다** — 행 버튼을 없애면 키보드 사용자가 상세에 도달할 수단을 잃을 수 있다. (2) RBAC 회귀 — 새 기본 동작이 권한 없는 역할에 노출. (3) 파괴적 동작의 시각 강등이 발견성을 낮춰 사용자가 기능을 못 찾을 수 있다. (4) 정적 검사를 도입하면 기존 화면 다수가 한꺼번에 실패하므로 예외 목록 관리 방식을 `check_typography_literals.py` 선례에 맞출 것. (5) 표 컴포넌트 변경은 표가 있는 전 라우트에 퍼진다.
acceptance_criteria: (1) 관리자·사용자 화면에서 `contained` 버튼이 **0개인 화면이 없다**(구조상 동작이 불가능한 읽기 전용 화면은 예외로 등재하고 사유를 남긴다). (2) 어떤 화면·오버레이에도 `contained` 버튼이 **2개 이상 있지 않다**. (3) 파괴적 동작(삭제·비활성화·보관)이 **`contained`가 아니고** 위험 스타일 + 별도 그룹이며 확인 단계를 갖는다. (4) 표에서 행 「상세」 버튼 열이 제거되고, **키보드만으로 행에 도달해 Enter로 상세를 열 수 있다**. (5) 스크린리더가 행이 조작 가능함을 알린다. (6) 새 기본 동작 버튼이 권한 없는 역할에게 보이지 않는다(역할 4종 검증). (7) 위계 규범이 정적 검사 또는 컴포넌트로 강제되어 새 화면이 자동으로 따른다. (8) `/users` 목록과 생성 모달의 기존 위계가 그대로다.
required_tests: 버튼 위계 정적 검사(화면당 contained ≤1, 파괴적 동작은 위험 변형) — `scripts/static_checks.sh`에 배선. 키보드 상세 도달 테스트(Tab으로 행 도달 → Enter → 상세 열림) — 표가 있는 라우트 대표 3개. 스크린리더 속성 테스트(행의 role/aria). RBAC 테스트(역할 4종 × 새 기본 동작). 파괴적 동작 확인 절차 테스트. `var/product-audit/probe_write_gate.py` 재실행으로 `operator` 쓰기 컨트롤 부재 유지 확인.
qa_gaps: `QA_COVERAGE.md`에 「화면당 기본 동작 존재/개수」와 「파괴적 동작의 시각 구분」 축이 없다. 「행 클릭 상세의 키보드 도달」도 검증된 적이 없다 — 행 버튼을 없애기 전에 이 축을 먼저 세워야 한다.
quality_rubric: `impeccable` — Operate 모드(동작 위계가 표현보다 우선), heuristic 5(Error Prevention: 파괴적 동작 전 확인과 구분)·8(Aesthetic and Minimalist Design), Working Memory 규범의 실무 적용("action buttons: 1 primary, 1–2 secondary, group the rest"), 페르소나 Sam(키보드 전용 도달)·Riley(오조작). `redesign-existing-projects` — "Always one filled button + one ghost button" 경고의 반대편(필드 버튼이 3개), "Buttons not bottom-aligned / 중복 컨트롤". `ui-ux-pro-max` `--domain ux` — Touch & Interaction의 error-feedback과 loading-buttons.
current_state: 관리자 16화면 중 10개, 사용자 10화면 중 4개가 `contained` 버튼 0개다(`/scheduler-calendar`는 버튼 33개에 0개, `/offboarding`은 27개에 0개). 반대로 상세 모달은 `contained`가 3개이고 `/departments`는 그중 하나가 「삭제」다. 표에는 행마다 「상세」 버튼이 있어 행 클릭과 중복된다. `/users` 목록과 생성 모달만 위계가 정확하다.
user_problem: 화면 절반에서 지금 무엇을 하면 되는지 시각적으로 알 수 없고, 상세 모달에서는 「삭제」가 「수정」과 똑같이 강조돼 오조작 위험이 높다. 표의 「상세」 버튼 20개는 행 클릭 이상을 주지 않으면서 시선을 가져간다.
design_verdict: REDESIGN
target_state: 어떤 화면을 열어도 기본 동작이 하나 눈에 들어오고, 파괴적 동작은 그것과 명확히 구분되며, 표에서는 행을 누르거나 키보드로 Enter를 눌러 상세를 연다.
target_design: 버튼 위계 규범을 컴포넌트와 정적 검사로 강제한다 — 화면/오버레이당 `contained` 1개, 보조는 `outlined`, 나머지 `text`, 파괴적 동작은 위험 스타일 + 별도 그룹 + 확인 단계. 기본 동작이 없는 14화면에 그 화면에서 실제로 가능한 기본 동작을 세운다(`/notifications` 모두 읽음, `/my-tickets` 새 티켓, `/dashboard`는 PA-RC-0018의 조치 버튼). 상세 모달은 「수정」만 primary로 남기고 「비활성화」·「보관」·「삭제」를 위험 그룹으로 분리한다. 표의 행 「상세」 버튼 열을 제거하고 행 클릭으로 통일하되 행에 `tabindex`와 Enter 처리를 두어 키보드 도달을 보존한다. 빈 상태에도 가능한 다음 행동을 버튼으로 올린다.
visual_change_required: true
target_visual_delta: 14개 화면에 채운 기본 동작 버튼이 하나씩 생긴다. 상세 모달에서 채운 버튼이 3개에서 1개로 줄고 「삭제」가 붉은 위험 스타일로 분리된다. 표의 우측 「상세」 버튼 열 20개가 사라져 데이터 열이 넓어지고 우측이 조용해진다.
affected_surfaces: dashboard · home · admin-console · table-screens · list-screens · settings · key-workflows · modal-drawer · forms · empty-state
affected_components: 버튼 위계 규범 정의(컴포넌트/토큰 층) · 위험 동작 버튼 변형(신설) · 표 컴포넌트의 행 조작 열과 행 키보드 처리 · 상세 모달 액션 그룹 · 14개 화면의 액션 영역 · 정적 검사 스크립트
workflow_change: 표에서 상세를 여는 방법이 「버튼 클릭 또는 행 클릭」에서 「행 클릭 또는 키보드 Enter」로 통일된다. 파괴적 동작의 실행 절차와 확인 단계는 불변이며 시각 강조만 바뀐다.
navigation_impact: 없음 — 라우트·메뉴 불변. 화면 내 액션 배치만 바뀐다.
data_impact: 없음.
api_impact: 없음 — 동작이 호출하는 엔드포인트 불변.
rbac_impact: 경계 불변. 새 기본 동작은 해당 권한이 있는 역할에게만 보이고 서버가 정본으로 재판단한다. `PA-F-053`이 확인한 「operator에게 쓰기 컨트롤이 보이지 않는다」 성질을 유지해야 한다.
browser_verification: 1920×1080 light·dark에서 기본 동작이 없던 14화면 스크린샷 — 각 화면에 채운 버튼 1개. `/users`·`/departments` 상세 모달 스크린샷 — contained 1개, 삭제가 위험 스타일 별도 그룹. 표 화면 스크린샷 — 「상세」 열 부재. 키보드만으로 Tab→Enter로 상세를 여는 조작을 실제로 수행하고 결과 확인. 역할 4종 스크린샷으로 버튼 노출 대조.
evidence_refs: `PRODUCT_AUDIT_DESIGN.md` §2-E·§3 table-screens·§3 modal-drawer·§3 empty-state·§4 · `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-065` · 계측 `var/product-audit/design_capture_admin.json`·`design_capture_user.json`(화면별 contained 수) · `design_capture2.json` detail[] buttons[](/users primary 3 = 비활성화·보관·수정, /departments primary 3 = 수정·비활성화·삭제) · `design_capture2.json` empty[](contained 0/0/0/1) · 스크린샷 `var/product-audit/shots/fhd_admin_dashboard.png`·`fhd_admin_users.png`·`detail_user-detail.png`·`detail_dept-detail.png`·`modal_user-add.png`
<!-- PA-RC-END -->

<!-- PA-RC-BEGIN PA-RC-0024 -->
rc_id: PA-RC-0024
severity: Medium
priority: P2
confidence: Confirmed
problem: **"상세 보기"라는 하나의 개념이 콘솔에 따라 두 가지 다른 것으로 구현돼 있다.** 사용자 콘솔은 실제 라우트다 — `frontend/src/app/UserRoutes.jsx:60-83`에 `/tickets/:id`·`/projects/:id`·`/chat-rooms/:id`·`/board/:id`·`/team-docs/:id`·`/games/:id` **6개**가 선언돼 있고 딥링크·뒤로가기·not-found가 전부 동작한다(이전 Cycle `PA-F-052`가 확인). 관리자 콘솔은 `:id` 라우트가 **하나도 없고** 행 클릭이 모달을 연다 — `/users` 992×887, `/audit` 992×896, `/departments` 992×560이며 **셋 다 URL이 바뀌지 않는다**(`urlBefore == urlAfter`). 결과로 두 가지가 깨진다. (1) 관리자 상세는 **딥링크·새로고침·뒤로가기가 성립하지 않는다.** (2) `/users/<uuid>`처럼 존재할 법한 URL을 입력하면 미등록 라우트로 떨어져 **9초 뒤 `h1` 「대시보드」로 조용히 이동**한다 — 오류도 설명도 없다. 같은 제품의 `/board/999999`는 정상적인 not-found를 보여주므로 처리 방식이 콘솔별로 갈린다.
expected: 같은 개념은 제품 전체에서 같은 방식으로 동작해야 하고, 상세는 공유 가능한 주소를 가져야 하며, 존재하지 않는 대상은 오류로 알려야 한다. 근거: ⑤ **사용자 콘솔이 같은 저장소 안에 옳은 구현을 이미 갖고 있다**(라우트 6개 + not-found 3요소) · ② 이전 Cycle의 `PA-RC-0002` 산출물인 `docs/UX_WRITING.md`가 오류 문구의 회복 3요소를 제품 규칙으로 정했고 사용자 콘솔이 그것을 만족한다 · ② CLAUDE.md §5가 "Navigation/deep-link/refresh/state retention"을 필수 검증 범위로 규정.
actual: 관리자 상세는 URL 없는 모달이라 공유·새로고침·뒤로가기가 안 되고, 미등록 상세 URL은 설명 없이 대시보드로 간다.
intent_evidence: ⑤ `frontend/src/app/UserRoutes.jsx:60,66,72,77,81,83`의 6개 `:id` 라우트 — 같은 팀이 같은 문제를 이미 라우트로 풀었다 · ② `docs/UX_WRITING.md`(not-found 3요소) · ② CLAUDE.md §5 · ⑤ 이전 Cycle `PA-F-052`가 사용자 콘솔 상세 6화면의 not-found 품질을 확인한 기록.
findings: PA-F-066
feature_contracts: FC-사용자관리 · FC-감사로그 · FC-부서관리(각 상세가 보여주는 정보와 가능한 동작) — **상세가 보여주는 정보·동작·권한은 전부 불변.** 바뀌는 것은 그 상세에 도달하고 그 상태를 주소로 표현하는 방식이다.
routes: 신설 대상 — `/users/:id` · `/audit/:id` · `/departments/:id`(그 외 관리자 상세 모달이 있는 화면 전체를 조사해 포함할 것). 참조 구현 — `/board/:id` · `/team-docs/:id` 등 사용자 콘솔 6개. 미등록 URL 처리 — 관리자 전 라우트.
frontend: `frontend/src/app/AdminRoutes.jsx`(라우트 추가) · 각 관리자 목록 화면의 행 클릭 핸들러(모달 열기 → 라우트 이동 + URL 동기화) · 상세 모달/드로어 컴포넌트(URL 상태와 동기화) · 라우터의 미등록 경로 폴백(현재 대시보드 리다이렉트) · 사용자 콘솔의 not-found 컴포넌트(공용으로 승격할 대상).
api: 없음 — 상세 조회 엔드포인트는 이미 존재한다(모달이 지금 그것을 부른다). **새 엔드포인트를 만들기 전에 기존 것을 확인할 것.**
backend: 없음. 단 상세 라우트가 생기면 존재하지 않는 id에 대한 404 응답이 필요한데, 이전 Cycle이 서버가 이미 404를 준다는 것을 확인했다(`PA-F-052`).
data: 해당 없음 — 데이터 구조·의미 불변.
rbac: **경계 불변이며 확인이 필요하다.** 상세 라우트가 생기면 직접 URL 진입이 가능해지므로, 권한 없는 사용자의 직접 진입이 **서버에서** 정확히 거부되는지 반드시 검증한다. 이전 Cycle이 프런트 게이트와 백엔드 판정이 일치함을 확인했으나(`PA-F-045`), 새로 생기는 라우트는 그 검증 범위 밖이므로 다시 확인해야 한다. IDOR 관점에서 다른 조직/부서의 id 진입도 검증 대상이다.
integration: 해당 없음.
state_transition: 해당 없음 — 상세에서 수행하는 동작의 전이 규칙 불변.
user_impact: 관리자가 특정 사용자나 감사 항목을 동료에게 링크로 보낼 수 없다. 상세를 연 뒤 뒤로가기를 누르면 상세만 닫히는 것이 아니라 이전 화면을 떠나고, 새로고침하면 상세가 사라진다. 잘못된 상세 링크를 받으면 오류 대신 대시보드에 도착해 무슨 일이 일어났는지 알 수 없다. 같은 제품의 게시글 상세는 링크가 되는데 사용자 상세는 안 되는 비일관이 학습을 방해한다.
implementation_direction: (1) **관리자 상세에 `:id` 라우트를 부여한다.** 표현은 지금처럼 목록 위 오버레이(모달/드로어)를 유지하되 **URL과 동기화**해 딥링크·뒤로가기·새로고침이 성립하게 한다. 표현을 바꾸는 것이 아니라 주소를 붙이는 작업이다. (2) **뒤로가기는 상세만 닫고 목록 상태(검색·필터·페이지)를 보존한다** — `PA-RC-0013`(`/users`가 목록 상태를 URL에 안 싣는다)을 **먼저 또는 함께** 처리해야 이것이 성립한다. 두 RC는 같은 URL 상태 문제의 앞뒤다. (3) **미등록/미해결 상세 id는 대시보드 이동이 아니라 not-found를 보여준다** — 사용자 콘솔이 이미 쓰는 3요소(무엇이 없다 / 왜 그럴 수 있다 / 목록·홈으로)를 **공용 컴포넌트로 승격**해 양쪽 콘솔이 같은 것을 쓰게 한다. 새로 만들지 말고 있는 것을 옮길 것. (4) 관리자 콘솔에 상세 모달이 있는 화면을 **전수 조사**해 이번에 확인한 3개 외에 더 있는지 확인하고 함께 처리한다. (5) 라우트 추가 후 권한 없는 직접 진입과 cross-scope id 진입을 반드시 검증한다.
constraints: RBAC 경계를 넓히지 않는다 — 라우트가 생겨도 접근 판단은 서버가 정본이고, 권한 없는 직접 진입은 거부되어야 한다(CLAUDE.md §3-5). IDOR 방지 규약 유지. 상세가 보여주는 정보와 가능한 동작을 바꾸지 않는다. not-found 문구는 **새로 쓰지 말고** 사용자 콘솔의 것을 공용화한다. 오버레이의 접근성 속성(`aria-modal`·`aria-labelledby`·Escape·포커스 관리)을 URL 동기화 과정에서 잃지 않는다.
regression_risk: (1) **RBAC/IDOR가 가장 큰 위험** — 직접 URL 진입 경로가 새로 열리므로 권한 검증을 반드시 재확인해야 한다. (2) URL 동기화는 목록 상태 보존과 얽혀 있어 `PA-RC-0013`과 충돌하거나 서로를 되돌릴 수 있다. (3) 뒤로가기 동작 변경은 브라우저 히스토리를 다루므로 중첩 오버레이·모달 위 모달에서 예상 밖으로 동작할 수 있다. (4) 미등록 경로 폴백 변경은 모든 오타 URL의 동작을 바꾼다 — 기존에 대시보드 리다이렉트를 기대하는 테스트가 있는지 확인할 것. (5) 오버레이 접근성 속성 유실.
acceptance_criteria: (1) `/users/:id`·`/audit/:id`·`/departments/:id`(및 조사로 발견된 나머지)가 **직접 URL 진입으로 상세를 연다**. (2) 상세가 열린 상태에서 **새로고침하면 같은 상세가 다시 열린다**. (3) **뒤로가기가 상세만 닫고** 목록의 검색·필터·페이지가 보존된다. (4) 존재하지 않는 id로 진입하면 **not-found 3요소**(무엇이 없다 / 왜 그럴 수 있다 / 목록·홈 두 경로)가 보이고 **대시보드로 이동하지 않는다**. (5) 사용자 콘솔과 관리자 콘솔이 **같은 not-found 컴포넌트**를 쓴다. (6) 권한 없는 역할이 상세 URL로 직접 진입하면 **서버가 거부**하고 화면이 권한 거부 상태를 보여준다(역할 4종 검증). (7) 다른 조직/부서 범위의 id 직접 진입이 거부된다. (8) 오버레이의 `aria-modal`·`aria-labelledby`·Escape·포커스 관리가 유지된다. (9) 관리자 상세 모달이 있는 화면을 전수 조사한 목록이 문서에 남아 있다.
required_tests: 상세 라우트 딥링크/새로고침/뒤로가기 테스트(관리자 상세 전체). not-found 공용 컴포넌트 테스트(양쪽 콘솔). **RBAC 직접 진입 negative 테스트** — 역할 4종 × 상세 라우트 전체, 권한 없음/타 조직 id. `var/product-audit/probe_badid.py`·`verify_badid.py`를 관리자 상세 라우트까지 확장해 재실행. 목록 상태 보존 테스트(`PA-RC-0013`과 공유). 오버레이 접근성 속성 회귀 테스트.
qa_gaps: `QA_COVERAGE.md`에 관리자 상세의 딥링크·새로고침·뒤로가기 축이 없다(라우트가 없어서 검증 대상이 아니었다). 미등록 URL 폴백 동작도 검증된 적이 없고, 이번 Cycle이 대시보드로 조용히 이동하는 것을 처음 관측했다. 관리자 상세 라우트의 RBAC/IDOR은 라우트 신설과 동시에 커버리지를 세워야 한다.
quality_rubric: `impeccable` — heuristic 3(User Control and Freedom: 뒤로가기·탈출 경로)·4(Consistency and Standards: 같은 개념이 같게 동작)·9(Error Recovery: 오류를 정확히 알리고 회복 경로를 준다), 페르소나 Riley(새로고침·뒤로가기로 흐름을 깨뜨려 보기). `ui-ux-pro-max` `--domain ux` — Navigation의 Deep Linking("URL은 공유 가능하도록 현재 상태를 반영해야 한다", "상태/뷰 변경 시 URL 갱신"). `ux-writing` — not-found 문구의 회복 3요소(이미 사용자 콘솔이 충족하므로 재사용).
current_state: 사용자 콘솔은 `:id` 라우트 6개로 상세가 딥링크·뒤로가기·not-found를 지원한다. 관리자 콘솔은 `:id` 라우트가 0개이고 행 클릭이 URL 없는 모달을 연다(`/users` 992×887 · `/audit` 992×896 · `/departments` 992×560, 셋 다 urlBefore==urlAfter). `/users/<uuid>` 직접 입력은 9초 뒤 h1 「대시보드」로 조용히 이동한다.
user_problem: 관리자가 사용자·감사 항목을 링크로 공유할 수 없고, 상세를 연 뒤 새로고침하면 사라지며 뒤로가기는 이전 화면을 떠난다. 잘못된 상세 링크는 오류 대신 대시보드로 데려간다.
design_verdict: REDESIGN
target_state: 관리자도 상세를 주소로 공유하고, 새로고침해도 같은 상세가 열리며, 뒤로가기는 상세만 닫고 목록 상태를 유지한다. 없는 대상은 사용자 콘솔과 똑같은 not-found 화면으로 알려준다.
target_design: 관리자 상세에 `/users/:id`·`/audit/:id`·`/departments/:id` 라우트를 부여한다. 표현은 목록 위 오버레이를 유지하되 URL과 동기화해 딥링크·뒤로가기·새로고침이 성립하게 한다. 뒤로가기는 상세만 닫고 목록 상태(검색·필터·페이지)를 보존한다 — 이를 위해 `PA-RC-0013`을 먼저 또는 함께 처리한다. 미해결·미등록 상세 id는 대시보드 이동 대신 사용자 콘솔이 이미 쓰는 not-found 3요소를 보여주며, 그 컴포넌트를 공용으로 승격해 양쪽 콘솔이 공유한다. 관리자 상세 모달이 있는 화면을 전수 조사해 함께 처리한다.
visual_change_required: false
target_visual_delta: 화면 모습은 거의 그대로다 — 상세는 지금처럼 목록 위 오버레이로 열린다. 눈에 보이는 변화는 주소창의 URL이 상세 id를 포함하게 되는 것과, 잘못된 상세 URL에서 대시보드 대신 not-found 화면이 나타나는 것뿐이다.
affected_surfaces: detail-screens · modal-drawer · error-state · table-screens(행 클릭 핸들러)
affected_components: `frontend/src/app/AdminRoutes.jsx` · 관리자 목록 화면의 행 클릭 핸들러 · 상세 오버레이 컴포넌트(URL 동기화) · 라우터 미등록 경로 폴백 · 사용자 콘솔 not-found 컴포넌트(공용 승격 대상)
workflow_change: 없음 — 상세를 보고 조작하는 절차와 권한은 불변이다. 상세에 도달하는 수단이 하나 늘어나고(직접 URL) 뒤로가기의 의미가 정확해진다.
navigation_impact: 관리자 콘솔에 상세 라우트가 신설된다. 뒤로가기 동작이 「이전 화면으로」에서 「상세만 닫기」로 바뀐다. 미등록 URL 폴백이 대시보드 리다이렉트에서 not-found로 바뀐다.
data_impact: 없음 — 상세가 보여주는 정보·구조·의미 불변.
api_impact: 없음 — 상세 조회 엔드포인트는 이미 존재하고 모달이 지금 그것을 부른다. 서버는 없는 id에 이미 404를 준다.
rbac_impact: **경계 불변이나 새 진입 경로가 생기므로 재검증 필수.** 직접 URL 진입 시 서버가 권한을 정본으로 판단해 거부해야 하고, 타 조직/부서 범위 id의 IDOR도 차단되어야 한다. 역할 4종 × 신설 라우트 전체의 negative 테스트가 완료 조건이다.
browser_verification: 1920×1080 light에서 `/users/<실제id>` 직접 입력 → 상세 열림 스크린샷, 그 상태에서 새로고침 → 같은 상세 스크린샷, 뒤로가기 → 목록 + 검색어/페이지 유지 스크린샷. `/users/<없는id>` → not-found 3요소 스크린샷(대시보드 아님). 권한 없는 역할로 같은 URL 진입 → 거부 화면 스크린샷. 사용자 콘솔 `/board/999999`와 나란히 놓고 같은 컴포넌트인지 대조.
evidence_refs: `PRODUCT_AUDIT_DESIGN.md` §3 detail-screens·§3 modal-drawer·§3 error-state · `PRODUCT_AUDIT_FINDINGS.md`의 `PA-F-066` · 계측 `var/product-audit/design_capture2.json` detail[](openedAs=dialog, urlBefore==urlAfter, 박스 크기)·states[](`/users/00000000-…` at9s h1=「대시보드」 / `/board/999999` at9s h1=「게시글」) · 소스 `frontend/src/app/UserRoutes.jsx:60,66,72,77,81,83`(사용자 `:id` 6개) 대비 `AdminRoutes.jsx`(0개) · 이전 Cycle `PA-F-052`(사용자 콘솔 not-found 3요소) · 스크린샷 `var/product-audit/shots/detail_user-detail.png`·`detail_audit-detail.png`·`detail_dept-detail.png`·`state_error-baduser.png`·`state_error-badboard.png`
<!-- PA-RC-END -->
