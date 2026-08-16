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

필수 18표면 중 **이 Cycle에서 실제로 깊게 판정한 것은 아래 13종**이다. 나머지 5종은
스크린샷과 레이아웃 계측은 확보했지만(`shots2/`, `pa2_design_*.json` — 28표면 실렌더)
UI/UX Skill 기준의 구조·위계 평가를 아직 마치지 않았다. **그 5종에 판정 블록을 쓰지 않는다**
— 계측만 있는 것을 `deep_audited: true` 로 적으면 그것이 조작이다.

| 상태 | 표면 |
|---|---|
| 판정 완료 (13) | `dashboard` · `home` · `admin-console` · `table-screens` · `app-shell` · `settings` · `sidebar` · `navigation-ia` · `global-header` · `detail-screens` · `error-state` · `empty-state` · `loading-state` |
| 계측·스크린샷만 (5) | `list-screens` · `forms` · `modal-drawer` · `ai-assistant-chat` · `key-workflows` |

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
user_problem: 직전 Cycle이 High로 올렸던 셸 문제(배너가 첫 화면의 31%인 331.5px를 26라우트에서 편차 없이 먹던 것)는 **해소됐다**. 지금 배너는 단일 행(높이 약 56px)이고 닫기가 있으며, 그것도 실제 장애가 있을 때만 뜬다. 셸 자체에서 새로 찾은 구조 결함은 **없다**. 헤더에서 실제로 잘리는 요소는 0개이고(전 요소 `scrollWidth == clientWidth` 실측), 유일하게 `clipped`로 잡힌 「읽지 않은 알림 13건」은 폭 1px의 스크린리더 전용 라벨이라 잘림이 아니라 의도된 시각적 숨김이다.
target_design: 구조 변경 없음. 헤더 높이(64px)·사이드바 폭(264px)·본문 폭 활용·고정 영역·스크롤 구조를 그대로 유지한다. 셸이 담는 **내용**의 분류 문제(관리자 메뉴 taxonomy)는 셸이 아니라 `navigation-ia` 표면에서 다루며 `PA-RC-0031`로 내려갔다.
rationale: `KEEP`의 근거는 「문제를 못 찾았다」가 아니라 **직전 Cycle이 이 표면에 대해 세운 구체적 계측 기준을 다시 재서 통과했다**는 것이다. 셸 비용(배너 331.5px → ~56px, 조건부), 본문 폭 활용, 라우트 간 편차 0, 역할별 내비 도달성 — 네 가지가 전부 개선된 상태로 유지된다. 28표면에서 셸이 흔들리는 라우트가 하나도 없었고, 어떤 화면에서도 셸이 본문을 가리지 않았다(직전 Cycle의 FAB 가림도 해소됐다 — 사용자 콘솔 표 화면에서 `상세` 버튼이 덮이지 않는다).
browser_evidence: 28표면 전체 스크린샷(`var/product-audit/shots2/d1_admin_*.png` 16종 + `d1_user_*.png` 12종, 전부 1920×1080 라이트 전체 페이지)에서 헤더·사이드바 박스를 `pa2_design.py`가 라우트마다 계측 — `header`/`sidebar`/`main` 박스와 `mainStartY`·`contentWidthPct`가 라우트 간에 일치. 사이드바 링크 도달성은 `var/product-audit/pa2_rbac.py`가 역할별로 실제 앵커를 세어 확인(operator 26개). 헤더 요소별 잘림은 `var/product-audit/pa2_ia.py`가 `scrollWidth` 대 `clientWidth`로 직접 계측(잘린 요소 0). **이 계측이 내가 스크린샷으로 세웠던 「장애 칩 잘림」 주장을 반증했다** — 상세는 `PRODUCT_AUDIT_FINDINGS.md` §PA-F-089.
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

