# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-23** (S13)
- phase: **D — 운영 · 이관.** S13 완료, 다음은 S14
- session: **S13 완료.** 다음은 **S14 — Cutover + Legacy 제거 (단독)**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S13 도 옮기지 않는다.** 이유는 S11·S12 와 같다 — S11 이 지운 시험 17건이 이 기준을 옮기는
  순간 검사 시야에서 사라진다. S13 은 시험을 **하나도 안 지웠다**.
- s1~s13_commit: `95a89189` · `eec4886c` · `e88e4de3` · `6909bb96` · `aa9c8c63` ·
  `971a31fa` · `87dd8707` · `0240c661` · `ba68ef2c` · `e3953192` · `08472e2e` · `5560eaaf` ·
  `3cdab1e0`
- working_tree: clean
- 스키마는 **94 표**다. `0011` 이 `legacy_mapping` 하나를 더한다.
  프런트 번들 초기 gzip **263KB**(예산 280) — S13 은 프런트를 안 건드렸다

## S13 이 실제로 한 것

**옛 데이터가 새 스키마로 전부 건너간다 — 그리고 두 번 돌려도 같다.**

실 운영 SQLite 스냅숏 + 실 Notion → 임시 PostgreSQL. 원장
[`EVIDENCE/S13/`](EVIDENCE/S13/README.md).

| | |
|---|---|
| 🔴 **검사 64건 전부 통과** | 길이 초과 0 · legacy/canonical 충돌 0 · 무결성 전항 0. 못 옮긴 것은 **분류된 예외 14건**이고 전부 사유가 붙어 있다(U11) |
| 🔴 **재실행 2회차의 신규가 0** | 같은 DB 에 같은 도구를 한 번 더. `counts` 가 한 글자도 안 달라졌고 판도 안 쌓였다(D-247). R8 이 요구한 것이 이것이다 |
| **표 63개가 계획대로 간다** | 이름이 같은 62 + 이름이 바뀐 2. 안 옮기는 10 표와 파생 1 표는 **이유와 함께** 보고서에 실린다. 계획에 없는 표를 만나면 멈춘다 |
| **세 층의 이름이 선다** | `legacy_key` 1,125 · `canonical_key` 1,120 · 별칭 1,125. 옛 `GIT-142` 가 영원히 같은 티켓을 연다(D-195) |
| **본문이 처음으로 들어왔다** | 티켓 **613건**(미러엔 31) · 문서 **103건**(미러엔 0, 평균 2,585자). Block JSON 이 정본이고 마크다운을 안 거친다(D-198) |
| **분류도 처음으로 들어왔다** | 문서 유형이 `doc_type` 으로, 카테고리가 **태그 11종 · 연결 70건**으로. 작성자 19건 |
| 🔴 **재실행을 실제로 돌려 결함 둘을 찾았다** | 표 복사와 재채번이 **같은 컬럼의 주인**이던 것(**D-275**)과 첨부 크기 한도가 **둘**이던 것(**D-280**) |
| 🔴 **「문서 분류가 비어 있다」의 원인을 찾았다** | Notion 속성 이름이 안 맞았다(**D-277**). 이제 분류가 실제로 들어온다 — 회의록 24 · 작업 계획서 21 · Knowledge base 15 … |
| **확정 Key 20건이 붙었다** | 소스가 이름을 바꿔서 20건 전부 «못 찾음» 이었다. **이름만** 갈고 Key 는 안 바꿨다(**D-278**) |

## S13 이 드러낸 것 — 회차를 두 번 돌려야 보이는 것들

### 1. 🔴 값 하나에 주인이 둘이면 **두 번째 회차에서** 터진다

1회차는 초록이었다. 2회차가 죽었다:
`ticket has a sequence number but no project`.

표 복사가 `tickets.project_uid` 를 소스 값(NULL)으로 다시 썼는데 `seq` 는 1회차 재채번이
매긴 값이 남아 있었다. 트리거는 옳았고 틀린 것은 구조였다.

