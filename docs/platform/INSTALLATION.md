# INSTALLATION — ClovirAssist 설치 · 배포 자동화 사양

> **이것은 Harness script 한 줄이 아니라 제품 요구사항이다** (D-205).
> 전담 소유 Session 은 **S4** 이고, 이후 **모든 Session 이 §6 Installer 계약**을 진다.
> 계획 전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md), 현재 상태는 [`WORK_STATE.md`](WORK_STATE.md).

**기록 시점**: 2026-08-21 (S0) · **S4 실행 반영** 2026-08-22 — `deploy/install.sh` 가 생겼고
LXD 리허설과 실 재부팅으로 확인했다. 아래에서 **실제와 달랐던 자리는 실제에 맞게 고쳤다**
(CLAUDE.md 머리말). 무엇을 왜 고쳤는지는 각 자리에 적어 둔다.

---

## 1. Clean Ubuntu Server 24.04 에서 실행하는 설치 명령

**최종 사용자 경로(Release, D-522).** Release 페이지에서 `install.sh` 하나를 받아 실행한다. 스크립트는 같은 Release 의
제품 묶음과 `SHA256SUMS` 를 받아 **체크섬이 맞을 때만** 풀고 나머지 Stage 를 지난다. Release 에 올린 사본은 그 Release
의 태그를 기본값으로 들고 있어 `--release` 를 따로 주지 않아도 자기 버전을 설치한다.

```bash
curl -fsSLO https://github.com/hshwang1994/clovirassist/releases/download/v<VERSION>/install.sh
sudo bash install.sh install --dns-name <host> --bind-ip <IP>
```

**개발자 경로(git).** 저장소를 설치 자리에 받고 그 안의 스크립트를 실행한다.

```bash
sudo apt-get update && sudo apt-get install -y git ca-certificates
sudo git clone --branch v<VERSION> https://github.com/hshwang1994/clovirassist.git /opt/clovirassist
sudo /opt/clovirassist/deploy/install.sh install --dns-name <host> --bind-ip <IP>
```

폐쇄망은 §3.1 의 오프라인 번들로 설치한다. 어느 길로 설치해도 설치가 끝나면 첫 관리자 설정 코드가 콘솔에 한 번 나오고
(§11), `/usr/local/bin/clovirassist` 명령이 생긴다(§4).

설치처 앞에 역방향 프록시(로드밸런서 · 사내 게이트웨이)가 있으면 그 주소를 `--upstream-proxy <ip[,cidr…]>` 로 함께 준다.
안 주면 nginx 의 속도 제한이 그 프록시 주소 하나에 걸려 **사용자 전원이 한 예산을 나눈다**(근거와 실측은
`docs/NGINX_AND_CAPACITY.md`). 한 번 주면 manifest 가 기억하므로 업그레이드 때 다시 줄 필요가 없고, `none` 을 주면 지운다.

대표 이름(`--dns-name`) 말고도 같은 서비스를 열 이름이 있으면 `--alias-name <name[,name…]>` 로 함께 준다(다섯 개까지, D-573).
별칭은 대표 이름과 **같은 server 블록**이 받고 같은 인증서의 SAN 에 들어간다 — 리디렉션하지 않으므로 옛 이름의 즐겨찾기와 검증
스크립트가 그대로 열린다. 알림 메일 · 링크의 주소(`APP_BASE_URL`)는 언제나 대표 이름 하나다. 한 번 주면 manifest 의 `alias_names`
가 기억하고, `none` 을 주면 지운다. 이름이 이 서버에서 안 풀리면 설치는 계속하고 알림만 남긴다. 운영 중에 대표 이름을 바꾸는 일은
설치 명령 대신 관리 화면이 한다(§12 「서비스 주소」).

**사용자가 손으로 만드는 디렉터리도, 복사하는 파일도 없다.** `git clone` 이 `/opt/clovirassist` 를
만들고, 그 안의 `deploy/install.sh` 가 나머지 전부(`/etc/clovirassist` · `/var/lib/clovirassist` ·
`/var/backups/clovirassist` · venv · systemd · nginx · TLS)를 만든다.

> git 경로에서 `sudo /opt/clovirassist/deploy/install.sh` 를 **최초 Entry Point 로 쓸 수 없다** — Clean Ubuntu 에
> 그 파일이 아직 없기 때문이다. 그래서 Source 확보 단계부터 사양에 넣는다. Ubuntu Server 24.04 최소 설치에는 `git` 이
> 없다. Release 경로는 `curl`(최소 설치에 있다)로 스크립트 하나를 받는 것이 Source 확보다.

---

## 2. 왜 `curl … | bash` 형태의 bootstrap installer 를 쓰지 않는가

이 저장소의 운영·보안 구조와 정면으로 어긋난다.

- `scripts/build-bundle.sh` 는 `MANIFEST.sha256` 을, 백업은 `SHA256SUMS` 를, rollback 은 그 검증을
  강제한다. **검증 없이 실행되는 원격 스크립트는 그 문화의 정반대다**
- CSP 가 inline script 를 금지하고 `check_git_secrets.py` 가 평문 자격증명을 훑는 제품에서,
  파이프 실행은 감사 흔적을 남기지 않는다
- `git clone` 은 **Source 확보 · 무결성(object hash) · Version 고정(tag)** 을 한 번에 준다
- clone 뒤에는 installer 가 **자기 Source 위치를 안다**(`git -C /opt/clovirassist rev-parse HEAD`).
  upgrade/rollback 이 같은 경로 위에서 이어진다 — 옛 `update-from-git.sh` 가 이미 쓰던 모델이고, S4 가 그것을 `deploy/install.sh` 안으로 옮겼다(S14 가 옛 스크립트를 지웠다)
- **Release 경로도 파이프 실행이 아니다(D-522).** 스크립트는 파일로 받아 읽은 뒤 실행하고, 그 체크섬은 Release 의
  `SHA256SUMS` 에 있다. 스크립트는 제품 묶음을 받은 뒤 **자기 줄을 글자 그대로 골라** 맞춰 보고, 맞을 때만 푼다.
  확인은 Stage 0 안에서 끝나므로 틀린 묶음은 서버에 아무 흔적도 남기지 않는다

---

## 3. Source 설정과 인증

