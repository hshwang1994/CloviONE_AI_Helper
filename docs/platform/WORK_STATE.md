# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-22** (S4)
- phase: **A — 기반**
- session: **S4 완료.** 다음은 **S5 — Identity & Access**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S4 도 옮기지 않는다.** S4 의 시험 변경은 전부 강화 방향(계약 시험 신설 76건, 기존 시험은
  옛 정체성을 새 정체성으로 옮긴 것뿐)이라 그 기준선 대비 그대로 통과한다
- s1_commit: `95a89189` · s2_commit: `eec4886c` · s3_commit: `e88e4de3`
- working_tree: clean
- **이번엔 제품 코드도 바뀌었다.** 스케줄러 레인 분리(D-225)와 제품 정체성 정본(D-226)이
  런타임에 닿는다. 나머지는 배포 자산·리허설·문서다

## S4 가 실제로 한 것

설치 축이다. 이제 **Clean Ubuntu 24.04 에서 세 줄로 제품이 서고, 재부팅하면 스스로 돌아온다.**

| | |
|---|---|
| **진입점** | `deploy/install.sh` 하나. `install`·`upgrade`·`rollback`·`uninstall`·`verify`·`version`·`preflight` |
| **Stage 0~18** | 각 Stage 가 `STAGE_<n>_<NAME>: OK\|SKIP\|FAIL <사유> \| 조치: <조치>` 한 줄을 낸다. 로그 파일을 열지 않고도 어디서 왜 멈췄는지 판별된다 |
| **Preflight** | 옛 installer 는 `/opt` 를 갈아엎고 venv 를 다시 만든 **뒤에** 설정 가드가 죽어 「새 코드 + 옛 스키마」를 남겼다. 검사를 전부 Stage 0 으로 올려 그 상태를 구조적으로 없앴다 |
| **systemd 5유닛** | `clovirassist-{web,worker,worker-conversational,scheduler,privhelper}`. 전부 `enable` 하고, 넷이 `wait-for-postgres.sh` 로 **PG 가 접속을 받을 때까지** 기다린다 |
| **스케줄러 분리** | 배치 워커의 tick 이던 스케줄 평가를 별도 프로세스로 꺼냈다 (**D-225**). 3600초짜리 잡 하나가 스케줄 발화를 통째로 밀던 문제다. 되돌릴 스위치는 `worker_scheduler_lane_enabled` |
| **slug 축 (R13)** | 정본을 `app/core/product.py` 하나로 모았다 (**D-226**). 열두 곳에 흩어져 있던 경로·유닛 이름·소켓·드롭인·계정 이름이 그것을 읽는다. 셋(파이썬·셸·유닛 파일)이 갈라지지 않는 것은 시험이 지킨다 |
| **옛 설치 이전** | `install` 이 옛 slug 설치를 발견하면 스냅샷을 뜨고 경로·유닛·계정을 새 이름으로 옮긴다. 리허설이 「업로드·비밀이 따라오고 옛 것이 남지 않는다」를 확인했다 |
| **PostgreSQL 설치** | Stage 6·7 이 실제로 cluster·role·DB·`pg_hba`·`listen_addresses`·extension 을 세운다. `max_connections` 를 120 이상으로 맞춘다 — 「AI 쿼터 잠금이 커넥션을 하나 더 쓴다」 risk 가 여기서 닫혔다 |
| **되돌리기** | `upgrade` 는 먼저 스냅샷(파일 + `pg_dump -Fc` + `pg_restore --list` + 체크섬)을 뜨고, `rollback` 은 체크섬을 확인한 뒤 복원하고 **복원 결과를 센다** |

## S4 가 드러낸 것 — 조용히 초록이던 자리 넷 (**D-228**)

값이 나간 것은 스크립트를 쓴 것이 아니라 **컨테이너에서 열한 번 돌려 본 것**이다.
넷 다 「검사가 있는데 검증하고 있지 않았다」 부류다 — S3 이 셋을 찾은 것과 같은 종류.

**1. 번들 신선도 해시가 운영체제를 탔다.** `sorted(Path)` 가 Windows 는 대소문자 무시,
리눅스는 바이트 순이다. 199개 파일의 내용 해시는 양쪽이 **전부 같은데** 최종 해시가 달랐다.
Windows 에서 찍은 기준으로는 **모든 리눅스 설치가** Stage 5 에서 「번들이 낡았다」로 죽는다.
정렬 키를 경로 문자열로 고정하고 `--self-test`(사례 6개·반례 포함)를 정적 검사에 걸었다.

