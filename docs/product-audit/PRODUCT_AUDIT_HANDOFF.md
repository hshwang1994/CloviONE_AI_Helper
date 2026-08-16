cycle_id=PA-20260816-100149-48671b72

# PRODUCT AUDIT — IMPLEMENTATION HANDOFF

<!-- HANDOFF-SUMMARY
cycle_id=PA-20260816-100149-48671b72
actionable_root_causes=1
redesign_root_causes=0
deferred_for_human_approval=0
-->

> 이 문서는 **구현 Phase(`autonomous_runner.ps1`)로 넘기는 계약**이다.
> `docs/BACKLOG.md`의 한 줄만 보고 구현하지 말고, 해당 `PA-RC-*` 블록 전체를 읽어라.
> 원본 증거는 `PRODUCT_AUDIT_FINDINGS.md`, 의도 근거는 `PRODUCT_AUDIT_FEATURE_CONTRACTS.md`.

## 이전 Cycle(`PA-20260812-171558-56c5befa`) 잔여분 — **전부 닫혔다. 재확인함**

`IMPLEMENTATION_CONSUMED`의 기록을 그대로 믿지 않고 이번 Cycle이 현재 HEAD(`64ef571`)에서
각 항목을 **다시 측정**했다.

| 이전 RC | 이번 Cycle 재측정 | 판정 |
|---|---|---|
| `PA-RC-0001` 타이포 토큰 미소비 | `scripts/check_typography_literals.py` 존재하고 `static_checks.sh:150`에 배선됨. 실행 결과 `TYPOGRAPHY_LITERALS_OK` (예외 16종 등재) | ✅ 닫힘 |
| `PA-RC-0002` UX Writing 규칙 부재 | `docs/UX_WRITING.md`(7,428B) 존재. `scan_errcopy.py` 재실행 → **회복 절 비율 100%**, 진짜 막다른 길 **0건**(기준은 90%) | ✅ 닫힘 — 기준 초과 달성 |
| `PA-RC-0003` 저장소 위생 검사 공백 | `scripts/check_git_secrets.py` 존재하고 `static_checks.sh:79`에 배선됨 | ✅ 닫힘(검사 공백 기준). 검사가 잡아내는 `stash@{0}` 자격증명 **회전 자체는 여전히 미수행** — 내 권한 밖 외부 행위라 `REPORT` §7-B에 사실만 적는다 |

즉 **이 Handoff의 실행 대상은 이번 Cycle이 새로 찾은 `PA-RC-0012` 하나다.**

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