```
Release      https://github.com/hshwang1994/clovirassist/releases/download/v<VERSION>/   # 기본
             --release-base <url> 로 사내 미러를 가리킬 수 있다
GIT_REMOTE   https://github.com/hshwang1994/clovirassist.git                            # git 경로
GIT_REF      v<VERSION>                                                                 # tag 고정. 브랜치 추적 금지
```

- Installer 는 **Remote 중립**이다. 사내 미러를 쓰면 `--git-remote <url>` 이나 `--release-base <url>` 만 바꾼다.
  한 번 준 remote 는 manifest 가 기억한다
- **토큰을 URL·명령행·환경변수에 넣지 않는다.** 비공개 미러에 인증이 필요하면 git 의 자격 증명 도우미를 쓴다
- 사내 CA 를 쓰면 `ca-certificates` 갱신을 Preflight 가 확인한다

### 3.1 폐쇄망 — 오프라인 Bundle 경로 (계속 지원)

```bash
# 통제 장비에서 번들 생성(bash scripts/build-bundle.sh) → scp 로 전달
scp dist/clovirassist-bundle.tar.gz <server>:/var/tmp/
sudo tar -xzf /var/tmp/clovirassist-bundle.tar.gz -C /var/tmp
sudo /var/tmp/stage/app-src/deploy/install.sh install --source bundle --offline \
     --dns-name <host> --bind-ip <IP>
```

번들은 `MANIFEST.sha256` + wheelhouse + 메일 구성 요소 `.deb`(`debs/`, Ubuntu 24.04 amd64, D-551)를 포함하고, installer 가 Stage 0 에서 **전개 전에 모든 파일을 그 목록으로
확인한다**(D-522. 예전 문서는 그렇게 적었지만 설치가 목록을 읽지 않았다). wheelhouse 는 번들 안의 `wheels/` 가 기본이다.
**wheelhouse 는 x86_64 용이다.** arm64 서버에서 번들로 설치하려 하면 Stage 0 이 멈춘다. 메일 구성 요소는 번들 안의 `debs/` 를
임시 로컬 apt 원본으로 걸고 깐 뒤 그 원본을 지운다(`--mail-debs <dir>` 로 다른 자리를 준다). `debs/` 가 없는 옛 번들은 경고하고
메일 구성 요소만 건너뛴다.

설치본에는 `installed_manifest.json`(source kind · git remote · ref · commit · Release 태그 · VERSION ·
alembic head · PG/extension 버전 · DNS 이름 · 별칭 목록(`alias_names`) · 바인드 주소 · 앞단 프록시 목록 · AI 상태(`with_ai`) ·
설치 시각 · Stage 결과)을 남긴다. 이 파일은 언제나 엄격한 JSON 이다 — 문자열의 줄바꿈 · 탭은 공백으로, CR 과 나머지 제어 문자는
걷는다(Windows 체크아웃에서 보낸 `VERSION` 의 CR 이 그대로 들어가 파이썬이 못 읽은 일이 있었다, 2026-10-15). 그 전에 쓴 매니페스트는
제품이 너그럽게 읽는다. 대표 이름 · 별칭은 관리 화면의 서비스 주소 바꾸기도 이 파일에 쓰므로 다음 `upgrade` 가 그대로 이어 받는다.

---

## 4. Entry Point — 설치 이후의 단일 명령

설치가 `/usr/local/bin/clovirassist` 를 깐다(Stage 13, D-522). 설치 뒤의 운영은 이 명령 하나로 한다.

```bash
sudo clovirassist <명령> [options]
```

| 명령 | 하는 일 |
|---|---|
| `install` · `upgrade` · `rollback` · `uninstall` · `verify` · `version` · `preflight` · `storage` · `ai` · `mail-relay` | 설치본의 `deploy/install.sh` 의 같은 서브커맨드다. `mail-relay` 는 로컬 릴레이 구성 요소를 나중에 깐다 |
| `first-admin-code` | 사용자가 아직 없을 때 첫 관리자 설정 코드를 새로 만든다(§11) |
| `user` · `migrate` · `storage-cli` · `ai-cli` | 제품 도구다. 서비스 계정과 설치 환경으로 돈다(`install.sh app-cli`) |

`sudo /opt/clovirassist/deploy/install.sh <subcommand>` 도 그대로 된다 — `clovirassist` 는 그 앞면이다.

**ClovirAssist 로컬 릴레이 구성 요소는 기본 설치 · 기본 꺼짐이다**(D-551). Stage 1 이 `postfix` · `opendkim` ·
`libsasl2-modules` 를 함께 깔지만, 설치하는 동안 서비스가 뜨지 않게 막고(`policy-rc.d`) 끝나면 두 서비스를 끄고 25 · 2525 · 8891 을
아무도 듣지 않는지 확인한다(어기면 Stage 1 이 실패다). 실제로 쓸지는 관리자가 메일 화면에서 고른다. 다른 메일 발송 프로그램(exim4 ·
sendmail …)이 있거나 제품 표지가 없는 Postfix 설정이 이미 있으면 **아무것도 깔거나 바꾸지 않는다** — 그 서버는 「외부 SMTP 사용」에서
그 메일 서버를 지정한다. 꾸러미 설치까지 빼려면 `--without-mail-relay` 를 준다(특수 설치 예외). 빼고 깐 서버에 나중에 깔려면
`sudo clovirassist mail-relay` 다.

**AI 는 기본이 꺼짐이다**(D-259). 켜려면 설치 때 `--with-ai` 와 함께 `--download-model`(설치가 모델을 받는다) 이나
`--ai-model-dir <모델 디렉터리>`(폐쇄망) 를 주거나, 나중에 `sudo clovirassist ai --download-model` 을 돌린다.
**모델을 받는 것은 부탁했을 때만이다(D-522).** 받는 것은 설치 셸이고, 주소, revision(커밋 해시), 파일마다의 크기와
sha256 은 제품 카탈로그(`app/ai/catalog.py`)가 고정한다. 받은 파일이 그 값과 다르면 캐시에 놓지 않는다. 제품(웹, 워커)은
모델 호스트로 나가지 않는다 — 바깥 허용 목록에 그 호스트가 없다.

