# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-21** (S3)
- phase: **A — 기반**
- session: **S3 완료.** 다음은 **S4 — 설치 · 배포 자동화 Foundation**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고, `check_test_strength.py` 가 이 값을 읽는다.
  **S3 은 이 값을 옮기지 않는다.** S2 가 「S3 부터의 시험 약화가 보이게」 하려고 여기에
  올려 둔 것이고, S3 의 시험 변경 4파일은 전부 **강화 방향**(단언 추가)이라 그 기준선 대비
  그대로 통과한다. 옮기는 것은 시험 지형을 크게 바꾼 세션의 일이다
- s1_commit: `95a89189` · s2_commit: `eec4886c`
- working_tree: clean
- **제품 코드 diff 0.** S3 이 고친 것은 QA 하네스 정책 · 설치 검증 스크립트 · 검사기 ·
  시험 넷이고, 나머지는 **서버 설정**이다(저장소가 아니라 `/etc` 에 있다)

## S3 이 실제로 한 것

호스트명 축이다. 이제 제품은 **한 이름으로만 응답하고, 그 이름이 인증서와 맞는다.**

| | |
|---|---|
| **인증서** | CN/SAN 이 `clovirone-ai.gooddi.lab` → **`clovirassist.gooddi.lab`**(+ IP SAN). 설치 스크립트 §10 과 **같은 openssl 호출**로 만들어 설치처와 저장소가 어긋나지 않게 했다 |
| **nginx** | `server_name` 과 `ssl_certificate` 넷. 손으로 고치지 않고 **저장소 템플릿을 렌더**했다(배포본 템플릿이 작업 트리와 바이트까지 같음을 먼저 확인) — diff 가 정확히 그 넷이다 |
| **`APP_BASE_URL`** | `https://clovirone-ai.gooddi.lab` → canonical. **이미 죽어 있던 값이다** — 아래 발견 참조 |
| **`TLS_CERT_PATH`** | 새 인증서로. 진단 화면의 만료일·자체서명 판정과 `cert.install` 이 이 값을 읽는다 |
| **cookie domain** | **안 붙인다**(D-224). `Domain=.gooddi.lab` 은 공유 n8n 을 포함한 도메인 전체로 세션 쿠키를 뿌린다. 계약을 시험이 지킨다 |
| **QA base URL** | 이미 S1 이 `capture.DEFAULT_BASE_URL` 한 곳으로 모아 놨다. 확인만 했다 |
| **프로브 TLS 검증** | `tls.py` 의 `DEFAULT_VERIFY = True`. 자체서명이라 그것만으로는 안 켜진다 — 아래 발견 |
| **옛 호스트 하드코딩 시험 2건** | `test_sysops_tls_paths.py` · `test_health_worker_hardening.py` |

## S3 이 드러낸 것 — 계획에 없던 발견 넷

**1. 옛 이름은 이미 DNS 에서 사라져 있었다.** 권위 서버가 NXDOMAIN 을 준다. W13 런북의
「이중 이름 인증서 → 두 이름 서브 → 나중에 퇴역」 호환 창은 전제가 깨진 상태였다. 아무도 못
푸는 이름을 위해 인증서와 vhost 에 옛 정체성을 남기지 않는다 (**D-222**). 롤백 근거는
「옛 이름이 계속 동작한다」에서 「바꾸기 전 파일이 그대로 있다」로 바뀌었다.

**2. `APP_BASE_URL` 이 죽은 이름을 가리키고 있었다.** 그 값으로 만드는 절대 URL —
알림 메일 링크·Notion 역링크·공유 주소 — 이 **이미 전부 깨져 있었다.** 아무 오류도 안 난다.
사용자가 링크를 눌러야만 드러나는 종류다. S3 이 호스트명 축을 열지 않았으면 계속 그대로였다.