**같은 결함이 `projects.code` 에도 있었고 그쪽은 오류를 안 낸다.** 소스에서 22건 전부
NULL 이라 2회차 복사가 1회차에 붙인 Project Key 를 **조용히 지운다** — 그러면
`canonical_key` 의 근거가 사라지고 `project_key_registry` 와 어긋난다.

한 번만 돌리는 도구였으면 이 둘은 Cutover 당일에 처음 보였다 (**D-275**).

### 2. 🔴 Notion 은 속성 이름이 틀려도 **오류를 내지 않는다**

INVENTORY 05 가 「문서 `type_names` 110건 전부 빈 문자열」을 사실로만 기록해 두었다.
원인은 이름이다 — 동기화가 찾는 `유형`·`카테고리`·`제목` 이 소스에 없고, 실제 이름은
` 유형`·` 카테고리`·`이름 ` 처럼 **앞뒤에 공백이 붙어 있다.** 프로젝트 진행률은 `formula`
라 `prop["number"]` 로는 영원히 `None` 이었다.

이름을 맞히는 것으로는 부족하다 — 내일 또 바뀐다. 그래서 **속성마다 「값이 들어 있던
행 수」를 세고 0 이면 보고서가 말한다.** 실 회차에서 ` 출처` 하나가 0 으로 잡혔고 그것은
정말 비어 있는 자리였다 (**D-277**).

### 3. 같은 사실에 한도가 둘이면 사람이 무엇을 정할지 못 읽는다

첨부 아홉 중 둘이 못 넘어왔는데 15MB PDF 는 **분류된 예외**였고 34MB 회의 녹음은
**blocking** 이었다. 이유는 같다 — 제품이 받는 크기를 넘었다. 내려받는 쪽이 제품과 다른
한도를 갖고 있었을 뿐이다 (**D-280**).

### 4. 확정된 표도 소스가 바뀌면 안 맞는다

D-243 이 확정한 이름 20건이 하루 만에 전부 안 맞게 됐다(실측 0/21 일치). **이름만** 갈고
Key 는 한 글자도 안 바꿨다 — 짝은 이름이 아니라 **티켓 수**로 확인했다(20/20).
옛 이름 20건은 `SUPERSEDED_NAMES` 로 남아 있다 (**D-278**).

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 프로브 8건 · PG 스택 실측(D-209~D-212) ·
  `VARCHAR(n)` 감사(D-214). **제품 코드 diff 0.**
- **S2 — PostgreSQL Foundation.** 70 표 · 256 인덱스가 `0001_pg_baseline` 하나로 선다.
  SQLite Runtime 의존 0 · `--workers 1→4`. 결정 **D-215~D-221**.
- **S3 — Product Identity · Hostname · TLS.** CN/SAN 일치 · `ssl_verify_result=0`.
  결정 **D-222~D-224**.
- **S4 — 설치 · 배포 자동화 Foundation.** Clean OS 에서 세 줄, 재부팅하면 스스로 복귀.
  결정 **D-225~D-229**.
- **S5 — Identity & Access.** 권한이 표가 되고 가시성이 함수 하나가 됐다. 결정 **D-230~D-235**.
- **S6 — Work Domain.** 티켓이 세 이름으로 불리고 그 셋이 같은 티켓을 가리킨다.
  결정 **D-236~D-243**.
- **S7 — Knowledge Domain (+P-14a).** 본문의 정본이 블록이 되고 그 블록에 이름이 붙었다.
  결정 **D-244~D-248**.
- **S8 — File Storage Providers.** 파일이 DB 밖에 살고, 그 자리가 진짜 그 저장소인지 매번 묻는다.
  결정 **D-249~D-253**.
