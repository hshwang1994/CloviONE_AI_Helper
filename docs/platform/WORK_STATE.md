# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-25** (S16)
- phase: **E — UI Renewal 재개.** S16 이 끝났고 다음은 S17~S20
- session: **S16 완료.** 다음은 **S17 — Empty / Loading / Error / Feedback + Clovi + Detail Metadata (요청 시)**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S14 도 옮기지 않는다.** 이유는 S11~S13 과 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- ui_gate: **UI_RENEWAL_COVERAGE_OK (stage=wave, wave=W6, 억제 1건)** — S16 이 UI 축의
  CHECKPOINT 를 W6 으로 올렸다. 억제 하나는 칸반 레인의 균등 격자다(SUP-01, 만료 2026-10-20).
  그쪽 상세는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **93 표**다. `0013~0016` 은 표를 안 늘린다(칸·데이터만 옮긴다). alembic head 는
  `0016_document_axis_to_documents` 다

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

## S16 이 실제로 한 것

이번 회차가 답한 질문은 하나다 — **표가 비교를 할 수 있게 되어 있는가.**

### 1. 열이 폭 대신 **의미**를 말한다 (D-288)

열이 자기 폭과 정렬을 숫자로 적고 있었다(`width: "6rem"` · `align: "right"`). 그 숫자는
화면마다 따로 정해졌고, 그래서 같은 뜻의 값이 화면마다 다른 폭과 다른 정렬로 나왔다 —
🔴 **개수인데 자릿수가 세로로 안 맞는 열이 여덟**이었다(`/board` 의 「조회」, `/my-stats` 의
「배정·완료」). 표의 존재 이유가 비교인데 그 여덟에서는 비교가 안 된다.

이제 열이 `type` 으로 의미를 말하고 폭·정렬·자릿수 고정·넘침이 거기서 파생한다
(`frontend/src/ui/columnTypes.js`, 타입 열넷). **여덟은 0 이 됐고** 아홉 번째가 생길 자리도
함께 닫혔다. 호출부가 적은 값은 언제나 이기므로 `type` 을 안 준 열의 렌더는 안 바뀐다.

그 과정에서 **선언만 있고 배선이 없던 것**을 하나 찾았다: QA 가 식별자형 숫자를 예외로
읽는 표식(`data-col-role="identifier"`)을 내보내는 소스가 저장소에 **한 곳도 없었다.**

### 2. 열을 언제 빼도 되는가 (D-289)

표는 **호출부가 준 질의 계약(`resultScope`) 없이는 아무 열도 안 없앤다.** 「이번 페이지의
값이 우연히 같다」로 열을 빼면 페이지를 넘길 때마다 열이 생겼다 사라지고, 사용자는 자기가
무엇을 해서 표가 바뀌었는지 알 수 없다. 사용자가 그 축을 직접 걸었거나 질의 계약상 값이
불변일 때만 빼고, 뺐다는 사실과 그 값을 표가 한 번 적는다.

### 3. 그 자리 편집의 공통 계약 (D-290)

같은 값을 Grid·상세 머리·폼 세 자리에서 바꾼다. 각자 구현하면 상태 기계가 셋이 되고, 하나는
롤백이 없고 하나는 두 번 저장한다. 상태 기계를 공통 계층 하나에 뒀다
(`frontend/src/ui/InlineEdit.jsx`). **성공은 서버가 돌려준 값으로 그린다** — 넘겨준 값이
아니라. **배선은 티켓 도메인 회차의 몫**이라 R-89 는 아직 `IN_PROGRESS` 다.

### 4. 그림이 자기가 답하는 업무 질문을 갖는다 (D-291)

제목(「상태 구성」)은 무엇을 그렸는지를 말하지 그것을 보고 무슨 판단을 해야 하는지를 말하지
않는다. 소비처 열둘이 각자 그 한 문장을 갖고, 소스를 직접 세는 시험이 그것을 지킨다.
그리고 「담당자별 완료 업무량」 막대 하나를 지웠다 — 바로 아래 표가 같은 사람들의 같은 숫자를
말하고 있었고, 게다가 막대는 값이 0 인 사람을 빼고 그려 **표와 명단이 달랐다.**

### 5. Brand 충돌 둘을 결정으로 닫았다 (D-292 · D-293)

PLAN 이 **W6 에게** 닫으라고 적어 둔 것이다. 판독값은 심각도가 없으면 Brand 잉크를 쓰고
있으면 상태색이 이긴다 — 색이 뜻을 나르는 자리에서 정체성이 이기면 그 색은 거짓말이 된다.
선택은 이 제품에서 세 자리 모두 **Brand 레일**인데 검사는 면을 요구하고 있었다(§Surface
위계와 정면 충돌). `selected_state` 를 잉크 role 로 옮겼다 — 무채색 선택은 여전히 실패한다.
판정 규칙을 고쳤으므로 반례 일곱을 `probe_selftest.py` 에 붙여 양방향으로 확인했다.

