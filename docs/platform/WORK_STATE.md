# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-26** (S21 뒤)
- phase: **F — Acceptance.** S21 이 W14(Functional E2E 전수)를 닫았다. 다음은 **S22**
- session: **S21 — Functional E2E 전수 완료.** 물은 것은 하나다 — **사용자가 실제로 그
  기능을 쓸 수 있는가.** 화면이 있는가가 아니다. `exists:true` Flow 809건을 실브라우저
  (Chromium · 로컬 PostgreSQL 씨앗)에서 눌러 **766 PASS / 43 FAIL**, 제품에 없는 동작
  122건을 `exists:false` 로 내렸다. 🔴 **관리자 화면 머리의 이동 버튼 일곱 개가 눌러도
  아무 데도 안 갔다**(D-324) — 오류도 이동도 없어서 어떤 시험도 못 봤다. 🔴 **AI 도우미의
  대화 검색 상자가 결과 0건이면 자기를 지웠다**(D-325). 아래 「S21 이 한 것」 절.
  결정 **D-322~D-325**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S20 도 옮기지 않는다.** 이유는 S11~S19 와 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- s19_commit: **`ee2e4118`** · hc_commit: **`2c3e6c60`**
- s20_commit: **`136b00aa`** · **`9a3ade64`**(배포 대상이었다)
- s21_commit: **ede55e47** — S21 본체(제품 결함 둘·하네스·원장·문서)
- deployed: **`9a3ade64`** 가 운영에 나갔다 (2026-08-25 20:11, `install.sh upgrade --source local`). Stage 0~18 전부 OK · `VERIFY_OK` · 스냅샷 `/var/backups/clovirassist/20260825-201111`. `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` · 유닛 6종 active · `STAGE_5_FRONTEND: 번들이 소스와 맞습니다`(배포본 `index.Dm759os4.js` 가 빌드한 것과 같다).
  스모크: 살아 있어야 하는 관리자 경로 여섯이 세션 없이 **401**(라우트는 있고 인증이 막는다) · 없어야 하는 `/api/admin/notion-mapping` 둘이 **404** · `/login` 200.
  🔴 **세션 스모크는 못 했다** — 이 호스트의 QA 계정이 `account_archived` 라 로그인이 안 되고, 스모크를 하려고 계정을 되살리는 것은 운영 데이터를 고치는 일이다. 대신 화면이 부르는 **그 함수**를 운영 DB 위에서 **읽기만** 하며 확인했다: 저장소 1개(운영·로컬·쓰기가능·58파일·같은 장치 경고 없음) · 초기 설정 단계 여섯에 `user_mapping` **없음** · 정합성 안내에 Notion **없음** · 오프보딩 후임 후보 14명 중 **옛 짝이 없는 2명이 실제로 포함**(고치기 전에는 이 둘이 빠졌다) · 사용자 응답에 `notion_mapping_status` **없음**.
  되돌리려면 `sudo /opt/clovirassist/deploy/install.sh rollback --target /var/backups/clovirassist/20260825-201111`
- full_snapshot: **HC 마지막 Full 1회** (`python scripts/verify.py --full`, 2026-08-25 17:29~18:13).
  정적 전량 **PASS** · 프런트 전량 **329 파일 / 2,451건 전부 PASS** · 백엔드 전량 **FAIL 7건**
  — 전부 `test_api_contract_golden.py` 이고 **HEAD 에서도 같은 7건**이 뜬다. **P-51** 이다.
  **S20 은 전량을 안 돌렸다** — 일상 개발의 Exit 가 아니다(§9.4-A)
