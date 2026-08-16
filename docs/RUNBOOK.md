# RUNBOOK — 장애 대응 플레이북

각 항목: 증상 → 진단 → 조치. 공통 도구는 `journalctl`, `/api/admin/dashboard`,
`sqlite3 /var/lib/clovirone-web-assistant/web.sqlite3`. 조치 후에는 반드시
`/healthz`·`/readyz`·대시보드로 결과를 직접 확인한다.

## 1. Worker가 멈춤 (채팅 응답이 계속 "처리 중")

- **먼저 확인 — 어느 유닛이 채팅을 처리하는가(D-118)**: 대시보드
  `/api/admin/dashboard`(또는 화면)의 `components`에 `worker_conversational` 칸이
  있으면(또는 `grep WORKER_CONVERSATIONAL_LANE_ENABLED /etc/clovirone-web-assistant/web.env`가
  `true`) **채팅은 대화형 레인 전용 유닛(`clovirone-web-worker-conversational`)이
  처리한다** — 배치 워커(`clovirone-web-worker`)가 멀쩡해도 채팅이 멈춰 있을 수 있다.
  이 칸이 없거나 설정이 `false`/미설정이면(대부분의 설치, 기본값) 채팅도 배치
  워커가 처리하므로 아래 절차를 `clovirone-web-worker`에 그대로 적용한다.
- **증상**: 대시보드 worker(또는 worker_conversational)/scheduler가 `stale`(heartbeat
  90초 초과), Job `queued` 적체(대화형 레인이면 `chat_message`/`llm_connection_test`만).
- **진단** (`<unit>`을 위에서 확인한 실제 유닛명으로 치환 — `clovirone-web-worker` 또는
  `clovirone-web-worker-conversational`):
  ```bash
  systemctl status <unit>
  journalctl -u <unit> -n 100
  sqlite3 "file:.../web.sqlite3?mode=ro" "SELECT status, COUNT(*) FROM jobs GROUP BY status;"
  ```
- **조치**: `sudo systemctl restart <unit>`.
  worker는 기동 시(및 매 tick) stuck-job sweep을 수행한다 — `running` 상태로 일정
  시간 넘게 방치된 Job은 자동으로 재큐 또는 최종 실패 처리되므로 수동 DB 조작이
  필요 없다. 이 임계값은 레인마다 다르다: 배치 워커는 기본 **65분(3900초,
  `jobs/repository.DEFAULT_RUNNING_TIMEOUT_SECONDS`)** — 스케줄/백업 같은 장시간
  작업을 오탐 회수하지 않기 위해 일부러 길다. 대화형 레인은 훨씬 짧은 전용 기본값
  **14분(840초, `worker_conversational_running_timeout_seconds`)** — n8n 웹훅
  타임아웃(180초)에 재시도 여유를 더한 값이다. 재발 시 journal에서 특정 job_type의
  반복 예외를 찾아 원인(대부분 n8n 연동, 또는 대화형 레인 동시성 하에서의 SQLite
  쓰기 경합 — 아래 §6 참고)을 제거.

## 2. n8n 다운 (채팅/스케줄 실패 급증)

- **증상**: 사용자 메시지가 `failed`(assistant_error), journal에 "n8n 연결 실패/응답 시간 초과",
  대시보드 integrations에서 n8n `down`.
- **진단**:
  ```bash
  systemctl status n8n
  curl -fsS http://127.0.0.1:5678/healthz
  ```
- **조치**: n8n은 **기존 서비스 — 이 플랫폼에서 수정 금지**. n8n 담당 절차로 복구한다.
  복구 대기 중에는 유지보수 모드를 켜서 사용자 오류 노출을 줄일 수 있다.
  복구 후: 실패 메시지는 사용자가 "다시 시도" 버튼으로, 실패 스케줄 run은
  관리자 콘솔 Schedules → 이력에서 retry. 큐의 실패 Job은 Jobs 섹션에서 retry(operator+).
  timeout/5xx/연결 오류는 자동 재시도(5s·10s·20s) 대상이므로 짧은 순단은 자가 복구된다.

## 3. TLS 인증서 만료 임박

- **증상**: 대시보드 `cert_days_remaining`이 감소, 30일 미만.
- **진단**:
  ```bash
  openssl x509 -enddate -noout -in /etc/clovirone-web-assistant/tls/clovirone-ai.gooddi.lab.crt
  ```
- **조치**: 새 self-signed(또는 사내 CA) 인증서 발급 후 `tls/`의 crt/key 교체,
  `sudo nginx -t && sudo systemctl reload nginx`. 앱 재시작 불필요
  (`TLS_CERT_PATH`는 모니터링용 경로일 뿐). 교체 후 대시보드 일수 갱신 확인.

## 4. 디스크 가득 참

- **증상**: 대시보드 disk `used_pct` 높음, SQLite 쓰기 오류(`disk I/O error`), 백업 실패.
- **진단**:
  ```bash
  df -h /var/lib/clovirone-web-assistant
  du -sh /var/lib/clovirone-web-assistant/exports /var/backups/clovirone-web-assistant
  journalctl --disk-usage
  ```
