# 근본 원인 분석 — 미판독 화면 40개 / 발견 73건

전체 73건 중 **66건이 7개 원인으로 묶인다.** 화면별 결함이 아니라 **7개의 규칙 부재**이고, 그중 3개(R1·R3·R5)는 "이미 만들어 둔 규칙을 배선하지 않은 것"이라 비용이 거의 없다.

---

## 1. 근본 원인 묶음

### R1. 이미 만든 공용 규칙이 **옵트인**이라, 등록을 잊은 한 곳에서 조용히 실패한다 (12건)

이 저장소는 필요한 토큰·헬퍼·등록표를 **이미 갖고 있다.** 문제는 전부 "쓰기로 선택해야 적용되는" 구조라, 새 화면이 하나 늘 때마다 재발한다. 실패가 조용해서 리뷰에서 안 걸린다.

| 화면 | 존재하는 능력 | 안 쓴 곳 |
|---|---|---|
| admin_announcements, admin_impersonation, user_team-docs-trash | `KO_WORD_BREAK` (theme.js:386-398, 주석에 "사용자 지적 #11") | `EmptyState`(kit.jsx:295-311), `Trash.jsx:140-142` |
| admin_departments, admin_org-tree | `ROUTE_OWNER` + `activeNavPath` (navConfig.js:240-265) | 두 경로만 미등록 |
| admin_notion-mapping | `primary:true` 헤더 액션 | DataScreen.jsx:486-489가 `showCreate`만 primary로 렌더 |
| admin_policies | `Callout tone="warn"` (같은 파일 531·540에서 사용 중) | DataScreen.jsx:524가 `config.help`를 무조건 info로 |
| admin_templates | `activeCol`(warn 톤, columnHelpers.jsx:11-15) / `searchPlaceholder` | `badgeCol`로 대체됨 / 미지정 → 기본값 "검색" |
| user_profile | `shortUA` + Tooltip (Users.jsx:42, :633) | Profile.jsx:383-386이 UA 원문 그대로 |
| admin_job-detail, admin_integration-detail | `rowName: true` (rowName.js:14-16) | `detailTitle`이 무조건 columns[0] (detailFields.js:18-29) |
| admin_backup | 수치 열 `align:"right"` (governance.js:341, authoring.js:341-345) | platform.js:67 크기 열에 없음 |

**대표 근거** — `frontend/src/ui/ko-wordbreak.test.jsx:25-37`은 **Callout에 도달하는지만** 검증한다. 정작 31개 파일이 쓰는 `EmptyState`에는 토큰이 안 걸려 있어, 같은 증상이 세 화면에서 재발했다.

**고칠 규칙:** 산문·라벨·상태 표현의 공용 규칙을 **옵트인 → 기본값**으로 뒤집고, 테스트를 "특정 컴포넌트"가 아니라 "사용자 산문을 그리는 모든 컴포넌트" 단위로 건다. 등록표(ROUTE_OWNER)는 라우트 정의에서 파생하거나 미등록을 CI에서 실패시킨다.

---

### R2. 개발자 문자열과 사용자 문구의 **경계가 없고, 검사망은 코드만 본다** (8건)

`scripts/check_user_text.py`가 소스만 스캔하므로, **DB·시드에 한 번 들어간 문자열은 영구히 검사를 빠져나간다.**

