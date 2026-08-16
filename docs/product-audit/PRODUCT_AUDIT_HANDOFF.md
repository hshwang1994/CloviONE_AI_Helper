# PRODUCT AUDIT — HANDOFF (구현 계약)

cycle_id=PA-20260817-072224-24b91505

> baseline=`2aacd2a2ab4a50e92d3dee8f3aba3a248e175e83` · baseline_branch=`ui/mui-migration`
>
> 이 문서는 **구현 Phase(`autonomous_runner.ps1`)의 입력**이다. Backlog 한 줄만 보고 구현하지
> 않는다 — 각 `PA-RC-*` 블록의 Acceptance Criteria 와 Regression 범위가 완료 판정의 기준이다.
>
> 직전 Cycle(`PA-20260816-120655`)의 `PA-RC-0012`~`0026` 15건은 **전부 구현·소비 완료**다.
> 그 블록은 이 문서에 다시 싣지 않는다 — `docs/BACKLOG.md` §PA2 와 `DECISIONS.md` D-91~D-105 가
> 정본이다. 아래는 이 Cycle이 HEAD(`2aacd2a`)에서 새로 찾은 것뿐이다.
>
> **이 Audit은 진행 중이다.** 아래 요약의 수는 현재까지 확정된 것이고, Cycle이 끝날 때
> `AUDIT_COMPLETE` 와 함께 최종값이 된다.

<!-- HANDOFF-SUMMARY
cycle_id=PA-20260817-072224-24b91505
actionable_root_causes=3
redesign_root_causes=1
deferred_for_human_approval=0
-->

---

