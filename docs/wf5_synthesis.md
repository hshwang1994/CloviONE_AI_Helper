# 미조사 6영역 종합 — 60건 (Critical 1 / High 6 / Med 19 / Low 34, 반증 폐기 25건)

> **이 종합의 검증 상태.** 아래 Critical/High 7건의 **코드 앵커는 내가 직접 다시 읽어 확인**했다(✅): `app/users/router.py:243-268 vs :284-285`, `app/games/service.py:451-479 / :678`, `frontend/src/ui/kit.jsx:826,835-847`, `app/runners/service.py:108 ↔ :204-227`, `frontend/src/screens/TicketAttachments.jsx:63-79`, `app/core/uploads.py:128-148`. **각 조사자가 돌린 재현 프로브는 내가 재실행하지 않았다(⚠️ 인용)** — 프로브 결과로 표시된 STATUS/DB 값은 조사자 보고를 그대로 옮긴 것이다. 심각도·중복 판정은 내가 재판정했다.

---

## 1. Critical / High 전수 (7건)

| # | 심각도·영역 | 문제 | 근거 | 고칠 지점 |
|---|---|---|---|---|
| **C1** | Critical · CSV일괄 | **`/api/admin/users/import/csv`가 역할 부여 게이트를 통째로 우회한다.** 단건 생성은 `payload.role in CONSOLE_WRITE_ROLES and actor != system_admin` → 403, PATCH는 system_admin 부여 하드 403 + admin 승격은 승인. CSV는 `ALL_ROLES` 안이기만 하면 `create_user(role=…)`로 직행 — plain `admin`이 system_admin을 찍어낸다. | ✅ 코드 확인: router.py:251-259는 `parse_import_csv` → `bulk.import_users`뿐, 역할 검사 0. :284-285에만 게이트. ⚠️ 조사자 재현: 같은 세션에서 POST `/api/admin/users {role:system_admin}` → **403**, CSV(system_admin·admin 2행, dry_run=false) → **200 {created:2}**, DB에 `global` 범위로 앉음. 기존 테스트 15개는 `admin` 픽스처가 role=system_admin(:30)이라 경계를 한 번도 안 밟는다. | **게이트를 라우터에서 `app/users/service.py::create_user`로 내리고 `actor_role`을 필수 인자로.** CSV·CLI·승인 실행기가 같은 규칙을 탄다. 최소 조치: bulk.py에서 비-system_admin의 admin/system_admin 행을 `failed` 처리. |
| **H1** | High · 첨부위젯 | **순차 업로드 중간 실패 시 이미 저장된 N-1개가 화면에 안 나타나고, 재시도하면 중복 저장된다.** `refresh()`가 `onSuccess`에만 있다. 서버 `add_attachment`에 파일명·해시 중복 검사가 없어 매번 새 UUID로 또 저장 → 10칸 상한을 스스로 소모. | ✅ 코드 확인: TicketAttachments.jsx:69-74 순차 `await` 루프, :77 `onSuccess: …refresh()`, :78 `onError: toast(...)` — refresh 없음. 현실적 방아쇠는 F8(드롭 경로에 형식 선검사 0): png 3 + txt 1 드롭 → 3개 저장 후 4번째 422 → 화면 0개. 대조군이 같은 저장소에 있다: **Board.jsx:153-170**이 파일별 try/catch + failed[] + "글은 저장했지만 첨부 N개를 못 올렸습니다"로 이미 풀어 뒀고 주석에 그 사고 이력까지 적혀 있다. | `onSuccess` → **`onSettled`에서 항상 `refresh()`**, mutationFn을 `{ok, failed[]}` 반환으로 (Board.jsx 패턴 이식). 크기 선검사도 Board.jsx:247-250처럼 "초과분만 제외"로 통일. **이 한 줄이 F7(삭제 실패 stale)도 함께 닫는다.** |
| **H2** | High · 첨부위젯 | **`save_upload`의 mkdir/write_bytes에 `OSError` 처리가 없어** 파일시스템 권한·용량 오류가 전역 핸들러까지 올라가 한국어 UI에 영어 `"Internal server error"`가 뜬다. 덤으로 `record_audit_from_request`가 서비스 호출 **뒤**라 업로드 실패는 감사에 한 줄도 안 남는다. | ✅ 코드 확인: uploads.py:146-148 `target_dir.mkdir(...)` / `write_bytes(...)` 무방비, 위 :129-143 검증만 존재. ⚠️ 조사자 재현: mkdir에 PermissionError 주입 → **500** `{"code":"internal_error","message":"Internal server error"}`, 같은 세션 감사 = `[('user.login','success')]`. | uploads.py에서 `OSError` → 503 AppError(한국어 + 문의번호), 원인은 `logger.exception`으로 서버에만. router.py:600-624를 try/except로 감싸 `result="failure"` 감사 후 재발생. **500 기본 문구 한국어화(errors.py:271-277)는 앱 전체를 함께 닫는다(FN-40/UX-40과 동일 자리).** |
| **H3** | High · 게임 | **타이머 자동 확정이 두 번 실행되어 서로 다른 승자를 쓴다.** 가드가 `if room.status != ROOM_PLAYING: return` 하나뿐인 read-then-write이고, 트리거가 **인증된 아무나의 `GET /state`(1.2초 폴링)** 라 참여자 수만큼 동시 진입한다. 확정한 요청은 자기 결과를 그 응답에 실어 주므로 A는 승자1, B는 승자2를 보고 다음 폴링에서 뒤집힌다 → 축포 2회. | ✅ 코드 확인: service.py:454 단일 가드, :468-478이 무작위 채움으로 결과 확정, 진입에 조건부 UPDATE 없음(`room.status = ROOM_FINISHED` 단순 대입 4곳). ⚠️ 조사자 프로브: 두 세션 겹침 → `game_events`의 `result` 이벤트 **2건**, winners `[]` vs `[호스트]`. `_append_event`가 seq 충돌을 흡수해 두 번째도 조용히 남는다. | 확정 진입을 **조건부 UPDATE**로: `UPDATE game_rooms SET status='finished' WHERE id=? AND status='playing'`의 `rowcount==1`인 요청만 계산·기록. (12라운드 CAS가 제출 경로에만 붙은 것의 나머지 절반 — F12 Med도 같은 자리다.) |
| **H4** | High · 게임 | **가위바위보 토너먼트만 유령 필터가 약해, 탭 닫고 떠난 사람이 대진에 들어가고 서버 무작위 채움 + 코인플립으로 챔피언까지 올라간다.** 시딩은 `m.active and role != spectator`, 강제 마감 present 판정은 `get_member(...) is not None`(=나가기를 눌렀는가)뿐. 나머지 6경로는 전부 `_present_players`(active + last_seen 90초 + 비관전). | ✅ 코드 확인: service.py:678 `[m for m in repository.members(...) if m.active and m.role != ROLE_SPECTATOR]`. ⚠️ 조사자: `grep '\.active = ' app/ alembic/` → **True 대입 2곳뿐**(:157,:1100) — `active`는 저장소 어디서도 False가 되지 않는다. 로컬 DB `active=0` 0행/7행. 고정 테스트(test_games_api.py:521)도 `leave` 경로만 검증. | :678 시딩과 :744-745 present 판정을 **`_present_players`로 통일**(2줄). 같은 수정이 F13(표시 계층 분모)의 서버측 근거도 만든다. |
| **H5** | High · 동시성마이그 | **관리 콘솔 공유 편집 폼(FormModal+DataScreen)이 화면에 그린 모든 필드를 매번 재전송**하고 서버는 `merged = {**before, **model_dump(exclude_unset=True)}`로 받는다 → 두 관리자가 같은 행을 열면 나중 저장이 앞사람 변경을 조용히 되돌리고 **양쪽 다 성공 토스트**를 본다. `config_version`은 존재·증가·응답·목록열까지 다 있는데 아무도 되돌려 보내지 않는다. | ✅ 코드 확인: kit.jsx:826 `shownFields`(showIf만 거름) → :838 루프가 checkbox/number/json 전부 `body[f.name]` 대입(:843,:847). 서버 merge 3곳(integrations/router.py:95, runners:110, workflows:71). 편집 폼 12개 라인 전부 실재. ⚠️ BACKLOG 2828줄 grep → **동시 편집/lost update 항목 0건**(내가 재확인: `config_version` 히트는 라벨 문제 VIS-145 하나뿐). | **`Users.jsx:50 diffFields`를 공용 모듈로 올려 `DataScreen.jsx:729`에서 `diffFields(body, editing)`**. 저장소에 방지 패턴이 이미 **세 벌**(diffFields + `projects/router.py:101-103 base_notion_version` + 문서 `base_version`) — 공유 부품에만 없다. |
| **H6** | High · 동시성마이그 | **`maintenance_state`가 서킷 브레이커(기계)와 편집 폼(사람) 양쪽 writer를 가진다.** 관리자 A가 '점검'으로 내려 배분을 멈춘 것을, 폼을 열어 두고 있던 B가 오탈자만 고쳐 저장하면 `normal`로 되살아나 **장애/점검 중 러너로 새 작업이 흘러간다**(service.py:188이 maintenance일 때만 배분을 막는다). | ✅ 코드 확인: service.py:108 `row.maintenance_state = config.maintenance_state`(폼 writer) ↔ :207-208 성공 시 degraded→normal 자동 복구, :213 임계 초과 시 degraded(기계 writer). 폼 필드 integrations.js:184, `RUNNER_MAINT_OPTS`에 세 값 모두 존재. **반증 시도가 오히려 강화**: `org.js:107`·`:147`에 같은 문장이 두 번 — "활성 토글은 확인 문구가 붙은 액션으로만 처리한다(수정 폼의 무경고 체크박스 제거)". 조직/부서/직책/연동/워크플로 편집 폼엔 상태 전이 필드가 0개. | `maintenance_state`를 edit.fields에서 빼고 **확인 문구가 붙은 전용 액션으로만**(org.js가 이미 한 그대로). 같은 낙오가 하나 더: **공지 `active`(platform.js:204)** — F54 Med, 같은 수정. |