- **admin_job-detail** — 목록 '오류' 열: `등록되지 않은 job_type: notion_mapping_sync`, `requester가 없는 payload — 위조 또는 손상`. 소스(`app/jobs/handlers/chat_message.py:147`)는 콜론인데 화면은 **금지 글리프 em 대시** — DB에 남은 옛 문자열이다.
- **admin_integration-detail** — 설명: `Claude Request Interpreter (기존 서비스 — 존재 여부 사전조사로 확인)` (내부 메모 + em 대시, DB 값)
- **admin_integration-detail** — 모달 제목이 사람 이름이 아니라 슬러그 `claude-request-interpreter` (시드 데이터)
- **admin_feature-flags** — 설명 열이 백엔드 레지스트리 원문: `유지보수 모드. 정본은 app_settings 테이블`, `자유게시판 모듈(§23).` **게다가 `app/admin/feature_flags.py:100`이 이 문자열을 기계 파싱한다("(소비자 없음)" 마커)** — 문구만 고치면 계약이 깨진다.
- **admin_documents** — 빈 상태에 `409`와 `#/settings`가 리터럴로. 같은 블록 아래 `emptyRelatedLink`(실제 링크)가 이미 있다.
- **admin_approval-delegations / admin_impersonation** — 사람을 고르는 화면인데 입력이 UUID다. 조회는 이름(`이름으로 검색`), 입력은 ID(`'사용자' 화면에서 ID를 복사하세요`)로 축이 갈린다. 프런트 전체에 사용자 선택 위젯이 없다(Autocomplete 0 hits). 같은 패턴이 ai-quotas `user_id`, template `prompt_id/policy_id/target_ref`에도 있어 **공용 피커 하나로 4화면이 함께 고쳐진다.**
- **admin_job-detail** — 멱등키 `chatmsg:058b36b7-…` / 메시지 ID `058b36b7-…` 를 두 줄로 반복
- **admin_backup** — em 대시 금지 규칙을 쉼표로 기계 치환한 흔적: `이 목록은 웹 콘솔 DB 스냅샷입니다, 웹에서 복원할 수 없으며…` (같은 패턴이 platform.js:46, integrations.js:161, DataScreen.jsx:540)

**고칠 규칙 3개:** ① 사용자에게 보일 문자열은 개발자 문자열과 **다른 필드**에서 온다(feature flag는 `admin_description` 신설). ② `check_user_text.py`를 **API 응답 페이로드와 시드/마이그레이션 값까지** 스캔. ③ em 대시 치환은 자동이 아니라 **문장 재작성**(규칙 원문이 이미 "자연스러운 문장으로 수정"이다).

---

### R3. 같은 값을 화면마다 다르게 부르고, 같은 라벨이 다른 값을 가리킨다 (10건)

용어 사전이 없어서 **같은 사실이 화면마다 다른 단어·다른 색·다른 형식**으로 나온다.

| 개념 | 화면별 표현 |
|---|---|
| 사용 여부 | 조직 = 평문 `사용`/`정지` · 부서·직책 = 녹색 칩 `사용 중`/`미사용` · 오프보딩 = 칩 `사용 중`/`비활성화` |
| maintenance_mode=off | 유지보수 화면 = 초록 채움 `정상` · 기능 플래그 = 회색 아웃라인 `꺼짐` |
| 헬스체크 | `헬스체크`(연동 모달) / `헬스`+`테스트`(러너 모달) / `상태 확인`(필드) / `헬스 체크`(안내문) — **전부 같은 엔드포인트 계열** |
| maintenance_state | 필터 라벨 `점검 상태` vs 열 헤더 `상태` (integrations.js:134 vs :137) |
| 승인 | 이 콘솔에서 `결재`는 **approval-delegations 화면에만** 등장(governance.js:159·162·164·165·192). 나머지는 예외 없이 `승인/거절/승인 큐` |
| 날짜/시각 | user_activity 그룹 헤더만 ISO `2026-08-08` · 나머지 `2026. 8. 8. 오후 5:43` |

**반대 방향 사례(더 나쁨)** — 같은 라벨이 다른 값:
- **admin_organizations** — 트리 "부서 1개"(직속 최상위, `tree.py:173`) vs 같은 화면 표 "부서 2"(전체, `router.py:254`). **한 화면 안에서 모순이 보인다.**
- **admin_backup** — 같은 행에 `생성 2026. 7. 19. 오전 1:37`(KST)와 `web-20260718_163727_…`(UTC). 둘 다 맞는데 두 날짜로 보인다.
- **admin_runner-detail** — `활성 예` / `상태 정상` / `상태 확인 정상`이 연속 3행. 실제 필드는 `enabled`/`maintenance_state`/`last_health_status`로 전부 다른데 설명이 없다.
- **admin_job-detail** — 실행 예정·시작·종료가 전부 `오후 3:22`(전역 포매터 `timeStyle:"short"`)인데 소요 시간은 `12.6초`.

