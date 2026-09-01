# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-09-02** (프로젝트 화면의 넘침·잘림, 그리고 백업 전반 — D-391~D-397)
- phase: **F — Acceptance 완료(S22).** 그 뒤는 CLAUDE.md §7.0 의 **일반 개발**이다
- session: **프로젝트 화면의 「그리드가 넘어간다 · 차트가 잘린다」와 백업에 딸린 것 전부를
  보고 고쳤다.** 눈으로 고르지 않고 실브라우저에서 **좌표로** 쟀다 — 어느 요소가 자기 칸
  오른쪽을 몇 픽셀 넘는가, 어느 글자가 `scrollWidth > clientWidth` 인가.
  ① **표의 마지막 열이 표 밖으로 나갔다**(D-391). 원인은 어휘였다 — `DateCell` 은 언제나
  「날짜와 시각」(120px)을 그리는데 그 열들이 `type:"date"`(8.5rem)나 더 좁은 명시 폭으로
  선언돼 있었다. 필요한 폭은 9.5rem 이고, `render` 가 있는 nowrap 열에는 `overflow:hidden`
  이 안 붙으므로(kit.jsx 의 의도된 규칙) 모자란 만큼이 **잘림이 아니라 침범**으로 나왔다.
  1920 실측 8px, 1366 실측 8px. 공용 `dateCol()` 과 화면 여섯이 같은 모양이라 공용 층에서
  고쳤고, 넓힌 뒤 열한 화면을 다시 찍어 `horizontal_overflow` **22/22 통과**를 확인했다.
  ② **「티켓 발생 추이」의 날짜 눈금이 두 가지로 틀렸다**(D-392). 「6/14」가 「6/1」로
  **말줄임표 없이** 잘렸고(1칸 17px · 390 에서는 3px), 게다가 **그림이 보여 주는 구간과
  다른 날짜**를 말했다 — 막대는 8/29~9/1 네 칸인데 눈금은 6/4~8/23 이었다. 축을 그림에
  넘겼다: 축은 지금 보이는 카테고리를 알고, 자리가 모자라면 자르는 대신 뺀다.
  ③ Health 판의 원이 1558px 판 **한가운데**에 혼자 떠 있었다(잉크 18%) — 점수와 그것을
  만든 규칙이 한 줄에서 함께 읽히게 나란히 세웠다. 「주간 추세」는 숫자 한 줄이던 것을
  스파크라인 + 가로 목록으로 바꿨고, 한 주뿐이면 그 사실을 문장으로 적는다.
  ④ **백업 화면의 「백업 실행」이 «...» 메뉴 안에 빨간 글씨로 숨어 있었다**(D-393).
  「확인을 한 번 묻는다」를 「파괴적이다」로 읽은 한 줄 때문이다. `primary` 는 그 화면의
  주 동작이므로 언제나 머리에 선다.
  ⑤ **상한이 있는 목록의 조건이 화면 안에서만 돌았다**(D-394 · 남겨 뒀던 항목 3). 「실패한
  백업만」이 실제로는 「최근 50건 안의 실패만」이었다. 조건을 서버로 옮기고 상한은
  `cap`/`capWarning` 으로 밝힌다.
  ⑥ **「백업 화면에서 예약을 켜세요」라는 알림이 가리키는 화면에 켤 것이 없었다**(D-395).
  백업 화면에 「백업 일정 설정」(설정 항목 딥링크)을 두고, 예약·마지막 백업·보존을 요약
  줄로, 경고를 **문장 그대로** 낸다(예전에는 「1건」이라는 숫자 카드였다).
  ⑦ **보관 기간을 고칠 자리가 제품 어디에도 없었다**(D-396) — 화면은 그 값을 카드로 보여
  주고 서버는 그것으로 지우는데 편집기에는 개수 칸만 있었다.
  ⑧ **내려받은 직후에 「서버에서 삭제」가 안 떴다**(D-397) — 그 단추의 조건이 서버가 방금
  남긴 값인데 목록을 다시 안 읽었다. D-204 의 두 번째 절반이 화면에 없었다.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **이번 회차도 안 옮긴다.** 이유는 S11~S22 와 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: **깨끗하다**(이 회차를 커밋한 뒤 기준).