**3. 재발급만으로는 TLS 검증이 안 켜진다** (**D-223**). S1 이 남긴 예측은 「인증서를 고치면
스위치 하나로 19개가 켜진다」였는데, 이 설치처의 인증서는 **자체서명**이라 이름을 맞춰도
믿을 근거가 클라이언트에 없다. 검증은 「이름이 맞다」와 「신뢰 기준점을 쥔다」가 함께 있어야
성립한다. 그래서 `tls.py` 에 `UI_QA_TLS_CA` 를 두었고, 오타 난 경로를 조용히 무시하지 않는다.
**브라우저 레그는 이 값을 못 받는다** — Playwright 에 신뢰 기준점 인자가 없어 Chromium 은
운영체제 저장소를 본다. 그것이 아래 P-10a 다.

**4. 설치 검증 스크립트가 검증하고 있지 않았다.** `validate-*.sh` 가 healthz/readyz 를
`curl -k` 로 쳤다 — 이름이 어긋난 채로도 계속 `[OK]` 다. 게다가 **이름만으로 자기 서버를
불렀는데**, 이 서버의 `/etc/hosts` 는 그 이름을 `127.0.1.1` 로 푼다(호스트명이 `clovirassist`
로 바뀌며 생긴 줄). nginx 는 `10.100.64.71:443` 한 곳에만 묶여 있어 그 호출은 `code=000` 이다.
`--resolve` + `--cacert` 로 고치고 CN/SAN 대조·80→443 이름 보존·`server_name` 중복 검사를
더했다. **반례로 확인했다** — 틀린 이름을 주면 여섯 항목이 실제로 빨간불이다.

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 프로브 8건 · PG 스택 실측(D-209~D-212) ·
  `VARCHAR(n)` 감사(D-214). **제품 코드 diff 0.**
- **S2 — PostgreSQL Foundation.** 70 표 · 256 인덱스가 `0001_pg_baseline` 하나로 선다.
  SQLite Runtime 의존 0 · `--workers 1→4`. 상세 [`INVENTORY/08_SQLITE.md`](INVENTORY/08_SQLITE.md),
  결정 **D-215~D-221**.
- **S3 — Product Identity · Hostname · TLS.** 위 절. 결정 **D-222~D-224**.

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다** (S2 가 남긴 구분, 그대로 유효)

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001_pg_baseline` 하나가 70 표 · **256 인덱스** · 부트스트랩 5행을 만든다 |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** 그래서 S3 의 서버 작업은 nginx·TLS·env 였고 DB 를 건드릴 일이 없었다 |

이관은 S13(Dry Run) → S14(Cutover)의 일이고, 그 사이 Session(S4~S12)은 새 스키마 위에서
개발한다. `alembic/legacy_sqlite/` 61개를 지우지 않은 이유가 이것이다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **이식 완료.** 앱·마이그레이션·시험이 전부 PG16 위에서 돈다. **서버 시스템 설치는 아직 0** — S4 Installer Stage 6·7 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ → S4(설치) |
| **SQLite 제거** | **Runtime 의존 0.** 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ → S13·S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `ticket_cache` 1,124 · `document_cache` 110 | Notion Runtime 의존 0, 데이터는 PG 로 | S13 → S14 |
| **AI** | **권한 필터 없음.** n8n → `claude-work-assistant`(8789) 가 Notion 전량을 모델에 싣는다 | Model Gateway + 권한이 앞서는 Hybrid Retrieval | S9 · S10 · S11 |
| **Backup** | **기본형 완료.** `pg_dump -Fc` + 체크섬 + `pg_restore --list` + 임시 DB 실복원 | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ → S12 |

**Identity 축은 둘로 갈렸다**: 호스트명·TLS 는 S3 이 닫았고, **slug**
(`clovirone-web-assistant` 경로·유닛·시스템 사용자)는 **S4 Installer** 가 새 slug 로 설치하며
정리한다 (MASTER_PLAN R13).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S3 의 변경 범위는 좁다(하네스 정책 · 검증 스크립트 · 검사기 · 시험 4파일). 전 회귀는 돌리지
않았다 — E1 대로 **S2 의 `FULL_REGRESSION_OK`(3,229건, 소스 지문 `d8fadd78`)를 인용**하고,
바뀐 자리만 새로 확인했다.

| 대상 | 결과 |
|---|---|
| 서버 TLS — `openssl s_client` CN/SAN | **일치** (`clovirassist.gooddi.lab` + IP SAN). 원장 [`EVIDENCE/S3/hostname_tls_cutover.txt`](EVIDENCE/S3/hostname_tls_cutover.txt) |
| 서버 TLS — `curl --cacert … %{ssl_verify_result}` | **0** (`/healthz`·`/readyz`·`/login`). **반례 둘도 함께**: 기준점 없이 **18**, 이름이 다르면 **1** — 초록이 무엇을 뜻하는지 정하는 것은 이쪽이다 |
| 80 → 443 이 이름을 보존하는가 | `Location: https://clovirassist.gooddi.lab/` |
| `scripts/validate-clovirone-web-assistant.sh` (고친 것) | **VALIDATE_OK** 14항. **틀린 이름을 주면 6항이 빨간불**(반례) |
| 로그인·테마 유지 E2E (제품 경로) | **LOGIN_THEME_E2E_OK** 4항. 원장 [`EVIDENCE/S3/login_theme_e2e.txt`](EVIDENCE/S3/login_theme_e2e.txt) |
| `scripts.ui_qa.run --routes smoke --fail-on auth_ok theme_applied console_errors page_errors` | **치명 검사 실패 없음 · 억제 0건** (서버 번들 지문 `fb19ecbe9fd8d36d`) |
| 하네스 파이썬 레그가 실제로 검증하는가 | 기준점을 주면 `_probe_server` **200**, 안 주면 `CERTIFICATE_VERIFY_FAILED` — **양방향 확인** |
| 바뀐 시험 5파일 (`pytest`) | **69건 통과** — `test_sysops_tls_paths` · `test_tenant_defaults` · `test_deploy_wiring` · `test_auth_login` · `test_health_worker_hardening` |
| `probe_selftest --logic-only` | **PROBE_SELFTEST_OK (16 사례)** — TLS 기준점 사례 5개를 새로 넣었고 양방향이다 |
| `scripts/static_checks.sh` | **S3 이 넣은 것은 전부 통과.** 전체는 **여전히 빨간불이고 원인은 S3 이 아니다** — 아래 절 |
| 제품 코드 · frontend · runner | **인용** — diff 0 (지문 `652f787e`) |

