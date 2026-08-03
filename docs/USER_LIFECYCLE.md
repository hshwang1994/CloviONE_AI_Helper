# USER LIFECYCLE — 계정 수명주기

계정 관련 모든 로직은 `app/users/service.py` 서비스 계층에 있고, 웹 관리자 API와
CLI(`python -m app.cli.user_cli`)가 이를 공유한다 — 어느 경로로 하든 동작이 같다.
셀프 가입은 없다. 계정 생성/변경은 admin 이상(또는 서버 CLI) 전용이다.

## 1. 생성 (admin)

- 경로: 관리자 콘솔 **사용자 → 추가**, `POST /api/admin/users`, 또는
  `user_cli add <email> --name <이름> [--role ...]`
- 검증: 회사 이메일 도메인(`allowed_email_domains`, 기본 `goodmit.co.kr`)만 허용,
  이메일 중복 거부, 이름 필수, 역할은 5종 중 하나
- 비밀번호를 지정하지 않으면 정책을 만족하는 **임시 비밀번호가 자동 생성**되어
  응답/터미널에 **한 번만** 표시된다(로그 저장 금지). CLI에서 직접 지정하려면
  `--password-stdin`(stdin 전용 — 인자로는 절대 받지 않음)
- 부서/직책을 함께 배정할 수 있다: API `department_id`/`title_id`, CLI `--department`/`--title`
  (CLI는 **등록된 이름**만 받아 명부 항목으로 해석한다 — 명부 관리는 아래 `dept-*`/`title-*` 참조)
- 생성된 계정은 `must_change_password=True` — 첫 로그인 시 변경 강제
- 이미 등록된 이메일은 거부되며, 그 주소를 **보관된(아카이브된) 계정**이 쥐고 있으면
  `archived_email_conflict`로 막힌다 — 목록에 안 보이는 계정이 원인이므로 복구를 안내한다(아래 §5)

## 2. 첫 로그인 + 강제 비밀번호 변경

`must_change_password`가 설정된 동안 API 의존성 `get_current_user`가 403
`password_change_required`를 반환한다. 허용되는 것은 로그인/로그아웃/비밀번호
변경/`/api/me` 뿐이며, HTML 페이지는 `/change-password`로 리다이렉트된다.

변경 조건: 현재 비밀번호 일치 + 정책(12자, 3종 조합) + 기존과 다른 값.
변경 성공 시 **다른 모든 세션 폐기 + 현재 세션 회전**(새 토큰/CSRF 발급).

## 3. 역할 (RBAC)

`user / operator / admin / auditor / system_admin` — 의미는 `docs/SECURITY.md` 참조.

- 변경 경로: `PATCH /api/admin/users/{id}` 또는 `user_cli set-role`
- **admin/system_admin으로 올리는 변경은 승인 대상** (spec §20):
  system_admin이 직접 하면 즉시 적용, 그 외에는 202 + pending 승인 생성 →
  Approvals에서 admin+가 결재하면 실행된다 (자기 승인 금지)
- 역할이 실제로 바뀌면 **그 사용자의 모든 세션이 즉시 폐기**된다 — 권한 상승/하강이
  이전 세션에 남지 않게 하기 위함
- CLI `set-role`은 서버 관리자의 비상 경로로 승인 게이트를 거치지 않는 대신
  감사 로그(`cli.user.set_role`)가 남는다

## 4. 비활성화 / 재활성화

- `POST /api/admin/users/{id}/disable` / `enable`, 또는 `user_cli disable|enable`
- 비활성화 즉시 **모든 활성 세션 폐기** (spec §11.5) — 로그인 자체가
  `account_disabled`로 거부된다. 데이터(대화, 감사 이력)는 보존된다. 계정을 아예
  명부에서 빼려면 삭제 대신 **보관(아카이브)** 을 쓴다(아래 §5) — 하드 삭제 API는 없다
- 세션만 정리하고 싶으면 `POST /api/admin/users/{id}/revoke-sessions`
  (CLI: `revoke-sessions`). 활성 세션 목록은 `GET /api/admin/users/{id}/sessions`
  (CLI: `sessions`)

