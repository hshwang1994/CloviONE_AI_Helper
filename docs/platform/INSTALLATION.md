# INSTALLATION — ClovirAssist 설치 · 배포 자동화 사양

> **이것은 Harness script 한 줄이 아니라 제품 요구사항이다** (D-205).
> 전담 소유 Session 은 **S4** 이고, 이후 **모든 Session 이 §6 Installer 계약**을 진다.
> 계획 전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md), 현재 상태는 [`WORK_STATE.md`](WORK_STATE.md).

**기록 시점**: 2026-08-21 (S0) — 아직 **구현 전 사양**이다. `deploy/install.sh` 는 S4 에서 생긴다.

---

## 1. Clean Ubuntu Server 24.04 에서 실행하는 최초 3줄

```bash
sudo apt-get update && sudo apt-get install -y git ca-certificates
sudo git clone --branch v<VERSION> https://gitlab.<사내>/clovir/clovirassist.git /opt/clovirassist
sudo /opt/clovirassist/deploy/install.sh install \
     --dns-name clovirassist.gooddi.lab --bind-ip <IP>
```

**사용자가 손으로 만드는 디렉터리도, 복사하는 파일도 없다.** `git clone` 이 `/opt/clovirassist` 를
만들고, 그 안의 `deploy/install.sh` 가 나머지 전부(`/etc/clovirassist` · `/var/lib/clovirassist` ·
`/var/backups/clovirassist` · venv · systemd · nginx · TLS)를 만든다.

> `sudo /opt/clovirassist/deploy/install.sh` 를 **최초 Entry Point 로 쓸 수 없다** — Clean Ubuntu 에
> 그 파일이 아직 없기 때문이다. 그래서 Source 확보(①②) 단계부터 사양에 넣는다.
> Ubuntu Server 24.04 최소 설치에는 `git` 이 없다.

---

## 2. 왜 `curl … | bash` 형태의 bootstrap installer 를 쓰지 않는가

이 저장소의 운영·보안 구조와 정면으로 어긋난다.

- `scripts/build-bundle.sh` 는 `MANIFEST.sha256` 을, 백업은 `SHA256SUMS` 를, rollback 은 그 검증을
  강제한다. **검증 없이 실행되는 원격 스크립트는 그 문화의 정반대다**
- CSP 가 inline script 를 금지하고 `check_git_secrets.py` 가 평문 자격증명을 훑는 제품에서,
  파이프 실행은 감사 흔적을 남기지 않는다
- `git clone` 은 **Source 확보 · 무결성(object hash) · Version 고정(tag)** 을 한 번에 준다
- clone 뒤에는 installer 가 **자기 Source 위치를 안다**(`git -C /opt/clovirassist rev-parse HEAD`).
  upgrade/rollback 이 같은 경로 위에서 이어진다 — 기존 `update-from-git.sh` 가 이미 쓰는 모델이다

---

## 3. Source 설정과 인증

```
GIT_REMOTE   https://gitlab.<사내>/clovir/clovirassist.git   # 제품 기준 Source
GIT_REF      v<VERSION>                                      # tag 고정. 브랜치 추적 금지
인증          GitLab deploy token (대화식 입력) 또는 SSH deploy key
```

- **토큰을 URL·명령행·환경변수에 넣지 않는다.** 비대화식 자동화가 필요하면
  `/etc/clovirassist/secrets/gitlab.token`(0600)을 **installer 가 만들어 주고**,
  `git -c credential.helper='!f(){ …; }'` 로 그 파일만 읽는다
- 사내 CA 를 쓰면 `ca-certificates` 갱신을 Preflight 가 확인한다
- 느린 회선이면 `--depth 1` 사용 가능. 단 이후 upgrade 가
  `git fetch --depth 1 origin refs/tags/<new>` 를 써야 하므로 installer 가 그 모드를 manifest 에 기록한다

**현 origin 이 GitHub(`hshwang1994/CloviONE_AI_Helper`)라는 사실은 제품 배포 Source 를 GitLab 으로
두는 요구를 축소하지 않는다.** Installer 는 **Remote 중립**으로 만들고 제품 문서/기본값은 GitLab 을
기준으로 한다. GitLab 주소가 정해지면 **설정만** 바꾼다 (R16).

### 3.1 폐쇄망 / GitLab 미도달 환경 — 오프라인 Bundle 경로 (계속 지원)

```bash
# 통제 장비에서 번들 생성 → scp 로 전달
scp clovirassist-bundle-v<VERSION>.tar.gz  <server>:/tmp/
sudo tar -xzf /tmp/clovirassist-bundle-v<VERSION>.tar.gz -C /opt
sudo /opt/clovirassist/deploy/install.sh install --source bundle \
     --dns-name clovirassist.gooddi.lab --bind-ip <IP>
```

