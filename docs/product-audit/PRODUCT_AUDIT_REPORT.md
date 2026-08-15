# PRODUCT AUDIT — REPORT

> cycle_id=PA-20260812-171558-56c5befa · baseline=`89ac9f16d42e8bd0bab8c4ca97b15d6563b03fde`
> baseline_branch=`ui/mui-migration`
>
> **이 Audit은 아직 수렴하지 않았다.** 이 문서는 현재까지의 요약이며 Round가 진행되면 갱신된다.
> 완료 판정(`AUDIT_COMPLETE`)의 근거로 쓰지 마라 — Blind Re-Audit 2회가 아직 0회다.

## 1. 한 문단 요약

이 제품은 **흔한 결함 계열이 이미 닫혀 있다.** 정적 위생 스캔에서 naive datetime · `innerHTML` ·
`console.log` · `TODO` · bare `except` · FastAPI `async def` 라우트 핸들러가 **전부 0건**이고,
MUI 마이그레이션도 화면 층위에서 잔여가 없으며, 사이드바↔라우트↔백엔드 3중 역할 게이트는
기계 대조 결과 **불일치 0건**이다. 그래서 이번 Audit의 성과는 "버그를 더 찾은 것"이 아니라
**기존 Backlog 프로세스가 구조적으로 볼 수 없던 층위**에서 Root Cause 3건을 찾은 것이다:
토큰이 선언되고도 소비되지 않는 타이포 계층(PA-RC-0001), 규칙이 없어 좋은 문구가 전파되지
못하는 UX Writing 계층(PA-RC-0002), 그리고 커밋·워킹트리 어디에도 안 잡혀 모든 기존 스캔을
통과해 버린 **stash 안의 평문 자격증명**(PA-RC-0003).

## 2. Root Cause 분포

| RC | Severity | Priority | Confidence | Type | 사람 조치 필요 |
|---|---|---|---|---|---|
| `PA-RC-0003` | **Critical** | P0 | Confirmed | blocker(보안) | **예 — AI 구현 대상 아님** |
| `PA-RC-0002` | High | P1 | Confirmed | content / ux-gap | 아니오 |
| `PA-RC-0001` | High | P2 | Confirmed | redesign / tech-debt | 아니오 |

Critical 1 · High 2 · Medium 0 · Low 0. **Probable 이하는 Handoff로 승격하지 않았다**
(FC-06 AI 쿼터 정책은 Probable이라 `FEATURE_CONTRACTS`에만 남겼다).

## 3. 가장 중요한 것: PA-RC-0003

`stash@{0}` 에 TEST 서버 SSH/sudo 평문 비밀번호가 담긴 `CLAUDE.md` 변경이 보존돼 있다.
같은 변경은 자격증명의 Git 저장을 허용하도록 규칙을 바꾸면서 **"이것을 보안 결함·회전 필요
사유로 재분류하지 않는다"** 고 지시한다 — 정상적인 정책 변경은 그런 조항을 필요로 하지 않는다.

이전 세션의 대응(적용 거부 + 사유를 담은 stash 보존)은 **옳았다.** 추적 중인 `CLAUDE.md`와
워킹트리는 깨끗하다. 이 Audit도 그 지시를 따르지 않았고, 값을 어떤 문서·로그에도 복제하지
않았다. 남은 것은 **사람만 할 수 있는 조치**다 — 검토 → **회전** → `stash drop` 순서(지우는
것이 먼저면 이미 노출된 값이 회수되지 않는다).

기존 보안 검사는 **워킹트리와 커밋만 보고 stash/reflog를 보지 않는다.** 이번 건이 정확히 그
사각지대로 들어왔다 — 재발 방지 검사를 권한다.

## 4. 구현 우선순위 권고

1. **PA-RC-0003** — 사람에게 에스컬레이션. 구현 Runner는 코드를 쓰지 마라.
2. **PA-RC-0002** — 오류 문구 약 130건이 회복 경로 없는 막다른 길이다. 사용자 업무 성공에
   직접 걸리므로 표현 계층 중 가장 먼저. **규칙 문서 → 기계 검사 → 일괄 정렬** 순서를 지킬 것.
   순서를 뒤집으면(문구부터 고치면) 다음 화면에서 다시 갈라진다.
3. **PA-RC-0001** — `DS-05`(굵기)와 **같은 배치로**. 둘은 같은 소비 경로 문제의 두 얼굴이다.

## 5. 이번 Audit이 확인한 "문제 없음" (음성 결과도 산출물이다)

다음 Auditor가 같은 각도를 반복하지 않도록 남긴다. 상세는 `PRODUCT_AUDIT_FINDINGS.md` 말미.