## 5. 보관 / 복구 (아카이브 = 소프트 삭제, 0014)

하드 삭제 대신 행을 남기고 `users.archived_at`(마이그레이션 0014)을 채워 목록·검색·
로그인에서만 빼는 소프트 삭제 경로다. 복구하면 정확히 보관 전 상태로 돌아온다.

- `POST /api/admin/users/{id}/archive` / `unarchive`, 또는 `user_cli archive|unarchive`
- 보관은 수명주기 변경이라 disable과 같은 안전장치를 전부 거친다: 권한 경계
  (`ensure_can_manage_target`), 마지막 system_admin 보호(§7), 자기 자신 금지. 보관 즉시
  **모든 세션 폐기** + 소유한 스케줄 비활성화. `active`는 건드리지 않는다(복구 시 그대로 복원)
- 목록/검색은 보관된 계정을 **기본으로 숨긴다**. `GET /api/admin/users?archived=true`(CLI
  `list --archived`)로 '보관함'을 열어야 보이고, 거기서만 복구할 수 있다
- 보관된 이메일은 유일 제약을 계속 쥐고 있어, 같은 주소로 새로 만들려 하면 위 §1의
  `archived_email_conflict`로 막힌다 — 새로 만들지 말고 복구한다

## 6. 비밀번호 재설정

- `POST /api/admin/users/{id}/reset-password` 또는 `user_cli passwd <email> --temp`
- 새 임시 비밀번호(또는 관리자가 지정한 정책 준수 비밀번호)로 교체하고:
  `must_change_password=True` 재설정, 실패 카운트·잠금 해제, **전 세션 폐기**
- 평문은 응답에 정확히 1회 노출 — 감사 로그에는 마스킹되어 저장

## 7. 로그인 실패 잠금 / 해제

- 연속 실패 5회(`login_max_failures`) → 15분(`login_lock_seconds=900`) 잠금.
  잠금 발생 시 본인 + 관리자에게 알림 생성
- 해제: 시간 경과 자동 해제, 또는 `POST /api/admin/users/{id}/unlock` / `user_cli unlock`
  (실패 카운트도 함께 초기화)

## 8. 마지막 system_admin 보호 (spec §32.8)

`ensure_not_last_system_admin`이 다음을 서버에서 차단한다:

- 유일한 활성 system_admin의 **비활성화**
- 유일한 활성 system_admin의 **역할 변경(강등)**

오류: 409 "마지막 system_admin 계정은 비활성화하거나 역할을 변경할 수 없습니다."
이 보호는 웹 API와 CLI 모두 동일하게 적용된다(같은 서비스 함수).
유일 system_admin이 잠기거나 비밀번호를 잃은 경우의 복구는 `docs/RUNBOOK.md` #7.

## CLI 요약 (`python -m app.cli.user_cli`)

| 명령 | 설명 |
|---|---|
| `add <email> --name N [--role R] [--department 부서] [--title 직책] [--password-stdin]` | 생성 (기본: 임시 비밀번호 자동, 부서/직책은 등록된 이름) |
| `list [--archived]` / `show <email>` | 목록(기본 보관 제외, `--archived`로 보관함) / 상세 |
| `enable` / `disable <email>` | 활성/비활성 (세션 폐기 포함) |
| `archive` / `unarchive <email>` | 보관(소프트 삭제 — 목록·로그인 제외) / 복구 |
| `passwd <email> [--temp]` | 비밀번호 재설정 (stdin 또는 임시 발급) |
| `unlock <email>` | 잠금 해제 |
| `sessions <email>` / `revoke-sessions <email>` | 세션 조회 / 전체 폐기 |
| `set-role <email> <role>` | 역할 변경 (비상용) |
| `dept-add --name N` / `dept-list` | 부서 명부 추가 / 목록(사용자 수 포함) |
| `title-add --name N` / `title-list` | 직책 명부 추가 / 목록(사용자 수 포함) |
| `verify-notion <email>` | Notion 매핑 재검증 |

모든 CLI 변경은 `cli.user.*` action으로 감사 기록된다.