**업그레이드는 AI 상태를 이어 간다(D-570).** `upgrade` 와 `ai` 에 AI 옵션이 하나도 없으면 지금 상태(manifest 의 `with_ai`, 또는 env 의
`AI_ENABLED=true`)를 그대로 쓴다 — 예전에는 옵션 없는 `upgrade`(배포 스크립트가 그렇게 돈다)가 `AI_ENABLED=false` 를 써서 깔려 있던
의미 검색을 조용히 껐다. 끄는 것은 `--without-ai` 로만 한다. `install` 의 뜻은 그대로다(옵션이 곧 상태). `sudo clovirassist ai` 는
모델과 런타임을 확인한 뒤 색인 유닛과 함께 **떠 있는** web · 배치 · 대화형 유닛도 다시 시작한다 — web 은 부팅 때 AI 연결을 만들고
다시 뜨기 전까지 「모델이 없다」고 말한다. 꺼져 있던 유닛은 켜지 않는다.

`upgrade` 는 git 설치면 `installed_manifest.json` 의 remote 를 읽어 스스로 `git fetch` → 원하는 tag checkout → 재설치하고
(`--ref v<다음>`), Release 설치면 다음 Release 를 받아 확인한 뒤 재설치한다(`--release v<다음>`). **사용자가 Source 위치를
다시 알려 줄 필요가 없다.** Release 설치에 다음 버전을 주지 않은 업그레이드는 거절한다.

---

## 5. Stage 정의 (0~18)

| # | Stage | 내용 | 실패 시 |
|---|---|---|---|
| 0 | **Preflight** | **Ubuntu 24.04 만**(다른 버전은 멈춘다, D-522) · 아키텍처 · 디스크/RAM · 포트 충돌 · DNS 해석 · 시간동기 · 필수 인자 · 기존 설치 감지 · 네트워크(또는 오프라인 모드) · **Release 받기와 체크섬 확인**, 번들의 `MANIFEST.sha256` 확인 | **아무것도 바꾸기 전에** 중단 |
| 1 | apt dependency | `postgresql-16` `postgresql-16-pgvector` `postgresql-contrib` `nginx` `python3.12-venv` `rsync` `openssl` `nfs-common` `cifs-utils` (+ Storage 사용 시) · 메일 구성 요소 `postfix` `opendkim` `libsasl2-modules`(설치 뒤 꺼짐, 다른 MTA · 기존 구성이 있으면 건너뜀, D-551) | 패키지명·원인 표시. 메일 구성 요소가 켜져 있거나 메일 포트를 듣는 것이 있으면 멈춘다 |
| 2 | 계정·디렉터리 | `clovirassist` 시스템 계정 · `/opt` `/etc` `/var/lib` `/var/backups` 권한 | |
| 3 | Source 배치 | git clone/checkout, 확인한 Release 트리, bundle 전개 (`rsync --delete`) | |
| 4 | Python Runtime | venv + wheelhouse 우선 `pip install`. **폐쇄망은 wheelhouse 에 `Pillow` 가 있어야 한다** — 프로필 사진을 서버가 디코드해서 다시 그린다(D-350). 없으면 아바타 업로드만 거절되고 나머지 제품은 그대로 돈다 | |
| 5 | Frontend Artifact | **커밋된 빌드 산출물(`app/static/react/`) 사용이 기본.** `check_bundle_fresh.py` 로 신선도 검증. Node 가 있으면 소스 빌드 옵션. 기본 아바타(DiceBear)는 이 산출물 안에 이미 들어 있다 — **설치 시점에 npm 도 인터넷도 필요 없다**(D-350) | 번들 stale 이면 중단 |
| 6 | **PostgreSQL 설치·초기화** | cluster 확인 · `clovirassist` role/DB 생성 · locale/encoding(UTF-8) · `pg_hba` 최소 권한 · listen 127.0.0.1 · 접속 검증 · **`PG_BIN_DIR` 를 `web.env` 에 쓴다**(비우면 `PATH` 의 낮은 버전 `pg_dump` 를 집어 백업이 조용히 실패한다 — S2) · **`max_connections` ≥ 워커수 ×(pool 5 + overflow 10)** | |
| 7 | **Extension** | `CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;` + 버전 기록 | 미설치 원인 표시 |
| 8 | Configuration/Secret 분리 | `/etc/clovirassist/clovirassist.env`(0640) + `/etc/clovirassist/secrets/`(**0750** — 소유 `root`, 그룹이 서비스 계정이다. `0700` 이면 제품이 자기 비밀을 못 읽는다. S14 가 실측으로 고쳤다). **DB 비밀번호는 DSN 이 아니라 `.pgpass`/파일 참조**. 허용 목록은 **새 기본 호스트만 더한다**(`deploy/merge_allowlist.py`, 운영자가 지운 기본 항목은 되살리지 않는다, D-522). 옛 `LLM_*` 키를 지우고 옛 API 키 파일을 `ai.anthropic.api_key` 로 옮긴다 | |
| 9 | **DB Migration** | `alembic upgrade head`. 실행 전 현재 revision 과 목표 revision 출력 | revision 위치 표시 |
| 10 | Seed/부트스트랩 | 기본 Role/Permission. 사용자가 0명이면 **첫 관리자 설정 코드**를 만든다(해시만 저장, 원문은 설치가 끝난 뒤 콘솔에만, §11) | |
| 11 | **File Storage 준비** ✅ | 디렉터리 생성/권한 · 기본 LOCAL Provider 부트스트랩 · **마운트 유닛과 `RequiresMountsFor=` drop-in 을 제품이 만들어 설치** · `systemctl enable --now` · **제품 코드로 `st_dev` 마운트 검증**(`storage_cli status` 의 종료코드가 계약이다) | 미마운트면 **쓰기를 거부하는 상태**라고 표시하고 멈춘다. 붙일 유닛 이름을 함께 낸다 |
| 12 | **AI Component** ✅ | 모델 캐시 디렉터리 · (`--with-ai` 일 때) `requirements-ai.txt` 설치 · 모델 파일 배치(`--ai-model-dir` 나 번들, 또는 `--download-model` 이면 카탈로그가 고정한 체크섬으로 받아 확인) · **제품 CLI 로 로드 검증**(`ai_cli status` 의 종료코드가 계약이고, `ai_cli selftest` 가 실제로 벡터를 만들어 길이까지 본다). AI 를 끄고 설치하면 캐시 자리만 만들고 **OK** 다 (D-259) | 켰는데 못 쓰면 **멈춘다**. 어느 파일이 없거나 틀렸는지는 로그가 말한다 |
| 13 | systemd unit 생성/설치 | **지금 여섯**: `clovirassist-web` · `-worker` · `-worker-conversational` · `-scheduler` · `-index` · `-privhelper`. `-index` 는 S9 이 넣었다(P-18 · D-257). 소스에 레인이 있는데 유닛이 없으면 이 Stage 가 막는다. 운영 명령 `/usr/local/bin/clovirassist` 도 여기서 깐다 | |
| 14 | `systemctl enable` + 의존 순서 | §6 | |
| 15 | **TLS** | 인증서 존재 확인 또는 자체 서명 생성. **CN = `--dns-name`, SAN = 대표 이름 + 별칭 전부 + 바인드 주소**(D-573). 있으면 SAN 이 그 이름을 모두 담는지까지 본다(있다 ≠ 맞다). 이름이 빠진 인증서가 **자체 서명이면** 이름을 더해 새로 만든다 | 이름이 빠진 인증서가 남이 발급한 것이면 바꾸지 않고 멈춘다(36) |
| 16 | nginx | 템플릿 치환(`__SERVER_NAMES__` = 대표 이름 + 별칭, 인증서 경로의 `__DNS_NAME__` = 대표 이름) + **미치환 플레이스홀더 거부** + 앞단 프록시 신뢰 목록(`/etc/clovirassist/nginx/realip.conf`, `--upstream-proxy`) + `nginx -t` + 이름마다 `server_name` 블록이 우리 둘(:80 · :443)뿐인지 정확한 이름으로 센다 | 목록을 줬는데 nginx 에 realip 모듈이 없으면 멈춘다. 다른 vhost 가 같은 이름을 들면 멈춘다 |
| 17 | 기동 + **Health Check** | 순서대로 기동 후 `/healthz` `/readyz` + DB + Storage + AI probe | 어느 컴포넌트가 왜 실패했는지 표시 |
| 18 | 설치 검증 | **`install.sh verify` 를 그대로 실행**하고 `installed_manifest.json` 을 확정한다. 옛 `validate-clovirone-web-assistant.sh` 는 부르지 않는다 — 옛 slug 설치 전용이고 n8n 활성 단언이 박혀 있어 S14 가 지웠다(§9). 새 설치의 검증 정본은 `verify` 하나다 | |