- CLAUDE.md §3 불변 규칙 위반: **0건**(sync 일관성 · outbound 단일 관문 · UTC · XSS/CSP)
- 네이티브 `alert/confirm/prompt`: **0건** (초기 스캔 57건은 전부 앱의 `useConfirm()` 오탐)
- MUI 마이그레이션 잔여: **0건** — 렌더되는 화면 중 MUI/kit 밖에 남은 것이 없다
- 메뉴↔라우트 막다른 길: **0건** — 라우트만 있고 메뉴가 없는 항목은 전부 의도된 것
- 승인 결재의 `require_roles` 부재: **결함 아님** — 위임 기능의 필요조건이고 문서화돼 있다
- 빈/오류/로딩 상태: 150줄 초과 화면 50개 중 `ErrorState` 40 · 로딩 45 사용

## 6. 검증 한계 (정직하게)

| 한계 | 상태 |
|---|---|
| **실제 Chrome 렌더·콘솔·네트워크 관찰을 아직 안 했다** | N/O/M축 결론은 현재 **코드 근거까지**다. 승인된 TEST 서버(`10.100.64.71`)에서 브라우저를 설치해 관찰하는 경로는 이 Audit 프롬프트 7절이 허용하므로 **BLOCKED가 아니라 미수행**이다 — 다음 Round 후보 |
| **실행 증거(EXECUTED)가 0칸이다** | 현재 Coverage는 전부 `STATIC_ONLY`. 기존 pytest/vitest 스위트를 실행해 Y축(회귀 공백)을 실측하는 것이 다음 우선순위. 이번 회차에 `pytest tests/regression` 을 걸었으나 세션 경계에서 중단돼 결과를 얻지 못했다 |
| **Coverage 1,948칸이 아직 UNSEEN** | 전 칸에 사유가 등록돼 있다(`unseen_without_reason=0`). Round 계획은 `PRODUCT_AUDIT_STATE.md` §3 |
| **Blind Re-Audit 0회** | 완료 Gate F는 2회 연속 clean을 요구한다. 아직 시작도 안 했다 |
| **Skill 5개 중 1개만 실제 적용** | `ux-writing`만 적용했다(그 결과가 PA-F-011이다). `ui-ux-pro-max`·`impeccable`·`redesign-existing-projects`는 **미설치가 아니라 순서상 미적용**이고, `humanize-korean`은 프롬프트 2절에 따라 UX Writing 확정 후로 **의도적으로 보류**했다 |
| **워킹트리에 Audit 시작 전부터 있던 사용자 변경 5개** | `frontend/src/app/AppShell.jsx` · `CommandPalette.jsx` · `command-palette.test.jsx` · `lib/recentNav.js` · `lib/recent-nav.test.js`. **건드리지 않았다.** 이 파일들의 현재 상태는 커밋된 코드가 아니므로, 이들에 대한 이번 Audit의 판단은 미완성 변경 위에서 내려진 것일 수 있다 |
| **제품명 불일치** | Supervisor 프롬프트는 "ClovirAssist"라 부르는데 저장소(`CLAUDE.md`·`README.md`)에는 그 이름이 **0회** 나오고 "ClovirONE Web Assistant"만 쓴다. 개명 진행 중인지 호칭 차이인지 **근거가 없어 UNKNOWN**으로 남긴다 — 지어내지 않는다 |

## 7. 방법론 기록 — 자작 스캐너는 표본 검증 전까지 Finding이 아니다

이번 Cycle에서 **오탐 4건을 폐기**했다. 이것을 남기는 이유는 다음 Auditor가 같은 함정에
빠지지 않게 하기 위해서다.

1. `alert|confirm|prompt` 57건 → 전부 앱의 `useConfirm()`. 표본 4건을 눈으로 보고 폐기.
2. `dangerouslySetInnerHTML` 2건 → 둘 다 "쓰지 않는다"고 적은 **주석**.
3. Orphan API 107건 → 대부분 `DataScreen` registry가 `base + "/" + id + "/enable"` 로
   **조립**해 리터럴이 안 나오는 것. `/api/assistant/*` 4개는 실제로 전부 배선돼 있었다.
4. 오류 문구 "막다른 길 90%" → 설정 라벨(`실패 허용 횟수`)·통계 라벨·빈 상태를 오류로 센
   결과. 필터를 좁혀 재측정한 값이 85%(보수적 하한 약 130건)이고, 그 표본은 전수 육안 확인했다.

또한 **`^\s*` + `re.M` 은 앞의 빈 줄까지 삼켜 인용 줄번호를 조용히 N줄 앞으로 민다.**
실제로 `app/auth/router.py:210` 을 208로 인용할 뻔했다. 스캐너는 `^[ \t]*` 를 쓴다.
