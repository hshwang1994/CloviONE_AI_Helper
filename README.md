# ClovirONE Web Assistant

사내 업무 자동화 웹 플랫폼 — 기존 ClovirONE AI 업무 도우미(n8n + Claude Runner + Notion)를
손상 없이 확장하는 웹 채팅 + 관리자 운영 콘솔.

- 사용자 웹 채팅 (본인 이름·이메일 자동 식별, n8n 연동)
- 관리자 콘솔 `/admin`: 사용자·역할, Notion 매핑, Integration/Runner/Workflow Registry,
  Prompt/Policy/Template 버전 관리, Scheduler, 승인, 감사 로그, 백업, 유지보수 모드

## 기술 스택

Python 3.12 · FastAPI(sync) · SQLAlchemy 2.0 · Alembic · SQLite(WAL) · Argon2id ·
Jinja2 + Vanilla JS(외부 CDN/폰트/npm 없음) · Nginx · systemd

## 개발 환경

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Windows
cp .env.example .env
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn "app.main:create_app" --factory --port 8080
```

## 테스트

```bash
.venv/Scripts/python -m pytest          # smoke 제외 전체
.venv/Scripts/python -m pytest -m security
```

## 문서

- **`CLAUDE.md`** — 유지보수·수정 세션의 출발점(불변 규칙·저장소 지도·배포·함정). Claude Code가 자동 로드.
- **`docs/MAINTENANCE_PLAYBOOK.md`** — 흔한 유지보수 작업 레시피(단계별) + 배포/롤백.
- `docs/BUILD_LOG.md` — 세션 인수인계 이력.
- `docs/` — ARCHITECTURE, SECURITY, OPERATIONS, RUNBOOK 등 20종 (spec §36.3).