- s22_commit: `2f4fc587` · `1921f884` · prev_commit: `e8d39fd3` · `757b6e22`
- this_commit: **`1d6e0514`**(프로젝트 넘침·잘림 + 백업 전반 · D-391~D-397) · 앞 회차 `b27f948c`(D-390)
- prev_session_commit: `7f221d6e` · `0f93c572` · `3accdf0a` · `0e771a90`
- deployed: **`1d6e0514`** 가 운영에 나갔다 (2026-09-02 00:47 · `scripts/deploy-upgrade.sh`).
  Stage 0~18 전부 OK · `VERIFY_OK` · `UPGRADE_OK` · 스냅샷 `/var/backups/clovirassist/20260902-004719`.
  **스키마는 그대로다** — alembic `0025_ticket_body_doc` → `0025_ticket_body_doc`(표 94개 ·
  사용자 26명). 이 회차는 프런트가 바뀌어 번들을 다시 만들었다 — 새 진입 번들
  `index.BD0VOgjF.js` 가 200 이고(`ssl_verify_result=0`), 새 청크 `Sparkline.BARvLvDJ.js`
  도 설치처에 있다.
  **이번 커밋의 것이 실제로 돌고 있다**: `/opt/clovirassist` 의 `list_backups` 가
  `(request, status, file_state, db)` 를 받고 `list_rehearsals` 가 `(ok, db)` 를 받는다.
  `BACKUP_LIST_LIMIT=50` · `REHEARSAL_LIST_LIMIT=20` 이고, 서버 venv 로 직접 불러
  `backup_health_alert_reason` 이 「백업 화면의 '백업 일정 설정'에서」로 답하는 것을
  확인했다(예전 문구가 가리키던 자리에는 켤 것이 없었다).
  스모크(`--cacert /etc/clovirassist/tls/clovirassist.gooddi.lab.crt` +
  `--resolve clovirassist.gooddi.lab:443:10.100.64.71`, 인증서는 sudo 로 읽는다):
  `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  `clovirassist-web`·`postgresql`·`nginx` 를 포함한 유닛 다섯이 전부 active.
  순서는 언제나 **빌드 → 소스 고침 끝 → `check_bundle_fresh.py --write` → 커밋**이다.
  되돌리려면 `sudo /home/cloviradmin/clovirassist-upgrade/deploy/install.sh rollback --target /var/backups/clovirassist/20260902-004719`
- deployed_prev: `b27f948c`(2026-09-01 22:53 · 스냅샷 `20260901-225325`) · `7f221d6e`(21:59)
- verification: 새 시험 **열여덟**(파일 다섯 벌)을 **전부 빨간불부터 확인**했다 — 차트 축
  여섯 · 어휘 둘 · 주 동작 하나 · 내려받기 하나 · 보존 기간 셋 · 서버 필터 넷(그중 셋이
  고침 전에 빨갛다, 넷째 「모르는 값은 무시」는 전후 모두 초록이라 그 사실을 시험에 적었다).
  공용 층(`DataScreen`·`columnHelpers`)을 건드렸으므로 vitest **전량**을 돌렸다 —
  368 파일 **2,781 시험 전부 초록**이고, 빨간 파일 둘(`registry-active-badge` ·
  `editable-body-identity-reset`)은 **깨끗한 HEAD 에서도 똑같이 빨갛다**(각각 S11 이 걷은
  화면을 부르는 수집 오류, jsdom 의 `getClientRects` 미구현). §7.0 의 unrelated 기존 실패다.
  백엔드는 backup·restore·settings·registry 이름이 걸린 시험 **231개**와 backup·worker·
  notification·project·admin 이름이 걸린 시험 **576개**, `tests/security` **전량**이 초록이다.
  `static_checks.sh --scope full` **`STATIC_CHECKS_OK`**(`BUNDLE_FRESH_OK` 포함).
- browser: **이번 회차는 실브라우저로 쟀다.** 고친 것의 절반이 좌표라 그래야 했다.
  `/projects` · `/projects/{id}` · `/backup` · `/backup?tab=restore-drills` · `/settings` 를
  1366·1920·390 에서 열어 **모든 요소의 오른쪽 넘침과 글자 잘림을 직접 쟀다**. 고치기 전
  넘침 다섯 자리 · 잘린 날짜 눈금 아홉 개였고, 고친 뒤 **프로젝트 두 화면에서 0**이다
  (남은 것은 `.sr-only` 머리글 둘 — 폭 1px 은 그 부품의 계약이다). 날짜 눈금은 이제
  8/30·8/31·9/1·9/2 로 **막대가 서 있는 그 날짜**를 말한다.
- capture: 전량 정본은 **`s22-final`** 그대로다. 이번 회차도 캡처 하네스를 전량으로 안 돌렸다.
  **부분 캡처는 전량 원장을 안 덮는다**(D-306) — `capture_labels.after` 를 옮기지 않았다
- ui_gate: `--stage plan` **PASS**. `--stage wave`(W15)는 **초록이 아니다** — 남은 것은
  **P-44** 의 기록 형식(사슬의 서버 칸 982)과 그것이 붙잡고 있는 축들이다. 상세는
  [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **94 표**다. alembic head 는 **`0025_ticket_body_doc`** 다 — 이 회차는 표도 칸도
  안 건드렸다(백업 목록 조건은 이미 있는 칸을 읽기만 한다).

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