> **15·16 은 초안과 순서가 바뀌었다(S4).** 초안은 15=nginx, 16=TLS 였는데 **그 순서로는 돌 수가
> 없다**: `nginx -t` 는 `ssl_certificate` 파일이 없으면 `cannot load certificate …
> BIO_new_file() failed` 로 죽는다. LXD 리허설이 정확히 거기서 멈췄고, 문서를 실제에 맞췄다.

**설치 실패 위치·원인 표시**: 각 Stage 는 `STAGE_<n>_<NAME>: OK|SKIP|FAIL <사유> | 조치: <조치>`
형식으로 출력하고 `/var/log/clovirassist/install-<ts>.log` + `install_state.json` 에 남긴다.
**어느 단계에서 왜 멈췄는지가 표준 출력만 보고 판별돼야 한다.**

**`SKIP` 이 있는 이유(S4)**: 아직 제품에 없는 Component 의 Stage 를 `OK` 로 찍으면 「설치했다」는
거짓말이 로그에 남는다. 그 Session 이 Component 를 넣을 때 `SKIP` 이 `OK` 로 바뀐다 —
§8 Acceptance 가 **전 Stage `OK`** 를 요구하므로 남아 있으면 그때 걸린다.
**Stage 11 은 S8 이, Stage 12 는 S9 이 채웠다.** 이제 `SKIP` 을 찍는 Stage 는 **하나도 없다**.

**Idempotent 재실행**: 모든 Stage 가 "이미 되어 있음" 을 감지하고 건너뛴다. 재실행이 데이터·설정을
파괴하지 않는다. 실패 후 재실행은 실패 지점부터 의미 있게 이어진다.

> **옛 installer 의 알려진 실패 모드 — 새 설계에서 해소됐다(S4).** 옛 스크립트는
> `rsync --delete` 로 `/opt` 를 갈아엎고 venv 를 다시 만든 **뒤에** 테넌트 값 가드가
> `exit 21` 을 하여 **"새 코드 + 옛 스키마"** 를 남겼다
> (옛 스크립트는 S14 가 지웠다 — §9).
> `deploy/install.sh` 는 그 검사를 전부 Stage 0 으로 끌어올렸고, `tests/unit/test_deploy_wiring.py`
> 가 「가드가 Preflight 안에 있다」를 계약으로 지킨다.

### 5.1 회차 팀 이관 `0029_sprint_team_owner` — preflight 중단과 되돌리기 (D-482)

Stage 9 가 `0029` 를 지날 때 **데이터가 스스로 정하지 못하는 것은 사람에게 돌려보낸다.**

- **중단하는 조건 셋**: 팀 축으로 옮겼을 때 같은 팀에 `active` 회차가 둘 · 같은 팀에 같은
  이름이 둘 · 팀의 조직과 회차의 조직이 다름. `alembic upgrade` 가 `RuntimeError("0029 중단 — …")`
  로 멈추고 충돌 행(id·이름·상태·팀)을 나열한다. 트랜잭션이 되돌아가므로 **아무것도 바뀌지
  않는다.** 자동으로 닫거나 합치거나 이름을 바꾸지 않는다 — 나열된 회차를 옛 앱에서 닫거나
  이름을 고친 뒤 `deploy-upgrade.sh` 를 다시 돌린다.
- **채우지 못한 회차**는 팀 미정(`department_id NULL`)으로 남고 `RAISE NOTICE '0029 sprints:
  assigned[…] unassigned=N mixed_team=M'` 이 개수를 말한다. 배포 뒤 조직 정합성 화면의 「회차」 탭이
  그 목록이다(`sprints_without_team`, 열린 회차만) — 관리자가 그 탭에서 팀을 지정한다. 닫힌 회차는
  기록이라 그대로 두고 참고 건수로만 보인다. 열린 회차의 팀 어긋난 티켓은 「티켓」 탭의
  `open_sprint_tickets_off_team` 이 세고, 같은 자리에서 회차에서 뺄 수 있다.
- **되돌리기**: `alembic downgrade 0028_document_legacy_author`. `project_id` 칼럼·FK·인덱스는
  0029 가 지우지 않고 값도 그대로라, 옛 인덱스 둘을 복원하고 `department_id` 를 지우면 이전
  앱이 그대로 돈다. `project_id` 는 다음 릴리스의 `0031` 이 걷는다(BACKLOG P-94) — 그 전까지는
  롤백이 데이터 손실 없이 된다.

