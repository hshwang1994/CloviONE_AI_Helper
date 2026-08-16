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
actionable_root_causes=6
redesign_root_causes=2
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

---

<!-- PA-RC-BEGIN PA-RC-0030 -->
rc_id: PA-RC-0030
severity: Medium
priority: P2
confidence: Confirmed
problem: `/settings` 의 탭 게이트가 역할 때문에 볼 수 없는 탭을 **주소는 그대로 둔 채** 첫 탭으로 떨어뜨린다. `admin`·`operator` 가 `/system` 으로 들어오면 주소는 `#/settings?tab=os` 인데 화면은 `시스템 정책` 이다. 거부 안내가 없고, 그 역할에게는 탭이 하나뿐이라 전환할 수 없는 탭 바만 남는다. 같은 콘솔의 라우트 게이트는 같은 상황에서 「권한이 없습니다」를 명시적으로 보여주므로 한 제품 안에 권한 거부 어휘가 두 벌이 된다.
expected: 주소와 화면이 같은 것을 말해야 한다. 역할 때문에 못 보는 탭을 요청하면 (a) 주소를 실제로 그리는 탭으로 정정하거나 (b) 라우트 게이트와 같은 어휘로 「권한이 없습니다」를 보여야 한다. 근거는 이 저장소가 `PA-RC-0024` 에서 세운 계약 - 「주소만 상세 상태를 실어 딥링크·새로고침·뒤로가기가 성립하게 한다」. 그리고 「모르는 tab 값」과 「역할 때문에 못 보는 tab」은 사용자에게 다른 사실이므로 같은 처리로 묶으면 안 된다.
actual: 역할 3종 x 옛 라우트 4종 = 12조합 실측. `system_admin` 은 4탭이 뜨고 요청한 탭이 정확히 활성화된다. `admin`·`operator` 는 8조합 전부에서 주소가 `?tab=os|ai|integration` 인 채 `시스템 정책` 탭이 활성화되고, 탭 수는 1이며 거부 안내는 없다(`denied=False`).
intent_evidence: `frontend/src/screens/settings/SettingsShell.jsx:64-67` 주석이 낙하를 의도로 적는다 - 「모르는(또는 지금 role 로는 못 보는) tab 값이 주소에 있으면 첫 탭으로 떨어진다 ... 빈 화면이나 에러 대신 항상 뭔가를 보여주게 한다」. **의도 자체는 명시돼 있으나 두 경우를 묶은 것이 문제다.** 상충하는 명시 의도가 `AdminRoutes.jsx` 의 `RequireRole`(명시적 거부 화면)과 `PA-RC-0024`(주소가 화면 상태의 정본)에 있다. 어느 쪽이 옳은지에 대한 판단은 INFERRED 이며 근거는 제품 내 일관성이다.
findings: PA-F-088
feature_contracts: FC-시스템설정, FC-권한거부표현
routes: `/settings`, `/system`, `/llm-console`, `/notion-console`, `/maintenance`
frontend: `frontend/src/screens/settings/SettingsShell.jsx:51-68`(`TAB_DEFS`·`visibleTabs`·`tab` 결정), `frontend/src/app/AdminRoutes.jsx`(옛 주소 4종의 `Navigate` 리다이렉트), `frontend/src/ui/kit.jsx` `EmptyState`(라우트 게이트가 쓰는 거부 표현)
api: 해당 없음 - 표시 계층 문제다. 서버 게이트는 이미 옳다
backend: 해당 없음 - 백엔드 변경이 필요하지 않다
data: 해당 없음 - 저장 데이터가 바뀌지 않는다
rbac: **경계는 바뀌지 않는다.** `TAB_DEFS` 의 `roles: ["system_admin"]` 세 탭은 그대로 유지되고 서버 게이트도 그대로다. 바뀌는 것은 거부를 **어떻게 말하는가**뿐이다
integration: 해당 없음 - 외부 연동과 무관하다
state_transition: 해당 없음 - 상태 전이가 없는 표시 경로다
user_impact: TEST SERVER 23명 중 `system_admin` 은 2명뿐이라 나머지 콘솔 사용자(admin 14 · operator 1 · auditor 2)가 전부 이 경로에 있다. 사용자는 자신이 무언가를 못 보고 있다는 사실 자체를 모른 채 다른 화면을 본다. 주소를 북마크하거나 공유하면 계속 다른 화면이 열려 「링크가 고장 났다」로 읽힌다.
implementation_direction: `SettingsShell` 에서 두 경우를 갈라 처리한다. (1) **모르는 tab 값**(오타·삭제된 탭)은 지금처럼 첫 탭으로 떨어뜨리되 주소를 `replace` 로 정정해 주소와 화면을 일치시킨다. (2) **역할 때문에 못 보는 tab** 은 라우트 게이트와 **같은 어휘**로 거부를 보여준다. `AdminRoutes.jsx` 의 `RequireRole` 이 쓰는 `EmptyState`(`title="권한이 없습니다"`, `art="noPermission"`, 이동 버튼)를 그대로 재사용한다 - 새 컴포넌트를 만들지 않는다. (3) `visibleTabs.length === 1` 이면 탭 스트립을 그리지 않는다(전환할 것이 없는 탭 바는 장식이다). 옛 라우트 4종의 리다이렉트 자체는 유지한다 - 죽은 링크를 만들지 않는 것이 `PA-RC-0017` 의 의도였다.
constraints: CLAUDE.md 3-5(권한 판단은 서버가 정본 - 프런트 표시를 바꾸되 게이트를 넓히지 않는다) · 3-6(서버 데이터를 `innerHTML` 로 주입하지 않는다) · `PA-RC-0017` 이 만든 탭 통합 구조와 옛 주소 리다이렉트를 되돌리지 않는다 · `PA-RC-0024` 의 딥링크 계약(주소가 화면 상태의 정본)을 지킨다 · `useQueryState(TAB_SPEC)` 의 기존 쿼리 상태 관례를 따른다
regression_risk: (a) 주소를 `replace` 로 정정하면 뒤로가기 동작이 바뀔 수 있다 - 히스토리에 항목을 쌓지 않는 `replace` 여야 뒤로가기가 이전 화면으로 간다. (b) 거부 화면을 넣을 때 `system_admin` 의 정상 경로가 영향받지 않아야 한다(4탭·요청 탭 활성). (c) 탭이 1개일 때 스트립을 숨기면 `PageHeader` 의 `tab={activeLabel}` 표시와 중복·누락이 생기지 않는지 확인한다. (d) `Project.jsx` 상세 탭이 같은 MUI Tabs 패턴을 쓰지만 **이 RC의 범위가 아니다**(`SettingsShell.jsx:70` 주석이 그 차이를 이미 기록하고 있다).
acceptance_criteria: (1) `admin`·`operator` 가 `/system`·`/llm-console`·`/notion-console` 로 들어오면 주소와 화면이 일치한다 - 주소가 정정되거나 거부 화면이 뜬다. (2) 거부를 보여주는 경우 그 표현이 라우트 게이트(「권한이 없습니다」 + 설명 + 이동 버튼)와 **같다**. (3) `system_admin` 은 4탭이 그대로 뜨고 요청한 탭이 정확히 활성화된다(회귀 없음). (4) 탭이 1개인 역할에게 전환 불가능한 탭 스트립이 보이지 않는다. (5) `/maintenance` -> `?tab=policy` 는 모든 역할에서 지금처럼 정상 동작한다(볼 수 있는 탭이라 원래 문제가 없다). (6) 역할 3종 x 라우트 4종 12조합을 다시 실측해 주소·화면 불일치가 0이다.
required_tests: (1) `SettingsShell` 컴포넌트 테스트 - 역할별 `visibleTabs`, 못 보는 탭 요청 시의 표현, 모르는 탭 값 요청 시의 주소 정정. (2) 12조합(역할 3 x 옛 라우트 4) 라우팅 테스트. (3) `system_admin` 정상 경로 회귀 테스트. (4) 실브라우저 재측정으로 수용 기준 (6) 을 확인.
qa_gaps: `QA_COVERAGE.md` 에 「주소와 화면이 같은 것을 말하는가」 축이 없다. 기존 검증은 화면이 열리는지(4xx/5xx·console error)만 보므로 **잘못된 화면이 성공적으로 열리는 것**은 전부 통과한다. `PA-RC-0029`가 드러낸 것과 같은 종류의 공백이다 - 검사가 "실패"만 보고 "틀림"은 안 본다.
quality_rubric: `ux-writing` - 권한 거부 문구의 일관성, 그리고 **없어서 문제인 문구**(거부를 아예 말하지 않는 것)를 핵심 근거로 삼았다. `ui-ux-pro-max` - 내비게이션/IA 의 「사용자가 지금 어디에 있는지 알 수 있는가」. 내장 rubric 4) 「같은 의미가 같은 component/pattern 으로 표현되는가」 - 한 콘솔에 권한 거부 표현이 두 벌인 것이 Root Cause 판정의 근거다.
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md` PA-F-088 · `frontend/src/screens/settings/SettingsShell.jsx:51-68` · `frontend/src/app/AdminRoutes.jsx`(옛 주소 리다이렉트 4종) · `var/product-audit/shots2/d1_admin_settings.png` · 12조합 실측(역할 3 x 라우트 4)
current_state: `admin`·`operator` 로 `/settings` 를 열면 탭이 `시스템 정책` 하나뿐이고, 그 아래 설정 표 11행 + `유지보수` + `점검 공지` 가 이어진다. 옛 주소 4종으로 들어와도 같은 화면이 뜨는데 주소만 `?tab=os|ai|integration` 으로 남는다. `system_admin` 은 4탭을 본다.
user_problem: 자신이 무언가를 못 보고 있다는 사실을 모른 채 다른 화면을 본다. 주소를 북마크·공유하면 계속 다른 화면이 열려 링크가 고장 난 것처럼 보인다.
design_verdict: REFINE
target_state: 주소와 화면이 항상 같은 것을 말한다. 권한이 없어 못 보는 탭을 요청하면 제품의 다른 곳과 같은 말투로 그 사실을 알려 준다. 탭이 하나뿐인 역할에게는 탭 바가 없다.
target_design: 탭 구조·탭 구성·`/settings` 통합 자체는 그대로 둔다(`PA-RC-0017` 의 성과를 유지). 바뀌는 것은 셋 - 주소 정정(`replace`), 역할 거부 시 기존 `EmptyState` 재사용, 단일 탭일 때 스트립 숨김. 새 컴포넌트·새 시각 언어를 만들지 않는다.
visual_change_required: true
target_visual_delta: `admin`·`operator` 의 `/settings` 에서 탭 스트립(높이 약 48px, 탭 1개)이 사라진다. 옛 주소로 진입하면 주소창의 `?tab=os` 가 사라지거나, 「권한이 없습니다」 EmptyState(아이콘 + 제목 + 설명 + 버튼)가 본문 자리에 나타난다. `system_admin` 화면은 한 픽셀도 바뀌지 않는다.
affected_surfaces: `A-SETTINGS` `/settings`, 옛 주소 `/system`·`/llm-console`·`/notion-console`·`/maintenance`
affected_components: `settings/SettingsShell.jsx`(`TAB_DEFS` 필터·`tab` 결정·탭 렌더), `ui/kit.jsx` `EmptyState`(재사용, 수정 없음), `AdminRoutes.jsx`(리다이렉트 유지)
workflow_change: 없음 - 볼 수 있는 것과 없는 것이 바뀌지 않는다. 못 보는 경우에 그 사실을 알게 되는 것뿐이다
navigation_impact: 옛 주소 4종의 리다이렉트는 유지된다. 사이드바 항목도 그대로다. 주소가 화면과 일치하게 되어 딥링크·새로고침·뒤로가기가 성립한다
data_impact: 해당 없음 - 데이터 의미가 바뀌지 않는다
api_impact: 해당 없음 - API 계약이 바뀌지 않는다
rbac_impact: **없어야 한다.** `TAB_DEFS` 의 `roles: ["system_admin"]` 을 넓히지 않는다 - 수용 기준 (3) 이 `system_admin` 회귀를, (1)(2) 가 나머지 역할이 여전히 내용을 못 보는 것을 확인한다
browser_verification: TEST SERVER 에서 `system_admin`·`admin`·`operator` 세 역할로 `/settings` 와 옛 주소 4종(총 12조합)을 1920x1080 라이트/다크 두 테마로 열어 주소·활성 탭·탭 수·거부 표현을 스크린샷으로 확인한다. `system_admin` 화면이 변하지 않았음을 이전 스크린샷과 대조한다.
<!-- PA-RC-END -->

---

<!-- PA-RC-BEGIN PA-RC-0031 -->
rc_id: PA-RC-0031
severity: Medium
priority: P2
confidence: Confirmed
problem: 사이드바 그룹 이름이 그 안의 내용을 설명하지 못한다. 관리자 `감사` 그룹 6개 중 3개(`기능 플래그`·`공지 배너`·`복구 리허설`)가 감사가 아니고, 같은 명사가 두 그룹으로 쪼개지며(`정책`은 `연동`, `정책 사용 통계`는 `감사`), 구조가 같은 사용 통계 화면 둘이 서로 다른 그룹에 있고(`프롬프트 사용 통계`는 `연동`, `정책 사용 통계`는 `감사`), 한 업무가 갈라진다(`백업`은 `운영`, 그 백업의 복구 가능성을 확인하는 `복구 리허설`은 `감사`). 업무용어 뒤에 기술용어를 괄호로 다는 좋은 관례가 34항목 중 3개에만 적용돼 나머지는 내부 구현 용어 그대로다. 사용자 콘솔에서는 `문서` 그룹이 `문서`와 `휴지통` 둘뿐인데 휴지통은 문서 화면 안의 상태이지 형제 메뉴가 아니다.
expected: 메뉴 그룹은 **업무 기준**으로 묶여야 하고, 그룹 이름만 보고 그 안에 무엇이 있는지 예측할 수 있어야 한다. 같은 종류의 화면은 같은 그룹에, 한 업무를 위해 함께 여는 화면은 인접해야 한다. 용어 규칙은 34항목 전체가 한 벌을 따라야 한다. 이 기대의 근거는 CLAUDE.md §5(「메뉴가 업무 기준인가 시스템 내부 구현 기준인가」·「같은 Workflow가 여러 Group에 흩어져 있지 않은가」를 Frontend 필수 완료 범위로 규정)와, 이 제품이 이미 3개 항목에서 스스로 확립한 `업무용어(기술용어)` 관례다.
actual: `pa2_ia.py` 가 아코디언을 전부 펼친 뒤 DOM 에서 덤프한 실제 트리 — 관리자 5그룹 34항목(`운영` 7 · `사용자와 권한` 7 · `자동화` 7 · `연동` 7 · `감사` 6), 사용자 5그룹 18항목(`내 업무` 5 · `도우미` 2 · `문서` 2 · `팀 공간` 6 · `내 정보` 3). 위 여섯 가지 어긋남은 전부 이 덤프에서 직접 읽은 것이다.
intent_evidence: CLAUDE.md §5 가 Navigation/IA 를 필수 완료 범위로 명시하고 그 판단 기준을 열거한다. 이 제품 자신이 `실행 일정(스케줄)`·`자동화 작업 실행기(러너)`·`업무 자동화 흐름(워크플로)` 세 항목에서 `업무용어(기술용어)` 관례를 확립했다 — 그 관례의 존재가 「내부 구현 용어를 그대로 쓰지 않는다」는 의도의 근거다. 다만 **어느 항목이 어느 그룹에 속해야 하는가에 대한 명시적 문서는 없다** — 그 부분은 INFERRED 이며 근거는 업무 인접성(백업↔복구 리허설)과 화면 종류의 동일성(사용 통계 둘)이다.
findings: PA-F-090
feature_contracts: FC-관리자내비게이션, FC-사용자내비게이션
routes: 사이드바가 가리키는 관리자 34개 · 사용자 18개 전부(라우트 자체는 하나도 바뀌지 않는다)
frontend: `frontend/src/app/navConfig.js`(그룹·항목·라벨 정의, 386줄), `frontend/src/app/AppShell.jsx`(사이드바 렌더), `frontend/src/screens/registry/*.js`(화면 title 이 메뉴 라벨과 일치해야 하는 곳)
api: 해당 없음 - 메뉴 구성은 프런트 설정이고 서버 계약과 무관하다
backend: 해당 없음 - 백엔드 변경이 필요하지 않다
data: 해당 없음 - 저장 데이터가 바뀌지 않는다
rbac: **경계를 바꾸지 않는다.** 각 항목의 역할 조건(`SCREEN_ROLES`)은 그대로 옮겨 간다. 그룹이 바뀌어도 누가 무엇을 보는지는 한 항목도 달라지면 안 된다 - F축 63조합 검증이 회귀 기준이다
integration: 해당 없음 - 외부 연동 계약과 무관하다
state_transition: 해당 없음 - 상태 전이가 없다
user_impact: 관리자가 한 업무를 끝내려고 그룹을 오간다. 백업 점검(`운영`의 `백업` → `감사`의 `복구 리허설`)과 사용 통계 확인(`연동` → `감사`)이 실측된 두 사례다. 그리고 `감사` 그룹을 열었을 때 절반이 감사가 아니라서, 그룹 이름으로 위치를 기억하는 방식이 통하지 않는다 - 항목 34개짜리 메뉴에서 이것은 매번 전체를 훑게 만든다.
implementation_direction: 그룹을 업무 기준으로 다시 긋는다. (1) `감사`에 감사만 남기고 **사용 통계 둘을 여기로 모은다**(`감사 로그`·`감사 이상 징후`·`정책 사용 통계`·`프롬프트 사용 통계`) - 이 한 수로 「같은 명사 분리」와 「같은 종류 화면 분리」가 동시에 풀린다. (2) `복구 리허설`을 `백업` 바로 옆 `운영`으로 옮긴다. (3) `기능 플래그`를 `운영`의 설정 계열로, `공지 배너`를 콘텐츠를 다루는 `자동화`로 옮긴다. (4) 용어 규칙을 하나로 정한다 - 이미 3개가 쓰는 `업무용어(기술용어)` 형식을 34항목 전체에 적용하거나, 반대로 그 3개에서 괄호를 빼 한 벌로 만든다. **둘 중 어느 쪽이든 좋으나 섞여 있으면 안 된다.** (5) 사용자 콘솔의 `휴지통`을 메뉴에서 빼고 `문서` 화면 안의 뷰로 넣는다 - 그러면 `문서` 그룹이 1항목이 되므로 그룹을 없애고 `팀 공간`에 합친다. 라우트(`#/team-docs/trash`)는 살려 두어 기존 링크가 죽지 않게 한다. 변경은 대부분 `navConfig.js` 한 파일에서 끝난다.
constraints: CLAUDE.md §3-5(권한 판단은 서버가 정본 - 메뉴를 옮기되 `SCREEN_ROLES` 를 넓히거나 좁히지 않는다) · §5(per-page 예외보다 shared 구조 우선) · **라우트를 삭제하지 않는다** - 옛 주소가 죽으면 즐겨찾기와 화면 간 딥링크가 끊긴다(`AdminRoutes.jsx` 가 `/organizations`·`/departments`·`/org-tree` 에서 이미 그 이유로 세 주소를 모두 유지한다) · 화면 제목과 메뉴 라벨이 갈라지지 않게 `registry/*.js` 의 `title` 을 함께 맞춘다
regression_risk: (a) **역할별 노출이 바뀌는 것이 가장 큰 위험이다** - 항목을 그룹 사이로 옮기면서 `SCREEN_ROLES` 조건을 빠뜨리면 조용히 권한이 넓어지거나 좁아진다. F축 63조합(21라우트 × 3역할)을 회귀 기준으로 그대로 다시 돌린다. (b) 메뉴 라벨을 바꾸면 `labelForPath` 를 쓰는 document title·breadcrumb·커맨드 팔레트가 함께 움직인다 - `frontend/src/app/document-title-item-override.test.jsx` 같은 기존 테스트가 라벨에 의존한다. (c) 사용자 콘솔에서 `휴지통` 메뉴를 없앨 때 라우트까지 지우면 딥링크가 끊긴다. (d) 그룹 수가 바뀌면 사이드바 세로 길이가 변해 좁은 뷰포트에서 스크롤이 생길 수 있다.
acceptance_criteria: (1) `감사` 그룹의 모든 항목이 감사·통계다(`기능 플래그`·`공지 배너`·`복구 리허설`이 그 그룹에 없다). (2) `정책 사용 통계`와 `프롬프트 사용 통계`가 **같은 그룹**에 있다. (3) `백업`과 `복구 리허설`이 같은 그룹에 인접한다. (4) 34항목의 라벨이 하나의 용어 규칙을 따른다 - 괄호 병기를 쓰든 안 쓰든 섞이지 않는다. (5) 사용자 콘솔에 `휴지통` 메뉴 항목이 없고 `#/team-docs/trash` 주소는 여전히 동작한다. (6) **역할별 메뉴 노출이 변경 전과 정확히 같다** - F축 63조합 재실행에서 나브·화면·API 불일치 0. (7) 모든 라우트가 살아 있다(삭제된 주소 0).
required_tests: (1) `pa2_rbac.py` 재실행으로 수용 기준 (6) - 21라우트 × 3역할에서 나브 노출이 변경 전 스냅샷과 일치. (2) `navConfig.js` 의 그룹·항목 구성을 고정하는 단위 테스트(그룹별 항목 목록). (3) `labelForPath` 소비자(document title·breadcrumb·커맨드 팔레트) 회귀 테스트 - 기존 `document-title-item-override.test.jsx` 포함. (4) `#/team-docs/trash` 딥링크가 메뉴 없이도 동작하는 라우팅 테스트. (5) `pa2_ia.py` 재실행으로 새 트리를 덤프해 수용 기준 (1)~(4)를 기계적으로 확인.
qa_gaps: `QA_COVERAGE.md` 에 「메뉴 분류가 업무와 맞는가」 축이 없다. 기존 검증은 각 라우트가 열리는지와 역할 게이트가 맞는지만 보므로, **모든 화면이 정상인데 찾을 수 없는 상태**는 전부 통과한다. 이 Cycle의 `PA-RC-0029`·`PA-RC-0030`과 같은 종류의 공백이다 - 검사가 "실패"만 보고 "틀림"은 안 본다.
quality_rubric: `ui-ux-pro-max` - Navigation/IA 의 「그룹 이름이 내용을 예측하게 하는가」·「같은 Workflow 가 여러 Group 에 흩어져 있지 않은가」. `redesign-existing-projects` - *"메뉴를 없애고 다른 화면 안으로 넣는 게 나은 경우는 없는가"* 로 사용자 콘솔 `휴지통` 판단. `impeccable` - 용어 규칙의 일관성(34항목 중 3개만 괄호 병기). 내장 rubric 4) 「같은 의미가 같은 component/pattern 으로 표현되는가」 - 사용 통계 두 화면이 다른 그룹에 있는 것을 Root Cause 로 묶은 근거.
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md` PA-F-090 · `PRODUCT_AUDIT_DESIGN.md` `navigation-ia` 판정 블록 · `var/product-audit/pa2_ia.py` 실행 결과 · `var/product-audit/pa2_ia.json`(그룹·항목 전체 덤프) · `frontend/src/app/navConfig.js` · `var/product-audit/shots2/d1_admin_dashboard.png` · `d1_user_me.png`
current_state: 관리자 5그룹 34항목 - `운영`(대시보드·알림·작업 큐·설정·진단·백업·메일 발송) `사용자와 권한`(사용자·오프보딩·조직 관리·직책 관리·권한 매트릭스·Notion 사용자 연결·대리 보기) `자동화`(실행 일정(스케줄)·실행 달력·문서 자동 생성·승인·승인 위임·AI 사용 상한·개발자 월간 리포트) `연동`(외부 연동·자동화 작업 실행기(러너)·업무 자동화 흐름(워크플로)·프롬프트·정책·템플릿·프롬프트 사용 통계) `감사`(감사 로그·감사 이상 징후·기능 플래그·공지 배너·복구 리허설·정책 사용 통계). 사용자 5그룹 18항목.
user_problem: 한 업무를 끝내려고 그룹을 오간다(백업 점검·사용 통계 확인). `감사` 그룹의 절반이 감사가 아니라서 그룹 이름으로 위치를 기억할 수 없고, 34항목 메뉴에서 매번 전체를 훑게 된다.
design_verdict: REDESIGN
target_state: 그룹 이름만 보고 그 안에 무엇이 있는지 예측할 수 있다. 한 업무를 위해 함께 여는 화면이 인접해 있다. 34개 라벨이 한 가지 용어 규칙을 따른다. 볼 수 있는 화면과 권한은 변경 전과 똑같다.
target_design: `감사` = 감사 로그 · 감사 이상 징후 · 정책 사용 통계 · 프롬프트 사용 통계. `운영` = 기존 7개 + 복구 리허설 + 기능 플래그. `자동화` = 기존 7개 + 공지 배너. `연동` = 외부 연동 · 러너 · 워크플로 · 프롬프트 · 정책 · 템플릿. 용어는 `업무용어(기술용어)` 한 규칙으로 통일. 사용자 콘솔은 `휴지통`을 `문서` 화면의 뷰로 넣고 `문서` 그룹을 `팀 공간`에 합쳐 4그룹으로 만든다. 라우트는 하나도 지우지 않는다.
visual_change_required: true
target_visual_delta: 관리자 사이드바에서 `감사` 그룹이 6항목에서 4항목으로 줄고 `운영`이 7에서 9, `자동화`가 7에서 8로 는다. 항목 라벨 일부가 괄호 병기 형식으로 바뀐다. 사용자 사이드바는 5그룹 18항목에서 **4그룹 17항목**이 되어 `문서` 그룹 헤더 한 줄과 `휴지통` 한 줄이 사라진다.
affected_surfaces: 관리자 사이드바 전체(34항목), 사용자 사이드바 전체(18항목), 그리고 라벨을 읽는 breadcrumb·document title·커맨드 팔레트
affected_components: `frontend/src/app/navConfig.js`(주 변경), `frontend/src/app/AppShell.jsx`, `frontend/src/screens/registry/*.js`(화면 title 정합), `frontend/src/app/CommandPalette.jsx`(라벨 소비)
workflow_change: 업무 동선이 **짧아진다** - 백업 점검이 한 그룹 안에서 끝나고 사용 통계가 한 그룹에 모인다. 사용자가 할 수 있는 일과 권한은 바뀌지 않고, 같은 화면에 도달하는 경로만 짧아진다
navigation_impact: 이 RC 자체가 Navigation/IA 변경이다. 그룹 구성과 라벨이 바뀌고 사용자 콘솔은 그룹이 5개에서 4개가 된다. **라우트는 하나도 바뀌지 않으며 옛 주소는 전부 살아 있다**
data_impact: 해당 없음 - 데이터 의미가 바뀌지 않는다
api_impact: 해당 없음 - API 계약이 바뀌지 않는다
rbac_impact: **없어야 한다.** 각 항목의 `SCREEN_ROLES` 조건을 그대로 들고 옮긴다. 수용 기준 (6)이 F축 63조합 재실행으로 이것을 검사하며, 한 조합이라도 달라지면 실패다
browser_verification: TEST SERVER 에서 `admin`·`operator`·`auditor`·`user` 네 역할로 로그인해 1920×1080 라이트/다크로 사이드바를 캡처하고, `pa2_ia.py` 로 새 트리를 덤프해 그룹 구성이 목표와 일치하는지 확인한다. 이어서 `pa2_rbac.py` 를 돌려 역할별 노출이 변경 전과 같은지 대조한다 - 화면과 권한을 한 번에 본다.
<!-- PA-RC-END -->

---

<!-- PA-RC-BEGIN PA-RC-0032 -->
rc_id: PA-RC-0032
severity: High
priority: P1
confidence: Confirmed
problem: 이 저장소는 SQLite 쓰기 경합을 다루는 공용 관용(`is_write_conflict` + `DEFAULT_WRITE_CONFLICT_RETRIES` + `write_conflict_backoff`)을 갖고 있고 25개 모듈이 그것을 쓴다. 그런데 두 개의 중요한 쓰기 경로에 그 보호가 없어서 `sqlite3.OperationalError: database is locked` 가 그대로 500으로 나간다 - 최초 로그인 강제 관문인 `POST /change-password`(`app/auth/router.py::change_password`)와 AI 대화 전송을 포함한 `app/chat/` 모듈 전체다. 같은 파일의 `login()` 은 그 관용의 기준 구현을 갖고 있는데, 쓰기를 더 많이 하는 `change_password()` 에는 없다.
expected: 쓰기 경합(`database is locked`)은 사용자에게 보이는 오류가 아니라 서버가 재시도로 흡수해야 하는 상태다. CLAUDE.md §3-10이 「SQLite write conflict/busy/locked 판정은 기존 공용 classifier/retry 규약을 재사용한다」고 못박고, `app/core/db.py:183` 이 그 기본값(재시도 10회 + 지터)을 **실측으로 검증된 값**으로 승격해 두었다. 재시도를 다 쓰고도 실패하면 그때는 500이 아니라 사용자가 무엇을 해야 하는지 아는 오류여야 한다.
actual: TEST SERVER(HEAD) 실측 - 오늘 `POST /change-password` 31건 중 **3건이 500**(약 10%), traceback 은 `app/auth/router.py` 689행의 `sqlite3.OperationalError: database is locked`. `POST /api/conversations/{id}/messages` 도 같은 예외로 500(05:09:23). 화면에는 「서버 오류로 비밀번호를 변경하지 못했습니다. 잠시 후 다시 시도해 주세요.」만 뜨고, 그때 클라이언트 검증 4종은 전부 통과 상태였다.
intent_evidence: (1) CLAUDE.md §3-10 - 공용 classifier/retry 규약 재사용 의무. (2) `app/core/db.py:183-210` - `DEFAULT_WRITE_CONFLICT_RETRIES = 10` 과 `write_conflict_backoff()` 를 「`app/auth/router.py`의 로그인 재시도가 실측으로 검증된 유일한 값」이라며 공용으로 승격한 주석, 그리고 「13개 호출부가 이미 이 패턴을 쓴다」. (3) `PA-RC-0008`(직전 Cycle) 이 이미 이 관용의 예산·지터를 통일했다. (4) 직전 커밋 `d5ba3f9` 가 알림 경로에 같은 처방(SAVEPOINT 재시도)을 적용했다 - 같은 결함 유형을 이 제품이 이미 결함으로 인정하고 고친 전례다. 의도는 INFERRED 가 아니라 **문서·코드·직전 수정 전례에 명시**돼 있다.
findings: PA-F-091
feature_contracts: FC-최초로그인-비밀번호변경, FC-AI대화전송
routes: `/change-password`(전체 사용자 필수 관문), `/chat`(AI 도우미), 그리고 `app/chat/` 이 지원하는 대화 화면 전부
frontend: `app/templates` 의 비밀번호 변경 화면과 `static/js/change_password.js`(서버 오류 문구 표시부), `frontend/src/screens/Chat*.jsx` 계열(전송 실패 표시)
api: `POST /change-password`, `POST /api/conversations/{id}/messages`, 그리고 `app/chat/router.py` 의 나머지 쓰기 엔드포인트
backend: `app/auth/router.py::change_password`(631-700행 부근, 실패 지점 689), `app/chat/router.py`·`app/chat/service.py`·`app/chat/attachments.py`(세 파일 모두 `is_write_conflict` 0회). 기준 구현은 같은 파일의 `app/auth/router.py::login`(476-508행)
data: 스키마 변경 없음. `users.password_hash`·`sessions`·`audit_logs`·대화/메시지 테이블에 대한 쓰기 경계가 대상이다
rbac: 해당 없음 - 권한 경계가 바뀌지 않는다. 재시도는 이미 인증된 요청 안에서 일어난다
integration: 해당 없음 - 외부 연동과 무관한 로컬 DB 경합이다
state_transition: `must_change_password: true -> false` 전이와 세션 폐기·재생성이 한 요청 안에서 일어난다. 이 전이가 부분적으로 남지 않아야 한다
user_impact: `change-password` 는 선택 화면이 아니라 **관문**이다. 최초 로그인과 관리자 비밀번호 재설정 직후에는 통과하지 못하면 제품에 들어갈 수 없다. 오늘 실측 실패율 약 10%이고, 가장 흔한 발생 시점이 신규 입사자의 첫 접속이라 제품의 첫인상이 원인 불명의 서버 오류가 된다. 사용자는 자신이 무엇을 잘못했는지 알 수 없다(아무 잘못도 없다). AI 대화 전송은 이 제품이 파는 핵심 상호작용이라 같은 잠금에서 raw 500이 나면 기능 실패다.
implementation_direction: 공용 관용을 두 경로에 적용한다. (1) `app/auth/router.py::change_password` 를 같은 파일 `login()`(476-508행)과 **같은 형태**로 감싼다 - `except (IntegrityError, OperationalError) as exc: if not is_write_conflict(exc) or attempt == N-1: raise; time.sleep(write_conflict_backoff(attempt))`. 예산은 `DEFAULT_WRITE_CONFLICT_RETRIES` 기본값을 쓴다(다르게 쓸 이유가 없다). **재시도 루프 구조 자체는 공용화하지 않는다** - `app/core/db.py:183` 주석이 "무엇을 다시 계산해야 하는지가 호출부마다 다르므로 예산·지터만 공용"이라고 이미 판단했고, 여기서 다시 계산해야 하는 것은 세션 재생성이다. (2) `app/chat/` 의 쓰기 경로(최소 `post_message`)에 같은 관용을 적용한다. (3) 재시도를 소진했을 때는 raw 500이 아니라 사용자가 다음 행동을 아는 오류로 접는다 - 이 저장소의 실패 문구 3요소(무엇이/왜/무엇을 하라) 규약을 따른다. (4) `app/core/sessions.py::_commit_best_effort` 는 **일부러** 기본값을 안 쓰는 예외로 명시돼 있으므로 건드리지 않는다.
constraints: CLAUDE.md §3-1(sync 일관성 - `async def` 추가 금지) · §3-10(**SAVEPOINT/`begin_nested()` 는 실제 outer transaction 안에서 동작해야 한다**. `app/core/db.py` 의 명시적 transaction/BEGIN 규약을 우회하지 않는다) · §3-3/§3-4(비밀번호·토큰을 로그에 남기지 않는다 - 재시도 로깅에 자격증명이 섞이면 안 된다) · §11.3 세션 규약(비밀번호 변경 시 다른 세션 전부 폐기 + 세션 회전)을 재시도 중에도 유지한다 · `:memory:` DB 로 WAL/멀티커넥션 의미를 대체하지 않는다
regression_risk: (a) **재시도 루프가 세션 회전을 두 번 하면 안 된다** - `revoke_all_for_user` + `create` 를 재시도 안에서 다시 부를 때 이전 시도의 부분 상태가 남아 있으면 세션이 중복 생성되거나 방금 만든 세션을 스스로 폐기할 수 있다. 무엇을 다시 계산할지(rollback 후 재조회인지 SAVEPOINT 되감기인지)를 명시적으로 정해야 한다. (b) 재시도로 응답이 느려진다 - `app/core/db.py` 가 예산 10에서 최대 누적 2.25초로 계산해 두었고 nginx `proxy_read_timeout 180s` 대비 무시할 수준이라고 이미 판단했다. (c) `app/chat/` 은 잡 큐에 넣는 경로라 재시도가 **중복 잡 생성**을 만들지 않는지 확인해야 한다(멱등성). (d) 알림 경로(`d5ba3f9`)가 배포 후 500 0건으로 유지되고 있으므로 그 수정을 건드리지 않는다.
acceptance_criteria: (1) 쓰기 경합을 인위적으로 만든 상태에서 `POST /change-password` 가 500을 내지 않는다 - 재시도로 성공하거나, 소진 시 사용자 행동을 안내하는 오류로 접힌다. (2) 같은 조건에서 `POST /api/conversations/{id}/messages` 가 500을 내지 않는다. (3) `app/chat/` 의 쓰기 경로에서 `is_write_conflict` 사용이 0이 아니다. (4) 재시도 후에도 §11.3 세션 규약이 유지된다 - 비밀번호 변경 성공 시 다른 세션은 전부 폐기되고 새 세션 하나만 남는다(세션 표 직접 조회로 확인). (5) **부분 쓰기가 남지 않는다** - 실패한 요청 뒤에 `must_change_password` 와 `password_hash` 가 요청 이전 상태로 일관된다. (6) AI 대화 전송 재시도가 잡을 중복 생성하지 않는다. (7) TEST SERVER 로그에서 `database is locked` 로 인한 500이 0건이다.
required_tests: (1) `tests/integration/test_notifications_write_conflict.py`(`d5ba3f9` 가 만든 것)를 **본보기로** `change_password` 용 쓰기 경합 테스트를 신설한다 - 같은 harness 를 재사용하면 판정이 갈라지지 않는다. (2) 같은 방식으로 `app/chat/` 의 `post_message` 쓰기 경합 테스트. (3) 재시도 성공 후 세션 규약(§11.3) 검증 테스트 - 다른 세션 전부 폐기 + 새 세션 1개. (4) 실패 경로에서 부분 쓰기가 없음을 확인하는 테스트(수용 기준 5). (5) 대화 전송 재시도의 잡 멱등성 테스트. (6) 회귀: 알림 경로의 기존 쓰기 경합 테스트가 계속 통과한다.
qa_gaps: `QA_COVERAGE.md` 에 「쓰기 경합에서 각 엔드포인트가 어떻게 답하는가」 축이 알림 경로에만 있다(`d5ba3f9` 가 만든 테스트 하나). 인증 관문과 AI 대화라는 **가장 중요한 두 쓰기 경로**에는 그 축이 없다. 더 넓게는 「25개 모듈은 공용 관용을 쓰는데 어느 모듈이 안 쓰는가」를 기계적으로 검사하는 정적 검사가 없어서, 새 쓰기 경로가 보호 없이 추가돼도 아무것도 빨개지지 않는다 - `scripts/static_checks.sh` 에 그 검사를 넣는 것을 함께 검토한다.
quality_rubric: 해당 없음 - 기능/데이터 정합성 계열이라 UI 품질 rubric 이 무관하다. 판정 기준은 CLAUDE.md §3-10(공용 classifier/retry 규약 재사용)과 §6(회귀 결함은 수정 전 실패 -> 수정 후 통과로 확인)이며, 사용자에게 보이는 실패 문구에 한해 `ux-writing` 의 3요소(무엇이/왜/무엇을 하라)를 적용해 수용 기준 (1)의 "안내하는 오류"를 정의했다.
evidence_refs: `PRODUCT_AUDIT_FINDINGS.md` PA-F-091 · `app/auth/router.py:631-700`(실패 지점 689) · `app/auth/router.py:476-508`(기준 구현) · `app/core/db.py:154-210`(`is_write_conflict`·기본값·지터) · `app/chat/router.py:177`(`post_message`) · TEST SERVER `journalctl -u clovirone-web-assistant` 2026-08-17 02:25:53 / 05:09:23 / 08:12:45 / 08:14:06 traceback · 오늘 `POST /change-password` 31건 중 500 3건 집계
<!-- PA-RC-END -->
