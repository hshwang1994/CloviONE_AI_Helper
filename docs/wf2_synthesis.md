# 6개 영역 전수조사 종합 — 발견 56건 정리

> 아래는 제출된 56건(적대적 검증 통과분)을 재검증 없이 **정리·구조화**한 결과다. 각 행의 근거는 원 조사자가 직접 재현/코드확인한 것으로 표기된 내용을 그대로 인용했다.
> 분포: Critical 2 · High 11 · Med 27 · Low(및 Low-Med) 16. 폐기 11건은 제외.

---

## 1. Critical / High 전수 (13건)

### Critical (2건)

| # | 영역 | 문제 | 근거 | 고칠 지점 |
|---|---|---|---|---|
| C1 | 입력검증 | 공지 수정에서 **'내용'을 비우면 500**. PATCH 루프가 `body=None`을 그대로 `setattr` → NOT NULL 위반. 사용자에겐 영어 "Internal server error"만. POST 경로는 `body or ""`로 이미 방어 중인 **비대칭**. | 재현: `ANN BODY NULL -> 500 internal_error` + `IntegrityError: NOT NULL constraint failed: announcements.body`. `AnnouncementPatch.body: str\|None`(router.py:62) ↔ `nullable=False`(models.py:35) | `app/announcements/router.py:190-192` 루프에서 None을 '변경 없음'으로 취급, 또는 `app/schedules/router.py:78-80`의 `mode="before"` 코어서 적용 |
| C2 | 설치배포 | **문서에 적힌 번들 업그레이드 명령이 반드시 실패한다.** upgrade가 installer를 부를 때 `DNS_NAME`/`BIND_IP`를 안 넘기는데 installer는 그 둘이 없으면 exit 2. 그 시점엔 **이미 web·worker를 정지시킨 뒤**이고 되돌리는 코드가 없다. 같은 절차서의 tar 해제도 `--strip-components=1`이 빠져 STAGE 경로가 어긋난다. | `upgrade-…sh:31`(STAGE만 전달) vs `install-…sh:46-52`(exit 2), 정지는 `:27-28`. `git log`: 요구조건은 0a082f3(08-07) 추가, upgrade는 초기 커밋 이후 무수정. `tar -tzf … \| head -5` → 최상위가 `stage/`. `grep -rn upgrade-clovirone tests/` → **0건** | `scripts/upgrade-clovirone-web-assistant.sh:20-33` (호출 형태는 `update-from-git.sh:301-302`가 정본) + `docs/MAINTENANCE_PLAYBOOK.md:64-70` · `docs/DEPLOY_NOW.md:28` |

### High (11건)

