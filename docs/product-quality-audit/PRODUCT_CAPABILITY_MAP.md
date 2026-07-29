# 제품 기능 지도 (PRODUCT_CAPABILITY_MAP)

이 문서는 저장소 코드를 직접 읽고 작성했다. 문서에만 있고 코드에서 확인하지 못한 내용은 그렇게
표시했다. 역할명은 코드에 실제로 정의된 다섯 가지만 쓴다: `user`(일반 사용자), `operator`(운영자),
`admin`(관리자), `auditor`(감사자), `system_admin`(시스템관리자). 역할에는 계층이 있고
(`user < operator < admin < system_admin`), `auditor`는 이 계층 밖에 있는 읽기 전용 갈래로,
각 라우터가 명시적으로 포함한 곳에서만 접근할 수 있다(`app/users/models.py`의
`roles_at_least`, `_ROLE_LEVELS` 주석 참고).

## 0. 제품 구조 개요

제품은 세 개의 프로세스로 이루어진다.

1. **FastAPI 웹 플랫폼** (`app/`) — 로그인한 사용자를 위한 채팅 화면(`/`)과 관리자 콘솔(`/admin`).
   자체 SQLite DB(`var/web.sqlite3`, WAL 모드)에 사용자, 세션, 대화, Job, 레지스트리, 감사 로그 등을
   저장한다. 업무 데이터(프로젝트, 티켓)는 이 DB에 없다.
2. **n8n 워크플로 엔진** (외부 서비스, 127.0.0.1:5678, 무접촉) — 웹훅 하나
   (`/webhook/clovirone-work-assistant`)로 노출되어 있고, Notion 조회와 Claude 러너 호출을
   오케스트레이션한다. 로컬 사본은
   `C:\Users\hshwa\Downloads\ClovirONE_AI_Work_Assistant\ClovirONE_AI_Work_Assistant_v7.json`.
3. **Claude 업무 도우미 러너** (`runner/claude-work-assistant/assistant.py`, 127.0.0.1:8789) —
   자연어 의도 해석(규칙 엔진) + Claude CLI 호출. 서버의 별도 SQLite
   (`/var/lib/n8n/clovirone-work-assistant-state.sqlite3`)에 "대화 문맥"과 "처리한 메시지
   idempotency 키"만 저장한다. 프로젝트/티켓 데이터 자체는 저장하지 않고 매 요청마다 n8n이 넘겨준
   Notion 조회 결과를 그때그때 정규화해서 쓴다.

요청 흐름(채팅 한 건 기준):

```
브라우저 → nginx → FastAPI(웹) : 메시지를 Job 큐에 저장, 202 즉시 응답, 화면은 폴링
                                  ↓
                    worker(app/jobs/worker.py) : chat_message Job을 집어 n8n 웹훅 호출
                                  ↓ (app/jobs/handlers/chat_message.py → OutboundClient)
                    n8n 워크플로 : Notion에서 프로젝트/작업/스키마 조회(캐시) → 러너 호출
                                  ↓
                    Claude 러너(assistant.py) : 의도 해석 → (조회는 즉시 응답 / 생성·변경은
                                  미리보기 후 사용자 확인) → 승인되면 Notion Write
                                  ↓
                    n8n → worker → 플랫폼 DB에 assistant 메시지 저장 → 브라우저가 폴링으로 수신
```

플랫폼은 Notion 토큰을 직접 들고 있지 않다(스펙 §19.1). Notion 접근은 항상 n8n 워크플로를 통해서만
이루어진다.

역할별 화면 도달 요약: `/`(채팅)은 로그인만 하면 모든 역할이 들어간다. `/admin`은
`must_change_password`가 아니고 역할이 `user`가 아니면(즉 `operator` 이상이면) 들어갈 수 있다
(`app/admin/router.py`). 다만 관리자 콘솔 화면 자체는 모든 섹션을 역할과 무관하게 렌더링하고
(`app/static/js/admin/app.js`의 `renderNav`는 역할 필터링을 하지 않는다), 실제 접근 제어는
전부 서버 API의 `require_roles` 의존성이 담당한다. 그 결과 예를 들어 `auditor`가 "사용자" 섹션
링크를 누르면 화면은 뜨지만 목록 API가 403을 돌려준다("이 화면에 접근할 권한이 없습니다").

---

## 1. 인증과 세션

| 기능 | 목적 | 대상 사용자 | 진입 화면 | API | 데이터 모델 | n8n 관여 | 필요 권한 | 알림/감사 |
|---|---|---|---|---|---|---|---|---|
| 로그인 | 이메일/비밀번호로 인증 후 세션 쿠키 발급 | 전체 역할 | `GET/POST /login` | `POST /login` | `User`(`app/users/models.py`), `UserSession`(`app/auth/models.py`) | 없음 | 없음(비로그인) | 로그인 실패 누적 시 계정 잠금 알림(본인+관리자), 잠금은 감사 로그 없음(알림만, `app/auth/router.py`) |
| 로그아웃 | 현재 세션 폐기 | 전체 역할 | 채팅/관리자 화면의 사용자 메뉴 | `POST /logout` | `UserSession` | 없음 | 로그인 상태 | 없음 |
| 비밀번호 변경 | 본인 비밀번호 변경, 세션 회전 | 전체 역할 | `/change-password` | `POST /change-password` | `User` | 없음 | 로그인 상태 | 감사 없음(본인 행위) |
| 세션 조회/강제 만료 | 특정 사용자의 활성 세션 목록 조회 및 전체 폐기 | admin 이상 | 관리자 콘솔 &gt; 사용자 &gt; 세션 조회 | `GET /api/admin/users/{id}/sessions`, `POST /api/admin/users/{id}/revoke-sessions` | `UserSession` | 없음 | `admin`, `system_admin` | `user.revoke_sessions` 감사 |

세부 규칙(코드 확인):

- 세션은 JWT가 아니라 256비트 랜덤 opaque 토큰이며 DB에는 SHA-256 해시만 저장한다
  (`app/core/security.py`, `app/core/sessions.py`).
- 절대 타임아웃 기본 8시간, 유휴 타임아웃 기본 30분이며 관리자 설정(`session_policy`)으로
  덮어쓸 수 있다. `last_seen_at` 갱신은 60초 단위로만 기록해 SQLite 쓰기 증폭을 줄인다.
- 로그인 실패는 IP당 분당 10회로 속도 제한되고(`RateLimiter`), 계정별 실패 임계치를 넘으면
  `locked_until`이 설정된다(기본 임계치는 `settings.login_max_failures`).
- 비밀번호 변경, 역할 변경, 계정 비활성화, 관리자의 비밀번호 재발급, 잠금 해제 시 모두 기존 세션이
  전부 폐기된다(`session_service.revoke_all_for_user`).
- `app/core/config.py`에 `session_secret` 필드가 선언되어 있으나 세션이 opaque 토큰 방식이라
  이 값을 실제로 참조하는 코드가 없다(죽은 설정). `SessionService.rotate()` 메서드도 정의는
  되어 있지만 호출하는 곳이 없다(죽은 코드) — 실제로는 로그인 시 `create()`만 쓰고, 비밀번호
  변경 시에도 `revoke_all_for_user` + `create()`로 직접 처리한다.

