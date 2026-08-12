# ClovirONE Web Assistant

사내 업무 자동화 웹 플랫폼. 기존 ClovirONE AI 업무 도우미(n8n + Claude Runner + Notion)를
손상 없이 확장한 웹 콘솔로, 사용자 셀프서비스와 관리자 운영을 한곳에서 제공한다.

---

## 어디로 가야 하나

이 파일이 저장소의 **유일한 출발점**이다. 하려는 일에 맞는 줄을 골라라.

| 하려는 일 | 가는 곳 |
|---|---|
| **새 서버에 설치한다** | [docs/INSTALL_FROM_GIT.md](docs/INSTALL_FROM_GIT.md) |
| **도는 서버를 업데이트한다 / 되돌린다** | [docs/INSTALL_FROM_GIT.md](docs/INSTALL_FROM_GIT.md) |
| **장애가 났다** | [docs/RUNBOOK.md](docs/RUNBOOK.md) |
| **느리다, 429 가 뜬다, 몇 명까지 되나** | [docs/NGINX_AND_CAPACITY.md](docs/NGINX_AND_CAPACITY.md) |
| **코드를 고친다** | [CLAUDE.md](CLAUDE.md) 를 먼저 읽는다 (불변 규칙, 저장소 지도, 함정) |
| **기능을 새로 만든다** | [docs/EXTENSION_GUIDE.md](docs/EXTENSION_GUIDE.md) |
| **쓰는 법을 알려 준다** | [docs/USER_GUIDE.md](docs/USER_GUIDE.md), [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) |
| **문서 전체 목록** | [docs/README.md](docs/README.md) |

---

## 빠른 설치 (git clone)

자세한 절차, 폐쇄망 준비물, 함정은 [docs/INSTALL_FROM_GIT.md](docs/INSTALL_FROM_GIT.md) 에 있다.

```bash
# ⚠️ /opt/clovirone-web-assistant 안에 clone 하면 안 된다(설치가 자기 자신을 덮어쓴다).
sudo mkdir -p /opt/src && cd /opt/src
sudo git clone <저장소 주소> clovirone-web-assistant
cd clovirone-web-assistant

sudo DNS_NAME=portal.example.internal BIND_IP=10.0.0.10 \
  bash scripts/install-clovirone-web-assistant.sh --from-repo

sudo /opt/clovirone-web-assistant/venv/bin/python \
  /opt/clovirone-web-assistant/scripts/seed_admin.py     # 최초 관리자

sudo DNS_NAME=portal.example.internal bash scripts/validate-clovirone-web-assistant.sh
```

업데이트:

```bash
cd /opt/src/clovirone-web-assistant
sudo DNS_NAME=... BIND_IP=... bash scripts/update-from-git.sh --dry-run   # 먼저 본다
sudo DNS_NAME=... BIND_IP=... bash scripts/update-from-git.sh
```

`update-from-git.sh` 는 시작할 때 버전, 변경 내역, **마이그레이션 필요 여부와 그중 되돌릴 수
없는 것**을 먼저 보여 주고 확인을 받는다. 실패하면 코드와 DB 를 백업 시점으로 되돌린다.
롤백이 정확히 무엇을 되돌리는지는 [문서 §5](docs/INSTALL_FROM_GIT.md) 에 적어 뒀다.
**읽고 시작해라.**

> 인터넷이 필요한가: 파이썬 의존성(`pypi.org`)만 필요하고, 폐쇄망이면 wheelhouse 를 미리
> 만들어 두면 된다. 화면(JS/CSS)은 빌드 산출물이 저장소에 커밋돼 있어 서버에 Node 가
> 필요 없다. 자세한 표는 문서 2절.

---

## 기능