| # | 영역 | 문제 | 근거 | 고칠 지점 |
|---|---|---|---|---|
| H1 | 입력검증 | 폼이 **선택 칸처럼 그린 4개 필드**(스케줄 시간대·타임아웃, 러너 타임아웃·동시실행수)를 비우면 null이 가는데 서버 계약이 non-Optional → 무조건 422 + 영어. 같은 파일의 다른 4개 필드엔 "콘솔이 명시적 null을 보낸다"는 주석과 코어서가 이미 있다. | 재현: `RUNNER PATCH {'timeout_seconds':None} -> 422 'Input should be a valid integer'`, `SCHED PUT {'timezone':None} -> 422` | 스케줄=`app/schedules/router.py:59,66`에 `:76-99` 코어서 패턴 적용. **러너는 스키마가 아니라** `app/runners/router.py:109-110`의 `RunnerConfig.model_validate(merged)` — merged에서 None 제거 |
| H2 | 입력검증 | 422 거절 시 대부분의 **사용자 화면**이 보는 유일한 문구가 영어 상수 `"Invalid request data"`. 실제 한국어 사유는 `error.details`에만 실리는데 `lib/api.js`가 `message`만 읽는다. 게시판·티켓·문서·게임·채팅·프로필이 전부 해당. | 재현: 게시판 20001자 → `message:"Invalid request data"`, `details[0].msg:"본문은 20000자 이하여야 합니다."` · `grep error.details frontend/src` → **2건**(사실상 kit.jsx 1곳) · `e.message` 호출부 **131건** | `frontend/src/lib/api.js:50` 한 곳. 규칙은 `app/static/js/change_password.js:492-501`에 이미 존재(details 우선 + `"Value error, "` 접두사 제거) |
| H3 | 설치배포 | **번들 업그레이드 경로에 실패 처리가 전혀 없다.** `set -euo pipefail`로 서비스를 멈추고 installer를 부르는데 pip/alembic/nginx -t/healthz 어디서 죽든 그냥 종료. `:22-24`에서 백업을 떠 놓고 쓰는 코드가 없다. git 경로엔 `rollback_now()`가 있다. | upgrade 스크립트 33줄 전문에 `trap`·`rollback` 문자열 **0건** vs `update-from-git.sh:61-88` 존재. 계약 테스트(`test_update_script_contract.py:33-35`)는 UPDATE/INSTALL만 대상 | `scripts/upgrade-clovirone-web-assistant.sh:20-33` + `tests/unit/test_update_script_contract.py` 대상 목록에 upgrade 추가 |
| H4 | 설치배포 | 설치처 고유값 가드의 주석이 **"여기서 멈추면 되돌릴 것이 없다"고 단언하지만 거짓**. 가드(226-252)보다 앞선 158행에서 `rsync -a --delete`로 /opt를 갈아치웠고 180행에서 venv도 올렸다. exit 21 시점 상태는 '새 코드 + 옛 스키마' + 서비스 정지. | `install-…sh:224` 주석 ↔ `:158` rsync, `:180` pip, 가드 `:226-252`(exit 21은 :249). `tests/unit/test_deploy_wiring.py:157-163`은 `guard_at < migrate_at`만 검사해 현 배치를 통과시킴 | 가드 블록(217-252)을 4단계 rsync(`:154`) **앞으로** 이동. 판정 근거(web.env·DB 존재)는 그 시점에 이미 갖춰짐. 테스트를 `guard_at < rsync_at`로 강화 |
| H5 | 설치배포 | **롤백이 특권 헬퍼를 되살리지 않는다.** stop은 privhelper까지 멈추는데(:20) 복원 루프(:64-66)·재시작(:76)·백업 대상(backup:21)은 web·worker 둘뿐. 롤백 후 healthz는 통과해 `ROLLBACK_OK`가 찍히지만 시스템 설정(타임존·DNS·호스트명·프록시·인증서)이 전부 "도우미가 없습니다". | 세 스크립트 전문 확인. `Restart=on-failure`는 명시적 stop을 되살리지 않음. `test_deploy_wiring.py:97-100`은 파일에 문자열 존재만 봐서 stop 한 줄로 통과 — **테스트가 구멍을 덮고 있다** | `backup-…sh:21` 유닛 목록 + `rollback-…sh:64,76`에 `clovirone-privhelper.service` 추가(기동 순서는 `install:289-291`). 테스트를 '재시작 대상에 있다'로 변경 |
| H6 | 게시판/문서 | **홈 '게시판' 위젯이 조직 게이트를 우회.** `list_posts`에 `org_id` 미전달 → `visible_posts(None)`. 게시판의 모든 경로는 `_viewer_org_id(me)`를 지나는데 홈 위젯만 문 밖. | 재현: 조직 B 세션 `GET /api/board/posts` → total=0 / **같은 세션** `GET /api/home/today` → recent.board = 조직 A 글 2건. 모듈 docstring(`readers.py:12`)은 "자유게시판 첫 페이지와 **동일**"이라 선언 | `app/home/readers.py:105-109` + `app/home/service.py:127`(viewer 인자 추가). 정답 모양 `app/board/router.py:244-263`. ※ 운영은 단일 조직이라 오늘 유출은 없음(잠재) |
| H7 | 게시판/문서 | **홈 '최근 문서' 위젯이 부서 범위 판정을 안 지난다.** archived/휴지통은 거르는데 부서 축이 없고 함수에 viewer 인자 자체가 없다. 다른 부서 문서의 제목·소유자·종류가 전 직원 홈에 노출. | 재현: B부서 사용자 `GET /api/team-docs` → items=[] / **같은 세션** `GET /api/home/today` → recent.documents 5건. `scope.py:147-155`가 `role=user`+부서 있음 → dept 스코프 — **오늘 운영에서 실제로 샌다** | `app/home/readers.py:69-102` + `service.py:126`. `app/team_docs/service.py:92-129 doc_in_scope` 경유(그 docstring이 열거한 관문 목록에 홈만 빠져 있음) |
| H8 | 게시판/문서 | **문서 목록이 범위를 페이지 자른 뒤 파이썬으로 거른다.** total은 '이 페이지에서 걸러진 수'만 깎여 총계가 틀리고 페이지는 안 채워짐. 사용자는 "3건" 페이저와 **빈 목록**을 동시에 본다. | 재현: 범위 밖 6건, page_size=3 → `page=1 total=3 items=0`, `page=2 total=3 items=0`. 저장소가 이미 이 결함에 이름을 붙여 뒀다: `app/tickets/router.py:235-237` | `app/team_docs/router.py:124-126` — 범위를 SQL로 내림. 정답: `app/tickets/service.py:289-311 _scope_assignee_ids`(질의) + `:459-469 _drop_out_of_scope`(그물) |
| H9 | 프로젝트 | **규칙 5개 중 1개만 판정돼도 score=100**이 나오고 그 100이 `Project.health_score`에 캐시돼 목록에 "100점"으로 뜬다. 대시보드 `unscored`는 NULL만 세므로 '못 잰 것'으로도 안 잡힌다. 상세 GET만 진실(`unknown`)을 안다. | 실행: `compute_health(…milestones=(), tasks=())` → `score=100 / checked=('notion_trouble',) / unknown=4개`. `_Ledger.result()`의 가드는 `if not checked:`(전부 unknown일 때만 None). `router.py:508-512` docstring이 정확히 이 상황을 금지하는 계약을 적어 뒀는데 **상세 응답에만** 걸려 있음 | `app/projects/health.py:228-239`에 '판정 규칙 n개 미만이면 None' 규칙, 또는 `checked/unknown`을 캐시에 함께 저장(`service.py:725-728`) |
| H10 | 러너 | `_READ_OR_QUESTION_RE`에 **호환 자모 리터럴** `ㄹ까`(U+3139)·`ㄴ지`(U+3134)가 들어 있어 조합형 한글과 절대 매치 못 한다 → '될까/할까/바꿀까/된 건지'가 질문으로 인식 안 됨. UPDATE-pending 분기의 가드 ①(:5492)이 **존재하는데 발화하지 않아** 허가를 구하는 질문이 미리보기 없는 직접 쓰기가 되거나 pending을 통째로 날린다. | 정규식 직접: '될까' False, '바꿀까' False / '맞는지' True. UPDATE pending 상태 라우팅: `'완료로 바꿔도 될까?'` → **action=WRITE_UPDATE** `{'진행상태':{'status':{'name':'완료'}}}`; `'완료로 바꿀까?'` → NEED_INPUT + pending 소실. BACKLOG RN-01(최상위 가드 부재)과 **다른 결함** | `runner/…/assistant.py:4984-4988` — `[가-힣]까` / `[가-힣]지` 또는 명시 대안. 회귀 테스트는 `test_assistant.py:3416` 계약을 미러링 |
| H11 | 화면간반영 | **사용자 홈('오늘')은 떠 있는 동안 절대 재조회되지 않는다.** 주석은 "30초면 알림·채팅 배지가 충분히 따라온다"고 단언하지만 `refetchInterval`이 없어 `staleTime`만으로는 아무 재조회도 안 일어난다. | 프로브 실행(가짜 타이머 300초): `/api/home/today` **0회**, `/api/board/mine` **0회** (채팅 13, 알림 5 등은 정상 폴링). `main.jsx:18 refetchOnWindowFocus:false`. `["home"]` 무효화 지점은 저장소 전체에 `ticket-views.js:40` 한 곳 | `frontend/src/screens/Home.jsx:280-288`. ⚠️ 폴링 추가 시 `home-request-budget.test.jsx`(분당 8요청 상한, 현재 ~6.2) 초과 — **알림/채팅 읽음 처리 자리에서 `["home"]` 무효화**가 예산상 안전 |

