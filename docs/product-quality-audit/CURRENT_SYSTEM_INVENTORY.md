# 현재 시스템 인벤토리 (CURRENT_SYSTEM_INVENTORY)

2026-07-16 기준, 서버에서 직접 확인한 실측값이다.

## 서버

- 호스트: 10.100.64.71 (`ai-n8n-svr`), Ubuntu 24.04.2 LTS, kernel 6.8.0-134
- 디스크: 294G 중 12G 사용 (5%)
- 접속: `cloviradmin` SSH 키 인증, sudo 사용 가능

## 서비스 (전부 systemd, 전부 부팅 시 자동 기동)

| 서비스 | 포트 | 역할 |
|---|---|---|
| `n8n.service` | 127.0.0.1:5678 (UI/웹훅), 5679 | 워크플로 엔진. 외부에 열려 있지 않다 |
| `claude-work-assistant.service` | 127.0.0.1:8789 | 이번 제품의 AI 러너 (`/opt/claude-work-assistant/assistant.py`) |
| `claude-ticket-runner.service` | 127.0.0.1:8787 | 기존 서비스 (무접촉) |
| `claude-request-interpreter.service` | 127.0.0.1:8788 | 기존 서비스 (무접촉) |
| `clovirone-web-assistant.service` | 127.0.0.1:8080 (uvicorn) | FastAPI 웹 플랫폼 |
| `clovirone-web-worker.service` | 없음 | Job 워커 + 스케줄러 |
| `nginx` | 10.100.64.71:443, 0.0.0.0:80 | 리버스 프록시. `sites-enabled`: `clovirone-web-assistant`, `default` |

사용자에게 열려 있는 경로는 nginx(443)뿐이다. 러너와 n8n은 전부 루프백 바인딩이라
서버 내부 프로세스만 접근할 수 있다.

## 데이터 저장소

- 플랫폼: SQLite (`/var/lib/clovirone-web-assistant/`), WAL 모드, alembic 마이그레이션
- n8n: SQLite (`/var/lib/n8n/.n8n/database.sqlite`), 약 357MB + WAL 15MB
- 업무 데이터의 원천: **Notion** (프로젝트 DB, 작업 DB). 플랫폼과 n8n은 Notion을 저장소로 쓰지 않고 매번 조회한다.
- 이미지 첨부: `/home/n8n/.n8n-files/clovirone-work-assistant-images/<대화키>/`, 24시간 TTL 스윕

## 요청 흐름

```
브라우저 → nginx:443 → uvicorn:8080 (FastAPI)
                          ↓ 대화 메시지를 Job 큐에 넣는다 (202 반환, 화면은 폴링)
                       worker → n8n webhook (127.0.0.1:5678/webhook/clovirone-work-assistant)
                                   ↓ Notion 조회(프로젝트/작업/스키마, 5분 캐시)
                                   ↓ 러너 호출 (127.0.0.1:8789) — 규칙 엔진 + LLM
                                   ↓ 쓰기가 필요하면 Notion API (생성/변경/댓글/이미지 첨부)
                                   → 응답 저장 후 플랫폼으로 반환
```

## 활성 n8n 워크플로

- id `reuSafmsRzO1tIzX` — "ClovirONE AI 업무 도우미" (34개 노드). 웹훅 `POST /webhook/clovirone-work-assistant`
- 나머지 20개 워크플로는 전부 비활성(과거 버전과 실험). 정리 대상으로 기록해 둔다.

## 저장소와 배포

- 로컬 저장소: `C:\Users\hshwa\clovirone-web-assistant` (git, 원격 없음)
- 플랫폼 배포: 번들 tar.gz → `scripts/upgrade-clovirone-web-assistant.sh` (백업 후 교체, 실패 시 롤백)
- 러너 배포: `assistant.py` scp → py_compile → 백업 → 교체 → 재시작 → `/healthz` 버전 확인 5회 → 실패 시 자동 롤백
- n8n 워크플로 배포: **n8n CLI만 사용한다.** `import:workflow` → `update:workflow --active=true` → 재시작 →
  `export:workflow`로 되읽어 검증. raw SQL 수정은 n8n이 읽는 상태와 갈라지므로 금지
  (이번 세션에서 실제로 겪었다. [CURRENT_WORK_COMPLETION.md](CURRENT_WORK_COMPLETION.md) 참고)