**고칠 규칙:** 도메인 용어 사전(값 → 라벨·톤·형식) 하나를 정본으로 두고, 같은 필드에 두 라벨이 붙으면 CI에서 실패시킨다. **`OrgTree.jsx:94-96`이 이미 이 원칙을 문장으로 적어 뒀다** — 문서화만 되고 강제되지 않았다.

---

### R4. 화면이 **약속한 것**과 실제로 **할 수 있는 것**이 어긋난다 (9건)

사용자가 화면 문구를 믿지 못하게 만드는 부류. 신뢰 손상이 가장 크고, 대부분 문구 삭제로 해결된다.

- **admin_ai-quotas** — 배너: "상한이 걸리는 곳은 아래 표 위의 '상한이 걸리는 곳' 목록으로 서버가 직접 알려 줍니다." → **그런 목록을 그리는 코드가 저장소에 없다**(전수 grep에서 help 문자열과 빌드 산출물뿐). 0건이라 안 보이는 게 아니라 어떤 상태에서도 렌더되지 않는다.
- **user_search** — 상단바 `티켓, 문서, 채팅, 사용자, 메뉴 검색` → `app/search/service.py:52` 주석: "채팅은 애초에 SEARCH_KINDS에 없다". **존재하지 않는 검색 범위를 광고 중.**
- **admin_offboarding** — H1 `온보딩, 오프보딩`, 내비 `온보딩과 오프보딩` → `Offboarding.jsx` 503줄 전체에 온보딩 경로가 0건.
- **user_my-stats** (High) — 배너: "Notion 사용자와 연결되어 있지 않아 담당 티켓을 찾을 수 없습니다" / 같은 화면 빈 상태: "내가 담당인 티켓이 하나도 없어서" + CTA `내 티켓으로`. **원인 진단이 서로를 모르고, CTA가 가리키는 화면도 같은 이유로 비어 있다**(MyStats.jsx:148-156이 `source.mapped`와 무관하게 항상 같은 문구).
- **admin_integration-detail** (High) — `상태 확인 정상`(초록) / `마지막 점검 2026. 7. 14.` = **25일 전 결과를 현재 상태로 표시.** 주기 헬스 스윕이 worker에 없고 staleness 표시도 없다(저장소는 `HEARTBEAT_STALE_SECONDS`를 이미 쓴다).
- **user_search-results** — 안내는 `티켓, 문서, 게시판, 사용자` 4종인데 결과는 2종. `service.py:178-180`이 0건 그룹을 조용히 `continue`하고, `KIND_ROLE_GATE`는 '사용자'를 일반 사용자에게 애초에 안 준다 — **화면에 그 사실이 없다.**
- **user_search-results** — "26건 중 20건을 보여 줍니다" ← 잘렸다고 알리면서 **더보기·페이지·정렬이 없다**(서버는 50까지 낼 수 있는데 프런트가 `limit:20` 고정, offset 개념 없음).
- **user_ideas** — 빈 상태 "위 '제안하기'로 …" ← 그 안내 **바로 아래**에 동일 라벨·동일 스타일의 같은 버튼 인스턴스를 다시 놓는다(Board.jsx:429 정의를 :529가 재사용).
- **user_unassigned** — `대분류` 필터는 자유 입력인데 placeholder·후보가 없고 서버는 **완전일치**로 거른다(`query.py:83-84`). `/api/tickets/meta`가 categories를 안 줘서 후보 제시도 불가.