---

## 2. 근본 원인 묶음 — "몇 개의 규칙을 고치면 함께 사라지는가"

### R1. 부차 읽기 경로가 스코프 관문 밖에 있다 (7건, High 3)
**규칙:** *데이터를 읽는 함수는 예외 없이 viewer를 인자로 받고, 범위 조건은 SQL로 내린다. 파이썬 후처리는 그물로만 쓴다.*

포함: H6(홈 게시판 org) · H7(홈 문서 부서) · H8(페이지네이션) · Med(filters `recent` + `projects`에 휴지통 잔존) · Med(주간 다이제스트 두 리더) · Med(N+1 `filter_options` 121쿼리) · Low(홈 위젯에 idea 글 섞임 — `kind` 미전달)

증상이 다 달라 보이지만 원인은 하나다 — `app/home/readers.py`와 `app/team_docs`의 보조 함수들이 **viewer 인자 없이 설계됐다.** `doc_in_scope`를 (scope, id_to_user, visible) 준비 + 순수 판정으로 쪼개면 H7·H8·N+1이 한 번에 닫힌다. `readers.py` 3함수에 viewer를 붙이면 H6·H7·다이제스트·kind가 같은 커밋에 사라진다.

### R2. 쓰기 후 무효화가 '표'가 아니라 '호출부의 기억'에 의존한다 (7건, High 1)
**규칙:** *파생 화면 키 표(`ticket-views.js` 패턴)를 도메인마다 하나씩 두고, 표에 없는 무효화는 리뷰에서 반려한다.*

