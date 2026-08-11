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
| 부서/직책 관리(org) | admin+ | — | admin+ |
| 개발자 월간 리포트(reports) | admin, system_admin, auditor | — | (조회 전용) |
| 자유게시판(board), 놀이(games), 문서 탭(team_docs), 티켓(tickets) | 로그인 사용자 전원 | — | 로그인 사용자 전원 |

board/games/team_docs/tickets는 사내 협업 영역이라 로그인 사용자 전원이 읽고 쓴다.
쓰기는 모두 CSRF를 요구하고, 남의 객체 수정은 소유권 확인으로 막는다(IDOR 방어).
games와 team_docs는 기능 플래그(`require_games_enabled` / `require_team_docs_enabled`)로
추가 게이트된다.

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
- 게임 AI 퀴즈 생성이 러너로 나갈 때 쓰는 토큰도 참조 이름 secret이다:
  `game_runner_token_ref`(기본 `game_runner_token`)로 `secrets_dir` 파일에서만 읽고,
  `OutboundClient`(allowlist=runners)가 주입한다. DB나 코드에 평문이 없다
- CLI는 비밀번호를 인자로 받지 않음 — stdin/getpass 전용

## CSP 및 응답 헤더 (spec §25.6, **2026-08-04 사용자 지시로 완화됨**)

**DOC-01**: 아래는 예전(도입 당시) 정책이 아니라 **현재 실제로 나가는 값**이다 — `default-src
'self' https:; script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; style-src 'self'
'unsafe-inline' https:; ...`. 사용자가 "CDN·웹폰트·외부 라이브러리를 UI 품질에 도움이 되면
자유롭게 쓰라"고 지시해 `script-src`/`style-src`/`font-src`/`img-src`/`frame-src`를 열었다.
**`connect-src`는 `'self'`로 유지한다**(2026-08-05 되돌림) — 저장소 전체에 외부
fetch/XHR/WebSocket 호출이 없어 여는 이유가 없고, XSS가 나면 `/api/me`·감사 CSV를 임의
호스트로 실어 보낼 유출 경로만 열기 때문이다. 정책 원문·근거는 `app/core/middleware.py`의
`CSP_POLICY`가 정본이다(문서를 다시 베끼지 않는다 — 두 벌이 되면 한쪽만 갱신된다).

`RequestContextMiddleware`가 모든 응답에 이 헤더를 부여한다.

**무엇을 잃었는가(정직하게)**: `script-src 'self'`가 예전엔 XSS 방어의 축이었다 — 지금은
없다. 대신 계속 지키는 것: ①서버 데이터를 `innerHTML`에 안 넣는다(React 이스케이프/
`textContent` 전용) ②사용자 입력을 스크립트·스타일 문자열에 이어 붙이지 않는다 ③href/src
스킴 검사(`app/core/safe_url.py` + `frontend/src/lib/safeUrl.js`) — `'unsafe-inline'` 아래
에서는 `javascript:` URI가 실행되므로 이게 없으면 링크 하나가 곧 XSS다.

`X-Content-Type-Options: nosniff` / `X-Frame-Options: DENY` / `Referrer-Policy: same-origin`
/ `Cache-Control: no-store`(정적 자원 제외)는 그대로 유지. 요청 본문은 256KB 제한
(nginx `client_max_body_size 256k`와 이중 방어). 에러는 표준 envelope로만 —
스택 트레이스 비노출 (spec §25.2).

## 파일 업로드 (spec §22)

자유게시판 첨부(이미지, PDF)가 유일한 업로드 표면이다. 통제는 `app/core/uploads.py`에 모여 있다.

- **형식은 매직바이트로 판정**한다 — 선언된 Content-Type이나 사용자 확장자를 믿지 않는다
  (`sniff_media_type`). 허용은 PNG/JPEG/GIF/WebP와 PDF뿐, 그 밖은 422로 거부
- **저장명은 서버가 만든 UUID + 판정된 확장자**다. 사용자 파일명은 표시(다운로드 시
  Content-Disposition)로만 새니타이즈해 두고 경로 구성에는 절대 쓰지 않는다(경로 traversal 차단)
- **크기·개수 상한**: 파일당 최대 10MB(`MAX_UPLOAD_BYTES`), 글당 최대 5개
  (`MAX_ATTACHMENTS_PER_POST`). 라우터가 `MAX_UPLOAD_BYTES+1`만큼만 읽어 초과를 막고,
  256KB 본문 제한과 별개다
- 파일은 **웹 루트 밖**(`data_dir/uploads/board/<post_id>`)에 저장하고, 서빙은 인증된
  엔드포인트가 담당한다. 응답은 `X-Content-Type-Options: nosniff` + inline이며 서버가
  판정·저장한 media_type만 실어 보낸다(실행 불가). 저장명은 서빙 시 서버 패턴으로 재검증하고,
  해석된 경로가 board 업로드 디렉터리 안임을 확인한 뒤에만 반환한다
- 업로드는 CSRF를 요구한다(`Depends(require_csrf)`)

문서(team_docs)와 티켓 본문은 리치 텍스트다. 길이 상한을 스키마에서 강제하고
(`app/board/schemas.py`의 `MAX_BODY` 등), Notion으로 내보낼 때는 `core/notion_blocks.py`의
`markdown_to_blocks`로 블록화한다. 프런트 렌더는 `textContent` 전용이라(불변 §6) 본문에 담긴
마크업이 실행되지 않는다.

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