- **조치**: ① 오래된 스크립트 백업 정리(`/var/backups/...`는 보존 대상 확인 후 수동 삭제)
  ② 앱 내 백업은 retention(최근 14개 유지)이 자동 적용되나 필요 시 exports/ 오래된 파일 삭제
  ③ `sudo journalctl --vacuum-size=500M`.
  절대 `web.sqlite3-wal`/`-shm`을 직접 삭제하지 말 것 — 공간 회수는 서비스 정지 후
  `sqlite3 web.sqlite3 "PRAGMA wal_checkpoint(TRUNCATE);"`로.

## 5. 서비스가 기동하지 않음

- **증상**: `systemctl start` 직후 failed, `Restart=on-failure` 반복.
- **진단**: `journalctl -u clovirone-web-assistant -n 50` — 전형적 원인:
  - `web.env` 문법 오류/필수값 누락 (`session_secret` 등)
  - Alembic 미적용으로 테이블 없음 → `no such table`
  - 8080 포트 선점 → `ss -lntp | grep 8080`
  - `/var/lib/clovirone-web-assistant` 권한 (clovirone-web 소유 아님)
- **조치**: 원인별로 —
  ```bash
  sudo -u clovirone-web /opt/clovirone-web-assistant/venv/bin/python -m alembic upgrade head
  sudo chown -R clovirone-web:clovirone-web /var/lib/clovirone-web-assistant
  ```
  수정 후 `systemctl start` → `curl 127.0.0.1:8080/readyz`로 확인.

## 6. DB locked (`database is locked` 반복)

- **증상**: journal에 OperationalError: database is locked, 응답 지연.
- **진단**: WAL + busy_timeout 5000ms에서 이 오류는 장기 writer가 있다는 뜻.
  `fuser /var/lib/clovirone-web-assistant/web.sqlite3` 로 DB를 연 프로세스 확인 —
  **운영 DB를 sqlite3 셸로 열어둔 채 방치한 경우가 최다 원인**.
- **조치**: 외부에서 연 세션 종료. 서버에서 DB를 조회할 때는 읽기 전용으로:
  `sqlite3 "file:web.sqlite3?mode=ro" ...`. 해소되지 않으면 두 서비스 재시작.
  대화형 레인이 꺼져 있으면(기본값) worker는 단일 프로세스라 정상 상태에서 writer
  경합은 짧다. **대화형 레인이 켜져 있으면(D-118, `worker_conversational_lane_enabled`)
  이 전제가 다르다** — 배치 워커 + 대화형 워커(스레드풀 동시성, 기본 3)가 같은
  DB 파일에 동시에 쓰므로 순간적인 `database is locked`는 그 자체로는 이상 징후가
  아니다(TEST SERVER 실측: 서로 다른 대화 3개를 70ms 이내로 보내면 실제로 발생,
  대부분 기존 백오프로 자가 회복). 이 경우 진짜 문제는 "잠금이 발생했는가"가
  아니라 "회복하지 못하고 `running`에 멈춘 Job이 있는가"다 — 위 §1의 레인별
  stuck-job 타임아웃(배치 3900초/대화형 840초)이 지나도 회수 안 된 Job이 있으면
  그때 조사한다.

## 7. 마지막 system_admin 잠금/접근 불가

- **증상**: 유일한 system_admin이 잠기거나 비밀번호 분실. (비활성화/강등은 앱이
  `ensure_not_last_system_admin`으로 차단하므로 발생하지 않음 — spec §32.8)
- **조치**: 서버 CLI는 웹 인증과 무관하게 동작한다.
  ```bash
  cd /opt/clovirone-web-assistant
  sudo -u clovirone-web venv/bin/python -m app.cli.user_cli unlock admin@goodmit.co.kr
  sudo -u clovirone-web venv/bin/python -m app.cli.user_cli passwd admin@goodmit.co.kr --temp
  ```
  `--temp`는 임시 비밀번호를 1회 출력하고 첫 로그인 변경을 강제한다.
  system_admin이 정말 0명이면 `add ... --role system_admin`으로 신규 생성.

## 8. 스케줄 이중 실행 의심

- **증상**: 같은 occurrence가 두 번 실행된 것으로 보임.
- **진단**: `schedule_runs.idempotency_key`는 `"{schedule_id}:{scheduled_at}"` UNIQUE —
  같은 키가 두 행이면 DB 제약이 깨진 것(정상적으로 불가능).
  ```bash
  sqlite3 ... "SELECT idempotency_key, COUNT(*) FROM schedule_runs
               GROUP BY idempotency_key HAVING COUNT(*)>1;"
  ```
  대부분은 ① `run-now` 수동 실행(키가 `manual:...`로 별도) ② `concurrency_policy=allow`
  스케줄의 정상 중첩 ③ misfire `run_once`의 catch-up 1회 — 이중 실행이 아니다.
- **조치**: run 이력에서 키/시각을 확인해 위 세 경우를 구분. 실제 중복 유입 경로가
  worker 다중 기동이라면 `systemctl status clovirone-web-worker` 인스턴스가 1개인지,
  수동으로 `python -m app.worker_main`을 띄운 세션이 없는지 확인 후 종료한다.
  (설계상 다중 인스턴스여도 insert-first 키 경합으로 한쪽만 소유권을 가진다.)

## 복원(최후 수단)

DB/설정 손상 시 `docs/BACKUP_RESTORE.md`의 스크립트 복원 절차를 따른다 —
복원 전 현재 상태 스냅샷 필수.
