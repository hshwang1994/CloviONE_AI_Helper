# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-20T04:05:00+09:00
- wave: W4
- wave_status: **완료** — 구현·측정·독립 검수 반영·Exit Gate 까지 끝났다. 다음은 W5
- build_index_sha256: `1a48d92ee9e55127` — 서버가 서브 중인 것이자 **After 의 지문**.
  W3 `c03113861aaa5138` · W2 `344ce7e7fc221246` · W1 `104e49366bf030f4` · Before `9ab4d470163e475a`.
  **이 지문은 `index.html` 만 본다** — lazy chunk 만 바뀐 빌드는 값이 안 움직인다(F-W4-10 에서
  실측). 그래서 소스 지문도 함께 적는다: `BUILD_STAMP.source_hash` `6ba5ed59b70f`
- coverage_gate: `--stage plan` **PASS** · `--stage wave`(**W4**) **PASS** (억제 0건).
  이 Wave 가 게이트에 **C10b** 를 더했다: 완료 Surface 는 `surface_repetition`·
  `oversized_empty_surface` 의 **실측 수치**를 갖고 있어야 하고, 전부 skip 이면 "재지 않았다" 다.
  위젯 Surface 셋은 자기 Route 가 없어 host 화면의 수치를 빌리고 `borrowed_from` 에 남긴다
- static_checks: **STATIC_CHECKS_OK** (신규 `check_ink_scale.py` · `check_logical_border_props.py` 포함)
- tests: frontend `npx vitest run` **2,347 PASS / 0 FAIL**(W3 대비 +20, 파일 316) ·
  `check_test_strength.py --base ab2bc618` **OK**(기본값 `HEAD` 는 커밋 뒤 무력하다) ·
  runner `test_assistant.py` **293 PASS**(PLAN:992 의 셋 중 하나인데 W1~W3 에 기록이 없다 —
  이번에 처음 돌렸다. F-W4-21) · backend `run_full_regression.sh` **FULL_REGRESSION_OK**
  (1,899s · unit·regression·security·integration 4청크). W4 는 `app/**/*.py` diff 0 이다
- 실측 (`w4-after` 84 Route × 2테마 × 4뷰포트 = **664페이지**+썸네일 · W3→W4 셀 19,256칸)
  · **신규 fail 26** — `control_baseline_mismatch` 24(조직 화면 넷. 독립 검수가 원인을 다시
    짚었다: 화면에서는 안 어긋나고(「?」와 「조직 추가」 중심 y 가 둘 다 242.5) assertion 이 깊이
    다른 둘을 짝짓는 기하 노이즈다 — F-W4-16. 라우트 넷에 OPEN, 승격 W5) · `detail_side_imbalance` 2
  · **fail → 아님 14** — `brand_role_coverage` 10 · `dead_blank_region` 2 · `brand_presence` 2
  · **skip → 실측 586** — 그중 `surface_repetition` 578. 재지 않던 자리가 아니라 **재 놓고
    안 적던** 자리다(C10b 를 만든 이유)
  · **실측 → skip 40** — `detail_side_imbalance` 30 · **`oversized_empty_surface` 8** ·
    `dead_blank_region` 2. 뿌리 하나다(F-W4-12) — 프로브가 대상을 **칠해진 면**으로 전제해
    판을 벗기면 못 찾는다. 8셀은 이 Wave 가 Verification 으로 지명한 검사라 따로 적는다
  · `dead_blank_region` 4셀(F-W4-13)은 최종 빌드에서 발화하지 않지만 **닫지 않았다** — 고쳐서가
    아니라 데이터가 늘어 잉크가 734→788px 가 됐을 뿐이고 임계 바로 위다. 라우트 자동 Finding 은
    `closed_by` 에 w2·w3·w4 가 쌓여 **Wave 마다 열고 닫히기를 반복**했다. F-W4-13 은 OPEN(W12)
    으로 두고 완료 조건을 «데이터 적은 상태에서도 임계 위» 로 적었다. 자동 닫힘은 F-W4-20(W15)
- kit 면 계약: `dist/ui-qa/w4-kit-e2e/surfaces.json` **40/40 조합 PASS · 판 안의 판 0자리**
  (4뷰포트 × 2테마 × **5화면** — 파괴 버튼이 실제로 있는 `/chat-rooms` 를 검수 뒤 넣었다).
  대표 실측(1920 light): 판독 줄 `plate=false` · 칸 구분선 **4/4** · 라벨 기준선 **0px**(W3 24px)
  · 활성 레일 solid 2px, 비활성도 2px · **활성 칸 배경 없음**(레일이 신호를 진다) · 잉크 분리도
  **1.532/1.596** · 보조 테두리 **4.181**(W3 17.1) · **파괴 테두리 6.536(L)/7.715(D)**(검수 전
  2.48/2.84) · 판독 슬롯 묶음당 **1개**(프로브가 40/19px 로 구분) · 대화상자 밖 채운 error **0**