## 2. 사용자와 역할 (RBAC)

| 기능 | API | 필요 권한 | 비고 |
|---|---|---|---|
| 목록/검색(이메일, 이름, 역할, 활성여부) | `GET /api/admin/users` | admin, system_admin | operator/auditor는 이 화면 전체에 접근 불가(다른 관리 화면과 다르게 예외적으로 좁다) |
| 생성(임시 비밀번호 1회 표시) | `POST /api/admin/users` | admin, system_admin | `admin`/`system_admin` 역할로 즉시 생성은 `system_admin`만 가능 |
| 상세 조회 | `GET /api/admin/users/{id}` | admin, system_admin | 활성 세션 수, Notion 매핑 상태 포함 |
| 수정(이름/부서/직함/역할/비밀번호 변경 요구) | `PATCH /api/admin/users/{id}` | admin, system_admin | `admin`으로 승격은 승인 대상(§15 참고), `system_admin` 부여/회수는 `system_admin`만 |
| 활성화/비활성화 | `POST /api/admin/users/{id}/enable`, `/disable` | admin, system_admin | 비활성화 시 세션 전부 폐기 + 본인 소유 활성 스케줄 자동 비활성화 |
| 비밀번호 재발급 | `POST /api/admin/users/{id}/reset-password` | admin, system_admin | 임시 비밀번호는 응답에서 한 번만 노출, 로그/감사엔 없음 |
| 잠금 해제 | `POST /api/admin/users/{id}/unlock` | admin, system_admin | |
| Notion 매핑 검증(사용자 화면에서 트리거) | `POST /api/admin/users/{id}/notion-mapping/verify` | admin, system_admin | §17과 동일 로직 재사용 |

데이터 모델: `User`(`app/users/models.py`) — 필드: `email`, `display_name`, `department`, `title`,
`role`, `active`, `password_hash`, `must_change_password`, `failed_login_count`, `locked_until`,
`created_by`, `last_login_at`.

권한 상승 방지(`app/users/service.py`의 `ensure_can_manage_target`, `ensure_not_last_system_admin`):

- `system_admin` 계정은 `system_admin`만 관리(비밀번호 재발급, 활성화 전환, 잠금 해제, 세션 폐기
  전부 포함)할 수 있다 — 일반 `admin`이 `system_admin` 계정을 장악할 수 없다.
- 마지막 남은 활성 `system_admin`은 비활성화하거나 역할을 바꿀 수 없다.
- `admin`으로의 역할 변경은 요청자가 `system_admin`이 아니면 즉시 반영되지 않고 승인 큐로 간다
  (아래 §15 승인 참고).

감사: `user.create`, `user.update`, `user.enable`, `user.disable`, `user.reset_password`,
`user.unlock`, `user.revoke_sessions`, `user.role_change_requested`가 각각 `record_audit_from_request`로
기록된다(`app/users/router.py`). 알림: 계정 비활성화/역할변경 자체는 알림이 없고, 승인 요청/결정
시점에만 승인 관련 알림이 간다(§15).

**최초 system_admin 계정은 웹 API로 만들 수 없다.** `scripts/seed_admin.py` 또는
`app/cli/user_cli.py`(서버 CLI, 비밀번호는 stdin으로만)로 서버에서 직접 만든다 — 스펙상 의도된
out-of-band 시딩이다.

## 3. 프로젝트

**플랫폼(app/) 안에는 "프로젝트"에 대응하는 데이터 모델도, API도, 관리 화면도 없다.** 프로젝트는
Notion 프로젝트 DB에만 존재하는 원천 데이터다. 채팅에서 "내 담당 프로젝트 보여줘"라고 물으면
FastAPI는 이 요청을 그대로 Job으로 만들어 n8n에 넘기고(§7), n8n이 그때그때 Notion에서 프로젝트
페이지를 조회해 러너(assistant.py)에 넘긴다. 러너는 응답마다 `normalize_project()`
(`runner/claude-work-assistant/assistant.py:571`)로 페이지를 `{id, name, status, primary(담당자 정),
secondary(담당자 부), url}` 모양으로 정규화해서 그 요청 처리 중에만 메모리에서 사용한다 — 어디에도
영속화하지 않는다.

| 기능 | 목적 | 대상 사용자 | 진입 화면 | 실제 구현 위치 | n8n 관여 |
|---|---|---|---|---|---|
| 프로젝트 조회(자연어) | "내 담당 프로젝트 보여줘" 같은 문장으로 조회 | 채팅을 쓰는 전체 역할 | `/` (채팅) | `runner/claude-work-assistant/assistant.py`의 `current_user_projects`, `asks_about_projects`, `resolve_project` | 있음(Notion 조회 중계) |
| 프로젝트 이름으로 티켓 필터링 | "용인 프로젝트의 계획 티켓 보여줘" | 채팅을 쓰는 전체 역할 | `/` (채팅) | `project_score`, `resolve_project`, `_PROJECT_STRONG_SPAN`/`_PROJECT_TOKEN_FLOOR` 기반 부분일치 | 있음 |
| 프로젝트 생성/수정/삭제 | — | — | — | **코드에 없음** — 채팅에서도 프로젝트 자체를 만들거나 바꾸는 명령은 지원하지 않는다(티켓만 대상) | — |

권한/감사: 플랫폼 쪽에는 프로젝트 전용 권한이나 감사 로그가 없다(대화 자체의 감사는 §7 참고).

## 4. 티켓

프로젝트와 마찬가지로 **플랫폼 DB에 "티켓" 테이블이 없다.** 티켓은 Notion 작업(업무) DB의 페이지이고,
`WORK_DB_ID`(`runner/claude-work-assistant/assistant.py:33`, 기본값
`262c5c5a-5684-81fa-9697-ee5691cb558d`)로 식별되는 데이터베이스에서 n8n이 조회해 러너에 넘긴다.
티켓에 대한 모든 조회/생성/변경 로직은 러너의 규칙 엔진에 있다.

| 기능 | 목적 | 진입점 | 핵심 함수(`assistant.py`) | 승인 필요 여부 | n8n 관여 |
|---|---|---|---|---|---|
| 티켓 생성 | 자연어로 신규 티켓 초안 작성 후 Notion에 등록 | `/` 채팅, 퀵프롬프트 "새 티켓 만들어줘" | `create_ticket`, `build_create_body`, `is_create_intent` | 있음(대화형 확인 — 아래 참고) | 있음 |
| 티켓 조회/집계 | 담당자, 상태, 마감일, 난이도, 우선순위, 제목 키워드로 조회·개수 세기 | `/` 채팅 | `query_tickets`(`assistant.py:2286`), `extract_assignee_filter`, `extract_difficulty_filter`, `resolve_status_intent`, `parse_date_range` | 없음(읽기 전용) | 있음 |
| 티켓 상세 조회 | "두 번째 티켓 상세 보여줘"처럼 직전 목록을 번호로 참조 | `/` 채팅 | `resolve_ticket_reference`, `parse_number_reference` | 없음 | 있음 |
| 티켓 상태/마감일/우선순위/난이도/담당자 변경 | 자연어로 필드 변경 | `/` 채팅 | `update_ticket`(`assistant.py:2941`), `detect_target_status`, `extract_priority`, `extract_difficulty` | 있음(대화형 확인) | 있음 |
| 티켓 삭제 | — | — | 명시적으로 **미지원** — `route_request`가 삭제 요청을 가로채 "채팅에서 지원하지 않는다"고 안내하고 상태를 '취소'로 바꾸도록 유도한다(`assistant.py:3956`) | 해당 없음 | 없음 |