### 사용자 콘솔 (`/`)
- **내 업무(홈)** - 내 티켓 요약 대시보드 + 내 게시판 활동 위젯(내 글, 받은 댓글, 조회 수)
- **티켓** - 내 티켓 / 미할당 티켓 / 새 티켓(제목, 목록, 구분선, 이모지를 지원하는 본문 에디터 + 미리보기)
- **AI 도우미** - 로그인 사용자 신원을 세션에서 자동 식별해 n8n/러너로 전달하는 채팅(위조 불가)
- **문서** - Notion "문서" 데이터베이스를 로컬로 미러링해 검색/필터로 보고, 새 문서를 생성
- **팀 공간**
  - **놀이** - 폴링 기반 실시간 게임 7종. 결과는 서버가 확정하고 승자 공개 시 축포 연출
  - **자유게시판** - 글/댓글/반응/첨부(이미지, PDF), 카테고리별 배지 색

### 관리자 콘솔 (`/admin`)
사용자/부서/직책/Notion 사용자 연결(RBAC 5역할), Integration/Runner/Workflow 레지스트리,
Prompt/Policy/Template 버전 관리, 스케줄러, 승인, 감사 로그, 백업, 유지보수 모드,
개발자 월간 리포트.

### AI 퀴즈 생성 (다크런치)
실시간 퀴즈의 문제를 주제만 주면 러너(Claude Code CLI)가 생성한다. `game_ai_enabled`
기능 플래그로 게이트되며 기본은 OFF.

---

## 기술 스택

- **백엔드**: Python 3.12, FastAPI(**sync 핸들러**), SQLAlchemy 2.0(sync), Alembic, SQLite(WAL), Argon2id
- **프런트엔드**: React 18 + Vite(HashRouter). **빌드 산출물을 저장소에 커밋한다** - 그래서 서버에 Node 가 필요 없다. 대신 소스만 고치고 번들을 다시 안 만들면 서버가 조용히 옛 화면을 도는데, 그것은 `scripts/check_bundle_fresh.py` 가 막는다
- **러너**: Python 표준 라이브러리 HTTP 서버 + Claude Code CLI(`runner/claude-work-assistant/assistant.py`)
- **인프라**: Nginx(자체 서명 TLS, gzip, 요청 속도 제한), systemd. 유일한 바이너리 의존성은 `argon2-cffi`

---

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
# 빌드 직후 기준을 적는다. 안 적으면 git 설치/업데이트가 "번들이 낡았다"로 멈춘다.
python scripts/check_bundle_fresh.py --write
```

## 테스트

```bash
.venv/Scripts/python -m pytest                 # 백엔드 전체(smoke 제외)
.venv/Scripts/python -m pytest -m security     # 마커별
SMOKE_BASE_URL=http://127.0.0.1:8099 .venv/Scripts/python -m pytest -m smoke  # 실브라우저 골든 패스(살아있는 서버 필요, 없으면 skip)
cd frontend && npm test                        # 프런트(vitest)
cd runner/claude-work-assistant && RUNNER_TOKEN=test ../../.venv/Scripts/python -m pytest   # 러너
bash scripts/static_checks.sh                  # 정적 불변 검사(STATIC_CHECKS_OK)
python scripts/check_bundle_fresh.py           # 커밋된 번들이 소스와 맞는가
```

## 배포 경로 요약

| 무엇이 바뀌었나 | 어떻게 |
|---|---|
| 정적만 | `app/static/react/` 교체. 재시작 없이 반영(자산 지문 캐시버스팅) |
| 코드/DB/의존성 (git) | `scripts/update-from-git.sh` |
| 코드/DB/의존성 (번들) | `scripts/build-bundle.sh` → scp → `scripts/upgrade-clovirone-web-assistant.sh` |
| 러너 | `dist/deploy-runner.sh` (APP_VERSION 게이트 + 백업 + 자동 롤백) |

---

## 불변 규칙(요약)

sync 일관성 유지, 아웃바운드 HTTP는 `app/core/http_client.py` 단일 관문, secret은 파일 참조만
(DB/응답/로그 미노출), opaque 세션 + `X-CSRF-Token`, 서버측 RBAC, 프런트는 textContent 렌더,
UTC 저장. 자세한 내용과 저장소 지도는 **[CLAUDE.md](CLAUDE.md)** 를 본다.