**설치 Version 확인**: `deploy/install.sh version` → VERSION · git ref/commit · alembic head ·
PG 버전 · extension 버전 · 각 서비스 상태.

---

## 6. 서비스 의존 순서와 자동 시작 (U14)

```
network-online.target
   ├─ clovirassist-privhelper.service            Before=clovirassist-web (root, 시스템 설정)
   └─ postgresql.service
        ├─ clovirassist-web.service              After=postgresql  Wants=network-online
        ├─ clovirassist-worker.service           After=postgresql   (배치 레인)
        ├─ clovirassist-worker-conversational…   After=postgresql   (D-118, 기본 대기)
        ├─ clovirassist-scheduler.service        After=postgresql   (D-225)
        └─ clovirassist-index.service            After=postgresql   (S9 ✅ · D-257)
   (Storage 사용 시) RequiresMountsFor=<마운트포인트>  ← Stage 11 이 유닛 넷에 drop-in 으로 얹는다 (S8 ✅)
```

**「떠 있어야 하는 유닛」과 「설치되는 유닛」은 다르다.** 대화형 레인은
`worker_conversational_lane_enabled` 가 꺼져 있으면 리스를 잡기 전에 `exit(0)` 해
`inactive (dead)` 로 쉰다 — 그것이 그 유닛의 정상 대기 상태다(D-118). 그래서 재부팅 복구
판정 대상은 `app/core/product.py::ALWAYS_ACTIVE_UNITS`(privhelper · worker · scheduler · web)이고,
그 목록과 설치 목록의 관계는 `tests/unit/test_product_identity.py` 가 지킨다.

- 전 유닛 `systemctl enable` — **재부팅 후 수동 명령 없이 복구된다**
- `Restart=on-failure` + `RestartSec` + `StartLimit*`
- 기동 시 **PG 준비 대기**(재시도) — `After=` 만으로는 PG 가 접속 가능하다는 보장이 없다.
  `deploy/wait-for-postgres.sh` 를 네 유닛이 `ExecStartPre=-` 로 부른다. 실패해도 기동을
  막지 않는다 — 이 대기의 일은 흔한 몇 초를 없애는 것이지 PG 장애를 판정하는 것이 아니다
- **Storage 마운트 전 기동 문제**: `RequiresMountsFor=` + 매 쓰기마다 `st_dev` 검사.
  마운트 안 됐으면 **쓰기를 거부**한다 — 로컬 디스크에 조용히 쌓이는 사고 방지.
  **둘 다 필요하다**: 순서는 「실패 자체가 없다」이고 가드는 「사용자가 실패를 본다」이다.
  drop-in 은 웹만이 아니라 **유닛 넷 전부**에 얹는다 — 워커가 먼저 뜨면 같은 사고가 난다.
  `/readyz` 도 저장소를 본다: 켜진 운영 저장소에 못 쓰면 `storage_not_writable` 로 503 이다
- **마운트 옵션의 기본값은 제품이 정한다**(D-251). NFS `soft,timeo=50,retrans=2` ·
  SMB `uid`·`gid`·`file_mode=0640`·`dir_mode=0750`. 운영자가 적은 값은 덮지 않는다.
  S8 실검증이 찾은 결함 둘이 전부 이 한 줄이었다 — 둘 다 마운트는 멀쩡했다

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
| **LXD/Incus Ubuntu 24.04 시스템 컨테이너** (테스트 서버 위) | **반복 가능한 Clean 설치 리허설.** 폐기·재생성이 싸서 idempotency · 실패지점 표시 · upgrade/rollback/uninstall 을 몇 번이고 돌린다 | 커널을 공유한다. **비특권 컨테이너에서는 NFS/CIFS 마운트가 제한된다** → Storage 검증은 여기서 하지 않는다(S8 은 **호스트에서** 돌렸다). **진짜 reboot 도 아니다** |
| **실 Ubuntu 24.04 VM** 또는 **테스트 서버 자체** | **최종 Acceptance**: Storage(NFS/SMB) · 실제 Reboot · TLS · 성능 | 테스트 서버를 쓰는 경우 재부팅 창이 필요하다 |

**컨테이너 통과를 "설치 검증 완료" 라고 쓰지 않는다** (R15).

**Release 경로 리허설(D-524)**: `scripts/release_rehearsal.sh <assets-dir> <tag-a> <tag-b>` 가 같은 LXD 에서 Release 경로를
처음부터 끝까지 돈다(미러, 첫 관리자, 메일 연결 확인, 프록시 뒤 AI 연결 확인, 다시 돌리기, 바뀐 묶음 거절, 업그레이드, 되돌리기,
제거 - 39항목). 2026-09-30 에 네 번째 실행이 전부 통과했다(`v0.1.0-rc.5` → `v0.1.0-rc.6`). 앞의 세 실행이 되돌리기와 AI 연결
확인의 결함을 찾았고 코드가 고쳐졌다. 같은 날 개발자 경로(`scripts/lxd_rehearsal.sh`, 저장소 소스로 설치, 실패 주입,
되돌리기, 업그레이드, 재시작 복구, 제거와 재설치, 옛 이름 이전, 완전 삭제 - 35항목)도 `a4bcad38` 로 전부 통과했다.
GitHub 의 실제 내려받기와 실제 AI 자격은 여기서 재지 않는다(BACKLOG P-116).

**S4 실행 기록**: LXD 컨테이너 리허설은 `scripts/lxd_rehearsal.sh` 가, 실 재부팅 복구는
`scripts/reboot_check.sh` 가 한다. 원장은 [`EVIDENCE/S4/`](EVIDENCE/S4/) 다.
**이 서버에는 `/dev/kvm` 이 없어**(VMware 게스트, 중첩 가상화 미노출) LXD **VM** 은 못 쓴다 —
그래서 «실 VM» 자리는 **테스트 서버 자체의 커널 재부팅**으로 채웠다. Storage(NFS/SMB)는
여전히 이 방법으로 검증되지 않는다(S8 의 몫).

### 7.1 Reboot Test — 제품 전체 (U14)

Storage 만이 아니라 전 서비스를 대상으로 한다.

