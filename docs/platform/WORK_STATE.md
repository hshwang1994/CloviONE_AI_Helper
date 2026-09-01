# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-09-01** (표의 바닥 폭 · 백로그 트랙 · 칸에 맞춘 열 접기 — D-379·D-380)
- phase: **F — Acceptance 완료(S22).** 그 뒤는 CLAUDE.md §7.0 의 **일반 개발**이다
- session: **표가 자기 바닥 폭을 갖고, 칸에 맞춰 열을 접는다** (D-379 · D-380).
  사용자가 「보드 칼럼 너비가 이상하고 배율을 조정하면 그리드가 깨져서 안 보인다」고 했다.
  `table-layout: fixed` 는 열의 `min-width` 를 안 보므로, 나머지 열의 고정 폭 합이 칸보다
  크면 남는 폭을 먹기로 한 **제목 열이 0** 이 되고 머리글이 옆 이름 위에 겹쳤다 — 팀 티켓은
  1280·1366·1536·1600 **네 폭 모두에서 제목이 0px** 였다. `tableMinWidth`/`tableLayoutSx` 로
  표에 바닥을 걸었다. 백로그는 반대쪽이었다: 제목 트랙이 26rem 에서 멈춰 줄 오른쪽이 2560
  에서 955px 비었고, `minmax(14rem, 1fr)` 로 표의 `title` 과 같은 규칙에 맞췄다.
  그 대가(좁은 화면의 가로 스크롤)를 **열 접기**로 갚았다 — 판단의 입력을 뷰포트에서
  **그 표가 받은 칸**으로 바꾸고(옛 900~1200 규칙은 칸이 902px 인 1920 화면에서 아무 열도
  안 뺐다) 들어갈 때까지 뒤에서부터 하나씩 뺀다. 규칙은 kit 하나가 들어
  `DataTable` 과 `GroupedTickets` 가 같은 함수를 본다. 1920 에서 넘치는 표가 **0개**가 됐다.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **이번 회차도 안 옮긴다.** 이유는 S11~S22 와 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: **깨끗하다**(이 회차를 커밋한 뒤 기준).