<!-- PA-RC-BEGIN PA-RC-0027 -->
rc_id: PA-RC-0027
severity: High
priority: P1
confidence: Confirmed
problem: 내 티켓을 판정할 수 없는 상태(`mapped: false`)에서 `/me` 와 `/my-stats` 의 개수 타일이 "모른다"를 숫자 `0` 으로 그린다. 사용자는 「오늘 마감 0」을 *"오늘 마감이 없다"* 로 읽지만 진실은 *"당신 담당이 무엇인지 알 수 없다"* 다. 같은 응답 안의 비율·진척 값은 `null` 로 옳게 답하고, 형제 화면(`/dashboard` 내 업무)은 가드를 걸어 「셀 수 없습니다」라고 옳게 말한다. 즉 제품은 이미 옳은 답을 알고 있고, 두 호출부에서만 그 가드가 빠져 있다.
expected: 티켓 소스를 읽을 수 없거나 계정 매핑이 없으면(`not (ok and mapped)`) 개수 버킷을 **응답에 싣지 않는다**. 프런트는 이미 버킷 부재를 `null` → `-` 로 그리도록 구현돼 있다(`Home.jsx:309`). 근거: `docs/DASHBOARD_METRICS.md` §3 이 네 타일 전부에 「소스 장애면 버킷 자체가 없다 → `-`」 라고 명시하고, 같은 문서 서두가 「0과 "없음"을 구분하는가(안 쟀다를 0으로 그리면 그럴듯해서 아무도 신고하지 않는다)」 를 원칙으로 못박는다.
actual: `GET /api/home/today` 가 `mapped: false` 를 실으면서 `due_today/overdue/in_progress/due_soon/blocked` 를 전부 `{"count": 0, "items": []}` 로 보낸다(같은 응답의 `sprint` 는 `null`). `GET /api/me/stats` 도 같은 모양으로 `totals` 를 0 으로 채운다(`completion_rate` 만 `null` → `-`). 화면은 그 0 을 그대로 그린다.
intent_evidence: (1) `docs/DASHBOARD_METRICS.md` §3 표의 「0과 없음」 열 — 네 타일 전부 「소스 장애면 버킷 자체가 없다 → `-`」. (2) `app/home/service.py:110` 주석 — 「티켓을 못 읽었으면 진척을 0으로 그리지 않는다 — 0건과 '모른다'는 다른 말이다」. (3) `app/home/work.py:236` 주석 — 「미러가 비어 있거나 매핑이 없으면 **모른다**. 0 으로 그리지 않는다(홈 '오늘'의 sprint 블록이 같은 판단을 한다 — **두 화면이 같은 상황에서 다른 말을 하면 안 된다**)」. (4) `frontend/src/screens/Home.jsx:309` 가 버킷 부재를 이미 `null` 로 처리한다. 의도는 INFERRED 가 아니라 **문서와 코드 양쪽에 명시**돼 있다.
findings: PA-F-082, PA-F-084, PA-F-085
feature_contracts: FC-홈-오늘(내 티켓 요약), FC-내업무량(완료 통계)
routes: `/me`, `/my-stats`, (전파) `/me` 의 AI 도우미 「오늘 브리핑」 패널
frontend: `frontend/src/screens/Home.jsx`(수정 불필요 — 이미 `null`→`-`), `frontend/src/screens/MyStats.jsx:135-139`(백엔드가 값을 빼면 `StatCard` 가 `-` 를 그리는지 확인 필요)
api: `GET /api/home/today`, `GET /api/me/stats`
backend: `app/home/service.py:106-114`(`build_today`), `app/profiles/router.py:481-490`(`my_stats`). 참조 구현은 `app/home/work.py:236-243`
data: 없음 — DB 스키마·저장 데이터는 바뀌지 않는다. `user_notion_mappings.status='verified'` 유무가 입력일 뿐이다
rbac: 영향 없음 — 두 엔드포인트 모두 본인 데이터만 읽고 역할 게이트가 바뀌지 않는다
integration: Notion(티켓 소스). 매핑 부재·소스 장애 두 경우 모두 같은 경로를 탄다
state_transition: 없음 — 읽기 전용 집계다
user_impact: TEST SERVER 실측으로 `users` 23명 중 verified 매핑은 13명 — **10명(43%)이 이 경로에 있다.** 가장 흔한 발생 시점이 **입사 직후 Notion 연결 전**이라, 사용자가 그 숫자를 검증할 수단이 가장 없는 때에 거짓 안심을 준다. 마감을 놓칠 수 있는 종류의 오답이다.
implementation_direction: `app/home/work.py:238` 의 `usable = state["ok"] and state["mapped"]` 패턴을 나머지 두 호출부에 그대로 적용한다. (1) `app/home/service.py::build_today` — `usable` 이 아니면 `ticket_block` 에 버킷 5종을 넣지 않고 `{configured, ok, mapped}` 상태 키만 싣는다. (2) `app/profiles/router.py::my_stats` — `usable` 이 아니면 `build_stats()` 를 호출하지 않고 `totals` 를 생략하거나 값 전체를 `null` 로 낸다(화면이 이미 `-` 를 그릴 수 있는 모양으로). **가드를 세 번째로 복사하는 대신 `load_my_tickets` 결과에 `usable` 을 함께 실어 호출부가 같은 판단을 재발명하지 않게 하는 것을 우선 검토한다** — 이 RC의 구조적 원인은 "가드가 로더 밖에 흩어져 있다"는 것이다. 프런트는 원칙적으로 수정 불필요이며, `MyStats.jsx` 만 값 부재 시 `-` 가 나오는지 확인한다.
constraints: CLAUDE.md §3-1 sync 일관성(`async def` 추가 금지) · §3-7 UTC 저장(표시 시점 계산은 기존 `local_today` 유지) · 응답의 최상위 `ok` 는 "요청이 처리됐는가"이지 "소스가 살아 있는가"가 아니다(`app/profiles/router.py` docstring 이 명시 — 소스 상태는 `source` 아래로 접어 둔 채로 유지한다) · 화면을 오류로 덮지 않는다(§17.4 장애 격리: 티켓이 죽어도 문서·게시판·알림 위젯은 그대로 나와야 한다)
regression_risk: **가장 큰 위험은 기존 테스트가 이 결함을 고정하고 있다는 것이다**(`PA-F-085`). `tests/integration/test_my_stats_api.py:180` `test_stats_survive_an_unmapped_account` 가 `body["totals"]["all"] == 0` 을 단언한다 — 수정하면 이 테스트가 **빨개지고, 그것이 정상이다.** 구현자가 회귀로 오해해 되돌리면 안 된다. 그 밖의 위험: (a) 버킷을 통째로 빼면 버킷을 무조건 참조하는 소비자가 터질 수 있다 — `/me` 의 AI 도우미 브리핑과 포커스 전환(`Home.jsx:250 focus`)이 버킷 키를 읽으므로 함께 확인한다. (b) `mapped: true` 인데 실제로 티켓이 0건인 정상 경로는 **계속 `0` 이어야 한다** — 이 둘을 뒤섞으면 반대 방향의 거짓말이 된다.
acceptance_criteria: (1) `mapped: false` 인 세션의 `GET /api/home/today` 응답에 `due_today/overdue/in_progress/due_soon/blocked` 버킷이 없거나 전부 `null` 이다. (2) 같은 세션의 `GET /api/me/stats` 의 `totals` 개수 값이 `0` 이 아니다(없거나 `null`). (3) `/me` 화면의 타일 4종이 `0` 이 아니라 `-` 를 그린다(실브라우저). (4) `/my-stats` 의 개수 타일 5종이 `-` 를 그리고, 기존에 이미 `-` 이던 `완료율` 과 일관된다. (5) `/me` 의 AI 도우미 「오늘 브리핑」이 「오늘 마감 0건, 지연 0건…」 을 말하지 않는다. (6) **`mapped: true` 이고 티켓이 실제로 0건인 사용자는 여전히 `0` 을 본다** — 회귀 테스트로 두 경우를 함께 고정한다. (7) `/dashboard` 내 업무의 기존 문구(「셀 수 없습니다」)가 바뀌지 않는다.
required_tests: (1) `tests/integration/test_my_stats_api.py::test_stats_survive_an_unmapped_account` 의 `totals["all"] == 0` 단언을 **계약에 맞게 바꾼다**(단언 삭제가 아니라 "0이 아님"으로). docstring 이 이미 「숫자를 지어내지 않고」 라고 말하므로 이름·의도는 그대로 두고 단언만 계약과 일치시킨다. (2) `tests/integration/test_home_today.py` 에 **미매핑 경로 테스트를 신설**한다 — 현재 `mapped is True` 정상 경로만 있다. (3) 「매핑 있음 + 티켓 0건」 경로가 `0` 을 유지하는 테스트를 신설해 과잉 수정을 막는다. (4) 프런트: `Home.jsx`·`MyStats.jsx` 가 버킷 부재에서 `-` 를 그리는 컴포넌트 테스트.
qa_gaps: `QA_COVERAGE.md` 에 「미매핑 계정의 홈·통계 표시」 축이 없다. 세 화면(`/me`·`/my-stats`·`/dashboard`)이 같은 상태에서 같은 말을 하는지 비교하는 검증도 없다 — 이 결함이 이제껏 안 잡힌 이유다.
quality_rubric: `ux-writing` — 「0과 없음의 구분」은 상태 표현(state messaging) 문제로 다뤘고, *"사용자가 이 숫자를 보고 무엇을 하는가"* 를 기준으로 High 로 판정했다(0을 보면 아무 것도 하지 않는다). 내장 rubric 4) 「같은 의미가 같은 component/pattern 으로 표현되는가」 — 같은 미매핑 상태가 한 화면 안에서 타일/Callout/EmptyState 세 벌로 다르게 표현되는 것을 Root Cause 병합의 근거로 삼았다.
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md` §PA-F-082 / §PA-F-084 / §PA-F-085 · `app/home/service.py:106-114` · `app/home/work.py:236-243` · `app/profiles/router.py:481-490` · `frontend/src/screens/Home.jsx:309` · `frontend/src/screens/MyStats.jsx:135-140` · `docs/DASHBOARD_METRICS.md` §3 · `var/product-audit/pa2_home_api.py` 실행 결과 · `var/product-audit/shots2/d1_user_me.png` · `d1_user_my-stats.png`
current_state: `/me` 상단에 개수 타일 4종(오늘 마감·지연·진행 중·7일 내 마감)이 전부 `0` 으로 떠 있고, 바로 아래 패널은 「담당 티켓을 판단할 수 없어 목록을 불러올 수 없습니다」 라고 말한다. `/my-stats` 는 개수 타일 5종이 `0`, 비율 타일 1종이 `-` 로 한 줄에 나란히 있고 위아래로 Callout 과 EmptyState 가 각각 「찾을 수 없습니다」 를 말한다.
user_problem: 사용자가 한 화면에서 서로 모순되는 두 답을 동시에 받는다. 숫자는 「없다」고 하고 문장은 「모른다」고 한다. 숫자가 먼저 읽히고 크게 그려져 있으므로 사용자는 숫자를 믿는다.
design_verdict: REFINE
target_state: 매핑이 없는 사용자가 `/me` 와 `/my-stats` 를 열면 개수 자리에 `-` 가 있고, 그 옆·아래의 안내 문구와 **같은 말**을 한다. 매핑이 되는 순간 같은 자리에 실제 숫자가 들어온다.
target_design: 타일 자체의 레이아웃·개수·위치는 바꾸지 않는다. 값만 `0` → `-` 가 된다. `StatCard` 는 이미 `null` 을 `-` 로 그리므로 새 컴포넌트도 새 변형도 만들지 않는다. `/my-stats` 는 이미 같은 줄에서 `완료율`이 `-` 를 그리고 있으므로, 수정 후 그 줄 전체가 한 가지 표현으로 통일된다 — 이 RC의 목표 상태는 **새 디자인이 아니라 이미 존재하는 표현으로의 수렴**이다.
visual_change_required: true
target_visual_delta: `/me` 상단 4타일의 값이 `0`(굵은 숫자) → `-` 로 바뀐다. `/my-stats` 상단 6타일 중 5개가 `0` → `-` 로 바뀌어 6개 전부 `-` 가 된다. 「지연」·「막힘」 타일의 위험색(`danger`) 조건이 `count > 0` 이므로 색은 원래 안 켜져 있었고 계속 안 켜진다.
affected_surfaces: `U-HOME` `/me`, `U-MYSTATS` `/my-stats`. (비교 기준으로만 관련) `A-DASH` `/dashboard` 내 업무 구역 — 이미 옳으므로 **바뀌면 안 된다**
affected_components: `frontend/src/ui/kit.jsx` `StatCard`(수정 없음 — 이미 `null`→`-`), `Home.jsx` 타일 4종 + AI 도우미 브리핑 문장 생성부, `MyStats.jsx` 타일 6종
workflow_change: 없음 — 사용자의 동선·클릭 수·화면 이동이 바뀌지 않는다. 바뀌는 것은 같은 자리에 있는 값의 표현뿐이다
navigation_impact: 없음 — 라우트·메뉴·IA 가 바뀌지 않는다
data_impact: 없음 — 저장 데이터는 그대로다. 응답에서 "모르는 값"을 0 으로 채우지 않게 되는 것뿐이고, `mapped: true` 경로의 값은 한 자리도 바뀌지 않는다
api_impact: `GET /api/home/today` 와 `GET /api/me/stats` 의 응답에서 특정 조건일 때 키가 사라지거나 `null` 이 된다. **계약이 넓어지는 방향**이며(문서가 이미 그렇게 규정한다) 기존 소비자는 프런트 두 곳뿐이라 함께 확인한다
rbac_impact: 없음 — 역할 게이트·범위 판정이 바뀌지 않는다. 본인 데이터만 읽는 엔드포인트다
browser_verification: TEST SERVER 에서 매핑 없는 계정(예: `qa-user@goodmit.co.kr`)으로 로그인해 1920×1080 라이트/다크 두 테마에서 `/me` 와 `/my-stats` 스크린샷을 찍어 타일이 `-` 인지 확인한다. 그리고 매핑이 있는 계정(`hsjung@goodmit.co.kr` 계열)으로 같은 두 화면을 열어 **숫자가 그대로 나오는지** 확인한다 — 한쪽만 보면 과잉 수정을 못 잡는다.
<!-- PA-RC-END -->

---

<!-- PA-RC-BEGIN PA-RC-0028 -->
rc_id: PA-RC-0028
severity: Medium
priority: P2
confidence: Confirmed
problem: 관리자 콘솔에 운영 상태를 말하는 화면이 둘 있고 본문의 68% 가 겹친다. `/diagnostics` 는 `/dashboard` 의 페이로드를 통째로 품은 뒤 항목을 더해 그린다 — `build_diagnostic_bundle` 이 `build_dashboard()` 를 그대로 호출하기 때문이다. 그 결과 `최근 주요 변경` 블록은 두 화면에서 16/16 문자열이 같고 `백업` 블록은 CTA(`백업 관리`)까지 같다. 게다가 같은 8개 서비스를 대시보드는 한 묶음으로, 진단은 `서비스 상태` 4 + `외부 연동` 4 로 **다르게 분류**해서, 「n8n 엔진이 서비스인가 연동인가」가 어느 화면에 있었는지에 달린다.
expected: 두 화면은 서로 다른 질문에 답해야 한다. `/dashboard` 는 「지금 무엇을 해야 하는가」(상시·자동 갱신), `/diagnostics` 는 「지원팀에 넘길 스냅샷을 만든다 + 대시보드가 답하지 않는 깊은 항목을 본다」(요청 시 수집). 번들이 대시보드를 **데이터로** 품는 것은 옳다(지원팀은 그 시점의 운영 상태를 함께 봐야 한다). 화면이 그것을 **그대로 펼쳐 그릴** 이유는 없다. 그리고 한 제품 안에서 같은 8개 서비스의 분류는 하나여야 한다.
actual: `pa2_dup.py` 실측 — 공유 섹션 제목 4종(`서비스 상태`·`작업 지표 (최근 24시간)`·`백업`·`최근 주요 변경`), `최근 주요 변경` 동일 문자열 16/16, `백업` 3/3, 본문 79줄 중 54줄(68%)이 양쪽에 존재. 두 화면 모두 옆의 카드가 이미 말한 것을 도넛이 다시 말한다(`정상 8개 (100%)` / `정상 4개 (100%)`).
intent_evidence: `app/health/service.py:390` `build_diagnostic_bundle` docstring 이 「this bundle **embeds a full `build_dashboard()` call**」 이라고 직접 말한다 — 중복은 우연이 아니라 구조다. 번들의 목적은 spec §14.7 「마스킹된 진단 — no secrets, no raw journals」 이고 `/diagnostics` 화면 상단도 「이 번들은 민감정보가 가려져 있어 지원팀에 그대로 전달해도 안전합니다」 라고 말한다. **번들의 의도는 명확하고 옳다. 화면이 그 번들을 어떻게 보여야 하는가에 대한 명시적 의도는 없다** — 그 부분은 INFERRED 이며, 근거는 두 화면의 역할 분담과 정보 위계 원칙이다.
findings: PA-F-083
feature_contracts: FC-운영대시보드, FC-진단번들
routes: `/dashboard`, `/diagnostics`
frontend: `frontend/src/screens/Dashboard.jsx`(754줄), `frontend/src/screens/ops/Diagnostics.jsx`, `ops/ServiceStatusPanel.jsx`, `ops/JobQueuePanel.jsx`, `ops/opsHelpers.js`(`integrationMix`·`healthVerdict`), `frontend/src/ui/charts/Donut.jsx`, `frontend/src/ui/adminKit.jsx`(`DashSection`·`StatusTile`·`SERVICE_GRID`)
api: `GET /api/admin/dashboard`, `GET /api/admin/diagnostics/bundle`
backend: `app/health/service.py:390 build_diagnostic_bundle`, `app/health/service.py build_dashboard`, `app/health/router.py:79-102`
data: 없음 — 스키마 변경 없음. 번들 페이로드의 모양도 바꾸지 않는다(지원팀 산출물 계약)
rbac: **건드리지 않는다.** `/api/admin/diagnostics/bundle` 은 `CONSOLE_OPS_ROLES`, 그 안의 `include_critical_audit` 는 `SENSITIVE_READ_ROLES` 로 따로 걸려 있다(`PA-RC-0026` 이 만든 구분). 화면에서 섹션을 옮기거나 지울 때 **그 분기를 통과하는 `최근 주요 변경` 블록의 역할 조건이 유실되지 않아야 한다** — 이 RC의 최대 위험이다
integration: n8n·업무 도우미·티켓 러너·요청 해석기의 분류 어휘가 두 화면에서 통일된다
state_transition: 없음
user_impact: 장애 대응 중인 운영자가 대부분 같은 말을 하는 화면 둘을 훑는다. 수집 시점이 다르므로(대시보드 30초 폴링 · 진단 수동 수집) 같은 지표가 동시에 다른 값으로 떠 있을 수 있고 — 실측 중 대시보드 `처리 요청 19 / 94.7%` 와 진단 `20 / 90%` 가 그랬다 — 둘 다 시각을 표기하니 거짓말은 아니지만 판단이 늦어진다. 그리고 정상 상태가 이상 상태와 같은 면적을 쓰기 때문에(카드 8장이 각각 「정상」, 도넛이 또 「100%」) 훑어서 이상을 찾는 목적에 정확히 역행한다.
implementation_direction: 화면의 역할을 갈라 놓는다. (1) `/diagnostics` 에서 **대시보드가 이미 상시로 보여 주는 블록을 본문에서 뺀다** — 최소한 `최근 주요 변경`(16/16 동일)과 `백업`(CTA까지 동일). 대신 그 자리에 「대시보드에서 보기」 링크를 둔다. 번들 **페이로드는 그대로 유지**한다(지원팀 산출물은 완전해야 한다) — 빠지는 것은 화면 렌더링뿐이다. (2) 진단에 남길 것은 대시보드가 답하지 않는 것들이다 — `시스템 리소스`(디스크·메모리·인증서 만료), `설치처 설정`, `최근 작업 오류` 상세, `원본(JSON) 보기`, 수집·복사·다운로드 동작. (3) 8개 서비스의 분류를 **한 벌로 통일**한다. 어느 쪽이 정본인지 정한 뒤(권장: 진단의 `서비스 상태`/`외부 연동` 2분류 — 내부 프로세스와 외부 의존은 장애 대응에서 실제로 다른 행동을 낳는다) 대시보드도 같은 어휘를 쓴다. (4) 두 화면의 도넛을 없앤다 — 옆의 카드가 이미 개별 상태를 말하고 있고, 100% 정상일 때 도넛은 화면에서 가장 큰 시각 요소가 되어 「볼 것 없음」에 최대 면적을 준다. 요약이 필요하면 섹션 제목 옆의 한 줄(`정상 8 / 8`)로 충분하다.
constraints: CLAUDE.md §3-1 sync 일관성 · §3-3 secret 비노출(번들 마스킹 규약 `mask_sensitive` 를 우회하지 않는다) · §3-5 권한 판단은 서버가 정본 — `include_critical_audit` 분기를 화면 정리 과정에서 없애지 않는다 · 번들 **응답 스키마는 바꾸지 않는다**(지원팀이 받는 산출물과 그 파서·`JSON 다운로드` 계약) · §8 제품 기능 경계(진단에 임의 shell/systemd 제어를 더하지 않는다)
regression_risk: (a) **`include_critical_audit` 유실** — `최근 주요 변경` 을 진단 화면에서 빼면서 백엔드의 역할 분기까지 지우면 operator 가 볼 수 없어야 할 슬라이스가 열리거나, 반대로 auditor 가 봐야 할 것을 잃는다. 이 분기는 `PA-RC-0026` 이 의도적으로 만든 것이다. (b) 번들 페이로드를 화면과 함께 줄이면 **지원팀 산출물이 빈약해진다** — 화면과 페이로드를 반드시 분리해서 다룬다. (c) 서비스 분류를 통일하면 `opsHelpers.js` 의 `integrationMix`·`healthVerdict` 와 대시보드의 집계(`서비스 정상 8/8`)가 같이 움직인다 — 한쪽만 고치면 두 화면이 다른 분모를 쓴다. (d) 도넛 제거는 `Donut.jsx` 의 다른 소비자를 확인한 뒤에 한다.
acceptance_criteria: (1) `pa2_dup.py` 를 다시 돌렸을 때 두 화면의 본문 줄 중복이 **68% → 35% 이하**로 내려간다. (2) `최근 주요 변경` 과 `백업` 블록이 `/diagnostics` 본문에 **더는 렌더되지 않는다**. (3) `GET /api/admin/diagnostics/bundle` 응답에는 그 데이터가 **그대로 남아 있다**(JSON 다운로드 산출물 불변). (4) operator 로 번들을 받아 `최근 주요 변경`(critical audit) 슬라이스가 **여전히 빠져 있고**, auditor/admin 은 여전히 받는다. (5) 8개 서비스가 두 화면에서 **같은 이름의 같은 묶음**으로 나타난다. (6) 두 화면 모두 도넛이 없고, 정상 상태의 세로 점유가 줄어든다(`/dashboard` scrollH 1580 기준 감소). (7) 「지금 무엇을 해야 하는가」에 답하는 블록(`확인이 필요한 항목`)은 `/dashboard` 에만 남는다.
required_tests: (1) `/api/admin/diagnostics/bundle` 의 **페이로드 불변** 회귀 테스트 — 화면 정리가 응답을 줄이지 않았음을 고정한다. (2) `include_critical_audit` 역할 분기 테스트를 operator/auditor/admin 세 역할로 유지·강화(기존 테스트가 있으면 그대로 통과해야 한다). (3) 프런트: `Diagnostics.jsx` 가 `최근 주요 변경`·`백업` 섹션을 렌더하지 않는다는 컴포넌트 테스트. (4) 서비스 분류 어휘가 두 화면에서 같은 소스(`serviceLabel`/분류 상수)를 쓴다는 테스트. (5) 실브라우저 중복 계측(`pa2_dup.py`)을 수용 기준 (1) 의 근거로 재실행.
qa_gaps: `QA_COVERAGE.md` 에 「두 관리 화면이 같은 사실을 말할 때 서로 모순되지 않는가」 축이 없다. 개별 화면은 각각 검증됐지만 **화면 간 일관성**은 검증 축 자체가 없어서 68% 중복이 여태 지표로 잡히지 않았다.
quality_rubric: `ui-ux-pro-max` — Data-Dense Dashboard 기준의 「정보 위계」와 「신호 대 잡음」: 정상 상태가 이상 상태와 같은 면적을 쓰면 훑기(scanning)가 실패한다. `redesign-existing-projects` — 화면 통합·분리 판단에서 *"이 화면이 없으면 사용자가 무엇을 못 하는가"* 를 물었고, 진단의 고유값은 수집·마스킹·원본 JSON·시스템 리소스뿐이라는 결론이 REDESIGN 판정의 근거다. `impeccable` — 중복 요소(도넛 vs 카드) 제거와 시각 위계 보정. 내장 rubric 4) 「같은 의미가 같은 component/pattern 으로 표현되는가」 · 7) 「대시보드: 지표가 의사결정으로 이어지는가, 장식용 카드가 아닌가」.
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md` §PA-F-083 · `PRODUCT_AUDIT_DESIGN.md` `dashboard`/`admin-console` 판정 블록 · `app/health/service.py:390-412` · `app/health/router.py:79-102` · `var/product-audit/pa2_dup.py` 실행 결과 · `var/product-audit/pa2_dup.json` · `var/product-audit/shots2/d1_admin_dashboard.png` · `d1_admin_diagnostics.png`
current_state: `/dashboard` 는 7섹션(`확인이 필요한 항목`·`서비스 상태`·`작업 지표`·`백업`·`최근 주요 변경`·`내 업무`)에 카드 11장, 세로 1580px. `/diagnostics` 는 11섹션(`시스템 리소스`·`서비스 상태`·`외부 연동`·`설치처 설정`·`현재 리소스`·`작업 지표`·`최근 작업 오류`·`백업`·`최근 주요 변경`·`원본 자료`)에 카드 14장, 세로 2629px. 그중 4섹션이 제목까지 같고 2섹션은 내용 문자열이 전부 같다.
user_problem: 장애 대응 중에 「어느 화면을 봐야 하는가」가 정해지지 않는다. 둘 다 열어야 안심이 되고, 열면 대부분 같은 말이라 시간만 든다. 그리고 같은 8개 서비스가 화면마다 다르게 묶여 있어 「n8n 이 우리 서비스인가 외부 연동인가」 같은 기초 개념이 화면에 따라 흔들린다.
design_verdict: REDESIGN
target_state: `/dashboard` 를 열면 「지금 조치할 것」이 먼저 보이고 상시 갱신된다. `/diagnostics` 를 열면 대시보드가 답하지 않는 깊은 항목(시스템 리소스·설치처 설정·오류 상세·원본 JSON)과 수집·전달 동작만 있다. 두 화면이 같은 말을 반복하지 않고, 서비스 분류 어휘가 한 벌이다.
target_design: `/diagnostics` 본문에서 `최근 주요 변경`·`백업` 섹션을 제거하고(데이터는 번들에 유지) 그 자리에 대시보드로 가는 링크 한 줄을 둔다. 진단의 첫 화면은 「수집 상태 + 수집/복사/다운로드」와 `오류 요약`, 그다음이 `시스템 리소스`·`설치처 설정`·`최근 작업 오류`·`원본 자료` 순이다. 서비스 목록은 두 화면 모두 `서비스 상태`(내부 프로세스)/`외부 연동`(n8n·업무 도우미·티켓 러너·요청 해석기) 2분류를 쓰고, 요약은 도넛 대신 섹션 제목 옆 `정상 8 / 8` 한 줄로 낸다. 카드·그리드 컴포넌트는 기존 `adminKit.jsx` 의 `DashSection`·`StatusTile`·`SERVICE_GRID` 를 그대로 쓴다 — 새 시각 언어를 만들지 않는다.
visual_change_required: true
target_visual_delta: `/diagnostics` 에서 `최근 주요 변경`(5행 표)과 `백업`(카드 1장 + `백업 관리` 버튼)이 사라져 세로가 2629px 에서 눈에 띄게 줄어든다. 두 화면의 도넛(각각 지름 ~140px 카드)이 사라지고 그 자리에 텍스트 한 줄이 온다. `/dashboard` 의 `서비스 상태` 8장 한 묶음이 4+4 두 묶음으로 갈라져 진단과 같은 모양이 된다.
affected_surfaces: `A-DASH` `/dashboard`, `A-DIAG` `/diagnostics`
affected_components: `Dashboard.jsx`, `ops/Diagnostics.jsx`, `ops/ServiceStatusPanel.jsx`, `ops/opsHelpers.js`, `ui/charts/Donut.jsx`(소비처 확인 후), `ui/adminKit.jsx`
workflow_change: 운영자의 동선이 짧아진다 — 지금은 두 화면을 다 열어야 하고, 바뀐 뒤에는 `/dashboard` 로 판단하고 지원팀에 넘길 때만 `/diagnostics` 로 간다. 업무 규칙·권한·데이터 의미는 바뀌지 않는다
navigation_impact: 라우트는 둘 다 그대로 남는다. 사이드바 항목도 그대로다. `/diagnostics` 본문에 `/dashboard` 로 가는 링크가 하나 는다
data_impact: 없음 — DB·집계 정의가 바뀌지 않는다. 번들 페이로드도 **불변**이다(수용 기준 (3))
api_impact: 없음이 목표다. 두 엔드포인트의 응답 스키마를 바꾸지 않는다 — 바뀌는 것은 프런트가 그중 무엇을 그리는가뿐이다
rbac_impact: 없어야 한다. `include_critical_audit`(`SENSITIVE_READ_ROLES`) 분기는 **그대로 유지**된다. 화면에서 그 블록을 빼더라도 백엔드 분기를 함께 지우지 않는다 — 수용 기준 (4) 가 이것을 검사한다
browser_verification: TEST SERVER 에서 admin·operator·auditor 세 역할로 `/dashboard` 와 `/diagnostics` 를 1920×1080 라이트/다크로 캡처한다. `pa2_dup.py` 를 재실행해 중복률이 35% 이하임을 수치로 확인하고, operator 세션에서 `최근 주요 변경` 이 번들 응답에 없음을 함께 확인한다(화면과 권한을 한 번에 본다).
<!-- PA-RC-END -->

