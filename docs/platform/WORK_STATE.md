# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-25** (Health Correction · S19 뒤)
- phase: **E — UI Renewal 재개.** S19 가 W10 화면의 **제품 결함**을 닫았고 다음은 S20
- session: **일회성 Product / Code / QA Health Correction 완료.** S1~S19 산출물 전체를
  독립적으로 훑어 실제 결함 넷과 구조 문제 셋을 고쳤고, QA 때문에 왜곡돼 있던 자리를
  바로잡았다. 🔴 **완료 계약을 둘로 갈랐다**(D-314) — 일반 Implementation 의 Exit 에서
  Coverage·Flow·Pilot·Capture·Evidence 를 뺐다. 그래서 S19 는 ✅ 다. **원장은 안 달랬다**:
  W10 20 행은 `NOT_AUDITED` 그대로이고 Flow 감사는 P-29, 캡처는 P-44 로 **Acceptance
  (S21·S22)** 가 소유한다. 다음은 **S20 — 관리자 IA + 관리자 콘솔 (요청 시)**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S18 도 옮기지 않는다.** 이유는 S11~S17 과 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- s18_commit: **`f1968a09`** — S18 본체(문서·원장·하네스·화면·시험)
- s19_commit: **`ee2e4118`** — S19 본체(화면·공용 부품·문서). **원장은 한 행만 바뀌었다**
  (`user_my-display` → 별칭). 나머지 W10 행은 `NOT_AUDITED` 그대로다
- hc_commit: **`2c3e6c60`** — 아래 「Health Correction 이 한 것」 절. 제품 결함 넷 · 구조 정리 셋 · QA 정리 ·
  `verify.py` 윈도우 실행기 · 완료 계약 분리(D-313~D-315)
