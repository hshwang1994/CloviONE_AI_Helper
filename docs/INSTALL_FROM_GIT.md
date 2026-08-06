# Git 저장소로 설치하고 운영하기

이 문서 하나만 보고 `git clone` 부터 설치, 업데이트, 롤백까지 할 수 있게 쓴다.

> **이 문서에서 검증되지 않은 부분** (먼저 읽어라)
>
> 아래 절차를 **깨끗한 리눅스에서 실제로 돌려 보지 않았다.** 작성 환경이 Windows 라
> clone, 설치, 기동, 재부팅, 업데이트, 롤백을 한 번도 끝까지 실행한 적이 없다.
> 확인한 것은 다음뿐이다.
>
> - 모든 셸 스크립트가 `bash -n` 을 통과한다
> - 스크립트의 단계와 순서를 고정하는 테스트가 있다 (`tests/unit/test_update_script_contract.py`)
> - 되돌릴 수 없는 마이그레이션 판정 함수는 실제로 실행해서 다섯 가지 경우를 확인했다
> - gzip 절감량은 저장소의 실제 번들 파일을 압축해서 쟀다
>
> **처음 설치는 반드시 버려도 되는 장비에서 한 번 해 보고 운영에 적용해라.**

---

## 1. 두 가지 설치 방법

| | 번들 STAGE (예전부터 있던 방법) | Git clone (이 문서) |
|---|---|---|
| 원본 | 개발 머신에서 `build-bundle.sh` 로 만든 tar 를 scp | 서버에서 직접 `git clone` |
| 파이썬 의존성 | 번들에 들어 있는 wheelhouse (오프라인) | wheelhouse 를 따로 준비하거나 인터넷 |
| 설치 | `install-clovirone-web-assistant.sh` | `install-clovirone-web-assistant.sh --from-repo` |
| 업데이트 | `upgrade-clovirone-web-assistant.sh` | `update-from-git.sh` |
| 언제 쓰나 | 서버가 git 원격에 닿지 못할 때 | 서버가 git 원격(사내 GitLab 등)에 닿을 때 |

둘 다 같은 `/opt/clovirone-web-assistant` 를 만든다. 설치 스크립트는 하나이고,
원본이 어디냐만 다르다. 그래서 번들로 설치한 서버를 git 으로 업데이트하는 식으로
섞어 쓰지 마라. 되기는 하지만 `/opt` 에 무엇이 있는지 추적이 어려워진다.

---

## 2. 서버에 필요한 것

Ubuntu 24.04 기준. 설치 스크립트가 없는 것만 `apt` 로 넣는다.

- `python3.12-venv`, `nginx`, `openssl`, `sqlite3`, `zip`, `rsync`
- `git` (git 설치/업데이트 경로에서만 필요하다. 설치 스크립트는 안 쓴다)
- root 권한

### 인터넷이 필요한가

**필요할 수 있다. 어디로 나가는지 먼저 확인해라.** 폐쇄망 고객이 있어서 이 절을 따로 둔다.

| 무엇 | 나가는 곳 | 피하는 방법 |
|---|---|---|
| OS 패키지 | 배포판 apt 미러 | 사내 apt 미러를 쓰거나, 위 패키지를 미리 깔아 둔다 |
| 소스 코드 | git 원격 | 사내 GitLab 등 내부 미러 |
| 파이썬 의존성 | `pypi.org`, `files.pythonhosted.org` (HTTPS) | **wheelhouse** (아래) |
| 화면(JS/CSS) | 나가지 않는다 | 빌드 산출물이 저장소에 커밋돼 있다. 서버에 Node 가 필요 없다 |
| 웹폰트 | `cdn.jsdelivr.net` | 브라우저가 받는다. 못 받으면 시스템 글꼴로 떨어지고 화면은 정상이다 |

즉 **폐쇄망에서 반드시 미리 준비할 것은 wheelhouse 하나**다. 나머지는 사내 미러로 해결되거나
없어도 동작한다.

### 폐쇄망: wheelhouse 만들기

인터넷이 되는 머신에서 만들어 서버로 옮긴다. 아키텍처와 파이썬 버전을 맞춰야 한다.