포함: H11(홈 폴링/무효화 부재) · Med(벨 '모두 읽음' ↔ 홈 카드) · Med(제안→티켓 전환이 `invalidateTicketViews` 미호출) · Med(`AssistantPanel`이 티켓 표에서 누락) · Med(feature-flags → `["me"]` 배선 없음) · Low(게시판 쓰기 → `home`/`board-mine`) · Low(문서 → `home`) · Low(댓글·반응 → 목록 카운트)

저장소는 **이미 정답 규약과 그 테스트 문화를 갖고 있다**(`ticket-views.js` 헤더, `crossScreenKeys.js`, `cross-screen-invalidation.test.jsx:123-129`). 결함은 규약 부재가 아니라 **적용 누락**이다 — 게시판/문서용 표를 하나 더 만들고 `["assistant"]`·`["home"]`·`["me"]` 세 줄을 기존 표에 추가하면 8건 중 7건이 소멸한다.

### R3. 클라이언트가 서버 계약(None 허용·길이·범위·정규식)의 사본을 갖고 있지 않다 (8건, Critical 1 / High 2)
**규칙:** *제약은 registry field 스키마 한 곳에 선언하고, 클라이언트 선검사와 서버 검증이 같은 출처를 읽는다. PATCH의 None은 언제나 '변경 없음'이다.*

포함: C1(공지 body null 500) · H1(4개 필드 null↔non-Optional) · Med(FormField에 상한 표현 수단 자체가 없음, registry 2,802줄에 maxLength/min/max **0건**) · Med(Board/TeamDocs 본문·메모 무제한) · Med(slug 정규식 원문 노출) · Med(BodyPreview 문구 ↔ 서버 전체 거절) · Low(user_id 필수 표시 누락) · Low(footer submit 이원화)

⚠️ **함정:** `inputProps`에 min/max를 다는 해법은 통하지 않는다 — `SettingEditor.jsx:59-60`이 "Save는 커스텀 버튼이라 네이티브 검증이 안 돈다"고 이미 경고했다. `maxLength`만 예외(입력 차단이라 동작). 정본은 registry 스키마 + `FormModal.submit()` 선검사.

### R4. 서버가 사용자에게 보낼 수 없는 말로 거절한다 (4건, High 1)
**규칙:** *422 응답의 `message`는 그 자체로 사용자에게 보여도 되는 한국어여야 하고, `loc`는 필드 지목에 쓰인다.*

포함: H2(`"Invalid request data"` 131개 호출부) · Med(FormModal이 `loc` 폐기 → 스크롤·포커스·하이라이트가 서버 실패 경로에서만 죽음) · Med(pydantic 정규식/영문 원문 노출) · Low(오류가 라벨 아닌 raw 필드명 `user_id`를 말함)

`lib/api.js:5-6`의 설계 의도("서버 문구가 있으면 그쪽이 항상 이긴다")는 *서버 문구가 사용자 언어*라는 전제 위에 서 있는데 `errors.py`의 422 경로가 그 전제를 깬다. **전제를 지키거나(서버 수정) 전제를 버리거나(클라 수정) 둘 중 하나**를 택하면 4건이 함께 닫힌다. 저장소는 이미 답을 알고 있다 — `change_password.js:492-501`이 그 규칙을 바닐라 JS 시절에 적어 뒀고 React로 전파되지 않았을 뿐이다.