**7건의 지형:** C1은 단독(권한). H1·H2는 같은 화면, H3·H4는 같은 파일, H5·H6·F54는 **같은 결함의 세 사례**. 즉 **수정 진입점은 5개**이고 그중 3개(H1 onSettled, H4 `_present_players`, H5 diffFields)는 각각 한 줄~두 줄이다.

---

## 2. 영역별 한 줄 판정 (예산 배분용)

| 영역 | 건수 (C/H/M/L) | 강점 → 약점 한 줄 | 예산 |
|---|---|---|---|
| **CSV일괄** (users bulk) | **12 (1/0/7/4)** | **최약점.** dry-run 강제·행별 실패 원칙·200 상한의 근거 주석까지 **설계는 이 저장소에서 가장 신중한 축**인데, 그 신중함이 전부 `bulk.py` 안에만 있고 **단건 라우터가 가진 게이트·검증·감사·메일은 하나도 물려받지 않았다** — 그래서 이 영역이 라운드 유일의 Critical을 냈다. | **최우선.** `create_user(actor_role=…)` 필수화 1건이 C1을 닫고, `parse_import_csv`가 `_validate_email_shape`를 재사용하면 F23이, dry-run 감사 1행이 F24 절반이 닫힌다. **3개 수정으로 12건 중 6건.** |
| **동시성마이그** | **11 (0/2/3/6)** | **인프라는 완비, 소비자가 0.** `config_version`·승인 경로 STALE 가드·0040+ 마이그 가드·`base_notion_version`까지 **정답이 저장소 안에 다 있는데 공유 폼 부품과 0001~0039만 그 밖에 있다.** 시계 축(3건)은 이 라운드가 처음 연 축. | **차우선.** `diffFields` 공용화 1건이 H5 + F56 + (폼에서 상태 필드 제거로) H6·F54를 함께 사정권에 넣는다. 마이그/시계는 **하드닝**이라 실환경 확인 후 판단(§5). |
| **게임** | **10 (0/2/3/5)** | **서버 확정 설계는 옳고 유령 필터도 6/7 경로에 이유 주석까지 붙어 있다** — 문제는 전부 **"7번째"**다(토너먼트 시딩, `_finish_vote`, 확정 진입 CAS, 표시 계층). 12라운드 CAS 수정이 제출 경로에서 멈춘 잔재가 그대로 남았다. | **중간.** 조건부 UPDATE 1개(H3) + `_present_players` 통일(H4) + 응답에 `present` 싣기(F13)면 High 2 + Med 2가 닫힌다. 나머지(F16~F19)는 만질 때 흡수. |
| **첨부위젯** | **9 (0/2/1/6)** | **입력 문(pick)을 하나로 모은 설계·상한 3종 값 일치·의도 주석은 좋은데, 전부 "성공했을 때"만 그려 뒀다** — 부분 성공·삭제 실패·이미지 404·형식 거절 어느 것도 화면에 자기 상태가 없다. | **작다(고효율).** `onSettled` 한 줄 + Board.jsx 패턴 이식 = H1 + F4 + F7 동반 마감. H2(OSError)는 **앱 전역 500 한국어화와 같이** 처리. |
| **잡핸들러** | **10 (0/0/3/7)** | **`PermanentJobError` 분류 규약이 docstring으로 명문화돼 있고 batch 핸들러는 실제로 지킨다** — 새는 곳은 필드 단위 파싱(`int(...)`)과 **형제 단건 경로**(sync엔 가드 3개, verify엔 0개). 종착 상태 중 `quality_failed`만 알림 비대칭. | **중간→작다.** verify_mapping에 sync의 가드 3줄 이식(F40) + `source_row_count` try/except(F41) + quality_failed 알림 1건(F42). 나머지 7건은 주석·문구 정리라 만질 때 흡수. |
| **lib기반** (shell/lib) | **8 (0/0/2/6)** | **가장 건강.** 벨의 401 폴링 정지·ErrorState 재로그인 CTA·계정별 테마 키 — 방어가 **실제로 있고 이유까지 적혀 있다.** 문제는 그 방어가 **같은 캐시 키의 두 번째 옵저버**(useNavBadges)와 **로그아웃 안 한 사용자**라는 두 구멍에서만 샌다. C/H 0건. | **가장 작다.** `auth.jsx` 2줄(refetchInterval/onFocus) + `useNavBadges`에 함수형 interval = Med 2건 마감. 나머지 6건은 죽은 코드 삭제·re-export라 리팩터 때 흡수. |