<!-- DESIGN-VERDICT-BEGIN sidebar -->
surface: sidebar
layout_family: shell
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: KEEP
current_state: 폭 264px 고정. 위에서부터 사용자/관리자 콘솔 전환 토글, `메뉴 찾기` 검색 입력, 그리고 아코디언 그룹 트리. 실측 트리 — 관리자 **5그룹 / 34항목**, 사용자 **5그룹 / 18항목**. 들여쓰기 단계는 12px·20px **두 단계뿐**(그룹 → 항목, 3단 중첩 없음). 역할에 따라 항목이 실제로 줄어든다(user 0 · operator 26 · admin 34). `알림`·`백업` 항목은 숫자 배지를 단다.
user_problem: 컴포넌트 자체에서 측정된 결함이 없다. 깊이가 2단이라 길을 잃을 구조가 아니고, 34항목이 5그룹으로 묶여 그룹당 평균 7개이며, `메뉴 찾기`가 있어 항목이 많아도 도달 비용이 낮다. 역할별 노출이 서버 권한과 정확히 일치한다는 것은 F축에서 63조합으로 따로 확인했다(나브·화면·API 불일치 0). 사이드바가 담는 **내용의 분류**에는 문제가 있지만 그것은 이 컴포넌트가 아니라 `navigation-ia`의 문제이므로 그쪽에서 판정했다.
target_design: 구조 변경 없음. 폭 264px, 2단 깊이, 아코디언, 콘솔 전환, `메뉴 찾기`, 역할 필터링, 배지를 그대로 유지한다. 이 컴포넌트에 손댈 이유가 측정으로 나오지 않았다.
rationale: `KEEP`의 근거는 「문제를 못 찾았다」가 아니라 **이 표면에 대해 구체적 기준을 세우고 재서 통과했다**는 것이다 — 깊이 2단(3단 이상이면 탐색 비용이 급증한다), 그룹당 항목 7개 평균(밀러 한계 안), 검색 존재, 역할 노출과 서버 권한 일치(63조합 실측), 28라우트에서 폭·위치 편차 0. 직전 Cycle이 High로 올렸던 「8그룹 평면이 분류를 사용자에게 떠넘긴다」는 지금 5그룹으로 정리돼 재현되지 않는다.
browser_evidence: `var/product-audit/pa2_ia.py`가 아코디언을 전부 펼친 뒤 DOM에서 트리를 그대로 덤프(`pa2_ia.json`) — 관리자 5그룹/34항목·사용자 5그룹/18항목, 들여쓰기 12·20px 두 단계. 폭·위치 편차는 `pa2_design.py`가 28라우트에서 계측. 역할별 도달성은 `pa2_rbac.py`(21라우트 × 3역할). 화면은 `shots2/d1_admin_dashboard.png`·`d1_user_me.png` 등 28종.
rc_ids: 해당 없음 — 이 컴포넌트에는 구현이 필요한 결함이 측정되지 않았다. 사이드바가 담는 분류 문제는 `navigation-ia`의 `PA-RC-0031`이 가져갔다.
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN navigation-ia -->
surface: navigation-ia
layout_family: shell
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: REDESIGN
current_state: 관리자 5그룹 34항목 — `운영`(7) `사용자와 권한`(7) `자동화`(7) `연동`(7) `감사`(6). 사용자 5그룹 18항목 — `내 업무`(5) `도우미`(2) `문서`(2) `팀 공간`(6) `내 정보`(3). 전부 실측 덤프(`pa2_ia.json`).
user_problem: 그룹 이름이 그 안의 내용을 설명하지 못하는 자리가 여러 곳이다. (1) **`감사` 그룹 6개 중 3개가 감사가 아니다** — `기능 플래그`(설정) `공지 배너`(콘텐츠) `복구 리허설`(운영). (2) **같은 명사가 두 그룹으로 쪼개진다** — `정책`은 `연동`에, `정책 사용 통계`는 `감사`에 있다. (3) **같은 종류의 화면이 다른 그룹에 있다** — `프롬프트 사용 통계`(연동)와 `정책 사용 통계`(감사)는 구조가 같은 사용 통계 화면인데 그룹이 다르다. (4) **같은 업무가 갈라진다** — `백업`은 `운영`, 그 백업이 실제로 복구되는지 확인하는 `복구 리허설`은 `감사`에 있다. 백업을 점검하러 온 관리자는 두 그룹을 오간다. (5) 업무용어 뒤에 기술용어를 괄호로 다는 좋은 관례(`실행 일정(스케줄)`·`자동화 작업 실행기(러너)`·`업무 자동화 흐름(워크플로)`)가 **34항목 중 3개에만** 적용돼 있어, 나머지(`프롬프트`·`정책`·`템플릿`·`기능 플래그`)는 내부 구현 용어 그대로다. (6) 사용자 콘솔의 `문서` 그룹은 `문서`와 `휴지통` 둘뿐인데, 휴지통은 문서 화면 안의 상태이지 형제 메뉴가 아니다.
target_design: 그룹을 **업무 기준**으로 다시 긋는다. `감사`는 감사만 남긴다(`감사 로그`·`감사 이상 징후`·`정책 사용 통계`·`프롬프트 사용 통계` — 사용 통계 둘을 여기 모으면 (2)(3)이 동시에 풀린다). `기능 플래그`는 `운영`의 설정 계열로, `공지 배너`는 콘텐츠를 다루는 `자동화`(문서 자동 생성과 같은 성격)로, `복구 리허설`은 `백업` 바로 옆 `운영`으로 옮긴다. 용어 관례를 통일한다 — 업무용어를 앞에 두고 기술용어를 괄호에 넣는 형식을 이미 3개가 쓰고 있으므로 나머지에도 같은 규칙을 적용하거나(예: `문구 틀(프롬프트)`), 반대로 3개에서 괄호를 빼서 한 벌로 만든다. 어느 쪽이든 **34항목이 한 규칙을 따라야 한다.** 사용자 콘솔의 `휴지통`은 메뉴에서 빼고 `문서` 화면 안의 뷰로 넣는다 — 그러면 `문서` 그룹이 항목 하나가 되므로 그룹 자체를 없애고 `팀 공간`으로 합친다. RBAC 경계·라우트·데이터 의미는 하나도 바꾸지 않는다(옛 주소는 살려 둔다).
rationale: 개별 화면은 각각 잘 만들어져 있는데 **찾는 비용**이 화면 품질과 무관하게 발생한다. 「백업이 실제로 복구되는지」를 확인하려면 `운영`과 `감사`를 오가야 하고, 「사용 통계」를 보려면 두 그룹을 다 열어야 한다. 이것은 항목 하나를 고쳐서 되는 일이 아니라 분류 체계를 다시 긋는 일이라 `REFINE`이 아니라 `REDESIGN`이다. 반대로 사이드바 컴포넌트 자체(깊이·폭·검색·역할 필터)는 건드릴 이유가 없어 그쪽은 `KEEP`으로 갈랐다 — **그릇은 좋고 분류가 틀렸다.**
browser_evidence: `var/product-audit/pa2_ia.py`가 아코디언을 전부 펼친 뒤 두 콘솔의 메뉴 트리를 DOM에서 그대로 덤프했다(`pa2_ia.json`) — 그룹명·항목명·href·들여쓰기까지 실측. 위 (1)~(6)은 전부 그 덤프에서 직접 읽은 것이고 추정이 아니다. 화면은 `shots2/d1_admin_dashboard.png`(관리자 사이드바 펼침)·`d1_user_me.png`(사용자 사이드바).
rc_ids: PA-RC-0031
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN global-header -->
surface: global-header
layout_family: shell
deep_audited: true
skills_applied: ui-ux-pro-max, impeccable, ux-writing
verdict: KEEP
current_state: 높이 64px 고정. 좌→우로 브랜드(264px, 사이드바 폭과 정렬), 전역 검색(약 615~625px, `Ctrl K` 단축키 표시), 어시스턴트 진입(`클로비`), 다크 모드 토글, 장애 칩(`장애 1` + 개수 배지), 알림 벨(배지), 계정. 두 콘솔에서 같은 구성이고 28라우트에서 위치·높이 편차가 없다.
user_problem: 측정된 결함이 없다. 요소별 `scrollWidth` 대 `clientWidth` 실측에서 **잘린 요소 0개**다. 전역 검색이 헤더 폭의 약 1/3을 차지해 이 제품에서 가장 큰 헤더 요소인데, 검색이 실제 진입 수단(`Ctrl K` 커맨드 팔레트)이라는 점에서 그 비중이 정당하다. 알림 개수가 헤더 벨과 사이드바 `알림` 항목에 **동시에 같은 값**으로 뜨는 것은 실측으로 확인했지만(같은 순간 둘 다 `15`), 전역 알림 표시와 목적지 메뉴가 같은 수를 보이는 것은 널리 쓰이는 의도된 패턴이고 이 제품이 그것을 결함으로 본다는 근거가 문서·테스트·주석 어디에도 없다 — 근거 없이 결함으로 부르지 않는다.
target_design: 구조 변경 없음. 높이 64px, 요소 구성과 순서, 검색의 비중, 배지 표시를 유지한다.
rationale: `KEEP`의 근거는 기준을 세우고 실측으로 통과한 것이다 — 잘림 0(요소별 scrollWidth 계측), 라우트 28곳에서 높이·위치 편차 0, 두 콘솔 구성 동일, 브랜드 폭이 사이드바 폭(264px)과 정확히 정렬. 처음에 스크린샷을 보고 「장애 칩이 잘린다」고 판단했으나 **계측이 그것을 반증했다**(`장애 1`: width 45 = scrollWidth 45). 그 오판과 정정을 `PA-F-089`에 남겼다.
browser_evidence: `var/product-audit/pa2_ia.py`의 헤더 계측 — 요소별 좌표·폭·`scrollWidth`/`clientWidth` 비교(잘린 요소 0, 유일한 `clipped`는 폭 1px 스크린리더 라벨). 배지 동시 계측은 `var/product-audit/pa2_badges.py`(같은 순간 사이드바 `알림 15` · 헤더 벨 `15`). 화면은 `shots2/d1_admin_dashboard.png`·`d1_user_me.png` 등 28종(1920×1080 라이트).
rc_ids: 해당 없음 — 실측에서 구현이 필요한 결함이 나오지 않았다. 이 표면에 대한 나의 첫 주장(칩 잘림)은 계측으로 반증돼 철회했다.
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN detail-screens -->
surface: detail-screens
layout_family: detail
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, ux-writing
verdict: REFINE
current_state: 상세는 두 가지 표현으로 나뉜다 - 사용자 콘솔은 **라우트**(`/projects/:id`·`/tickets/:id`·`/board/:id`·`/team-docs/:id`·`/chat-rooms/:id`·`/games/:id`), 관리자 콘솔은 **목록 위 모달**(`/users/:id`·`/departments/:id`·`/audit/:id`, 목록과 같은 element 를 가리켜 인스턴스가 유지된다). 존재하지 않는 id 로 9개 전부에 진입해 보면 주소는 전부 유지되는데 화면은 셋으로 갈린다 - 침묵 3(관리자) · 정확히 안내 5 · 30초 걸려 안내 1(`/board/:id`).
user_problem: 관리자 상세 3종은 없는 레코드를 요청해도 목록만 그린다. 주소는 계속 그 레코드를 가리키므로 사용자는 삭제된 것인지 잘못 온 것인지 못 보는 것인지 알 수 없고 결국 목록에서 손으로 다시 찾는다. 감사 로그가 특히 나쁘다 - 항목 링크는 사건을 특정해 공유하는 용도인데 그 항목이 없으면 8,138자짜리 전체 목록이 뜬다. `/board/:id` 는 답을 알면서도 404 를 네 번 재시도하느라 20초를 넘긴다.
target_design: 상세 표현이 콘솔별로 다른 것 자체는 유지한다 - 관리자 목록-모달은 `PA-RC-0024` 가 「목록의 스크롤·필터·데이터를 잃지 않는다」는 실측 근거로 택한 구조이고 실제로 성립한다. 바꾸는 것은 **없을 때의 경로**뿐이다. 세 관리자 라우트가 상세 자리(모달·오른쪽 패널)에 기존 `ErrorState`(`status: 404`)를 그려 사용자 콘솔 5종과 같은 문구를 말하게 한다. `/board/:id` 는 전역 재시도 정책을 고쳐 즉시 답하게 한다. 새 컴포넌트·새 문구를 만들지 않는다.
rationale: 구조를 다시 그릴 이유가 없다 - 두 표현이 각각 그 콘솔의 사용 방식에 맞고, 5개 라우트는 이미 정답을 보여주고 있다. 그래서 `REDESIGN` 이 아니다. 그러나 9개 중 4개가 없는 레코드에 대해 사용자에게 아무 말도 못 하거나 30초 걸려 말하므로 `KEEP` 도 아니다. 고칠 것이 레이아웃이 아니라 **누락된 상태 경로**라서 정확히 `REFINE` 이다.
browser_evidence: `var/product-audit/pa2_badid.py` 가 존재할 수 없는 UUID 로 9개 상세 라우트에 실제 진입해 본문 텍스트·모달 유무·주소 유지를 계측(`pa2_badid.json`). `/board/:id` 는 네트워크를 함께 기록해 같은 404 가 4회 호출되는 것을 확인했고, 20초·30초 두 시점에서 화면 상태를 따로 관측했다. 화면은 `shots2/d2_error_baduser.png`·`d2_error_404route.png`.
rc_ids: PA-RC-0033, PA-RC-0034
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN error-state -->
surface: error-state
layout_family: state
deep_audited: true
skills_applied: ux-writing, ui-ux-pro-max, impeccable
verdict: REFINE
current_state: 공용 `ErrorState`(`frontend/src/ui/kit.jsx`)가 「찾을 수 없습니다 / 요청한 항목을 찾을 수 없습니다. 이미 삭제되었거나 이동했을 수 있습니다. / 홈으로」를 그린다 - 제목·설명·회복 동작 3요소에 삽화까지 갖췄다. 알 수 없는 관리자 라우트(`RouteNotFound`), 사용자 콘솔 상세 5종이 전부 이것을 쓴다. 권한 거부는 별도로 `EmptyState`(`art="noPermission"`, 「권한이 없습니다」 + 설명 + 「대시보드로 이동」)를 쓴다. 세션 만료(401)는 권한 없음과 구분해 재로그인 링크가 있는 `ErrorState` 로 따로 처리한다(`AdminRoutes.jsx`).
user_problem: 컴포넌트와 문구는 좋다. 문제는 **그것이 필요한 자리에 항상 놓이지는 않는다**는 것이다. 관리자 상세 3종은 404 를 받고도 이 컴포넌트를 그리지 않고 목록을 보여주며(`PA-RC-0033`), `/settings` 의 탭 게이트는 권한 거부에 이 어휘를 쓰지 않고 조용히 다른 탭을 보여준다(`PA-RC-0030`). 즉 제품에 좋은 오류 표현이 **있는데도** 같은 상황에서 어떤 화면은 쓰고 어떤 화면은 안 쓴다.
target_design: 컴포넌트 자체는 그대로 둔다 - 문구·삽화·버튼 구성을 바꾸지 않는다. 대신 **적용 범위를 채운다**: 관리자 상세 3종의 404 경로(`PA-RC-0033`)와 `/settings` 탭 권한 거부(`PA-RC-0030`)가 이 공용 표현을 쓰게 한다. 그리고 오류가 확정된 뒤 즉시 표시되도록 재시도 정책을 고친다(`PA-RC-0034`) - 30초 뒤에 나오는 좋은 오류 화면은 좋은 오류 화면이 아니다.
rationale: 문구 품질은 이 제품의 강점이다(3요소 + 회복 동작 + 401/403 구분). 그래서 표현을 다시 설계할 이유가 없어 `REDESIGN` 이 아니다. 그러나 같은 상황에서 이 표현을 쓰는 화면과 안 쓰는 화면이 갈리고 그 격차가 실측으로 4건 확인됐으므로 `KEEP` 도 아니다 - 이 표면의 결함은 컴포넌트가 아니라 **적용 일관성**이다.
browser_evidence: `var/product-audit/pa2_states.py` 가 없는 사용자 id·알 수 없는 라우트로 실제 진입해 본문·버튼·삽화 수를 계측(`d2_error_404route.png`: 「찾을 수 없습니다」 + 「홈으로」 버튼, 삽화 2). `pa2_badid.py` 가 9개 상세 라우트에서 이 표현이 나오는 5곳과 안 나오는 3곳을 갈라 확인. `/settings` 탭 거부는 역할 3종 × 라우트 4종 12조합 실측.
rc_ids: PA-RC-0030, PA-RC-0033, PA-RC-0034
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN empty-state -->
surface: empty-state
layout_family: state
deep_audited: true
skills_applied: ux-writing, ui-ux-pro-max, impeccable
verdict: KEEP
current_state: 필터로 결과가 0건이 되는 경우 - `/users?q=<없는 값>` 은 「조건에 해당하는 사용자가 없습니다 / 검색어나 필터를 지우고 다시 확인하세요」 + **「필터 지우기」 버튼**을 그리고, 그 버튼이 필터 카드와 빈 상태 양쪽에 놓인다(삽화 포함, 본문 237자). 데이터 자체가 없는 경우 - `/me` 의 미매핑 상태는 「내 계정이 Notion 사용자와 연결되어 있지 않습니다」 + 번호 매긴 조치 2단계 + 「기대 결과: 연결되면 내 담당 티켓이 이 자리에 표시됩니다」를 그린다.
user_problem: 실측에서 이 표면의 결함이 나오지 않았다. 「결과 없음」(필터를 지우면 해결)과 「데이터 없음」(설정이 필요)을 **다른 문구와 다른 회복 동작**으로 구분하고 있고, 둘 다 사용자가 다음에 무엇을 할지 알 수 있다. `/me` 의 빈 상태는 원인·조치·기대 결과 3요소를 갖춰 이 제품에서 가장 잘 쓰인 문구에 속한다. 다만 그 화면의 **숫자 타일**이 같은 상황을 `0` 으로 말하는 것은 별개 결함이며 `PA-RC-0027` 이 가져갔다 - 빈 상태 문구 자체는 옳다.
target_design: 변경 없음. 두 종류의 빈 상태를 구분하는 현재 방식, 회복 동작 버튼의 위치, 삽화, 3요소 문구 구성을 유지한다.
rationale: `KEEP` 의 근거는 기준을 세우고 실측으로 통과한 것이다 - (1) 「결과 없음」과 「데이터 없음」이 구분되는가: 그렇다, (2) 회복 동작이 있는가: 그렇다(「필터 지우기」가 실제 동작하는 버튼으로 두 곳에), (3) 원인을 말하는가: 그렇다, (4) 기대 결과를 말하는가: `/me` 는 명시한다. `ux-writing` 의 빈 상태 기준(무엇이 없는지·왜 없는지·무엇을 하면 되는지)을 네 항목 다 만족한다.
browser_evidence: `var/product-audit/pa2_states.py` 가 `/users?q=zzzz-no-such-user-zzzz` 로 실제 필터 빈 상태를 만들어 본문·버튼·삽화를 계측(`shots2/d2_empty_users.png`, 버튼에 「필터 지우기」 2회 등장, 삽화 8). `/me` 미매핑 빈 상태는 `shots2/d1_user_me.png` 를 `Read` 로 열어 3요소를 확인.
rc_ids: 해당 없음 - 이 표면에서 구현이 필요한 결함이 측정되지 않았다. `/me` 의 숫자 타일 문제는 빈 상태가 아니라 값 표현의 결함이라 `PA-RC-0027` 이 가져갔다.
<!-- DESIGN-VERDICT-END -->