- functional: `scripts/ui_qa/kit_e2e.py`(신규) 가 `kit_primitives` 5 Flow 를 실브라우저에서
  네트워크와 함께 돌린다 — 다섯 다 관측됐지만 Control Plane 에서는 **전부 IN_PROGRESS** 다.
  C11 의 사슬 핵심 넷 중 서버 쪽 셋이 없기 때문이다(판독 칸은 초점만 바꾸고, 더티 판정은 값
  스냅샷, 도움말 접힘은 컴포넌트 상태다). 없는 다섯 축은 FF-1405~1409 로 `exists:false`
- modals: `--modals` 를 켠 첫 실행(`w4-modals`) — 모달 Assertion 7종이 W0 이후 **한 번도
  실행된 적이 없었다**(F-W4-08). 최종 빌드에서 5 Route × 2테마 **7종 × 8페이지 전부 통과**
- shell 재검증: 캡처만 믿지 않고 최종 빌드에서 두 셸 프로브를 다시 돌렸다 — `w4-shell-e2e`
  12 Flow(9건 사슬 4/4) · `w4-nav-e2e` **18/18 조합 PASS**. D-184 규율("캡처가 증명하는 것은
  Assertion 재측정이지 셸 고유 계약이 아니다") 그대로다
- reviewers: 구현하지 않은 독립 3 렌즈(시각 Before/After · 요구사항 · 디자인 감각)가 **24건**
  제기 → 상위 10건을 반증 시도 에이전트가 검증 → **확정 2 · 기각 8**.
  확정 둘은 성격이 같다 — **자기가 바꾼 자리를 자기 검사가 안 본다**: 파괴 버튼 테두리가 MUI
  기본 alpha 0.5(판 위 2.48:1)인데 새 프로브가 `outlinedError` 를 건너뛰었고(F-W4-14), 판독 값
  글자를 정렬 래퍼에서 읽어 «묶음당 판독 하나» 단언이 한 번도 실행되지 않았다(F-W4-15). 둘 다
  고쳐 재측정했다. 기각 8건은 수치는 실재하나 결론이 정본과 어긋났고, 잔여물 둘만 함께 닫았다
  (F-W4-16 오귀속 주석 · F-W4-17 죽은 CSS). 상세는 D-185 «덧 셋»
- open_findings: **Surface Finding 323건 전수** — 이 Wave 가 21건을 새로 등록하고
  (F-W4-01 ~ F-W4-21) F-W2R-01 · F-W4-09 · `public_login/console_errors` 를 닫았다.
  W1 독립 리뷰 잔여 27건(F-W1R-03·04·16·27 네 건을 이 Wave 가 종결).
  재라우팅: F-W2R-04 → W5 · F-W1R-23 → W8 · F-W1R-29 → W6
- test_server: https://clovirassist.gooddi.lab = 10.100.64.71. 접속·배포·QA 값은
  `dist/ops/server.env`(gitignore). 배포는 사람 없이 돈다 — `scripts/apply-static-update.sh`
- commit: `8ce696bd` (W4 전체 — 소스 · 번들 · 캡처 664장 · Control Plane)
- plan: docs/ui-renewal/PLAN.md (정본), docs/ui-renewal/DIRECTIVE_v7.txt (원 지시서)

## NOW
W4(공유 Layout Primitive). **면은 이제 부품이 정한다.**
`kit.jsx::Surface` 가 PLAN «Surface 위계» 의 7 tone 표를 들고, `Card` 는 그중 `plate` 의
별칭이며, 체크리스트 ⑥ «컨테이너 없음» 자리에 쓸 부품(`Section`)이 처음으로 생겼다 —
금지만 하고 대안을 안 주면 화면은 다시 판을 만든다. 하드 금지 다섯 중 **판 안의 판**은 코드가
강제한다: 자동으로 `none` 이 되고 여백까지 함께 버리며, 그 사실이 `data-surface="plate>none"`
으로 남아 하네스가 센다(배포본 40조합에서 0자리). 판을 벗긴 자리는 넷이다 —
`MetricStrip`·`MetaBar`·`SettingList`·`StatusList`.

이번 Wave 가 배운 것 셋. **하나 — 판을 벗기면 그 판이 감추고 있던 것이 드러난다.**
칸 구분선은 애초에 그려지지 않고 있었고(`borderInlineStart: 1` 은 shorthand 라 style 을
`none` 으로 되돌린다 — 안 그려지는 게 아니라 **있던 선을 지운다**), 활성 칸의 오목면은
캔버스 위에서 **더 밝아 신호가 뒤집혔다**(대비 1.055:1). 둘 다 판이 있는 동안에는 보이지
않던 결함이라 판 제거와 같은 커밋에서 고쳐야 했다.

**둘 — 토큰의 역할을 바꾸는 결정은 소비처에서 완결된다.** `text.faint` 를 AA-large 자리로 좁히고
값을 벌린 것(분리도 1.10 → 1.53)은 소비처를 옮기지 않으면 문서일 뿐이다. 그 과정에서
`text.disabled` 가 `faint` 와 **같은 값을 쓰고 있었다**는 것이 배포본 실측으로 드러났다 — 비활성
입력 라벨이 4.18:1 로 AA 아래였고, 두 역할을 값까지 분리해서 닫았다.

**셋 — 프로브는 양쪽으로 틀린다.** `kit_e2e` 첫 실행의 «계약 위반» 12조합은 **넷 다 프로브
결함**이었고(AI 서랍의 같은 `role="dialog"` · px 를 4K 레버로 정규화 · 접힌 줄 · 남은 모달),
반대로 판독 슬롯 검사는 **아무것도 안 재면서 통과**하고 있었다(F-W4-15). 위양성만 의심하면
후자를 영영 못 본다. 근거·수치는 `docs/DECISIONS.md` **D-185**.

## NEXT
1. **W5(Search/Filter/Form 설계)** 를 시작한다. 소유 파일 `frontend/src/ui/FilterBar.jsx` ·
   `filters.jsx`(+`EntityCombobox`) · `SavedViews.jsx`, 소비처 4곳을 정해진 순서로.
   **입력이 준비돼 있다** — `F-W2R-04`(AI 앵커 컨트롤 리듬, W4 에서 재라우팅) 와
   `control_baseline_mismatch` 134셀(그중 조직 화면 24셀이 이번에 새로 드러났다).
   이 클래스와 `isolated_control_row` 가 W5 에서 `--fail-on` 으로 승격된다.
2. Wave 마다: **CHECKPOINT 의 `wave:` 를 먼저 올린다** → 구현 → focused test →
   배포(`apply-static-update.sh`) → 실브라우저 재캡처 → `collect_evidence --into after` →
   `merge_qa_findings --write` → `--stage wave` → **구현하지 않은 에이전트**의 독립 검수.
   **종료 시험은 셋이다(PLAN:992)** — `run_full_regression.sh` · `npm test` · runner
   `test_assistant.py`. **공유 파일 Wave 면 9뷰포트 × 2테마까지**(둘 다 W1~W4 에서 빠졌다,
   F-W4-21). `check_test_strength.py` 는 `--base <직전 Wave 커밋>`, 전량 캡처는
   `--rebuild-auth`(F-W4-09). 리뷰 Workflow 는 `…/scratchpad/w4-review.js` 를 복제해 쓴다.
3. 그 뒤 W5B → W6 → W7 → W8(Pilot 8종) → W9~W15.
   W6: `F-W1R-29`(표머리 12 vs 셀 14) · `F-W4-05`. W7: `F-W1R-41`(brandTint 배선) ·
   `F-W4-18`(미배선 셋) · `F-W4-11`(죽은 CSS 잔여). W8: `F-W1R-23` · `F-W4-01` · `F-W4-02` · **`F-W4-21`** —
   PLAN:992 의 9뷰포트 하네스가 W1~W4 에서 안 돌아 5뷰포트가 W0 이후 미측정이다(W0 과 대조).
   W9: `F-W4-03` · `F-W4-12`. W12: `F-W4-04` · `F-W4-13`. W14: `F-W4-08`.
   W15: `F-W4-06`(kit.css·screens.css vitest 0) · `F-W4-07` · `F-W4-10` · `F-W4-19` · `F-W4-20`.
4. 승격 예정 Gate: `isolated_control_row`·`control_baseline_mismatch` → **W5** ·
   `brand_role_coverage` → W6 · Table 4종 → W6 · `mascot_visible_size` → W7.

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