**2. `pg_restore` 는 오류를 세어 두고 0 으로 끝난다.** `--exit-on-error` 가 없으면 그렇다.
`--clean` 이 표를 먼저 지우므로 전부 실패해도 「복원했다」가 되고 **빈 데이터베이스**가 남는다.
실제로 그렇게 초록으로 통과했다. 원인은 덤프 안의 extension DDL 이 슈퍼유저 전용이라는 것이고,
`--use-list` 로 그 항목만 뺐다. 지금은 복원 뒤 `public` 표 수를 세어 비어 있으면 실패로 본다.

**3. `nginx -t` 는 인증서 파일이 없으면 죽는다.** 그래서 사양 초안의 Stage 순서
(15=nginx, 16=TLS)로는 설치가 **돌 수가 없었다.** 문서를 실제에 맞춰 뒤집었다.

**4. CRLF 로 저장된 셸 스크립트는 리눅스에서 안 돈다** — 그리고 스크립트 안의 CRLF 가드는
`set -euo pipefail` **뒤에** 있어 영원히 울리지 않는다(옛 installer 도 같다). 리허설 한 회차를
버리고 나서 배포 자산 줄바꿈 검사를 정적 검사에 넣었다.

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 프로브 8건 · PG 스택 실측(D-209~D-212) ·
  `VARCHAR(n)` 감사(D-214). **제품 코드 diff 0.**
- **S2 — PostgreSQL Foundation.** 70 표 · 256 인덱스가 `0001_pg_baseline` 하나로 선다.
  SQLite Runtime 의존 0 · `--workers 1→4`. 결정 **D-215~D-221**.
- **S3 — Product Identity · Hostname · TLS.** CN/SAN 일치 · `ssl_verify_result=0` ·
  브라우저 프로브까지 검증 켜고 통과. 결정 **D-222~D-224**.