### ⚠️ `static_checks.sh` 전체는 아직 빨간불이다 — **S1 이후 UI 커밋 둘이 남긴 것이다**

S2 가 기록한 것과 같고 아무것도 바뀌지 않았다. `BACKLOG.md` **P-09a** 가 Owner(UI 축)를 갖는다.

| 무엇 | 어디서 왔나 |
|---|---|
| 사용자 문구의 가운뎃점(·) **7건** | `4dd62181` — `Integrity.jsx` · `AccentPicker.jsx` · `Sprint.jsx` · registry 4곳 |
| `tokens.css` 가 `theme.js` 와 어긋남 | `dac17928` 이 토큰 정본을 고치고 `generate_design_tokens.mjs` 를 안 돌렸다 |

**고칠 때까지 모든 Session 이 빨간 정적 검사를 본다** — 자기 회귀로 오해하지 않도록 남긴다.

## NOW

**S3 은 끝났다.** 제품이 한 이름으로만 응답하고 그 이름이 인증서와 맞는다.

이 세션에서 가장 값이 나간 것은 인증서 재발급이 아니라 **「검증한다고 적힌 것들이 실제로는
검증하고 있지 않았다」를 셋이나 찾은 것**이다: `curl -k` 로 치던 설치 검증, 이름만으로 자기
서버를 부르다 `code=000` 이 나던 호출, 그리고 죽은 이름을 들고 있던 `APP_BASE_URL`.
셋 다 오류를 안 낸다. 초록이거나, 아무 일도 안 일어난다.

그래서 이번에 넣은 것은 전부 **반례를 함께 가진다** — 틀린 이름을 주면 빨간불이 나는 것을
보고 나서야 초록을 믿는다.

## NEXT — 다음 시작점: S4 (요청 시)

**S4 = 설치 · 배포 자동화 Foundation.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, 계약은 [`INSTALLATION.md`](INSTALLATION.md) §6.

S3 이 S4 에게 넘기는 것:

1. **slug 축이 통째로 남아 있다** (R13). 경로 `/etc`·`/var/lib`·`/opt`, systemd 유닛 4종,
   시스템 사용자 `clovirone-web`, nginx conf 파일명. **호스트명·TLS 는 이미 정리됐으니**
   그 축과 엉킬 일은 없다
