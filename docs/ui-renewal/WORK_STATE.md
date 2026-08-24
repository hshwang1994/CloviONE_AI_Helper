# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-25T04:10:00+09:00
- wave: W7
- wave_status: **완료 (S17).** 진행 단위는 Wave 가 아니라 **Session S15~S20** 이다 —
  재배치 표는 `docs/platform/MASTER_PLAN.md` §14.3, 계획 전체는 그 파일 §9 다
- build_index_sha256: `aa4ec9579a009725` — **S17 캡처(`s17-after`)가 찍은 번들**.
  S16 `dfd1cadb396b788d` ·
  S15 `c9cab277de958811` · W5 `08b5525cb2f52618` · W4 `1a48d92ee9e55127` ·
  W3 `c03113861aaa5138` · W2 `344ce7e7fc221246` · W1 `104e49366bf030f4` ·
  Before `9ab4d470163e475a`
- coverage_gate: `--stage plan` **PASS** · `--stage wave`(**W7**) **PASS** (억제 1건 — 아래 `suppressions`).
  `capture_labels.after` 를 `s17-after` 로 옮겼다. **C10c 가 다시 실제로 걸렸다** — 승격된
  아홉이 `--fail-on` 으로 걸린 채 돌았고 그중 `mascot_visible_size` 가 이번에 새로 승격됐다
- static_checks: **FAILED — S17 이 만든 것이 아니다.** `check_test_strength.py` 가 기준
  `eec4886c` 대비 **15건**을 든다(전부 S13·S14 가 남긴 선언 미비, 소유는 **P-38**).
  S17 이 건드린 시험 넷은 사유를 적었고 `--base 51c926ee` 로는 **초록**이다.
  S17 이 더한 검사: `gen_mascot_bounds.py --check`(클로비 자산 경계 잠금 신선도)
- tests: frontend `npx vitest run --testTimeout=20000` **2,439 PASS / 0 FAIL**(파일 327).
  **P-34 의 셋이 닫혔다** — 셋 다 화면이 아니라 시험이 틀렸다. S17 신규 시험 **24건** PASS.
  backend `tests/regression/test_mascot_visible_bounds.py` **6 PASS**.
  ⚠️ 기본 타임아웃 5초로 돌리면 이 기계에서 부하 때문에 무관한 파일이 빨개진다
- 실측 (`s17-after` — 15화면 × 2뷰포트 × 2테마 = **60페이지**, E5 대로 변경 Surface만):
  승격 아홉이 전부 **fail 0**. S16 과 겹치는 48페이지에서 상태가 바뀐 것은
  `dead_blank_region` **fail→pass 4건**뿐이고 나빠진 것은 **0** 이다
- 상세 밴드 (`s17-detail-zoom` — 상세 3화면 × **1920·2560·3072·3840** × 2테마 = 24페이지):
  R-90 이 요구한 «긴 프로젝트명 실데이터 × FHD/QHD/4K × Zoom 3단계». 4K 패널의 확대
  100/125/150% 가 곧 CSS 폭 3840/3072/2560 이라 그 셋이 Zoom 사다리다. `hostile_data --modes long`
  이 같은 네 폭에서 **잘림 0 · 세로 붕괴 0 · 가로 넘침 0**
- reviewers: 독립 에이전트 검수는 안 썼다 — 판정을 **실브라우저 실측**과 **반례**로 세웠다.
  판정 규칙을 고친 셋(잉크 정의 · 빈 상태 밴드의 순환 · `highlight` 의 `.k-metabar`)은
  `probe_selftest.py` 에 반례 여덟을 붙여 양방향으로 확인했다(전체 34사례 초록)
- test_server: https://clovirassist.gooddi.lab = 10.100.64.71. 값은 `dist/ops/server.env`.
  **S17 은 배포했다** — S15~S17 세 회차의 변경이 이 회차에서 함께 설치처로 나갔다
- suppressions: **1건 (SUP-01)** — 칸반 레인의 균등 격자. 만료 2026-10-20. S16 이 적은 근거 그대로다
- commit: `d6eb48cf` (S17 본체)
- plan: `docs/ui-renewal/PLAN.md`(UI 축 정본) · `DIRECTIVE_v7.txt`(원 지시서) ·
  **`docs/platform/MASTER_PLAN.md`(제품 전체 정본 — 여기가 상위다)**

## NOW
**S17 이 W7 을 끝냈다.** 이번 회차가 답한 질문은 둘이다 — **클로비가 실제로 보이는가**,
그리고 **값이 없을 때 화면이 그 사실을 말하는가.**

🔴 **클로비가 작았던 원인은 «작게 줬다» 가 아니라 «박스를 줬다» 였다.** 포즈 PNG 는 전부
1024² 인데 캐릭터가 차지하는 세로 비율이 자산마다 **0.666~0.850** 으로 벌어진다 — 같은
`size={48}` 이 자산에 따라 40px 캐릭터도 되고 32px 도 된다. 박스를 재는 어떤 검사로도 안
보이는 축이다. 이제 호출부는 **자리 이름**만 말하고(`MASCOT_PLACE`) 박스는
`보이는 크기 / 여백 비율` 로 파생한다(D-294). 상단바의 보이는 캐릭터가 **22px → 34px**
(2200 이상에서 40px)이 됐고, 얼굴이 **눈 감은 졸린 포즈에서 웃는 포즈**로 바뀌었다.