---

<!-- PA-RC-BEGIN PA-RC-0029 -->
rc_id: PA-RC-0029
severity: Medium
priority: P2
confidence: Confirmed
problem: `/users` 표에서 사용자의 1차 식별자인 이메일이 **20행 중 20행 전부** 잘린다(열 폭 131px, 필요 198px). 같은 표에서 `역할`은 295px, `최근 로그인`은 287px 로 이메일의 2배 이상을 쓴다. 표에 가로 스크롤이 없어(`tableScrollsHoriz: false`) 사용자가 잘린 부분을 드러낼 방법이 화면에 없다 — 행을 열어야 전체 주소를 볼 수 있다. 폭이 부족해서가 아니라 **열 폭 배분이 식별자보다 보조 열에 후하다.**
expected: 표에서 행을 식별하는 열은 잘리지 않는 것이 기본이다. 1920px 뷰포트에서 이메일 전체가 보여야 하고, 폭이 정말 모자라면 보조 열(`최근 로그인`·`직책` 등)이 먼저 줄거나 접혀야 한다. 이 저장소는 이미 같은 종류의 규약을 갖고 있다 — 「목록 카드의 `count` 는 언제나 진짜 총계이고 `items` 만 5줄로 잘린다」(`docs/DASHBOARD_METRICS.md`), 즉 **잘림은 보조 정보에서 일어나야 한다는 원칙이 제품에 이미 있다.**
actual: `pa2_cols.py` 실측(1920×1920, admin 세션) — 표 폭 1550 / 컨테이너 1550 / 가로 스크롤 없음. 열 폭: 체크박스 72 · **이메일 131(필요 198, 20/20행 잘림)** · 이름 131 · 역할 295 · 상태 155 · 부서 184 · 직책 131 · Notion 연결 163 · 최근 로그인 287. 예: `ui-qa-user@goodmit.co.kr` 가 `ui-qa-user@go…` 로 보인다.
intent_evidence: 직접적인 열 폭 규정 문서는 **없다** — 이 부분은 INFERRED 다. 근거는 (1) 위의 「잘림은 보조 정보에서」 규약, (2) 이 표가 이메일을 첫 데이터 열로 두어 식별자로 쓰고 있다는 화면 자체의 설계 의도, (3) `역할` 열은 짧은 배지 2개만 담는데 295px 를 쓰고 있어 폭 배분이 내용량과 무관하다는 실측.
findings: PA-F-087
feature_contracts: FC-사용자관리
routes: `/users`, `/users/:id`
frontend: `frontend/src/screens/Users.jsx`, `frontend/src/screens/registry/*`(열 정의), 공통 표 컴포넌트 `DataScreen`/`DataTable`(`frontend/src/ui/kit.jsx`)
api: 없음 — 표시 전용이다. `GET /api/admin/users` 응답은 이미 전체 이메일을 준다
backend: 없음
data: 없음
rbac: 없음
integration: 없음
state_transition: 없음
user_impact: 관리자가 사용자를 찾을 때 쓰는 유일한 고유 식별자가 목록에서 안 읽힌다. 이름이 같은 사람(동명이인)이나 QA/서비스 계정처럼 접두어만 다른 주소(`ui-qa-user@` vs `ui-qa-auditor@` vs `ui-qa@`)를 목록에서 구분할 수 없어 행을 하나씩 열어 봐야 한다. TEST SERVER 21명 중 QA 계정 7개가 정확히 그런 접두어 공유 상태다.
implementation_direction: 열 폭 배분을 내용 요구량 기준으로 다시 준다. 이메일 열에 최소 폭(실측 필요폭 198px 이상)을 주고, 남는 폭은 `역할`·`최근 로그인`에서 회수한다(각각 295·287px 로 내용 대비 과다). 표 컴포넌트를 새로 만들지 않는다 — 열 정의(설정) 수준에서 끝난다. 폭이 정말 부족한 좁은 뷰포트에서는 보조 열을 먼저 접는다. 함께 볼 것: `/audit`·`/jobs` 는 잘림이 0이므로 **건드리지 않는다**(측정으로 확인됨).
constraints: 표 계열 27개 화면이 공유하는 `DataScreen` 계약을 깨지 않는다 — 한 화면을 위해 공통 컴포넌트에 예외를 만들지 말고 열 정의로 해결한다(CLAUDE.md §5: per-page 예외보다 shared token/variant 우선). 가로 스크롤을 새로 도입하는 방식은 피한다(다른 표와 상호작용이 달라진다).
regression_risk: 열 폭을 바꾸면 같은 표 컴포넌트를 쓰는 다른 화면의 레이아웃이 함께 움직일 수 있다 — 열 정의를 `/users` 에 한정해 바꾸고, 좁은 뷰포트(1366·390)에서 가로 넘침이 새로 생기지 않는지 확인한다. 이 저장소는 `horizontal_overflow` 를 UI QA 의 실패 조건으로 이미 쓰고 있다(`scripts/ui_qa/run.py --fail-on`).
acceptance_criteria: (1) 1920×1080 에서 `/users` 의 이메일 열 잘림이 **20/20행 → 0행**이 된다(`pa2_cols.py` 재실행으로 `clippedRows=0` 확인). (2) 표 전체 폭이 컨테이너를 넘지 않아 가로 스크롤이 생기지 않는다. (3) 1366px 와 390px 에서 가로 넘침이 발생하지 않는다. (4) `/audit`·`/jobs` 의 열 잘림은 여전히 0이다(회귀 없음).
required_tests: (1) `scripts/ui_qa` 의 기존 `horizontal_overflow` 검사를 `/users` 를 포함해 1920·1366·390 뷰포트로 실행. (2) `pa2_cols.py` 계측을 수용 기준 (1)(4) 의 근거로 재실행. (3) 프런트 컴포넌트 테스트로 이메일 열의 최소 폭 설정이 유지되는지 고정(열 정의가 나중에 조용히 되돌아가지 않게).
qa_gaps: `QA_COVERAGE.md` 에 「표의 식별자 열이 실제로 읽히는가」 축이 없다. 기존 UI QA 는 `horizontal_overflow`(표가 화면을 넘는가)만 보므로 **표 안에서 셀이 잘리는 것은 통과한다** — 이 결함이 여태 안 잡힌 이유다.
quality_rubric: `ui-ux-pro-max` — 「표/목록: 밀도, 정렬, **열 우선순위**」 항목. 내장 rubric 5) 「표·목록: 열 우선순위」 및 3) 「정보 위계가 3단계 이내로 읽히는가」 — 식별자가 안 읽히면 행을 특정하는 첫 단계가 실패한다. `impeccable` — 폭 배분이 내용량과 무관한 것을 시각 위계 결함으로 판정.
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md` §PA-F-087 · `PRODUCT_AUDIT_DESIGN.md` `table-screens` 판정 블록 · `var/product-audit/pa2_cols.py` 실행 결과 · `var/product-audit/pa2_cols.json` · `var/product-audit/shots2/d1_admin_users.png`
current_state: `/users` 표 8열 21행. 이메일 열 131px 로 20/20행 잘림(`ui-qa-user@go…`), 역할 295px, 최근 로그인 287px. 표 폭 1550 = 컨테이너 폭 1550, 가로 스크롤 없음.
user_problem: 목록에서 사용자를 고유하게 식별할 수 없어 행을 열어 확인해야 한다. 접두어를 공유하는 계정이 많을수록 악화된다.
design_verdict: REFINE
target_state: 1920px 에서 이메일이 온전히 읽히고, 표가 여전히 가로 스크롤 없이 컨테이너 안에 들어온다.
target_design: 열 폭 배분만 바꾼다 — 이메일에 최소 폭을 부여하고 `역할`·`최근 로그인` 에서 회수. 열 구성·순서·표 컴포넌트·필터·페이지네이션은 그대로 둔다.
visual_change_required: true
target_visual_delta: 이메일 열이 131px 에서 약 200px 로 넓어져 말줄임표가 사라진다. `역할`·`최근 로그인` 열이 그만큼 좁아진다. 행 높이·행 수·색·배지는 바뀌지 않는다.
affected_surfaces: `/users` (표 계열 중 이 화면만 — `/audit`·`/jobs` 는 실측상 잘림 0)
affected_components: `Users.jsx` 열 정의, 공통 `DataTable`(수정 없이 설정으로 해결하는 것이 목표)
workflow_change: 없음 — 동선·클릭 수가 바뀌지 않는다. 행을 열어야 이메일을 확인하던 우회가 없어질 뿐이다
navigation_impact: 없음
data_impact: 없음
api_impact: 없음
rbac_impact: 없음
browser_verification: TEST SERVER 에서 admin 으로 `/users` 를 1920×1080 · 1366×768 · 390×844 세 뷰포트에서 캡처하고, 각 뷰포트에서 `pa2_cols.py` 계측으로 `clippedRows=0` 과 가로 넘침 없음을 함께 확인한다. `/audit`·`/jobs` 도 같은 계측으로 회귀가 없음을 확인한다.
<!-- PA-RC-END -->