---

## 3. 새로 드러난 근본 원인 (기존 **WF1 R1~R7 · WF2 R1~R6 · WF4 N1~N6**에 없던 것만)

### N7. 시계는 앞으로만, 일정하게 간다 — 벽시계 차분에 하한도 정합성 검사도 없다 (5건)
**규칙:** *경과를 재는 코드는 시각이 아니라 경과를 물어야 한다(`monotonic`). 시각을 써야 한다면 그 값의 그럴듯함을 먼저 검사한다.*
포함: F53(ratelimit `elapsed`에 `max(0.0, …)` 없음 → 역행 시 토큰 음수, `login:{ip}` 키라 NAT 뒤 전원 차단, **`reset()` 호출부 0건이라 올바른 비번으로도 못 푼다**) · F57(워커 리스 만료가 벽시계 → 살아 있는 워커 인수) · F58(되돌릴 수 없는 삭제 8종이 `now - timedelta` 하나에만 의존) · F60(게임 카운트다운 클라 스큐).
**왜 기존 R이 아닌가:** 기존 시간 관련 항목(UA-07/08)은 전부 **UTC vs KST 경계**이고 QA-08은 **테스트 결정성**이다. "시계가 움직인다"는 축은 `docs/wf3_gaps.json:270-274`가 *never examined*로 지목만 해 둔 채 비어 있었다 — **이번이 첫 관측**이다. 제품 안의 유발 경로도 실재한다: `app/sysops/actions_system.py:123-150 _perform_ntp`(관리자가 임의 NTP 서버 지정 후 timesyncd 재시작).
**가장 싼 수정:** `elapsed = max(0.0, …)` 2줄 + `RateLimiter.reset()`을 로그인 성공 경로에 배선(이게 F53의 유일한 탈출구를 만든다).