- ui_gate: `--stage plan` **PASS**(S20 도 확인 — 새 Surface 를 세우고 없어진 Surface 를
  `RETIRED` 로 적은 뒤에도 초록이다). `--stage wave` 는 안 돌렸다 — W8 잔여(P-44)를 여는
  일이고 그것은 **Acceptance 축**이다(§9.4). 그쪽 상세는
  [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **93 표**다. alembic head 는 `0016_document_axis_to_documents` 다. **S20 도 스키마를
  안 건드렸다** — 지운 것은 라우터와 화면이고 표는 이관 계보라 남겼다(D-316)
- pilot: **258 Flow 중 252 PASS / 6 FAIL** (`dist/ui-qa/pilot/flows.json`). S18 이 잡은 조용한
  결함 넷과 결정 **D-299~D-305**

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

## S21 이 한 것 — Functional E2E 전수 (W14)

### 0. 무엇을 셌나

원장의 `exists:true` NOT_AUDITED Flow 931건을 소스와 먼저 대조했다. **111건은 제품에서
없어진 기능**이었다(`/team-docs` 는 `/knowledge` 로 되보내기만 한다 · 러너·워크플로·템플릿·
문서 생성 회차는 S11 이 걷었다 · 사용자 화면의 수동 동기화는 S15 · 「유형」 선택기는 S20).
남은 **820건을 실브라우저에서 눌렀다** — 첫 전수 662 PASS / 158 FAIL, 고친 뒤 마지막 전수
738 PASS / 82 FAIL, 그 뒤 깊은 진단이 찾은 제품 결함 하나를 고치고 그 화면들만 다시 돌려
**최종 766 PASS / 43 FAIL** 이다. 실측이 11건을 더 「없는 것」으로 밝혀 `exists:false` 는
122건이 됐다(D-323).

### 1. 🔴 눌러도 **아무 데도 안 가는 버튼이 일곱 개** 있었다 (D-324)

`DataScreen` 의 행 액션은 맨 앞에서 `a.navigate` 를 처리하는데 **머리 액션에는 그 가지가
없었다.** registry 가 `{ label: "백업 목록", navigate: () => "#/backup" }` 로 선언한 버튼은
쓰기 분기로 떨어져 `a.path()` 에서 예외가 났고, 잡히는 곳이 오류 처리기라 화면에는 아무
일도 안 일어난 것처럼 보였다 — **오류도 없고 이동도 없다.** 백업 목록 · 백업 일정 설정 ·
정책 사용 통계 · 프롬프트 사용 통계 · 이상 징후 보기 · 감사 로그 전체 · 감사 로그에서 보기.

어떤 시험도 못 잡은 이유는 **아무것도 실패하지 않았기 때문**이다. 요청이 안 나가고 상태가
안 바뀌고 오류가 안 뜬다 — 「눌렀는데 주소가 그대로다」를 보는 눈이 있어야만 보인다.

### 2. 🔴 조건을 좁힌 사람이 **넓힐 칸을 잃었다** (D-325)

AI 도우미의 대화 검색 상자는 결과가 있을 때만 그려졌다. 서버가 이미 걸러 온 결과라, 한
글자를 잘못 친 순간 그 상자가 **자기를 지웠다.** 되돌리는 길이 빈 상태의 다른 버튼으로
옮겨 가 있어 기능 손실은 아니었지만, 조건을 적은 자리에서 그것을 못 고치는 것은 옳지 않다.

### 3. 권한은 **양방향으로** 쟀다

역할 다섯(user·operator·auditor·admin·system_admin) × 관리자 엔드포인트 18개를 직접 불렀고,
문서·티켓·게시글·프로젝트는 **목록과 상세가 같은 답을 하는지**를 표본 8·8·8·3건으로 봤다.
어긋남 **0건**(`dist/ui-qa/s21-permission/permission.json`).

- 일반 사용자는 관리자 엔드포인트 **전부에서 403** 이다(하나는 405 — 그 문이 없다).
- 문서·티켓·프로젝트는 목록에서 0건을 보는 동시에 **관리자가 보는 상세 주소를 직접 열어도
  403** 이다 — 목록에서 안 보이는 것이 주소로 열리는 우회가 없다.
- 감사 역할은 읽고 못 쓴다(감사 로그·백업 목록·정합성 진단은 200, 모든 쓰기는 403).
- 🔴 **기대값 쪽이 틀린 것 열셋을 제품 소스에 맞춰 고쳤다** — 「아무도 못 만든다」로 적혀
  있던 사용자 생성은 실제로 `CONSOLE_WRITE_ROLES` 이고, 기능 플래그 쓰기는 `PATCH` 가 아니라
  `PUT` 이라 405 를 「막혔다」로 세고 있었다. 그리고 목록 표본이 **0건인 채로 통과하고
  있었다**(응답을 400자로 자른 뒤에 파싱해서 언제나 깨진 JSON 이었다) — 표본 수를 안 보면
  그 통과는 침묵과 구별되지 않는다.

### 4. 원장을 제품에 맞췄다 (D-323)

정렬은 **날짜 열에만** 붙는다(`dateCol` 만 `sortable` 을 준다). 날짜 열이 없는 표 여섯에
「정렬을 눌러 본다」가 서 있었다. 조직 콘솔의 오른쪽 판은 `inSplitView` 라 검색 상자도 저장된
뷰도 안 그리는데(왼쪽 트리가 그 일이다) 그 셋이 원장에 있었다. 알림 화면은 `onQuery` 를
선언하지 않아 `?id=` 딥링크가 없다. **제품을 원장에 맞추지 않고 원장을 제품에 맞췄다.**

### 5. 하네스 결함도 함께 고쳤다 (인수를 막는 최소 범위에서)

무리 머리글(`<th scope="colgroup">`)을 데이터 행으로 세던 것 · 셸에 늘 하나 떠 있는
`role="dialog"` 를 「모달이 안 닫혔다」로 읽던 것 · 확인 버튼을 이름으로 찾다 엉뚱한 것을
누르던 것 · 대화 줄을 **이름을 고치는 동안에만** 붙는 이름표로 세다 셸의 내비게이션 버튼을
대신 세던 것. 그리고 **QA 실행이 저장소의 `config/feature-flags.json` 을 고치고 있었다** —
설정 디렉터리를 베껴서 쓰게 했다.

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
- **S20 ✅ — 관리자 IA + 관리자 콘솔.** 옛 시스템이 화면에만 살아 있었고(D-316) 그 잔재
  뒤에 조용한 제품 결함 셋이 있었다(D-317 · D-318). 부르는 화면이 0건이던 파일 저장소
  계약에 화면을 세웠다(D-319). 결정 **D-316~D-321**.
- **S21 ✅ — Functional E2E 전수 (W14).** Flow 809건을 실브라우저에서 눌러 766 PASS /
  43 FAIL 이고 `exists:true` 에 `NOT_AUDITED` 가 0 이다. 눌러도 아무 데도 안 가던 머리
  버튼 일곱(D-324)과 자기를 지우던 검색 상자(D-325)를 고쳤고, 권한을 역할 다섯 × 18
  엔드포인트 + 목록·상세 일관성으로 재 어긋남 0 이다. 결정 **D-322~D-325**.
- **S18 ✅ — Pilot Archetype 8종.** 기능 축만 닫았다 — Flow 258건을 실브라우저에서 눌러
  252 PASS / 6 FAIL, 원장을 두 방향으로 대조하게 했고(C1c) 조용한 결함 넷을 잡았다.
  캡처를 다시 안 찍어 17 화면은 `IN_PROGRESS` 이고 잔여는 **P-44** 다. 결정 **D-299~D-305**.

## 상태 — 전환 축 다섯

| 축 | 현재 | 소유 Session |
|---|---|---|
| **PostgreSQL** | ✅ **System of Record 다.** 운영이 그 위에서 돈다 | S2 ✅ · S4 ✅ · S9~S14 ✅ |
| **SQLite 제거** | ✅ **끝났다.** Runtime 의존 0 이고 데이터도 전부 넘어갔다 | S13 ✅ · S14 ✅ |
| **Notion Migration** | ✅ **끝났다.** 런타임은 S14 가, 화면 잔재는 S20 이 걷었다 | S13 ✅ · S14 ✅ · S20 ✅ |
| **AI** | ✅ 끝났다 | S9 ✅ · S10 ✅ · S11 ✅ |
| **Backup** | ✅ 끝났다 — 그리고 S14 가 **실 데이터로 다시 증명**했다 | S2 ✅ · S4 ✅ · S8 ✅ · S12 ✅ · S14 ✅ |

**Identity 축도 닫혔다** — 호스트명·TLS(S3) · slug(S4) · 역할·권한(S5), 그리고 마지막 한 건인
세션 쿠키 이름을 S14 가 갈았다(P-33).

**UI 축은 W14 의 기능 축까지 왔다.** 근거와 수치는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이었고 재개는 Phase E(S15~S20)다 (D-207).

## NEXT — 다음 시작점: S22 (요청 시)

**S22 = Final Audit · Full Capture(최초이자 유일) · 설치 Acceptance 완주** (W15).
사용자 요청 없이 착수하지 않는다. 범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1 ·
§10, Backlog 는 **P-32**.

S21 이 넘기는 것 다섯:

1. **남은 Flow 실패 43건은 전부 QA·씨앗·환경이고 제품 결함이 아니다**(**P-53** 신규).
   시험이 제품 계약을 잘못 읽는 것 31건 · 씨앗과 실행 순서 10건 · 환경 2건. 하나하나의
   사유는 `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 `findings` 에 그대로 있다.
2. **S18 캡처·기록 형식(P-44)** 그대로. 소유는 S22 이고, S21 의 Functional Evidence 는
   **재사용한다**(§9.2 E7 — S22 는 S21 전체 재실행이 아니다).
3. **P-50 · P-52**(프런트 호출 0건인 라우터 둘) · **P-51**(티켓 읽기 golden 7건) 그대로.
4. **P-40 · P-43** 은 소유 회차 그대로다(S22).
5. **Acceptance 축의 도구는 안 지웠다.** `scripts/ui_qa/s21_*.py` 열여섯은 전부 `python -m`
   진입점이고, `s21_permission.py` 는 권한 계약을 **매번 다시 잴 수 있는** 형태로 남는다.
