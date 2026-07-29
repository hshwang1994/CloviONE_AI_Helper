# SECURITY — 보안 모델 (spec §25 매핑)

모든 통제는 **서버 측**에서 강제된다. UI에서 버튼을 숨기는 것은 통제가 아니다 (spec §25.5).

## 인증 (spec §25.1)

- **비밀번호 해시**: Argon2id (`argon2-cffi` 라이브러리 기본 파라미터), `app/core/security.py`
- **비밀번호 정책**: 최소 12자 + 대문자/소문자/숫자/특수문자 중 3종 이상
  (`validate_password_policy`). 임시 비밀번호는 `secrets` 모듈로 생성되고 정책을 만족할 때까지 재생성
- **첫 로그인 강제 변경**: `must_change_password=True`로 생성 —
  `get_current_user` 의존성이 변경 전에는 403 `password_change_required`를 반환
  (login/logout/change-password/me만 예외)
- **로그인 잠금**: 연속 실패 `login_max_failures`(기본 5)회 → `locked_until` =
  now + `login_lock_seconds`(기본 900s). 잠금 시 본인 + admin에게 알림.
  IP 기준 rate limit 별도(토큰 버킷, 약 10회/분, spec §25.2)
- **오류 메시지**: 존재하지 않는 계정과 비밀번호 오류를 구분하지 않음 (`invalid_credentials`)

## 세션 (spec §11.3)

- Opaque 토큰 256bit(`token_urlsafe(32)`), DB에는 **SHA-256 해시만** 저장
- 쿠키 `clovirone_session`: `HttpOnly`, `SameSite=Strict`, `Secure`(운영), path=/
- **idle timeout 30분**(`session_idle_timeout_seconds=1800`),
  **absolute timeout 8시간**(`session_ttl_seconds=28800`)
- **회전(rotation)**: 로그인·비밀번호 변경 시 새 토큰 발급. 비밀번호 변경은
  다른 모든 세션 폐기(`revoke_all_for_user`) 후 회전
- 계정 비활성화·역할 변경 시 전체 세션 즉시 폐기 (spec §11.5)

## RBAC (spec §10, §25.5)

역할 5종 — 계층형 user(1) < operator(2) < admin(3) < system_admin(4),
**auditor는 계층 밖의 읽기 전용 분기**로 명시된 곳에만 부여된다 (`app/users/models.py`).

| 영역 | 읽기 | 운영(테스트/헬스/재시도) | 쓰기 |
|---|---|---|---|
| 레지스트리(Integration/Runner/Workflow), Prompt/Policy/Template, Schedule, Documents | operator+, auditor | operator+ | admin+ |
| 사용자 관리, 승인 결정 | admin+ | — | admin+ |
| 감사 로그 | admin, system_admin, auditor | — | (조회 전용) |
| Job 큐 | operator+ | operator+ (retry/cancel) | — |
| 백업 생성/검증, 복원 안내 | operator+ 읽기 | — | **system_admin 전용** |

강제 지점은 라우터의 `Depends(require_roles(...))` — 요청마다 서버에서 재평가된다.

## CSRF (spec §25.6)

- 세션마다 CSRF 토큰 발급(로그인/`/api/me` 응답에 포함)
- 모든 변이 요청(GET/HEAD/OPTIONS 외)은 `X-CSRF-Token` 헤더 필수 —
  `require_csrf`가 `secrets.compare_digest`로 비교, 실패 시 403 `csrf_failed`
- 쿠키 `SameSite=Strict`가 1차 방어, 헤더 토큰이 2차 방어

## SSRF 아웃바운드 통제 (spec §25.3)

- 허용 목록 3종: `allowed-services.json` / `allowed-runners.json` / `allowed-workflows.json`
  (`config_dir`, 운영은 /etc/clovirone-web-assistant). **host:port 정확 일치**,
  http/https만, URL userinfo 금지, 파일 없으면 **전면 거부**(allow-all 아님)
- `OutboundClient`(`core/http_client.py`)가 유일한 아웃바운드 경로:
  app/ 내 httpx import는 이 모듈뿐(정적 테스트로 강제), **호출 시점에** allowlist 검사,
  `follow_redirects=False`, `trust_env=False`(프록시 환경변수 무시)
- 레지스트리 저장 시 URL 검사는 UX일 뿐 — 보안 경계는 호출 시점 검사다

## Secret 처리 (spec §25.4)

- DB·API 응답·로그에는 secret **참조 이름만** 존재. 값은
  `secrets_dir`(운영: /etc/clovirone-web-assistant/secrets, root:clovirone-web 0640) 파일
- `SecretValue`는 repr/str/format을 모두 `***`로 마스킹 — 로깅 사고로도 유출 불가
- 인증 주입은 `OutboundClient` 내부에서만: `bearer` → `Authorization`,
  `api_key_header` → `X-API-Key`
- CLI는 비밀번호를 인자로 받지 않음 — stdin/getpass 전용

## CSP 및 응답 헤더 (spec §25.6)

`RequestContextMiddleware`가 모든 응답에 부여:

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self';
  img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none';
  base-uri 'self'; frame-ancestors 'none'; form-action 'self'
X-Content-Type-Options: nosniff / X-Frame-Options: DENY / Referrer-Policy: same-origin
Cache-Control: no-store (정적 자원 제외)
```

인라인 JS/CSS는 어디에도 없다(모두 `/static` 파일). 요청 본문은 256KB 제한
(nginx `client_max_body_size 256k`와 이중 방어). 에러는 표준 envelope로만 —
스택 트레이스 비노출 (spec §25.2).

## 감사 로그와 마스킹 (spec §25.7)

- `record_audit`: actor, action, object, before/after 스냅샷, result, client_ip, request_id
- 스냅샷은 저장 전 재귀 마스킹 — 키가 `password|secret|token|credential|api[_-]?key`에
  걸리면 값이 `***`. 비밀번호 해시는 스냅샷에 아예 포함되지 않음(`user_snapshot`)
- `config_versions` 스냅샷은 복원 가능해야 하므로 마스킹하지 않지만,
  secret은 참조 이름만 담기므로 값 유출이 없다

## 승인 게이트 (spec §20)

필수 승인 대상: **Schedule 활성화**, **Runner 설정 변경**, **admin 이상으로의 역할 변경**,
**문서 발행**. system_admin은 즉시 적용, 그 외 권한자는 pending 승인 생성(202).
승인 시 저장된 payload를 동일 서비스 경로로 **정확히 1회 재실행**(executor),
자기 승인은 `self_approval_allowed` 플래그가 없는 한 금지. 기본 만료 72시간.

## 신원 위조 방지 (spec §11.2, §12.3)

n8n으로 나가는 requester(user_id/email/name)는 **서버 세션의 사용자에서만** 구성된다.
브라우저가 보낸 어떤 신원 값도 신뢰하지 않으며, Notion user id도 브라우저에서 받지 않는다.