**대화형 확인(컨펌) 흐름**은 §15의 플랫폼 승인(Approval) 모듈과 **다른 메커니즘**이다. 티켓
생성/변경은 사용자가 "네", "승인", "그대로 진행" 등으로 답해야 실제 Notion Write가 나가고
(`handle_confirmation`, `is_approval_message`, `APPROVE_COMMANDS`/`DECLINE_COMMANDS`), 이 확인은
러너 프로세스 내부의 대화 상태(`pending_action`)로만 관리되며 플랫폼 DB의 `Approval` 테이블과는
무관하다. 댓글 작성만 예외로 확인 없이 즉시 반영된다(§5).

담당자 변경 시 재검증: `handle_confirmation`은 확정 시점에 티켓이 여전히 요청자 본인에게 할당되어
있는지 `person_matches`로 다시 확인한다 — 미리보기와 확정 사이에 담당자가 바뀌면 변경을 거부한다.

권한: 플랫폼 쪽 역할 체계와 무관하게, 러너는 요청자의 Notion 사람 매핑(§17)으로 "본인 티켓"인지
판단한다. 플랫폼 역할(`user`/`operator`/...)은 티켓 조작 권한에 전혀 관여하지 않는다 — 채팅을 쓸 수
있는 사람이면 역할과 무관하게 자신이 담당자로 매핑된 티켓을 다룰 수 있다.

## 5. 댓글

티켓 댓글도 Notion 페이지에 대한 코멘트이며 플랫폼 DB에 없다. 러너의 `comment_ticket`
(`assistant.py:3282`)이 처리한다.

| 항목 | 내용 |
|---|---|
| 목적 | 지목한 티켓에 한 줄 댓글을 남긴다 |
| 진입점 | `/` 채팅. 예: `두 번째 티켓에 "내일 배포 예정"이라고 댓글 남겨줘` |
| 트리거 판정 | `is_comment_intent` — "댓글"이라는 낱말과 "남겨/달아/작성해/추가해/써줘" 류 동사가 함께 있어야 함 |
| 대상 해석 | `resolve_ticket_reference`로 직전 목록의 번호나 제목에서 티켓 하나를 특정. 댓글 본문 자체가 대상 해석에 끼어들지 않도록 따옴표 안 텍스트를 먼저 떼어낸다 |
| 승인 필요 여부 | **없음** — 코드 주석에 "low-risk write — no approval step"이라고 명시되어 있고, 확인 절차 없이 바로 `WRITE_COMMENT` 액션으로 Notion에 반영된다 |
| n8n 관여 | 있음(Notion 댓글 API 호출은 n8n/Notion 쪽에서 수행) |

## 6. 검색, 필터, 정렬

이 기능은 성격이 다른 두 군데에 따로 존재한다.

**(A) 관리자 콘솔의 목록 API** — 서버 사이드 페이지네이션(`app/core/pagination.py`의 `PageParams`,
기본 20건/최대 100건)과 리소스별 쿼리 파라미터 필터.

| 화면 | 필터 파라미터 | 정렬 |
|---|---|---|
| 사용자 | `q`(이메일/이름), `role`, `active` | 생성일 역순 고정(서버) |
| 감사 로그 | `action`, `object_type`, `object_id`, `user_id`, `since`, `until`(ISO 8601) | 생성일 역순 고정 |
| Job 큐 | `status`, `job_type` | 생성일 역순 고정 |
| 승인 | `status` | 요청일 역순 고정 |
| 문서 생성 | `status` | 생성일 역순 고정 |
| Notion 매핑 | `q`, `status`, `user_ids`(콤마 구분) | 이메일순 고정 |
| 스케줄 실행 이력 | `status` | 생성일 역순 고정 |

관리자 콘솔 화면(`app/static/js/admin/app.js`의 `renderTable`)은 이미 받아온 한 페이지 안에서만
컬럼 헤더 클릭으로 클라이언트 사이드 재정렬을 한다 — 서버에 정렬 파라미터를 보내지 않으며, 페이지를
넘기면 정렬 상태가 사라진다.

**(B) 채팅의 자연어 조회 필터** — 러너(`assistant.py`)의 `query_tickets`가 담당.

| 조건 종류 | 함수 | 예시 |
|---|---|---|
| 상태(진행/계획/완료/검증/이슈/취소, 포함/제외 조합) | `resolve_status_intent` | "완료 제외하고 보여줘", "검증 상태인 것만" |
| 마감일 범위 | `parse_date_range` | "이번 주까지", "다음 달", "8월 1일까지" |
| 담당자 | `extract_assignee_filter` | "민지원 담당 티켓", "미할당 티켓" |
| 난이도 | `extract_difficulty_filter` | "난이도 4 이상" |
| 제목 키워드 | `extract_keyword` | "제목에 Jenkins가 포함된 티켓" |
| 그룹핑 | `extract_group_by` | "상태별로 정리해줘" |
| 정렬 | `extract_sort`, `sort_tickets_by` | "마감일 빠른 순으로 정렬해줘" |
| 결과 개수 제한 | `extract_limit` | |

두 검색 체계는 서로 연결되어 있지 않다 — 관리자 콘솔에서 티켓/프로젝트를 검색할 방법은 없다(그런
데이터 자체가 플랫폼에 없으므로).

## 7. AI 채팅

| 항목 | 내용 |
|---|---|
| 목적 | 로그인한 사용자가 자연어로 티켓/프로젝트 업무를 처리 |
| 대상 사용자 | 전체 역할(`user` 포함) |
| 진입 화면 | `/` (`app/templates_html/chat.html`), 퀵프롬프트 7개 제공 |
| API | `GET /` (페이지), `GET/POST/PATCH/DELETE /api/conversations`, `GET/POST /api/conversations/{id}/messages`, `POST /api/messages/{id}/retry` |
| 데이터 모델 | `Conversation`, `Message`(`app/conversations/models.py`), `Job`(`app/jobs/models.py`) |
| n8n 관여 | 있음(모든 메시지가 Job → worker → n8n 웹훅 경로를 탄다) |
| 필요 권한 | 로그인 상태만 있으면 됨. 단, `must_change_password`가 true면 강제로 `/change-password`로 리다이렉트되어 채팅을 쓸 수 없다 |
| 알림/감사 | 대화/메시지 자체는 감사 로그 대상이 아니다(개인 업무 데이터로 취급). Job 실패는 본인에게 알림(`job_failed`) |

세부 동작:

