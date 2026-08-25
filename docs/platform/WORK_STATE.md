# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-25** (S18)
- phase: **E — UI Renewal 재개.** S18 이 W8 Pilot 의 **기능 축**을 닫았고 다음은 S19~S20
- session: **S18 기능 축 완료 · 시각·반응형 축 미측정.** 다음은 **S19 — 나머지 User Route (요청 시)**.
  S18 이 남긴 잔여는 **P-44**(S19 소유)
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S18 도 옮기지 않는다.** 이유는 S11~S17 과 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- s18_commit: **`f1968a09`** — S18 본체(문서·원장·하네스·화면·시험)
- deployed: **S15~S17 이 운영에 나갔다. S18 은 아직 안 나갔다** (2026-08-25 04:13, `install.sh upgrade --source local`).
  Stage 0~18 전부 OK · `VERIFY_OK` · 스냅샷 `/var/backups/clovirassist/20260825-041314`.
  `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  배포본 번들 지문 `39187bca03b30bc3` 가 빌드한 것과 같다. 스모크 6화면(홈·내 티켓·티켓 상세·
  게시판·문서·채팅방)에서 **콘솔 오류 0 · 페이지 오류 0**. 되돌리려면
  `sudo /opt/clovirassist/deploy/install.sh rollback --target /var/backups/clovirassist/20260825-041314`
- ui_gate: `--stage plan` **PASS** · `--stage wave`(**W8**) **FAILED (274건)**. S18 이 UI 축의
  CHECKPOINT 를 W8 로 올렸다. 실패 274건은 셋 다 **기록 형식**이고 화면 결함이 아니다 —
  ① 사슬의 서버 칸 243건(하네스가 `/openapi.json` 으로 핸들러 표를 만드는데 이 제품은 그
  경로를 안 연다) ② 조건 다섯 축이 아직 없는 화면 24건 ③ 화면 사슬 칸이 빈 Flow 7건.
  전부 **P-44** 다. `capture_labels.after` 는 `s17-after` 그대로다 — S18 이 캡처를 다시 안 찍었다.
  억제 하나는 칸반 레인의 균등 격자다(SUP-01, 만료 2026-10-20).
  그쪽 상세는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **93 표**다. alembic head 는 `0016_document_axis_to_documents` 다. S18 도 스키마를
  안 건드렸다(프런트·백엔드 읽기 경로·QA 하네스·문서만)
- pilot: **258 Flow 중 252 PASS / 6 FAIL** (`dist/ui-qa/pilot/flows.json`). 실브라우저가
  조용한 결함 넷을 잡아 고쳤다 — `/me` 500(**D-302**) · 티켓 댓글 알림이 `NameError` 로
  통째로 죽어 담당자에게 한 건도 안 가던 것 · 조건이 붙은 주소가 그 조건을 잃던 것(**D-304**) ·
  QA 씨앗이 제품에 없는 상태 낱말을 심던 것. 결정 **D-299~D-305**

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
데이터는 전부 넘어갔고 서비스는 열려 있다. 원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).

| | |
|---|---|
| 사용자 · 프로젝트 · 티켓 | 25 · 22 · **1,140**(컷오버 뒤 실사용자가 새로 만든 7건 포함) |
| 프로젝트 코드 | **22 / 22.** S13 에서 확정표에 없어 못 받던 둘도 받았다 |
| 문서 · 판 · 태그 · 문서 첨부 | 110 · 166 · 106(19종) · 54 |
| 티켓 댓글 · 티켓 첨부 | 336(이관 첫 회차가 0건 옮겼던 324건을 재이관이 채웠다) · 236 |
| 옛 이름 층 | **없다** — `tickets.legacy_key` · `ticket_key_aliases` · `project_key_registry` 를 `0012` 가 내렸다 |
| Notion 런타임 | **없다.** 모듈 열다섯을 지웠고, 런타임 SSRF 목록에 `api.notion.com` 이 **없다** |
| SQLite 런타임 | 없다. 옛 파일은 `/var/lib/clovirassist/web.sqlite3` 에 남아 있지만 제품이 못 연다 |

## S18 이 실제로 한 것

이번 회차가 답한 질문은 둘이다 — **원장이 제품과 같은 것을 말하는가**, 그리고 **한 화면이
200 을 받았다고 완료인가.**

### 1. 🔴 원장에는 있는데 제품에는 없는 화면이 셋 있었다 (D-299)

W0 이 세운 커버리지 조건 C1 은 «소스에 있는 화면이 원장에 있는가» 한 방향만 본다. 반대쪽은
아무 검사도 안 건드렸고, 그래서 **열리지도 않는 화면 셋**이 「아직 안 본 화면」으로 남아 다음
회차를 기다리고 있었다(`/team-docs/:pageId` · `/notion-console` · 설정 › 연동 탭). 나쁜 점은
「하나 빠뜨렸다」가 아니다 — 다음 회차가 **없는 화면을 감사하려 들거나**, 더 나쁘게는 그것을
`PASS` 로 적게 된다는 것이다.

반대 방향 조건(**C1c**)을 세웠다: 원장의 각 행이 가리키는 컴포넌트 파일 · 탭 키 · 리다이렉트
대상이 소스에 실재하는지 본다. 없어진 화면의 상태는 **`RETIRED`** 다 — 「안 봤다」와 「없다」를
같은 칸에 적으면 안 된다. 행은 지우지 않는다(Before 캡처와 Requirement Matrix 가 그 id 를
가리킨다). 반례 17건이 그 판정을 양방향으로 지킨다.

### 2. Pilot 17 화면의 Flow 258건을 실브라우저에서 눌렀다 — 252 PASS / 6 FAIL

Flow 를 문서가 아니라 **코드**로 세웠다(`scripts/ui_qa/pilot_*.py`). 각 Flow 는 무엇을 눌렀고,
어떤 요청이 나갔고, 무엇이 그려졌는지를 함께 남긴다. 두 규칙을 새로 못 박았다:

* **서버를 안 부르는 것이 정답인 동작은 그렇다고 선언한다**(**D-300**). 모달을 열고 닫는 것,
  필수값이 빈 채 제출이 막히는 것에 서버 칸을 요구하면 답이 둘뿐이다 — 사슬을 지어내거나,
  영원히 미완으로 두거나. 이제 사유를 적으면 화면 사슬 셋을 대신 요구한다.
* **쓰기 Flow 는 다른 화면에서 그 값을 다시 찾는다**(**D-301**). 29건에 배선했다 — 티켓 편집은
  `/my-tickets` 의 그 행에서, 게시글 삭제는 목록에서 사라졌는지로, 설정 초안은 **새로 읽어도
  안 들어가 있는지**로 확인한다.

### 3. 🔴 실브라우저가 조용한 결함 넷을 잡았다

전부 오류를 안 내는 종류다.

* **`/me` 가 옛 Health 스냅샷을 만나면 500 이었다**(**D-302**). 사유 칸이 옛 행에서는 리스트,
  새 행에서는 객체인데 읽는 자리가 둘이었고 한쪽만 객체를 알았다. 파서를 하나로 합쳤다.
* **티켓 댓글 알림이 통째로 죽어 있었다.** `_notify_ticket_comment` 안에서 `split_names` 가
  임포트되지 않아 `NameError` 가 났고, 그 함수는 자기 실패를 삼키도록 설계돼 있다 — 댓글은
  전부 정상 저장되고 응답은 200 이라 **응답을 보는 어떤 시험도 이것을 못 본다.** 담당자에게는
  알림이 한 건도 안 갔다.
* **조건이 붙은 주소가 그 조건을 잃었다**(**D-304**). `onQuery` 를 가진 목록 화면이 딥링크
  쿼리를 청소하면서 **쿼리 전체**를 지웠다 — `#/jobs?status=succeeded` 로 들어오면 조건이
  주소에서 사라져 링크 공유도 뒤로가기도 깨졌다. 이제 남의 의도 키만 지운다.