🔴 **그리고 그것을 재던 검사가 틀려 있었다.** 프로브가 알파 문턱 8 에 부유 픽셀 제거 없이
재서 `clovi-talking` 의 잉크 비율을 **1.000** 으로 봤다 — 참값은 **0.817** 이다. 그 22%p
만큼 「보이는 크기」가 부풀어 **정말 작은 마스코트가 통과한다.** PLAN 이 이 실패를 이름으로
예고해 두었는데 구현이 안 따랐다(D-295). 정의를 잠갔고(`mascot-bounds.json` + 생성기 +
`static_checks` 신선도 + Python 회귀 6건), 그 위에서 `mascot_visible_size` 를 `--fail-on`
으로 승격해 60페이지 초록을 받았다.

같은 회차가 닫은 것 넷:

* **값이 없으면 접는다** — 점선 상자(`ChartEmpty`)를 폐기했다(D-296). 0건이면 차트·표·페이저가
  **언마운트**되고, 로딩 자리는 같은 높이의 **차트 모양** 스켈레톤이 잡는다. 그래서 이제
  「불러오는 중」과 「값이 없다」가 서로 다르게 보인다. 렌더 시험 11건이 양방향으로 지킨다
* **빈 상태 밴드의 순환을 정리했다** — 「빈 공간을 캐릭터로 때우는가」는 컨테이너 높이를
  **그림이 아닌 것이 정할 때만** 물을 수 있다(D-297). 그림이 가장 큰 요소이면 분자가 분모를
  정해서 어떤 비율도 통과할 수 없다. 밴드 상수는 안 건드렸고, 어느 자리가 어느 밴드를
  주장하는지를 화면이 선언하게 했다
* **상세 속성이 위계를 갖는다** — 폭은 S16 이 닫았고 남은 것은 **무게**였다(D-298). 화면이
  `rank: "primary"` 로 먼저 판단할 값을 선언하면 그것만 위 줄이 되고 나머지는 아래 압축 띠로
  내려간다. 선언이 없는 호출부의 렌더는 **안 바뀐다**
* **P-34 셋이 닫혔다** — 그리고 셋 다 **화면이 아니라 시험이 틀렸다.** 특히 ③ 은 「bool 설정이
  검증 통과를 안 그린다」로 등록돼 있었는데, 화면은 옳게 「검증을 통과했습니다」라고 말하고
  있었고 시험만 옛 조각(`검증 통과`)을 찾고 있었다

**범위 밖 발견 둘**을 등록했다: 화면에 남아 있는 Notion 잔재(**P-41**, S20)와 `/dev-report` 의
판이 자기 폭을 못 채우는 것(**P-42**, S20). 그리고 담당자 후보가 비었을 때의 안내가 **없어진
시스템**을 원인으로 대고 있어 고쳤다 — S15(D-285)가 규칙을 바꾼 뒤로 사실이 아니었다.

## NEXT
다음 작업은 **S18 — Pilot Archetype 8종(새 IA 기준)** 이다(Backlog **P-28**).
시작점은 `docs/platform/WORK_STATE.md` 이고 이 파일은 그 회차가 다시 연다.

S17 이 다음 Session 에게 넘기는 것 다섯:

1. **클로비 크기는 자리 이름으로 말한다.** `frontend/src/ui/Mascot.jsx` 의 `MASCOT_PLACE` 에
   줄 하나를 더하면 그 자리의 박스가 자산 여백에 맞춰 파생한다 — 숫자를 적지 않는다.
   `<MascotPose place="…">` 없이 `size=` 만 쓰면 `mascot-size-contract.test.js` 가 잡는다
2. **빈/로딩/오류 넷이 부품으로 서 있다.** `Skeleton kind="chart"` · `ChartNoData` ·
   `EmptyState layout="page|region|inline"` · `ErrorState`. 화면은 **고르기만** 한다
3. **상세 속성의 `rank` 배선이 티켓 하나뿐이다.** 문서 상세·게시글 상세·프로젝트 상세는
   그 화면들 회차(S18·S19)가 같은 한 줄로 닫는다
4. **캡처는 설치처 없이 찍는다** — `python -m scripts.ui_qa.local_capture --label <라벨>
   --routes <화면들> --fail-on <검사들>`. 긴 데이터는 `--harness hostile_data --modes long
   --viewports …` 로 같은 임시 서버에 대고 돌린다(S17 이 `--base-url` 을 붙였다)
5. **범위 밖으로 넘긴 것 넷**: 시험 강도 선언 미비 15건(**P-38**) · 백엔드 회귀 넷(**P-39**) ·
   화면에 남은 Notion 잔재(**P-41**, S20) · `/dev-report` 의 빈 판(**P-42**, S20)

승격 예정 Gate 는 소유 Session 을 따라간다: `detail_side_imbalance` → S19 ·
`brand_presence` → S22.

실행 규칙의 우선순위: S15~S20 에는 `docs/platform/MASTER_PLAN.md` §9.3(**D-208**)이 우선한다.
`PLAN.md` 의 「Wave 종료마다 전체 Regression」·「전체 뷰포트 × 2테마 전량 실행」 조항은 **W0~W5 가
그렇게 했다는 기록**이고 재개되는 Session 에 적용하지 않는다 — **영향 Surface/범위만** 검증하고,
Whole-product Full Capture 는 **S22 최종 빌드에서 1회**다. **W0~W5 의 완료 기록과 Evidence 는
그대로 둔다.**

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