### N8. 공유 편집 폼이 "화면에 있는 것 = 사용자가 정한 것"으로 전송한다 — 사람 writer가 기계 writer를 덮는다 (4건, High 2)
**규칙:** *PATCH 본문은 화면이 아니라 **변경분**이어야 한다. 컬럼에 자동 writer가 있으면 그 컬럼은 폼에 두지 않는다.*
포함: H5(DataScreen 12개 폼 전부) · H6(`maintenance_state` ↔ 서킷 브레이커) · F54(공지 `active` ↔ 확인 문구 액션) · F56(승인 경로엔 STALE 스냅샷 대조가 있는데 **가장 강한 권한인 직접 PATCH에만 없다**).
**왜 기존 R이 아닌가:** `wf4_synthesis.md:96`이 스스로 적었다 — *"낙관적 잠금은 이번 45건에 **동시 편집 축이 하나도 없었다**"*. 예고만 있고 사례가 0이던 축이고, N2(형제 미전파)와 달리 **형제 파일 diff로는 안 나온다** — "이 컬럼의 writer 집합"을 열거해야만 나온다.
**가장 싼 수정:** `diffFields` 공용화(H5) + 상태 전이 필드를 폼에서 제거(H6·F54). org.js:107이 **이미 그 규칙을 문장으로 세워 뒀다** — 관례가 없는 게 아니라 낙오가 3건 있는 것이다.