```bash
# 인터넷이 되는 머신에서 (저장소 루트)
pip download --only-binary=:all: \
  --platform manylinux_2_28_x86_64 \
  --implementation cp --python-version 3.12 --abi cp312 --abi abi3 --abi none \
  -d wheelhouse -r requirements.txt
pip download --only-binary=:all: -d wheelhouse pip setuptools wheel

tar czf wheelhouse.tar.gz wheelhouse
# 서버로 옮긴 뒤, clone 한 저장소 루트에 wheelhouse/ 로 풀어 둔다
```

설치 스크립트는 `<저장소>/wheelhouse` 를 자동으로 본다. 다른 곳에 두려면
`WHEELHOUSE=/path/to/wheels` 를 넘긴다.

wheelhouse 가 없으면 스크립트가 로그에 이렇게 적고 인터넷으로 나간다.

```
wheelhouse 가 없습니다(/opt/src/clovirone-web-assistant/wheelhouse). pip 이 인터넷으로 나갑니다.
  필요한 호스트: pypi.org, files.pythonhosted.org (HTTPS)
  폐쇄망이면 중단하고 wheelhouse 를 먼저 만드십시오
```

폐쇄망이면 그 줄을 보는 즉시 `Ctrl+C` 로 멈춰라. 그대로 두면 몇 분 매달렸다가 죽는다.

---

## 3. 처음 설치

```bash
# 1) 저장소를 /opt 바깥에 clone 한다.
#    ⚠️ /opt/clovirone-web-assistant 안에 clone 하면 안 된다. 설치가 자기 자신을
#       덮어쓴다. 스크립트가 그 배치를 발견하면 멈춘다.
sudo mkdir -p /opt/src
cd /opt/src
sudo git clone <저장소 주소> clovirone-web-assistant
cd clovirone-web-assistant

# 2) (폐쇄망이면) wheelhouse 를 여기에 풀어 둔다

# 3) 설치. DNS_NAME 과 BIND_IP 는 설치처마다 다르므로 기본값이 없다.
sudo DNS_NAME=portal.example.internal BIND_IP=10.0.0.10 \
  bash scripts/install-clovirone-web-assistant.sh --from-repo

# 4) 최초 관리자 계정. 설치 로그에 임시 비밀번호가 남지 않도록 일부러 분리돼 있다.
sudo /opt/clovirone-web-assistant/venv/bin/python \
  /opt/clovirone-web-assistant/scripts/seed_admin.py

# 5) 확인
sudo DNS_NAME=portal.example.internal bash scripts/validate-clovirone-web-assistant.sh
```

성공하면 마지막 줄이 `INSTALL_OK` 다.

설치 스크립트가 하는 일 순서: 패키지 → **번들 신선도 검사** → 시스템 계정 → 디렉터리 →
소스 배포 → venv/의존성 → `web.env` 생성(SESSION_SECRET 은 서버에서 만든다) →
DB 마이그레이션 → systemd 유닛 → TLS 자체 서명 → nginx vhost + 로그 회전 → 기동 + health 확인.
여러 번 실행해도 안전하다(멱등).

### 번들 신선도 검사에서 멈춘다면

git 설치는 저장소에 **커밋된 화면 번들**(`app/static/react/`)을 그대로 서빙한다.
프런트 소스만 고치고 번들을 다시 안 만든 커밋을 설치하면, 그 서버는 아무 오류 없이
**옛 화면을 계속 돈다.** 로그에도 화면에도 흔적이 없다.

그래서 git 경로는 `scripts/check_bundle_fresh.py` 를 반드시 지난다. 걸리면 이렇게 멈춘다.

```
번들이 소스보다 낡았습니다. 이대로 설치하면 이 서버는 옛 화면을 조용히 계속 씁니다.
고치는 법(개발 머신에서): cd frontend && npm run build
                          python scripts/check_bundle_fresh.py --write
                          그리고 app/static/react/ 를 커밋해서 push
```

**우회로는 없다.** 우회할 수 있게 만들면 결국 우회하게 되고, 이 검사는 없는 것과 같아진다.

> **지금 상태 (2026-08-06 확인)**: 기준 파일 `app/static/react/BUILD_STAMP.json` 이 아직
> 없고, `frontend/src` 의 파일 다수가 현재 번들보다 나중에 수정돼 있다. 즉 **지금 커밋으로는
> git 설치와 git 업데이트가 위 메시지를 내고 멈춘다.** 최종 빌드를 한 뒤 `--write` 로
> 기준을 적고 커밋해야 열린다. 기준을 실제 빌드 없이 적으면 낡은 번들에 "최신" 도장을
> 찍는 것이라 이 검사가 통째로 거짓이 된다.