**고칠 규칙:** 문구가 참조하는 대상(UI 영역·기능·검색 범위·시각)이 **존재하고 최신인지** 보장한다. 없으면 문구를 지운다. "일부만 보여준다"고 말하는 화면은 반드시 나머지에 도달할 수단을 함께 제공한다.

---

### R5. 0건·미설정·부분결과 상태 규칙이 없다 (8건)

`help`와 `emptyHelp`가 **같은 사실을 각각 하드코딩**하고, 툴바는 결과가 비었는지 보지 않는다.

- 중복 서술: **admin_documents** 배너 "…'+ 문서 생성'으로 워크플로와 기간을 지정하면…" ↔ 빈 상태 "'+ 문서 생성'으로 워크플로와 기간을 지정하면…" (거의 어절 단위 동일, automation.js:198 vs 202). 같은 쌍이 **admin_ai-quotas**(platform.js:215 vs 216), **admin_approval-delegations**(governance.js:159 vs 165), **user_team-docs-trash**(Trash.jsx:141 vs 152)에도 있다 — 총 4화면.
- 0건인데 툴바 상시: **admin_impersonation**(필터 3개 + 저장된 뷰가 온보딩 빈 상태 위를 차지), **user_ideas**(0건인데 칩 11개 + 검색 + 정렬, y≈228~388). `DataScreen.jsx:468 showToolbar = showSearch || filters.length > 0` — **같은 컴포넌트가 :651-657에서 이미 "필터 때문에 0건"과 "애초에 0건"을 구분하고 있는데** 툴바는 그 판단을 안 본다.
- 빈 상태에 다음 행동 없음: **user_team-docs-trash**(action 0개), **user_profile**(`부서 -`, `직책 -`, `Notion 연결 [미연결]`에 CTA 없음 — 같은 상태를 MyStats.jsx:88-95는 "관리자에게 계정 연결을 요청하세요"로 안내), **user_search** 진입 화면(안내 3줄 + 마스코트, 클릭 가능 요소 0개, 저장소에 '최근 검색' 개념 자체가 없음).
- 조용한 잘림: **admin_offboarding** — `api("/api/admin/users?page_size=20")` 하드 상한, 총건수·페이저·상태 필터 없음. **사용자가 21명이 되는 순간 21번째는 이름을 정확히 쳐야만 닿는다.** 같은 모집단의 notion-mapping은 `1/1, 총 18건` + 페이저 + 필터 4개를 준다. DataScreen에는 `capWarning`이 있는데 이 화면은 그 계약 밖이다.

**고칠 규칙:** 상태 매트릭스 하나 — {0건·필터로 0건·부분/잘림·미설정} × {무엇을 말할까·어떤 액션을 줄까·툴바를 그릴까}. `help`↔`emptyHelp`는 한 문장을 공유하거나 역할을 나눈다(배너=상시 규칙, 빈 상태=첫 행동).

---

### R6. 넓은 뷰포트의 **폭 예산**이 없고, 넓어진 자리가 정보를 안 나른다 (13건)

1920에서 면적은 늘었는데 그 면적에 들어갈 정보는 안 늘었다.