번들은 `MANIFEST.sha256` + wheelhouse 를 포함하고 installer 가 **전개 전에 checksum 을 검증**한다.
`build-bundle.sh` 를 승계한다.

설치본에는 `installed_manifest.json`(source kind · git remote · ref · commit · VERSION ·
alembic head · PG/extension 버전 · 설치 시각 · Stage 결과)을 남긴다.

---

## 4. Entry Point — 설치 이후의 단일 명령

```bash
sudo /opt/clovirassist/deploy/install.sh <subcommand> [options]
```

서브커맨드: `install` · `upgrade` · `rollback` · `uninstall` · `verify` · `version` · `preflight`.

`upgrade` 는 `installed_manifest.json` 의 remote 를 읽어 스스로 `git fetch` → 원하는 tag checkout →
재설치한다. **사용자가 Source 위치를 다시 알려 줄 필요가 없다.**

---

## 5. Stage 정의 (0~18)

| # | Stage | 내용 | 실패 시 |
|---|---|---|---|
| 0 | **Preflight** | OS 24.04 확인 · 아키텍처 · 디스크/RAM · 포트 충돌 · DNS 해석 · 시간동기 · 필수 인자 · 기존 설치 감지 · 네트워크(또는 오프라인 모드) | **아무것도 바꾸기 전에** 중단 |
| 1 | apt dependency | `postgresql-16` `postgresql-16-pgvector` `postgresql-contrib` `nginx` `python3.12-venv` `rsync` `openssl` `nfs-common` `cifs-utils` (+ Storage 사용 시) | 패키지명·원인 표시 |
| 2 | 계정·디렉터리 | `clovirassist` 시스템 계정 · `/opt` `/etc` `/var/lib` `/var/backups` 권한 | |
| 3 | Source 배치 | git clone/checkout 또는 bundle 전개 (`rsync --delete`) | |
| 4 | Python Runtime | venv + wheelhouse 우선 `pip install` | |
| 5 | Frontend Artifact | **커밋된 빌드 산출물(`app/static/react/`) 사용이 기본.** `check_bundle_fresh.py` 로 신선도 검증. Node 가 있으면 소스 빌드 옵션 | 번들 stale 이면 중단 |
| 6 | **PostgreSQL 설치·초기화** | cluster 확인 · `clovirassist` role/DB 생성 · locale/encoding(UTF-8) · `pg_hba` 최소 권한 · listen 127.0.0.1 · 접속 검증 · **`PG_BIN_DIR` 를 `web.env` 에 쓴다**(비우면 `PATH` 의 낮은 버전 `pg_dump` 를 집어 백업이 조용히 실패한다 — S2) · **`max_connections` ≥ 워커수 ×(pool 5 + overflow 10)** | |
| 7 | **Extension** | `CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;` + 버전 기록 | 미설치 원인 표시 |
| 8 | Configuration/Secret 분리 | `/etc/clovirassist/clovirassist.env`(0640) + `/etc/clovirassist/secrets/`(0700). **DB 비밀번호는 DSN 이 아니라 `.pgpass`/파일 참조** | |
| 9 | **DB Migration** | `alembic upgrade head`. 실행 전 현재 revision 과 목표 revision 출력 | revision 위치 표시 |
| 10 | Seed/부트스트랩 | 최초 관리자 · 기본 Role/Permission · 기본 Storage Provider(Local) | |
| 11 | **File Storage 준비** | 디렉터리 생성/권한 · 마운트 유닛 설치(NFS/SMB 설정 시) · **`st_dev` 마운트 검증** | 미마운트면 쓰기 거부 상태로 표시 |
| 12 | **AI Component** | Embedding/Rerank 모델 파일 배치(오프라인 캐시 지원) · ONNX Runtime · 로드 검증 | 모델 부재 원인 표시 |
| 13 | systemd unit 생성/설치 | `clovirassist-web` · `-worker` · `-scheduler` · `-index` · `-privhelper` | |
| 14 | `systemctl enable` + 의존 순서 | §6 | |
| 15 | nginx | 템플릿 치환 + **미치환 플레이스홀더 거부** + `nginx -t` | |
| 16 | TLS | 인증서 존재 확인 또는 자체 서명 생성. **CN/SAN = `--dns-name`** | |
| 17 | 기동 + **Health Check** | 순서대로 기동 후 `/healthz` `/readyz` + DB + Storage + AI probe | 어느 컴포넌트가 왜 실패했는지 표시 |
| 18 | 설치 검증 | `verify_deploy.sh` + `validate` 실행, `installed_manifest.json` 확정 | |

