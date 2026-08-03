# TEST SCENARIOS — 테스트 스위트 개요

## 실행 방법

```bash
.venv/Scripts/python -m pytest              # 기본: smoke 제외 전체 (pytest.ini addopts)
.venv/Scripts/python -m pytest -m security  # 마커 선택 실행
.venv/Scripts/python -m pytest tests/unit/test_scheduler_tick.py -k misfire
cd frontend && npm test                     # 프런트(React) vitest 스위트 — 별도 묶음
```

플랫폼 pytest와 프런트 vitest는 서로 다른 러너다. 개수는 문서에 박지 않는다
(여러 갈래가 동시에 추가해 매 세션 움직인다). 세는 법은 `CLAUDE.md` §1 참조.

마커(`pytest.ini`): `unit`(빠른 격리), `integration`(app factory 대상 API 테스트),
`security`, `regression`(고정 결함 회귀), `smoke`(**라이브 인스턴스 필요 — 기본
deselect**).

## 테스트 인프라 (`tests/conftest.py`)

- **DB 전략**: 세션당 1회 `alembic upgrade head`로 템플릿 SQLite 파일 생성 →
  테스트마다 파일 복사. 마이그레이션이 매 실행 검증되면서도 빠르다.
  `:memory:`는 쓰지 않는다 — WAL·다중 커넥션 동작을 운영과 동일하게 유지
- **주입 페이크** (`tests/fakes/`): `FakeClock`(시간 제어),
  `FakeHTTP`(httpx transport 대체 — 실제 네트워크 없이 아웃바운드 검증).
  `create_app(settings, clock=..., outbound_transport=...)`로 주입

## 레이아웃과 핵심 시나리오

### tests/unit — 순수 로직

| 파일 | 검증 내용 |
|---|---|
| `test_password_policy.py` | 12자/3종 정책, 임시 비밀번호 생성 |
| `test_config.py` | Settings 환경변수 파싱 |
| `test_db_pragmas.py` | WAL/busy_timeout/foreign_keys PRAGMA 적용 |
| `test_secret_refs.py` | 참조 이름 검증, SecretValue 마스킹(repr/str/format=`***`) |
| `test_audit_masking.py` | password/secret/token/api_key 재귀 마스킹 |
| `test_jobs_repository.py` | enqueue/backoff(5·10·20s)/idempotency/stuck recovery |
| `test_cron.py` | preset, timezone(Asia/Seoul), **DST 전환** next-fire 계산 |
| `test_scheduler_tick.py` | due 평가, **misfire skip/run_once**, 동시성 skip, idempotency 키 |
| `test_runner_circuit.py` | **5회 연속 실패→degraded+300s open**, 성공 시 자동 복구 |
| `test_document_quality.py` | 빈 제목/짧은 본문/소스 0건/민감정보/notion 링크 게이트 |
| `test_sqlite_backup.py` | Backup API·체크섬·integrity_check·temp restore |
| `test_ticket_create.py` | 티켓 생성: 제목 조합/기본 status, project 필수 게이트, 담당자 해석, priority/마감 검증, 설명 markdown→Notion 블록 |
| `test_ticket_edit.py` | 티켓 수정: 소유자와 미할당만 편집(+bypass 역할), 담당자 해석(미검증/미매핑 거부), claim(매핑 필요, 타인 티켓 금지) |
| `test_my_tickets.py` | 내 티켓/미할당 필터(verified notion_id 기준), 종료 상태 제외, 활성 검증 담당자만 노출 |
| `test_board_service.py` | 게시판 서비스: 업로드 sniff, 파일명 sanitize, 용량/타입 거부, 카테고리/제목 검증, 1단계 답글 강제, soft delete 캐스케이드, 반응 유니크 |
| `test_team_docs_sync.py` | 문서 미러 동기화: 캐시 채우기와 이름 해석, taxonomy 분류, truncated 시 prune 생략, 제거분 prune, 실패 시 마지막 캐시 유지 |
| `test_dev_report.py` | 개발자 월간 리포트: month range 검증, 개발자별 집계(이름, 연체), 미매핑 assignee placeholder, 토큰 없음/Notion 401→not configured |
| `test_runner_health_sweep.py` | 러너 헬스 스윕: 도달성 up/down, health_url 없으면 up, strict 2xx, disabled skip, 예외 격리 |
| `test_chat_attachments.py` / `test_chat_extract_text.py` | 채팅 첨부 검증, 본문 텍스트 추출 |

### tests/integration — API 레벨 (app factory + TestClient)

