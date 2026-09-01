# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-09-02** (「이슈 있음」을 켤 자리를 만든다 — D-398~D-402)
- phase: **F — Acceptance 완료(S22).** 그 뒤는 CLAUDE.md §7.0 의 **일반 개발**이다
- session: **「티켓 조건의 `이슈 있음` 이 무엇인가」에서 시작해, 그 조건을 아무도 켤 수
  없다는 것을 찾아 고쳤다.** 조건 자체는 한 줄이다 — `tickets.issue_flag = true`.
  ① **켜는 자리가 제품 어디에도 없었다**(D-398). 설계는 그것을 「사람이 켜는 플래그」라고
  적었고(D-349) 서버는 `issue_flag`·`blocked_flag`·`blocked_reason` 셋을 받는데, 목록·상세·
  작업 보드·회의·주간보고가 **읽기만** 했다. 그래서 그 필터는 이관 시점 데이터 말고는
  영원히 비어 있었다. `TicketEditModal` 에 「신호」 절을 넣었다 — 상태 격자와 **다른 축**이라
  따로 세우고, 사유 칸은 차단을 켰을 때만 선다.
  ② **켠 사실이 아무 데도 안 남았다**(D-399). `snapshot()` 이 신호 둘을 안 실어서 이슈를
  켠 편집은 before 와 after 가 똑같은 감사 기록이었고, 「바뀐 것만」 말하는 이력 화면에는
  그 줄이 빈 채로 섰다. 두 칸을 넣고 깃발은 「켜짐/꺼짐」으로 읽는다.
  ③ **사유가 요청 안의 키 순서에 걸려 있었다**(D-400). 저장소가 사유를 적용할 때 그
  시점의 차단 여부를 봐서, 사유가 깃발보다 먼저 오면 「막혔다 + 이유」를 한 번에 보낸
  저장에서 이유만 조용히 사라졌다. 지금까지는 스키마의 필드 순서가 우연히 지켜 줬다.
  ④ **같은 신호가 화면마다 다른 색이었다**(D-401). 어휘 표는 `lib/ticketSignals.js`
  하나인데 작업 보드와 회의 화면이 이름과 색을 다시 적어 뒀다 — 보드 한 화면 안에서 같은
  티켓의 「이슈 있음」이 목록에서는 보라, 위 타일에서는 주황이었고 지연과 차단은 타일에서
  둘 다 빨강이었다(묶음 A Exit 조건 위반). 공용 표로 되돌렸다.
  ⑤ **되돌려도 보라가 안 그려졌다**(D-402). `paletteAt` 이 톤 색을 팔레트 경로로 푸는데
  보라·틸·인디고는 `--badge-*-fg` CSS 변수라 `undefined` 가 나갔고, `border-color` 가
  기본값 `currentColor` 로 떨어져 **글자색 띠**가 그려졌다. 경로가 아닌 값은 그대로
  돌려주게 고치고, 톤 표를 `kit.jsx` 한 곳으로 모았다.
  ⑥ 낡은 문구 둘 — `이슈` 는 마이그레이션 0018 이후 상태가 아닌데 AI 도우미가 「상태가
  이슈인 티켓이 없습니다」로, 내 업무량이 「막힘(이슈)」로 그렇게 부르고 있었다.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **이번 회차도 안 옮긴다.** 이유는 S11~S22 와 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: **깨끗하다**(이 회차를 커밋한 뒤 기준).
