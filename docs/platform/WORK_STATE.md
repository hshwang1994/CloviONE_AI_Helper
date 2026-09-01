# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-09-01** (승인·알림·프로젝트 결함 여섯 — D-385~D-389)
- phase: **F — Acceptance 완료(S22).** 그 뒤는 CLAUDE.md §7.0 의 **일반 개발**이다
- session: **승인·알림, 그리고 프로젝트 화면과 거기 딸린 것 전부에 버그가 있는지 보고 고쳤다.**
  가장 무거운 둘은 「화면은 하라고 하고 서버는 못 한다고 한다」였다.
  ① **위임받은 일반 사용자는 결재를 한 건도 못 했다**(D-385) — 결재 경로가 범위를 언제나
  결재자 **본인**의 관리 범위로 쟀는데 일반 사용자의 그것은 빈 집합이다. 내 결재함은 줄을
  보여 주고 `can_decide: true` 로 버튼까지 켜는데 누르면 전부 404 였다. 관리 콘솔 밖의
  사람을 위해 만든 `/my-approvals` 의 버튼이 통째로 죽어 있었다. 위임으로 결재할 때는
  **위임자의** 범위로 잰다 — 대리인은 위임자를 넘지 못하므로 IDOR 방어는 그대로다.
  ② **「내 업무 > 알림」의 '모두 읽음'이 관리 알림을 삼켰다**(D-386) — 목록 응답의 `unread`
  와 `read-all` 만 `audience` 를 안 받고 있었다. 빈 목록 위에 「안 읽음 3」이 뜨고, 그 숫자가
  띄운 버튼이 백업 실패·계정 잠금을 화면에 보인 적 없이 읽음으로 바꿨다.
  ③ **벨 배지의 낙관 갱신이 죽은 코드였다**(D-387) — 접두어를 `getQueryData` 에 넘겨 읽기는
  언제나 `undefined`, 쓰기는 아무 캐시에도 안 닿았다. 같은 결함을 목록 쪽에서는 이미
  고쳐 놓고 배지만 남아 있었다.
  ④ **`/projects` 의 「필터 지우기」가 아무것도 안 지웠다**(D-388) — 여섯 축을 세면서 둘만
  되돌려, 검색어로 0건이 된 화면에서 눌러도 주소가 한 글자도 안 바뀌었다.
  ⑤ **프로젝트 안에서 연 티켓이 프로젝트 목록으로 떨어졌다**(D-389) — 티켓 탭과 주간
  리포트가 「돌아올 자리」에 `/projects` 를 적고 있었다. 문서 탭만 맞았다.
  ⑥ 프로젝트 문서 탭이 상한을 넘긴 문서를 조용히 감췄다 — 서버가 주는 `total` 을 안 읽었다.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **이번 회차도 안 옮긴다.** 이유는 S11~S22 와 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: **깨끗하다**(이 회차를 커밋한 뒤 기준).
- s22_commit: `2f4fc587` · `1921f884` · prev_commit: `e8d39fd3` · `757b6e22`
- this_commit: **`7f221d6e`**(승인·알림·프로젝트 결함 여섯 · D-385~D-389)
- prev_session_commit: `0f93c572` · `3accdf0a` · `0e771a90` · `acd378ca`
- deployed: **`7f221d6e`** 가 운영에 나갔다 (2026-09-01 21:59 · `scripts/deploy-upgrade.sh`).
  Stage 0~18 전부 OK · `VERIFY_OK` · `UPGRADE_OK` · 스냅샷 `/var/backups/clovirassist/20260901-215720`.
  **스키마는 그대로다** — alembic `0025_ticket_body_doc` → `0025_ticket_body_doc`(표 94개 ·
  사용자 26명). 이번 회차는 프런트와 백엔드가 함께 바뀌었다(마이그레이션은 없다).
  **이번 커밋의 것이 실제로 올라갔다**: 새 진입 번들 `index.AsjPK74b.js` 가 200 이고 직전
  배포의 `index.-JF0krO5.js` 는 404 다. 프로젝트 고침이 사는 `UserRoutes.BoWMgWh7.js` 와
  알림 화면이 사는 `datascreen.CKfSgxY2.js` 도 200 이다. 백엔드도 서버에서 직접 확인했다 —
  `/opt/clovirassist` 의 `approvals/router.py` 에 위임자 범위 판정이, `notifications/` 의
  라우터와 서비스에 `audience` 인자가 들어 있다.
  스모크(`--cacert /etc/clovirassist/tls/clovirassist.gooddi.lab.crt` +
  `--resolve clovirassist.gooddi.lab:443:10.100.64.71`, 인증서는 sudo 로 읽는다):
  `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  `ssl_verify_result=0` · `postgresql`·`nginx`·제품 유닛 여섯 전부 active.
  순서는 언제나 **빌드 → 소스 고침 끝 → `check_bundle_fresh.py --write` → 커밋**이다.
  되돌리려면 `sudo /home/cloviradmin/clovirassist-upgrade/deploy/install.sh rollback --target /var/backups/clovirassist/20260901-215720`
- deployed_prev: `0f93c572`(2026-09-01 20:15 · 스냅샷 `20260901-201250`)
- verification: 새 시험 **열다섯**(파일 다섯 벌)을 전부 **빨간불부터 확인**했다 — 위임
  결재 둘 · 알림 audience 셋 · 벨 낙관 갱신 셋 · 프로젝트 필터 지우기 셋 · 돌아올 자리
  둘 · 문서 잘림 둘. 고침을 되돌리면 빨갛고 되돌려 놓으면 초록인 것을 짝으로 확인했다.
  공용 층(`NotificationBell.jsx` 은 시험 23개가, `registry/notifications.js`
  는 43개가 들여온다)을 건드렸으므로 vitest **전량**을 돌렸다 — 365 파일 **2,765 시험 전부
  초록**이고, 실패한 파일 하나(`registry-active-badge`)는 S11 이 걷은 `integrations` 화면을
  아직 부르는 수집 오류라 이 변경과 무관하다(§7.0 의 unrelated 기존 실패).
  백엔드는 승인·알림 이름이 걸린 시험 **275개 전부 초록**, 프로젝트 도메인 시험도 초록.
  `static_checks.sh --scope full` **`STATIC_CHECKS_OK`**(`BUNDLE_FRESH_OK` 포함).
- browser: **이번 회차는 실브라우저로 안 쟀다.** 고친 여섯은 브라우저가 아니라 요청·캐시·
  주소에서 갈리는 것이라 시험이 그 자리를 직접 짚는다(결재의 404, `read-all` 의 audience,
  react-query 키, 주소에 남는 조건, `state.from`). 「안 봤다」와 「봤고 통과했다」는 다른
  사실이므로 그렇게 적는다.
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
