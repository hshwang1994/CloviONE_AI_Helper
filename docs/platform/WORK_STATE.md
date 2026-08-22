# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-22** (S5)
- phase: **B — 도메인**
- session: **S5 완료.** 다음은 **S6 — Work Domain** (또는 S7, 둘은 병렬 가능)
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S5 도 옮기지 않는다.** S5 의 시험 변경은 전부 강화 방향이다 — **시험 7파일 · 125건 신설**
  (보안 5파일 114건 · 단위 2파일 11건). 줄어든 것은 표 이름을 새 이름으로 맞춘 마이그레이션
  회귀 3파일뿐이라 `qa-contract-change:` 를 적었다. 그 기준선 대비 그대로 통과한다
- s1_commit: `95a89189` · s2_commit: `eec4886c` · s3_commit: `e88e4de3` · s4_commit: `6909bb96`
- working_tree: clean
- **런타임 권한 계약이 바뀌었다.** 가시성 판정의 자리가 옮겨 갔고(D-231) 프로젝트 멤버가
  새 가시성 갈래가 됐다(D-233). 새 Runtime Component 는 없다 — Installer 계약(D-205)은 무변경

## S5 가 실제로 한 것

권한 축이다. 이제 **「누가 무엇을 할 수 있는가」는 표에 있고, 「무엇이 보이는가」는 함수 하나에 있다.**

| | |
|---|---|
| **권한 모델** | `permissions` 32 · `roles` 5(builtin) · `role_permissions` 107 · `user_roles` · `resource_grants`. 마이그레이션 `0002_identity_access` 하나가 세운다 |
| **다섯 역할의 뜻** | **안 바뀌었다.** 권한 → 역할 사상은 `app/authz/permissions.py` 가 적고 그 오른쪽은 **반드시 `app/core/authz.py` 의 그룹 상수**다 — 「역할 → 사람」은 여전히 한 곳이다 (**D-230**) |
| **가시성** | `app/authz/visibility.py::effective_visibility_clause` 하나. 규칙마다 **SQL 절과 행 판정 두 표현을 한 객체에** 담아 두 렌더러가 같은 목록을 접는다 (**D-231**) |
| **`confidential`** | 유일한 축소 원시연산. 예외는 셋(소유자·명시 부여자·`*_ADMIN`)인데 **검색에는 하나도 없다** — 그 차이를 자원 명세의 한 칸으로 만들었다 (**D-232**) |
| **직접 부여** | `resource_grants`. 없으면 `confidential` 은 축소가 아니라 잠금이다. 쓰기 입구는 제한 토글과 같은 권한(`PUT /api/team-docs/{id}/allowed-users`, 운영자만) |
| **Project Member** | D-193 의 공식에는 있는데 **코드에는 없던 항**이다. 넣었다 — 부서가 달라도 참여한 프로젝트는 보인다. 넓히기만 하므로 기존 판정은 그대로 (**D-233**) |
| **`org_units`** | `departments` 표를 이름째 옮겼다(인덱스 4 · 제약 3 · `kind` 추가). `Department` 는 **같은 클래스의 별칭**이다. 컬럼 이름과 API 경로는 그대로 (**D-234**) |
| **auth Provider** | 로그인 일곱 조각 중 **자격 증명 검증 하나만** 뗐다. LDAP 이 와도 잠금·감사·세션은 안 건드린다. 모르는 Provider 이름은 **오류**다 (**D-235**) |
| **P-12a** | 결재 대리 셋이 `principal` 을 안 받던 것을 닫았다. `check_scope_gates.py::KNOWN_GAPS` 가 **비었다** |

## S5 가 드러낸 것 — 「같은 규칙」이 절반만 사실이던 자리

D-194 는 목록·상세·Search 가 같은 함수를 쓰라고 했고, 겉보기에는 그랬다 —
셋 다 `app/core/ownership.py` 를 불렀다. **그런데 그 공용 파일 안에서 판정이 넷이었다:**

| 무엇 | 목록·상세 | Search |
|---|---|---|
| 소속 | `scope_can_view` (파이썬) | `stored_ownership_clause` (SQL) |
| 열람 제한 | `doc_in_scope` 안의 두 줄 | `not_restricted_clause` |

같은 파일에 있었을 뿐 **네 곳에 각각 적혀 있었다.** 한쪽만 고치는 날 갈라지는 구조이고,
그것이 이 저장소가 네 번 반복한 실수의 정확한 모양이다.