- s22_commit: `2f4fc587` · `1921f884` · prev_commit: `e8d39fd3` · `757b6e22`
- this_commit: **`d6a32933`**(신호를 켤 자리 + 어휘·톤 통일 · D-398~D-402) · 앞 회차 `1d6e0514`(D-391~D-397)
- prev_session_commit: `b27f948c` · `7f221d6e` · `0f93c572` · `3accdf0a`
- deployed: **`d6a32933`** 가 운영에 나갔다 (2026-09-02 08:03 · `scripts/deploy-upgrade.sh`).
  Stage 0~18 전부 OK · `VERIFY_OK` · `UPGRADE_OK` · 스냅샷 `/var/backups/clovirassist/20260902-080057`.
  **스키마는 그대로다** — alembic `0025_ticket_body_doc` → `0025_ticket_body_doc`(표 94개 ·
  사용자 26명). 프런트가 바뀌어 번들을 다시 만들었다 — 새 진입 번들 `index.DSBT6Jpt.js` 가
  200 이고(`ssl_verify_result=0`), 새 `kit.B9Kw3lwL.js` 도 200 이다.
  **이번 커밋의 것이 실제로 돌고 있다**: `/opt/clovirassist` 의 `snapshot()` 이
  `blocked`·`issue` 를 포함한 여덟 칸을 돌려주고, `HISTORY_FIELDS` 가 그 둘을 「이슈 있음」·
  「차단됨」으로 부르며, `_history_value` 가 「켜짐/꺼짐」으로 답한다. 배포된
  `UserRoutes.B-NXGEZD.js` 에 새 편집 칸(`te-blocked-reason`)이 들어 있다.
  스모크(`--cacert /etc/clovirassist/tls/clovirassist.gooddi.lab.crt` +
  `--resolve clovirassist.gooddi.lab:443:10.100.64.71`, 인증서는 sudo 로 읽는다):
  `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  `clovirassist-web`·`postgresql`·`nginx` 를 포함한 유닛 다섯이 전부 active.
  순서는 언제나 **빌드 → 소스 고침 끝 → `check_bundle_fresh.py --write` → 커밋**이다.
  되돌리려면 `sudo /home/cloviradmin/clovirassist-upgrade/deploy/install.sh rollback --target /var/backups/clovirassist/20260902-080057`
- deployed_prev: `1d6e0514`(2026-09-02 00:47 · 스냅샷 `20260902-004719`) · `b27f948c`(2026-09-01 22:53)
- verification: 새 시험 **열여덟**(파일 셋)을 **전부 빨간불부터 확인**했다 — 프런트 편집
  여섯 · 어휘 다섯 · 백엔드 일곱. 백엔드 일곱 중 **셋이 고침 전에 빨갛다**(사유 순서 ·
  감사 스냅샷 · 이력 어휘)고, 나머지 넷은 전후 모두 초록인 회귀 방지막이라 그 사실을
  시험에 적었다. 공용 층(`kit.jsx`)을 건드렸으므로 vitest **전량**을 돌렸다 — 370 파일
  **2,792 시험 전부 초록**이고, 빨간 파일 하나(`editable-body-identity-reset`)는 **깨끗한
  HEAD 에서도 똑같이 빨갛다**(jsdom 의 `getClientRects` 미구현). 백엔드는 ticket·work·
  audit·history·sprint·home·weekly 이름이 걸린 시험이 전부 초록이고, 빨간 둘
  (`test_review3_fixes` · `test_ticket_create`)도 깨끗한 HEAD 에서 똑같이 빨갛다 — §7.0 의
  unrelated 기존 실패다. `static_checks.sh --scope full` **`STATIC_CHECKS_OK`**
  (`BUNDLE_FRESH_OK` 포함).
- browser: **실브라우저로 한 바퀴를 돌았다** — 새 하네스 `scripts/ui_qa/signal_e2e.py`
  (`local_capture --harness signal_e2e`). 팀 티켓에서 편집을 열어 「이슈 있음」을 켜고
  저장 → 목록에 표식이 서고(`rgb(74,62,140)`) → 작업 보드의 「이슈 있음」 타일이 0 에서
  1 로 올랐다. 타일 셋의 위색 띠는 차단 `rgb(179,38,30)` · 지연 `rgb(138,83,0)` ·
  이슈 `rgb(74,62,140)` 으로 **서로 다르다** — 고치기 전에는 보라가 글자색으로 떨어졌으므로
  이 값이 곧 그 고침의 증거다. 색은 좌표가 아니라 **계산된 스타일**로 쟀다.
- capture: 전량 정본은 **`s22-final`** 그대로다. 이번 회차도 캡처 하네스를 전량으로 안 돌렸다.
  **부분 캡처는 전량 원장을 안 덮는다**(D-306) — `capture_labels.after` 를 옮기지 않았다
- ui_gate: `--stage plan` **PASS**. `--stage wave`(W15)는 **초록이 아니다** — 남은 것은
  **P-44** 의 기록 형식(사슬의 서버 칸 982)과 그것이 붙잡고 있는 축들이다. 상세는
  [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **94 표**다. alembic head 는 **`0025_ticket_body_doc`** 다 — 이 회차는 표도 칸도
  안 건드렸다(신호 세 칸은 0018 이 이미 만들어 뒀고, 이번에는 그것을 **쓰는 길**만 열었다).

## 이번 회차가 **안 고친** 것 — 그리고 그 이유

- **`Callout` 판형이 넓은 화면에서 오른쪽을 비운다.** 백업 화면의 새 경고 배너가
  1606×68 에 잉크 15% 로 `oversized_empty_surface` 를 띄운다. 이것은 새 결함이 **아니다** —
  `s22-final` 원장에 같은 부품의 같은 표본이 **30건** 있다(`/diagnostics` · `/mail` …).
  공용 부품 하나의 판형 문제라 호출부 67곳에 닿고, 이번 요청 범위 밖이라 안 건드렸다.
- **`text` 열의 머리글과 값이 서로 다른 자리에 선다.** 「파일」·「원본」 열이 그렇다.
  머리글은 언제나 가운데, 몸통은 값의 뜻이 정한다는 **문서화된 계약**이다
  (`ui/columnTypes.js` 의 «머리글은 언제나 가운데다» 절). 계약을 바꾸는 것은 별개 결정이다.
  「서버 파일」열은 배지인데 `text` 로 선언돼 있어서 그것만 `status` 로 고쳤다.

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

## 앞선 회차가 한 것 — 목록 · 필터/정렬 · 티켓 만들기

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
3. ~~**`backup`·`restore-drills` 의 `clientFilter` 를 아직 승격 안 했다.**~~ **닫았다**
   (2026-09-02 · D-394) — 조건을 서버가 받고(`status`·`file_state`·`ok`) 상한은
   `cap`/`capWarning` 으로 밝힌다. 상한 너머의 실패를 조건으로 찾을 수 있는지는
   `tests/integration/test_backup_list_filters.py` 가 표본을 상한 밖에 심어 확인한다.
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
