# CLAUDE.md — ClovirONE Web Assistant

> 이 파일은 Claude Code가 이 저장소에서 세션을 시작할 때 자동으로 읽는 **작업 지침·컨텍스트**다.
> 향후 유지보수·수정을 하는 세션은 **먼저 이 파일을 읽고**, 필요한 세부는 `docs/`를 참조한다.
> 코드를 고치기 전에 아래 **§2 불변 규칙**을 반드시 확인한다.

## 1. 이 프로젝트가 무엇인가

사내 업무 자동화 웹 플랫폼. 기존 ClovirONE AI 업무 도우미(n8n + Claude Runner + Notion)를
**손상 없이 확장**한다.

- **사용자 콘솔** (`/`) — React SPA. 로그인 신원을 세션에서 자동 식별(위조 불가). 좌측 그룹 네비:
  - 내 업무(홈 대시보드=티켓 요약+내 게시판 활동), 내 티켓/미할당/새 티켓(설명 리치 본문 에디터)
  - 도우미(AI 도우미 채팅, n8n/러너 연동)
  - 문서(Notion "문서" DB 미러링+검색/필터+새 문서 생성, 장애 격리 캐시)
  - 팀 공간: 놀이(폴링 실시간 게임 7종, 서버 확정, 승자 축포) + 자유게시판(글/댓글/반응/첨부)
- **관리자 콘솔** (`/admin`) — 사용자/부서/직책/Notion 사용자 연결(RBAC 5역할), Integration/Runner/
  Workflow Registry, Prompt/Policy/Template 버전 관리, Scheduler, 승인, 감사 로그, 백업, 유지보수 모드,
  개발자 월간 리포트
- **AI 퀴즈 생성**(§7-9, 다크런치) — 앱 → 러너 `/v1/assistant/quiz`(Claude CLI)로 퀴즈 문제 생성.
  `game_ai_enabled` 플래그 기본 OFF

**기술 스택**: Python 3.12, FastAPI(**sync 핸들러**), SQLAlchemy 2.0(**sync**), Alembic,
SQLite(**WAL**), Argon2id, **React 18 + Vite(HashRouter)** — 소스 `frontend/`, 빌드 산출물
`app/static/react/`(index.html+assets)를 Jinja 셸로 서빙. **런타임 외부 CDN/폰트/네트워크 금지**
(CSP `script-src 'self'`), npm은 빌드에만. 로그인/비밀번호변경만 `app/static/js`(login.js 등)에 남은
소규모 바닐라 JS. Nginx, systemd. 유일한 바이너리 의존성은 `argon2-cffi`(전체는 `requirements.txt` 버전 고정).

**상태**: 프로덕션 배포 완료(서버 `10.100.64.71`, `https://clovirone-ai.gooddi.lab`). 테스트 4묶음 전부 green,
7관점 검수 루프 6회 수렴(Critical/High 0). 상세 이력은 `docs/BUILD_LOG.md`(세션 인수인계의 출발점).
테스트 개수는 여기 박지 않는다 — 이 줄이 이미 세 번 낡았고(예: 한때 458/122/131이라 적혀 있었는데
어느 하나도 실제와 안 맞았다), 여러 갈래가 동시에 테스트를 추가해 매 세션 움직인다. 지금 세는 법:
- 플랫폼: `.venv/Scripts/python -m pytest --collect-only | tail -1`
- 러너: `cd runner/claude-work-assistant && ../../.venv/Scripts/python -m pytest --collect-only | tail -1`
- 프런트(React) 유닛: `cd frontend && npm test`(vitest). 예전 vanilla `tests/js/*` 하네스는 vanilla→React
  포팅으로 부팅 대상(app/static/js/chat.js)이 사라져 죽은 코드였다 — 삭제하고 vitest로 대체했다.

## 2. 불변 규칙 (Invariants — 깨면 안 됨)

이 규칙들은 스펙과 검수 루프로 강제된다. 수정 시 반드시 유지한다. 여러 개는 **정적 검사
(`scripts/static_checks.sh`)로 자동 감시**되니, 어기면 CI/커밋 전 검사에서 걸린다.

1. **동기(sync) 일관성** — SQLAlchemy·FastAPI 핸들러 모두 sync. `async def` 핸들러/`aiosqlite`
   추가 금지(worker/scheduler 결정론 테스트가 깨진다).