---

## 4. 업데이트

```bash
cd /opt/src/clovirone-web-assistant

# 무엇이 바뀌는지 먼저 본다. 아무것도 바꾸지 않는다.
sudo DNS_NAME=portal.example.internal BIND_IP=10.0.0.10 \
  bash scripts/update-from-git.sh --dry-run

# 실제 업데이트
sudo DNS_NAME=portal.example.internal BIND_IP=10.0.0.10 \
  bash scripts/update-from-git.sh
```

시작할 때 이런 것을 먼저 보여 주고 확인을 받는다.

```
------------------------------------------------------------
현재  : 0.1.0-dev  85d48eaa1b2c  2026-08-05
대상  : 0.2.0       9f13c7d0a4e1  2026-08-06  (origin/main)
------------------------------------------------------------
변경 내역 (7 커밋):
  9f13c7d feat(nginx): gzip 과 요청 속도 제한을 넣는다
  ...
------------------------------------------------------------
마이그레이션: 필요함
  [적용] alembic/versions/0049_ticket_labels.py
  [되돌릴 수 없음] alembic/versions/0050_drop_legacy_note.py  (upgrade() 가 테이블이나 컬럼을 지운다)
------------------------------------------------------------
```

옵션:

| 옵션 | 뜻 |
|---|---|
| `--dry-run` | 보고만 하고 멈춘다 |
| `--ref origin/release` | 특정 브랜치/태그/커밋으로 간다 (기본: 현재 브랜치의 upstream) |
| `--yes` | 확인 질문을 건너뛴다 (cron 등 비대화형) |

진행 순서와 그 이유:

1. **작업 트리가 깨끗한지 확인** - 롤백이 `git reset --hard` 를 쓰기 때문이다. 서버에서
   손으로 고친 것이 있으면 여기서 멈춘다. 그러지 않으면 되돌리는 순간 그 수정이 사라진다.
2. **fetch, 보고, 확인**
3. **코드 교체** - 실행 중인 앱은 `/opt` 에서 도니까 여기서 서비스는 멈추지 않는다.
4. **번들 신선도 검사** - 여기서 걸리면 **무정지로** 원래 커밋으로 돌아간다.
5. **서비스 정지 → 백업** - 순서가 중요하다. 백업을 먼저 뜨고 멈추면 그 사이에 쓰인
   데이터가 롤백 때 사라진다.
6. **설치** (`--from-repo`, 마이그레이션 포함)
7. **검증** - `healthz`, `readyz`, web/worker active. 하나라도 실패하면 롤백한다.

성공하면 마지막 줄이 `UPDATE_OK <이전> -> <이후>` 다.

---

## 5. 롤백이 실제로 무엇을 되돌리는가

**이 절을 읽지 않고 업데이트하지 마라.**

이 스크립트는 `alembic downgrade` 를 **쓰지 않는다.** 되돌릴 때는 백업해 둔 DB 파일을
통째로 제자리에 놓는다(`scripts/rollback-clovirone-web-assistant.sh`). 그래서:

- **되돌릴 수 없는 마이그레이션이 섞여 있어도 그 자리에서의 자동 롤백은 안전하다.**
  스키마도 데이터도 백업 시점 그대로 돌아온다. `downgrade()` 가 비어 있든 말든 상관없다.
- **백업 이후에 쓰인 데이터는 사라진다.** 그래서 서비스를 멈춘 뒤에 백업을 뜬다. 그러면
  "백업 이후"라는 창이 사실상 없다.
- ⚠️ **문제는 나중이다.** 업데이트가 성공해서 사람들이 새 버전으로 며칠 일한 뒤에
  되돌리고 싶어지면, 되돌리는 방법은 그때의 백업을 복원하는 것뿐이다. 즉 **그 며칠치
  작업을 버려야 한다.** 되돌릴 수 없는 마이그레이션이 있으면 다른 길이 없다.

그래서 업데이트를 시작할 때 그런 마이그레이션이 있는지 먼저 알려 주고 확인을 받는다.

판정 기준(어림짐작이다):

- `downgrade()` 가 아예 없다
- `downgrade()` 가 예외를 던진다
- `downgrade()` 본문에 `op.` 호출이 하나도 없다 (`pass` 뿐이다)
- `upgrade()` 가 `op.drop_table` / `op.drop_column` 을 부르거나 `DELETE` / `TRUNCATE` /
  `UPDATE` 를 실행한다 (컬럼을 되살려도 그 안에 있던 값은 돌아오지 않는다)