- **S9 — AI Platform 1 (Gateway · Pipeline).** 모델이 계약 뒤로 들어가고 문서가 스스로
  색인된다. 결정 **D-254~D-259**.
- **S10 — AI Platform 2 (Retrieval · Citation · 생성).** 권한이 `LIMIT` 앞에 걸리고
  인용이 문단을 가리킨다. 결정 **D-260~D-264**.
- **S11 — n8n · 외부 Runner 제거.** 옛 AI 경로가 사라지고 채팅이 제품 안에서 답한다.
  결정 **D-265~D-268**, 원장 [`EVIDENCE/S11/`](EVIDENCE/S11/README.md).
- **S12 — Backup / Restore 운영.** 백업이 「되돌리면 앱이 돈다」를 증명한다.
  결정 **D-269~D-273**, 원장 [`EVIDENCE/S12/`](EVIDENCE/S12/README.md).
- **S13 — Migration Tool + Dry Run.** 위 두 절. 결정 **D-274~D-281**, 원장
  [`EVIDENCE/S13/`](EVIDENCE/S13/README.md).

## ⚠️ 옮길 수 있다는 것을 증명했고, **운영을 옮기지는 않았다**

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001`~`0011` 이 **94 표**를 만든다 (`0011` 은 `legacy_mapping` 하나) |
| **이관 도구** | **선다.** `app/migration/` + `python -m app.cli.migrate_cli`. Dry Run 과 Cutover 가 같은 코드를 부른다 — 다른 것은 `DATABASE_URL` 하나다 |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** Dry Run 은 임시 DB 로 갔고 운영 원본은 읽기만 했다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** 그 빌드의 채팅은 n8n 을 부르므로 답을 못 한다 — S11 이 만든 의도한 결과다. 설치 이전은 **S14** |

**S14 가 알아야 하는 것 아홉**:

1. **Dry Run 과 Cutover 는 같은 명령이다.** `DATABASE_URL` 이 임시 DB 를 가리키면 Dry Run,
   운영을 가리키면 Cutover 다. 도구가 모드에 따라 다르게 동작하면 Dry Run 이 증명한 것이
   Cutover 에서 성립하지 않는다.
2. **순서가 계약이다** (D-281): 표 복사 → 프로젝트(Notion) → **Project Key** → 티켓(Notion)
   → **재채번** → **채번 시드** → 관계 → 사용자 매핑 → 문서 → 첨부 → 다리 → 검증.
   Key 가 재채번보다 앞이고 시드가 재채번보다 뒤다. 바꾸면 조용히 틀린다.
3. **본문 재수집은 십 분 넘게 걸린다.** `extract --bodies` 로 캐시를 먼저 채워 두면
   Cutover 당일의 Delta 는 바뀐 것만 받는다(`last_edited` 기준).
4. 🔴 **적재 직후 파생 넷은 비어 있는 것이 정상이다**(D-270 · D-276). 색인 레인의 훑기와
   검색 색인 갱신이 채운다. 목록의 정본은 `app/backups/policy.py` 하나다.
5. **분류된 예외 14건은 사람이 결정할 목록이다** — 상위 작업 다중 6 · 사용자 미매핑 3 ·
   첨부 크기 초과 2 · 바깥 링크 1 · 소스에서 사라진 프로젝트 1 · 값이 한 번도 안 들어온
   속성 1. 티켓 예외 13건은 **그와 다른 것**이고 `migration_exceptions` 에 있다
   (`source_missing` 8 · `missing` 3 · `ambiguous` 2).
6. **첨부 둘은 제품 업로드 한도(10MB)를 넘는다** — 34MB 회의 녹음과 15MB PDF. 한도를
   넓힐지는 **제품 결정**이고 S13 의 범위가 아니었다(D-280).
7. **이관 전용 SSRF 목록(`config/allowed-migration-sources.json`)은 Cutover 이후 필요 없다**
   (D-279). 걷을 때 런타임 목록을 건드리지 않는다.
8. **`app/llm` 은 아직 산다.** 주간 리포트 요약이 그 경로를 쓴다 (S11 이 넘긴 것 그대로).
9. **옛 셸 백업 스크립트는 S14 가 걷는다.** `/etc/cron.d/clovirone-backups` 가 지금
   운영에서 실제로 돌고 있으므로, 지금 지우면 그 설치가 백업 없이 남는다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **설치까지 끝났다.** `0011` 까지 94 표 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ · S4 ✅ · S9~S13 ✅ |
| **SQLite 제거** | **Runtime 의존 0 이고 이관 도구가 선다.** 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ · S7 ✅ · S13 ✅ → **S14** |
| **Notion Migration** | **Dry Run 이 끝났다.** 티켓 1,133 · 문서 110 · 본문·분류·첨부·관계까지 실제로 건너갔고 재실행이 멱등이다. 남은 것은 **운영에 적용하는 것** | Notion Runtime 의존 0, 데이터는 PG 로 | S13 ✅ → **S14** |
| **AI** | ✅ **끝났다.** | Model Gateway + 권한이 앞서는 Retrieval + 옛 경로 0 | S9 ✅ · S10 ✅ · S11 ✅ |
| **Backup** | ✅ **끝났다.** | Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ · S4 ✅ · S8 ✅ · S12 ✅ |

**Identity 축은 닫혔다** — 호스트명·TLS 는 S3, slug 는 S4, 역할·권한·가시성은 S5.
**남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고 S14 다 (`BACKLOG.md` **P-33**).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

| 대상 | 결과 |
|---|---|
| 🔴 **Migration Dry Run (실 운영 SQLite + 실 Notion → 임시 PG)** | **검사 64건 전부 통과.** 티켓 1,133 · 문서 110 · 판 110 · 관계 121 · 첨부 6 · `legacy_mapping` 1,372. 원장 [`EVIDENCE/S13/`](EVIDENCE/S13/README.md) |
| 🔴 **재실행 (같은 DB · 같은 도구)** | **신규 0.** `counts` 가 1회차와 동일하고 판이 안 쌓였다 |
| 검증기 자기검증 (regression) | **17건.** Known Good · 자리마다 Known Bad 12 · 반례 3. 실 DB 를 하나씩 망가뜨려 **그 항이** 실패하는지 본다 — 누락·번호와 이름의 어긋남·사유 없는 무번호·낡은 예외·깨진 관계·판 없는 문서·파생 표의 행·**Notion 임시 주소**·뒤처진 카운터·고아 별칭·충돌·사라진 예약 Key. 「검사가 하나도 없는 보고서는 통과가 아니다」도 함께 |
| 이관 파이프라인 (integration · real_db) | **15건.** 세 층의 이름 · 예외 분류 · 채번 시드 · 본문 Block JSON · **분류(유형→`doc_type` · 카테고리→태그 · 작성자)** · 첨부(호스트/바깥링크) · 다리 · 사용자 매핑 · **재실행 신규 0** · 파생 넷 공백 · 길이 초과 반례 |
| 계획·변환·값 (unit) | **57건.** 소스 75 표가 넷으로 전부 갈리는가(+모르는 표 반례) · 타입별 변환이 **틀린 쪽으로도** 움직이는가 · Notion 속성 파싱 · 블록 → Block JSON · 재채번 멱등 |
| 이관 경계 (security) | **5건.** 런타임 SSRF 목록이 **안 넓어졌는가**(정확한 내용 단언) · 이관 목록이 좁은가 · 목록 밖 주소 거절(반례 둘) · 보고서에 토큰이 안 실리는가 · 대상 주소에서 비밀번호가 빠지는가 |
| 재실행 결함 고정 (regression) | **8건.** 뒤 단계가 주인인 컬럼 목록 · `DROPPED_COLUMNS` 와 안 섞이는가(양방향) · 첨부 크기 한도의 주인이 하나인가 |
| 백엔드 전 회귀 (PostgreSQL) | `scripts/run_full_regression.sh` — unit · regression · security · integration 청크 4개 = **7통 전부 초록** (`FULL_REGRESSION_OK`, 38분 26초) |
| 마이그레이션 왕복 | `0011` 을 실 PG 에서 `upgrade`→`downgrade`→`upgrade`. 대칭이고 autogenerate diff **0** |
| `static_checks.sh` | S13 이 만든 실패 **0**. 남은 셋은 전부 P-09a 소유(가운뎃점·em 대시 6 · subprocess encoding · `tokens.css` 드리프트) — S11·S12 시점과 같다 |
| 프런트 | **안 건드렸다.** 번들 재생성 불필요 |

## NOW

**S13 은 끝났다.** 옛 데이터가 새 스키마로 **전부** 건너가고, 두 번 돌려도 같다.

이 세션에서 가장 값이 나간 것은 파이프라인을 쓴 것이 아니라 **두 번 돌린 것**이다.
1회차는 초록이었고 2회차가 죽었다 — 표 복사와 재채번이 같은 컬럼의 주인이었기 때문이다.
그리고 같은 결함이 `projects.code` 에도 있었는데 **그쪽은 오류를 안 낸다**: 재실행이 확정
Project Key 를 조용히 지운다. 한 번만 돌리는 도구였으면 둘 다 Cutover 당일에 처음 보였다.

두 번째는 **속성 이름을 다시 잰 것**이다. 「문서 분류 110건이 전부 비어 있다」는 사실이
INVENTORY 에 반년 가까이 적혀 있었고 원인은 아무도 몰랐다. Notion 은 이름이 틀려도 오류를
내지 않는다 — 그냥 그 키가 없는 응답을 준다. 이름을 맞히는 것으로 끝내지 않고 **「한 번도
값을 안 낸 속성」을 세게** 만든 것이 이 자리의 진짜 산출물이다.

세 번째는 **확정된 것도 소스가 바뀌면 안 맞는다**는 것이다. 하루 전에 사용자가 확인한
Key 표의 이름 20건이 전부 «못 찾음» 이었다. Key 는 안 바꾸고 이름만 갈되, 짝은 이름이
아니라 티켓 수로 확인했다.

## NEXT — 다음 시작점: S14 (요청 시)

**S14 = Cutover + Legacy 제거 (단독).** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §7.5 · §9.1, Backlog 는 **P-24·P-33**.

S13 이 다음 Session 에게 넘기는 것은 위 「S14 가 알아야 하는 것 아홉」이다. 그중 셋을
다시 적는다:

1. **Cutover 직전에 백업 → 리허설을 한 번 돌려라.** S12 가 그 도구를 세워 뒀고, 지금은
   운영 표가 거의 비어 있어 복원이 싸다.
2. **적재 뒤 파생 넷이 비어 있는 것을 확인하라.** 거기 행이 있으면 이관이 백업 정책과
   다른 목록을 쓴 것이고, 그 사실은 첫 복구 리허설 5단계에서 터진다.
3. **분류된 예외 14건 + 티켓 예외 13건은 사람이 하나씩 정할 목록이다.** 서비스 Open 을
   막지 않는다 — 소속 없는 티켓은 fail-closed 로 전역 관리자에게만 보인다(의도한 동작).

## RISK — 지금 살아 있는 것

전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12.

| # | Risk | 상태 / Owner |
|---|---|---|
| ~~R1~~ ~~R2~~ ~~R3~~ | (S2 가 닫음) | 해소 |
| ~~R4~~ ~~R5~~ ~~R6~~ ~~R7~~ | (S1 이 닫음) | 해소 |
| ~~R8~~ | Notion 본문 재수집 중 rate limit / 원본 변경 | **해소 (S13)** — `last_edited` delta + 재실행 신규 0 |
| ~~R9~~ | 러너 6,395줄 중 무엇이 이관 대상인가 | **해소 (S11)** — 이관 대상은 없었다 |
| ~~R13~~ ~~R14~~ | 제품 slug · 설치 자동화 | 해소 (계약 이행은 매 Session 이 계속 진다) |
| ~~R15~~ | LXD 컨테이너가 실 장비와 다르다 | **해소** — 재부팅 축은 S4(D-229), Storage 축은 S8 |
| ~~R17~~ | pgvector 검색 품질 | **해소 (S10)** — MRR@10 0.7553 → **0.8869**(D-260) |
| R11 | **시험 Storage 가 실 NAS 와 다르다** | **살아 있다(의도한 대로)** — 실 정보 수령 시 **설정만** 바꾼다 |
| R16 | GitLab 주소 부재 | **완화** — Installer 가 Remote 중립이다 |
| — | **검색 품질을 업무 기록으로는 아직 못 쟀다** | **다시 잴 수 있게 됐다** — Dry Run DB 에 본문이 들어왔다(티켓 613 · 문서 103). 재는 자리는 Cutover 이후다(D-262) |
| — | **저장소 장애 중 쓰기가 21초~180초 이상 걸린다** | **알려진 성질**(D-251) |
| — | **색인 레인이 안 뜨면 검색 결과가 조용히 낡는다** | **완화** — `ALWAYS_ACTIVE_UNITS` 에 있어 재부팅 판정과 Stage 17 이 본다 |
| — | **리허설을 아무도 안 돌리면 S12 의 증명이 낡는다** | **살아 있다** — 관리 콘솔의 복구 리허설 화면이 「마지막으로 언제」에 답한다 |
| — | **Notion 속성 이름이 또 바뀔 수 있다** | **완화 (S13)** — 앞뒤 공백을 무시하고 찾고, **한 번도 값을 안 낸 속성을 보고서가 말한다**(D-277) |
| — | **운영 데이터가 아직 SQLite 에 있고, 운영 서버는 아직 옛 slug 설치다** | **S14** |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **20개 Project Key 명명** | **확정됐고 적용된다.** 정본은 `app/work/project_keys.py::CONFIRMED`, 사람이 읽는 사본은 [`PROJECT_KEYS.md`](PROJECT_KEYS.md). 🔴 **이름은 2026-08-23 에 갈았다** — 소스가 접두사를 뺐다. **Key 는 안 바꿨다**(D-278). Key 가 없는 프로젝트 둘(`S협회 …` 활성 · `M. 고려대학교 …` 보관)은 확정이 20건이므로 정상이다 |
| **S13 이관 하네스** | 서버의 `~/s13`: `work/legacy.sqlite3`(운영 무중단 스냅숏) · `src/`(그때의 소스 사본) · `cache/`(Notion 추출 1,235페이지) · `out/`(보고서). 임시 DB 는 `~/s1pg` 안의 `clovir_s13` 이고 **지우면 다시 만들면 된다** |
| **이관을 돌릴 때** | `SECRETS_DIR=/etc/clovirone-web-assistant/secrets` 를 주고 **sudo 로** 돌린다 — 토큰을 다른 자리에 복사하지 않는다. `~/s1pg` 는 소켓이라 `DATABASE_URL` 에 `?host=…/sock&port=55432` 와 `user=cloviradmin` 이 필요하다(sudo 면 OS 사용자가 root 다) |
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore) |
| **테스트 서버의 PostgreSQL** | **사용자 공간 PG** `~/s1pg`(16.15 · 포트 55432 · 유닉스 소켓 · `pgvector` 0.6 + `pg_trgm` 1.6). `. ~/s1pg/env.sh` 뒤 `pg_ctl … start` |
| **S12 리허설 하네스** | 서버의 `~/s12rehearsal`. 원본 DB `s12src` 는 남겨 뒀다 |
| **n8n 을 되살려야 한다면** | `/var/backups/n8n-s11/` 에 스냅숏 · 유닛 · `/etc` · `/opt` 원본이 `SHA256SUMS` 와 함께 있다 |
| **서버에 3.4GB 가 「치워 둔」 채로 있다** | `/var/backups/n8n-s11`(2.7G) + `/var/lib/n8n.removed-s11`(738M). 그 서버는 1006G 중 38G(4%)만 쓴다 — **회수를 서두를 이유가 없고** 지우는 것은 되돌릴 수 없으므로 사람이 정할 일이다 |
| **임베딩 모델 파일** | **테스트 서버에 셋 다 있다** — `~/s1bench/models/`. 설치는 `deploy/install.sh ai --ai-model-dir <디렉터리>` 이고 **네트워크로 안 받는다**(D-259) |
| **S9·S10 검증 하네스** | 서버의 `~/s9verify` · `~/s10bench`. 이관도 `~/s9verify/venv` 를 썼다 |
| **테스트 서버의 시험 Storage** | **세워 뒀다** — NFS `/srv/clv-nfs-export` · Samba `/srv/clv-smb-share` · 마운트 `/mnt/clv-nfs`·`/mnt/clv-smb` · 시험 계정 `clvsvc`. SMB 자격증명은 `/etc/clovirassist/secrets/smb_matrix`(0600, root) |
| **LXD** | 초기화해 뒀다. **`/dev/kvm` 이 없어 LXD VM 은 못 쓴다** |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. 옛 이름은 DNS 에 없다(NXDOMAIN) |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore). **네 파일은 같은 값이다**(INVENTORY 07) |
| **Notion 데이터베이스 id** | **저장소에 안 적는다.** 이관 도구가 `/v1/search` 로 **제목으로 찾고**, 못 찾으면 멈춘다 — 옛 설정의 id 는 틀려 있었다(INVENTORY 07). 이름이 바뀌면 `--database role=id` 로 준다 |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433 · `pgvector/pgvector:pg16`). `CLOVIR_TEST_PG_URL` 로 덮어쓴다 |
| **전 회귀를 돌릴 때** | **`scripts/run_full_regression.sh` 를 쓴다.** `pytest tests` 를 백그라운드로 직접 돌리면 14% 근처에서 **CPU 0 으로 멈춘다**(P-09e) |
| **회귀 결과를 읽을 때** | **파이프 뒤에서 읽지 않는다.** `pytest … \| grep …` 의 `$?` 는 grep 의 종료코드다. 결과는 **파일로 받는다** |
| **`TestClient` 로 로그인 경로를 태울 때** | 🔴 **`base_url` 을 `https://` 로 준다.** 세션 쿠키가 `Secure` 라 `http://` 로는 안 실린다 |
| **파이썬으로 파일을 다시 쓸 때** | `Path.write_text` 는 윈도에서 `\n` 을 **CRLF 로 바꾼다.** 배포 자산이 그렇게 되면 리눅스에서 죽는다 — `newline=""` 을 준다 |
| **프런트를 고쳤을 때** | `cd frontend && npm run build` → `python scripts/check_bundle_fresh.py --write` |
| **원격에서 오래 걸리는 명령을 돌릴 때** | **시간 제한을 건다.** 걸린 하네스는 결과를 한 줄도 안 낸다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다.** 실 왕복은 테스트 서버의 `~/s1pg` 에서 잰다 |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 실 정보를 받으면 `storage_providers` 행의 `source`·`options` 만 바꾸고 `deploy/install.sh storage` 를 다시 돌린다 (U8·U9) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19). **셋 다 지금도 워크스페이스에 있다** — 이관 보고서가 그 사실을 적는다 |
| GitLab Repository 주소·자격증명 | Installer 가 Remote 중립이라 **주소가 정해지면 설정만 바꾼다** (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