- **인증**: 로그인 성공/실패/잠금(`test_auth_login.py`), 비밀번호 변경 시 세션 회전·
  타 세션 폐기(`test_auth_change_password.py`, `test_auth_sessions.py`)
- **채팅**: 대화/메시지 CRUD·소유권(`test_chat_api.py`), 핸들러의 n8n 왕복·재시도
  (`test_chat_handler.py`), **미매핑 1인칭 요청 safe-refusal**(`test_chat_notion_refusal.py`)
- **Job 큐**: `test_job_claim_race.py` — **다중 스레드 동시 claim 경쟁에서 이중 claim
  0건** 증명, `test_worker.py` — run_once/sweep/on_failure/graceful 흐름
- **레지스트리**: integrations/runners/workflows API — disabled 생성 기본,
  버전/롤백, 도달성 테스트 (`test_*_api.py`)
- **콘텐츠**: prompts/policies 수명주기 전이·publish 자동 archive·diff·rollback,
  templates 참조 검증
- **스케줄**: 생성 검증, enable 승인 게이트(202), dry-run/run-now, run retry
  (`test_schedules_api.py`)
- **승인**: 생성→approve 실행/reject/만료/자기 승인 금지 (`test_approvals.py`)
- **문서 자동 생성**: generate→preview→품질 게이트→모드별 분기 (`test_documents_api.py`)
- **문서 탭(team_docs)**: 목록 검색/필터/정렬, 즐겨찾기, 상세(recent 기록), 필터 목록, 새 문서
  생성(쓰기 매핑 없으면 403), operator 동기화(Notion 없이 graceful), 플래그 OFF 숨김
  (`test_team_docs_api.py`)
- **게시판(board)**: 생성/목록/상세/댓글/반응 전체 흐름, 1단계 답글 강제, 검색과 카테고리 필터,
  작성자만 편집/삭제, moderator 편집과 pin, 첨부 업로드/서빙/타입 거부(+auth 요구), 부모 삭제 시
  답글 숨김, 내 활동 위젯, 플래그 OFF 숨김 (`test_board_api.py`)
- **놀이(games)**: 7종 서버 확정 로직 — 랜덤추첨 승자, 팀 균등 분할, 사다리 1인 1결과,
  퀴즈 라운드 채점/정답 숨김/공개 후 응답 차단, 가위바위보 판정과 무승부, 숫자눈치 최소 유일값,
  빠른투표 집계와 중복표, 호스트만 시작/이탈 시 재배정, 관전, AI 퀴즈 생성(플래그 ON/OFF, CSRF,
  유효 문제 0건 422), 플래그 OFF 숨김 (`test_games_api.py`)
- **Notion 매핑**: verify 1건/0건/충돌, 수동 매핑/충돌 해결 (`test_notion_mapping.py`),
  매핑 동기화 잡 (`test_notion_mapping_sync_job.py`)
- **조직(org)**: 부서/직책 CRUD, 중복·공백 이름 거부, 이름 변경이 전 사용자에 반영, 사용 중
  삭제 거부(사용 수 안내, 아카이브 사용자 포함 집계), 비활성 부서 배정 차단, 감사 기록,
  비관리자 거부 (`test_admin_org.py`)
- **사용자 아카이브 수명주기**: soft delete로 목록/검색에서 숨김(archived=true로만 노출),
  복원, 아카이브 사용자 로그인 차단과 세션 폐기, 감사 기록, 아카이브 이메일 재생성 시 복원 안내,
  멱등, 소유 스케줄 자동 disable (`test_admin_user_archive.py`)
- **하드닝(리트라이/멱등)**: 이미 published면 재시도 단락, chat 요청 안정적 idempotency 키,
  sync 진행 중 중복 방지와 완료 후 재실행 허용 (`test_handlers_hardening.py`),
  cert 만료일 파싱과 heartbeat 비프 루프 (`test_health_worker_hardening.py`),
  once 스케줄 run_at 검증, run-now 더블클릭 비중복, misfire catchup/알림 (`test_schedules_hardening.py`)