### N9. 스키마 변경의 원자성이 "첫 문장이 DML인가"라는 우연에 걸려 있다 (3건)
**규칙:** *SQLite에서 마이그레이션의 원자성은 보장이 아니라 부산물이다. 존재 가드가 재실행 가능성의 유일한 근거다.*
포함: F52(pysqlite는 DDL 앞에서 BEGIN을 안 걸어, 첫 문장이 DDL인 마이그레이션이 중간에 죽으면 표는 남고 `alembic_version`은 안 올라 **재실행이 `table already exists`로 영구 고착** — 0001~0039 가드 0개, 0040~0052만 가드 있음) · F55(alembic 자체 엔진이 `busy_timeout`을 안 걸어 앱과 비대칭 → 즉시 `database is locked`) · F59(0050이 원자적인 **이유가 설계가 아니라 `_TABLES` 순서**라, 누가 "고아가 없으면 UPDATE 생략"으로 최적화하면 조용히 비원자적이 된다).
**왜 기존 R이 아닌가:** N1("파일시스템은 실패하지 않는다")과 같은 *환경 낙관* 계열이지만 대상이 **트랜잭션 의미론**이라 탐지 방법이 다르다 — 코드 읽기로는 안 나오고 **예외 주입 재현**으로만 나왔다(⚠️ 조사자 재현: 0033 4번째 create_table에 예외 주입 → 3표 잔존 + 고착 확인). `install.sh` 헤더의 *"Idempotent, re-runnable"* 이 **완주한 경우에만 참**이라는 것도 이 축의 소산이다.

### N10. 권한 게이트가 **라우터 층**에 살아, 진입점이 늘어날 때마다 사본이 필요하고 새 진입점의 기본값은 '무게이트'다 (Critical 1 + 3건)
**규칙:** *게이트는 서비스 함수의 **인자**여야 한다. 라우터에 있는 게이트는 그 라우터만 지킨다.*
포함: C1(CSV가 유일하게 열린 문 — PATCH로는 재현 불가) · F21(`UserCreateRequest`에 `admin_scope` 필드 자체가 없어 **한 번에 범위 좁힌 관리자를 만들 방법이 제품에 없다** → 항상 `global`로 태어남) · F23(이메일 형태 검사가 스키마 층에만) · F26(`bulk_apply`의 `set_department`에 범위 검사 없음).
**왜 기존 R이 아닌가:** WF4-N4는 **CLI(웹 밖)** 진입점이었고 결론이 *"정책은 인자로 흐른다"* 였다. 이번 것은 **웹 안에서 라우터 하나만 다른 문을 통과**한 사례라, "웹 라우트는 다 봤다"는 이전 커버리지 판단을 무효화한다. N4의 확장이되 **위험 등급이 다르다** — CLI는 운영자만 쓰지만 CSV는 콘솔 버튼이다.
**곁가지(별건, BACKLOG 없음):** 조사 중 확인된 더 짧은 경로 — 부서 범위 관리자가 `PATCH /api/admin/users/{자기 id} {"admin_scope":"global"}` → **200**. `_apply_admin_scope`(service.py:293-350)에 행위자 검사가 없다. **C1과 함께 같은 함수에서 닫아야 한다.**

### N11. 감사는 "성공한 상태 변화"만의 기록이다 — 거부·미리보기·반출 질의·실패는 사후 재구성 불가 (5건)
**규칙:** *권한 경계에 막힌 시도와 데이터 반출 질의는 성공한 변경보다 감사가 더 알아야 할 사건이다.*
포함: F24(CSV dry_run 무감사 — 200행 이메일 사전을 흔적 없이 반복 조회 가능) · F27(대량 작업 **실패 건 무감사** + 응답에 `id`만 담아 화면도 "어느 3명"인지 못 보여 줌) · F28(사용자 CSV 내보내기 감사에 `q·role·department_id` 등 **필터가 전부 빠져** 행 수만 남음 — "개발팀 12명"과 "임원 12명"이 구별 안 됨) · H2 후반(업로드 실패 무감사) · F14 계열.
**왜 기존 R이 아닌가:** WF2-R5는 "부분 성공이 **성공 신호를 낸다**"(사용자 화면 축)이고, 이건 **관측 기록 축**이다. 결정적 대조군이 같은 저장소에 있다: `app/core/deps.py:179-202`가 임퍼소네이션의 **막힌 쓰기**를 굳이 별도 세션까지 열어 세면서 *"막힌 시도는 세어 둔다 … 그 사실은 감사가 알아야 한다(실수든 아니든)"* 라고 적어 뒀다. 같은 저장소가 같은 종류의 사건을 다른 곳에서 전부 버린다.
**부수 효과 하나:** 이 결함이 **BACKLOG OPS-01의 추론 근거를 무효화한다** — "그 이후 업로드 시도: 감사·로그에 없음 → 아무도 시도하지 않아서"는 성립하지 않는다. 시도해서 실패해도 감사에는 안 남는다(§5-1).