* **QA 씨앗이 제품에 없는 상태 낱말을 심고 있었다**(`done`, 제품은 `succeeded`). 그래서 운영
  콘솔의 «완료» 조건이 언제나 0건이었고 그 0건이 화면 결함처럼 보였다.

그리고 분할 뷰의 중복 조건 입구를 내렸으며(**D-303**), 티켓 상세의 가장 큰 공백이던 **활동
이력**을 권한과 «바뀐 칸» 으로 좁혀 열었다(**D-305**).

### 4. 남긴 것

**캡처를 다시 찍지 않았다.** 그래서 17 화면은 `IN_PROGRESS` 이고 게이트 `--stage wave`(W8)는
**기록 형식 274건**으로 실패한다 — 사슬의 서버 칸 243건(하네스가 `/openapi.json` 으로 핸들러
표를 만드는데 이 제품은 그 경로를 안 연다) · 조건 다섯 축이 아직 없는 화면 24건 · 화면 사슬 칸이
빈 Flow 7건. 실패 6건과 함께 **P-44**(S19 소유)로 등록했다.

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
- **S6 — Work Domain.** 티켓에 번호가 붙고 그 번호가 영원히 같은 티켓을 가리킨다.
  결정 **D-236~D-243**(그중 Key 정책은 S14 가 대체했다).
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
- **S13 — Migration Tool + Dry Run.** 옛 데이터가 새 스키마로 전부 건너가고 두 번 돌려도 같다.
  결정 **D-274~D-281**, 원장 [`EVIDENCE/S13/`](EVIDENCE/S13/README.md).
