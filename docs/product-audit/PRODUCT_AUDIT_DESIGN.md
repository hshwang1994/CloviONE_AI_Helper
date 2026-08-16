# PRODUCT AUDIT — DEEP UI/UX DESIGN AUDIT

> cycle_id=PA-20260817-072224-24b91505 · baseline=`2aacd2a2ab4a50e92d3dee8f3aba3a248e175e83`
>
> **이 문서는 이 Cycle에서 처음부터 다시 쓴다.** 직전 Cycle(`PA-20260816-120655`)의 판정
> 18건은 `REBUILD` 1 · `REDESIGN` 10 · `REFINE` 6 · `KEEP` 1 이었고 그 **전부가 구현됐다**
> (`PA-RC-0016`~`0026`, `IMPLEMENTATION_CONSUMED`). 즉 그 판정들이 묘사한 화면은 더 이상
> 존재하지 않는다 — 대시보드 카드는 40장에서 **11장**이 됐고, `/system`·`/llm-console`·
> `/notion-console`·`/maintenance` 는 `/settings?tab=*` 리다이렉트로 접혔다.
> 옛 판정을 옮겨 적는 것은 없어진 화면을 감사한 것이 된다. 아래는 **HEAD에서 다시 본 것**이다.
>
> 판정 어휘: `KEEP`(구조가 충분히 좋다 — 근거 필수) · `REFINE`(구조 유지 + 의미 있는 개선) ·
> `REDESIGN`(정보구조·레이아웃·동선의 상당한 변경) · `REBUILD`(기능 계약만 남기고 새로 구현).

## 진행 상태 — 정직하게

필수 18표면 중 **이 Cycle에서 실제로 깊게 판정한 것은 아래 6종**이다. 나머지 12종은
스크린샷과 레이아웃 계측은 확보했지만(`shots2/`, `pa2_design_*.json` — 28표면 실렌더)
UI/UX Skill 기준의 구조·위계 평가를 아직 마치지 않았다. **그 12종에 판정 블록을 쓰지 않는다**
— 계측만 있는 것을 `deep_audited: true` 로 적으면 그것이 조작이다.

| 상태 | 표면 |
|---|---|
| 판정 완료 (6) | `dashboard` · `home` · `admin-console` · `table-screens` · `app-shell` · `settings` |
| 계측·스크린샷만 (12) | `global-header` · `sidebar` · `navigation-ia` · `list-screens` · `detail-screens` · `forms` · `modal-drawer` · `ai-assistant-chat` · `empty-state` · `error-state` · `loading-state` · `key-workflows` |

## 적용한 Skill (실제 이름)

| Skill | 이 문서에서 쓴 자리 |
|---|---|
| `ui-ux-pro-max` | Data-Dense Dashboard 기준의 정보 위계·신호 대 잡음·동작 위계 |
| `redesign-existing-projects` | *"이 화면이 없으면 사용자가 무엇을 못 하는가"* 로 통합·분리 판단 |
| `impeccable` | 중복 요소 제거, 시각 위계 보정, 정상 상태의 면적 점유 |
| `ux-writing` | 상태 표현(0 vs `-` vs 문장), 없어서 문제인 문구 |

`skill_gap` 없음.

---