**경고가 없다고 "되돌릴 수 있다"는 뜻은 아니다.** 판정은 파일을 읽는 어림짐작이라 놓칠 수
있다. 큰 업데이트 전에는 마이그레이션을 직접 읽어라.

### 손으로 되돌리기

업데이트가 성공한 뒤에 되돌리고 싶다면, 스크립트가 마지막에 찍어 준 두 줄을 그대로 쓴다.

```bash
sudo bash scripts/rollback-clovirone-web-assistant.sh /var/backups/clovirone-web-assistant/20260806_143012
sudo git -C /opt/src/clovirone-web-assistant reset --hard 85d48eaa1b2c
```

백업 목록은 `ls -1 /var/backups/clovirone-web-assistant/` 로 본다.

---

## 6. 설치가 만드는 것

| 자리 | 내용 |
|---|---|
| `/opt/clovirone-web-assistant` | 애플리케이션 + `venv/` |
| `/etc/clovirone-web-assistant` | `web.env`, TLS, 허용 목록 JSON. 재설치해도 덮어쓰지 않는다 |
| `/var/lib/clovirone-web-assistant` | SQLite DB, 업로드, 생성물 |
| `/var/backups/clovirone-web-assistant` | 백업 (root 만, 0700) |
| `/var/log/clovirone-web-assistant/install.log` | 설치 로그 (git 설치일 때) |
| `/var/log/nginx/clovirone-web-assistant.*.log` | 이 서비스 전용 nginx 로그 |
| systemd | `clovirone-web-assistant`, `clovirone-web-worker`, `clovirone-privhelper` |

저장소에는 있지만 `/opt` 로 가지 않는 것: `.git`, `tests`, `docs`, `frontend/node_modules`,
`.claude`, `wheelhouse`, `dist`, `var`. 특히 `.claude` 는 에이전트 작업 사본이 쌓이는
자리라 반드시 빠져야 한다. 예전에 번들에 88벌(398MB)이 들어간 적이 있는데, 그때 진짜 문제는
용량이 아니라 **서버에서 어느 코드가 도는지 알 수 없게 된 것**이었다.

---

## 7. 자주 걸리는 곳

| 증상 | 원인과 조치 |
|---|---|
| `DNS_NAME 과 BIND_IP 를 지정해야 합니다` | 설치처마다 다른 값이라 기본값을 두지 않는다. 예전에 최초 고객사 값이 박혀 있어서 다른 곳에 설치하면 남의 이름으로 인증서를 만들었다 |
| `번들이 소스보다 낡았습니다` | 위 3절. 빌드 후 `--write` 로 기준을 적고 커밋해야 한다 |
| `저장소를 /opt/... 안에 clone 하지 마십시오` | clone 위치를 `/opt/src/...` 처럼 설치 대상 바깥으로 옮긴다 |
| `설치용 clone 에 커밋되지 않은 변경이 있습니다` | 서버에서 손으로 고친 것이 있다. `git -C <repo> status` 로 확인하고, 필요하면 저장소에 반영한 뒤 다시 시도한다 |
| pip 이 오래 매달린다 | 폐쇄망인데 wheelhouse 가 없다. 2절 |
| `nginx -t FAILED` | 스크립트가 우리 vhost 심링크를 걷어내고 멈춘다. 기존 nginx 설정은 그대로다. `/var/log/.../install.log` 를 본다 |
| `readyz` 실패로 롤백됨 | 마이그레이션이 어긋났을 가능성이 높다. `journalctl -u clovirone-web-assistant -n 100` |

---

## 관련 문서

- **[NGINX_AND_CAPACITY.md](NGINX_AND_CAPACITY.md)** - gzip, 요청 속도 제한, 동시 사용자 한계
- **[BACKUP_RESTORE.md](BACKUP_RESTORE.md)** - 백업과 복원의 전체 그림
- **[MAINTENANCE_PLAYBOOK.md](MAINTENANCE_PLAYBOOK.md)** - 번들 STAGE 경로를 포함한 유지보수 레시피
- **[RUNBOOK.md](RUNBOOK.md)** - 장애 대응
- **[OPERATIONS.md](OPERATIONS.md)** - 서비스, 로그, 일상 운영