**설치 실패 위치·원인 표시**: 각 Stage 는 `STAGE_<n>_<NAME>: OK|FAIL <사유> <조치>` 형식으로
출력하고 `/var/log/clovirassist/install-<ts>.log` + `install_state.json` 에 남긴다.
**어느 단계에서 왜 멈췄는지가 표준 출력만 보고 판별돼야 한다.**

**Idempotent 재실행**: 모든 Stage 가 "이미 되어 있음" 을 감지하고 건너뛴다. 재실행이 데이터·설정을
파괴하지 않는다. 실패 후 재실행은 실패 지점부터 의미 있게 이어진다.

> **현행 installer 의 알려진 실패 모드**: Stage 4 `rsync --delete` 와 Stage 5 venv 재생성 **뒤에**
> 테넌트 값 가드가 `exit 21` 을 하여 **"새 코드 + 옛 스키마"** 상태를 남긴다
> (`scripts/install-clovirone-web-assistant.sh:221-235`).
> 새 설계는 **검증을 전부 Preflight 로 끌어올려** 이 상태를 만들지 않는다.

**설치 Version 확인**: `deploy/install.sh version` → VERSION · git ref/commit · alembic head ·
PG 버전 · extension 버전 · 각 서비스 상태.

---

## 6. 서비스 의존 순서와 자동 시작 (U14)

```
network-online.target
   └─ postgresql.service
        ├─ clovirassist-web.service         After=postgresql  Wants=network-online
        ├─ clovirassist-worker.service      After=postgresql
        ├─ clovirassist-scheduler.service   After=postgresql
        └─ clovirassist-index.service       After=postgresql
   (Storage 사용 시) RequiresMountsFor=/var/lib/clovirassist/files
```

- 전 유닛 `systemctl enable` — **재부팅 후 수동 명령 없이 복구된다**
- `Restart=on-failure` + `RestartSec` + `StartLimit*`
- 기동 시 **PG 준비 대기**(재시도) — `After=` 만으로는 PG 가 접속 가능하다는 보장이 없다
- **Storage 마운트 전 기동 문제**: `RequiresMountsFor=` + 기동 시 `st_dev` 검사.
  마운트 안 됐으면 **쓰기를 거부**한다 — 로컬 디스크에 조용히 쌓이는 사고 방지

### 6.1 Installer 계약 — 모든 Session 에 적용 (D-205)

**Runtime Component 를 추가하는 Session 은 그 Session 안에서**

1. installer Stage
2. systemd unit + `enable` + 의존 순서
3. health probe
4. uninstall 경로
5. reboot 후 복구

를 **함께** 완성한다. **"나중에 설치 붙이기" 를 허용하지 않는다.**

---

## 7. 검증 환경과 그 한계

| 환경 | 용도 | 한계 (과장하지 않는다) |
|---|---|---|
| **LXD/Incus Ubuntu 24.04 시스템 컨테이너** (테스트 서버 위) | **반복 가능한 Clean 설치 리허설.** 폐기·재생성이 싸서 idempotency · 실패지점 표시 · upgrade/rollback/uninstall 을 몇 번이고 돌린다 | 커널을 공유한다. **비특권 컨테이너에서는 NFS/CIFS 마운트가 제한된다** → Storage 검증은 여기서 하지 않는다. **진짜 reboot 도 아니다** |
| **실 Ubuntu 24.04 VM** 또는 **테스트 서버 자체** | **최종 Acceptance**: Storage(NFS/SMB) · 실제 Reboot · TLS · 성능 | 테스트 서버를 쓰는 경우 재부팅 창이 필요하다 |

**컨테이너 통과를 "설치 검증 완료" 라고 쓰지 않는다** (R15).

### 7.1 Reboot Test — 제품 전체 (U14)

Storage 만이 아니라 전 서비스를 대상으로 한다.

`reboot` → 로그인 없이 대기 → `systemctl is-active` 전 유닛 · `postgresql` · `nginx` →
`/healthz` `/readyz` → 로그인 → 대표 데이터 조회 → Storage 쓰기/읽기 →
Worker/Scheduler 틱 진행 확인 → **실패 유닛 0**.

**실행 시점 (E4)**: **S4** 에서는 그 시점에 존재하는 Component 범위(PG · web · worker · scheduler ·
nginx)로 1회. **S22** 에서 Storage · AI · index lane 까지 포함한 **전 Component** 로 §8 의 일부로
수행한다. 그 사이 Session 들은 §6.1 에 따라 **자기가 추가한 Component 의 기동·복구만** 확인하고
전 제품 Reboot 을 반복하지 않는다.

---

## 8. 최종 Acceptance 시나리오 (S22 에서 실행)