2. **아웃바운드 HTTP는 단일 관문** — 외부 호출은 `app/core/http_client.py`의 `OutboundClient`
   **한 곳으로만**. 다른 모듈에서 `import httpx` 금지(정적 검사가 차단). SSRF allowlist·redirect
   금지·secret 주입이 여기에만 있다.
3. **Secret은 절대 DB/응답/로그에 없다** — DB엔 `secret_ref`(이름)만. 실제 값은
   `SECRETS_DIR/<name>` 파일 참조(`SecretValue.repr/str == "***"`). 응답·로그·감사엔 마스킹.
4. **비밀번호·토큰은 명령행·파일·env·git에 남기지 않는다** — 오직 stdin/프롬프트로만. `sshpass`
   금지. 임시 비밀번호는 콘솔 1회 표시 후 로그 미기록.
5. **세션은 opaque 토큰** — 256-bit 랜덤, DB엔 SHA-256 해시만 저장. JWT 아님. CSRF는
   `X-CSRF-Token` 헤더. RBAC는 서버측에서만 판단(프런트 신뢰 금지).
6. **프런트 렌더는 textContent 전용** — 서버 데이터를 `innerHTML`에 넣지 않는다(XSS). CSP
   `script-src 'self'` — 인라인 `<script>`·`onclick=` 금지. JS는 외부 파일에서만.
7. **불변성(immutability)** — 객체를 제자리 수정하지 말고 새 객체를 만든다.
8. **작은 파일 다수 > 큰 파일 소수** — 모듈은 feature별(`router`/`service`/`repository`/`schemas`/
   `models`). 파일 200~400줄 권장, 800 최대.
9. **UTC 저장, Asia/Seoul은 표시·cron 평가 때만.**
10. **구현하지 않는 것**(스펙 §0.2): Runner 코드 웹 편집, 임의 shell 실행, secret 평문 표시,
    임의 systemd 관리. 서비스 재시작 API는 501 + 안내만.

## 3. 저장소 지도

```
app/
  main.py                 create_app(settings, clock, outbound_transport) — app factory
  worker_main.py          단일 worker (job loop + scheduler tick), build_handlers() 잡 등록점
  core/                   config, db(WAL/PRAGMA), http_client(OutboundClient), security(Argon2),
                          sessions, secrets, errors, middleware(CSP), feature_flags,
                          notion_blocks(markdown_to_blocks — 문서/티켓 본문→Notion 블록) … ← 인프라, 조심해서 수정
  <feature>/              auth users org(부서·직책) integrations runners workflows prompts policies
                          templates schedules approvals notifications documents notion_mapping chat
                          conversations jobs backups audit settings profiles health reports(월간리포트)
                          tickets team_docs(문서 탭) board(게시판) games(놀이 7종+AI 퀴즈)
                          → 각 feature = router.py + service.py + repository.py + schemas.py + models.py
                          (신규 모델은 models_registry.py 임포트 + main.py include_router 한 줄)
  static/                 react/(Vite 빌드 산출물: index.html+assets, 메인 SPA) css/ img/
                          js/(login.js·change_password.js·theme.js 만 남은 소규모 바닐라) — 외부 의존 0
  templates_html/         Jinja2 셸(로그인·사용자 콘솔·admin 셸이 React 번들을 로드)
frontend/                 React 18 + Vite 소스(src/app, src/screens, src/ui, src/lib). npm은 빌드에만
alembic/                  마이그레이션 0001~0019 (script_location 상대경로 → 서버에선 cd APP_DIR 필요)
config/                   allowlist JSON(services/runners/workflows) + feature-flags.json (개발용 사본)
scripts/                  install/upgrade/rollback/backup/validate .sh + seed_admin.py + static_checks.sh + build-bundle.sh
deploy/                   systemd/*.service, nginx/*.conf, web.env.example, 00-precheck.sh
dist/                     build-bundle 산출물 + deploy-runner.sh(러너 안전 배포)
docs/                     기능별 문서 (아래 §9 색인)
tests/                    unit/integration/security/regression/smoke + fakes/
```