<!-- DESIGN-VERDICT-BEGIN dashboard -->
surface: dashboard
layout_family: dashboard
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: 1920×1080 실측 — 7섹션(`확인이 필요한 항목`·`서비스 상태`·`작업 지표 (최근 24시간)`·`백업`·`최근 주요 변경`·`내 업무`), 카드 11장, 세로 1580px, 본문 내 contained 버튼 1개. `확인이 필요한 항목`이 최상단에 있고 그 안에 조치가 필요한 2행이 각각 CTA를 갖는다. `서비스 상태`는 8개 서비스를 한 묶음으로 카드 8장 + 도넛 1개로 그린다. 본문 79줄 중 54줄(68%)이 `/diagnostics`에도 그대로 있다.
user_problem: 직전 Cycle의 REBUILD가 실제로 통했다 — 카드 40장이 11장이 됐고 「지금 조치할 것」이 화면 맨 위에 생겼다. 남은 문제는 화면 안이 아니라 **화면 사이**에 있다. (1) `/diagnostics`와 68% 같은 말을 하고, `최근 주요 변경`은 16/16 문자열이 동일하며 `백업`은 CTA까지 같다. (2) 같은 8개 서비스를 대시보드는 한 묶음, 진단은 4+4로 다르게 분류한다. (3) 정상 상태가 이상 상태와 같은 면적을 쓴다 — 카드 8장이 각각 「정상」이라 말한 뒤 도넛이 또 「정상 8개 (100%)」라고 말한다. 훑어서 이상을 찾는 화면에서 정반대 방향이다. (4) `확인이 필요한 항목`의 두 행이 **같은 라벨(`작업 큐 열기`)로 같은 곳**에 가면서 한쪽만 contained라 위계가 우연처럼 보인다.
target_design: 대시보드는 「지금 조치할 것」에만 전념한다. `확인이 필요한 항목`을 유지하되 같은 목적지로 가는 중복 CTA는 하나로 합친다. `서비스 상태`를 진단과 같은 2분류(`서비스 상태` 내부 프로세스 4 / `외부 연동` 4)로 통일하고, 도넛을 없애고 섹션 제목 옆 `정상 8 / 8` 한 줄로 요약한다 — 도넛이 차지하던 카드 한 장이 사라지고 정상 상태의 세로 점유가 준다. `최근 주요 변경`·`백업`은 대시보드가 정본으로 유지하고 진단 본문에서 뺀다(`PA-RC-0028`). 새 컴포넌트를 만들지 않는다 — `adminKit.jsx`의 `DashSection`·`StatusTile`·`SERVICE_GRID`를 그대로 쓴다.
rationale: 화면 자체의 위계는 이제 읽힌다(제목 → 조치 → 상태 → 지표). 그래서 `REBUILD`가 아니다. 그러나 정보의 **소속**이 틀렸다 — 진단과 겹치는 두 섹션, 화면마다 달라지는 서비스 분류, 카드가 이미 한 말을 반복하는 도넛은 전부 「이 사실이 어느 화면의 것인가」를 정하지 않아서 생긴다. 그것은 `REFINE`(구조 유지 + 개선)의 범위를 넘고, 두 화면의 역할 분담을 다시 그어야 풀린다.
browser_evidence: `var/product-audit/shots2/d1_admin_dashboard.png`(1920×1080 라이트, 전체 페이지) — `Read`로 열어 판정. 계측은 `pa2_design_admin.json`(카드 11 · 버튼 27 · contained 1 · scrollH 1580). 중복률은 눈이 아니라 `var/product-audit/pa2_dup.py`가 문자열로 계측(섹션 4종 공유, `최근 주요 변경` 16/16, 본문 68%).
rc_ids: PA-RC-0028
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN admin-console -->
surface: admin-console
layout_family: dashboard
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: `/diagnostics` 1920×1080 실측 — 11섹션(`오류`·`시스템 리소스`·`서비스 상태`·`외부 연동`·`설치처 설정`·`현재 리소스`·`작업 지표 (최근 24시간)`·`최근 작업 오류`·`백업`·`최근 주요 변경`·`원본 자료`), 카드 14장, 세로 2629px. 상단에 `진단 수집`·`복사`·`JSON 다운로드` 세 동작. 그중 4섹션이 `/dashboard`와 제목까지 같고 2섹션은 내용 문자열이 전부 같다. `/rbac`·`/integrations`는 각각 세로 1080px에 카드 2장으로 가볍다.
user_problem: 장애 대응 중 「어느 화면을 봐야 하는가」가 정해지지 않는다. 진단의 고유값(수집·마스킹·원본 JSON·시스템 리소스·설치처 설정)은 화면의 아래쪽에 있고, 위쪽 절반은 대시보드에서 이미 본 것이다. 그리고 두 화면의 수집 시점이 달라(대시보드 30초 폴링 · 진단 수동) 같은 지표가 동시에 다른 값으로 떠 있을 수 있다 — 실측 중 실제로 `19/94.7%` 대 `20/90%`가 그랬다. 부수적으로 `오류`라는 제목 아래에 실제로는 `주의 2`·`위험 1`이 들어 있어 제목과 내용의 심각도 어휘가 어긋난다.
target_design: 진단을 「지원팀에 넘길 스냅샷을 만드는 화면」으로 좁힌다. 첫 화면은 수집 상태 + 세 동작 + `오류 요약`이고, 그다음이 대시보드가 답하지 않는 것들(`시스템 리소스`·`설치처 설정`·`최근 작업 오류` 상세·`원본 자료`)이다. `최근 주요 변경`과 `백업`은 본문에서 빼고 대시보드 링크 한 줄로 대체한다 — **번들 페이로드는 그대로 유지한다**(지원팀 산출물은 완전해야 하고, `include_critical_audit`의 역할 분기도 그대로 살아 있어야 한다). 서비스 2분류(`서비스 상태`/`외부 연동`)를 이 화면의 것으로 삼고 대시보드가 그것을 따른다. 도넛 제거. 섹션 제목 `오류`를 내용의 실제 심각도에 맞게 고친다.
rationale: 이 화면은 존재 이유가 분명하다 — 마스킹된 번들을 만들어 밖으로 넘기는 것은 다른 어떤 화면도 못 한다. 그래서 `REBUILD`가 아니라 `REDESIGN`이다. 다만 지금은 그 고유 기능이 대시보드 복사본에 파묻혀 있다. `build_diagnostic_bundle`이 `build_dashboard()`를 통째로 품는 것은 **데이터로서는 옳고**(지원팀은 그 시점 운영 상태를 함께 봐야 한다) **화면으로서는 그대로 펼칠 이유가 없다** — 이 구분이 이 판정의 핵심이다.
browser_evidence: `var/product-audit/shots2/d1_admin_diagnostics.png`(1920×1080 라이트, 전체 페이지 2629px) — `Read`로 열어 판정. `d1_admin_rbac.png`·`d1_admin_integrations.png` 함께 확인. 계측 `pa2_design_admin.json`(카드 14 · 버튼 24 · scrollH 2629). 중복은 `pa2_dup.py` 문자열 계측. 소스 근거는 `app/health/service.py:390` docstring의 「embeds a full build_dashboard() call」.
rc_ids: PA-RC-0028
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN home -->
surface: home
layout_family: dashboard
deep_audited: true
skills_applied: ui-ux-pro-max, ux-writing, impeccable
verdict: REFINE
current_state: `/me` 1920×1080 실측 — 카드 4장, 세로 1121px, contained 버튼 0. 상단에 개수 타일 6종(`오늘 마감`·`지연`·`진행 중`·`7일 내 마감`·`안 읽은 알림`·`안 읽은 채팅`), 좌측에 선택된 버킷의 티켓 목록, 우측에 `이번 주 내 진척`과 `최근 문서`, 하단에 `AI 도우미`(4탭). 미매핑 계정 기준으로 티켓 타일 4종이 전부 `0`이고, 그 아래 목록 패널은 「담당 티켓을 판단할 수 없어 목록을 불러올 수 없습니다」, 진척 카드는 「계산할 수 없습니다」다.
user_problem: 한 화면이 같은 상태에 대해 **세 가지 다른 답**을 동시에 준다. 숫자는 「없다」(`0`), 목록은 「모른다」, 진척은 「계산할 수 없다」. 숫자가 가장 크고 가장 먼저 읽히므로 사용자는 숫자를 믿는다 — 「오늘 마감 0」은 *"오늘 마감이 없다"* 로 읽힌다. TEST SERVER 기준 23명 중 10명이 이 상태에 있고, 가장 흔한 발생 시점이 입사 직후라 검증할 수단이 가장 없는 때다. 그 밖의 구조는 좋다 — 빈 상태가 원인·조치·기대 결과 3요소를 갖췄고(「1. 관리자에게 요청하세요 2. 새로고침하세요 / 기대 결과: 연결되면 여기 표시됩니다」) 이 저장소의 실패 문구 규약을 충실히 따른다.
target_design: 레이아웃·타일 수·배치를 바꾸지 않는다. 값 표현만 통일한다 — 판정 불가 상태에서 개수 타일이 `0` 대신 `-`를 그려 같은 화면의 문장들과 같은 말을 하게 한다. `StatCard`는 이미 `null`을 `-`로 그리므로 새 컴포넌트도 새 변형도 만들지 않는다. `AI 도우미`의 「오늘 마감 0건, 지연 0건…」 문장도 같은 판단을 따른다. 즉 이 화면의 목표 상태는 새 디자인이 아니라 **이미 존재하는 표현으로의 수렴**이다.
rationale: 정보 구조·동선·컴포넌트 선택에 구조적 문제가 없다. 위계가 3단계로 읽히고(제목 → 타일 → 상세), 빈 상태 문구가 이 제품에서 가장 잘 쓰인 축에 든다. 그래서 `REDESIGN`이 아니다. 그러나 `KEEP`도 아니다 — 화면이 사용자에게 **사실과 다른 것**을 말하고 있고, 그것이 레이아웃이 아니라 값 표현의 문제라서 정확히 `REFINE`이다.
browser_evidence: `var/product-audit/shots2/d1_user_me.png`(1920×1080 라이트, 전체 페이지) — `Read`로 열어 판정. API 원문 대조는 `var/product-audit/pa2_home_api.py` 실행 결과(`mapped: false` + 버킷 5종 `count: 0` + `sprint: null`). 계측 `pa2_design_user.json`(카드 4 · 버튼 12 · scrollH 1121).
rc_ids: PA-RC-0027
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN table-screens -->
surface: table-screens
layout_family: table
deep_audited: true
skills_applied: ui-ux-pro-max, impeccable, redesign-existing-projects
verdict: REFINE
current_state: `/users` 1920×1080 실측 — 페이지 헤더에 동작 3종(`CSV 내보내기`·`CSV 가져오기`·`+ 사용자 추가`, 마지막만 contained), 필터 카드(검색 + 역할·활성·잠김 3 셀렉트 + 보관 체크박스), 표 8열(이메일·이름·역할·상태·부서·직책·Notion 연결·최근 로그인) 21행, 하단 페이지네이션(`1 / 2, 총 21명`). 세로 1253px. `/audit`은 scrollH 4186, `/jobs`는 4358로 훨씬 길고 둘 다 contained 동작이 0이다.
user_problem: 표 자체의 밀도·정렬·배지 어휘·필터·페이지네이션은 잘 잡혀 있다. 실제 문제는 두 가지다. (1) **이메일 열이 잘린다** — `ui-qa-user@go…`, `donghyunkim@…` 처럼 사용자의 1차 식별자가 읽히지 않는데, 1920px에서 표 오른쪽에 여백이 남아 있다. 폭이 없어서가 아니라 열 폭 배분이 식별자보다 `최근 로그인`·`Notion 연결` 같은 보조 열에 후하다. (2) `/audit`·`/jobs`가 세로 4,200~4,400px로 대시보드의 세 배인데 **contained 동작이 0개**다 — 훑을 것은 많고 할 수 있는 것은 표시되지 않는다.
target_design: 열 폭 배분을 식별자 우선으로 바꾼다 — 이메일이 잘리지 않는 것을 기본으로 하고 보조 열을 줄이거나 접는다(1920px에서 잘림 0). `/audit`·`/jobs`처럼 긴 표는 헤더 동작을 재검토해 그 화면에서 가장 흔한 조치 하나를 primary로 올린다. 표 컴포넌트(`DataScreen`)를 새로 만들지 않는다 — 이 두 가지는 설정(열 정의·동작 정의) 수준에서 끝난다.
rationale: 표 계열은 이 제품에서 가장 성숙한 화면군이다. 27개 REGISTRY 화면이 하나의 `DataScreen` 계약을 공유하고 필터·페이지네이션·빈 상태가 일관된다 — 구조를 다시 그릴 이유가 없어 `REDESIGN`이 아니다. 다만 「식별자가 잘리는데 여백이 남는다」는 표에서 가장 기본적인 실패이고, 4,000px 표에 primary 동작이 없는 것은 동작 위계의 공백이라 `KEEP`도 아니다.
browser_evidence: `var/product-audit/shots2/d1_admin_users.png`(1920×1080 라이트, 전체 페이지) — `Read`로 열어 이메일 잘림과 우측 여백을 확인. `d1_admin_audit.png`·`d1_admin_jobs.png`·`d1_admin_feature-flags.png` 함께 확인. 계측 `pa2_design_admin.json`(`/users` 표 8열 21행 · scrollH 1253 / `/audit` scrollH 4186 contained 0 / `/jobs` scrollH 4358 contained 0).
rc_ids: PA-RC-0029
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN app-shell -->
surface: app-shell
layout_family: shell
deep_audited: true
skills_applied: ui-ux-pro-max, impeccable, redesign-existing-projects
verdict: KEEP
current_state: 1920×1080 실측 — 헤더 높이 64px(브랜드 + 전역 검색 `Ctrl K` + 어시스턴트 + 테마 토글 + 장애 칩 + 알림 벨 + 계정), 사이드바 폭 264px(사용자/관리자 콘솔 전환 + 메뉴 검색 + 그룹 아코디언), 본문은 나머지 폭 전체를 쓰고 좌우 여백이 균일하다. 사이드바 링크 26개가 역할에 따라 달라진다(user 0 / operator 26). 28표면 전부에서 셸이 같은 위치·같은 높이로 유지되고 본문 시작 y가 라우트 간에 흔들리지 않는다.
user_problem: 직전 Cycle이 High로 올렸던 셸 문제(배너가 첫 화면의 31%인 331.5px를 26라우트에서 편차 없이 먹던 것)는 **해소됐다**. 지금 배너는 단일 행(높이 ~56px)이고 닫기가 있으며, 그것도 실제 장애가 있을 때만 뜬다. 남은 것은 사소하다 — 헤더의 장애 칩이 「장애 1, 안내」에서 잘리고, 알림 수가 벨 배지와 사이드바 `알림` 배지에 두 번 나온다. 둘 다 셸의 구조 문제가 아니라 개별 요소의 문구·중복이다.
target_design: 구조 변경 없음. 헤더 높이·사이드바 폭·본문 폭 활용·고정 영역·스크롤 구조를 유지한다. 장애 칩 잘림과 알림 배지 중복은 셸 재설계가 아니라 각 요소의 개선으로 다룬다(별도 RC 후보).
rationale: `KEEP`의 근거는 「문제를 못 찾았다」가 아니라 **직전 Cycle이 이 표면에 대해 세운 구체적 계측 기준을 다시 재서 통과했다**는 것이다. 셸 비용(배너 331.5px → ~56px, 조건부), 본문 폭 활용, 라우트 간 편차 0, 역할별 내비 도달성 — 네 가지가 전부 개선된 상태로 유지된다. 28표면에서 셸이 흔들리는 라우트가 하나도 없었고, 어떤 화면에서도 셸이 본문을 가리지 않았다(직전 Cycle의 FAB 가림도 해소됐다 — 사용자 콘솔 표 화면에서 `상세` 버튼이 덮이지 않는다).
browser_evidence: 28표면 전체 스크린샷(`var/product-audit/shots2/d1_admin_*.png` 16종 + `d1_user_*.png` 12종, 전부 1920×1080 라이트 전체 페이지)에서 헤더·사이드바 박스를 `pa2_design.py`가 라우트마다 계측 — `header`/`sidebar`/`main` 박스와 `mainStartY`·`contentWidthPct`가 라우트 간에 일치. 사이드바 링크 도달성은 `var/product-audit/pa2_rbac.py`가 역할별로 실제 앵커를 세어 확인(operator 26개).
rc_ids: 해당 없음 — 구조 변경이 필요하지 않다. 장애 칩 잘림·알림 배지 중복은 이 표면의 RC가 아니라 `global-header` 판정에서 다룬다(아직 미판정).
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN settings -->
surface: settings
layout_family: settings
deep_audited: true
skills_applied: ui-ux-pro-max, ux-writing, redesign-existing-projects
verdict: REFINE
current_state: `/settings` 는 `PA-RC-0017` 이 `/system`·`/notion-console`·`/llm-console`·`/maintenance` 네 화면을 접어 넣은 탭 그릇이다. `TAB_DEFS` 4종 중 `policy` 만 전역 공개이고 `os`·`integration`·`ai` 는 `system_admin` 전용이다. 실측(1920×1080, admin): 탭 **1개**(`시스템 정책`), 그 아래 설정 표 11행 + `유지보수`(현재 상태·활성화 버튼) + `점검 공지`(textarea + `미리 검증`·`공지 저장`·`버전 기록`), 카드 3장, 세로 1383px. `system_admin` 은 탭 4개를 본다.
user_problem: 통합 자체는 성공했다 — 네 화면을 오가던 것이 한 주소가 됐고 옛 주소도 죽지 않았다. 문제는 **볼 수 없는 탭을 요청했을 때**다. `admin`·`operator` 가 `/system` 으로 들어오면 주소는 `#/settings?tab=os` 가 되는데 화면은 `시스템 정책` 이다 — 주소와 화면이 다른 것을 말하고, 거부 안내는 없다. 12조합(역할 3 × 옛 라우트 4) 전부 실측했다. 같은 콘솔의 라우트 게이트는 같은 상황에서 「권한이 없습니다」를 명시적으로 보여주므로 권한 거부 어휘가 두 벌이다. 그리고 그 두 역할에게는 전환할 것이 없는 탭 바가 하나 남는다.
target_design: 탭 구조와 통합 자체는 그대로 둔다. 셋만 고친다 — (1) 모르는 탭 값은 첫 탭으로 떨어뜨리되 주소를 `replace` 로 정정해 주소와 화면을 맞춘다, (2) 역할 때문에 못 보는 탭은 라우트 게이트와 **같은** `EmptyState`(「권한이 없습니다」 + 설명 + 이동 버튼)로 답한다, (3) 볼 수 있는 탭이 하나뿐이면 탭 스트립을 그리지 않는다. 새 컴포넌트를 만들지 않고 이미 있는 `EmptyState` 를 재사용한다.
rationale: `PA-RC-0017` 의 통합은 되돌릴 이유가 없다 — 화면 넷을 하나로 모은 것이 IA 상 옳고 옛 주소도 살아 있다. 그래서 `REDESIGN` 이 아니다. 그러나 `KEEP` 도 아니다: 이 화면은 대부분의 사용자(23명 중 `system_admin` 2명을 뺀 전원)에게 **주소가 거짓말을 하는 화면**이고, 그것은 이 저장소가 `PA-RC-0024` 에서 스스로 세운 딥링크 계약을 정면으로 어긴다. 고칠 것이 구조가 아니라 거부의 표현과 주소 동기화라서 정확히 `REFINE` 이다.
browser_evidence: `var/product-audit/shots2/d1_admin_settings.png`(1920×1080 라이트, 전체 페이지 1383px) — `Read` 로 열어 탭이 1개인 것과 본문 구성을 확인. 역할별 동작은 `system_admin`·`admin`·`operator` 세 계정으로 옛 라우트 4종을 실제 이동해 주소·활성 탭·탭 수·거부 여부를 12조합 계측(결과는 `PRODUCT_AUDIT_FINDINGS.md` §PA-F-088 표). 소스 근거 `settings/SettingsShell.jsx:51-68`.
rc_ids: PA-RC-0030
<!-- DESIGN-VERDICT-END -->
