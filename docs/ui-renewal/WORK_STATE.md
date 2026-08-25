# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-25T18:40:00+09:00
- wave: W10
- wave_status: **제품 축은 닫혔다.** S19 가 W10 화면의 결함을 뿌리에서 고쳤고, Health
  Correction 이 그 회차가 남긴 결함 넷을 더 닫았다. **기능 축(Flow 감사)과 시각 축(캡처)은
  안 쟀다** — 그 둘은 이제 **Acceptance 축**이고 소유는 S21·S22 다(`MASTER_PLAN.md` §9.4 ·
  **D-314**). 진행 단위는 같은 문서 §14.3
- build_index_sha256: `39187bca03b30bc3` (S17 `s17-after`). **S19 도 HC 도 이 값을 안 올린다** —
  번들은 다시 만들었지만 캡처를 안 찍었다. S16 `dfd1cadb396b788d` · S15 `c9cab277de958811` ·
  W5 `08b5525cb2f52618` · W4 `1a48d92ee9e55127` · W3 `c03113861aaa5138` ·
  W2 `344ce7e7fc221246` · W1 `104e49366bf030f4` · Before `9ab4d470163e475a`
- coverage_gate: `--stage plan` **PASS**. `--stage wave` 는 S19 도 HC 도 **안 돌렸다** —
  W8 잔여(P-44)를 여는 일이고 그것은 Acceptance 축이다. `capture_labels.after` 는
  `s17-after` 그대로다
- surfaces: W10 의 20 화면은 **`NOT_AUDITED` 그대로**다. 제품을 고친 것과 그 화면을 감사한
  것은 다른 사실이라 원장에 완료로 적지 않는다 — 그리고 **회차가 지나갔다는 사실은 그 둘 중
  어느 것도 아니다**(D-314). 바뀐 행은 하나뿐이다: `user_my-display` 가
  `state_variant · alias_of=user_profile` 이 됐다(D-310, 소스가 실제로 `<Navigate>` 다)
- tests: 표적 재검증 전부 초록. 🔴 **S19 가 「HEAD 에 이미 있다」고 등록한 프런트 실패 8건이
  이제 0 이다** — 셋은 제품 결함이었고(P-45·P-46·P-49) 셋은 시험이 틀렸다(P-47). 시험 강도
  게이트(P-38)도 15건에서 0 이 됐다
- remaining: **P-44 는 손대지 않았다**(S18 잔여 — Acceptance 소유). 새로 등록한 것은 둘이다 —
  **P-50**(`/api/team-docs` 가 프런트 호출 0건인데 살아 있다 · P-41 과 같은 묶음)과
  **P-51**(티켓 읽기 golden 7건이 S15 이후 안 갱신됐다. HC 변경을 stash 한 HEAD 에서도 같다)
- full_snapshot: **HC 마지막 Full 1회.** 정적 전량 PASS · 프런트 전량 **329 파일 / 2,451건
  전부 PASS** · 백엔드 전량 FAIL 7건(전부 P-51, HEAD 에서도 같다)
- commit: **`2c3e6c60`** (HC) · `ee2e4118` (S19)
- suppressions: **1건 (SUP-01)** — 칸반 레인의 균등 격자. 만료 2026-10-20
- plan: `docs/ui-renewal/PLAN.md`(UI 축 정본) · `DIRECTIVE_v7.txt`(원 지시서) ·
  **`docs/platform/MASTER_PLAN.md`(제품 전체 정본 — 여기가 상위다)**

## NOW
**Health Correction 이 S1~S19 산출물 전체를 독립적으로 훑었다.** 물은 것은 하나다 —
**QA 를 만족시키려고 제품이 이상해진 자리가 어디인가.**

🔴 **완료 계약이 두 축을 한 Exit 에 묶고 있었다**(D-314). S19 의 Exit 는 「각 화면 Functional
Flow 가 최소 `IN_PROGRESS`」였는데, 그 회차가 한 일은 제품 결함을 고친 것이고 Exit 는 감사
원장의 상태를 요구했다. 그 묶음은 양방향으로 해롭다: 한 줄 import 를 고치는 일이 20 화면
감사를 통과해야 끝나거나(그래서 아무도 작은 결함을 안 고친다 — `PATH_SEP` 한 줄이 실제로
회차 하나를 건너뛰었다), 아니면 Flow·Capture 가 「회차가 지나가며 채우는 칸」이 된다.
계약을 **Implementation** 과 **Acceptance** 로 갈랐다. **원장은 안 달랬다.**

