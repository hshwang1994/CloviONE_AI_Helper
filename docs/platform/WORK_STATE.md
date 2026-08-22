# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-22** (S6)
- phase: **B — 도메인**
- session: **S6 완료.** 다음은 **S7 — Knowledge Domain**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S6 도 옮기지 않는다.** S6 의 시험 변경은 전부 강화 방향이다 — **시험 10파일 · 91건 신설**
  (integration 19 · regression 15 · security 10 · unit 47) + 프런트 10건. 옛 시험에서 줄인
  것은 없고, 축이 바뀐 자리 셋(WBS·부모 미러·진행률 순수함수)은 **같은 성질을 새 축으로
  다시 단언**한다
- s1_commit: `95a89189` · s2_commit: `eec4886c` · s3_commit: `e88e4de3` · s4_commit: `6909bb96` ·
  s5_commit: `aa9c8c63`
- working_tree: clean
- **Runtime Component 는 늘지 않았다** — Installer 계약(D-205)은 무변경. 프런트 의존이
  셋 늘었고(`@dnd-kit/*`) 번들은 **라우트 단위로 늦게 싣는다**(`WorkBoard` 57.9 kB · gzip 19.9)

## S6 가 실제로 한 것

이름 축이다. 이제 **티켓은 세 이름으로 불리고, 그 셋이 영원히 같은 티켓을 가리킨다.**

| | |
|---|---|
| **세 층의 이름** | `id`(uuid) · `canonical_key`(`SKH-37`) · `legacy_key`(`GIT-142`). 해석 순서는 canonical → legacy → alias → uuid 이고 **순서가 계약이다** (D-195) |
| **canonical 을 앱이 안 쓴다** | BEFORE INSERT/UPDATE 트리거가 `projects.code + seq` 로 파생시킨다. 앱이 무엇을 적든 트리거가 덮어쓴다 — 어긋날 자리가 없다 (**D-236**) |
| **Key 소유는 영구** | `project_key_registry`. `retired` 는 「해제」가 아니라 「더 쓰지 않는다」다 — 행이 남아 있어야 `<KEY>-<SEQ>` 가 전역에서 안 겹친다. `GIT` 은 예약어다 |
| **Key 20건 확정** | 사용자가 초안표 그대로 승인했다(2026-08-22). 정본은 `app/work/project_keys.py::CONFIRMED` 이고 문서가 사본이다 — 문서만 두면 S13 이 20줄을 손으로 옮겨 적는다 (**D-243**) |
| **채번** | `INSERT … ON CONFLICT DO UPDATE … RETURNING`. 롤백되면 번호도 돌아온다 — `SEQUENCE` 는 안 돌아와서 안 쓴다 (D-196) |
| **표 이름** | `ticket_cache` → **`tickets`** (인덱스 8 · 제약 3 함께). `TicketCache` 는 별칭이고 **컬럼 이름은 그대로**다 (**D-238**) |
| **계층** | `ticket_relations` 한 곳이다. `parent_page_id` 는 그 표의 **입력**이고, 진행률·WBS 가 `parent_map` 하나를 지난다 (**D-239**) |
| **상태 어휘** | 앱이 소유한다. `app/work/workflow.py` 가 정본이고 `ticket_statuses` 가 그 결과다 — 표시 Status 6 → 집계 Category 4 |
| **낙관적 잠금** | Ticket·Project·Document 가 **같은 이름의 정수 `version`**. `notion_version` 해시는 물러났다 (**D-240**) |
| **순서** | `backlog_rank`(정밀도 없는 `numeric`). 프런트는 인덱스가 아니라 **놓인 자리의 두 이웃**을 보낸다 (**D-241**) |
| **Drop** | Status+Activity+Audit+`updated_at`+Notification 이 **한 트랜잭션**. 상태만은 저장소 seam 을 지난다 (**D-242**) |

## S6 이 드러낸 것 — 초안이 지금 데이터와 안 맞던 자리

§5.2 의 `ck_tickets_assigned` 는 `project_id`·`seq`·`canonical_key` 셋을 한 묶음으로
묶었다. **그대로 걸면 미러 1,124행이 전부 위반이다** — 프로젝트에는 연결돼 있는데
Project Key 가 하나도 없어서(22건 전부 `code IS NULL`) 번호를 줄 수가 없다.

계획이 틀린 것이 아니라 **계획이 그리는 상태가 S13 이후의 상태**였다. 그래서 지금 지켜야
하는 불변식만 남기고(번호와 표시 이름은 함께 있거나 함께 없다), 나머지 절반은 트리거가
막게 했다 — 「번호는 Key 를 가진 프로젝트 안에서만 발급된다」는 한 문장은 그대로다(D-237).

