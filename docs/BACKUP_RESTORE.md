# BACKUP / RESTORE (spec §6, §14.6)

원칙: **백업은 앱/스크립트 양쪽에서, 복원은 스크립트로만.** 웹 UI/API에는 복원 기능이
없다 — `GET /api/admin/backups/restore-instructions`는 절차 안내 텍스트만 반환한다.

## 1. 앱 내 DB 백업 (관리자 콘솔 / API)

`POST /api/admin/backups` (**system_admin 전용**) → `app/backups/service.run_backup`:

1. **SQLite 온라인 Backup API** (`sqlite3.Connection.backup()`) — 서비스 무중단,
   naive 파일 복사 절대 아님 (WAL 중이어도 일관된 스냅샷)
2. 산출물: `<data_dir>/exports/web-YYYYMMDD_HHMMSS.sqlite3`
   (운영: `/var/lib/clovirone-web-assistant/exports/`)
3. **SHA-256 체크섬** 계산·저장
4. **즉시 임시 복원 테스트** (`restore_test`): 백업본을 임시 디렉터리에 다시 복사한 뒤
   `PRAGMA integrity_check` — 라이브 데이터는 절대 건드리지 않음
5. 상태 기록: `succeeded` → 검증 통과 시 **`verified`**, 실패 시 `failed`+사유

부가 기능:

- `GET /api/admin/backups` — 이력 조회 (경로/크기/체크섬/상태, 읽기: operator+/auditor)
- `POST /api/admin/backups/{id}/verify` (system_admin) — 기존 백업 재검증
  (체크섬 대조 + integrity_check)
- **보존(retention)**: 최근 **14개** 유지, 초과분은 레코드+파일 삭제 (`apply_retention`)
- 대시보드에 마지막 성공 백업 시각/상태 표시

## 2. 서버 전체 백업 (스크립트, root)

```bash
sudo /opt/clovirone-web-assistant/scripts/backup-clovirone-web-assistant.sh
```

`/var/backups/clovirone-web-assistant/<YYYYMMDD_HHMMSS>/` (0700, root 전용)에 생성:

| 파일 | 내용 |
|---|---|
| `app.tar.gz` | /opt/clovirone-web-assistant 전체 |
| `etc.tar.gz` | /etc/clovirone-web-assistant (env, allowlist, secrets, tls 포함 — root 전용 디렉터리라 허용) |
| `web.sqlite3` | `sqlite3 ".backup"` — 온라인 Backup API |
| `clovirone-web-*.service`, `nginx-vhost.conf` | systemd 유닛 + nginx vhost |
| `state.txt` | 포트/서비스 상태 스냅샷 |
| `SHA256SUMS` | 전체 체크섬 (복원 시 검증) |

성공 시 `BACKUP_OK <경로>` 출력. 업그레이드 스크립트는 이 백업을 자동 선행한다.

## 3. 복원 (스크립트 전용, system_admin)

**복원 전 반드시 현재 상태를 별도 스냅샷으로 보존한다** — 복원이 잘못됐을 때
되돌아갈 지점이 필요하다.

```bash
# 0) 유지보수 모드 켜고 진행 중 Job이 없는지 확인 (admin 콘솔)
# 1) pre-restore 스냅샷
sudo /opt/clovirone-web-assistant/scripts/backup-clovirone-web-assistant.sh
# 2) 복원
sudo /opt/clovirone-web-assistant/scripts/rollback-clovirone-web-assistant.sh \
     /var/backups/clovirone-web-assistant/<복원할_시점>
```

`rollback-clovirone-web-assistant.sh <BACKUP_DIR>`의 동작:

1. `SHA256SUMS` **체크섬 검증 — 실패 시 즉시 중단** (exit 3)
2. 서비스 중지 (worker 먼저)
3. **우리 파일만** 복원: /opt, /etc/clovirone-web-assistant, web.sqlite3
   (소유권 clovirone-web, 0660), systemd 유닛, nginx vhost.
   공유 서버이므로 /etc/nginx 전체를 blanket-restore하지 않는다
4. `systemctl daemon-reload` → `nginx -t` (실패 시 vhost 심링크 제거 안내 후 중단)
5. 서비스 재기동 → `/healthz` 20초 폴링 — 성공 시 `ROLLBACK_OK`

`--uninstall` 옵션은 최초 설치 롤백용: 유닛/vhost 제거, **데이터는 보존**
(`/var/lib/clovirone-web-assistant` 삭제는 별도 수동 명령으로만).

## 4. 복원 후 검증 체크리스트

```bash
sudo /opt/clovirone-web-assistant/scripts/validate-clovirone-web-assistant.sh
curl -k https://clovirone-ai.gooddi.lab/readyz
journalctl -u clovirone-web-worker -n 20     # heartbeat 재개 확인
```

- 관리자 콘솔 Dashboard: worker/scheduler `up`, 마지막 백업 표시 정상
- 시험 로그인 + 채팅 1건 왕복
- Schedules: 복원 시점 이후 misfire된 occurrence는 정책(skip/run_once)대로
  처리되는지 run 이력 확인
- 이상 없으면 유지보수 모드 해제

## 권장 주기

- 앱 내 DB 백업: 일 1회 이상 (verified 상태 확인 습관화)
- 서버 전체 백업: 변경 배포 전 필수 + 주 1회
- 백업만 있고 복원 연습이 없으면 백업이 아니다 — 분기 1회 복원 리허설 권장
