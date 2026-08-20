# INVENTORY 02 — Page / Surface / Archetype

**정본**: `docs/ui-renewal/ROUTE_COVERAGE.json`(surfaces) · `docs/ui-renewal/PLAN.md`(Archetype 정의)
**측정**: 2026-08-21 (Gate 출력) / 2026-08-20 (Plan Mode)

## 측정

| 항목 | 값 |
|---|---|
| Surface (route/tab/widget/alias) | **93** |
| 검증 대상 Surface | **89** |
| `DataScreen` + registry | **27/28** — registry 28키 중 27이 `DataScreen` 소비처 |
| 반응형 프로파일 | 9 뷰포트 × 2 테마 (W5 가 처음으로 9뷰포트 전량 실행) |

> `REGISTRY` 28키는 Coverage Gate 가 **소스에서 읽지 않는다.** 계획 세션이 정규식으로 7개 도메인
> 파일을 훑었을 때 28개 중 1개(`admin-notifications`)를 조용히 놓쳤고, **놓친 키는 커버리지에
> 없어도 Gate 가 초록이 됐다.** 이 자리는 「검사가 없는 것보다 나쁜 상태」의 표본이다.

## Archetype

Pilot Archetype 8종은 **새 IA 기준으로 교체된다** (D-207, W8 → S18 REDEFINE).
새 집합에는 최소 `/projects/:id/board` · `/spaces/:id` · `/ai/workspace` 가 포함된다.

## Page 가 지켜야 하는 것 (CLAUDE.md §6)

Token/Theme/CSS/Primitive 정리만으로 Design 완료라고 하지 않는다. Page 마다 다음이 판정 대상이다.

Information Hierarchy · Content Architecture · Layout/Space Utilization · Brand Identity ·
Typography · Density · Search/Filter/Form · Table/Grid · Empty/Loading/Error/Permission ·
Responsive/Zoom · Accessibility/Keyboard/Focus · 주요 Action 과 Feedback.

**큰 화면에서 콘텐츠가 좌측 상단에만 몰리고 나머지가 거대한 Blank Canvas 로 남는 상태를 허용하지
않는다.** 데이터가 적은 화면(승인·Empty List·놀이·기능 개선 제안·Sprint)도 Page 전체가 완성된
제품처럼 보여야 한다.

## 완성도 — S1 이 마저 할 것

- `read_tab_groups()` / `read_settings_tabs()` **빈 결과 FATAL화** (`12_PROBE.md` 우선순위 1)
- REGISTRY 28키를 **소스에서 직접 읽는** 리더 추가 여부 판단 — 지금은 다섯 번째 진실이 검사되지
  않는다