- deployed: **S15~S17 이 운영에 나갔다. S18 은 아직 안 나갔다** (2026-08-25 04:13, `install.sh upgrade --source local`).
  Stage 0~18 전부 OK · `VERIFY_OK` · 스냅샷 `/var/backups/clovirassist/20260825-041314`.
  `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  배포본 번들 지문 `39187bca03b30bc3` 가 빌드한 것과 같다. 스모크 6화면(홈·내 티켓·티켓 상세·
  게시판·문서·채팅방)에서 **콘솔 오류 0 · 페이지 오류 0**. 되돌리려면
  `sudo /opt/clovirassist/deploy/install.sh rollback --target /var/backups/clovirassist/20260825-041314`
- full_snapshot: **HC 마지막 Full 1회** (`python scripts/verify.py --full`, 2026-08-25 17:29~18:13).
  정적 전량 **PASS** · 프런트 전량 **329 파일 / 2,451건 전부 PASS**(S19 가 남긴 8건이 0 이 됐다) ·
  백엔드 전량 **FAIL 7건** — 전부 `test_api_contract_golden.py` 이고 **HEAD 에서도 같은 7건**이
  뜬다(HC 는 백엔드 소스를 한 줄도 안 고쳤다). **P-51** 로 등록했다
- ui_gate: `--stage plan` **PASS**(HC 도 확인). `--stage wave` 는 S19 도 HC 도 **안 돌렸다** —
  W8 잔여(P-44)를 여는 일이고, 그것은 이제 **Acceptance 축**이다(§9.4). 아래는 **S18 이
  남긴 그대로**다.
  `--stage wave`(**W8**) **FAILED (274건)**. S18 이 UI 축의
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

## Health Correction 이 한 것 (일회성 · S20 아님)

S1~S19 산출물 **전체**를 독립적으로 훑었다. 물은 것은 하나다 — **QA 를 만족시키려고 제품이
이상해진 자리가 어디인가.**

### 1. 🔴 완료 계약이 두 축을 한 Exit 에 묶고 있었다 (D-314)

S19 의 Exit 는 「각 화면 Functional Flow 가 최소 `IN_PROGRESS`」였다. 그 회차가 한 일은
**제품 결함을 뿌리에서 고친 것**인데 Exit 는 **감사 원장의 상태**를 요구해서 「미충족」으로
닫혔다. 그 묶음은 양방향으로 해롭다: 한 줄 import 를 고치는 일이 20 화면 감사를 통과해야
끝나거나(그래서 아무도 작은 결함을 안 고친다 — `PATH_SEP` 한 줄이 실제로 회차 하나를
건너뛰었다), 아니면 Flow·Capture 가 「회차가 지나가며 채우는 칸」이 된다(그 순간 원장은
«제품을 봤다» 가 아니라 «회차가 지나갔다» 를 뜻한다).

계약을 둘로 갈랐다(`MASTER_PLAN.md` §9.4 · `CLAUDE.md` §7.0). **Implementation** 은 구현 →
표적 시험 → 결함 수정 → 영향 범위 재검증 → 문서 → Commit 이고, Coverage·Flow·Pilot·
Capture·Evidence·전체 Route Coverage·unrelated 기존 실패는 **완료 실패 사유가 아니다**.
**Acceptance**(S21·S22)가 그 다섯을 소유한다. **원장은 안 달랬다** — W10 20 행은
`NOT_AUDITED` 그대로다. 「안 봤다」와 「없다」와 「봤고 통과했다」는 서로 다른 세 사실이고,
회차가 지나갔다는 사실은 그 셋 중 어느 것도 아니다.

### 2. 🔴 무효화 표가 **없는 키**를 가리키고 있었다 (D-313)

`document-views.js` 는 「문서를 고친 뒤 무엇을 다시 부르는가」를 적은 표다. 그 표가 든 것은
`["team-docs"]`·`["team-doc"]` — S14 가 문서 축을 정본으로 옮기면서 화면 키가
`["knowledge", …]` 로 바뀌었는데 표가 안 따라왔다. `invalidateQueries` 는 **없는 키를 지워도
오류가 아니다.** 그래서 휴지통에서 문서를 복원·영구 삭제하면 무효화가 매번 돌고 매번
아무것도 안 지웠다: 복원한 문서가 `staleTime`(30초) 동안 `/knowledge` 에 안 나타나고, 영구
삭제한 문서의 상세는 그동안 멀쩡히 열린다.

🔴 **그것을 재던 시험도 같은 옛 키를 보고 있었다.** `trash-doc-detail-invalidation.test.jsx`
가 `["team-doc", id]` 를 **스스로 심고** 그 키의 무효화를 물어서, 제품이 실제 문서 캐시를
하나도 안 지우는 동안 세 사례가 전부 초록이었다. 시험이 계약이 아니라 사라진 구현 세부를
고정하면 그 시험은 결함을 못 본다. 화면이 실제로 쓰는 키(상세·목록 둘)를 심게 고쳤고,
옛 키로 되돌려 **3건이 전부 빨개지는 것**을 확인한 뒤 복구했다.

### 3. 나머지 제품 결함 셋

* **`PATH_SEP` 미임포트로 티켓 상세의 공유 범위 판이 죽었다**(P-45). 한 줄 import 로 달래지
  않고 뿌리로 고쳤다 — 경로 문자열은 `ui/OrgPath.jsx::pathText` 하나가 만든다. 같은 세 줄을
  손으로 다시 쓰던 자리 둘(`ScopeBar.jsx` 의 지역 사본, `UserMenu.jsx`)도 그 함수로 모았다.
* **시간 레일이 선언만 있고 안 그려졌다**(P-49). `TicketHistory.jsx` 의
  `borderInlineStartColor: "divider"` — 논리 이름에는 MUI 가 팔레트 경로를 안 풀어 준다.
* **열 이름이 표준 동사표와 어긋났다**(P-46). `created_at` 열을 registry 9곳은 「추가」로
  부르는데 `MyTickets`·`Projects` 만 「생성」이었다. 그리고 화면 문구 하나에 남아 있던
  가운뎃점(`registry/org.js`)을 걷었다.

### 4. QA 자산 — 두 벌이던 것을 한 벌로

* **같은 계약을 두 계층이 각자 들고 있었다.** UX Writing 두 규칙(쉼표 이어붙이기·표준
  동사표)이 `static_checks.sh` 의 bash grep 과 vitest 두 곳에 있었고 허용 목록이 **실제로
  갈라졌다** — 「이 조건 지우기」가 bash 에만 있어 vitest 만 빨간 채였다(P-46). bash 사본을
  걷고 vitest 를 정본으로 삼았다(`static_checks.sh` 가 그 파일을 직접 돌린다). 원래 정본이던
  `docs/UX_WRITING.md` 는 `2b2bc9e7` 에서 이미 걷혀 있었다.
* **`verify.py` 안의 죽은 정책 두 개**(`needs_coverage_plan`·`needs_test_strength`)를 걷었다 —
  아무도 안 부르고 같은 판정이 `static_checks.sh` 에 이미 있었다. 두 벌이면 한쪽만 고쳐진다.
* **`filter-chain-contract` 3건은 제품 결함이 아니었다**(P-47). 상태 조건은 다중 선택이고
  MUI 의 다중 Select 는 항목을 눌러도 메뉴를 안 닫는다 — 그게 정답이다. 메뉴가 떠 있는 동안
  나머지 화면이 `aria-hidden` 이라 뒤 단언이 전부 못 찾았다. 시험 도우미가 단일 선택 시절
  그대로였고, 응답 흉내도 `get("status")`(첫 값)만 읽어 「진행」과 「진행+완료」를 같은
  글자로 만들고 있었다. 둘 다 고쳐 다중 값 축이 실제로 눌리게 했다.
* **백엔드 회귀 넷도 같은 뿌리였다**(P-39). 전부 S14 의 축 이동(`notion_page_id` →
  `document_id`)을 시험이 안 따라온 것이다. 셋은 옮겨 간 이름을 확인하고 선언했고, 하나는
  **다시 썼다** — 「옛 컬럼이 있는가」라는 물음의 사유(휴지통 중복 방지 키)는 휴지통에만
  해당하는데 즐겨찾기·최근 열람까지 함께 묻고 있었다. 지키려던 성질을 구조가 아니라
  **동작**으로 보게 하고 반례를 붙였다. 🔴 넷이 빨간 동안 **진짜 누락이 생겨도 같은 빨강에
  묻혔다.**
* **시험 강도 원장을 사실로 닫았다**(P-38, 15건). S13·S14 가 남긴 채 계속 빨갛던 게이트다.
  삭제 아홉은 계약이 **어디로 갔는지 파일마다 확인하고** 대체를 명명했고, 단언이 줄어든
  여섯은 사유를 적었다(전부 S14 의 축 이동이고 옮겨 간 자리에 같은 판정이 있다). 대체가
  **정말 없던 것 하나**(일괄 삭제 확인)는 계약이 살아 있는 화면에서 시험을 새로 썼다.
  이제 초록이므로 **다음 약화를 실제로 잡는다.**
* **S19 이 남긴 QA 넷은 유지한다** — `optical_alignment` assertion 과 D-307 은 반례 다섯으로
  양방향 검증돼 있고 `--fail-on` 기본에 없다. `probe_selftest`·`run.py`·`local_server` 도
  현재 계약이다.

### 5. `verify.py` — 윈도우에서 표적이 안 뜨던 것 (D-315)

`["npx", "vitest", …]` 를 셸 없이 부르면 PATH 의 실체가 `npx.CMD` 라 `[WinError 2]` 로 죽는다
(P-48). 실행기를 이름으로 해석한다(`frontend/node_modules/.bin/vitest[.cmd]` → `which("npx")`).
셸로 우회하지 않았다 — 인자 따옴표 규칙이 플랫폼마다 달라 경로에 공백이 있으면 다시 깨진다.
같이 못박은 것 셋: 실행기가 없으면 **전량으로 갈아타지 않고** `RUNNER_MISSING` 으로 그
단계만 실패한다 · 공용 부품 변경이 전량 vitest 를 자동 선택하지 않는다 · 전량 실패는
`--failed` 기록을 안 남긴다(적으면 `--failed` 가 전량 게이트가 된다). 시험 6건이 지킨다.

### 6. 안 지운 것 — P-50

**`/api/team-docs` 를 프런트가 한 번도 안 부른다**(0건). 그런데 라우터는 그대로 물려 있고
(엔드포인트 11개 · 1,918줄) `app/authz/visibility.py` 에 그 미러 표를 위한 가시성 갈래가
따로 산다. 이번에 안 지운 이유 셋: 표가 이관 계보를 들고 있어 **데이터 결정**이 필요하고,
지우면 가장 값진 권한 음성 시험 넷이 대상을 잃으며(정본 쪽에 그 계약이 **전부** 있는지 먼저
대조해야 한다), 브라우저 E2E 없이는 남은 소비처를 못 본다. **P-41 과 같은 묶음**이다.

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
- **S17 — Empty / Loading / Error / Feedback + Clovi + Detail Metadata.** 클로비가 박스가
  아니라 «보이는 크기» 로 서고, 값이 0 이면 화면이 접힌다. 결정 **D-294~D-298**.
- **S19 ✅ — 나머지 User Route.** 열이 한 배치 규칙만 쓰고(D-308) 빈 화면이 자기 자리에 선다
  (D-309). `/ai` 가 통째로 500 이던 것(D-311)을 포함해 화면 결함 넷을 함께 고쳤다. 결정
  **D-308~D-312**. Flow 감사와 캡처는 **Acceptance 축**이다(P-29 · P-44 · §9.4).
- **S18 ✅ — Pilot Archetype 8종.** 기능 축만 닫았다 — Flow 258건을 실브라우저에서 눌러
  252 PASS / 6 FAIL, 원장을 두 방향으로 대조하게 했고(C1c) 조용한 결함 넷을 잡았다.
  캡처를 다시 안 찍어 17 화면은 `IN_PROGRESS` 이고 잔여는 **P-44** 다. 결정 **D-299~D-305**.

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

## NEXT — 다음 시작점: S20 (요청 시)

**S20 = 관리자 IA + 관리자 콘솔** (W11 + W12).
사용자 요청 없이 착수하지 않는다. 범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1,
Backlog 는 **P-30**. Exit 는 이제 **§9.4-A** 다 — Coverage·Flow·Pilot·Capture·Evidence 를
그 회차의 완료 조건으로 걸지 않는다.

Health Correction 이 넘기는 것 넷:

0. **P-51 신규 — 티켓 읽기 계약의 golden 이 7건 어긋나 있다.** 마지막 Full 이 잡았고
   **HC 변경을 전부 stash 한 HEAD 에서 같은 7건이 그대로 뜬다.** 그냥 다시 찍으면 안 된다 —
   칸이 늘어난 것(의도된 확장일 가능성)과 **첫 행이 바뀐 것**(순서가 달라졌다는 뜻)이 섞여
   있고, 덮으면 뒤쪽 증거가 사라진다.
1. **P-50 신규 — `/api/team-docs` 가 아무도 안 부르는 채로 서 있다.** 프런트 호출 0건인데
   라우터 11개·1,918줄과 가시성 갈래가 살아 있다. **P-41(화면에 남은 Notion 잔재)과 같은
   묶음**이라 함께 정해야 반쪽으로 안 끝난다. 지우기 전에 권한 음성 시험 넷의 계약이 정본
   쪽에 전부 있는지 대조해야 한다.
2. **Acceptance 축은 그대로 남아 있다** — W10 Flow 감사(**P-29**)와 S18 캡처·기록 형식
   (**P-44**). 소유는 **S21·S22** 다(§9.4-B). 원장의 `NOT_AUDITED` 는 손대지 않았다.
3. **P-40 · P-41 · P-42 · P-43** 은 소유 회차 그대로다(S22 · S20 · S20 · S22).
4. **Acceptance 축의 도구는 안 지웠다.** `scripts/ui_qa/` 의 독립 프로브 열하나(`ai_e2e` ·
   `filter_e2e` · `approval_e2e` 등)는 전부 `python -m` 진입점이고 여럿이 DECISIONS·PLAN 에서
   그 결정을 **증명한 계측기**로 인용된다. 브라우저를 안 돌리는 회차가 지울 근거가 없다.

**닫은 것**: P-38(시험 강도 15건) · P-39(백엔드 회귀 넷 — 전부 S14 축 이동의 잔상이었다) ·
P-45(`PATH_SEP`) · P-46(동사표) · P-47(`filter-chain`, 제품 결함이 아니었다) ·
P-48(`verify.py` 윈도우) · P-49(논리 테두리).