- **S14 — Cutover + Legacy 제거.** 위 절. 결정 **D-282~D-284**, 원장
  [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).
- **S15 — Search/Filter 기능 정확성.** 조건이 맞는지를 **두 구현의 대조**로 봤다 — 결함 여섯을
  뿌리에서 고쳤고 전부 오류를 안 내는 종류였다. 결정 **D-285~D-287**.
- **S16 — Table / Grid / Metadata / Alignment + Chart.** 열이 폭 대신 의미를 말한다.
  `numeric_alignment` 8건이 0 이 됐다. 결정 **D-288~D-293**.
- **S17 — Empty / Loading / Error / Feedback + Clovi + Detail Metadata.** 위 절.
  결정 **D-294~D-298**.

## 상태 — 전환 축 다섯

| 축 | 현재 | 소유 Session |
|---|---|---|
| **PostgreSQL** | ✅ **System of Record 다.** 운영이 그 위에서 돈다 | S2 ✅ · S4 ✅ · S9~S14 ✅ |
| **SQLite 제거** | ✅ **끝났다.** Runtime 의존 0 이고 데이터도 전부 넘어갔다 | S13 ✅ · S14 ✅ |
| **Notion Migration** | ✅ 런타임은 끝났다. **화면에는 잔재가 남아 있다**(P-41, S20) | S13 ✅ · S14 ✅ |
| **AI** | ✅ 끝났다 | S9 ✅ · S10 ✅ · S11 ✅ |
| **Backup** | ✅ 끝났다 — 그리고 S14 가 **실 데이터로 다시 증명**했다 | S2 ✅ · S4 ✅ · S8 ✅ · S12 ✅ · S14 ✅ |

**Identity 축도 닫혔다** — 호스트명·TLS(S3) · slug(S4) · 역할·권한(S5), 그리고 마지막 한 건인
세션 쿠키 이름을 S14 가 갈았다(P-33).

**UI 축은 W7 까지 왔다.** 근거와 수치는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이었고 재개는 Phase E(S15~S20)다 (D-207).

## NEXT — 다음 시작점: S19 (요청 시)

**S19 = 나머지 User Route.**
사용자 요청 없이 착수하지 않는다. 범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1,
Backlog 는 **P-29**. **S18 이 남긴 잔여는 P-44 이고 소유가 S19 다.**

S18 이 다음 Session 에게 넘기는 것 다섯:

1. **Flow 표가 코드로 서 있다.** `scripts/ui_qa/pilot_kit.py`(공용 조작) ·
   `pilot_b*.py`(화면별 258 Flow) · `pilot_e2e.py`(실행기) · `pilot_record.py`(원장 기록).
   새 화면은 `flow(...)` 한 줄과 `act` 하나면 되고, 결과는 `pilot_record` 가 옮겨 적는다.
2. **조건 다섯 축이 부품이다** — `compound` · `page_reset` · `no_page_axis` · `race` ·
   `cache_key` · `back_forward`. 쪽이 없는 화면은 «초기화할 쪽이 없다» 가 정답이고 그 사실을
   주소로 확인한다.
3. **원장은 두 방향으로 대조된다**(C1c). 화면이 제품에서 없어지면 행을 지우지 말고
   `RETIRED` 로 적는다 — Before 캡처와 Requirement Matrix 가 그 id 를 가리킨다.
4. **W8 의 시각·반응형 축이 열려 있다.** `--label s18-after` 로 12 Route 를 찍고
   `pilot_record --capture s18-after` 로 기록하면 17 화면이 `DONE` 후보가 된다(**P-44**).
5. **범위 밖으로 넘긴 것 다섯**: 시험 강도 선언 미비(**P-38**) · 백엔드 회귀 넷(**P-39**) ·
   화면에 남은 Notion 잔재(**P-41**, S20) · `/dev-report` 의 빈 판(**P-42**, S20) ·
   값이 0 인 날의 판독값(**P-43**, S22).