- **보존/정리(retention)**: 종료 잡, 스케줄 런, 오래된 대화 청크 purge와 보고 (`test_retention_purge.py`)
- **운영**: 유지보수 모드 차단·operator 통과(`test_maintenance_mode.py`),
  설정 dry-run/rollback(`test_settings_api.py`), 알림 소유권(`test_notifications.py`),
  대시보드·백업(`test_dashboard_backups.py`), 대시보드 critical 감사 노출 역할 게이트
  (`test_dashboard_critical_audit.py`), 감사 조회(`test_audit_api.py`),
  Job 큐 API(`test_jobs_api.py`), 사용자 관리 API(`test_admin_users.py`),
  admin 콘솔 셸과 JSON 계약(`test_admin_console.py`, `test_admin_console_json_contract.py`),
  에러 envelope 형식(`test_error_envelope.py`), 헤더/CSP(`test_middleware.py`),
  HTML 페이지 응답(`test_pages.py`), CLI 전 명령(`test_cli_user.py`),
  healthz/readyz(`test_health.py`), 응답 시간 sanity(`test_perf_sanity.py`)

### tests/security — 보안 강제 검증

| 파일 | 검증 내용 |
|---|---|
| `test_rbac_basics.py` / `test_admin_rbac.py` | 역할별 403 — user는 admin API 전면 거부, auditor는 읽기만 |
| `test_csrf.py` | 헤더 누락/불일치 변이 요청 403, 안전 메서드 면제 |
| `test_ssrf_allowlist.py` | host:port 불일치·scheme·userinfo 거부, **파일 없음=전면 거부** |
| `test_outbound_client.py` | **httpx import가 http_client뿐임을 정적 검사**, redirect 미추종, secret 주입 |
| `test_async_handler_ban.py` | **async def 라우트 핸들러 0건 정적 검사**(sync 일관성 불변) |
| `test_chat_security.py` | 타인 대화 접근 거부, requester 위조 불가(서버 세션 기준) |
| `test_idor_and_privilege.py` | 타 사용자 객체 접근 거부, 역할 미달 admin write 차단, operator/auditor 경계, user의 admin 네임스페이스 전면 거부 |
| `test_injection_and_traversal.py` | 사용자 검색/감사 필터 SQL 인젝션 무해, static과 secret_ref 경로 traversal 차단, open redirect와 backslash next 우회 방지 |
| `test_secret_exposure_sweep.py` | 어떤 엔드포인트도 secret 평문 미노출, 상태만 노출, 버전 스냅샷과 감사엔 ref만 |
| `test_admin_authority_boundary.py` | admin이 system_admin 대상 비번 리셋/비활성/잠금해제/세션 폐기/프로필 수정 불가, system_admin은 가능 |
| `test_user_archive_authority.py` | admin의 system_admin 아카이브 금지, 자기 아카이브 금지, 마지막 system_admin 보호(CLI 포함), CSRF/비관리자 거부 |
| `test_create_secret_binding_gate.py` | secret 바인딩 integration/runner 생성과 클론은 system_admin만, auth 활성화 PATCH 게이트 |
| `test_integration_health_url_gate.py` | health_url 변경과 롤백은 admin에 승인 게이트 |
| `test_adversarial_scenarios.py` | 잘못된 러너 URL 거부, URL id 위조 차단, 스케줄 이중 발화 방지, 임시 비번 미로그, 마지막 system_admin 보호, 브라우저 새로고침 티켓 비중복, 러너 불량 JSON 처리 |

### tests/regression / tests/smoke

- `regression/`: 고정된 결함의 재발 방지 테스트 수납처 (버그 수정 시 추가하는 규칙).
  자산 캐시 버스팅, CSS 계약, installer venv 권한, 마이그레이션 0015 org 왕복, Notion 매핑
  워크플로 시딩, 테마와 워드마크 서피스 등 과거 실제로 터진 결함을 못 박는다
- `smoke/`: 배포된 라이브 인스턴스 대상 점검용 — 기본 실행에서 제외

### frontend — 프런트(React) vitest 스위트 (별도 묶음)

플랫폼 pytest와 분리된 러너. `cd frontend && npm test`(내부적으로 `vitest run`).
소스 옆(`frontend/src/screens/*.test.{js,jsx}`)에 화면 헬퍼 순수 로직 단위 테스트로 둔다 —
chat/settings/users/dashboard/board 헬퍼, 설정 값 강제(coerce), 사용자 상세 등. jsdom 환경,
`@testing-library`. 프런트 로직을 바꾸면 이 묶음도 green이어야 한다.

## 커버리지 기대치

핵심 경계(인증/RBAC/CSRF/SSRF/큐/스케줄러/품질 게이트)는 유닛+통합 이중으로 덮는다.
새 기능 추가 시 최소한: 서비스 로직 unit + API happy/오류 경로 integration +
권한 거부 security 케이스 1개를 함께 커밋한다.