## 4. 로컬 개발·테스트

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt      # Windows (Linux: .venv/bin/…)
cp .env.example .env
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn "app.main:create_app" --factory --port 8080 --env-file .env
```

- **테스트**: `.venv/Scripts/python -m pytest`  (smoke 제외 전체 자동)  ·  마커: `-m security` 등
- **정적 검사**: `bash scripts/static_checks.sh` → 마지막 줄 `STATIC_CHECKS_OK` 확인
- **로컬 admin 계정 만들기**: `python -m app.cli.user_cli add --email me@goodmit.co.kr --name 이름 --role system_admin --password-stdin`
  (또는 `scripts/seed_admin.py`). 비밀번호는 stdin으로만.
- DB는 파일 기반 SQLite(`var/…`). `:memory:` 쓰지 말 것(WAL·멀티커넥션 테스트 필요).

## 5. 변경 워크플로 (수정할 때마다)

1. 관련 `docs/` 읽기 → §2 불변 규칙 확인
2. **테스트 먼저**(TDD): 실패 테스트 추가 → 구현 → 통과. 회귀 결함은 `tests/regression/`에 핀.
3. `.venv/Scripts/python -m pytest` **전체 green** + `bash scripts/static_checks.sh` **OK**
4. JS 바꿨으면 `node --check <file>` (static_checks가 node 있으면 자동 수행)
5. 커밋(conventional commits: `feat: / fix: / docs: …`). 커밋 전 §7 보안 체크리스트.
6. 배포 필요 시 §6.

## 6. 배포 & 프로덕션

**서버**: `cloviradmin@10.100.64.71` (Ubuntu 24.04, `clovirone-ai.gooddi.lab`).
SSH **키 인증**(비번 없음). **sudo는 비밀번호 필요**(임시 NOPASSWD는 제거됨 — root 작업은 사용자가
직접 실행). 기존 서비스와 **공존**: n8n `:5678`, claude runner `:8787/:8788/:8789` — 절대 건드리지 않음.

- 앱: `/opt/clovirone-web-assistant` (root:root). 설정: `/etc/clovirone-web-assistant/web.env`
  (0640 root:clovirone-web, `SESSION_SECRET`는 서버 생성·비출력). 전용 사용자 `clovirone-web`(nologin).
- 서비스: `clovirone-web-assistant.service`(web, `127.0.0.1:8080`), `clovirone-web-worker.service`(worker),
  `nginx`(`:443` self-signed → HSTS off). 로그: `journalctl -u clovirone-web-assistant`.

**정적 파일만 바꿨을 때(프런트 핫 업데이트)** — 서비스 재시작 불필요(StaticFiles가 디스크에서
매 요청 서빙). 방법은 `docs/MAINTENANCE_PLAYBOOK.md` §1.
**사용자에게 새로고침을 부탁하지 않는다** — `app/core/assets.py`가 파일의 mtime·크기로 지문을
계산해 `/static/css/x.css?v=<지문>`으로 내보내므로, 파일이 바뀌면 주소가 바뀌고 브라우저가
무조건 새로 받는다. HTML은 `no-store`라 항상 새 주소를 본다.

**코드/DB/의존성 바뀐 전체 업그레이드** — `scripts/build-bundle.sh`로 번들 생성 → scp →
`scripts/upgrade-clovirone-web-assistant.sh`(root): 백업 → 서비스 정지 → 멱등 installer 재실행
(소스·deps·migrate·units·nginx·기동). 상세: `docs/MAINTENANCE_PLAYBOOK.md` §2, `docs/OPERATIONS.md`.

**롤백** — `scripts/rollback-clovirone-web-assistant.sh <BACKUP_DIR>` (자사 파일만 복원). 백업은
`/var/backups/clovirone-web-assistant/<ts>/`. 첫 설치 되돌리기는 `--uninstall`.

## 7. 커밋 전 보안 체크리스트

- [ ] 하드코딩 secret 없음(정적 검사 통과) · 입력 검증 있음 · SQL은 파라미터 바인딩
- [ ] 새 외부 호출은 `OutboundClient` 경유 + allowlist 반영 · `import httpx` 추가 안 함
- [ ] 새 엔드포인트에 RBAC 의존성 + 상태변경엔 CSRF · IDOR(객체 소유권) 확인
- [ ] secret/비번/토큰이 응답·로그·감사·에러 메시지에 노출 안 됨
- [ ] 권한 상승 경로 없음(특히 lifecycle 엔드포인트는 `ensure_can_manage_target`로 target 역할 확인)

## 8. 함정(반드시 기억, BUILD_LOG 교훈)

- **datetime 문자열은 Python과 SQLite의 strftime이 서로 다르다. 섞으면 데이터가 깨진다.**
  - **Python**(`datetime.strftime`): `"%Y-%m-%d %H:%M:%S.%f"` — `%f`가 마이크로초 6자리다.
    DB에 넣을 문자열은 이 형식이어야 ORM이 다시 읽는다.
  - **SQLite**(`STRFTIME(...)`): **`%f`는 '초.밀리초'다**(`%S`가 아니라 `%S.%f` 전체에 해당).
    그래서 `STRFTIME('%H:%M:%S.%f')`는 `'06:58:51.51.066'` — **초가 두 번 들어간다.**
    SQLite에서 같은 모양을 만들려면 `STRFTIME('%Y-%m-%d %H:%M:%f')`다(`%S` 없이).
  - 이 함정이 실제로 터졌다: 마이그레이션이 `STRFTIME('...%H:%M:%S.%f')`로 timestamp를 넣었고,
    그 행을 ORM으로 읽는 순간 `ValueError: Invalid isoformat string`으로 **'부서 관리' 화면과
    CLI가 통째로 크래시**했다. raw SQL로 `name`만 보던 테스트는 못 잡았다 — 프로덕션 데이터로
    CLI를 직접 돌려서야 나왔다. **마이그레이션의 timestamp는 Python에서 만들어 파라미터로 넘겨라.**
  원시 UPDATE 후 ORM 객체는 `db.refresh` 필요.
- **라우터 팩토리 파일에 `from __future__ import annotations` 금지**(FastAPI 의존성 해석 깨짐).
- **install/alembic는 `cd $APP_DIR` 먼저**(script_location·`python -m app`이 상대경로).
  `runuser`는 `-l` 없으면 CWD 보존.
- **`web.env`(0640)는 cloviradmin이 못 읽음** → grep은 `sudo bash -c`로 root가 수행.
- **installer의 chmod/chown은 venv 제외**(`-path "$APP_DIR/venv" -prune -o …`) — 안 하면 venv exec 비트 손상.
- **FastAPI StaticFiles = 디스크 직접 서빙** → 정적 파일 교체는 재시작 불필요.
  단 `assets.py`의 지문을 **캐시하면 안 된다** — 한때 지문을 프로세스 수명 동안 고정했더니
  이 절차대로 교체해도 옛 주소가 계속 나가 캐시 버스팅이 통째로 무효였다(사용자에겐 "바뀐 게
  없다"로 보인다). 지금은 매 요청 stat한다. `tests/regression/test_asset_cache_busting.py`가 못 박음.
- **nginx는 공유 자원** — IP-literal listen이 기존 wildcard vhost 트래픽을 가로챌 수 있음. vhost 추가만,
  기존 무접촉. `default_server` 금지.

## 9. 문서 색인 (`docs/`)

| 문서 | 내용 |
|---|---|
| **BUILD_LOG.md** | 세션 인수인계 이력 — **새 세션은 여기부터** |
| **MAINTENANCE_PLAYBOOK.md** | 흔한 유지보수·수정 작업 레시피(단계별) + 배포/롤백 |
| ARCHITECTURE.md | 시스템 설계·데이터 모델 |
| SECURITY.md | 위협 모델·보안 통제 | OPERATIONS.md / RUNBOOK.md | 운영·장애 대응 |
| INSTALLATION_REPORT.md | 배포 최종 보고(secret 미포함) | KNOWN_LIMITATIONS.md | 알려진 제한 |
| EXTENSION_GUIDE.md | 확장 가이드(Postgres 전환 기준 등) | ADMIN_GUIDE.md / USER_GUIDE.md | 사용자 매뉴얼 |
| USER_LIFECYCLE · RUNNER_MANAGEMENT · WORKFLOW_REGISTRY · PROMPT_POLICY_MANAGEMENT · SCHEDULER · NOTION_MAPPING · DOCUMENT_AUTOMATION · BACKUP_RESTORE · TEST_SCENARIOS | 기능별 상세 |

**스펙 원본**: `C:\Users\hshwa\Downloads\ClovirONE_Web_Assistant_Final_Claude_Instructions.md` (v2.0).
**승인된 계획**: `~/.claude/plans/c-users-hshwa-downloads-clovirone-web-as-indexed-quokka.md`.

## 10. 조치 필요 (운영 전, 사용자)

- 대화에 노출된 **관리자 임시 비밀번호**와 **SSH 비밀번호** 변경(스펙 §1).
- 자체서명 인증서 → 사설 CA/사내 인증서로 교체 시 HSTS 활성 검토(`docs/SECURITY.md`).