그래서 규칙 하나가 **두 표현을 함께 들도록** 바꿨다(`_Rule(sql=…, row=…)`). 갈래를 더하면
두 표현이 같이 생긴다 — 한쪽만 만들 수가 없다. 그리고 그 설계가 실제로 성립하는지는
**실행해 봐야 알기 때문에** 진짜 행으로 전수 대조한다(자원 3종 × 사람 5명).

두 번째로 드러난 것: **`Project Member` 는 D-193 의 공식에 있는데 코드에는 없었다.**
`project_members` 표는 있는데 가시성이 그것을 안 봤다 — 「참여시켜 놨는데 안 보이는」
상태이고, 설명할 수 없는 상태다.

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 프로브 8건 · PG 스택 실측(D-209~D-212) ·
  `VARCHAR(n)` 감사(D-214). **제품 코드 diff 0.**
- **S2 — PostgreSQL Foundation.** 70 표 · 256 인덱스가 `0001_pg_baseline` 하나로 선다.
  SQLite Runtime 의존 0 · `--workers 1→4`. 결정 **D-215~D-221**.
- **S3 — Product Identity · Hostname · TLS.** CN/SAN 일치 · `ssl_verify_result=0` ·
  브라우저 프로브까지 검증 켜고 통과. 결정 **D-222~D-224**.
- **S4 — 설치 · 배포 자동화 Foundation.** Clean OS 에서 세 줄, 재부팅하면 스스로 복귀.
  결정 **D-225~D-229**.