### R5. 부분 성공이 성공 신호를 낸다 (5건, Critical 0 / High 2)
**규칙:** *일부만 됐으면 OK를 찍지 않는다. 판정 불가는 만점이 아니라 '못 잼'이다.*

포함: H9(1/5 판정 → 100점 캐시) · H5(privhelper 죽은 채 `ROLLBACK_OK`) · Med(app/etc tar 부분 실패해도 `BACKUP_OK`, 그 문자열을 update-from-git이 '되돌릴 지점이 생겼다'의 근거로 파싱) · Med(nginx 심링크 없는 상태로 127.0.0.1 찔러 `ROLLBACK_OK`) · H8(걸러진 페이지에 total만 남음)

이 묶음은 **가장 위험한 부류**다 — 결함이 자기 자신을 숨긴다. 성공 판정을 "사용자가 실제로 쓰는 층"에서 하도록(healthz→nginx 경유 URL, BACKUP_OK→필수 구성원 존재 확인, score→checked 개수) 바꾸면 5건이 함께 사라지고, 앞으로 같은 부류가 생겨도 드러난다.

### R6. 러너의 의도 판정 술어가 있는데 그 자리에서 안 불린다 (6건, High 1)
**규칙:** *질문·취소·부정·댓글 술어는 pending 분기 안이 아니라 라우팅 전처리에서 한 번 평가하고, 술어마다 유니코드 정규화 테스트를 붙인다.*

포함: H10(자모 리터럴로 가드 무력화) · Med(CREATE 중 탈출구 없음 — `is_undo_intent`·`DECLINE_COMMANDS`가 True인데 `if pending:` 안에 갇혀 도달 불가) · Med(`추가` 때문에 댓글 요청이 CREATE로 납치) · Med(`'응 이대로 해줘'`가 승인 아닌 UPDATE 피벗으로 읽혀 pending 소실) · Med(CREATE/UPDATE pending 중 댓글 요청이 조용히 증발) · Low-Med(`'맞아'` 계열이 도달 불가한 죽은 엔트리)

전부 "판단 로직이 없다"가 아니라 **"판단 로직이 그 경로에서 호출되지 않는다"**다. 기존 BACKLOG RN-01~03도 같은 뿌리 — 즉 러너는 개별 패치가 아니라 **라우터 구조 1회 리팩터링**으로 접근해야 하는 영역이다.

---

## 3. 영역별 한 줄 판정 (예산 배분용)

| 영역 | 건수 (C/H) | 판정 | 예산 권고 |
|---|---|---|---|
| **설치·배포** | 13 (1/3) | **최약점.** 문서대로 하면 서비스가 멈춘 채 복구 경로가 없고, 계약 테스트가 실제 배포 경로를 비껴가 구멍을 오히려 덮고 있다. | **최우선·최대.** 여기가 막히면 다른 55건을 고쳐도 배포할 수 없다 |
| **게시판·문서·홈** | 13 (0/3) | **약점(경계 한정).** 주 경로(라우터)는 견고한데 **부차 읽기 경로가 관문 밖**. 오늘 실제 유출 1건(부서), 나머지는 잠재. | **높음.** 단 수정이 `readers.py` 1파일 3함수에 집중돼 투자 대비 회수가 매우 큼 |
| **입력검증** | 10 (1/2) | **구조적 약점, 그러나 국소 수정 가능.** 서버 검증은 촘촘한데 계약 사본이 클라에 없어 폼 수만큼 결함이 증식. | **높음(효율 1위).** 공용 지점 3곳(`lib/api.js`·`kit.jsx`·registry 스키마)이 8~10건을 덮는다 |
| **러너 의도분류** | 6 (0/1) | **약점이나 '알려진' 약점.** BACKLOG RN-01~20이 이미 있고 신규 6건도 뿌리가 같다 — 개별 패치는 두더지잡기. | **중간, 별도 트랙.** 라우터 전처리 리팩터링 1회로 묶어서 |
| **화면간 반영** | 8 (0/1) | **중간, 사실상 강점 인프라.** 규약(`ticket-views.js`)·테스트 문화가 이미 있고 위반이 누적됐을 뿐. 8건 중 5건은 노출 창이 30초로 한정. | **중간(효율 2위).** 표에 3~4줄 추가 + 테스트 확장으로 7건 소멸 |
| **프로젝트·스프린트** | 6 (0/1) | **상대적 강점.** 최소 건수이고 High 1건 외엔 위생·문서·표기 문제. 모듈 docstring이 계약을 잘 적어 뒀다(H9도 그 계약을 어긴 것이 근거였다). | **최소.** H9 하나만 처리하고 나머지는 백로그 |