🔴 **무효화 표가 없는 키를 가리키고 있었다**(D-313). `document-views.js` 가 든 접두사는
`["team-docs"]`·`["team-doc"]` 인데 S14 가 문서 축을 옮기면서 화면 키는 `["knowledge", …]` 가
됐다. `invalidateQueries` 는 **없는 키를 지워도 오류가 아니다** — 그래서 휴지통에서 문서를
복원·영구 삭제하면 무효화가 매번 돌고 매번 아무것도 안 지웠다. 복원한 문서가 30초 동안
`/knowledge` 에 안 나타나고, 영구 삭제한 문서의 상세는 그동안 멀쩡히 열린다. **그것을 재던
시험도 같은 옛 키를 스스로 심고** 있어서 세 사례가 전부 초록이었다 — 시험이 계약이 아니라
사라진 구현 세부를 고정하면 결함을 못 본다. 화면이 실제로 쓰는 키로 바꾸고, 옛 키로 되돌려
3건이 전부 빨개지는 것을 확인한 뒤 복구했다.

나머지 제품 결함 셋:

* **`PATH_SEP` 미임포트로 티켓 상세의 공유 범위 판이 죽었다**(P-45). 한 줄 import 로 달래지
  않고 뿌리로 고쳤다 — 경로 문자열은 `ui/OrgPath.jsx::pathText` 하나가 만든다. 같은 세 줄을
  손으로 다시 쓰던 자리 둘(`ScopeBar.jsx`·`UserMenu.jsx`)도 그 함수로 모았다
* **시간 레일이 선언만 있고 안 그려졌다**(P-49). `TicketHistory.jsx` 의
  `borderInlineStartColor: "divider"` — 논리 이름에는 MUI 가 팔레트 경로를 안 풀어 준다
* **열 이름이 표준 동사표와 어긋났다**(P-46). `created_at` 을 registry 9곳은 「추가」로
  부르는데 `MyTickets`·`Projects` 만 「생성」이었다. 화면 문구의 가운뎃점 하나도 걷었다

QA 자산에서 걷은 것: **같은 계약을 두 계층이 각자 들고 있었다.** UX Writing 두 규칙이 bash
grep 과 vitest 두 곳에 있었고 허용 목록이 실제로 갈라져 vitest 만 빨간 채였다 — bash 사본을
걷고 vitest 를 정본으로 삼았다. `verify.py` 안의 죽은 정책 둘도 걷었다(같은 판정이
`static_checks.sh` 에 이미 있다). **`filter-chain-contract` 3건은 제품 결함이 아니었다**
(P-47) — 상태 조건은 다중 선택이고 MUI 의 다중 Select 는 항목을 눌러도 메뉴를 안 닫는 것이
정답이다. 시험 도우미가 단일 선택 시절 그대로였다. **시험 강도 원장(P-38, 15건)을 사실로
닫았다** — 계약이 어디로 갔는지 파일마다 확인하고 대체를 명명했으며, 대체가 정말 없던 것
하나(일괄 삭제 확인)는 계약이 살아 있는 화면에서 시험을 새로 썼다.

**S19 이 남긴 QA 넷은 유지한다** — `optical_alignment` 와 D-307 은 반례 다섯으로 양방향
검증돼 있고 `--fail-on` 기본에 없다.

## NEXT
다음 작업은 **S20 — 관리자 IA + 관리자 콘솔**이다. 그 회차의 Exit 는 **§9.4-A** 다 —
Coverage·Flow·Pilot·Capture·Evidence 를 완료 조건으로 걸지 않는다.

넘기는 것 넷:

1. **P-50 신규** — `/api/team-docs` 를 프런트가 한 번도 안 부르는데 라우터 11개·1,918줄과
   가시성 갈래가 살아 있다. **P-41(화면에 남은 Notion 잔재)과 같은 묶음**이다
2. **W10 Flow 감사(P-29)와 S18 캡처·기록 형식(P-44)** 은 그대로다. 소유는 **S21·S22**
3. **P-39(백엔드 회귀 넷)** 그대로. 그중 둘은 「옛 축을 지키자」는 계약이라 사람이 정해야 한다
4. **P-40 · P-42 · P-43** 은 소유 회차 그대로다(S22 · S20 · S22)

실행 규칙의 우선순위: `docs/platform/MASTER_PLAN.md` §9.3(**D-208**)과 §9.4(**D-314**)가
우선한다. Whole-product Full Capture 는 **S22 에서 1회**다.

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