<!-- DESIGN-VERDICT-BEGIN loading-state -->
surface: loading-state
layout_family: state
deep_audited: true
skills_applied: ui-ux-pro-max, impeccable, ux-writing
verdict: REFINE
current_state: 네트워크를 2.2초 지연·12KB/s 로 조인 상태에서 `/audit` 을 열면 「불러오는 중…」 텍스트와 스켈레톤/스피너 **5개**가 뜨고, 화면 골격(제목·필터·동작 버튼)은 먼저 그려져 있다. 라우트 전환에는 `AdminRoutes.jsx` 의 `React.Suspense` 가 카드형 스켈레톤을 보인다. `registry` 로딩 중에는 catch-all 이 대시보드로 튕기지 않고 로딩을 유지한다(주소 깜빡임 방지).
user_problem: 로딩 표현 자체는 옳다 - 골격을 먼저 그리고 데이터 자리만 스켈레톤으로 채우는 방식이라 레이아웃이 튀지 않는다. 문제는 **로딩이 끝나야 할 때 끝나지 않는 경우**다. `/board/<없는 id>` 는 서버가 즉시 404 를 답했는데도 같은 요청을 네 번 재시도하느라 20초 시점에 여전히 「불러오는 중…」이었다. 그 사이 화면은 정상 로딩과 구분되지 않아 사용자는 기다릴지 새로고침할지 판단할 수 없다.
target_design: 로딩 표현(스켈레톤·「불러오는 중…」·골격 우선 렌더)은 그대로 둔다. 바꾸는 것은 **로딩이 끝나는 조건**이다 - 확정적인 4xx 를 재시도하지 않게 해 오류가 확정되는 즉시 로딩을 끝내고 오류 상태로 넘긴다(`PA-RC-0034`). 목표는 「없는 게시글」 판정이 3초 안에 끝나는 것이다.
rationale: 스켈레톤·골격 우선 렌더·라우트 전환 로딩은 이미 잘 만들어져 있어 다시 설계할 이유가 없다. 그래서 `REDESIGN` 이 아니다. 그러나 이 표면의 목적은 「기다리는 동안 무슨 일이 일어나는지 알려 주는 것」인데, 답이 이미 나온 뒤에도 20초를 더 기다리게 하는 경로가 실측으로 존재하므로 `KEEP` 도 아니다. 고칠 것이 로딩의 **모양**이 아니라 **지속 시간**이라 `REFINE` 이다.
browser_evidence: `var/product-audit/pa2_states.py` 가 CDP `Network.emulateNetworkConditions`(지연 2,200ms · 12KB/s)로 실제 느린 네트워크를 만들어 `/audit` 로딩을 관측 - 스피너/스켈레톤 5개 + 「불러오는 중…」(`shots2/d2_loading_audit.png`). `/board/<ghost>` 는 20초·30초 두 시점에서 본문을 따로 읽어 20초에는 로딩, 30초에는 「찾을 수 없습니다」임을 확인하고 네트워크에서 404 4회를 기록.
rc_ids: PA-RC-0034
<!-- DESIGN-VERDICT-END -->
