# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

사내 구성원 전용(폐쇄망). 현재 실사용 계정 23명, `docs/PRODUCTIZATION_ARCHITECTURE.md` §0에서
"한 회사 + 여러 부서, 향후 최대 약 1000명"으로 확장 방향이 확정되어 있다(완전 멀티테넌시는
만들지 않기로 결정됨).

역할은 5단계이며 서버가 정본으로 강제한다(`app/core/authz.py`):
`user` · `operator` · `auditor` · `admin` · `system_admin`.
조직/부서 축이 실재하며 행 단위 스코핑이 걸린다(`app/core/scope.py`).

**사용 상황(2026-08-18 사용자 확인)**: **하루 종일 브라우저 탭에 띄워두는 상시 도구**다.
잠깐 들렀다 나가는 도구가 아니라, 업무 중 수시로 돌아와 상태를 확인하고 다음 일을 고르는 자리다.

**주 작업(2026-08-18 사용자 확인)**: 티켓 · 문서 · AI 도우미와 채팅 · 프로젝트와 스프린트가
**모두** 주 사용처다. 어느 하나가 부수 기능이 아니다.

## Product Purpose

사내에 흩어져 있던 업무 도구를 하나의 웹 콘솔로 모은다. 기존 n8n 기반 AI 업무 도우미를
손상 없이 확장하는 것이 출발점이었고(`docs/ARCHITECTURE.md`), 지금은 티켓 · 문서 · 프로젝트 ·
스프린트 · 팀 공간 · AI 도우미 · 관리자 운영을 한곳에서 처리한다.

성공은 "사용자가 여러 도구를 오가지 않고 이 콘솔 안에서 하루 업무를 판단하고 처리하는 것"이다.

## Positioning

**Notion을 정본 데이터 소스로 두고 그 위에 업무 실행 계층을 올린 사내 플랫폼**이다.
티켓 · 문서 · 프로젝트는 Notion에서 주기적으로 미러링되고(`app/*/sync.py`,
`document_cache` · `ticket` · `project`), 포털은 그 미러 위에 권한 스코핑 · 검색 · 승인 ·
자동화 실행 · AI 도우미 · 감사 기록을 붙인다.

**방향(2026-08-18 사용자 확인)**: **사용자가 포털 안에서 대부분을 끝내는 것이 목표다.**
Notion은 뒤에 있는 저장소이고, 사용자는 포털만 보고 일할 수 있어야 한다.
따라서 포털 내 조회뿐 아니라 **작성 · 편집 경험이 1급 요구사항**이다.
"원본 열기"는 탈출구로 남지만 주 동선이 아니다.

경쟁 제품이 그대로 복사할 수 없는 지점: 폐쇄망 단일 서버에서 Notion 미러 · n8n 워크플로 ·
Claude Runner · 사내 RBAC · 감사 로그가 한 트랜잭션 경계 안에서 맞물려 돈다.

## Operating Context

- **접속**: `https://clovirone-ai.gooddi.lab` (사내망 전용, self-signed 인증서).
- **배포 형태**: 단일 서버. Nginx(TLS 종단) → uvicorn 127.0.0.1:8080 → Worker 프로세스.
  폐쇄망이라 설치는 git clone 또는 번들 scp로 한다.
- **외부 연동**: Notion(정본 데이터), n8n(워크플로 엔진), Claude Runner(AI 실행),
  SMTP(메일, 현재 미설정 상태).
- **화면 환경**: 사무용 데스크톱 모니터. QA 캡처가 1366 · 1920 · 2560 · 3840 폭에서 돈다.
  라이트/다크 두 테마를 실제로 쓴다.
- **언어**: 사용자 노출 문구는 한국어. UTC로 저장하고 Asia/Seoul로 표시한다.
- **문서 규약**: 오류 문구와 표준 동사는 `docs/UX_WRITING.md`가 정본이다.

## Capabilities and Constraints

**기능 범위**: 사용자 콘솔 27개 Route, 관리자 콘솔 46개 Route.
티켓(내/팀/미할당/상세/생성) · 문서(목록/상세/휴지통) · 프로젝트(목록/상세/WBS/주간/지표) ·
스프린트 회의 · AI 도우미 채팅 · 팀 채팅방 · 자유게시판 · 아이디어 제안 · 놀이 ·
알림 · 승인 · 프로필/활동/업무량, 그리고 관리자 측 운영 · 사용자와 권한 · 자동화 · 연동 ·
감사 · 시스템 설정.

**기술 제약(`CLAUDE.md` §3 불변 규칙)**:
- FastAPI **sync** 핸들러만. `async def` 라우트 핸들러와 `aiosqlite` 금지.
- 외부 HTTP는 `app/core/http_client.py`의 `OutboundClient` 단일 관문만 경유.
- secret은 DB · 응답 · 로그 · 감사에 평문으로 남기지 않는다.
- opaque session + CSRF. **권한 판단은 서버가 정본이고 프런트 표시는 보조일 뿐이다.**
- 서버 데이터를 `innerHTML`로 주입하지 않는다. inline script 금지.
- UTC 저장. `app/core/db.py`의 명시적 transaction 규약 유지.
- Runner 코드 웹 편집 · 임의 shell 실행 · secret 평문 표시 · 범용 systemd 제어를
  제품 기능으로 추가하지 않는다.