두 번째로 드러난 것: **계층을 도메인 표로 옮기니 순환이 들어올 수 없게 됐다.** 그래서
`wbs.py` 의 순환 방어를 실 DB 로는 시험할 수 없게 됐고, 그 시험을 순수 함수 층으로
옮겼다 — 방어 자체는 **그대로 둔다**(그물 하나에만 기대지 않는다).

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
- **S5 — Identity & Access.** 권한이 표가 되고 가시성이 함수 하나가 됐다. 결정 **D-230~D-235**.
- **S6 — Work Domain.** 위 두 절. 결정 **D-236~D-242**.

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다** (S2 가 남긴 구분, 그대로 유효)

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001`+`0002`+`0003` 이 **84 표**를 만든다 (S6 이 9 표 신설 · 트리거 1) |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** 운영 설치를 새 slug 로 이전하는 것은 데이터 이관과 함께 갈 일이고 S13·S14 의 몫이다 |

**S13 이 알아야 하는 것 셋**:
1. 표 이름이 `departments` → `org_units`(D-234), `ticket_cache` → `tickets`(D-238)로 바뀌었다.
   **컬럼 이름은 둘 다 그대로**다(`department_id`·`dept_id`·`project_uid`).
2. 적재 직후 `app/work/numbering.py::seed_counters()` 를 부른다 — 안 부르면 첫 신규 티켓이
   마지막 기존 티켓과 같은 번호를 받는다.
3. **Project Key 20건은 확정됐다**(2026-08-22 · D-243). 적재 직후 순서가 하나다 —
   프로젝트 적재 → `app/work/project_keys.py::apply_confirmed(db)` →
   `numbering.seed_counters(db)` → 재채번. 뒤바뀌면 번호가 겹친다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **설치까지 끝났다.** Installer Stage 6·7 이 cluster·role·DB·extension 을 세운다 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ · S4 ✅ |
| **SQLite 제거** | **Runtime 의존 0.** 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ → S13·S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `ticket_cache` 1,124 · `document_cache` 110. **다만 받을 그릇은 이제 있다** — 식별자·채번·예외 분류가 S13 의 입력 그대로다 | Notion Runtime 의존 0, 데이터는 PG 로 | S13 → S14 |
| **AI** | **권한 필터 없음.** n8n → `claude-work-assistant`(8789) 가 Notion 전량을 모델에 싣는다. 붙일 함수는 있다 — S10 은 `effective_visibility_clause` 에 연결하기만 하면 된다 | Model Gateway + 권한이 앞서는 Hybrid Retrieval | S9 · S10 · S11 |
| **Backup** | **기본형 + 설치 스냅샷.** `pg_dump -Fc` + 체크섬 + `--exit-on-error` 복원 + 복원 결과 확인 | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ · S4 ✅ → S12 |

**Identity 축은 닫혔다** — 호스트명·TLS 는 S3, slug 는 S4, 역할·권한·가시성은 S5.
**남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고, 바꾸면 전원이 로그아웃돼 S14 로 넘겼다
(`BACKLOG.md` **P-33**).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S6 은 **공유 계층 셋**을 바꿨다 — 티켓 표 이름, 계층의 정본, 프로젝트 잠금 규약.
그래서 E1 인용으로 끝내지 않고 **백엔드 전 회귀를 다시 돌렸다.**

| 대상 | 결과 |
|---|---|
| 백엔드 전 회귀 (PostgreSQL) | **FULL_REGRESSION_OK — 3,497건 / 361파일, 38분 43초.** unit · regression · security · integration 4청크 전부 초록 |
| **채번 동시성** (§9.3 면제 불가) | **5건.** 12스레드 동시 생성에서 **1..12 가 정확히 한 번씩** · 프로젝트별 번호 공간 분리 · **롤백 시 미소비** · `seed_counters` 는 낮추지 않는다. **반례를 함께 둔다** — 잠금 없는 「읽고 +1」이 실제로 부딪히는지 먼저 보여, 세 시험이 「경합이 안 일어나서」 통과한 상태와 구별한다 |
| **`GIT-142` resolution** | **8건.** 번호 전·후, Key 변경 뒤에도 같은 티켓. **어느 층이 답했는지**까지 단언한다(찾기만 보면 순서가 뒤집혀도 통과한다). 옛 Key 는 `retired` 라 다른 프로젝트가 못 가져가고, 앱이 `canonical_key` 에 무엇을 적든 트리거가 덮어쓴다 |
| **Exception 임의 배정 0** | **7건.** 네 갈래(ambiguous·missing·unresolved·source_missing)를 실제로 잡는지 먼저 보이고, 그 티켓들에 **프로젝트도 번호도 안 붙는지** 확인한다. 재실행해도 줄이 안 쌓이고, 사람이 지정하는 순간 채번이 돈다 |
| **Drop 한 트랜잭션** | **6건.** 다섯이 함께 남는지, 그리고 **실패를 주입해 다섯이 함께 사라지는지**. 낡은 판은 409 · 모르는 상태는 422 · 빈 이동은 422 |
| **보드 범위 (음성)** | **10건.** 판·백로그·이동·이름 해석·관계 잇기·상세가 전부 범위를 지킨다(**404**, 403 이 아니다). 각 단정에 「우리 것은 보인다」를 함께 둬서 전부 막는 구현이 통과하지 못하게 한다 |
| **확정 Key 적용** | **17건.** 문서와 코드가 같은 20쌍인지(순서까지) · 확정 Key 가 제품 규칙을 통과하는지 · 예약어와 안 겹치는지 · 그리고 **표에 없는 프로젝트는 안 건드리는지**(U11). 잘린 이름 `OKE` 를 다음 사람이 「오타 같다」며 완성하지 못하게 못박는다 |
| `check_work_domain_single_source.py` | **신설.** 자기검증 8사례(검출 7 · 위양성 1) · 규칙 6개를 app 340파일에서 확인. `canonical_key` 는 **어느 파일도** 못 쓴다(트리거만) |
| 마이그레이션 왕복 | `upgrade` → `downgrade` → `upgrade` 를 실 PG 에서 돌렸다. 표 76→85 · 인덱스 276→313 · 제약 162→201 · 트리거 1 이 **대칭으로** 돌아온다 |
| 프런트 | `npx vitest run` — **2,431건 / 324파일 중 3 실패**(전부 S6 이전 커밋이 남긴 것, 아래 참조). DnD 자리 계산 10건 신설 |
| 번들 | `npm run build` 통과 · `check_bundle_fresh.py --write`. `WorkBoard` 는 **라우트 단위 lazy** 라 첫 로딩에 안 실린다 |

### ⚠️ `static_checks.sh` 와 프런트 시험은 아직 빨간불이다 — **S6 이 만든 것이 아니다**

`BACKLOG.md` **P-09a** 가 Owner 를 갖는다. **S6 은 자기가 넣은 것을 전부 고쳤다.**

| 무엇 | 어디서 왔나 |
|---|---|
| 사용자 문구의 가운뎃점(·) 7건 · `tokens.css` 드리프트 · S4 잔여 둘 | S5 가 이미 기록한 넷 |
| `ko-wordbreak.test.jsx:179` 안 닫힌 JSX 주석 | `dac17928` (S6 이 `git log -L` 로 확인) |
| `SettingVersions.jsx:75` 의 「변경」(표준 동사표는 「수정」) | `c1bd9306` |
| `settings-coerce.test.jsx` 「검증 통과」 미표시 | S6 이전 |

## NOW

**S6 은 끝났다.** 티켓은 이제 세 이름으로 불리고, 그 셋이 영원히 같은 티켓을 가리킨다.

이 세션에서 가장 값이 나간 것은 표를 만든 것이 아니라 **되돌릴 수 없는 것과 그렇지 않은
것을 가른 것**이다. Key 소유는 영구라 사람이 정하고(D-197), 번호는 트랜잭션 안에 있어서
롤백되고, 표시 이름은 트리거가 만들어서 앱이 어긋나게 할 수가 없다. 셋 다 「조심해서 쓰자」로
막을 수 있는 성질이 아니다.

두 번째는 **초안과 지금 데이터의 거리를 재 본 것**이다. §5.2 의 제약을 그대로 걸었다면
마이그레이션이 첫 줄에서 실패했다 — 그 제약이 그리는 것은 S13 이후의 상태였다. 계획을
고친 것이 아니라 **지금 지킬 수 있는 절반과 트리거가 지킬 절반으로 나눴다.**

## NEXT — 다음 시작점: S7 (요청 시)

**S7 = Knowledge Domain.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, 설계 요지는 §5.3.

S6 이 다음 Session 에게 넘기는 것:

1. **새 자원의 쓰기 입구를 하나로 둔다.** `scripts/check_work_domain_single_source.py` 의
   `RULES` 에 한 줄 더하면 그 규칙이 app 전체에서 지켜진다 — S7 의 Block JSON 정본
   (D-198)이 정확히 같은 성질을 요구한다(정본이 하나여야 파생이 갈라지지 않는다)
2. **권한 어휘 `SPACE_*` 는 이미 있다** (S5 가 미리 고정했다). 새 이름을 짓지 말고 그것을
   쓰고, 소비처를 연결한 뒤 마이그레이션 시드도 함께 고친다
   (`tests/unit/test_identity_access_seed.py` 가 둘을 맞물려 둔다)
3. **`document_cache.version` 이 이미 있다** — S6 이 세 자원에 같은 규약으로 넣었다(D-240).
   S7 이 `documents` 표를 만들 때 그 컬럼을 옮겨 가면 되고, 새 잠금 방식을 만들지 않는다
4. **DnD 가 필요하면 `frontend/src/ui/DragDrop.jsx` 를 쓴다** — 폴더 트리 정렬이 그 자리다.
   키보드·스크린리더 안내가 거기 한 곳에 있고, 새로 만들면 그 둘이 빠진다
5. **`kit.jsx` 는 S6 이 안 건드렸다.** S7 과 겹치지 않는다
6. **문자열 날짜 컬럼은 S7 것이다** (`BACKLOG.md` **P-14a**). 실측 10번이 「S6·S7 로
   이월」이라고만 적어 두어 소유가 갈려 있었는데, **반씩 나눠 하면 더 나쁘다** — 티켓·
   프로젝트·문서가 같은 문자열 규약을 공유하고 동기화 파서·필터·리포트·번다운이 전부
   그 규약으로 비교한다. S6 이 새로 만든 `sprints.starts_on`·`ends_on` 도 **일부러 같은
   규약**을 따랐다

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

- **없음.** Project Key 20건이 확정되면서(D-243) 마지막 결정 대기도 닫혔다.

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **20개 Project Key 명명** | **확정됐다** (2026-08-22 · D-243). 정본은 `app/work/project_keys.py::CONFIRMED`, 사람이 읽는 사본은 [`PROJECT_KEYS.md`](PROJECT_KEYS.md). **지금 적용된 프로젝트는 0건이고 그것이 정상이다** — PG 의 `projects` 가 비어 있다(적재는 S13). 한 건씩 손으로 넣을 때는 `PUT /api/work/projects/{id}/key` |
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore). 값을 tracked 파일·커밋·로그에 복사하지 않는다 |
| **LXD** | 이 서버에 **초기화해 뒀다**(dir 스토리지 풀 + `lxdbr0`). `sudo bash scripts/lxd_rehearsal.sh <src.tar.gz>` 로 언제든 다시 돈다. **`/dev/kvm` 이 없어 LXD VM 은 못 쓴다** — 실 재부팅이 필요하면 서버 자체를 재부팅한다 |
| **리허설 소스 tarball** | 작업 트리를 그대로 tar 로 만들어 넣는다(`.git`·`node_modules`·`docs`·`tests`·`var` 제외). **LF 로 저장돼 있어야 한다** |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. 옛 이름은 DNS 에 없다(NXDOMAIN). 인증서는 자체서명이고 사본이 `dist/ops/` 에 있다 |
| **하네스를 원격에 겨눌 때** | `UI_QA_TLS_CA` 로 그 인증서를 준다 — `tls.py` 가 파이썬과 Node 양쪽에 심는다. **Chromium 의 페이지 이동만은 운영체제 신뢰 저장소를 본다.** QA 계정 `ui-qa@goodmit.co.kr` 은 **보관 상태**다 |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433). `CLOVIR_TEST_PG_URL` 로 덮어쓴다 |
| **전 회귀를 백그라운드로 돌릴 때 (Windows)** | **`run_full_regression.sh` 가 이제 스스로 `< /dev/null` 을 붙인다** (P-09e). `tests/regression/test_stage_static_update.py` 가 `subprocess.run(capture_output=True)` 로 셸 스크립트를 부르는데, stdin 이 안 닫힌 파이프면 그 자식이 영원히 막힌다. `subprocess` 의 `timeout=` 은 **손자 프로세스를 안 죽여서** 5분 뒤에도 안 풀린다 — 겉보기에는 pytest 가 65% 에서 멈춘 것으로 보이고 CPU 도 0 이다. 근본 조치(시험이 `stdin=subprocess.DEVNULL` 을 넘기는 것)는 P-09e 가 소유한다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다**. `PG_BIN_DIR` 를 비워 두면 안 된다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 시험 Storage 로 실검증. 실 정보 수령 시 **Configuration 만** 변경 (U8·U9) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19) |
| GitLab Repository 주소·자격증명 | Installer 가 Remote 중립이라 **주소가 정해지면 설정만 바꾼다** (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
