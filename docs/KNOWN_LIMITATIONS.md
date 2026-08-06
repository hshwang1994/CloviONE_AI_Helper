# KNOWN LIMITATIONS — 알려진 제약

의도된 설계 결정과 아직 구현되지 않은 항목을 구분해 정리한다. "제약"은 대부분
현 규모(사내 단일 서버 PoC~초기 운영)에 맞춘 선택이며, 확장 경로가 준비되어 있다.

## 1. SQLite 단일 writer

- WAL + busy_timeout(5s)으로 동시 읽기는 원활하지만 **쓰기는 한 번에 하나**다.
  대량 동시 쓰기 워크로드에는 부적합
- 운영 중 DB 파일을 외부 도구로 열 때는 반드시 읽기 전용(`mode=ro`)으로 —
  장기 writer 세션이 `database is locked`를 유발한다 (`docs/RUNBOOK.md` #6)
- 전환 기준과 이식 경로: `docs/EXTENSION_GUIDE.md` §7 (Postgres, spec §7.4)

## 2. 단일 Worker 프로세스

- Job 처리량 = worker 1개의 순차 처리. 긴 n8n 호출(최대 180s)이 큐를 막을 수 있다
- claim이 원자적(UPDATE…RETURNING + UNIQUE idempotency key)이라 **worker를 여러 개
  띄워도 이중 처리는 없지만**, 공식 배포는 단일 인스턴스만 검증되어 있다
- Scheduler가 worker 안에서 돌므로 worker 중단 = 스케줄 중단 (misfire 정책이
  재기동 시 처리). 분리 배포는 tick 콜백 구조상 코드 변경 없이 가능 (spec §2.3)

## 3. 알림은 인앱 전용

- Email/Teams 발송은 **아직 없다.** `NotificationProvider` 인터페이스와 fan-out
  지점(`notifications/service.py`)은 준비되어 있으나 구현체는 인앱뿐
- 결과: 승인 요청/실패 알림을 보려면 사용자가 접속해야 한다. 긴급 통지는 별도 채널 필요

## 4. Self-signed 인증서 / HSTS 미적용

- TLS는 self-signed(PoC)라 브라우저 경고가 발생하고, **HSTS는 의도적으로 켜지 않았다**
  (nginx vhost 주석 참조) — 잘못된 인증서로 HSTS를 고정하면 복구가 어렵기 때문
- 사내 CA 또는 정식 인증서 도입 시: cert 교체 → HSTS 활성화 검토
- 대시보드가 만료 일수를 표시하지만 자동 갱신은 없다 (`docs/RUNBOOK.md` #3)

## 5. Notion 매핑은 workflow 의존

- 이메일→Notion user id 해석은 n8n의 예약 workflow `notion-user-mapping`이 있어야
  동작한다. workflow 미구성/비활성/다운이면 모든 검증이 unmapped로 끝나고,
  미매핑 사용자의 1인칭 요청은 safe-refusal 안내로만 응답된다
- 관리자 수동 매핑이 우회 수단이지만 id를 직접 확인해 입력해야 한다

## 6. 서비스 재시작은 웹에서 불가 (안내만)

- 설정 변경 API는 `restart_required` 플래그를 돌려줄 뿐 **재시작을 수행하지 않는다**
- 백업 복원도 동일 철학: `GET /api/admin/backups/restore-instructions`는 절차 텍스트만
  반환하고 실제 복원은 서버 스크립트로만 (spec §14.6)
- systemd 하드닝(NoNewPrivileges 등) 하에서 앱이 systemctl을 호출하지 않는 것은
  의도된 보안 경계다 — 재시작은 SSH + sudo 권한자의 몫

## 7. 브라우저 렌더링 검증 미완

- 테스트 스위트는 API/보안/회귀(pytest) + React 컴포넌트 유닛(vitest, `frontend/`) 중심이다.
  유닛 레벨은 커버되지만, HTML+JS UI의 통합 테스트는 페이지 응답과 정적 자원까지만 확인하며,
  **실 브라우저(E2E) 렌더링·상호작용 검증은 아직 수행되지 않았다**
  (`tests/smoke`는 라이브 인스턴스 필요, 기본 deselect)
- UI 변경 후에는 수동으로 로그인→내 업무/도우미/문서/팀 공간(놀이·게시판)→관리자 콘솔
  주요 섹션을 확인할 것

## 8. 기타 소소한 제약

- 채팅 응답은 폴링 방식(1~5s backoff) — WebSocket/SSE 아님. 지연 체감은 수 초 이내
- 대화 목록은 최근 100개. **보존 기간 설정은 실제로 동작한다** — 워커가
  `app/core/retention.py::run_retention` 을 주기적으로 돌려
  `conversation_retention_days` 보다 오래된 대화를 **지운다**
  (`app/worker_main.py` 의 보존 정리 틱).
  > ⚠️ 이 문서는 오랫동안 "자동 정리 잡은 아직 없다" 고 **거짓을 적고 있었다**(N7).
  > 그 말을 믿고 보존 기간을 줄이면 **다음 주기에 대화가 대량 삭제된다** — 되돌릴 수 없다.
  > 값을 줄이기 전에 백업을 확인하라.
- run-now/스케줄 payload는 template 그대로 전달 — 변수 치환(예: `{week}`)은
  workflow(n8n) 쪽 책임
- **알림은 자동 정리된다**(`notification_retention_days`, 같은 보존 정리 틱).
  감사 로그는 자동 아카이브가 없다 — 보존 일수 설정만 있고 아무도 안 읽는다
  (감사 기록은 지우지 않는 편이 안전한 기본값이지만, **설정이 아무 일도 안 한다는
  사실은 화면에 적혀 있지 않다**).
- 다국어 미지원 — UI/메시지는 한국어 고정

## §32 검수 루프에서 확인·문서화한 잔여 항목 (Medium/Low)

아래는 2026-07-14 7관점 적대 검수(iteration 1)에서 발견됐으나 현 규모에서 영향이
제한적이라 문서화 후 후속으로 미룬 항목이다. Critical/High는 모두 수정됨(commit 6787df9).

- **Alembic autogenerate 노이즈**: 마이그레이션은 UNIQUE를 unique **index**로,
  모델은 `unique=True`(unique **constraint**)로 선언한다. SQLite에서 기능은 동일하고
  유일성은 실제로 강제된다(멱등 dedup 테스트로 증명). 다만 `alembic revision
  --autogenerate`가 drop/create 잡음을 낸다 → **autogenerate 출력은 항상 사람이 검토**
  (표준 관행). 영향: 런타임 버그 없음. 우회: 수동 마이그레이션 작성.
- **승인 필요 write workflow의 스케줄 자동 실행**: `schedule_run` 핸들러는
  `approval_required=true`인 write workflow를 자동 실행하지 않고 실패시킨다(fail-closed).
  주기 자동 발행이 필요하면 문서 자동화(§19, preview→승인→publish)를 사용한다.
- **workflow rollback 승인 게이트 미적용**: runner·integration rollback은 게이트하지만
  workflow webhook_url을 rollback으로 바꾸는 경로는 미게이트(webhook은 allowlist로 여전히 제한).
- **백업 보존 정책**: `apply_retention`은 실패 백업도 keep-14 창에 포함한다. 백업 연속
  실패 시 성공 백업이 조기 삭제될 수 있음 → 대시보드의 마지막 성공 시각으로 모니터링.
- **대시보드 경고는 수동 관찰**: 인증서 만료·디스크 부족·큐 적체는 대시보드에 수치로
  표시되나 능동 알림(Notification 발송)은 아직 없다(§31.9 후속).
- **사용자 콘솔 알림 진입점**: (해소됨) 사용자 콘솔에 알림 목록 화면(`/notifications`)이
  생겨, 상단바의 알림 벨은 이제 **모든 로그인 사용자**에게 노출된다(과거엔 관리자 콘솔에만
  화면이 있어 operator 이상에게만 보였다). 알림 발송 채널 자체는 여전히 인앱 전용(§3).
- **사용자 콘솔 부가 진입점**: 전역 Search/Help 전용 진입점은 미구현. 내 프로필은
  사용자 메뉴의 '내 프로필' 모달(부서/직책/마지막 로그인/활성 세션 수/Notion 연결 상태)로 제공한다.
- **로그인 타이밍 사이드채널(Low)**: 미등록 이메일과 오답 비밀번호의 응답 시간이 미세하게
  다를 수 있음. 계정 열거 위험은 낮음(동일 오류 메시지, rate limit 적용).

## admin 한 명이 승인 없이 발행할 수 있다 (설계상 허용, 감사 로그에 남음)

`self_approval_allowed`를 끄면 자기가 낸 요청을 자기가 승인할 수 없다. 그런데 admin은
Workflow 등록 정보의 `approval_required`를 끌 수 있고(WRITE_ROLES = admin, system_admin),
템플릿 정책이 없으면 `publish_approval_required()`가 False가 되어 승인 단계 자체가 사라진다.
결과적으로 **admin 한 명이 다른 사람의 확인 없이 문서를 발행할 수 있다.**

**이것을 결함으로 보지 않는 이유:**
- 워크플로 수정 권한과 승인 결재 권한이 **같은 역할**이다(둘 다 admin·system_admin).
  즉 그 admin은 approval_required를 끄지 않아도 자기 권한으로 승인할 수 있는 사람이다.
  권한 상승이 아니다.
- 스펙 §20은 자기 승인 금지를 **"옵션을 제공한다"**고 규정한다. 불변 조항이 아니다.
- `approval_required` 변경은 `record_audit_from_request`로 감사 로그에 남는다. 조용한 우회가 아니다.

**그래도 알아야 하는 이유:** 자기승인 금지를 켜 두면 "발행에는 두 사람이 필요하다"고 기대하기
쉬운데, admin 한 명이 그 요구 자체를 끌 수 있으므로 그 기대는 성립하지 않는다. 두 사람을
강제해야 하는 조직이라면 `approval_required` 수정 권한을 system_admin으로 좁히고
Workflow 수정 감사 로그를 정기적으로 봐야 한다. (검수에서 제기됐고 반증 2/3으로 기각됐으나,
검증자 한 명이 익스플로잇을 실제로 재현했기에 성질만 기록해 둔다.)

## AI 채팅의 승인/재정의/피벗 판정은 규칙 기반이라 자연어 꼬리가 남는다

러너(`runner/claude-work-assistant/assistant.py`)는 티켓 생성·변경·댓글의 미리보기에 대한
사용자 답변이 **승인**인지, 값을 바꾸라는 **재정의**인지, 그냥 **묻는 말/조회**인지, **거절**인지를
규칙(정규식·키워드)으로 가른다. 이 경계는 자유 한국어라 규칙만으로는 '두 번 연속 결함 0'에
수렴하지 않는다(검수 round1~16, 확정 카운트 1→3→7→6→7→3→2→4→3→5→3→5→6→4→5→18의
진자). 매 라운드 새 키워드가 인접 표현을 깨뜨린다.

**그래서 fail-safe로 재설계했다(러너 3.53.0, round16).** 원칙은 "애매하면 쓰지 않는다":
- 승인은 **보수적으로** 인정한다 — 첫 낱말이 정확히 yes(응/네/오케이…)이거나 정확 조합
  (`is_exact_approval`)일 때만. 접두 매칭('응답'의 '응')은 승인 없는 쓰기를 냈기에 제거했다.
- 부정('아니/하지마/말고')·연기('나중에')·물음(조회 동사·의문 어미)이 섞이면 **절대 승인이 아니다** —
  답만 하거나 되묻고, pending은 유지한다.
- 값을 담은 재정의는 그 값을 **승인 대기 중이던 그 티켓**에 반영한다(대상을 잃지 않는다).

**남는 것:** 위 가드가 승인을 놓쳐 **안전하게 되묻는** 경우는 여전히 있을 수 있다(예: 아주 드문
무공백·변형 표현). 이는 사용자가 한 번 더 답하면 되는 MED 불편이지, 데이터를 잘못 쓰는 HIGH가
아니다. **잘못된 쓰기(HIGH)는 구조적으로 막았고, 남은 것은 되묻기(MED)로 수렴한다.** 근본적
정확도를 더 올리려면 이 경계를 LLM 의도 분류로 넘겨야 하나(러너는 이미 Claude CLI를 호출한다),
매 pending 턴에 LLM 지연이 붙고 결정론 테스트가 어려워지는 트레이드오프가 있어 채택하지 않았다.
