# OPERATIONS — 운영 가이드

대상 서버: Ubuntu 24.04, `10.100.64.71` (`clovirone-ai.gooddi.lab`). 시스템 계정
`clovirone-web`(nologin). 기존 n8n·Runner 서비스는 무접촉 원칙 — 이 문서의 어떤
절차도 n8n을 건드리지 않는다.

## 경로

| 경로 | 내용 |
|---|---|
| `/opt/clovirone-web-assistant` | 앱 소스 + venv + scripts |
| `/etc/clovirone-web-assistant` | `web.env`(환경변수), allowlist JSON 3종, `feature-flags.json`, `secrets/`, `tls/` |
| `/var/lib/clovirone-web-assistant` | `web.sqlite3`(+WAL/SHM), `exports/`(앱 내 백업) |
| `/var/backups/clovirone-web-assistant` | 스크립트 백업(루트 전용 0700) |

## 서비스 (systemd)

| 유닛 | 실행 | 설명 |
|---|---|---|
| `clovirone-web-assistant.service` | uvicorn `app.main:create_app` --factory, 127.0.0.1:8080, workers 1 | 웹 API/UI |
| `clovirone-web-worker.service` | `python -m app.worker_main` | Job 큐 + Scheduler + heartbeat. SIGTERM graceful (진행 중 Job 완료 후 종료, TimeoutStopSec=60) |

두 유닛 모두 spec §26.1 하드닝 적용(NoNewPrivileges, ProtectSystem=strict,
MemoryDenyWriteExecute 등, 쓰기 허용은 `/var/lib/clovirone-web-assistant`만).

```bash
# 상태
systemctl status clovirone-web-assistant clovirone-web-worker nginx

# 시작/중지/재시작 (중지는 worker 먼저 — Job drain)
sudo systemctl stop clovirone-web-worker && sudo systemctl stop clovirone-web-assistant
sudo systemctl start clovirone-web-assistant && sudo systemctl start clovirone-web-worker
sudo systemctl restart clovirone-web-assistant clovirone-web-worker
```

웹에는 서비스 재시작 API가 **없다**. 재시작이 필요한 설정 변경은 API 응답의
`restart_required` 플래그로 안내만 되고, 실제 재시작은 SSH에서 위 명령으로 수행한다.

## 로그

```bash
journalctl -u clovirone-web-assistant -f          # 웹 (access log 포함, request_id 표기)
journalctl -u clovirone-web-worker -f             # worker/scheduler/handler 로그
journalctl -u clovirone-web-assistant --since "1 hour ago" -n 200
```

앱은 파일 로그를 쓰지 않는다 — stdout → journald. 각 요청 응답 헤더의
`X-Request-ID`로 로그 라인을 상호 참조할 수 있다.

## Health / Readiness

| 엔드포인트 | 의미 |
|---|---|
| `GET /healthz` | liveness — 프로세스 응답 여부 (`{"status":"ok"}`) |
| `GET /readyz` | readiness — DB `SELECT 1` 실패 시 503 `{"status":"unready"}` |
| `GET /api/admin/dashboard` | operator+ — worker/scheduler heartbeat(90초 초과 시 stale), Job 24h 통계, 디스크/메모리, TLS 만료 일수, 마지막 백업 |
| `GET /api/admin/diagnostics/bundle` | admin+ — 마스킹된 진단 번들(최근 Job 오류 20건, 설정, 연동 상태) |

```bash
curl -k https://clovirone-ai.gooddi.lab/healthz
curl -fsS http://127.0.0.1:8080/readyz          # nginx 우회 직접 확인
```

Worker는 15초마다 `heartbeats` 테이블에 worker/scheduler를 기록한다.
대시보드에서 stale이면 worker 프로세스부터 확인한다 (`docs/RUNBOOK.md`).

## 유지보수 모드 (spec §14.5)

- 켜기/끄기: 관리자 콘솔 **Maintenance** 섹션 또는
  `PUT /api/admin/settings/maintenance_mode` `{"value": true}` (admin+)
- 효과: 역할 `user`의 **신규 요청(채팅 전송 등)**이 503 `maintenance_mode`로 차단.
  operator 이상은 통과하므로 점검 작업 가능
- 공지 문구는 `maintenance_message` 설정으로 변경

## 정기/일상 운영

- **백업**: 관리자 콘솔 Backup 섹션(system_admin) 또는 서버에서
  `sudo /opt/clovirone-web-assistant/scripts/backup-clovirone-web-assistant.sh`.
  절차와 복원은 `docs/BACKUP_RESTORE.md`
- **설치 검증**: `sudo scripts/validate-clovirone-web-assistant.sh` —
  서비스 active, 포트, healthz/readyz, TLS를 일괄 점검하고 `VALIDATE_OK` 출력
- **업그레이드**: 스테이징 디렉터리에 소스 배치 후
  `sudo scripts/upgrade-clovirone-web-assistant.sh` — 백업 → worker부터 중지 →
  installer 재실행(의존성/Alembic migrate/유닛/nginx/기동)
- **사용자 관리(비상용 CLI)**: `venv/bin/python -m app.cli.user_cli list|show|unlock ...`
  (웹이 죽어도 동작, `docs/USER_LIFECYCLE.md`)
- **allowlist 변경**: `/etc/clovirone-web-assistant/allowed-*.json` 편집 —
  mtime 기반 캐시라 **재시작 불필요**, 저장 즉시 반영

## 설정 변경 흐름 (spec §14.4)

관리자 콘솔 Settings 섹션은 허용 목록(`app/settings/registry.py`)에 있는 키만 수정 가능:
`conversation_retention_days`, `notification_retention_days`, `ui_branding`,
`maintenance_mode`, `maintenance_message`, `password_policy`, `session_policy`,
`allowed_email_domains`, `document_automation_enabled`.

허용 목록에 없는 값(base URL, 기본 timeout, page size, timezone, retry/misfire 정책 등)은
env 또는 객체별 설정으로만 다루며, 효과 없는 스위치를 콘솔에 노출하지 않도록 의도적으로
registry에서 뺐다.

절차: dry-run(검증) → 적용(변경 전 스냅샷 자동 저장) → 필요 시
`POST /api/admin/settings/{key}/rollback` `{"version": N}`. 모든 변경은 감사 기록.

## 기능 플래그 다크런치 (feature-flags.json)

Settings registry에 없는 다크런치용 토글은 `/etc/clovirone-web-assistant/feature-flags.json`에
둔다(예: AI 퀴즈 생성 `game_ai_enabled`, 팀 공간 `board_enabled`/`team_docs_enabled`/`games_enabled`,
모두 기본값 있음, game_ai_enabled만 기본 OFF). 값을 켜려면 이 파일을 편집해 해당 키를 `true`로
바꾼다. 이 파일은 요청마다 다시 읽으므로 저장 즉시 반영되며 재시작이 필요 없다(파일이 없거나
JSON이 깨지면 기본값으로 fail-closed). 안정화되어 상시 노출이 필요한 값은 registry로 옮겨
콘솔에서 관리한다(document_automation_enabled가 그렇게 옮겨진 예다).

## Nginx

vhost는 `10.100.64.71:443` 전용 listen(기존 서비스 vhost와 격리, default_server 아님).
`proxy_read_timeout 180s`(n8n 장시간 응답 대비), 정적 자원 1시간 캐시.

```bash
sudo nginx -t && sudo systemctl reload nginx
```