---

## 4. 가장 먼저 고칠 것 3개

### ① 배포 배선 복구 — C2 + H3 (+ H4, H5, Med 4건 동반)
**왜 1순위인가:** 유일하게 **다른 모든 수정을 차단**하는 항목이다. 지금 문서대로 업그레이드하면 서비스를 멈춘 뒤 exit 2로 죽고, 되돌릴 코드가 없다. 나머지 55건을 다 고쳐도 프로덕션에 내보낼 경로가 없다는 뜻이다. 게다가 이 영역의 결함들은 **자기를 숨긴다**(R5) — `ROLLBACK_OK`·`BACKUP_OK`가 거짓으로 찍혀 실패를 못 본다.

작업: `upgrade-…sh`에 `DNS_NAME`/`BIND_IP` 전달 + 서비스 정지 **전** 사전검증 + `rollback_now()` 이식 → 절차서 tar/`sha256sum` 3줄 수정 → 가드를 rsync 앞으로 → privhelper를 backup/rollback 목록에 추가 → `test_update_script_contract.py` 대상에 upgrade 추가.
검증: 스테이징에서 **문서에 적힌 명령을 그대로 복붙 실행**해 통과하는 것을 볼 것. 스크립트 단위 통과는 증거가 아니다(그게 지금 이 사태의 원인이다).

### ② `app/home/readers.py` 스코프 관문 — H7 + H6 (+ Med 3건, Low 1건 동반)
**왜 2순위인가:** **오늘 실제로 데이터가 샌다.** H7은 부서가 채워진 이 저장소에서 잠재가 아니라 현행이고, 다른 부서 문서의 제목·소유자가 전 직원 홈 사이드레일에 뜬다. 그리고 수정 범위가 **한 파일 3함수 + service.py 2줄**로 극히 좁은데 High 2건 + Med 3건이 함께 닫힌다 — 위험도 대비 최소 비용.

작업: `recent_documents`/`recent_board_posts`/`documents_changed_between`/`board_posts_between`에 viewer 인자 추가 → `doc_in_scope`·`org_id` 경유 → `kind=KIND_FREE` 추가 → `comment_count` 루프를 `comment_counts`로 → 같은 커밋에서 `team_docs/router.py:124-126`을 SQL 범위로 전환(H8).
회귀 핀: "조직/부서 밖 사용자의 `/api/home/today`와 `/api/board/posts`·`/api/team-docs`가 같은 집합을 본다"를 테스트로.

### ③ `lib/api.js` 오류 문구 조립 + 공지 PATCH None 가드 — H2 + C1
**왜 3순위인가:** **레버리지가 가장 높다.** `lib/api.js:50` 한 줄 수정이 `e.message`를 쓰는 **131개 호출부**를 동시에 고친다 — 게시판·티켓·문서·게임·채팅·프로필 전체가 "왜 거절됐는지"를 한국어로 말하기 시작한다. 여기에 C1을 얹는 이유는, C1이 **유일하게 사용자가 500과 영어 문구를 동시에 보는 경로**이고 수정이 한 줄이며, ②를 배포하는 창에 같이 태울 수 있어서다.

작업: `lib/api.js`에서 `details` 우선 조립 + `"Value error, "` 접두사 제거(규칙 원본은 `change_password.js:492-501`) → 공지 PATCH 루프에서 None을 '변경 없음'으로 → 여력이 있으면 `kit.jsx:889-892`에서 `loc` 마지막 요소를 `setErrField`로(이미 구현된 스크롤·포커스·하이라이트가 그 즉시 살아난다).
⚠️ 함께 하지 말 것: `inputProps`로 min/max를 다는 접근(R3 함정). registry 스키마 확장은 별도 사이클로.

**보류 권고:** H9(health 100점)·H10(자모 정규식)·H11(홈 stale)은 각각 단독 수정이 가능하지만, H10은 러너 라우터 전처리 리팩터링과 묶어서, H11은 요청 예산 테스트 때문에 무효화 방식 설계가 선행돼야 하므로 4순위 이후로 둔다.