- 사용자 신원(이메일, 이름)은 세션에서만 가져와 Job payload에 실어 보낸다 — 클라이언트가 보낸
  값을 신뢰하지 않는다(`app/chat/service.py`의 `_build_job_payload` 주석).
- 메시지 전송은 `client_message_id`로 멱등 처리된다(중복 클릭/새로고침 시 같은 Job을 재사용).
- 이미지 첨부(최대 3장, PNG/JPEG/WebP, 장당 3MB/합계 6MB)를 함께 보낼 수 있다(§21 참고).
- 실패한 메시지는 "다시 시도" 버튼으로 재전송할 수 있다(`retry_message`) — 이때도 실패한 Job에
  남아있던 이미지 첨부를 복구해서 재전송한다.
- 유지보수 모드(§18)가 켜지면 `user` 역할만 새 메시지 전송/재시도가 막힌다
  (`app/settings/gate.py`의 `block_if_maintenance`, `operator` 이상은 통과).
- 화면은 폴링 방식으로 새 메시지를 받는다(`app/static/js/chat.js`) — 웹소켓/SSE는 없다.
- 대화는 보존 기간(기본 90일, 관리자 설정 가능)이 지나면 워커가 자동 삭제한다(`app/core/retention.py`).
- 러너 쪽 대화 지원 범위: 티켓/프로젝트 관리 외의 요청(이메일 발송, Teams 메시지, 캘린더 등록)은
  명시적으로 거부되고(`explicit_unsupported_action`), 그 외 일상 대화나 소소한 질문은
  `claude_query`(자유대화 레이어)가 응답한다. "도움말"을 입력하면 지원 기능 목록을 보여준다.

## 8. 알림

| 항목 | 내용 |
|---|---|
| 목적 | 계정 잠금, Job 실패, 승인 요청/결정/만료, 스케줄 실행 실패 등을 인앱으로 통지 |
| 대상 사용자 | 전체 역할(본인 알림), 관리자 역할(`admin`, `system_admin`)은 승인 요청 등 관리 알림도 수신 |
| 진입 화면 | 관리자 콘솔 &gt; 알림 섹션(`sections.js`의 `notifications`). 일반 사용자용 알림 벨/배지 UI는 채팅 화면에 **없다**(§ "구현됐는데 도달 불가" 참고) |
| API | `GET /api/notifications`(unread_only 필터), `GET /api/notifications/unread-count`, `POST /api/notifications/{id}/read` |
| 데이터 모델 | `Notification`(`app/notifications/models.py`) |
| n8n 관여 | 없음 |
| 필요 권한 | 로그인 상태만 있으면 됨(관리자 전용 API가 아니다 — `/api/notifications`에는 `require_roles`가 없다) |
| 발생 트리거 | 계정 잠금(본인+관리자), Job 최종 실패(본인), 승인 요청 생성(관리자 전원), 승인 승인/거절(요청자), 승인 만료(요청자), 스케줄 실행 실패(스케줄 소유자) |

채널은 인앱뿐이다. 코드 주석(`app/notifications/service.py`)에 "Future Email/Teams providers
implement the same notify() shape"라고 명시되어 있어, 이메일이나 Teams 알림은 설계상 확장
지점으로만 존재하고 현재 구현되지 않았다. `docs/EXTENSION_GUIDE.md`도 이를 향후 확장으로만
서술하고 있어 문서와 코드가 일치한다(과장 없음).

## 9. 감사 로그

| 항목 | 내용 |
|---|---|
| 목적 | 관리 행위(생성/수정/활성화/승인/롤백 등)의 행위자, 변경 전/후 값, 결과, 클라이언트 IP를 남긴다 |
| 대상 사용자 | 조회는 `admin`, `system_admin`, `auditor` |
| 진입 화면 | 관리자 콘솔 &gt; 감사 로그 |
| API | `GET /api/admin/audit`(action, object_type, object_id, user_id, since, until 필터 + 페이지네이션) |
| 데이터 모델 | `AuditLog`(`app/audit/models.py`) |
| n8n 관여 | 없음 |
| 필요 권한 | `admin`, `system_admin`, `auditor` — **`operator`는 감사 로그를 볼 수 없다**(다른 관리 화면 대부분이 `operator`도 읽기를 허용하는 것과 다르다) |
| 기록 위치 | `app/core/audit.py`의 `record_audit_from_request`를 각 라우터가 행위 시점에 직접 호출 |

민감정보 마스킹: `mask_sensitive`가 딕셔너리 키 이름에 `password|secret|token|credential|api[_-]?key`가
매칭되면 값을 `***`로 치환한다. 다만 이는 **키 이름 기반**이라, 민감하지 않은 키의 값 문자열 안에
비밀값이 통째로 들어있으면 마스킹되지 않는다(예: 자유 텍스트 필드에 토큰을 붙여넣은 경우) — 코드를
직접 읽고 확인한 한계다.

감사되는 대표 행위: 사용자 계정 CRUD/역할변경/잠금해제, Integration/Runner/Workflow의 생성/수정/
활성화/비활성화/롤백, Prompt/Policy의 생성/내용수정/전이/새버전/롤백, Template CRUD/활성화, Schedule
CRUD/활성화/비활성화/실행, Job 재시도/취소, 승인 요청/승인/거절/취소, 알림과 무관한 설정 변경/롤백,
문서 생성 요청, Notion 매핑 검증/수동매핑/해제/충돌해결, 백업 생성/검증.

## 10. 통합 (Integration Registry)

| 항목 | 내용 |
|---|---|
| 목적 | 플랫폼이 알고 있는 외부 서비스(엔드포인트, 인증방식, 헬스URL)를 메타데이터로 등록/관리 |
| 대상 사용자 | 읽기: `operator`, `admin`, `system_admin`, `auditor`. 쓰기: `admin`, `system_admin` |
| 진입 화면 | 관리자 콘솔 &gt; 외부 연동 |
| API | `GET/POST /api/admin/integrations`, `GET/PATCH /{id}`, `POST /{id}/enable,disable,health`, `GET /{id}/versions`, `POST /{id}/rollback` |
| 데이터 모델 | `Integration`(`app/integrations/models.py`) + `ConfigVersion`(`app/core/versioning.py`, object_type=`integration`) |
| n8n 관여 | n8n 자신이 등록 대상 중 하나(헬스체크 핑 대상)이지만, 이 레지스트리가 n8n 워크플로를 실행시키지는 않는다 |
| 필요 권한 | 위 표 참고. 헬스체크는 `operator` 이상(auditor 불가 — 실행성 행위이므로) |
| 알림/감사 | 생성/수정/활성화/비활성화/롤백 전부 감사. 알림 없음(단, 민감 필드 변경은 승인 요청 알림으로 이어짐) |

초기 시드(`app/integrations/discovery.py`, `python -m app.integrations.discovery`)로 n8n,
clovirone-work-assistant(러너), claude-ticket-runner, claude-request-interpreter 4개가 등록된다.
`base_url`/`secret_ref` 변경은 승인 대상(§15)이고, `system_admin`이 아니면 즉시 반영되지 않는다.
outbound 호출은 전부 `app/core/http_client.py`의 `OutboundClient` 한 곳을 거치며, allowlist
(`config/allowed-services.json`)에 없는 호스트:포트는 저장 시점과 호출 시점 모두에서 거부된다.