**Clean Ubuntu Server 24.04 에서 §1 의 세 줄로 시작한다. 다른 문서를 참조하지 않는다.**

| # | 단계 | 확인 |
|---|---|---|
| 1 | 전체 자동 설치 | Stage 0~18 전부 `OK`. **수동 mkdir/cp 0회** |
| 2 | DB 준비 / Migration | `install.sh version` 의 alembic head == 코드 head |
| 3 | 서비스 자동 등록 | `systemctl is-enabled` 전 유닛 `enabled` |
| 4 | Health PASS | `/healthz` `/readyz` 200 + DB·Storage·AI probe |
| 5 | Login / Smoke PASS | 로그인 → 사용자 콘솔 → 관리자 콘솔 → 대표 데이터 |
| 6 | **Server Reboot** | `sudo reboot` |
| 7 | 전체 서비스 자동 복구 | **수동 명령 0회.** `systemctl is-active` 전 유닛 + `postgresql` + `nginx` |
| 8 | Health PASS | 동일 |
| 9 | 기존 데이터 정상 | 재부팅 전 데이터가 그대로 조회됨 |
| 10 | Upgrade 검증 | `install.sh upgrade --ref v<VERSION+1>` → Health PASS. 실패 주입 시 `rollback` 으로 원복 |

**부가 검증**

1. 3번째 명령 **재실행(idempotent)** — 데이터·설정 무손상
2. `uninstall` 후 **재설치**
3. 의도적 Stage 실패 주입 시 **어느 Stage 에서 왜 멈췄는지 표준 출력만으로 판별되는지**
4. 오프라인 Bundle 경로로도 동일 시나리오 1회

---

## 9. 현재 자산 실측 — 있는 것과 없는 것 (2026-08-20 · **S2 반영 2026-08-21**)

| 있는 것 | 상태 |
|---|---|
| `scripts/install-clovirone-web-assistant.sh` (12 stage) | 존재. **S2 가 SQLite 자국만 걷어냈다**(`sqlite3` 패키지 → `postgresql-client-16`, PRAGMA 확인 → `alembic current` 확인, 「기존 설치인가」 판정을 `DATABASE_URL` 기준으로). 여전히 **Notion·n8n 결합**이고 PostgreSQL 설치·AI·Storage 개념이 없다 — 전면 재작성은 S4 |
| `scripts/upgrade-*.sh` · `rollback-*.sh`(`--uninstall` 포함) · `update-from-git.sh` · `build-bundle.sh` | 존재. **S2 가 백업/롤백의 단일 파일 전제를 걷어냈다**: `backup-*.sh` 는 `pg_dump -Fc` + `pg_restore --list` 검증이고 **실패하면 죽는다**(예전엔 파일이 없으면 조용히 건너뛰고 `BACKUP_OK` 를 찍었다), `rollback-*.sh` 는 `pg_restore --clean --if-exists` 이고 **SQLite 시절 백업을 만나면 그렇게 말하고 멈춘다**. 운영 정책(Schedule·Retention·Manifest)은 여전히 **S12** |
| `deploy/00-precheck.sh` · `deploy/nginx/*.conf`(`__DNS_NAME__` 템플릿) · systemd unit 4종 | **재사용 가능한 뼈대** |
| `scripts/validate-clovirone-web-assistant.sh` | **n8n 활성 단언**(`:23`)이 박혀 있어 **n8n 제거 시 실패한다** → S11 |

| 없는 것 |
|---|
| GitLab 기준 Source 경로 · **PostgreSQL 서버 설치/초기화**(Stage 6·7 — S2 는 앱만 옮겼다) · Extension · Storage 준비 · AI Component · Scheduler 별도 인식 · **전 제품 Reboot 검증** · Clean OS 재현 설치 검증 |

### 9.1 nginx 하드 블로커

`nginx client_max_body_size` 는 기본 **256k** 이고, 대화 메시지(8m)·게시판 첨부(12m) location 만
올려 놨다. **파일 업로드 제품화의 하드 블로커다** — S8 에서 Storage 와 함께 푼다.

---

## 10. 제품 slug 이전 (R13)

현재 slug `clovirone-web-assistant` 가 경로·유닛·백업 루트에 박혀 있고 템플릿화돼 있지 않다.

- **새 설치**: Installer 가 새 slug `clovirassist` 로 설치한다 (`/opt/clovirassist` ·
  `/etc/clovirassist` · `/var/lib/clovirassist` · `/var/backups/clovirassist` ·
  `clovirassist-{web,worker,scheduler,index,privhelper}.service`)
- **기존 설치**: 경로 이전은 **upgrade 경로**로 처리한다
- 사용자 노출 면은 전부 `ClovirAssist` 로 통일한다 (S3)
