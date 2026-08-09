# 6영역 조사 종합 — 45건 (Critical 2 / High 3 / Med 16 / Low 24, 반증 폐기 24건)

> 이 종합에서 **내가 직접 원문을 재확인한 것**: `scripts/install-clovirone-web-assistant.sh:145-152`(uploads 부재) · `scripts/backup-cron.sh:12,24-35` · `app/audit/anomalies.py:49-67` · `app/core/worker_lock.py:108-132` · `app/worker_main.py:76-88` · `docs/wf3_gaps.json`(미조사 38영역 중 이번 라운드가 소비한 10개 → 잔여 정확히 28개) · `docs/wf3_handoff.md` §1 수렴 판정.
> 상태 라벨: **[확인]** = 증거를 직접 봤다 / **[미확인]** = 했지만 결과를 못 봤다 / **[확인불가]** = 이 환경에서 볼 수 없다.

---

## 1. Critical / High 전수 (5건)

| # | 심각도 · 영역 | 문제 | 근거 | 고칠 지점 |
|---|---|---|---|---|
| **C1** | **Critical** · uploads 배치 | 2026-08-07 privhelper StateDirectory 사고로 데이터 디렉터리가 root 소유가 됐고 **복구 chown이 비재귀**여서 `uploads/` 하위만 잔재로 남았다. installer의 `install -d -o $SVC_USER` 목록에 `$VAR_DIR/uploads`가 **없어** 이후 업그레이드가 돌아도 영구히 정규화되지 않는다. `save_upload`는 mkdir/write_bytes에 `except OSError`가 없어 board·ticket·team_chat·avatar **4 네임스페이스 첨부가 전부 500**이 된다. | **[확인]** journal: `Aug 07 07:07:26 privhelper 시작` → `07:07:31 worker.lock PermissionError` 재시작 4회 · sudo 로그 `Aug 07 07:10:02` 복구 명령에 `-R` 없음 · installer:150-151 목록에 uploads 없음(내가 원문 재확인) · DB·exports·locks만 정상인 **비대칭이 이 목록으로 설명된다** · 업로드 4경로 `except OSError` 0건 · health에 `W_OK` 프로브 0건. **[확인불가]** 지금 실제로 업로드가 실패하는지 — sudo 없음, 8/6 이후 첨부 POST 0건이라 실패가 **관측된 적은 없다**(원 조사의 "지금 전부 실패한다"는 추론). | ① `chown -R clovirone-web:clovirone-web /var/lib/clovirone-web-assistant` ② `install-clovirone-web-assistant.sh:150-151` 목록에 `$VAR_DIR/uploads` 추가 + 매 실행 재귀 정규화 ③ `/readyz`에 data_dir 쓰기 프로브. **사용자 30초 확인:** `sudo -u clovirone-web test -w /var/lib/clovirone-web-assistant/uploads && echo WRITABLE \|\| echo NOT_WRITABLE` |
| **C2** | **Critical** · 운영내구성 | `WorkerLock.acquire()`가 `os.open`의 **FileExistsError만** 잡는다. EACCES/ENOSPC/EIO는 `main()`을 관통해 `raise SystemExit(main())`이 traceback으로 죽고(exit≠0) systemd가 3초 뒤 재시작 → 같은 실패 → **상한 없는 루프**. | **[확인]** worker_lock.py:113-114가 유일 핸들러(내가 원문 재확인) · worker_main.py:279 `if not lock.acquire()`, :598 `raise SystemExit(main())` · 유닛 `Restart=on-failure` / `RestartSec=3` / StartLimit 미지정 → **RestartSec=3이면 즉사해도 10초 창에 최대 3.3회라 기본 burst 5에 구조적으로 도달 불가**(추정 기동시간에 의존하지 않는 논증) · `patch("os.open", side_effect=PermissionError)` 재현 성공. **원 조사가 놓친 두 번째 구멍:** FileExistsError 분기 안의 `self._write(payload)`(:121)도 무방비 — 락 파일이 이미 있는 **정상 재시작 경로**에서 ENOSPC가 같은 곳으로 떨어진다. | `acquire()`를 `except OSError`로 넓혀 '리스 경쟁'과 '파일시스템 고장'을 분리, 후자는 백오프 재시도 · 유닛에 `RestartSec` 상향 + `StartLimitIntervalUSec` 확대(또는 `RestartSteps`/`RestartMaxDelaySec`). |
| **H1** | **High** · 백업범위 | 보존이 "7일"이 아니라 **"7개"**다. 배포 백업이 upgrade 스크립트를 통해 같은 스크립트·같은 이름 규칙으로 생성돼 **일일 백업과 카운터 7칸을 공유**한다. 배포가 잦은 날 하루에 일주일치 복원 지점이 증발한다. | **[확인]** `backup-cron.sh:12` 주석 원문 `KEEP_PLATFORM=7 # …(일 단위 실행 기준 7일)` — **코드가 보장하지 않는 것을 주석이 보장한다고 적었다**(내가 재확인) · :24-35 prune이 이름 정규식으로 전부 수집 후 `count-KEEP_PLATFORM`개 삭제 · 서버 `/var/log/clovirone-backup.log` 8/8 03:30 prune **1회에 10개** 삭제(8/3~8/7 **일일 5일치 전부 포함**), 8/9에 4개 추가 · sudo 로그의 upgrade 5회 + cron 2회 = 정확히 7 → **가장 오래된 복원 지점 = 2026-08-07 19:07**. 이 라운드에서 유일하게 **로그·sudo 타임스탬프 두 갈래로 교차검증**된 항목. | 배포 백업에 접두어(`pre-upgrade_<ts>`)를 주고 KEEP 분리, 또는 개수 대신 나이 기준(`find … -mtime +7`). 같은 커밋에 backup 스크립트 끝의 `PRAGMA integrity_check`(Med #18)를 얹으면 "검사 시점이 장애 당일"도 함께 닫힌다. |
| **H2** | **High** · user_cli / 감사 | 이상 탐지의 `SENSITIVE_ACTION_PREFIXES`에 `"user."`만 있어 **`cli.user.*`가 하나도 매칭되지 않고**, `CRITICAL_ACTIONS`에도 `cli.user.set_role`이 없다. 5개 규칙 중 off_hours·critical_action·new_actor_action **3개가 CLI 계정 조작을 전량 놓친다** — 그런데 관리자 수명주기의 다수가 CLI를 지난다(ADM-01: 잠금해제 웹 0/CLI 13, 생성 2/15). | **[확인]** anomalies.py:49-67 원문 재확인(prefixes 9개에 `cli.` 없음, CRITICAL_ACTIONS 4개) · 상수 임포트 후 매칭 실행: `cli.user.reset_password/unlock/disable/create/archive/set_role` **6/6 False** · 같은 문자열이 `health.CRITICAL_ACTIONS_MATCH`에서는 True · **형제 모듈이 같은 함정을 17줄 주석으로 설명하고 이미 고쳐 놨다**(health/service.py:51-60) · 고정 테스트 0건(`grep tests/` → 0). 반증 시도 3종(소비측 보정·테스트·의도 주석) 전부 없음. | 두 모듈이 **한 목록**(`app/audit/actions.py`)을 공유하게 한다 — 같은 사실이 두 벌이면 이 상태가 재발한다. 최소 조치: prefixes에 `"cli."` 추가 + CRITICAL 매칭을 health와 동일하게. 회귀는 `tests/security/test_audit_anomalies_scope.py`. |
| **H3** | **High** · 운영내구성 | 하트비트 스레드에서 `beat_liveness()`는 예외를 전부 가두는데 **바로 다음 줄 `lock.renew()`는 무방비**다. `renew()→_write()→write_text()`의 OSError가 스레드 밖으로 나가 **데몬 스레드만 조용히 죽고**, `stop_event`는 꺼진 채라 본 루프는 계속 돈다. 90초 뒤 대시보드는 '워커 중단'이라 말하고(살아 있는데), 120초 뒤 리스가 만료된다. | **[확인]** worker_main.py:83 `beat_liveness`(내부에서 삼킴) vs :84 `if lock is not None and not lock.renew()`(보호 없음) — 원문 재확인 · worker_lock.py:150→:176 `write_text` 무보호 · `_write`를 `OSError(28)`로 바꿔 `run_heartbeat_loop` 호출 → `RAISED OUT OF THREAD TARGET`, `stop_event set? False` 재현 · **의도 면제 아님**: docstring(:77-81)은 '갱신 실패(=남이 가져갔다)' **False 경로에만** 의도를 적었고 예외 경로는 침묵. | `renew()` 호출을 `try/except OSError`로 감싸 '리스 상실(False)'과 '갱신 실패(예외)'를 구분, 후자는 재시도 초과 시 `stop_event` + **실패 종료코드**. 스레드 생존을 본 루프가 감시하는 장치도 없다(현재 0). |

**표에서 읽어야 할 것:** 5건 중 **C1·H1 두 건은 저장소 코드만 읽어서는 나오지 않는다** — journal·sudo 로그·백업 로그·`stat`이 있어야 나왔다. 이 사실이 §4 수렴 판정의 핵심 근거다.

---

## 2. 영역별 한 줄 판정

| 영역 | 건수 (C/H) | 판정 | 예산 권고 |
|---|---|---|---|
| **team_chat** (1,953줄, 제품 최대 미감사 백엔드) | 11 (0/0) | **상대적 강점.** gaps가 High로 지목한 두 가설이 **둘 다 반증됐다** — DM 이미지 IDOR 경계는 실재하고(`ensure_access`를 서빙 전에 호출, 403→404), 최대 미감사 모듈에서 Critical/High가 **0건**이다. 남은 11건은 자기 목록만 망가지는 게이트 누락 3건 + 같은 사실을 두 표로 보는 문제 몇 건. | **최소.** 유일하게 화면에서 도달 가능한 '내 팀 방 나가기'(Low #3)만 처리하고 나머지는 백로그. |
| **core/uploads.py** | 5 (1/0) | **코드는 강점, 배치는 최약점.** traversal·네임스페이스·매직바이트·`content_disposition` 화이트리스트는 무결점이고 polyglot도 못 뚫는다. 그런데 그 코드가 쓰는 **디렉터리 소유권이 두 달째 깨진 채 아무도 모른다.** 결함이 코드가 아니라 **코드 밖**에 있다. | **최우선(C1 한 건).** 나머지 4건은 Low·Med이고 한 줄 수정. |
| **백업범위** | 3 (0/1) | **약점.** 유일하게 실측 로그로 교차검증됐고 결과가 나쁘다 — 복원 지점이 문서가 약속한 7일이 아니라 **하루 반**이다. 게다가 보관된 산출물의 무결성을 **자동으로** 확인하는 절차가 없다(검사 시점 = 장애 당일). | **높음.** 3건이 한 스크립트(`backup-cron.sh` + `backup-*.sh` 끝 2줄)에 모인다. |
| **cli/user_cli.py** (390줄) | 7 (0/1) | **체계적 약점.** 관리자 수명주기의 다수가 지나는 표면인데 **정책·감사·문서 3축 전부에서 웹의 이등시민**이다: 정책(비밀번호·도메인)을 안 받고, 이상탐지가 `cli.*`를 못 보고, 최후 복구 경로 문서(RUNBOOK #7)의 명령이 **인자 형식만으로 rc=2로 죽는다.** | **높음.** `main()`에서 `SettingsCache(...).load(db)` 한 번 부르면 Med 2건이 같이 닫히고, 감사 목록 공유 1건이 H2를 닫는다. |
| **core/sync_prune.py** | 8 (0/0) | **설계는 강점, 단언이 약점.** 3개 호출부가 `refused`를 **3/3 전부** 읽고 바닥도 실제로 작동한다. 문제는 주석·docstring이 실제 보장보다 넓게 단언한 것이고(48줄 "최악은 막는다"는 keep=∅에만 참), **그 잘못된 모델이 테스트 주석 2곳에 복제**됐다. 실피해 조건은 신규 설치·소규모 워크스페이스 한정(오늘 로컬 document_cache=104, ticket_cache=1056). | **중간(문서 우선).** 주석 3곳 정정 + 문서 소프트 프룬(0047이 이미 예고)이면 Med 4건 중 3건이 닫힌다. |
| **운영내구성** (worker·디스크·자산 핫스왑) | 11 (1/1) | **최약점.** 유일하게 Critical+High가 **같은 원인**에서 나왔다. 워커가 죽는 경로가 3개(무한 재시작 루프 / 스레드만 조용히 사망 / 오탐으로 exit 0 후 영구 정지)이고, **죽어도 사람에게 가는 능동 경로는 0건**이다 — 같은 저장소에 정답 패턴(백업 실패 → 메일 + 인앱)이 이유까지 적힌 채 있는데 blast radius가 더 큰 쪽이 못 받았다. | **최우선.** C2+H3가 `worker_lock`/`worker_main` 두 파일 4줄이고, `/readyz` 쓰기 프로브 하나가 C1과 Med 2건을 동시에 관측 가능하게 만든다. |

---

## 3. 이번에 새로 드러난 근본 원인 (기존 WF1 R1~R7 · WF2 R1~R6에 **없던 것만**)

### N1. "파일시스템은 실패하지 않고 디스크는 무한하다"는 가정이 코드·설치·감시 3계층에 걸쳐 있다 — **Critical 2건 포함 9건**
**규칙:** *바이트를 쓰는 모든 경로는 (a) 쓰기 전에 여유를 보고 (b) `OSError`를 잡고 (c) 그 상태가 readiness에 반영돼야 한다.*
포함: C1(installer 디렉터리 목록 + `save_upload` 무방비) · C2(`acquire`가 FileExistsError만) · H3(`renew` 무방비) · Med(업로드 용량 쿼터 0 · `disk_usage` 소비처 0 · `/readyz`가 `SELECT 1` 하나 · 백업이 같은 볼륨에 DB 2배 요구) · Low(아바타 unlink가 커밋 전 · sessions 무한 잔류).
**왜 기존 R이 아닌가:** R1~R7·R1~R6은 전부 **요청→응답 안쪽**(스코프·문구·계약·술어)에서 뽑은 것이다. 이 묶음은 전부 **프로세스 밖 자원**이고, 실패가 앱 논리로는 관측조차 되지 않는다. `shutil.disk_usage`는 저장소 전체에서 `health/service.py:92` **한 곳**에만 있고 그 값으로 거부하는 경로는 **0건**이다.
**가장 싼 수정:** `health/service.py:92`를 공통 가드로 뽑아 업로드·백업·export 진입점에서 fail-closed + `/readyz`에 data_dir 쓰기 프로브. **이 한 프로브가 C1을 두 달간 숨겨 준 healthz 200을 없앤다.**

### N2. 같은 함정을 **이미 고친 형제가 저장소 안에 있는데** 수정이 전파되지 않았고, 그 주석이 다음 사람을 안심시킨다 — **High 1건 포함 6건**
**규칙:** *같은 사실이 두 벌이면 한쪽만 고쳐진다. 고칠 때 두 벌을 한 벌로 합치지 않으면 그 수정은 반쪽이다.*
포함: H2(`anomalies` vs `health.CRITICAL_ACTIONS_MATCH` — **17줄 주석으로 함정을 설명하고 자기만 고침**) · Med(`tenant_config.py:196-206`이 '저장 안 한 키도 기본값으로 항상 존재' 함정을 **진단에서만** 고쳐 → 진단은 "설정됨(env)", 집행은 검사 생략 = **진단과 집행이 반대로 말한다**) · Med(웹은 `effective_settings`를 넘기고 CLI는 안 넘김) · Low(`projects/models.py:195`는 소프트 프룬을 정확히 적고 `tickets/models.py:136`은 틀리게 적음 · `board`는 첨부 업로드 감사를 남기고 채팅만 안 남김 · `retention.py:265-269`가 경고한 위험의 **거울상**이 `profiles/router.py:273`에 있음).
**왜 기존 R이 아닌가:** WF2-R1/R2/R6은 "규칙이 있는데 **안 부른다**"이다. 이건 "**이미 발견하고 고쳤는데 절반만 고쳤고, 그 사실이 주석으로 남아 완료처럼 보인다**" — 시간축이 다르고, 탐지 방법도 다르다(호출부 grep이 아니라 **형제 모듈 diff**로만 나온다).

### N3. 시간 단위 정책이 개수·비율로 구현돼, 다른 생산자가 끼어들면 조용히 무너진다 — **High 1건 포함 4건**
**규칙:** *"N일 보존"은 개수로 구현하지 않는다. 같은 저장소에 다른 주기의 생산자가 쓰면 정책이 사라진다.*
포함: H1(`KEEP_PLATFORM=7`이 배포 백업과 슬롯 공유 → 7일이 하루 반) · Med(`sync_prune` 비율 바닥이 **회차 단위·무상태**라 하드 삭제로 분모가 10 밑으로 내려가면 바닥이 스스로 꺼진다) · Med(`MIN_ROWS_FOR_RATIO_GUARD` 경계 9↔10에서 `keep≠∅`인 전량 삭제가 통과) · Low(`sessions`가 유일하게 보존 상한 없는 인증 표).
**왜 기존 R이 아닌가:** RET 절은 "보존 **대상 표**가 빠졌다"는 목록 문제였다. 이건 **단위 불일치**(기간 vs 개수, 누적 vs 회차)라 목록을 아무리 채워도 안 닫힌다.

### N4. 두 번째 진입점(CLI)은 웹의 정책 배선을 하나도 물려받지 않는다 — **High 1건 포함 7건**
**규칙:** *같은 service 함수를 부르는 것은 같은 정책을 적용받는다는 뜻이 아니다 — 정책은 **인자로** 흐른다.*
포함: H2(감사 이상탐지 사각) · Med(비밀번호 정책 미적용 → 12자/3종 기본값 고정, registry의 "즉시 적용"이 거짓) · Med(도메인 제한 미적용) · Med(RUNBOOK #7·USER_LIFECYCLE의 **CLI 예시 전부**가 rc=2 + DATABASE_URL 배선 없음) · Low(before/after 스냅숏 누락 · verify-notion 감사 0 · admin_scope 커맨드 부재).
**왜 기존 R이 아닌가:** `user_cli` docstring의 "웹과 같은 service 층을 쓰므로 동작이 갈라지지 않는다"는 **부분적으로 참**이다(권한 가드는 실제로 돈다 — handoff가 확인). 갈라지는 것은 **service 함수가 인자로 받는 정책 컨텍스트**(`effective_settings`·`actor_id`·스냅숏)다. `grep 'effective_settings\|SettingsCache' app/cli/user_cli.py` → **0건**. 기존 조사가 웹 라우터만 봤기 때문에 이 축 자체가 없었다.

### N5. 클라이언트는 장수(長壽) 프로세스인데, 배포는 그 수명을 모른다 — **4건**
**규칙:** *`rsync --delete`는 열려 있는 탭의 계약을 깬다. 캐시 버스팅은 '새 주소를 받는' 문제를 풀지 '옛 주소가 사라지는' 문제를 풀지 않는다.*
포함: Med(`AdminRoutes` registry dynamic import에 `.catch` 없음 → REGISTRY 라우트 **25개**가 영구 로딩 스켈레톤, ErrorBoundary 밖) · Low(정적 교체 경로가 둘인데 열린 탭에 대한 결과가 **반대** — stage는 덧씌우기, 업그레이드는 `--delete`) · Low(`React.lazy` 청크 404가 rejected를 영구 캐시 → reload 외 탈출구 없음, 서버 기록 0) · Low(`BUILD_STAMP.json`이 배포돼 있는데 **런타임에 아무도 읽지 않는다**).
**왜 기존 R이 아닌가:** `CLAUDE.md` §6이 "사용자에게 새로고침을 부탁하지 않는다"고 단언하는데 **전체 업그레이드 경로에 대해 거짓**이다. 문서·배포·프런트 세 곳에 걸친 수명 불일치라 어느 한 R로도 안 잡힌다.

### (부수) N6. 상태 전이 게이트가 응답 조립부에 인라인돼 있어 프런트만 집행한다 — 3건, 저위험
서버가 `can_hide`/`can_leave`를 **계산해서 내려주면서** POST 핸들러는 그 판정을 재사용하지 않는다(`hide_room`은 `is_global`만, `leave_room`은 1:1을 안 막는다 — 같은 파일의 `disband_room`은 정확히 같은 함정을 알고 409로 막아 뒀다). 불변규칙 §2-5의 새로운 변종(권한이 아니라 **상태 전이**)이지만, 피해가 전부 자기 자신에게만 미쳐 Low로 둔다. `ensure_can_manage_room`과 같은 관용으로 판정과 계산을 한 함수에 묶으면 3건이 함께 닫힌다.

### 새 범주가 **아닌** 것 (기존 R의 추가 사례로만 세라)
- 멘션 후보표 2벌 · 안읽음이 내 글을 셈 · `_mention_candidates`의 org 인자 누락 → **WF2-R1/R2**
- `has_more=true`인데 truncated=False · prune 거부 사유가 어느 화면에도 없음 · 워커 중단 능동 알림 0 → **WF2-R5**(부분 성공/판정 불가가 성공 신호). *단 "능동 알림 경로 부재"는 R5의 가장 비싼 사례다 — 기록은 정확한데 사람에게 가는 경로가 없다.*
- `since=0` 계약 드리프트 · `pruned_count` 주석 · `{ratio:.0%}` · sync_prune 손실 목록 낡음 → **WF1-R4**(약속-이행 불일치)
- `client_message_id` 중복 제거 키 · 그룹 정원 50 off-by-one · `sanitize_filename`의 `.strip(".")` → 단독 위생

---

## 4. 수렴 재판정 — "새 범주가 계속 나오는가"

### 판정: **축마다 답이 다르다.** 앱 논리·프런트 축은 수렴했고, **프로세스 밖·환경 축은 수렴하지 않았다** — 그리고 이번 라운드가 그 축을 처음 열었다.

**결정적 증거는 이번 라운드 안에 있다.** 같은 6영역, 같은 조사자, 같은 방법인데 축별로 결과가 정확히 갈렸다.

| 축 | 이번 라운드 영역 | 건수 | 새 근본 원인 |
|---|---|---|---|
| 앱 논리(요청→응답) | team_chat · sync_prune | **19건** | **0개** — 전부 기존 R1/R2/R4/R5의 추가 사례거나 단독 위생 |
| 두 번째 진입점 | user_cli | 7건 | **1개**(N4) + N2 1건 |
| 프로세스 밖(파일시스템·systemd·배포·보존) | uploads 배치 · 백업범위 · 운영내구성 | 19건 | **4개**(N1·N2·N3·N5), **Critical 2건 전부** |

`docs/wf3_handoff.md` §1의 "새 범주 발견의 의미에서는 수렴했다"는 판정은 **틀리지 않았지만 범위가 잘못 적혔다.** 그 판정의 근거였던 WF1·WF2 두 워크플로는 **둘 다 앱 논리·프런트 축**이었고, 그 축에서는 이번에도 새 범주가 0개다. 반면 축을 바꾸자 즉시 5개가 나왔다. 즉 **"수렴"은 표본이 아니라 축의 성질이었다.**

보강 증거 하나 더: 이 제품의 **Critical 4건이 4/4 모두 프로세스 밖에서 나왔다** — SYS-01(TLS 경로) · DEPLOY-01(배포 스크립트) · C1(디렉터리 소유권) · C2(systemd 재시작 루프). 앱 논리 축에서 나온 Critical은 지금까지 **0건**이다.

### 남은 28개를 축으로 갈랐을 때

| 축 | 잔여 | 목록 | 새 범주 기대 |
|---|---|---|---|
| **앱 논리(백엔드)** | **11** | notion_console(H) · tenant_config(M) · notion_mapping(M) · jobs/handlers 5개(M) · people(M) · **versioning(M)** · etag+presence(M) · notion_blocks+source_registry(M) · games(M) · admin/rbac(L) · policies(L) | **낮음.** 이 영역들의 결함 가설은 gaps 원문 스스로가 "R1 배선 누락 · R5 부분 성공 · IDOR의 재탕"이라고 적고 있다. **예외 1개: `versioning.py`** — "스냅샷은 마스킹하지 않는다"가 §2-3(secret 불변규칙)과 접하는 **유일한 지점**이고, 값이 들어가 있으면 그건 기존 어떤 R에도 없는 Critical 축이다. |
| **프런트 화면** | **12** | 게임방(H) · 중첩 표면(H) · 티켓 첨부(H) · UsersBulk(H) · src/lib 6모듈(M) · 셸 부품(M) · CommentThread(M) · charts(M) · settings 하위(M) · ChatRoom 관리(M) · reduced-motion(L) · AI 본문(L) | **낮음, 그러나 착시 주의.** 여기서 나올 "새 범주"는 대부분 **새 프로브를 만들어서 생긴 계측 축**이다(중첩 모달 z-index·1.2초 폴링 비용·reduced-motion). handoff §1이 말한 "프로브를 만들면 범주는 무한히 늘어난다 = 정지 규칙이 없다"가 정확히 이 12개에 해당한다. 결함 **종류**는 R1~R7로 이미 포화. |
| **프로세스 밖·환경** | **5** | 시계 역행(monotonic 0건) · nginx 로그 위생·회전 · **낙관적 잠금이 폼 전체 저장에 없음** · 마이그레이션 중간 사망 상태 · usage_events 보존 | **높음 — 여기가 수렴 안 한 곳이다.** 시계 역행은 N1과 정확히 같은 부류("환경은 얌전하다")이고 사전 근거(monotonic 0건)가 이미 있다. 마이그레이션 중간 사망은 **R5 × N1 교차**. 낙관적 잠금은 이번 45건에 **동시 편집 축이 하나도 없었다** — 유일하게 스친 것이 `client_message_id` Low 1건이다. |

### 그래서 무엇을 할 것인가

1. **조사를 무한정 이어가지 말되, 축 하나는 마저 열어라.** 남은 28개 중 **5개(프로세스 밖) + versioning 1개, 총 6개만** 시간상자로 처리하고, 나머지 22개는 handoff §3의 원칙대로 **구현이 그 파일을 만질 때 흡수**한다. 근거: 같은 라운드에서 앱 논리 축 19건이 새 범주 0을 냈다는 것이 그 축의 한계수익을 실측한 값이다.
2. **handoff §3 단계 9의 시간상자 대상을 교체하라.** 현재 지정된 4개 중 **`team_chat`은 이번에 소비됐고(11건, C/H 0) `tenant_config`도 절반 소비됐다**(Med #22가 `tenant_config.py:190-215`를 직접 짚었다). 남길 것은 `notion_console` · `jobs/handlers` 2개이고, 여기에 `versioning` + 프로세스 밖 5개를 더한 **7개**로 재구성하는 것이 맞다.
3. **방법론 제약을 먼저 풀어라(Blocker).** C1·H1은 저장소 읽기로는 나오지 않았다 — journal·백업 로그·`stat`이 있어야 나왔다. 남은 5개 중 **시계 역행·nginx 로그·마이그레이션 중단 3개는 같은 관측을 요구**하는데, 이번 세션은 `sudo: a password is required`로 C1의 최종 관측(`test -w uploads`)조차 못 했다. **sudo 없는 조사 세션을 더 돌리면 이 축은 계속 절반만 열린다.** 사용자에게 필요한 것은 조사 예산이 아니라 관측 권한이다.
4. **품질 신호(참고):** 이번 라운드는 45건을 남기며 **24건을 반증 폐기**했고(35%), 남긴 것 중에서도 원 보고 대비 심각도를 내린 것이 9건, 기전 자체를 뒤집은 것이 2건(`admin_scope`는 "빈 목록"이 아니라 **조용한 범위 이동**, `sync_prune`의 fix_hint는 문서화된 결정을 뒤집는 제안이었다)이다. **이미 열린 축에서 조사를 한 번 더 도는 것의 한계수익이 낮다**는 판단은 이 폐기율로도 뒷받침된다.