## 11. 러너 레지스트리

| 항목 | 내용 |
|---|---|
| 목적 | 로컬 HTTP 실행기(Claude 러너 등)를 메타데이터로 등록/관리 — 코드나 프로세스는 건드리지 않는다 |
| 대상 사용자 | 읽기: `operator`, `admin`, `system_admin`, `auditor`. 헬스/테스트: `operator` 이상. 등록/수정/복제/롤백: `admin`, `system_admin` |
| 진입 화면 | 관리자 콘솔 &gt; 러너 |
| API | `GET/POST /api/admin/runners`, `GET/PATCH /{id}`, `POST /{id}/enable,disable,health,test,clone`, `GET /{id}/versions`, `POST /{id}/rollback` |
| 데이터 모델 | `Runner`(`app/runners/models.py`) |
| n8n 관여 | 없음(러너를 직접 HTTP로 호출) |
| 필요 권한 | 위 표 참고 |
| 알림/감사 | 등록/수정/활성화/비활성화/복제/롤백 전부 감사 |

핵심 규칙(코드 확인):

- 신규 등록은 항상 `enabled=False`로 저장된다(요청에 `true`를 보내도 무시) — 헬스체크로
  검증 후 명시적으로 활성화해야 한다.
- **서킷 브레이커**: 연속 5회 실패(`CIRCUIT_FAILURE_THRESHOLD`)하면 `maintenance_state=degraded`로
  바뀌고 5분(`CIRCUIT_COOLDOWN_SECONDS`) 동안 `can_dispatch`가 호출을 거부한다. 쿨다운 후 첫 성공
  시 자동으로 `normal`로 복구된다.
- 설정 변경(`base_url`/`secret_ref`/`health_url`)과 롤백은 승인 대상.
- **중요한 제약**: `RunnerHttpProvider.invoke`(실제 업무 요청을 러너에 보내는 함수)는 코드 전체에서
  관리자 콘솔의 "테스트" 버튼(`POST /{id}/test`, 고정된 `{"ping": true}` 페이로드)에서만 호출된다.
  실제 채팅 업무 트래픽은 이 레지스트리를 전혀 거치지 않고 n8n 웹훅으로만 흐른다(§0 그림 참고) —
  즉 이 화면에 러너를 등록/활성화해도 실제 채팅 동작에는 영향이 없다. 자세한 내용은 문서 끝
  "구현됐는데 화면에서 도달할 수 없는 것" 참고.

## 12. 워크플로 레지스트리

| 항목 | 내용 |
|---|---|
| 목적 | n8n 워크플로(웹훅 URL, 읽기/쓰기 모드, 승인 필요 여부)를 메타데이터로 등록/관리 |
| 대상 사용자 | 읽기: `operator`, `admin`, `system_admin`, `auditor`. 테스트: `operator` 이상. 등록/수정/롤백: `admin`, `system_admin` |
| 진입 화면 | 관리자 콘솔 &gt; 워크플로 |
| API | `GET/POST /api/admin/workflows`, `GET/PATCH /{id}`, `POST /{id}/enable,disable,test`, `GET /{id}/versions`, `POST /{id}/rollback` |
| 데이터 모델 | `Workflow`(`app/workflows/models.py`) |
| n8n 관여 | 있음(등록된 워크플로가 실제 n8n 웹훅을 가리킨다) |
| 필요 권한 | 위 표 참고 |
| 알림/감사 | 등록/수정/활성화/비활성화/롤백 전부 감사 |

초기 시드(`seed_known_workflows`, `app/workflows/service.py`)로 "ClovirONE AI 업무 도우미"
워크플로(웹훅 `http://127.0.0.1:5678/webhook/clovirone-work-assistant`, `operation_mode=write`)가
등록된다. `POST /{id}/test`는 실제로 워크플로를 실행하지 않고 GET으로 도달 가능성만 확인한다
(`N8nWorkflowProvider.test`). 실제 실행은 채팅(§7), 문서 생성(§16), 스케줄(§14)이 각각
`N8nWorkflowProvider.invoke`를 통해 수행한다. `Notion 매핑`(§17)의 `notion-user-mapping`이라는
예약된 이름의 워크플로도 이 레지스트리에서 관리된다.

## 13. 프롬프트, 정책, 템플릿

| 항목 | 내용 |
|---|---|
| 목적 | Prompt(자유 텍스트)와 Policy(JSON) 콘텐츠를 draft→test→review→published→archived 수명주기로 버전 관리. Template은 Workflow/Runner + Prompt/Policy + 승인정책을 묶은 활성/비활성 레지스트리 |
| 대상 사용자 | 읽기: `operator`, `admin`, `system_admin`, `auditor`. 쓰기: `admin`, `system_admin` |
| 진입 화면 | 관리자 콘솔 &gt; 프롬프트 / 정책 / 템플릿 |
| API | `GET/POST /api/admin/prompts`(`policies` 동형), `GET/PATCH /{id}`, `POST /{id}/transition,new-version`, `GET /diff/view`, `POST /rollback`; 템플릿은 `GET/POST /api/admin/templates`, `GET/PUT /{id}`, `POST /{id}/enable,disable` |
| 데이터 모델 | `Prompt`, `Policy`(둘 다 `app/prompts/models.py`에 정의), `AutomationTemplate`(`app/templates/models.py`) |
| n8n 관여 | **없음** |
| 필요 권한 | 위 표 참고 |
| 알림/감사 | 생성/내용수정/전이/새버전/롤백/템플릿 CRUD 전부 감사 |

수명주기 규칙: 내용 수정은 draft 상태에서만 가능하고, 이름당 published는 항상 1개만 유지된다(새
버전을 published로 전이하면 기존 published가 자동으로 archived된다). 롤백은 과거 버전 내용을
복사한 새 버전을 만들어 즉시 published까지 전이시키는 방식이라, 이력은 항상 append-only다.

**중요한 제약(코드로 확인)**: `get_published()`(발행된 버전 조회 함수)를 호출해서 실제 업무
로직에 그 콘텐츠를 주입하는 코드는 어디에도 없다. Prompt/Policy/Template은 순수하게 관리자
콘솔에서 버전을 관리하는 메타데이터일 뿐이며, 채팅 러너(assistant.py)나 n8n 워크플로가 이
플랫폼 API를 호출해 발행된 프롬프트나 정책을 가져가는 경로가 없다. 즉 이 화면에서 프롬프트를
"발행"해도 실제 러너 동작(하드코딩된 규칙과 Claude CLI 호출)에는 아무 영향이 없다 — 실제 반영은
사람이 러너 배포 파이프라인으로 직접 해야 한다. Policy 내용은 JSON 객체인지만 검증하고
(`validate_policy_content`), 그 안의 스키마(예: 규칙 필드 구성)를 강제하는 로직은 없다.

