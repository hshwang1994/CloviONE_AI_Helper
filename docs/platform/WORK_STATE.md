# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-25** (S20 뒤)
- phase: **E — UI Renewal 재개.** S20 이 W11+W12 를 닫았다. 다음은 **Acceptance 축**(S21·S22)
- session: **S20 — 관리자 IA + 관리자 콘솔 완료.** 물은 것은 둘이다 — 관리자 영역에서
  **여기서 할 수 있는 일이 없는 자리가 어디인가**, 그리고 **할 수 있는데 화면이 없는 일이
  무엇인가**. 🔴 옛 시스템이 화면에만 살아 있었고(P-41 · D-316) 그 잔재 뒤에 **조용한 제품
  결함 셋**이 있었다(D-317 · D-318). 🔴 S8 이 만든 파일 저장소 계약은 **부르는 화면이
  0건**이라, 「운영과 백업이 같은 장치인가」를 서버가 계산해 두고도 아무도 못 보고 있었다
  (D-319). 아래 「S20 이 한 것」 절. 결정 **D-316~D-321**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S20 도 옮기지 않는다.** 이유는 S11~S19 와 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- s19_commit: **`ee2e4118`** · hc_commit: **`2c3e6c60`**
- s20_commit: **`136b00aa`** — S20 본체(화면·registry·백엔드·원장·하네스·문서) ·
  **`9a3ade64`** — 배포 뒤 운영을 읽다가 나온 결함 하나(걷어낸 이름이 든 연동 행이 고쳐지지
  않던 것 — D-321 의 다른 절반). **배포 대상은 `9a3ade64`** 다
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

## S20 이 한 것 — 관리자 IA + 관리자 콘솔

### 1. 🔴 옛 시스템이 **화면에만** 살아 있었다 (P-41 · D-316)

Notion 런타임은 S14 가 걷었다. 그런데 화면에는 사이드바 항목 「Notion 사용자 연결」과 그
화면 전체, 사용자 상세·내 프로필의 연결 상태 줄, 오프보딩 목록의 연결 열, 초기 설정의
「사용자 매핑」 단계와 그 링크, 외부 연동의 「Notion」 유형이 남아 있었다. 공통점은 하나다 —
**거기서 할 수 있는 일이 없다.** 연결을 만드는 경로가 제품에 없고, 있어도 아무것도 안 바뀐다
(담당자 축은 **D-285** 가 옮겼다).

가르는 기준은 **「지금 할 수 있는가」**다. 내린 것: 화면·라우트·사이드바 항목·라우터
(`app/notion_mapping/router.py`, 소비처가 그 화면뿐이었다)·응답 칸(`notion_mapping_status`)·
초기 설정 단계. **남긴 것**: 표 `user_notion_mappings`(이관 계보이자 옛 담당자 토큰의 짝) ·
감사 대상 유형 `user_notion_mapping`(**옛 기록이 있다** — 목록에서 빼면 그 기록을 걸러 볼
방법이 사라진다) · 이름표들 · 옛 연동 행의 검증 어휘(롤백 스냅샷이 그것으로 다시 검증된다).
같은 규칙을 S11 이 이미 `runner`·`workflow`·`template` 에 적용해 뒀다.

### 2. 🔴 그 잔재 뒤에 **조용한 제품 결함 셋**이 있었다 (D-317 · D-318)

셋 다 오류를 안 냈다.

* **오프보딩 후임 후보**가 `user_notion_mappings` 를 INNER JOIN 했다. 그 짝은 컷오버 뒤로
  **새로 안 생긴다** — 이관 이후에 만든 계정은 후임 명단에서 통째로 빠졌고, 화면은 이유를
  말하지 않았다. 재배정 경로(`replace_ticket_assignee`)는 앱 user_id 를 그대로 받으므로
  **막을 이유도 없었다.**
* **조직 정합성 진단**의 「담당자를 포털 계정으로 연결하지 못한 티켓」이 옛 id 만 «아는 값»
  으로 셌다. 새 계정이 담당한 **정상 티켓**이 매번 이 목록에 올라왔고 안내는 없는 화면으로
  가라고 말했다 — 진단이 **없는 문제를 만들어 내고 있었다.**
* **초기 설정 체크리스트의 「사용자 매핑」 단계**가 재던 것은 verified 행 수인데, **새 설치에서
  그 행은 영원히 0 이다**(만드는 경로가 제품에 없다). 목록은 끝까지 갈 수 없었고 그 뒤에
  `requires` 로 매달린 「AI 러너」까지 잠겼다. 오프보딩 미리보기의 같은 항목도 함께 걷었다.

### 3. 🔴 계약이 있는데 **부르는 화면이 없었다** — 파일 저장소 (D-319)

S8 이 저장소 계약을 전부 만들었다(목록·추가·수정·마운트 실측·용량·같은 장치 경고·권한·시험
열셋). **프런트 호출은 0건이었다.** 그래서 업로드가 어디에 쌓이는지, 그 자리가 지금 붙어
있는지, **운영과 백업이 같은 장치인지**를 서버에 들어가야만 알 수 있었다 — 마지막 것은
「장치가 죽으면 백업도 함께 죽는다」는 뜻이라 사람이 봐야 하는 사실이다.

`설정 → 파일 저장소` 탭을 세웠다. 자리의 근거 둘: 목표 IA(§14.1)가 「일반 설정 · File
Storage · AI 설정」을 한 묶음으로 적었고, `STORAGE_CONFIGURE` 가 `SYSTEM_ADMIN_ONLY` 라
os·ai 탭과 role 이 균일하다(이 그릇의 제약이 그것이다). 화면이 답하는 질문은 하나다 —
**「지금 파일을 쓸 수 있는가」**. 「지금 확인」은 안 붙어 있을 때 **다음에 칠 명령**
(`systemctl start <유닛>`)을 준다. 마운트 자체는 안 한다(웹 프로세스에 그 능력이 없다).

### 4. IA 정합 — 빵부스러기와 이름

화면 셋이 자기가 있는 묶음을 틀리게 말하고 있었다(초기 설정 「감사」 · 설정 「운영」 ·
개발자 월간 리포트 「자동화」). registry 화면 24개는 `area` 가 사이드바와 전부 맞는다 —
어긋난 것은 **손으로 적는** `PageHeader area=` 를 가진 화면들뿐이었다(D-320). 화면 제목
하나도 사이드바와 맞췄다: 「임퍼소네이션(대리 보기)」 → 「대리 보기」.

`/dev-report` 의 판 둘이 자기 폭을 못 쓰던 것을 고쳤다(**P-42**) — 조건 줄은 이 저장소에 이미
계약이 있어서(`FilterSurface`) 거기로 내렸고, `xxl` 아래로 접힐 때 늘어나던 도넛 판은
내용만큼만 서게 했다. 고를 것이 하나뿐이던 외부 연동의 「유형」 선택기도 내렸다(D-321).

### 5. 권한 — 감춘 것과 막은 것

새 화면의 쓰기 셋(추가·수정·지금 확인)을 `user`·`operator`·`admin`·`auditor` 넷이 **직접
불러 전부 403** 인 것과, `system_admin` 은 **실제로 된다**는 반례를 같은 자리에서 센다.
화면에서 탭을 감춘 것은 표시일 뿐이다(불변규칙 §5).

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