### (부수) N12. 서버가 판정에 쓰는 술어를 응답에 싣지 않아, 화면이 대체 술어를 발명한다 — 3건, 게임 한정
`_present_players`(active + 90초)로 판정하면서 응답엔 `active`만 실어 화면이 그걸로 분모를 만든다 → **"모두 제출했습니다"가 영원히 안 뜬다**(F13). 같은 형태로 토너먼트 대진표는 `user_id` 없이 **이름 문자열**로 승패를 표현해 동명이인 양쪽에 '승' 배지(F16), 서버가 만들어 내려보내는 `replayed`는 프런트 소비처 **0건**(F17). WF4-N6("상태 전이 게이트가 응답 조립부에 인라인")의 거울상이라 **새 범주로 세지 말고 N6의 반대 방향 사례로 기록**하는 편이 맞다.

### 새 범주가 **아닌** 것 — 기존 R의 추가 사례로만 세라
- **성공 경로에만 refresh/알림** (H1 · F7 삭제 실패 · F42 quality_failed 침묵 · F32 me 쿼리) → **WF2-R5 / R2**. 다만 H1은 R5의 가장 비싼 사례(중복 데이터 생성).
- **영어 500 문구** (H2 전반부) → **WF2-R4**. 이미 FN-40(공지 PATCH) + UX-40(422판, 호출부 131개)이 있다. **신규는 "uploads.py에 OSError 번역이 아예 없다"는 코드 사실뿐.**
- **같은 규칙 두 벌** (F36 `affiliation`/`affiliationOf` — 두 함수 모두 자기가 정본이라 주석에 적음, 그리고 **이미 한 번 게임방에서 실제 화면 버그를 냈다**: MembersList.jsx:18-20의 자백) → **WF1-R1 / WF4-N2**.
- **부분 전파** (12라운드 CAS가 제출 4경로만 · 유령 필터 6/7 · sync 핸들러엔 가드 3개인데 verify엔 0개 · `_finish_vote`만 present 미적용) → **WF4-N2**. 다만 **N2의 정량적 격상은 기록할 만하다: 이번 60건 중 최소 6건이 "직전 3개 라운드의 자체 수정이 형제 경로에 안 닿은 자리"다.** 즉 이 저장소에서 **결함의 최대 단일 공급원은 이제 자기 수정 이력**이다.
- **죽은 코드·주석 부패** (F34 도달 불가 세션 만료 패널 — `showMenu`와 그 패널이 **같은 커밋 413b798의 자체모순** · F39 `SCOPE_TEXT` · F48 mail_send 주석 · F44 SlotLock 근거 부재) → **WF1-R4**.
- **클라가 서버 계약 사본을 안 가짐** (F8 드롭 경로 형식 검증 0 · F5 nginx↔미들웨어 집합 대조 없음) → **WF2-R3**.

---

## 4. 수렴 재판정 — 네 번째 라운드인데 아직도 새 범주가 나오는가

### 판정: **나온다. 그러나 예상된 자리에서만 나왔고, 그 자리가 이제 거의 비었다.**

`wf4_synthesis.md:96`이 남은 축을 이렇게 예고했다 — *"프로세스 밖·환경 5개: **시계 역행 · nginx 로그 · 낙관적 잠금이 폼 전체 저장에 없음 · 마이그레이션 중간 사망 · usage_events 보존** — **높음, 여기가 수렴 안 한 곳이다**"*. 이번 라운드는 그 예측의 **정확도를 검증한 라운드**다.