또한 `AutomationTemplate.target_type`이 `runner`인 템플릿의 `target_ref`(러너 id)를 실제로
호출하는 실행 경로도 코드에 없다 — 등록/검증(대상 Workflow/Runner/Prompt/Policy 존재 여부)까지만
하고 "실행"은 어디서도 트리거되지 않는다. 문서 생성(§16)의 `config.get("template_id")`는 승인
정책을 읽어오는 용도로만 쓰이고, 실제 문서 생성은 항상 Workflow를 통해서만 이루어진다.

부수 발견: `app/policies/` 패키지가 저장소에 존재하지만 `__init__.py` 하나뿐인 빈 패키지다 — `Policy`
모델과 로직은 전부 `app/prompts/` 아래에 있다. 이름과 실제 위치가 어긋나 있다(CLAUDE.md의 저장소
지도에는 `policies`가 독립 feature로 나열되어 있으나 실제 구현은 `prompts` 모듈에 합쳐져 있다).

## 14. 스케줄

| 항목 | 내용 |
|---|---|
| 목적 | cron 반복 또는 1회 실행으로 Workflow(또는 system:noop)를 자동 실행 |
| 대상 사용자 | 읽기: `operator`, `admin`, `system_admin`, `auditor`. dry-run/run-now/실행이력 재시도: `operator` 이상. 생성/수정/활성화/비활성화: `admin`, `system_admin` |
| 진입 화면 | 관리자 콘솔 &gt; 스케줄 |
| API | `GET/POST /api/admin/schedules`, `GET/PUT /{id}`, `POST /{id}/enable,disable,dry-run,run-now`, `GET /{id}/runs`, `POST /runs/{run_id}/retry` |
| 데이터 모델 | `Schedule`, `ScheduleRun`(`app/schedules/models.py`) |
| n8n 관여 | `target_type=workflow`일 때만(내부적으로 `N8nWorkflowProvider.invoke` 호출). `target_type=system`(`noop`만 허용)은 n8n을 타지 않는다 |
| 필요 권한 | 위 표 참고 |
| 알림/감사 | 생성/수정/활성화/비활성화/실행/재시도 전부 감사. 실행 실패 시 스케줄 소유자에게 알림 |

동작 규칙: 활성화(`enable`)는 승인 대상이며, `system_admin`이 아니면 승인 큐로 간다(§15). 승인
집행 시점에 스케줄 정의가 요청 시점과 달라졌으면 stale로 판단해 거부한다(TOCTOU 방지,
`_execute_schedule_enable`). Misfire 정책은 `skip`(누락분 건너뜀) 또는 `run_once`(한 번만 만회
실행) 둘 중 하나이며, "누락분 전체 실행"은 스펙상 구현하지 않는다. 동시 실행 방지 정책은
`skip`(이미 실행 중이면 이번 회차 건너뜀) 또는 `allow`. 중복 실행 방지는 `ScheduleRun.idempotency_key`
UNIQUE 제약으로 삽입 경합을 해결한다(`create_run_and_enqueue`).

## 15. 승인

**주의**: 이 절은 관리자 콘솔의 `Approval` 모듈만 다룬다. 채팅에서 티켓 생성/변경 전에 사용자가
"네/승인"이라고 답하는 대화형 확인 절차(§4)는 완전히 다른, 별도의 메커니즘이다.

| 항목 | 내용 |
|---|---|
| 목적 | `system_admin`이 아닌 역할이 민감한 변경(설정, 러너/통합 설정, 사용자 역할, 스케줄 활성화, 문서 발행)을 요청하면 즉시 적용하지 않고 대기열에 넣어 `admin` 이상의 승인을 받게 한다 |
| 대상 사용자 | 조회: `operator`, `admin`, `system_admin`, `auditor`. 승인/거절: `admin`, `system_admin`. 취소: `operator`, `admin`, `system_admin`(본인 요청 또는 admin 이상) |
| 진입 화면 | 관리자 콘솔 &gt; 승인 |
| API | `GET /api/admin/approvals`, `GET /{id}`, `POST /{id}/approve,reject,cancel` |
| 데이터 모델 | `Approval`(`app/approvals/models.py`) |
| n8n 관여 | 간접적 — `document.publish` 승인 실행기가 `document_generate` Job을 다시 큐에 넣고, 그 Job이 n8n을 호출한다. 나머지 승인 유형은 n8n과 무관 |
| 필요 권한 | 위 표 참고 |
| 알림/감사 | 승인 요청 시 관리자 전원에게 알림, 승인/거절 시 요청자에게 알림, 만료 시 요청자에게 알림. 승인/거절/취소는 감사 로그 |

게이트 대상 요청 유형(`APPROVAL_EXECUTORS`, `app/approvals/service.py`): `schedule.enable`,
`runner.change_config`, `integration.change_config`, `user.role_change`, `document.publish`. 규칙:

- `system_admin`이 직접 수행하면 즉시 적용되고, 그 외 역할이 수행하면 승인 요청이 생성된다
  (`needs_approval`).
- 자기 승인은 금지되며, `self_approval_allowed` 기능 플래그(`config/feature-flags.json`)가
  켜져 있어야만 예외적으로 허용된다.
- 만료(기본 72시간)는 백그라운드에서 스윕되지만, 조회 시점에는 만료 시각이 지난 pending 건을
  즉시 `expired`로 표시한다(`approval_view`가 실시간 계산).
- 승인 집행은 요청 시점에 저장된 payload를 스냅샷과 다시 대조해 변조/변경 여부를 확인한 뒤
  실행한다(`schedule.enable`, `user.role_change` 실행기에 명시적 stale 검사가 있다).

## 16. 문서 생성

| 항목 | 내용 |
|---|---|
| 목적 | 등록된 Workflow를 통해 Notion 데이터를 요약한 문서를 미리보기 → (필요 시 승인) → 발행 |
| 대상 사용자 | 조회: `operator`, `admin`, `system_admin`, `auditor`. 생성 요청: `admin`, `system_admin` |
| 진입 화면 | 관리자 콘솔 &gt; 문서 자동화 |
| API | `GET /api/admin/documents`, `POST /api/admin/documents/generate`, `GET /{id}` |
| 데이터 모델 | `DocumentGeneration`(`app/documents/models.py`) |
| n8n 관여 | 있음 — 지정된 Workflow로 `preview`/`publish` 액션을 호출 |
| 필요 권한 | 위 표 참고 |
| 알림/감사 | 생성 요청 감사, 발행 승인 필요 시 관리자에게 알림 |

모드는 세 가지: `preview_only`(미리보기까지만), `preview_then_approve`(미리보기 후 승인
필요), `auto_publish`(품질 게이트 통과 시 즉시 발행). 요청자가 `auto_publish`를 골라도, 서버가
해당 Workflow/Template의 승인 정책(`publish_approval_required`)을 보고 승인이 필요하다고 판단하면
`preview_then_approve`로 강제 전환한다(요청자의 선택이 서버 정책을 우회할 수 없다). 품질 게이트
(`app/documents/quality.py`)는 제목/본문 존재, 최소 본문 길이(30자), 소스 행 수 &gt; 0, 주민등록번호
/카드번호/비밀정보 패턴 미검출, Notion 링크 형식(`https://.../notion.so|site`)을 검사한다. 중복
생성 방지는 `schedule_id + period + target + template_version` 조합의 idempotency 키로 막는다.