- 프런트 빌드 산출물을 git에 커밋한다(서버에 Node가 없다). 초기 로드 gzip 예산 280KB.

**정책 값의 위치**: `app/settings/registry.py::REGISTRY`(22개 키)가 관리자가 바꿀 수 있는
정책의 정본이다. 세션 만료 · 계정 잠금 · 비밀번호 · 보존 기간 · SMTP · 유지보수 모드 등.
동기화 주기는 아직 이 레지스트리에 없고 env 기본값으로만 존재한다(개선 대상).

**명시적으로 미결정**: 완전 멀티테넌시(실제 두 번째 회사가 생기기 전에는 만들지 않는다).

## Brand Commitments

- **제품명**: Clovir Assist (내부 코드명 ClovirONE Web Assistant). 부제 "SMART WORKSPACE ASSISTANT".
- **로고·워드마크**: 네잎클로버 마크 + 워드마크. `app/static/brand/logo/`, `frontend/src/ui/BrandLogo.jsx`.
  **변경하지 않는다.**
- **마스코트 '클로비(Clovi)'**: 사용자가 2026-08-18에 **"제품의 정체성"**이라고 확인했다.
  최대한 유지한다. 포즈 PNG 11종(`app/static/brand/mascot/`). 런타임 프레임 합성은 금지되며
  `scripts/static_checks.sh`가 이를 검사한다.
- **로그인 화면과 로그인 직후 폭죽(confetti)**: 사용자가 2026-08-18에 **"없어지면 안 되는
  디자인"**이라고 확인했다. `frontend/src/app/LoginHandoff.jsx`.
- **계정별 화면 강조색 선택 기능**: 기존 제품 기능이다(`/my-display`, `ACCENT_PRESETS`).
- **문체**: 한국어. `docs/UX_WRITING.md`의 오류 문구 규칙과 표준 동사표를 따른다.
  사용자 노출 문구에 가운뎃점과 em 대시를 쓰지 않는다(`scripts/check_user_text.py`가 검사).

## Evidence on Hand

실제 운영 데이터가 있다. 목업이나 시드가 아니다.

- 사용자 23명, 프로젝트 22건, 문서 107건, 티켓 다수(스프린트 화면에 수백 행).
- QA 캡처 71화면 × 라이트/다크 × 1366~3840 폭: `dist/ui-qa/responsive_4k/`.
- Playwright 기반 UI QA 하네스: `scripts/ui_qa/`(라우트 레지스트리 · 대비 · 키보드 ·
  시맨틱 · 실패 상태 · 적대적 데이터).
- Vitest 304개 파일, 백엔드 pytest 2,900건대.
- 승인된 TEST 서버 `10.100.64.71`에서 실제 배포와 브라우저 검증이 가능하다.

**지어내면 안 되는 것**: 고객사 사례 · 벤치마크 · 가격 · 라이선스 · 외부 도입 실적.
이 제품은 사내 도구이며 그런 근거는 존재하지 않는다.

## Product Principles

1. **서버가 권한의 정본이다.** 화면에서 감추는 것은 통제가 아니다. 프런트 표시는 서버 판정과
   일치해야 하고, 어긋나면 서버가 옳다.
2. **Notion은 저장소이고 포털이 업무 자리다.** 사용자가 포털을 벗어나야만 일이 되는 상태를
   남기지 않는다.
3. **상시 도구답게 동작한다.** 하루 종일 열려 있는 화면이므로 정보 밀도와 상태 변화 가시성이
   장식보다 우선한다.
4. **내부 구현은 사용자의 문제가 아니다.** 환경변수명 · 파일 경로 · 내부 상태 키 · 원시 오류를
   일반 화면의 주 정보로 노출하지 않는다. 필요한 기술 정보는 권한 있는 사람에게 별도로 준다.
5. **되돌릴 수 없는 일은 그 무게만큼 다룬다.** 시스템에 영향을 주는 작업은 실행 전에 무엇이
   바뀌는지 알 수 있어야 하고, 실행 후 실제 상태를 다시 확인한다.

## Accessibility & Inclusion

- 한국어 텍스트가 기본이다. 줄바꿈은 `word-break: keep-all` 규약을 따른다.
- 키보드만으로 조작 가능해야 한다. QA 하네스에 `keyboard.py` · `semantics.py` · `contrast.py`가
  이미 있고 heading 순서 검사(`heading-order.test.jsx`)가 돈다.
- 색만으로 상태를 전달하지 않는다. 라이트/다크 양쪽에서 대비를 각각 검증한다
  (`theme-link-contrast.test.js`가 4개 강조색 × 2개 모드를 계산한다).
- `prefers-reduced-motion`을 존중한다.