| 축 | 이번 영역 | 건수 | 새 근본 원인 | 예고돼 있었나 |
|---|---|---|---|---|
| 앱 논리(요청→응답) | 잡핸들러 | 10 | **0** | ✔ "낮음" — 적중 |
| 프런트 화면 | 첨부위젯 · lib기반 | 17 | **0** (전부 R2/R4/R5 사례) | ✔ "낮음, 착시 주의" — 적중 |
| 앱 논리(동시성) | 게임 | 10 | **0** (H3/H4는 12라운드 부분 수정의 잔재 = N2) | — |
| **권한 진입점** | CSV일괄 | 12 | **2 (N10·N11)** + Critical 1 | ✖ **미예고** |
| **프로세스 밖·환경** | 동시성마이그 | 11 | **3 (N7·N8·N9)** | ✔ "높음" — 적중, 5개 중 **3개 소진** |

**즉 축은 세 번째로 갈렸다.** 앱 논리·프런트 27건에서 새 범주 **0개**(WF4와 동일한 결과가 다른 6영역에서 재현됐다 — 이제 이 축의 수렴은 표본 2회로 뒷받침된다). 반면 환경 축은 예고대로 3개를 냈고, **예고에 없던 축이 하나 더 열렸다: 권한 게이트의 층위(N10)** — 이건 "웹 라우트는 다 봤다"는 커버리지 가정이 **라우트 단위 조사로는 잡히지 않는 결함**(같은 규칙의 라우터 간 비대칭)을 놓쳤기 때문이다. 라운드 유일의 Critical이 거기서 나왔다.

**그래서 아직도 나오는가 →** 그렇다. **그러나 남은 자리는 이제 셀 수 있다.**

| 남은 미조사 | 왜 남았나 | 새 범주 기대 |
|---|---|---|
| **nginx 로그 위생·회전** | wf4 예고 5개 중 미소진 | 중 — N1(환경 낙관) 계열일 가능성이 높아 **새 범주보다 사례** |
| **usage_events 보존** | wf4 예고 5개 중 미소진 | 낮음 — N3(시간 단위 정책)의 추가 사례 |
| **`versioning.py` 스냅샷 마스킹** | wf4가 "**예외 1개**"로 지목, 여전히 미확인 | **높음 — §2-3(secret 불변규칙)과 접하는 유일한 지점. 값이 들어가 있으면 기존 어떤 R에도 없는 Critical 축이다. 이 라운드도 안 열었다.** |
| **N10 전면 스윕**(라우터 간 게이트 비대칭) | 이번에 축이 열렸을 뿐 CSV 하나만 봤다 | **높음 — 같은 형태를 `_apply_admin_scope`에서 이미 하나 더 찾았다(별건).** 게이트를 가진 함수 전부에 대해 "호출부가 몇 개이고 각각 게이트를 지나는가"를 기계적으로 세면 끝난다 |
| **실환경 관측이 필요한 것 전부** | sudo/서버 접근 없음 | **판정 불가** — §5 |

**정지 규칙 제안:** 조사를 라운드로 더 도는 대신 **남은 2개(versioning · N10 스윕)만 시간상자**로 처리하고 나머지는 구현이 그 파일을 만질 때 흡수한다. 근거: 이번 라운드가 앱 논리·프런트 27건으로 새 범주 0을 두 번째로 실측했고, 폐기율 25/85(29%)가 WF4(24/69, 35%)와 비슷해 **조사 품질은 유지되는데 산출물의 신규성만 떨어지고 있다**. 그리고 이 라운드에서 가장 큰 발견(N2의 격상 — 결함의 최대 공급원이 자기 수정 이력)이 시사하는 것은 명확하다: **다음 라운드보다 지금까지 찾은 것을 "형제 경로까지" 고치는 쪽의 한계수익이 더 크다.**

---

## 5. 서버 확인이 필요해 미결로 남은 것

> 입력의 `미결` 배열은 비어 있었다. 아래는 **60건의 note에서 조사자들이 "서버 확인 필요"·"확인하지 않았다"로 명시한 것을 내가 모아 정리한 것**이다. 전부 ❌(내 환경에서 확인 불가) 또는 ⚠️(미확인)이며, 괄호 안이 30초 확인법이다.

**A. 판정을 뒤집을 수 있는 것 (먼저)**