**코드로 확인한 스펙 편차**: 승인이 완료되면(`_execute_document_publish`) 검토했던 미리보기
내용을 그대로 발행하는 것이 아니라, `document_generate` Job을 `auto_publish` 모드로 다시 큐에
넣어 **미리보기를 처음부터 재생성**한 뒤 발행한다(`handle_document_generate`가 매번 preview 액션을
먼저 호출한다). 승인자가 검토한 시점과 실제 발행 시점 사이에 원본 데이터가 바뀌면, 승인자가 보지
않은 내용이 발행될 수 있다.

부수 발견: `documents/service.py`의 `EXAMPLE_TEMPLATE` 상수는 정의만 되어 있고 어디서도 참조되지
않는다(죽은 코드, 문서화 목적의 예시로 보인다). `var/generated`, `var/temp` 디렉터리가 저장소에
존재하지만 이를 참조하는 Python 코드가 없다 — 발행된 문서는 파일이 아니라 `published_ref`
(Notion URL 문자열)로만 남는다.

## 17. Notion 매핑

| 항목 | 내용 |
|---|---|
| 목적 | 플랫폼 로그인 계정(이메일)과 Notion 사람(People) 속성을 연결해, 러너가 "내 티켓"을 정확히 식별하게 한다 |
| 대상 사용자 | 조회: `operator`, `admin`, `system_admin`, `auditor`. 검증/수동매핑/해제/충돌해결: `admin`, `system_admin` |
| 진입 화면 | 관리자 콘솔 &gt; Notion 매핑. 본인 상태는 `/api/profile`의 `notion_mapping_status`로도 노출 |
| API | `GET /api/admin/notion-mapping`, `GET /{user_id}`, `POST /{user_id}/verify,map,unmap,resolve-conflict` |
| 데이터 모델 | `UserNotionMapping`(`app/notion_mapping/models.py`) |
| n8n 관여 | 있음 — 이름이 정확히 `notion-user-mapping`인 등록된 Workflow를 호출해 이메일로 Notion 사용자를 조회 |
| 필요 권한 | 위 표 참고 |
| 알림/감사 | 검증/수동매핑/해제/충돌해결 전부 감사. 알림은 없음 |