2. **인증서 발급 경로는 지금 것이 맞다.** `install-*.sh` §10 의 openssl 호출을 그대로 써서
   서버를 고쳤다 — Installer 를 다시 쓸 때 이 호출의 CN/SAN 모양을 유지하면 된다
3. **`validate-*.sh` 가 이제 `DNS_NAME` 과 `BIND_IP` 를 **둘 다** 요구한다.** Installer 가
   이미 둘 다 요구하므로 호출부만 맞추면 된다. `--resolve` 없이 이름만으로 자기 서버를 부르면
   `/etc/hosts` 때문에 `code=000` 이라는 것이 이번에 실측으로 확인됐다
4. **PG 시스템 설치는 아직 0이다.** 서버에 도는 것은 S2 이전 빌드이고 `postgresql` 유닛은
   `inactive` 다. Installer Stage 6·7 이 그것을 세운다
5. 옛 인증서·키 파일이 `/etc/clovirone-web-assistant/tls/` 에 아직 있다. **참조하는 설정은
   없다**(확인함). Installer 가 `/etc` 를 새 slug 로 다시 세울 때 함께 사라진다

## RISK — 지금 살아 있는 것

전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12. **S3 이 R13 의 절반을 닫았다.**

| # | Risk | 상태 / Owner |
|---|---|---|
| ~~R1~~ ~~R2~~ ~~R3~~ | (S2 가 닫음) | 해소 |
| ~~R4~~ ~~R5~~ ~~R6~~ ~~R7~~ | (S1 이 닫음) | 해소 |
| R13 | 제품 slug 가 경로·유닛·백업 루트에 박혀 있다 | **절반 해소** — 호스트명·TLS·`APP_BASE_URL` 은 S3 이 닫았다. 남은 slug 축은 **S4** |
| R14 · R15 · R16 | 설치 자동화 · LXD 리허설의 한계 · GitLab 주소 부재 | S4 |
| R17 | pgvector 검색 품질 | S10(하이브리드 가중치) |
| — | **AI 쿼터 잠금이 커넥션을 하나 더 쓴다** — 기본 풀 15 에서 동시 7~8을 넘으면 마른다(증상은 오류가 아니라 «느리다») | S4(풀·`max_connections` 사이징) |
| — | **운영 데이터가 아직 SQLite 에 있다** | S13 · S14 |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore). 값을 tracked 파일·커밋·로그에 복사하지 않는다 |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. **옛 이름 `clovirone-ai.gooddi.lab` 은 DNS 에 없다**(NXDOMAIN). 인증서는 자체서명이고 사본이 `/home/cloviradmin/clovirassist.gooddi.lab.crt` 와 `dist/ops/` 에 있다 |
| **하네스를 원격에 겨눌 때** | 검증을 켜려면 `UI_QA_TLS_CA` 로 그 인증서를 준다. **브라우저 레그는 실행 머신의 신뢰 저장소가 필요하다**(P-10a). 계정은 원격에서 만들 수 없다 — 서버에서 `user_cli` 로 열고 `UI_QA_EMAIL`/`UI_QA_PASSWORD` 로 넘긴다. QA 계정 `ui-qa@goodmit.co.kr` 은 지금 **보관 상태**다(S3 이 열었다가 되돌렸다) |
| **되돌릴 지점** | `/root/s3-hostname-backup-20260821-220722/` — vhost · tls 디렉터리 · web.env |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433). `CLOVIR_TEST_PG_URL` 로 덮어쓴다. **DB 를 만들고 지울 권한**이 필요하다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다**. `PG_BIN_DIR` 를 비워 두면 안 된다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 시험 Storage 로 실검증. 실 정보 수령 시 **Configuration 만** 변경 (U8·U9) |
| 20개 Project Key 명명 | **S6 에서** 초안표 제시 → 사용자 확인 → 적용. **확정 전 재채번 없음** (U11) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19) |
| GitLab Repository 주소·자격증명 | **없어도 S4 는 진행한다** (Remote 중립 + 오프라인 Bundle) (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