`reboot` → 로그인 없이 대기 → `systemctl is-active` 전 유닛 · `postgresql` · `nginx` →
`/healthz` `/readyz` → 로그인 → 대표 데이터 조회 → Storage 쓰기/읽기 →
Worker/Scheduler 틱 진행 확인 → **실패 유닛 0**.

**실행 시점 (E4)**: **S4** 에서는 그 시점에 존재하는 Component 범위(PG · web · worker · scheduler ·
nginx)로 1회. **S22** 에서 Storage · AI · index lane 까지 포함한 **전 Component** 로 §8 의 일부로
수행한다. 그 사이 Session 들은 §6.1 에 따라 **자기가 추가한 Component 의 기동·복구만** 확인하고
전 제품 Reboot 을 반복하지 않는다.

**S4 에서 1회 수행함 (2026-08-22)**: 테스트 서버를 실제로 재부팅했고(`boot_id` 가 바뀐 것으로
확인) 사람이 아무 명령도 치지 않은 채 컨테이너 → PG · nginx · privhelper · worker · scheduler ·
web 이 전부 돌아왔다. `/healthz` · `/readyz` 200, 표 71개 그대로, `install.sh verify` 통과.
(**표 수는 스키마와 함께 움직인다** — S5 가 권한 표 다섯을 더해 지금은 더 많다. 리허설은
절대 수가 아니라 **재설치 전후가 같은지**를 본다.)
원장 [`EVIDENCE/S4/reboot_recovery.txt`](EVIDENCE/S4/reboot_recovery.txt).
「로그인 → 대표 데이터 조회」와 「Storage 쓰기/읽기」는 **아직 안 했다** — 관리자 계정 생성과
Storage Provider 가 이 시점 제품에 없다. S22 가 전 Component 로 다시 한다.

---

## 8. 최종 Acceptance 시나리오 (S22 에서 실행)

**Clean Ubuntu Server 24.04 에서 §1 의 설치 명령으로 시작한다. 다른 문서를 참조하지 않는다.**

| # | 단계 | 확인 |
|---|---|---|
| 1 | 전체 자동 설치 | Stage 0~18 전부 `OK`. **수동 mkdir/cp 0회** |
| 2 | DB 준비 / Migration | `install.sh version` 의 alembic head == 코드 head |
| 3 | 서비스 자동 등록 | `systemctl is-enabled` 전 유닛 `enabled` |
| 4 | Health PASS | `/healthz` `/readyz` 200 + DB·Storage·AI probe |
| 5 | Login / Smoke PASS | 설치 콘솔의 설정 코드로 첫 관리자 만들기(§11) → 로그인 → 사용자 콘솔 → 관리자 콘솔 → 대표 데이터 |
| 6 | **Server Reboot** | `sudo reboot` |
| 7 | 전체 서비스 자동 복구 | **수동 명령 0회.** `systemctl is-active` 전 유닛 + `postgresql` + `nginx` |
| 8 | Health PASS | 동일 |
| 9 | 기존 데이터 정상 | 재부팅 전 데이터가 그대로 조회됨 |
| 10 | Upgrade 검증 | `clovirassist upgrade --release v<VERSION+1>`(git 설치는 `--ref`) → Health PASS. 실패 주입 시 `rollback` 으로 원복 |

**부가 검증**

1. 설치 명령 **재실행(idempotent)** — 데이터·설정 무손상
2. `uninstall` 후 **재설치**
3. 의도적 Stage 실패 주입 시 **어느 Stage 에서 왜 멈췄는지 표준 출력만으로 판별되는지**
4. 오프라인 Bundle 경로로도 동일 시나리오 1회

---

## 9. 현재 자산 실측 — 있는 것과 없는 것 (2026-08-20 · **S2 반영 2026-08-21** · **S4 반영 2026-08-22** · **S14 반영 2026-08-24**)

| 있던 것 | S14 가 한 일 |
|---|---|
| `scripts/install-clovirone-web-assistant.sh` (12 stage) · `upgrade-*.sh` · `rollback-*.sh` · `backup-*.sh` · `backup-cron.sh` · `install-backup-cron.sh` · `update-from-git.sh` · `validate-*.sh` · `apply-app-update.sh` | **지웠다.** 아홉 전부 옛 slug 설치를 위한 것이고 `deploy/install.sh` 하나가 그 일을 한다(S4). 옛 slug 설치는 Cutover 가 이전을 끝냈으므로 이 스크립트들이 섬길 설치가 남아 있지 않다. `validate-*.sh` 는 S11 뒤로 **깨져 있었다**(«n8n 이 살아 있다» 를 성공 조건으로 단언) |
| `deploy/systemd/clovirone-*.service` 4종 · `deploy/nginx/clovirone-web-assistant.conf` · `logrotate-clovirone-web-assistant` | **지웠다.** 설치기는 옛 유닛을 **이름으로만** 안다(`LEGACY_UNITS`) — 이전할 때 찾아 멈추고 스냅샷에 담기 위해서다. 저장소 안의 파일 사본은 아무도 안 읽는다 |
| `scripts/build-bundle.sh` | **남긴다.** `MANIFEST.sha256` 을 만드는 **유일한** 자리이고 `install.sh --source bundle` 이 그것을 읽는다. 산출물 이름만 새 slug 로 갈았다(`clovirassist-bundle.tar.gz`) |
| `scripts/lxd_rehearsal.sh` | **남긴다.** 옛 slug 설치를 **일부러 만들어** 이전을 리허설한다 — 옛 이름이 여기 있는 것이 그 시험의 내용이다 |

🔴 **지우면서 갭 하나를 찾았다.** 옛 `backup-*.sh` 는 사용자가 올린 파일
(`/var/lib/<slug>`)을 담았는데 `deploy/install.sh::take_snapshot` 은 안 담았다 — DB 덤프만
있고 첨부 파일이 없는 스냅샷이라, 되돌리면 「행은 있는데 파일이 없는」 상태가 된다. 옛
스크립트의 시험이 계속 초록이라 두 벌을 유지하는 동안 아무도 못 봤다. 설치기에 넣었고
(`data.tar.gz`, 모델 파일은 제외) rollback 이 소유권까지 다시 잡는다.