**폭 낭비 (실측)**
- admin_approvals — 필터 카드 1590px, 내부 컨트롤은 `상태` 드롭다운 254px **하나**
- admin_prompt-usage — 이름 `주간 업무 리포트 생성`(x334~440) → 다음 잉크 x686, **246px 공백** (3행 전부)
- admin_audit-anomalies — 요약 끝 x1101 → 건수 x1424(**323px**), 마지막 x1575 → 상세 버튼 x1787(**207px**)
- admin_runner-detail — 값 열이 x655에서 시작해 가장 긴 UUID도 x925에서 끝, 모달은 x462~1457 → **오른쪽 절반이 통째로 빈다.** 같은 모달이 세로로 뷰포트 94%를 쓰면서 `회로 차단 해제`·`생성`·`수정`·`설명` **4필드를 화면 밖으로 밀어낸다**(24필드 중 20개만 보임) — 원인과 해법이 한 쌍이다.
- user_search-results — 좌측 `티켓 3`은 y555에서 끝, 우측 `문서 26`은 y1580까지 → **1025px 빈 배경.** (`Search.jsx:52-62`가 바로 이 증상 때문에 grid 대신 columnCount를 택했는데 그룹 2개·극단 편중 조합에서 재발)
- user_my-stats — 지표 6개가 4+2로 갈려 둘째 줄 우측 800px 공백(xl=4열, 지표 6개 → 구조적으로 항상 4+2)
- user_activity — 탭 3개 전용 카드가 전체폭, 우측 1320px 공백 + 1페이지인데 비활성 페이저
- user_unassigned — 우선순위·난이도 열이 20행 중 5행만 채워짐(미할당=미분류라 **구조적으로** 빈다)
- user_profile — 알림 14행 flat 나열(서버 레지스트리는 `prefs.py:49-57`에서 이미 두 덩어리로 나뉘어 있는데 화면은 무시)

**면적은 쓰는데 정보량 0**
- admin_audit-anomalies (High) — 가장 넓은 `요약` 열이 `유형` 열의 되풀이: 유형 `처음 하는 동작` / 요약 `이 계정이 처음 하는 동작입니다`가 5행 중 4행. **판별 정보(evidence·detail)를 서버가 따로 내려주는데 목록은 title만 쓴다**(anomalies.py:213-217 vs governance.js:335-340).
- user_search-results — 문서 20행 부제가 `회의록, 개발` / `회의록, 기타` 반복. `indexer.py:204`가 부제를 document_type+work_field+owner로 만드는데 검색어가 '회의'라 첫 토큰이 전부 고정된다. 수정일·작성자는 모델에 있고 상세 화면이 이미 쓴다.
- user_activity — `로그인했습니다` 6행과 `비밀번호를 변경했습니다` 2행이 **전부 같은 파란 원형 화살표.** 아이콘이 사건 유형이 아니라 '내가 한 일/나에게 일어난 일' 분류만 나르고(Activity.jsx:62-72), 그 분류는 **같은 줄 꼬리표 텍스트와 100% 중복**이다.

**고칠 규칙:** ① 컨테이너 폭은 콘텐츠에 맞춘다(필터 카드·탭 카드는 전체폭 금지). ② 라벨-값 상세는 넓은 화면에서 2열로 접는다. ③ 표 열은 균등분산 대신 콘텐츠 폭 + 최대폭. ④ **같은 값을 두 자리에 그리지 않는다**(요약≠유형, 아이콘≠꼬리표, 제목≠첫 필드).

---

### R7. 버튼 variant → 의미 매핑이 화면마다 임의다 (6건)

- **admin_maintenance** — `버전 기록`·`변경 기록(켜고 끈 이력)`이 `variant="ghost"`(MUI text + `color:inherit`)라 테두리·밑줄·링크색이 **하나도 없다.** 실제로 판독자가 `변경 기록`을 "내용 없는 섹션 라벨"로 오독했다 — 그 오독이 어포던스 실패의 실측 증거다.
- **user_board-post** — 액션 4개 중 `목록`만 맨 텍스트(같은 줄에 외곽선 2개, 빨간 채움 1개)
- **admin_runner-detail** — `수정 | 비활성화 | 헬스 | 테스트 | 복제 | 버전 기록 | 감사 로그에서 보기` 7개가 같은 높이·구분선 없이 한 줄
- **user_team-doc-detail** — 가장 무거운 버튼이 **삭제**(빨간 채움), 가장 자주 쓰는 **본문 편집**은 카드 안쪽 작은 외곽선. `Ticket.jsx:156`·`BoardPost.jsx:437`도 동일 → **한 화면 버그가 아니라 제품 전반의 관례**다.
- **user_new-ticket** — 유일한 확정 동작 `티켓 만들기`가 y≈1175(접힘선 1080 아래), 헤더 액션은 비어 있음
- **user_team-tickets** — 같은 미할당 티켓이 여기선 `편집`만, `/unassigned`에선 `나에게 배정`+`편집`. 구조적 원인: `ticketColumns`가 표 단위라 "미할당 그룹만 배정 버튼"을 표현할 수 없다.