- s22_commit: `2f4fc587` · `1921f884` · prev_commit: `e8d39fd3` · `757b6e22`
- this_commit: **`9fb6187f`**(바닥 폭 · 백로그 트랙 · D-379) · **`34c77989`**(칸에 맞춘 열 접기 · D-380)
- prev_session_commit: `bc55228c` · `4ca1aab5` · `b340ab09` · `5db48df3`
- deployed: **`b340ab09`** 이 운영에 나갔다 (2026-09-01 17:24 · `scripts/deploy-upgrade.sh`).
  Stage 0~18 전부 OK · `VERIFY_OK` · `UPGRADE_OK` · 스냅샷 `/var/backups/clovirassist/20260901-172145`.
  **스키마가 바뀌었다** — alembic `0024_technology_tags` → **`0025_ticket_body_doc`**(표 94개 ·
  사용자 26명). 운영 DB 에서 `tickets.body_doc jsonb` 를 직접 확인했다.
  **이번 커밋의 것이 실제로 올라갔다**: 새 진입 번들 `index.CPdJHECE.js` 와
  `BlockEditor.BdP7d9UQ.js`(티켓 폼이 지연 로드하는 편집기)가 200 이고, 직전 배포의 진입
  번들 `index.D5HRTY7W.js` 는 404 다.
  스모크: `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  `postgresql`·`nginx`·제품 유닛 다섯 전부 active · `ssl_verify_result=0`.
  이번에는 `STAGE_5_FRONTEND` 가 한 번에 통과했다 — 빌드 직후
  `check_bundle_fresh.py --write` 로 기준을 다시 적었기 때문이다(앞 회차가 두 번 멈춘 자리).
  되돌리려면 `sudo /home/cloviradmin/clovirassist-upgrade/deploy/install.sh rollback --target /var/backups/clovirassist/20260901-172145`
- deployed_prev: `757b6e22`(2026-09-01 14:36 · 스냅샷 `20260901-143412`)
- verification: **표적**이다(§7.0 일반 개발). `scripts/verify.py` **초록**
  (`static_checks --scope dev` + vitest 표적). 공용 표를 건드렸으므로 `src/ui` 전량과
  접기가 닿는 화면 시험을 함께 돌렸다 — 67 파일 / 784 시험, 실패는 `editable-body-*`
  하나이고 **단독 실행에서 통과**하는 tiptap/jsdom 부하 흔들림이다(표와 무관).
  D-379 회차의 vitest 전량(363 파일)도 이번 변경 전에 초록이었다.
  🔴 `theme.js` 를 고쳐 `tokens.css` 의 source-hash 가 밀렸다 —
  `node scripts/generate_design_tokens.mjs` 로 다시 냈고 **토큰 값은 한 줄도 안 바뀌었다**.
- browser: **실브라우저로 쟀다**(로컬 QA 서버 · 헤드리스 Chromium · light).
  ① **전후 실측**(D-379) — 팀 티켓의 제목 열이 1280/1366/1536/1600 네 폭에서 `0px → 256px`
  이고, 1920·2560·3840 은 **한 픽셀도 안 바뀐다**. 백로그의 줄 오른쪽 빈 자리는
  494/955/1608px → 68/76/85px(=칸 사이와 여백뿐)이다.
  ② **회귀**(D-379) — 12 화면 × 2 뷰포트를 전후로 찍어 `results.json` 의 assertion 결과를
  대조했다. **달라진 항목 0**(실패 9건은 전후 동일 · 열 폭과 무관).
  ③ **전 화면 훑기**(D-380) — 20 화면 × 3 뷰포트의 표 48개. **폭이 0 인 열 0개**이고,
  가로로 밀리는 표가 1920 에서 **3개 → 0개**, 1366 에서 8개(최대 756px) → 5개(최대 260px),
  1200 에서 13개(최대 922px) → 11개(최대 426px)다. 남은 것은 접을 열을 아직 안 정한 표다.
- capture: 전량 정본은 **`s22-final`** 그대로다. 이번 회차도 캡처 하네스를 전량으로 안 돌렸다.
  **부분 캡처는 전량 원장을 안 덮는다**(D-306) — `capture_labels.after` 를 옮기지 않았다
- ui_gate: `--stage plan` **PASS**. `--stage wave`(W15)는 **초록이 아니다** — 남은 것은
  **P-44** 의 기록 형식(사슬의 서버 칸 982)과 그것이 붙잡고 있는 축들이다. 상세는
  [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **94 표**다. alembic head 는 **`0025_ticket_body_doc`** 다 — 표를 만들거나 지우지
  않았고, `tickets` 에 nullable 칸 하나(`body_doc jsonb`)를 더한다(D-374). 전량 백필은 안 한다

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
데이터는 전부 넘어갔고 서비스는 열려 있다. 원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).

| | |
|---|---|
| 사용자 · 프로젝트 · 티켓 | 26 · 22 · **1,145** |
| 티켓 번호 | 1,130건에 붙어 있고 **중복 0** · 고유 1,130 · 나머지 15 는 컷오버 뒤 만든 native 티켓이다 |
| 프로젝트 코드 | **22 / 22** · 중복 0 · 전부 여섯 자 대문자 · UNIQUE 인덱스가 지킨다 |
| 첨부 | `files` 58 · 티켓 첨부 237 · 문서 첨부 54 · **DB 가 가리키는 바이트 누락 0** |
| 이관 예외 | 미해결 11 — 그중 사람이 프로젝트를 정해야 하는 **9 건은 `/integrity` 가 전부 보여 준다**(P-52) |
| 옛 이름 층 | **없다** · 옛 포트(5678·5679·8787·8788·8789) 청취 **0건** · 그 포트를 가리키던 연동 등록 행 넷도 이제 없다(0017) |

## 이번 회차가 한 것 — 목록 · 필터/정렬 · 티켓 만들기

**목록에서 쪽이 사라졌다.** 페이저 다섯 벌(`ui/Pager.jsx` · `DataScreen` · `Users` ·
`Offboarding` · `SubListDrawer`)이 목록 끝 줄 하나(`ui/InfiniteScroll.jsx::ListFooter`)가 됐다.
굴리면 다음 묶음이 붙고, 「더 보기」 단추가 함께 선다(키보드·스크린리더는 무한 스크롤에 닿을
수 없다). 스크롤 창은 **윈도**다(D-364) — 그래서 `lib/listReturn.js` 를 한 줄도 안 고쳤다.
봉투 셋(`page` · `limit/offset` · `cursor`)을 `lib/useInfiniteList.js` 어댑터 하나로 받는다.

**필터·정렬은 서버가 한다**(D-367). 후보 값을 「지금 받아 둔 행」에서 뽑던 셋을 고쳤고
(D-368), `optionsFrom`/`datalistFrom` 두 갈래를 없앴다. 서버 정렬을 라우터 아홉 곳에 넣고
(D-369) 화이트리스트를 미러로 고정했다(`sortKeys.json`).

**덤으로 찾은 것**: `/audit` 의 고정 열 이름이 처음부터 안 움직이고 있었다(D-365 — 판의
`overflow:hidden` 이 sticky 의 스크롤 창이 되어 있었다).

**티켓 만들기**는 미리보기를 없애고, 서식·이모지가 커서 자리에 들어간다(D-371 — 포커스 없는
`<textarea>` 의 `selectionStart` 가 0인 것을 커서로 믿고 있었다).

**실브라우저가 유닛 시험이 통과시킨 결함 둘을 잡았다**(D-372). ① 넘침을 바깥으로 넘기는 것은
표가 칸 안에 들어갈 때만이어야 한다 — CSS 는 `overflow-x: auto` 와 `overflow-y: visible` 을
한 요소에 같이 못 쓰므로, 넓은 표까지 넘기면 판 밖으로 나가 옆 사이드바 위에 겹쳐 그려진다
(문서 목록에서 130px 실측). ② MUI 의 `sx` 는 `width: 1` 을 1px 이 아니라 `100%` 로 옮긴다 —
보이지 않는 센티넬이 바닥 줄 폭을 915px 먹어 건수 문구와 단추가 오른쪽으로 밀려 있었다.
둘 다 시험으로 고정했고, 고치기 전에 **빨간불부터 확인했다**.

스키마·권한·채번 계약은 안 건드렸다. `tests/security/` 전량이 그대로 초록이다.

## 완료

- **S0~S14** — 기반 · PostgreSQL · Identity/TLS · 설치 자동화 · RBAC · Work · Knowledge ·
  Storage · AI 1·2 · n8n 제거 · Backup/Restore · Migration · Cutover. 결정 D-187~D-284.
- **S15~S20** — Search/Filter 정확성 · Table/Grid · Empty/Loading/Error · Pilot Archetype ·
  나머지 User Route · 관리자 IA. 결정 D-285~D-321.
- **S21 ✅ — Functional E2E 전수 (W14).** Flow 809건을 실브라우저에서 눌러 766 PASS / 43 FAIL
  이고 `exists:true` 에 `NOT_AUDITED` 가 0 이다. 눌러도 아무 데도 안 가던 머리 버튼 일곱
  (D-324)과 자기를 지우던 검색 상자(D-325)를 고쳤다. 결정 **D-322~D-325**.
- **S22 ✅ — Final Audit · Full Capture · 설치 Acceptance (W15).** 판정은 **RELEASE READY
  WITH DOCUMENTED LIMITATIONS** 다. 되돌리기가 세 레인을 못 살리던 것(D-326·D-327), 설정
  보존이 죽은 줄까지 보존하던 것(D-328), 시각 결함 다섯(D-329~D-334)을 고쳤다. 결정
  **D-326~D-334**, 원장 [`EVIDENCE/S22/`](EVIDENCE/S22/README.md).
- **화면 셋 고도화 + Legacy 정리 ✅** — 결정 **D-335~D-340**.
- **화면 셋 UI/UX 마무리 ✅** (`b3c368c6`) — 홈 판의 높이 범위 · 레일 폭 · 「최근 완료 추이」
  비율 · 낱말 · 관리자 「운영」 세 묶음. 결정 **D-341~D-345**.
- **대시보드 높이 예산 ✅** (`ca49e7d8` · `3804bc0e`) — 판마다 바닥과 천장을 함께 주고, 자라는
  것은 판이 아니라 판 안의 한 칸이 맡는다. AI 도우미의 탭이 `{ head, detail }` 두 조각을 내고,
  `stickyHeader` 를 켠 표의 감싸는 상자가 스스로 안 굴러간다. 결정 **D-346 · D-347**.
- **목록 무한 스크롤 · 서버 필터/정렬 · 티켓 만들기 ✅** — 결정 **D-364~D-371**.

## 남긴 것 — 이번 회차가 **안 한** 것

정직하게 적는다. 셋(1~3)은 「시간이 없었다」가 아니라 **판단**이고, 넷째는 **못 잰 것**이며, 다섯째는 **이번 변경 밖**이다 — 세 가지를 같은 낱말로 적지 않는다.

1. **커서 페이징을 안 했다.** 전순서는 보장하지만(D-369) OFFSET 은 묶음 사이에 행이 삽입·삭제
   되면 여전히 건너뛴다. 감사·잡·알림이 append-heavy 라 실사용에서 겪는다 — 화면은 행 id 로
   중복만 거르고, 각 라우터 docstring 에 그 한계를 적어 뒀다. 선례는 이미 있다
   (`/api/work/backlog` + `WorkBoard.jsx`).
2. **관리 콘솔에 열 머리 필터를 아직 안 붙였다.** 부품(`TableHeaderCell` · `ColumnFilterPopover`)
   은 범용이고 티켓 3화면에 배선돼 있다. 관리 콘솔에 얹으려면 툴바 필터와 **같은 상태**를 보는
   조건 축(`filterAxes`)이 먼저 서야 하고, 그 앞에 `datascreen-view.js` 의 다중값 직렬화가
   필요하다(지금은 스칼라 전용이라 반복 키를 덮어쓴다). 사용자가 신고한 증상(후보가 지금 쪽
   것만)은 D-368 이 이미 닫았다.
3. **`backup`·`restore-drills` 의 `clientFilter` 를 아직 승격 안 했다.** 두 화면은
   `paginated` 가 아니지만 서버가 `.limit(50)`/`.limit(20)` 으로 자른다 — 「실패한 백업만」이
   51번째 이후에서는 구조적으로 답이 안 나온다. 계약 시험은 `cap` 선언이 있을 때 잘림 경고를
   요구하지만, 그 두 화면은 `cap` 을 아직 선언하지 않아 지금은 통과한다.
4. **우선순위·난이도 후보를 못 쟀다 — 그래서 아무것도 안 고쳤다.** `repository_native.py` 는
   후보를 **이미 그 값이 들어 있는 티켓에서만** 뽑는다(코드 주석이 그 한계를 스스로 적어 뒀다).
   「얇으면 표준 사다리를 합친다」가 계획이었고 판정 근거는 운영 DB 의 distinct 인데, 이 회차의
   실행 환경에서 그 읽기가 막혔다(원격 `sudo` 가 비밀번호를 요구하고 그것을 넘기는 것이 차단됐다).
   **못 쟀으므로 안 고쳤다** — 못 잰 것을 「값이 충분하더라」로 적지 않는다. 재는 방법은 그대로다:
   `select distinct priority, count(*) ...` 를 읽기 전용으로 한 번.
5. **문서 목록의 제목 열이 폭 0 인 것을 안 고쳤다** — 실브라우저에서 찾았지만 `HEAD` 의 빌드에서
   숫자가 똑같아 **이번 변경이 만든 것이 아니다**(D-373). 표 배치 계약 전부에 닿는 별개 작업이라
   `BACKLOG` 의 **P-59** 로 넘겼다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 소유 Session |
|---|---|---|
| **PostgreSQL** | ✅ **System of Record 다.** 운영이 그 위에서 돈다 | S2 ✅ · S4 ✅ · S9~S14 ✅ |
| **SQLite 제거** | ✅ 끝났다 | S13 ✅ · S14 ✅ |
| **Notion Migration** | ✅ 끝났다 — 마지막 설정 잔재는 S22 가 걷었다 | S13 ✅ · S14 ✅ · S20 ✅ · S22 ✅ |
| **AI** | ✅ 끝났다 | S9 ✅ · S10 ✅ · S11 ✅ |
| **Backup** | ✅ 끝났다 — S22 가 **운영 데이터로** 다시 증명했다 | S2 ✅ · S12 ✅ · S14 ✅ · S22 ✅ |

**UI 축은 W15 까지 왔다.** 근거와 수치는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).

## NEXT — 이 Transition/Renewal 계획의 Acceptance 는 끝났다

**새 Stage 를 자동으로 만들지 않는다.** S0~S22 로 세운 계획이 닫혔을 뿐이고, 이 제품의
다음 기능 개발은 평소대로 CLAUDE.md §7.0 의 일반 개발 흐름을 탄다.

남긴 것은 전부 Backlog 다 — 새 회차가 아니라 **소유자 없는 항목**이다:

1. **P-44** — 사슬의 서버 칸 982. 그 하나가 W8·W15 게이트의 마지막 축을 붙잡고 있다.
2. **P-54 · P-55 · P-56 · P-58** — S22 가 새로 적은 것 넷(넓은 화면의 빈 아래 / 곁열 판정
   위양성 의심 / 모달 검사 0회 실행 / 열 하나의 어휘 누락).
3. **P-50 · P-52** — 부르는 화면이 없는 라우터 둘. P-52 의 남은 물음은 S22 가 답했다.
4. **P-57** — 설치 로그 보관 기간.
5. **P-35 · P-37** — 옛 문서 미러 표와 담당자 축 통합(플랫폼 축).

## BLOCKERS

- 없음.
