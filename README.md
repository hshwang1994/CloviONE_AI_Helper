# ClovirONE Web Assistant

사내 업무 자동화 웹 플랫폼. 기존 ClovirONE AI 업무 도우미(n8n + Claude Runner + Notion)를
손상 없이 확장한 웹 콘솔로, 사용자 셀프서비스와 관리자 운영을 한곳에서 제공한다.

## 기능

### 사용자 콘솔 (`/`)
- **내 업무(홈)** — 내 티켓 요약 대시보드 + 내 게시판 활동 위젯(내 글, 받은 댓글, 조회 수)
- **티켓** — 내 티켓 / 미할당 티켓 / 새 티켓(설명은 제목, 목록, 구분선, 이모지를 지원하는 본문 에디터 + 미리보기)
- **AI 도우미** — 로그인 사용자 신원을 세션에서 자동 식별해 n8n/러너로 전달하는 채팅(위조 불가)
- **문서** — Notion "문서" 데이터베이스를 로컬로 미러링해 검색/필터로 보고, 새 문서를 생성(본문 에디터 + 미리보기, 장애 격리 캐시)
- **팀 공간**
  - **놀이** — 폴링 기반 실시간 게임 7종(랜덤 추첨, 빠른 투표, 랜덤 팀 나누기, 숫자 눈치, 사다리타기, 가위바위보, 실시간 퀴즈). 결과는 서버가 확정하고 승자 공개 시 축포 연출
  - **자유게시판** — 글/댓글/반응/첨부(이미지, PDF), 카테고리별 배지 색

### 관리자 콘솔 (`/admin`)
사용자/부서/직책/Notion 사용자 연결(RBAC 5역할), Integration/Runner/Workflow 레지스트리,
Prompt/Policy/Template 버전 관리, 스케줄러, 승인, 감사 로그, 백업, 유지보수 모드,
개발자 월간 리포트.

### AI 퀴즈 생성 (다크런치)
실시간 퀴즈의 문제를 주제만 주면 러너(Claude Code CLI)가 생성한다. `game_ai_enabled`
기능 플래그로 게이트되며 기본은 OFF(켜기 전까지 비활성).

## 기술 스택

- **백엔드**: Python 3.12, FastAPI(**sync 핸들러**), SQLAlchemy 2.0(sync), Alembic, SQLite(WAL), Argon2id
- **프런트엔드**: React 18 + Vite(HashRouter). 빌드 산출물을 Jinja2 셸에서 서빙하며, **런타임에는 외부 CDN/폰트/네트워크를 쓰지 않는다**(CSP `script-src 'self'`). npm은 빌드에만 사용
- **러너**: Python 표준 라이브러리 HTTP 서버 + Claude Code CLI(`runner/claude-work-assistant/assistant.py`)
- **인프라**: Nginx(자체 서명 TLS), systemd. 유일한 바이너리 의존성은 `argon2-cffi`

## 로컬 개발

```bash
# 백엔드
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt        # Windows (Linux: .venv/bin/…)
cp .env.example .env
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn "app.main:create_app" --factory --port 8080 --env-file .env

# 프런트엔드(SPA 번들). app/static/react/ 로 산출물이 나온다
cd frontend && npm install && npm run build
```

## 테스트

```bash
.venv/Scripts/python -m pytest                 # 백엔드 전체(smoke 제외)
.venv/Scripts/python -m pytest -m security     # 마커별
cd frontend && npm test                        # 프런트(vitest)
cd runner/claude-work-assistant && RUNNER_TOKEN=test ../../.venv/Scripts/python -m pytest   # 러너
bash scripts/static_checks.sh                  # 정적 불변 검사(STATIC_CHECKS_OK)
```

## 배포

- **정적만 변경**: `app/static/react/`만 교체하면 서비스 재시작 없이 반영(assets 지문 캐시버스팅)
- **코드/DB/의존성 변경**: `scripts/build-bundle.sh` → scp → `scripts/upgrade-clovirone-web-assistant.sh`(백업 → 마이그레이션 → 재기동, health 게이트). 상세는 `docs/MAINTENANCE_PLAYBOOK.md`
- **러너**: `dist/deploy-runner.sh`(APP_VERSION 게이트 + 백업 + 자동 롤백)
- 프로덕션 서버 `10.100.64.71`, `https://clovirone-ai.gooddi.lab`

## 불변 규칙(요약)

sync 일관성 유지, 아웃바운드 HTTP는 `app/core/http_client.py` 단일 관문, secret은 파일 참조만
(DB/응답/로그 미노출), opaque 세션 + `X-CSRF-Token`, 서버측 RBAC, 프런트는 textContent 렌더,
UTC 저장. 자세한 내용과 저장소 지도는 **`CLAUDE.md`**를 본다.

## 문서

- **`CLAUDE.md`** — 유지보수 세션의 출발점(불변 규칙, 저장소 지도, 배포, 함정). Claude Code가 자동 로드
- **`docs/MAINTENANCE_PLAYBOOK.md`** — 흔한 유지보수 작업 레시피 + 배포/롤백
- **`docs/BUILD_LOG.md`** — 세션 인수인계 이력
- `docs/` — ARCHITECTURE, SECURITY, OPERATIONS, RUNBOOK, USER_GUIDE, ADMIN_GUIDE 등 기능별 상세