- **S5 — Identity & Access.** 위 두 절. 결정 **D-230~D-235**.

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다** (S2 가 남긴 구분, 그대로 유효)

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001_pg_baseline` + `0002_identity_access` 가 **75 표**를 만든다 |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** 운영 설치를 새 slug 로 이전하는 것은 데이터 이관과 함께 갈 일이고 S13·S14 의 몫이다 |

**S13 이 알아야 하는 것 하나**: 표 이름이 `departments` → `org_units` 로 바뀌었다(D-234).
컬럼 이름(`department_id`·`dept_id`)은 그대로다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **설치까지 끝났다.** Installer Stage 6·7 이 cluster·role·DB·extension 을 세운다 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ · S4 ✅ |
| **SQLite 제거** | **Runtime 의존 0.** 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ → S13·S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `ticket_cache` 1,124 · `document_cache` 110 | Notion Runtime 의존 0, 데이터는 PG 로 | S13 → S14 |
| **AI** | **권한 필터 없음.** n8n → `claude-work-assistant`(8789) 가 Notion 전량을 모델에 싣는다. **다만 붙일 함수는 이제 있다** — S10 은 `effective_visibility_clause` 에 연결하기만 하면 된다 | Model Gateway + 권한이 앞서는 Hybrid Retrieval | S9 · S10 · S11 |
| **Backup** | **기본형 + 설치 스냅샷.** `pg_dump -Fc` + 체크섬 + `--exit-on-error` 복원 + 복원 결과 확인 | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ · S4 ✅ → S12 |

**Identity 축은 닫혔다** — 호스트명·TLS 는 S3, slug 는 S4, 역할·권한·가시성은 S5.
**남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고, 바꾸면 전원이 로그아웃돼 S14 로 넘겼다
(`BACKLOG.md` **P-33**).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S5 는 **공유 계층**을 바꿨다 — 가시성 판정이 옮겨 가고 로그인 경로가 Provider 를 지난다.
그래서 E1 인용으로 끝내지 않고 **백엔드 전 회귀를 다시 돌렸다.**

| 대상 | 결과 |
|---|---|
| 백엔드 전 회귀 (PostgreSQL) | **FULL_REGRESSION_OK — 3,419건 / 353파일, 32분 42초.** unit · regression · security · integration 4청크 전부 초록 |
| **5역할 동등성** | **39건 전수 통과.** 옮긴 게이트 7종 × 5역할을 **두 층**에서 봤다 — 권한 보유 집합이 옛 그룹과 같은가, 그리고 실제 요청 4라우트 × 5역할의 허용/거부가 옛 규칙과 같은가. 「전부 허용하는 게이트」가 통과하지 못하도록 각 케이스에 **거부되는 역할이 있는지**를 함께 단언한다 |
| **두 렌더러 대조** | **18건 — 자원 3종 × 사람 5명 전부 일치.** 진짜 행으로 대조하고, 「보이는 행과 안 보이는 행이 모두 있는가」까지 확인한다(한쪽만 있으면 대조가 헛돈다) |
| **부여·축소 음성** | **15건.** 부여가 **그 자원만** 여는가 · 거두면 닫히는가 · 자원 종류가 다르면 같은 id 라도 안 열리는가 · `confidential` 이 같은 부서 동료에게 닫히는가 · **검색은 운영자·작성자·명시 부여자 셋 다에게 안 보여 주는가** |
| **P-12a 음성** | **5건.** 부서 admin 이 남의 부서 결재 대리를 **못 만들고 못 취소하고 못 본다**. 반대편도 함께 본다 — 자기 부서 안에서는 여전히 만들 수 있고 전역 관리자는 그대로다 |
| `check_scope_gates.py` | **미해결 GAP 0건** (라우트 선언 48파일 · 모듈 44개 · id 경로 131개 · 면제 6) |
| `check_visibility_single_source.py` | **신설.** 자기검증 5사례(검출·위양성 양방향, 「산문에만 적혀 있음」 포함) · 소비자 4개 도달 확인 · 은퇴한 판정 부품 4개를 app 전체 328파일에서 확인 |
| 마이그레이션 왕복 | `upgrade` → `downgrade` → `upgrade` 를 실 PG 에서 돌렸다. 표 이름·인덱스 4·제약 3 이 대칭으로 돌아온다 |
| `check_test_strength.py` | 통과 (`eec4886c` 대비 시험 파일 15개 검사) |
| 프런트 | **인용** — `frontend/` diff 0 |

### ⚠️ `static_checks.sh` 전체는 아직 빨간불이다 — **S5 가 만든 것이 아니다**

`BACKLOG.md` **P-09a** 가 Owner 를 갖는다. **S5 는 자기가 넣은 16건을 전부 고쳤다.**

| 무엇 | 어디서 왔나 |
|---|---|
| 사용자 문구의 가운뎃점(·) **7건** | `4dd62181` — `Integrity.jsx` · `AccentPicker.jsx` · `Sprint.jsx` · registry 4곳 |
| `tokens.css` 가 `theme.js` 와 어긋남 | `dac17928` 이 토큰 정본을 고치고 `generate_design_tokens.mjs` 를 안 돌렸다 |
| **S4 잔여 둘** | `app/worker_main.py:815` 의 로그 문자열에 em 대시(—) · `tests/unit/test_deploy_wiring.py:543` 의 `subprocess.run(text=True)` 에 `encoding=` 없음. 둘 다 `e7a5540a`·`6909bb96` 에서 왔다 |

**고칠 때까지 모든 Session 이 빨간 정적 검사를 본다** — 자기 회귀로 오해하지 않도록 남긴다.

## NOW

**S5 는 끝났다.** 권한은 표가 되었고, 가시성은 함수 하나가 되었다.

이 세션에서 가장 값이 나간 것은 새 표를 만든 것이 아니라 **「같은 함수를 쓴다」가 어디까지
사실인지 실제로 세어 본 것**이다. 셋 다 공용 파일을 부르고 있었는데 그 안에서 판정은 넷이었다 —
소속 둘(파이썬·SQL), 열람 제한 둘. 정적 검사로는 통과했을 상태이고, 실제로 D-194 는 그것을
「같은 함수」로 읽고 있었다.

그래서 이번 조치의 핵심은 표가 아니라 **모양**이다: 규칙 하나가 두 표현을 함께 들게 하면
한쪽만 고칠 수가 없다. 그리고 그 성질은 주석으로 약속할 수 없으므로, 두 렌더러를 진짜 행으로
대조하는 시험이 함께 있어야 한다.

`Project Member` 도 같은 종류의 발견이다. D-193 의 공식에 이름이 적혀 있고 표까지 있는데
**부르는 코드가 없었다** — 문서와 스키마만 보면 있는 기능이고, 실행해야 없는 것이 보인다.

## NEXT — 다음 시작점: S6 (요청 시)

**S6 = Work Domain.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, 설계 요지는 §5.2.
**S6 과 S7 은 병렬 가능**하다(서로 다른 도메인) — 다만 `kit.jsx` 같은 공유 자산은 겹치지 않게 한다.

S5 가 다음 Session 에게 넘기는 것:

1. **새 자원을 만들면 `app/authz/visibility.py` 에 등록한다.** 등록하지 않은 자원 종류는
   **아무것도 보이지 않는다**(fail-closed) — 빈 화면이 나오고, 그건 조용히 전량이 열리는
   것보다 낫다. 등록은 `_PLANS` 한 곳이고 SQL·행 두 표현을 함께 적는다
2. **권한이 필요하면 `app/authz/permissions.py` 에 넣는다.** `SPACE_*`(S7) ·
   `STORAGE_CONFIGURE`(S8) · `AI_CONFIGURE`(S9) 는 **이미 어휘가 있다** — 새 이름을 짓지 말고
   그것을 쓰고, 소비처를 연결한 뒤 마이그레이션 시드도 함께 고친다
   (`tests/unit/test_identity_access_seed.py` 가 둘을 맞물려 둔다)
3. **`confidential` 이 필요한 자원이면 `CONFIDENTIAL_MODE` 에 칸을 채운다.** 뜻은 한 문장으로
   고정돼 있다 — 자원마다 다시 해석하지 않는다
4. **S10 은 AI 경로를 같은 함수에 연결하기만 하면 된다.** P-13 이 목록·상세·Search 를 닫았고
   AI 는 그 Component 가 아직 없어 남았다. 붙이는 자리는 `effective_visibility_clause` 이고,
   음성 테스트로 증명하는 것은 D-202 의 요구 그대로다
5. **Installer 계약은 무변경이다** — S5 는 Runtime Component 를 추가하지 않았다

## RISK — 지금 살아 있는 것

전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12.

| # | Risk | 상태 / Owner |
|---|---|---|
| ~~R1~~ ~~R2~~ ~~R3~~ | (S2 가 닫음) | 해소 |
| ~~R4~~ ~~R5~~ ~~R6~~ ~~R7~~ | (S1 이 닫음) | 해소 |
| ~~R13~~ ~~R14~~ | 제품 slug · 설치 자동화 | 해소 (계약 이행은 매 Session 이 계속 진다) |
| R15 | LXD 컨테이너가 실 장비와 다르다 | **절반 해소**(재부팅 축은 D-229). **Storage(NFS/SMB)는 여전히 컨테이너에서 검증되지 않는다** → S8 |
| R16 | GitLab 주소 부재 | **완화** — Installer 가 Remote 중립이다 |
| R17 | pgvector 검색 품질 | S10(하이브리드 가중치) |
| — | **운영 데이터가 아직 SQLite 에 있고, 운영 서버는 아직 옛 slug 설치다** | S13 · S14 |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore). 값을 tracked 파일·커밋·로그에 복사하지 않는다 |
| **LXD** | 이 서버에 **초기화해 뒀다**(dir 스토리지 풀 + `lxdbr0`). `sudo bash scripts/lxd_rehearsal.sh <src.tar.gz>` 로 언제든 다시 돈다. **`/dev/kvm` 이 없어 LXD VM 은 못 쓴다** — 실 재부팅이 필요하면 서버 자체를 재부팅한다 |
| **리허설 소스 tarball** | 작업 트리를 그대로 tar 로 만들어 넣는다(`.git`·`node_modules`·`docs`·`tests`·`var` 제외). **LF 로 저장돼 있어야 한다** |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. 옛 이름은 DNS 에 없다(NXDOMAIN). 인증서는 자체서명이고 사본이 `dist/ops/` 에 있다 |
| **하네스를 원격에 겨눌 때** | `UI_QA_TLS_CA` 로 그 인증서를 준다 — `tls.py` 가 파이썬과 Node 양쪽에 심는다. **Chromium 의 페이지 이동만은 운영체제 신뢰 저장소를 본다.** QA 계정 `ui-qa@goodmit.co.kr` 은 **보관 상태**다 |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433). `CLOVIR_TEST_PG_URL` 로 덮어쓴다 |
| **전 회귀를 백그라운드로 돌릴 때 (Windows)** | **`run_full_regression.sh` 가 이제 스스로 `< /dev/null` 을 붙인다** (P-09e). `tests/regression/test_stage_static_update.py` 가 `subprocess.run(capture_output=True)` 로 셸 스크립트를 부르는데, stdin 이 안 닫힌 파이프면 그 자식이 영원히 막힌다. `subprocess` 의 `timeout=` 은 **손자 프로세스를 안 죽여서** 5분 뒤에도 안 풀린다 — 겉보기에는 pytest 가 65% 에서 멈춘 것으로 보이고 CPU 도 0 이다. S5 가 여기서 두 번 걸려 완주한 회귀를 두 번 버렸다. 근본 조치(시험이 `stdin=subprocess.DEVNULL` 을 넘기는 것)는 P-09e 가 소유한다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다**. `PG_BIN_DIR` 를 비워 두면 안 된다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 시험 Storage 로 실검증. 실 정보 수령 시 **Configuration 만** 변경 (U8·U9) |
| 20개 Project Key 명명 | **S6 에서** 초안표 제시 → 사용자 확인 → 적용. **확정 전 재채번 없음** (U11) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19) |
| GitLab Repository 주소·자격증명 | Installer 가 Remote 중립이라 **주소가 정해지면 설정만 바꾼다** (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