| **S4 가 만든 것** | 상태 |
|---|---|
| `deploy/install.sh` | 단일 진입점 7개 서브커맨드 · Stage 0~18 · 옛 slug 이전 · 스냅샷/rollback |
| `deploy/systemd/clovirassist-*.service` 5종 · `deploy/wait-for-postgres.sh` | 기동 시 PG 준비 대기 포함 |
| `deploy/nginx/clovirassist.conf` · `logrotate-clovirassist` · `deploy/clovirassist.env.example` | 새 slug |
| `scripts/lxd_rehearsal.sh` · `scripts/reboot_check.sh` | 리허설 34항 · 실 재부팅 복구 |
| PostgreSQL 서버 설치/초기화(Stage 6) · Extension(Stage 7) | 실제로 돈다 — `max_connections` 사이징 포함 |
| Scheduler 별도 유닛 | `--lane=scheduler` (D-225) |

| 아직 없는 것 | 소유 |
|---|---|
| Storage 준비 실체(NFS/SMB Provider · 마운트 유닛 · `st_dev` 가드) — Stage 11 은 `SKIP` 이다 | S8 (P-17) |
| ~~AI Component(모델 배치 · ONNX Runtime)~~ | ~~S9 (P-18)~~ — **완료 (2026-08-23)**. 실검증 원장은 [`EVIDENCE/S9/`](EVIDENCE/S9/README.md) |
| ~~`clovirassist-index.service`~~ | ~~S9 (P-18)~~ — **완료 (2026-08-23)** |
| **전 Component** Reboot 검증(Storage·AI 포함) | S22 |

### 9.1 nginx 하드 블로커

`nginx client_max_body_size` 는 기본 **256k** 이고, 대화 메시지(8m)·게시판 첨부(12m) location 만
올려 놨다. **파일 업로드 제품화의 하드 블로커다** — S8 에서 Storage 와 함께 푼다.

---

## 10. 제품 slug 이전 (R13) — **끝났다**

현재 slug 는 `clovirassist` 다. 경로·유닛·백업 루트·서비스 계정이 전부 그 이름이고,
운영 설치는 Cutover 로 그리로 넘어갔다.

- **경로**: `/opt/clovirassist` · `/etc/clovirassist` · `/var/lib/clovirassist` ·
  `/var/backups/clovirassist`
- **유닛**: `clovirassist-{web,worker,worker-conversational,scheduler,index,privhelper}.service`
  (`deploy/install.sh` 의 `ALL_UNITS` 가 정본이다)
- **사용자 노출 면**은 전부 `ClovirAssist` 다 (S3)

옛 slug `clovirone-web-assistant` 를 **아는 자리는 둘뿐**이고, 둘 다 「이전 대상을 찾기
위해서」다: `deploy/install.sh` 의 `LEGACY_SLUG`·`LEGACY_SVC_USER`·`LEGACY_UNITS`(옛 설치를
찾아 멈추고 스냅샷에 담아 이전한다)와 `deploy/00-precheck.sh` 의 재실행 감지다.
그 밖의 곳에 옛 이름을 다시 적지 않는다 — 그러면 걷어낸 정체성이 제품에 되살아난다
(CLAUDE.md §0).

---

## 11. 첫 관리자 계정 (D-522)

설치는 계정을 만들지 않는다. 만들면 누군가 비밀번호를 정해야 하고, 그 값이 콘솔이나 설치 로그에 남는다. 대신 사용자가
0명이면 Stage 10 이 **일회용 설정 코드**를 만들고, 모든 Stage 가 끝난 뒤 콘솔에 한 번 보인다.

```
=== 첫 관리자 계정 ===
아직 계정이 없습니다. 브라우저에서 https://<host>/setup/first-admin 을 열고 아래 설정 코드를 넣어
시스템 관리자 계정을 만드세요. 코드는 한 번만 쓸 수 있고 설치 로그에는 남지 않습니다.

  설정 코드: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX
```

- 코드는 128비트 무작위 값이다. 서버에는 sha256 해시, 만료 시각(24시간), 실패 횟수만 `/var/lib/clovirassist/first-admin.json`
  에 남는다.
- `/setup/first-admin` 은 스크립트 없는 서버 렌더 폼이다. 코드, 이메일, 이름, 비밀번호를 받아 시스템 관리자를 만들고
  코드를 지운다. **사용자가 한 명이라도 있으면 이 경로는 404 다.**
- 틀린 코드가 다섯 번 들어오면 코드를 폐기한다. 비밀번호 정책에 걸린 것은 실패로 세지 않는다.
- 코드를 잃어버렸거나 만료됐으면 `sudo clovirassist first-admin-code` 로 새로 만든다(옛 코드는 무효가 된다).

## 12. 설치 뒤 설정

필수 설정(관리자 계정, 조직과 부서, TLS)은 설치와 §11 이 끝낸다. 관리자로 로그인하면 **설정 > 초기 설정** 화면이 남은
항목을 보인다. 메일과 AI 는 **선택**이다. 쓰지 않으면 그 화면에서 「사용하지 않음」으로 표시한다(D-520).

- **비밀 값은 설치 명령에 넣지 않는다.** 메일 비밀번호와 AI 키는 웹 화면에서 넣고, 특권 도우미가
  `/etc/clovirassist/secrets/` 에 쓴다(값을 돌려주는 API 는 없다, D-503).
