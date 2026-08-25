# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-25T13:40:00+09:00
- wave: W8
- wave_status: **기능 축 완료, 시각·반응형 축 미측정.** 진행 단위는 Wave 가 아니라
  **Session S15~S20** 이다 — 재배치 표는 `docs/platform/MASTER_PLAN.md` §14.3
- build_index_sha256: `39187bca03b30bc3` (S17 `s17-after`). **S18 은 이 값을 안 올린다** —
  번들은 다시 만들었지만 캡처를 다시 재지 않았다. S16 `dfd1cadb396b788d` ·
  S15 `c9cab277de958811` · W5 `08b5525cb2f52618` · W4 `1a48d92ee9e55127` ·
  W3 `c03113861aaa5138` · W2 `344ce7e7fc221246` · W1 `104e49366bf030f4` ·
  Before `9ab4d470163e475a`
- coverage_gate: `--stage plan` **PASS** · `--stage wave`(**W8**) **FAILED (274건)**.
  셋 다 **기록 형식**이고 화면 결함이 아니다 — 아래 `remaining` 참고.
  `capture_labels.after` 는 `s17-after` 그대로다(S18 이 캡처를 다시 안 찍었다)
- pilot: `s18-pilot` — **258 Flow 중 252 PASS / 6 FAIL** (1,121초, 실 브라우저 Chromium +
  로컬 PostgreSQL 씨앗). 산출물 `dist/ui-qa/pilot/flows.json`. 17 Surface 의
  `functional_audit` 에 그 결과를 그대로 적었다
- surfaces: W8 의 17 화면은 **`IN_PROGRESS`** 다. 기능 축은 실측으로 끝냈고 시각·반응형 축은
  이 회차가 다시 재지 않았다 — 안 본 것을 봤다고 적지 않는다
- retired: **3 화면**(`user_team-docs-id` · `admin_notion-console` ·
  `admin_settings__integration`). 제품에 없는데 원장에 살아 있던 것을 C1c 가 찾았다(D-299)
- tests: 신규 백엔드 회귀 **5파일 46건 PASS**(역방향 커버리지 17 · 쓰기 경합 9 · Health 사유
  모양 12 · 티켓 이력 권한·검열 5 · 티켓 댓글 알림 3). 프런트 신규 1파일 5건 PASS,
  `DataScreen` 관련 6파일 35건 PASS. **전체 회귀는 이 회차에서 안 돌렸다**
- remaining: **비차단 잔여 3종은 P-44 다** — ① C11 사슬의 서버 칸 243건(하네스가
  `/openapi.json` 에서 핸들러 표를 만드는데 제품이 그 경로를 안 연다) ② 조건 다섯 축이 아직
  없는 화면 24건 ③ 화면 사슬 칸이 빈 Flow 7건. 실패 6건도 같은 항목이다
- suppressions: **1건 (SUP-01)** — 칸반 레인의 균등 격자. 만료 2026-10-20
- plan: `docs/ui-renewal/PLAN.md`(UI 축 정본) · `DIRECTIVE_v7.txt`(원 지시서) ·
  **`docs/platform/MASTER_PLAN.md`(제품 전체 정본 — 여기가 상위다)**

## NOW
**S18 이 W8 Pilot 의 기능 축을 실측으로 닫았다.** 이번 회차가 답한 질문은 둘이다 —
**원장이 제품과 같은 것을 말하는가**, 그리고 **한 화면이 200 을 받았다고 완료인가.**

🔴 **원장에는 있는데 제품에는 없는 화면이 셋 있었다.** W0 이 세운 C1 은 «소스 → 원장» 한
방향만 본다. 반대쪽은 아무 검사도 안 건드렸고, 그래서 열리지도 않는 화면 셋이 «아직 안 본
화면» 으로 남아 다음 회차를 기다리고 있었다. 반대 방향 조건(**C1c**)을 세우고, 없어진 화면은
`RETIRED` 로 적는다 — 「안 봤다」와 「없다」는 같은 칸에 적으면 안 된다(**D-299**).