**고칠 규칙:** variant 매핑표를 정본화한다 — 주 동작=채움 / 보조=외곽선 / 이동=링크색 텍스트 / 파괴=확인 다이얼로그 + **채움 금지(외곽선 danger)**. `ghost`는 링크색을 갖거나 폐기. 액션 4개 초과 시 오버플로 메뉴. 폼의 제출은 sticky 바.

---

## 2. [잘 됨] — 다른 화면이 따라야 할 본보기

원문을 그대로 남긴다. 이들은 **"이 저장소는 이미 답을 안다"는 증거**이기도 하다 — 위 7개 묶음 대부분은 새 규칙이 아니라 이 본보기의 확장이다.

**① user_search-empty — 결과 없음 상태의 정본**
> 제목 "'존재하지않는검색어zz' 검색 결과" → "검색 결과 없음" → "'존재하지않는검색어zz' 와 일치하는 항목을 찾지 못했습니다." → "맞춤법을 확인하거나 더 짧은 검색어로 다시 시도해 보세요." → 「검색어 지우기」 1개(중립 스타일)

무엇이/왜/다음에 무엇을 한 화면에서 말하고, **되돌릴 버튼 하나만** 준다. R5의 목표 상태가 이것이다.

**② admin_ai-quotas 빈 상태 — 위험 → 절차 → 기대결과 4단 구조**
> 빈 상태가 위험을 먼저 말한 뒤 절차·기대결과로 이어져 본보기다 (platform.js:216-220 emptySituation/emptySteps/emptyExpected)

**③ 조용히 반만 거르지 않는다 — admin_documents 모드 필터 경고**
> "이 화면은 paginated라 모드 필터는 구조적으로 지금 페이지 안까지가 한계다. 경고 Callout이 그 필터 이름을 지목해 함께 알린다 — 조용히 반만 거르지는 않는다. 제대로 된 해결은 서버가 mode를 받는 것이고 그건 이 작업의 소유 범위 밖이라 적어 둔다." (automation.js:226-229)

**R5·R4의 정답이 여기 다 있다.** offboarding의 조용한 20건 잘림, search-results의 도달 불가 잘림이 정확히 이 원칙 위반이다.

**④ 추측하지 않는다 — 0을 0으로 보여준다**
> "추측하지 않는다: 참조가 0이면 0으로 보여 준다. 쓰이지 않는 프롬프트를 알아보는 것이 이 화면의 목적이므로 애매하게 감추면 목적이 사라진다." (app/prompts/router.py:279-280)

**⑤ 같은 라벨로 다른 수를 적지 않는다**
> "같은 라벨로 적으면 두 숫자가 같은 뜻으로 읽혀 오해가 된다" (OrgTree.jsx:94-96, user_count/subtree_user_count에 대해)

R3의 정본. **같은 파일이 부서 수에서는 이 규칙을 안 지켰다.**

**⑥ 원시 UUID로 방치하지 않는다 — 딥링크**
> `러너 ID`가 평문이 아니라 `#/runners?id=`로 러너 상세 드로어를 곧바로 여는 링크 (authoring.js:55-58). 도움말도 "참고용 메타데이터, 이 값만으로 실행되지는 않습니다"로 성격을 밝힌다.

R2에서 UUID를 손으로 옮겨 적게 하는 4화면이 따라야 할 본보기.