상태는 `unmapped`(연결 안 됨), `verified`(연결됨), `conflict`(동일 이메일에 후보가 2명 이상)
세 가지다. 매핑용 워크플로가 없거나 비활성이면 검증 시 캐시된 값을 지우고 `unmapped`로 되돌린다
(오래된 매핑이 잘못 유지되는 것을 막기 위함). **중요**: 매핑은 정확도를 높이는 보조 수단일 뿐,
실제 채팅에서 "내 티켓"을 처리할 때 이 매핑이 없다고 요청 자체를 막지는 않는다 — 러너가 매 요청마다
이름/이메일로 Notion People 목록과 직접 매칭을 시도하고, 정말 특정할 수 없을 때만 안내 메시지를
낸다(`app/jobs/handlers/chat_message.py`의 주석: "Admin-verified mapping remains an accuracy
booster, not a gate").

## 18. 설정

| 항목 | 내용 |
|---|---|
| 목적 | 화이트리스트로 정의된 일부 애플리케이션 설정을 즉시 변경 |
| 대상 사용자 | 조회: `operator`, `admin`, `system_admin`, `auditor`. 변경: `admin`, `system_admin` |
| 진입 화면 | 관리자 콘솔 &gt; 설정, &gt; 유지보수 |
| API | `GET /api/admin/settings`, `POST /{key}/dry-run`, `PUT /{key}`, `GET /{key}/versions`, `POST /{key}/rollback` |
| 데이터 모델 | `AppSetting`(`app/settings/models.py`) + `ConfigVersion`(object_type=`setting`) |
| n8n 관여 | 없음 |
| 필요 권한 | 위 표 참고 |
| 알림/감사 | 변경/롤백 전부 감사 |

변경 가능한 키는 `app/settings/registry.py`의 `REGISTRY`에 고정되어 있고, 그 밖의 키는 API로 바꿀
수 없다: `conversation_retention_days`, `notification_retention_days`, `ui_branding`,
`maintenance_mode`, `maintenance_message`, `password_policy`, `session_policy`,
`allowed_email_domains`. 각 값은 저장 전에 `dry-run`으로 검증할 수 있고, 이력이 남아 이전 버전으로
롤백할 수 있다(롤백도 새 버전으로 기록되는 append-only 방식). `maintenance_mode`는 `user` 역할의
채팅 쓰기만 막는다(§7).

기능 플래그(`config/feature-flags.json`, `app/core/feature_flags.py`)는 이 설정 레지스트리와
별개다: `maintenance_mode`, `document_automation_enabled`, `limited_service_actions_enabled`,
`self_approval_allowed` 네 가지가 파일 기반으로 관리되며, 이 파일을 편집하는 API는 없다(서버
파일을 직접 고쳐야 한다) — `maintenance_mode`는 설정 레지스트리 쪽 값이 실제로 쓰이고
(`app/settings/service.py`의 `is_maintenance_mode`), 기능 플래그 파일의 `maintenance_mode`는
사실상 중복 필드로 보인다(확인 필요 — 어느 쪽이 우선하는지 코드에서 하나의 소스로 못박혀 있는지는
더 깊은 추적이 필요).

## 19. 대시보드와 상태

| 항목 | 내용 |
|---|---|
| 목적 | 서비스 생존 여부, 최근 24시간 Job 처리 현황, 디스크/메모리, 인증서 만료, 마지막 백업을 한눈에 |
| 대상 사용자 | `operator`, `admin`, `system_admin`, `auditor` |
| 진입 화면 | 관리자 콘솔 &gt; 대시보드(기본 화면) |
| API | `GET /healthz`(무인증), `GET /readyz`(무인증), `GET /api/admin/dashboard` |
| 데이터 모델 | `Heartbeat`(`app/health/models.py`), 그 외 여러 모델을 집계만 함 |
| n8n 관여 | 없음(n8n은 대시보드에 "등록된 Integration의 헬스 상태"로만 나타난다) |
| 필요 권한 | 위 표 참고 |
| 알림/감사 | 없음(조회 전용) |

`web` 컴포넌트 상태는 이 엔드포인트가 응답하면 무조건 `up`으로 하드코딩되어 있다(실제 heartbeat가
아니다, `build_dashboard`의 주석 "if this endpoint responds, web is up"). `worker`/`scheduler`는
90초 이상 heartbeat가 없으면 `down`으로 표시된다. 인증서 만료일은 `settings.tls_cert_path`가
설정되어 있어야만 계산된다(운영 설정 필요, 코드 자체는 정상).

## 20. 백업과 진단

| 기능 | API | 필요 권한 | 비고 |
|---|---|---|---|
| 백업 목록 | `GET /api/admin/backups` | `operator`, `admin`, `system_admin`, `auditor` | 최근 50건 |
| 백업 생성 | `POST /api/admin/backups` | `system_admin`만 | SQLite 파일 복사 + 즉시 임시 복원 검증(`restore_test`), `var/exports/web-<타임스탬프>.sqlite3`에 저장 |
| 백업 검증 | `POST /api/admin/backups/{id}/verify` | `system_admin`만 | 체크섬 재확인 |
| 복원 안내 | `GET /api/admin/backups/restore-instructions` | `system_admin`만 | **실제 복원은 웹 API가 아니라 스크립트 전용**(`scripts/rollback-clovirone-web-assistant.sh`) — 안내 문구만 반환 |
| 진단 번들 | `GET /api/admin/diagnostics/bundle` | `admin`, `system_admin`(operator/auditor 불가) | 마스킹된 설정값, 최근 실패 Job 20건, down 상태 Integration 목록 |

데이터 모델: `Backup`(`app/backups/models.py`). 보존 정책은 성공/검증된 백업 최신 14건을 유지하고
그 외(실패 포함)는 정리한다(`apply_retention`). 파일명에 마이크로초까지 포함해 같은 초에 두 번
생성해도 충돌하지 않는다.

## 21. 파일과 첨부

플랫폼에는 범용 "파일 첨부/문서함" 기능이 없다. 파일 관련 기능은 채팅 이미지 첨부 하나뿐이다.

| 항목 | 내용 |
|---|---|
| 목적 | 채팅 메시지에 이미지를 첨부해 러너의 비전 분석에 활용, Notion 티켓에도 첨부 가능 |
| 대상 사용자 | 채팅을 쓰는 전체 역할 |
| 진입 화면 | `/` 채팅 화면의 첨부 버튼(📎), PNG/JPEG/WebP, 최대 3장 |
| API | `POST /api/conversations/{id}/messages`의 `attachments` 필드(base64) |
| 데이터 모델 | 저장하지 않음 — `Message.structured_payload_json`에는 파일명/타입만 남고, 실제 바이트는 `Job.payload_json`에만 잠깐 존재 |
| n8n 관여 | 있음 — 러너가 비전 분석 후 Notion에 첨부 |
| 필요 권한 | 로그인 상태만 |
| 검증 | 장당 3MB, 합계 6MB, 매직바이트로 실제 이미지인지 확인(확장자/선언 타입만으로 속일 수 없음), 파일명 화이트리스트 정규식 |
| 보존 | 이미지 바이트는 플랫폼에 영속 저장하지 않는다(스펙 §13 확장, "서버 미보관"). 성공/실패가 확정되면(`strip_attachment_bytes`) Job payload에서 즉시 스트립되고, 재시도 대기 중인 실패 Job에만 24시간 동안 남아 있다가 보존 작업(`strip_stale_job_attachments`)이 정리한다 |

관련 없는 발견: 저장소에 `var/exports`(백업이 실제로 사용, §20), `var/generated`, `var/temp`
디렉터리가 있는데, `generated`와 `temp`는 이를 참조하는 코드가 없다(확인 필요 — 향후 문서 파일
출력이나 임시 작업용으로 예약된 디렉터리로 추정되나 현재는 미사용).

---

## 코드에 없는데 문서에만 있는 것

- 이메일/Teams 알림 채널: `docs/EXTENSION_GUIDE.md`가 `NotificationProvider.notify()` 형태로
  이메일/Teams 알림을 만들 수 있다고 안내하지만, 이는 문서 자체가 "향후 확장 방법"으로 명시한
  것이라 과장된 문서-코드 불일치는 아니다. 다만 현재 알림 채널은 인앱뿐이라는 점은 분명히 해둔다
  (§8).
- 그 밖에 이번 조사에서 읽은 `docs/PROMPT_POLICY_MANAGEMENT.md`, `docs/RUNNER_MANAGEMENT.md`,
  `docs/NOTION_MAPPING.md`, `docs/DOCUMENT_AUTOMATION.md`, `docs/SCHEDULER.md`은 코드가 실제로
  하는 일과 일치했다(오히려 Runner Registry 문서는 "메타데이터로만 관리, 실제 dispatch 경로
  아님"이라고 스스로 정직하게 적어 두고 있었다). 문서가 코드보다 더 강하게 주장하는 항목은
  발견하지 못했다.
- `CLAUDE.md`의 저장소 지도는 `policies`를 `prompts`와 별개의 feature 디렉터리처럼 나열하지만,
  실제로는 `app/policies/`가 빈 패키지이고 `Policy` 모델/서비스/라우터는 전부 `app/prompts/`
  안에 있다(§13). 문서가 구조를 실제보다 더 분리된 것처럼 묘사하는 유일한 사례로 확인했다.

## 구현됐는데 화면에서 도달할 수 없는 것

- **러너 레지스트리 → 실제 업무 트래픽 미연결**: Runner 등록/활성화/헬스체크는 화면에서 전부
  가능하지만, 실제 채팅 요청은 이 레지스트리를 전혀 거치지 않고 n8n 웹훅 한 곳으로만 흐른다.
  `RunnerHttpProvider.invoke`를 호출하는 코드는 관리자 콘솔의 "테스트" 버튼뿐이다(§11). 화면
  자체는 도달 가능하지만, 그 화면에서 하는 일(등록, 활성화)이 실제 업무 경로에 아무 효과가
  없다는 뜻에서 "기능이 완결되지 않은 채 도달 가능"한 사례다.
- **Prompt/Policy 발행이 러너에 반영되지 않음**: draft→published 수명주기 전체가 화면에서
  동작하지만, 발행된 콘텐츠를 실제로 읽어가는 소비자(러너, n8n)가 코드에 없다(§13). 화면의
  "발행" 버튼은 도달 가능하고 정상 동작하지만 결과가 실제 업무에 반영되지 않는다.
- **AutomationTemplate(target_type=runner)의 실행 경로 없음**: 템플릿을 만들고 Runner를 대상으로
  지정할 수 있지만, 그 템플릿을 "실행"하는 API/Job/스케줄 대상이 코드 어디에도 없다(§13). 문서
  생성(§16)만 Workflow 대상 템플릿을 참조하며, 그나마도 승인 정책 조회 용도일 뿐이다.
- **일반 사용자용 알림 UI 부재**: 알림 API(`/api/notifications`)는 역할 제한이 없어 `user`도 호출할
  수 있지만, 채팅 화면(`chat.html`/`chat.js`)에는 알림 벨/배지/목록을 보여주는 UI 요소가 없다
  (관리자 콘솔에만 알림 섹션이 있다). 계정 잠금 알림 등을 받는 일반 사용자는 이를 확인할 화면이
  없다(§8).
- **기능 플래그 파일 편집 UI 없음**: `config/feature-flags.json`의 네 값(`maintenance_mode`,
  `document_automation_enabled`, `limited_service_actions_enabled`, `self_approval_allowed`)을
  바꾸는 API/화면이 없다 — 서버 파일을 직접 편집해야 한다(§18). `maintenance_mode`는 설정
  레지스트리 쪽에 동일 이름의 값이 따로 있어 관리자 콘솔에서 그 값만 바꿀 수 있다.