같은 회차가 닫은 것 넷:

* **서버를 안 부르는 것이 정답인 Flow 를 선언하게 했다**(**D-300**). 모달을 열고 닫는 것,
  필수값이 빈 채 제출이 막히는 것은 부르지 않는 것이 맞다. 그런 Flow 에 서버 칸을 요구하면
  답이 둘뿐이다 — 지어내거나(거짓), 영원히 `IN_PROGRESS` 로 두거나. 이제 `server_free` 에
  **왜 안 부르는지**를 적으면 화면 사슬 셋을 대신 요구한다
* **쓰기 Flow 는 다른 화면에서 그 값을 다시 찾는다**(**D-301**). 29건에 `cross_surface` 를
  달았다 — 티켓 편집은 `/my-tickets` 의 그 행에서, 게시글 삭제는 목록에서 사라졌는지로,
  설정 초안은 **새로 읽어도 안 들어가 있는지**로 확인한다
* **실브라우저가 조용한 결함 넷을 찾았다**: `/me` 가 옛 Health 스냅샷을 만나면 500 이던 것
  (**D-302**) · 티켓 댓글 알림이 `NameError` 로 통째로 죽어 담당자에게 한 건도 안 가던 것 ·
  조건이 붙은 주소로 들어오면 화면이 그 조건을 **주소에서 지우던 것**(**D-304**) ·
  QA 씨앗이 제품에 없는 상태 낱말(`done`)을 심어 «완료» 조건이 언제나 0건이던 것
* **분할 뷰의 중복 조건 입구를 내렸고**(**D-303**), 티켓 상세의 가장 큰 공백이던 **활동 이력**을
  권한과 «바뀐 칸» 으로 좁혀 열었다(**D-305**)

**시각·반응형 축은 이 회차가 재지 않았다.** 캡처를 다시 찍지 않았으므로 17 화면은
`IN_PROGRESS` 로 남는다 — `DONE` 은 시각 감사와 After 캡처가 함께 있어야 한다.

## NEXT
다음 작업은 **S19 — 나머지 User Route** 다(Backlog **P-29**). 시작점은
`docs/platform/WORK_STATE.md` 이고 이 파일은 그 회차가 다시 연다.

S18 이 다음 Session 에게 넘기는 것 넷:

1. **Flow 표가 코드로 서 있다.** `scripts/ui_qa/pilot_kit.py`(공용 조작) +
   `pilot_b*.py`(화면별 258 Flow) + `pilot_e2e.py`(실행기) + `pilot_record.py`(원장 기록).
   새 화면은 `flow(...)` 한 줄과 `act` 하나를 더하면 되고, 결과는
   `python -m scripts.ui_qa.pilot_record --flows dist/ui-qa/pilot/flows.json` 이 옮겨 적는다
2. **W8 의 시각·반응형 축이 열려 있다.** 캡처 라벨 `s18-after` 로 12 Route 를 찍고
   `--capture s18-after` 로 기록하면 17 화면이 `DONE` 후보가 된다(P-44 ①과 함께)
3. **조건 다섯 축**(복합·쪽 초기화·경합·캐시 키·뒤로가기)은 `pilot_kit` 에 부품으로 있다 —
   `compound` · `page_reset` · `no_page_axis` · `race` · `cache_key` · `back_forward`
4. **범위 밖으로 넘긴 것**: P-38 · P-39 · P-41 · P-42 · P-43 · **P-44**(S18 잔여)

승격 예정 Gate 는 소유 Session 을 따라간다: `detail_side_imbalance` → S19 ·
`brand_presence` → S22.

실행 규칙의 우선순위: S15~S20 에는 `docs/platform/MASTER_PLAN.md` §9.3(**D-208**)이 우선한다.
`PLAN.md` 의 「Wave 종료마다 전체 Regression」 조항은 **W0~W5 가 그렇게 했다는 기록**이고
재개되는 Session 에 적용하지 않는다 — Whole-product Full Capture 는 **S22 에서 1회**다.

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