**⑦ 정보 노출을 의도적으로 줄인 자리에는 이유를 적어 둔다**
> "서버가 요청자 이메일/이름을 일부러 뺀다, 큐 화면이 대화 내용 열람의 우회로가 되지 않게. 그래서 라벨에 '계정 ID'라고 적어 사람 이름이 아님을 분명히 한다." (automation.js:371-374)
> "파일명만 목록에 보이고(내부 배포 경로 노출·너비 낭비 방지), 전체 경로는 상세에서" (platform.js:66-68)

**이 두 주석 때문에 적대적 검증에서 오탐 2건이 기각됐다.** 이유를 코드에 남기는 것 자체가 리뷰 비용을 줄인다.

**⑧ 기본 필터를 "사용자가 건 필터"로 세지 않는 이유** (DataScreen.jsx:454-465) — 오탐 1건 기각. **⑨ 사람이 읽는 텍스트만 검색 대상으로 좁힘** (authoring.js:210). **⑩ shortUA + Tooltip(원문)** (Users.jsx:42, :633) — R1의 profile UA 문제의 답이 같은 저장소에 있다.

---

## 3. 묶이지 않는 단독 결함 (6건)

| 화면 | 심각도 | 결함 | 왜 단독인가 / 고칠 지점 |
|---|---|---|---|
| **user_team-doc-detail** | **High** | 미러링된 문서 본문에 접속 URL 2건·계정 ID 3건·비밀번호 4건·원격데스크톱 IP+포트+계정 조합이 **마스킹 없이 평문 렌더**. 로그인만 하면 범위 내 누구나 열람. | 앱 버그가 아니라 **Notion 원본 콘텐츠**가 그대로 미러링된 것. 임의 본문 마스킹은 비현실적. 앱이 손댈 수 있는 것은 (1) 문서 단위 열람 범위/민감 표시 (2) 원본에서 자격증명 제거·회전. **추가 위험: QA 캡처 `dist/ui-qa-admin-2/…/user_team-doc-detail.png`가 저장소 안에 그 값들을 담고 있다.** |
| **admin_departments** | Med | 하위에 12명 딸린 부서가 인원 0으로 보이고, **그 0이 삭제 버튼 노출 조건**이다 | `org.js` 삭제 `when: (r) => !r.user_count`, `service.py:300-317`도 직속만 센다. 데이터는 안 사라지지만(`ondelete="SET NULL"`) **조직도가 조용히 재배치된다.** 표시 결함이 아니라 파괴적 액션의 게이트 조건 결함이라 R3와 분리했다. |
| **admin_policies** | Med | 정책 목록에 "무엇을 강제하는 규칙인가" 열이 **없고 넣을 수도 없다** — Policy 모델에 purpose/description 컬럼이 아예 없다 | 자매 엔티티 Prompt에는 `purpose`가 있고 화면에도 '용도' 열이 있다(`app/prompts/models.py:34` vs `:44-52`). **화면만 고쳐선 해결 안 되는 스키마 비대칭.** 대안: content_json에서 파생 요약 또는 컬럼 추가. |
| **admin_feature-flags** | Low | '기본값' 열이 없어 위험 플래그가 기본과 반대로 켜진 사실이 행에서 안 보인다 (`game_ai_enabled` 켜짐, 설명은 "기본 OFF(fail-closed)") | API가 이미 `default`를 내려주고 화면은 상세 드로어에서만 쓴다(`feature_flags.py:96` → `platform.js:279`). **순수 프런트 변경으로 가능한데 안 함.** |
| **user_team-doc-detail** | Med | 브레드크럼 `문서` 바로 아래 제목도 `문서`, 실제 제목은 카드 안 두 번째 위치 → **한 페이지에 h1이 2개** | `kit.jsx:1039` PageHeader가 `component="h1"`, `TeamDoc.jsx:289`도 `component="h1"`. 접근성 결함이 함께 나온다. |
| **user_team-doc-detail** | Low | 본문 안 URL이 본문과 같은 색·굵기의 평문이라 클릭 불가 | `TeamDoc.jsx` DocBlock에 linkify/href 경로가 없다. §2.6(innerHTML 금지)의 자연스러운 결과지만 **안전한 앵커 생성으로 고칠 수 있어 규칙이 막는 사안은 아니다.** |