### 6. 🔴 실브라우저가 시험이 못 보던 것을 잡았다 — `/work-board` 가 안 열리고 있었다

프로젝트 목록 응답은 객체(`{projects: [...]}`)인데 그 화면만 배열로 읽어 `.map` 을 불렀고,
질의가 도착하는 순간 `TypeError` 로 ErrorBoundary 가 화면을 대신 그렸다. 같은 훅을 쓰는
나머지 넷은 전부 옳게 읽는다 — **한 곳만 다르게 읽는 것**이라 정적 검사로는 안 보이고,
그 화면에는 렌더 시험이 **하나도 없었다.** 고치고 나니 크래시가 가려 두었던 두 번째 결함이
드러났다: 프로젝트 선택기가 평범한 드롭다운이었다. 둘 다 고쳤고 시험으로 못박았다.

### 7. 함께 걷어낸 것

화면 문구의 가운뎃점·em 대시 다섯 · subprocess 인코딩 하나 · `tokens.css` 지문 표류.
셋 다 `static_checks.sh` 에서 오래 빨간 채였고 S16 이 만든 것이 아니지만 전부 한 줄짜리였다.

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
- **S16 — Table / Grid / Metadata / Alignment + Chart.** 열이 폭 대신 의미를 말한다. 승격한
  여덟 검사가 `--fail-on` 으로 걸린 채 전부 초록이고 `numeric_alignment` 8건이 0 이 됐다.
  결정 **D-288~D-293**.

## 상태 — 전환 축 다섯

| 축 | 현재 | 소유 Session |
|---|---|---|
| **PostgreSQL** | ✅ **System of Record 다.** 운영이 그 위에서 돈다 | S2 ✅ · S4 ✅ · S9~S14 ✅ |
| **SQLite 제거** | ✅ **끝났다.** Runtime 의존 0 이고 데이터도 전부 넘어갔다 | S13 ✅ · S14 ✅ |
| **Notion Migration** | ✅ **끝났다.** 데이터가 넘어갔고 런타임 코드가 없다 | S13 ✅ · S14 ✅ |
| **AI** | ✅ 끝났다 | S9 ✅ · S10 ✅ · S11 ✅ |
| **Backup** | ✅ 끝났다 — 그리고 S14 가 **실 데이터로 다시 증명**했다 | S2 ✅ · S4 ✅ · S8 ✅ · S12 ✅ · S14 ✅ |

**Identity 축도 닫혔다** — 호스트명·TLS(S3) · slug(S4) · 역할·권한(S5), 그리고 마지막 한 건인
세션 쿠키 이름을 S14 가 갈았다(P-33). 브라우저에 남아 있던 저장소 키 다섯과 관리 콘솔의 옛
systemd 이름도 함께 갈았다.

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이었고 재개는 Phase E(S15~S20)다 (D-207).

## NEXT — 다음 시작점: S17 (요청 시)

**S17 = Empty / Loading / Error / Feedback + Clovi 크기 + Detail Metadata 위계.**
사용자 요청 없이 착수하지 않는다. 범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1,
Backlog 는 **P-27**.

S16 이 다음 Session 에게 넘기는 것 다섯:

1. **열에 뜻을 붙이면 폭이 따라온다.** `frontend/src/ui/columnTypes.js` 에 `type:` 을 붙이면
   그 열의 폭·정렬·자릿수가 한 자리에서 정해진다 — 숫자를 다시 적지 않는다.
2. **그 자리 편집 계약이 서 있다.** `frontend/src/ui/InlineEdit.jsx` 의 상태 여섯을 다시
   만들지 않아도 된다. 배선하는 회차가 R-89 를 닫는다.
3. **빈 데이터 4단계의 나머지 절반이 S17 몫이다.** W6 은 표현 축(타입·중복 제거)만 닫았다 —
   차트 모양 스켈레톤과 「진짜 없음이면 차트를 접는다」는 W7 Exit 가 소유한다.
4. **캡처를 설치처 없이 찍는다.** `python -m scripts.ui_qa.local_capture --label <라벨>
   --routes <화면들> --fail-on <검사들>`. ⚠️ **S16 도 설치처에 배포하지 않았다** — 고친
   화면이 사람들에게 닿으려면 배포가 따로 필요하다.
5. **범위 밖으로 넘긴 것 넷**: 프런트 시험 셋(**P-34**, S17) · 시험 강도 선언 미비 15건
   (**P-38**) · 백엔드 회귀 넷(**P-39**) · 중립 램프의 divider 가 Brand 색으로 세어지는 것
   (**P-40**, S22). 앞의 셋은 S13·S14 가 남겼고 **변경을 stash 한 채로 같은 것들이 그대로 뜬다.**