- **S4 — 설치 · 배포 자동화 Foundation.** 위 두 절. 결정 **D-225~D-229**.

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다** (S2 가 남긴 구분, 그대로 유효)

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001_pg_baseline` 하나가 70 표 · **256 인덱스** · 부트스트랩 5행을 만든다 |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** S4 는 새 installer 를 **컨테이너에서만** 돌렸다 — 운영 설치를 새 slug 로 이전하는 것은 데이터 이관과 함께 갈 일이고 S13·S14 의 몫이다 |

이관은 S13(Dry Run) → S14(Cutover)의 일이고, 그 사이 Session(S5~S12)은 새 스키마 위에서
개발한다. `alembic/legacy_sqlite/` 61개를 지우지 않은 이유가 이것이다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **설치까지 끝났다.** Installer Stage 6·7 이 cluster·role·DB·extension·`max_connections` 를 세우고 리허설이 실측했다 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ · S4 ✅ |
| **SQLite 제거** | **Runtime 의존 0.** 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ → S13·S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `ticket_cache` 1,124 · `document_cache` 110 | Notion Runtime 의존 0, 데이터는 PG 로 | S13 → S14 |
| **AI** | **권한 필터 없음.** n8n → `claude-work-assistant`(8789) 가 Notion 전량을 모델에 싣는다 | Model Gateway + 권한이 앞서는 Hybrid Retrieval | S9 · S10 · S11 |
| **Backup** | **기본형 + 설치 스냅샷.** `pg_dump -Fc` + 체크섬 + `pg_restore --list` + `--exit-on-error` 복원 + 복원 결과 확인 | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ · S4 ✅ → S12 |

**Identity 축은 닫혔다** — 호스트명·TLS 는 S3, slug(경로·유닛·시스템 계정·콘솔이 보는 이름)는 S4.
**남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고, 바꾸면 전원이 로그아웃돼 S14 로 넘겼다
(`BACKLOG.md` **P-33**).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S4 는 배포 자산이 주역이지만 **런타임 위상**(스케줄러 레인)과 **공유 계층**(제품 정체성)을
건드렸다. E1 의 인용으로 끝내지 않고 **백엔드 전 회귀를 다시 돌렸다.**

| 대상 | 결과 |
|---|---|
| **LXD Clean 설치 리허설** | **LXD_REHEARSAL_OK — 34항.** 원장 [`EVIDENCE/S4/lxd_rehearsal.txt`](EVIDENCE/S4/lxd_rehearsal.txt) |
| ├ Clean 설치 | Stage 0~18 전부 `OK`(11·12 는 `SKIP` — 그 Component 가 아직 없다) |
| ├ 재실행이 무해한가 | 설정 해시와 스키마가 그대로. 「기존 설정을 보존하고 설치처 값만 맞췄습니다」 |
| ├ 의도적 실패 주입 | `--inject-failure 9` → `STAGE_9_MIGRATION: FAIL` · `INSTALL_FAILED stage=9` · **다음 Stage 없음** |
| ├ rollback | 체크섬 확인 → 복원 → **public 표 71개 확인** → verify 통과 |
| ├ upgrade / uninstall / 재설치 | 각 1회. `uninstall` 은 데이터를 남기고 `--purge --yes` 만 지운다 |
| └ 옛 slug 이전 | 업로드·비밀이 새 자리로 따라오고 **옛 경로·유닛·시스템 계정이 사라진다** |
| **실 재부팅 복구** | **REBOOT_RECOVERY_OK.** `boot_id` `944f2f25…` → `4a16b59b…` 로 **진짜 재부팅을 먼저 확인**하고, 수동 명령 0회로 컨테이너 → PG·nginx·privhelper·worker·scheduler·web 전부 복귀 · `/healthz`·`/readyz` 200 · 표 71개 그대로 · `install.sh verify` 통과. 원장 [`EVIDENCE/S4/reboot_recovery.txt`](EVIDENCE/S4/reboot_recovery.txt) |
| `verify` 가 진짜 검증하는가 | `--cacert` + `--resolve` 로 `ssl_verify_result=0` · CN/SAN 대조 · `server_name` 중복 검사. **`curl -k` 는 쓰지 않는다**(S3 이 그 초록의 값을 보여 줬다) |
| 백엔드 전 회귀 (PostgreSQL) | **통과 — 3,290건 / 346파일.** unit · regression · security · integration 4청크가 전부 초록이다. 한 회차에서 `test_tenant_defaults` 가 빨간불이었는데 **검사가 옳았다** — 리허설 스크립트 둘이 이 설치처의 호스트명을 기본값으로 들고 있었다. 고치고 `tests/unit` 을 다시 돌려 초록을 확인했다 |
| `scripts/static_checks.sh` | **S4 가 넣은 것은 전부 통과.** 전체는 **여전히 빨간불이고 원인은 S4 가 아니다** — 아래 절 |
| `check_bundle_fresh.py --self-test` | **BUNDLE_SELFTEST_OK (6 사례)** — 반례로 옛 구현이 실제로 다른 순서를 내는 것을 확인했다 |
| 프런트 | **인용** — `frontend/` diff 0. 번들 기준(`BUILD_STAMP.json`)은 다시 적었지만 **번들 자체는 안 바뀌었다**(해시 규칙만 결정적으로 고쳤다) |

### ⚠️ `static_checks.sh` 전체는 아직 빨간불이다 — **S1 이후 UI 커밋 둘이 남긴 것이다**

S2·S3 이 기록한 것과 같고 아무것도 바뀌지 않았다. `BACKLOG.md` **P-09a** 가 Owner(UI 축)를 갖는다.

| 무엇 | 어디서 왔나 |
|---|---|
| 사용자 문구의 가운뎃점(·) **7건** | `4dd62181` — `Integrity.jsx` · `AccentPicker.jsx` · `Sprint.jsx` · registry 4곳 |
| `tokens.css` 가 `theme.js` 와 어긋남 | `dac17928` 이 토큰 정본을 고치고 `generate_design_tokens.mjs` 를 안 돌렸다 |

**고칠 때까지 모든 Session 이 빨간 정적 검사를 본다** — 자기 회귀로 오해하지 않도록 남긴다.

## NOW

**S4 는 끝났다.** Clean OS 에서 세 줄로 제품이 서고, 재부팅하면 사람 손 없이 돌아온다.

이 세션에서 가장 값이 나간 것은 `install.sh` 를 쓴 것이 아니라 **그것을 열한 번 돌려 본 것**이다.
「검사가 있는데 검증하고 있지 않았다」를 넷 찾았고(D-228), 그중 둘은 **되돌리기가 데이터를 없애는**
부류였다 — `pg_restore` 가 오류를 삼키고 0 으로 끝나던 것, 그리고 그 앞에서 `--clean` 이 표를
먼저 지우던 것. 스크립트만 읽어서는 셋 다 초록으로 보였다.

재부팅 검증을 두 조각으로 나눈 이유도 같다(D-229). 한 스크립트가 재부팅을 걸고 이어서 확인하면
그 사이에 사람이 무엇을 했는지 구분할 수 없다. 그래서 `prep` 이 상태를 적고 끝나고, `verify` 는
**`boot_id` 가 바뀌었는지부터** 본다 — 그것이 그대로면 아래 초록은 「원래 떠 있었다」는 뜻일 뿐이다.

## NEXT — 다음 시작점: S5 (요청 시)

**S5 = Identity & Access.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, 설계 요지는 §5.1.

S4 가 S5 에게 넘기는 것:

1. **Installer 계약이 이제 스크립트로 강제된다** (INSTALLATION §6.1 · D-227). Runtime Component 를
   추가하면 그 Session 이 Stage·유닛·probe·uninstall·복구를 함께 넣어야 한다. Stage 12·13 이
   「소스에 Component 가 생겼는데 Stage 가 비어 있는」 상태를 **FAIL** 로 잡는다
2. **제품 이름·경로를 새로 쓸 일이 있으면 `app/core/product.py` 에 넣는다.** 거기 없는 곳에
   문자열로 적으면 `tests/unit/test_product_identity.py` 가 잡는다
3. **S5 는 `roles`·`permissions` 표를 만든다** — 지금은 없다. 리허설의 데이터 확인이
   `pg_tables` 수를 세는 이유가 그것이다(`roles` 를 세려다 한 번 헛짚었다)
4. **`P-12a` 결재 대리 범위 게이트**가 S5 소유로 남아 있다 — S1 이 드러낸 실제 결함이다

## RISK — 지금 살아 있는 것

전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12. **S4 가 R13·R14 를 닫고 R15·R16 을 줄였다.**

| # | Risk | 상태 / Owner |
|---|---|---|
| ~~R1~~ ~~R2~~ ~~R3~~ | (S2 가 닫음) | 해소 |
| ~~R4~~ ~~R5~~ ~~R6~~ ~~R7~~ | (S1 이 닫음) | 해소 |
| ~~R13~~ | 제품 slug | **해소** — 남은 것은 세션 쿠키 이름 하나(P-33 · S14) |
| ~~R14~~ | 설치 자동화를 마지막에 몰면 실패한다 | **골격 해소.** 계약 이행은 매 Session 이 계속 진다 |
| R15 | LXD 컨테이너가 실 장비와 다르다 | **절반 해소** — 재부팅 축은 닫혔다(D-229). **Storage(NFS/SMB)는 여전히 컨테이너에서 검증되지 않는다** → S8 |
| R16 | GitLab 주소 부재 | **완화** — Installer 가 Remote 중립이다. 주소가 오면 설정만 바꾼다 |
| R17 | pgvector 검색 품질 | S10(하이브리드 가중치) |
| — | **운영 데이터가 아직 SQLite 에 있고, 운영 서버는 아직 옛 slug 설치다** | S13 · S14 |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore). 값을 tracked 파일·커밋·로그에 복사하지 않는다 |
| **LXD** | 이 서버에 **초기화해 뒀다**(dir 스토리지 풀 + `lxdbr0`). `sudo bash scripts/lxd_rehearsal.sh <src.tar.gz>` 로 언제든 다시 돈다. **`/dev/kvm` 이 없어 LXD VM 은 못 쓴다**(VMware 게스트) — 실 재부팅이 필요하면 서버 자체를 재부팅한다 |
| **리허설 소스 tarball** | 작업 트리를 그대로 tar 로 만들어 넣는다(`.git`·`node_modules`·`docs`·`tests`·`var` 제외). **LF 로 저장돼 있어야 한다** — 정적 검사가 그것을 본다 |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. 옛 이름은 DNS 에 없다(NXDOMAIN). 인증서는 자체서명이고 사본이 `dist/ops/` 에 있다 |
| **하네스를 원격에 겨눌 때** | `UI_QA_TLS_CA` 로 그 인증서를 준다 — `tls.py` 가 파이썬과 Node 양쪽에 심는다. **Chromium 의 페이지 이동만은 운영체제 신뢰 저장소를 본다**(이 개발 머신에는 넣어 뒀다). QA 계정 `ui-qa@goodmit.co.kr` 은 **보관 상태**다 |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433). `CLOVIR_TEST_PG_URL` 로 덮어쓴다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다**. `PG_BIN_DIR` 를 비워 두면 안 된다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 시험 Storage 로 실검증. 실 정보 수령 시 **Configuration 만** 변경 (U8·U9) |
| 20개 Project Key 명명 | **S6 에서** 초안표 제시 → 사용자 확인 → 적용. **확정 전 재채번 없음** (U11) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19) |
| GitLab Repository 주소·자격증명 | Installer 가 Remote 중립이라 **주소가 정해지면 설정만 바꾼다** (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