---

## 4. 가장 먼저 고칠 것 3개

### ① user_team-doc-detail의 자격증명 노출 + 저장소 안 QA 캡처 (단독 High)
**이유: 유일하게 되돌릴 수 없다.** 다른 72건은 오늘 고치나 다음 달에 고치나 비용이 같지만, 이건 이미 노출됐고 **QA 캡처 PNG가 git 히스토리에 그 값을 담고 있어** 시간이 갈수록 회수 비용이 커진다. UI 결함이 아니므로 UI 사이클을 기다릴 이유도 없다.
순서: (1) `dist/ui-qa-admin-2/…/user_team-doc-detail.png` 처리 + 히스토리 확인 → (2) Notion 원본에서 자격증명 제거 → (3) 노출된 계정·비밀번호 회전 → (4) 문서 단위 열람 범위/민감 표시는 별도 설계.

### ② R1 — 공용 규칙을 옵트인에서 기본값으로 뒤집기 (12건)
**이유: 비용 대비 파급이 압도적이고, 논쟁할 것이 없다.** 규칙은 **이미 결정돼 있고 토큰·헬퍼·등록표까지 만들어져 있다.** 빠진 건 배선뿐이다. `EmptyState`에 `KO_WORD_BREAK` 한 줄이면 31개 파일이 동시에 좋아지고, `ROUTE_OWNER` 2줄이면 High 1건이 사라진다.

더 중요한 건 **실패 모드가 조용하다**는 점이다. `nav-active.test.js`가 이미 적어 뒀듯 "오타 하나면 그 화면에서 영원히 표시가 안 켜지는데, 증상이 조용해서 안 보인다." 지금 뒤집지 않으면 **다음에 추가되는 모든 화면에서 같은 12종이 재발한다** — 이번 판독에서 재발이 실제로 3번(KO_WORD_BREAK) 확인됐다.
함께 할 것: 테스트를 "컴포넌트 단위"에서 "사용자 산문을 그리는 모든 컴포넌트 단위"로 확장(현 `ko-wordbreak.test.jsx`가 Callout만 보는 것이 이 사태의 원인이다).

### ③ R4 — 약속-이행 불일치 (9건, High 2건 포함)
**이유: 신뢰를 직접 깎고, 대부분 문구 삭제라 가장 저렴하다.** 존재하지 않는 목록을 지목하고(ai-quotas), 인덱싱조차 없는 검색 범위를 광고하고(search), 없는 기능을 제목에 넣고(offboarding), 막다른 CTA를 주고(my-stats), 25일 전 데이터를 현재로 표시한다(integration-detail). **사용자가 한 번 화면 문구에 속으면 맞는 안내까지 안 읽는다** — 이 콘솔은 R5의 본보기들처럼 안내 문구에 크게 투자한 제품이라 손해가 특히 크다.

착수 순서(비용 낮은 순): ai-quotas 배너 문장 삭제 → TopSearch placeholder에서 '채팅' 제거 → offboarding 제목 정정 → my-stats 빈 상태를 `source.mapped` 분기와 연결 → integration-detail staleness 표시(`HEARTBEAT_STALE_SECONDS` 재사용) → search-results 0건 그룹·권한 게이트 명시.

---

**다음 후보:** R3(용어 사전)은 건수는 많지만 정본을 정하는 합의가 먼저 필요하고, R6(폭 예산)·R7(액션 위계)은 제품 전반의 디자인 결정이라 개별 화면 수정으로 접근하면 안 된다 — `user_team-doc-detail`의 삭제 버튼처럼 "한 화면 버그"로 보이는 것이 실은 `Ticket.jsx`·`BoardPost.jsx`와 공유된 관례인 경우가 있다.