1. **OPS-01의 근거 재검토** ❌ — BACKLOG는 "업로드 시도가 감사·로그에 없음 → 아무도 시도하지 않아서"로 추론했는데, **H2에서 업로드 실패는 감사에 안 남는 것이 확인됐다.** 추론이 무효다. → *nginx access log에서 `POST /api/tickets/*/attachments`의 4xx/5xx 유무*, `journalctl -u clovirone-web-assistant | grep uploads`. **uploads 디렉터리 쓰기 가능 여부(`sudo -u clovirone-web test -w <data_dir>/uploads`)** 도 아직 미관측(wf4에서도 sudo 부재로 못 했다).
2. **조직(organizations) 행 수** ⚠️ — 1개면 F25(org 범위 dry-run ↔ 실행 판정 불일치, "미리보기 전건 성공 → 실행 전건 실패")는 잠복, 2개 이상이면 **해당 범위 관리자는 CSV 가져오기를 영영 못 쓴다**. → `SELECT count(*) FROM organizations;`
3. **n8n notion-mapping 워크플로의 실제 응답 모양** ❌ — F40(verify가 배열/`{"error":…}`를 "무일치"로 오독해 verified 행을 지움)은 **n8n이 그 모양을 실제로 돌려주는가**에 걸려 있다. → n8n에서 해당 워크플로 1회 실행 후 응답 JSON 최상위 타입 확인.
4. **프로덕션 `alembic_version`** ⚠️ — BACKLOG:1598 기준 0052로 가정하고 F52를 High→Med로 내렸다. **0040 미만이면 다시 High다.** → `sqlite3 <db> "select * from alembic_version;"`

**B. 심각도·우선순위에 영향 (다음)**

5. **사용자 수와 `admin_scope` 분포** ⚠️ — F31(export 무제한 `.scalars().all()`)의 실피해와 F21(항상 `global`로 생성)의 현재 노출. → `SELECT admin_scope, count(*) FROM users GROUP BY 1;`
6. **SMTP 구성 여부 + `mail_deliveries` 행 수** ⚠️ — F43(QUIT 사후 실패로 최대 5통 중복 발송)을 "현재 실피해 0"으로 보고 Low로 내린 근거이자, F22(CSV 계정 임시 비번 전달 경로 없음)의 대안 성립 여부. → `SELECT count(*) FROM mail_deliveries;` + web.env에 SMTP 키 존재 여부(root로).
7. **서버 시계 동기화 상태** ❌ — N7 3건 전부의 발동 조건. → `timedatectl`(NTP synchronized / 설정된 서버) + `journalctl -u systemd-timesyncd | grep -i step`으로 과거 스텝 이력.
8. **배포된 nginx conf의 `client_max_body_size` location 집합** ⚠️ — F5. 미들웨어 `_UPLOAD_ROUTE_RES` 4개와 **집합이 일치하는가**, 특히 `/api/me/avatar`(크기 테스트가 없는 유일한 라우트). → 서버의 `/etc/nginx/.../clovirone-web-assistant.conf`와 `middleware.py:85-90` 대조.
9. **`game_room_members.active=0` 행이 실제로도 0인가 + 방·이벤트 규모** ⚠️ — H4·F13은 로컬 DB 7행 기준이다. F18(`since=0` 전량 재전송)의 실비용도 여기 걸린다. → `SELECT active, count(*) FROM game_room_members GROUP BY 1;`, `SELECT room_id, count(*) FROM game_events GROUP BY 1 ORDER BY 2 DESC LIMIT 5;`
10. **첨부 DB 행 ↔ 디스크 파일 불일치 현황** ⚠️ — F9(이미지 404 폴백 UI 없음)와 F3(고아 스윕 유예가 mtime 기준)의 실제 노출. → `ticket_attachments`의 `stored_name`과 uploads 디렉터리 파일 목록 diff, + 고아 파일 개수.

**C. 브라우저 실렌더 미확인 (코드로만 판정한 것)**

11. F9 첨부 이미지 404 시 실제 화면(깨진 아이콘) · F32/F34 **세션 만료 상태에서 사이드바가 사라지고 본문 ErrorState의 '로그인 화면으로' 버튼이 실제로 보이는가**(F34의 심각도를 Med→Low로 내린 근거가 이것이다) · F60 카운트다운 스큐. → 프로덕션에서 로그인 후 DB에서 세션 행 삭제 → 화면 관찰 30초.

**D. 관측 권한 자체가 Blocker (wf4 §4-3의 반복)**

12. 위 1·7·8은 **root/sudo 없이는 확인 불가**다. wf4가 이미 *"sudo 없는 조사 세션을 더 돌리면 이 축은 계속 절반만 열린다 — 사용자에게 필요한 것은 조사 예산이 아니라 관측 권한이다"* 라고 적었고, **이번 라운드도 같은 이유로 같은 3건을 미결로 남긴다.** 이 상태가 유지되면 N7·N9의 실환경 판정은 다음 라운드에도 불가능하다.