- **메일**: 시스템 관리자가 운영 > 메일의 설정 탭을 **위에서 아래로** 따라간다(D-560). 화면 머리의 진행 띠가 일곱 단계(① 메일 발송 켜기
  ② 보내는 방법 고르기 ③ 보내는 사람과 방식별 정보 입력 ④ 저장과 적용 ⑤ 연결 확인 ⑥ 시험 메일 ⑦ 받은 편지함 확인)의 상태와 「다음 할 일」
  한 문장을 보이고, [이동]이 그 자리로 간다. 보내는 방법은 둘이다 — 「ClovirAssist 로컬 릴레이」(기본, 이 서버에 함께 깔린 발송 전용 구성 요소,
  계정이 필요 없다)와 「외부 SMTP 사용」(회사 계정이나 Gmail 같은 외부 계정 — Gmail · Microsoft 365 · Naver 프리셋이 서버 값을 채우고 계정과
  비밀번호만 넣는다). 로컬 릴레이 안에서는 「상위 SMTP 이용」(다른 SMTP 서버를 거친다) 또는 「인터넷으로 직접 전달」(받는 쪽 메일 서버로 바로
  보낸다)을 고른다. 직접 전달은 **도메인 DNS 담당자와 회선 · 클라우드 업체의 일**이 함께 필요하다 — 공개 서버 이름 · PTR · SPF 에 이 서버의
  IP 합치기 · DKIM 공개키. 화면의 「담당자에게 요청하기」 상자가 준비 점검 결과에서 담당자별 요청문(레코드 값 그대로)을 만들어 주고, 요청이
  끝나면 [점검 다시 하기]가 통과를 보인다. 기술 진단(DNS 레코드 · 점검 표)은 「진단 펼치기」 안에 있다. 로컬 릴레이의 받는 문은 이 서버 안의
  127.0.0.1:2525 하나이고 앱만 가진 클라이언트 인증서가 있어야 중계한다 — 바깥에서 붙을 수 없고, 다른 로컬 프로세스와 `sendmail`
  명령으로는 보낼 수 없다(D-551). 저장하면 연결 확인이 저절로 돌고, 시험 메일의 결과는 「메일 서버가 접수함」과 「받은 편지함 도착」을 섞지
  않는다(D-555) — 받았는지는 시험 메일 창의 [받았습니다]로 사람이 기록한다(⑦). 메일 서버 설정은 시스템 관리자만 바꿀 수 있고, 비밀번호는
  언제나 고정 칸 하나에서 읽는다(D-545). 예전 설치가 비밀번호 파일 이름을 따로 적어 두었으면 업그레이드가 `smtp` 로 시작하는 이름의 파일만
  그 칸으로 옮긴다 — 그 밖의 이름을 쓰던 설치는 업그레이드 뒤 메일 비밀번호를 다시 넣는다. 메일 틀은 제품 머리(로고 표식 + 워드마크) 하나이고
  로고는 메일에 붙어 가는 PNG 한 장이라 바깥 그림 주소가 없다(D-561). 알림 메일은 사용자가 내 프로필에서 켠 유형만 가고 관리자 허용
  목록 안에서 고른다(D-562, 계정 잠금 · 비밀번호 변경 요구는 선택과 무관한 보안 메일).
- **AI**: AI > AI 연결 화면에서 제공자와 인증 방식을 고른다(D-539). 인증 방식은 둘이다(D-566) — **API 키**(Anthropic 콘솔 또는 OpenAI
  플랫폼에서 발급한 키, 조직 키 권장, 쓴 만큼 그 키의 계정에 과금)를 넣고 「저장하고 확인」을 누르거나, OpenAI 는 **ChatGPT 계정**(Sign in with
  ChatGPT, Plus · Pro 요금제)으로 로그인한다. 상태 면은 서버가 준 사실만 보이고 「다음 할 일」 한 문장이 다음 단계를 가리킨다(D-558).
  ChatGPT 계정 로그인은 새 창에서 승인한 뒤 「127.0.0.1 … 연결할 수 없습니다」 오류 화면의 주소를 화면에 붙여 넣는 순간 연결된다(D-540,
  설치할 프로그램이 없다). 연결한 계정 하나의 요금제를 그 설치의 모든 사용자와 배치 기능이 함께 쓴다. 한계는 사용자가 안고 간다 — OpenAI 가
  여러 사람이 접속하는 호스팅 서비스에서의 요금제 공유를 공식 허용하는지는 확인되지 않았고, OpenAI 가 거절하면(`subscription_sharing_*`) 그
  문장이 화면에 그대로 보인다. 여러 사람이 쓰는 설치에는 조직 API 키를 권한다.
- **바깥 프록시**: AI 제공자 호출이 사내 프록시를 거쳐야 하면 설정 > 설정의 OS와 서비스 동작 탭에서 프록시 주소와 예외
  목록을 넣고 서비스를 다시 시작한다. 그 값은 웹, 배치 워커, 대화형 워커, 스케줄러 유닛의 드롭인이 되고 앱의 바깥 호출
  문(`OutboundClient`)이 명시적으로 읽는다(D-516). 허용 목록은 그대로 목적지에 걸린다. 인증이 필요한 프록시는 아직 지원하지
  않는다(BACKLOG P-112).
- **TLS**: 설치가 `--dns-name` 으로 자체 서명 인증서를 만든다. 브라우저 경고를 없애려면 설정 > 설정의 OS와 서비스 동작
  탭에서 신뢰된 인증서와 개인키로 바꾼다(키와 인증서가 한 쌍인지 확인한 뒤에만 바꾼다).
- **서비스 주소(대표 이름 바꾸기, D-573)**: 설정 > 설정의 OS와 서비스 동작 탭 맨 위 「서비스 주소」가 대표 주소 · 지금 접속한 주소 ·
  함께 쓰는 주소(별칭) · 인증서 · 확인 넷(DNS · HTTPS · 웹 서버 · 서비스 설정)을 보인다. DNS 는 **이 서버가 쓰는 해석기 기준**이고, 메일
  설정의 「비교할 공개 DNS」를 넣었으면 공개 답을 따로 정보로 보인다(공개 DNS 를 완료로 표시하지 않는다). 「주소 바꾸기」는 새 주소 ·
  함께 쓸 주소(기본으로 지금 대표 주소가 들어간다) · 인증서 방식(자체 서명 새로 만들기 · 지금 인증서 유지 · PEM 붙여 넣기)을 받아 미리
  확인한 뒤 특권 도우미의 `domain.apply` 로 적용한다. 순서는 인증서 → nginx vhost → `nginx -t` → nginx reload → env(`APP_BASE_URL` ·
  `TLS_CERT_PATH`) · 매니페스트(`dns_name` · `alias_names`) → 자체 확인(이 서버 443 에 새 이름으로 TLS 를 맺어 `/healthz` · `/login`) →
  배치 · 대화형 · 예약 · 색인 유닛 재시작 → (고르면) 3초 뒤 웹 서버 재시작(`systemd-run`, 약 3초 동안 접속이 끊긴다)이다. 자체 확인까지
  어느 단계가 실패하면 파일을 되돌리고 nginx 를 옛 설정으로 다시 읽힌다. 새 주소로는 한 번 다시 로그인한다(로그인은 주소마다 따로 유지된다).
  사내 DNS · 공개 DNS 와 외부 인증서는 바뀌지 않는다 — 담당자의 일이다. 적용 기록은 감사(`system_action/domain.apply`)에 남고 인자는 남지
  않는다. 같은 값은 설치 명령으로도 줄 수 있다(`--dns-name` · `--alias-name`, §1).
