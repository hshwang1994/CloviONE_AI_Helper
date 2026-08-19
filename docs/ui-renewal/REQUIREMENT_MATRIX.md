# ClovirAssist UI/UX 리뉴얼 — 요구사항 추적표

> 지시서 v7 의 최상위 지시 0-x 와 상세 요구사항 1~84, 그리고 사용자 보강 요구 R-85~R-97 전부.
> 항목마다 필드 아홉 개가 모두 채워져 있어야 한다.
> `scripts/check_ui_renewal_coverage.py` 가 번호 누락, 빈 필드, 없는 Wave 참조,
> 근거 없는 완료, 제목만 있는 항목을 검사한다 (지시 56 · R-96).
> Wave 이름의 정본은 `docs/ui-renewal/ROUTE_COVERAGE.json` 의 `waves` 다.
> 정본 계획서는 `docs/ui-renewal/PLAN.md` 다.

**항목 161개 · 빠진 번호 0 · 빈 필드 0 · 없는 Wave 참조 0**

---

## R-0. 이번 재작업의 절대 원칙

- **Wave**: W0
- **Requirement**: 이 조항이 요구하는 것은 다음이다. 이번 재작업의 절대 원칙. 이번 계획에서는 이 원칙을 Wave 배정과 Gate 조건으로 옮겨, 구현 중에 사람이 기억하는 대신 스크립트가 검사하게 한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0.1. 현재 구현 결과를 완료 상태, 올바른 Design Direction, 재사용해야 할 Visual Baseline으로 간주하지 않는다.

- **Wave**: W0
- **Requirement**: 이 조항이 요구하는 것은 다음이다. 현재 구현 결과를 완료 상태, 올바른 Design Direction, 재사용해야 할 Visual Baseline으로 간주하지 않는다. 이번 계획에서는 이 원칙을 Wave 배정과 Gate 조건으로 옮겨, 구현 중에 사람이 기억하는 대신 스크립트가 검사하게 한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0.2. 기존 기능, 데이터, 권한, 보안, 업무 흐름, API 계약은 보존하되 현재 Visual Design, Layout, Component 표현, Theme 방향은 다시 판단한다.

- **Wave**: W0
- **Requirement**: 이 조항이 요구하는 것은 다음이다. 기존 기능, 데이터, 권한, 보안, 업무 흐름, API 계약은 보존하되 현재 Visual Design, Layout, Component 표현, Theme 방향은 다시 판단한다. 이번 계획에서는 이 원칙을 Wave 배정과 Gate 조건으로 옮겨, 구현 중에 사람이 기억하는 대신 스크립트가 검사하게 한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0.3. 기존 테스트가 PASS하거나 Browser에서 깨지지 않는다는 이유로 디자인이 완료되었다고 판단하지 않는다.

- **Wave**: W0
- **Requirement**: 이 조항이 요구하는 것은 다음이다. 기존 테스트가 PASS하거나 Browser에서 깨지지 않는다는 이유로 디자인이 완료되었다고 판단하지 않는다. 이번 계획에서는 이 원칙을 Wave 배정과 Gate 조건으로 옮겨, 구현 중에 사람이 기억하는 대신 스크립트가 검사하게 한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0.4. 코드 품질 개선, Token 통합, Bundle 최적화, 테스트 추가는 중요한 기반 작업이지만 그것만으로 UI Renewal 완료가 아니다.

- **Wave**: W0
- **Requirement**: 이 조항이 요구하는 것은 다음이다. 코드 품질 개선, Token 통합, Bundle 최적화, 테스트 추가는 중요한 기반 작업이지만 그것만으로 UI Renewal 완료가 아니다. 이번 계획에서는 이 원칙을 Wave 배정과 Gate 조건으로 옮겨, 구현 중에 사람이 기억하는 대신 스크립트가 검사하게 한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0.5. 실제 사용자가 보는 각 Page의 Composition, 정보 위계, 공간 활용, Brand Identity, Typography, Interaction, Empty State, Page Purpose가 충분히 개선되어야 한다.

- **Wave**: W8
- **Requirement**: 이 조항이 요구하는 것은 다음이다. 실제 사용자가 보는 각 Page의 Composition, 정보 위계, 공간 활용, Brand Identity, Typography, Interaction, Empty State, Page Purpose가 충분히 개선되어야 한다. 이번 계획에서는 이 원칙을 Wave 배정과 Gate 조건으로 옮겨, 구현 중에 사람이 기억하는 대신 스크립트가 검사하게 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Projects.jsx`, `frontend/src/screens/Ticket.jsx`, `frontend/src/screens/OrgConsole.jsx`
- **Verification**: 독립 Visual Reviewer 와 독립 Requirement Reviewer 서명, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 Pilot Flow PASS
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0.6. 특정 Page에서 발견된 문제는 해당 Page만 수정하지 않고 동일한 Root Cause, 공통 Component, Page Archetype, UX Pattern을 사용하는 전체 Route를 조사한다.

- **Wave**: W0
- **Requirement**: 이 조항이 요구하는 것은 다음이다. 특정 Page에서 발견된 문제는 해당 Page만 수정하지 않고 동일한 Root Cause, 공통 Component, Page Archetype, UX Pattern을 사용하는 전체 Route를 조사한다. 이번 계획에서는 이 원칙을 Wave 배정과 Gate 조건으로 옮겨, 구현 중에 사람이 기억하는 대신 스크립트가 검사하게 한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0.7. 사용자가 추가 지적할 때까지 결함을 남겨두지 않는다. Audit에서 발견한 동일 유형 문제는 스스로 전체 범위에 확장하여 수정한다.

- **Wave**: W0
- **Requirement**: 이 조항이 요구하는 것은 다음이다. 사용자가 추가 지적할 때까지 결함을 남겨두지 않는다. Audit에서 발견한 동일 유형 문제는 스스로 전체 범위에 확장하여 수정한다. 이번 계획에서는 이 원칙을 Wave 배정과 Gate 조건으로 옮겨, 구현 중에 사람이 기억하는 대신 스크립트가 검사하게 한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0.8. 기존 design/baseline/preview-standalone.html은 보지 않는다. 분석하지 않는다. 복원하지 않는다. 새 Preview로 재작성하지 않는다. 실제 Runtime과 실제 Browser가 유일한 Visual 검증 대상이다.

- **Wave**: W0
- **Requirement**: 이 조항이 요구하는 것은 다음이다. 기존 design/baseline/preview-standalone.html은 보지 않는다. 분석하지 않는다. 복원하지 않는다. 새 Preview로 재작성하지 않는다. 실제 Runtime과 실제 Browser가 유일한 Visual 검증 대상이다. 이번 계획에서는 이 원칙을 Wave 배정과 Gate 조건으로 옮겨, 구현 중에 사람이 기억하는 대신 스크립트가 검사하게 한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-1. Brand Color와 제품 정체성은 Purple/Indigo로 유지

- **Wave**: W1
- **Requirement**: 이번 재작업에서 ClovirAssist의 기존 Purple/Indigo 계열 Brand Identity를 유지하는 것은 사용자 확정사항이다. 이 요구사항은 기존 지시 53번, 65번의 일반적인 Design Direction 자유도보다 우선한다. 현재 구현처럼 제품 Chrome과 주요 화면을 White/Gray 중심의 Neutral UI로 바꾸고 Purple을 Logo나 작은 Accent에만 남기는 방향을 사용하지 않는다. `chrome recedes to neutral`, `채도를 데이터에만 사용`, `기존 라벤더 기를 제거` 같은 이전 작업의 자체 Design Thesis는 폐기한다. 기존 Source와 Git History에서 ClovirAssist가 사용해 온 Purple/Indigo Brand Token과 Logo Palette를 확인하여 Brand SSOT를 다시 정의한다. 기존 코드에 존재하는 brand.deep, brand.mid, brand.purple 등 실제 ClovirAssist Brand 계열을 우선 조사한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/theme.js`, `scripts/generate_design_tokens.mjs`, `frontend/src/styles/tokens.css`, `app/static/css/tokens.css`
- **Verification**: `frontend/src/ui/theme-contract.test.js`, `frontend/src/styles/tokens-generated.test.js`, `node scripts/generate_design_tokens.mjs --check`, assertion `brand_presence`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2. 현재 Browser 캡처에서 확인된 문제를 최소 수정 기준으로 사용

- **Wave**: W0
- **Requirement**: 현재 실제 Browser 캡처에서 다음 문제가 확인되었다. 아래 항목은 예시가 아니라 이번 재작업에서 반드시 해결해야 하는 최소 Finding이다. 같은 문제가 다른 Route에도 있는지 전수조사한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.1. 사용자 Home

- **Wave**: W10
- **Requirement**: 상단 KPI는 숫자만 일렬로 나열되어 있고 전체 화면이 White/Gray Strip과 Box 위주다. 오늘 마감 데이터가 없을 때 큰 빈 Panel이 남고, 화면 중간에 지나치게 큰 공백이 발생한다. 오른쪽 Sprint/최근 문서와 아래 내 업무의 관계와 우선순위가 약하다. 사용자가 지금 해야 할 일, 지연 위험, 승인 필요, Sprint 상태, 최근 변화가 하나의 업무 Home으로 자연스럽게 연결되지 않는다. 동기화 실패 같은 운영 정보가 일반 사용자에게 전폭 Warning으로 노출되는 문제도 다시 점검한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.2. 승인

- **Wave**: W10
- **Requirement**: 데이터가 없을 때 작은 Empty State만 좌측 상단에 있고 화면 대부분이 비어 있다. Tab과 Empty State만 있는 화면으로 끝내지 말고 처리할 승인, 내가 올린 요청, 처리 이력이라는 Page 목적에 맞는 정보 구조를 재검토한다. 데이터가 없으면 과도한 Panel을 유지하지 않고 Compact Empty State와 필요한 Context만 남긴다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.3. 프로젝트

- **Wave**: W10
- **Requirement**: 현재 화면은 KPI Strip + Filter + Excel 형태 Table 조합의 인상이 강하다. Project Portfolio에서 실제로 필요한 Health, 일정 위험, 진행률, 최근 변화, 우선 확인 대상이 빠르게 읽히는지 다시 설계한다. Table은 유지할 수 있지만 전체 Page가 Table 하나를 위한 Wrapper처럼 보이지 않아야 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.4. 채팅방

- **Wave**: W9
- **Requirement**: 좌측 대화 목록과 거대한 빈 Main Canvas, 하단 Composer만 남아 있어 화면 대부분이 의미 없이 비어 있다. 대화가 없는 상태, 메시지가 있는 상태, 1:1, 그룹, AI 대화 등 실제 Context에 맞는 Composition을 설계한다. 대화 Header, 참여자/Context, Message 흐름, Composer, 첨부, Action을 ClovirAssist 자체의 Collaboration/AI Experience로 만든다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/MyTickets.jsx`, `frontend/src/screens/TeamDocs.jsx`, `frontend/src/screens/ChatRooms.jsx`, `frontend/src/ui/MirrorNotice.jsx`
- **Verification**: `frontend/src/screens/tickets-list.test.jsx`, `frontend/src/screens/cross-screen-invalidation.test.jsx`, `python -m scripts.ui_qa.run --routes user`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.5. 기능 개선 제안

- **Wave**: W10
- **Requirement**: 검색/필터 Box와 작은 Empty State만 있고 나머지 화면이 거의 모두 비어 있다. Empty State에서 작은 Illustration과 문장만 놓고 끝내지 않는다. 제안 목적, 탐색, 상태, 참여 흐름을 Page 목적에 맞게 구성한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.6. 놀이

- **Wave**: W10
- **Requirement**: 열린 Game이 없을 때 Page 전체가 비어 보인다. 데이터가 없다는 이유로 전체 Page가 미완성 화면처럼 보이지 않도록 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.7. 내 업무량/완료 통계

- **Wave**: W10
- **Requirement**: Chart와 보조 정보가 존재하지만 전체 Visual Language가 White Card 중심이고 Chart의 선, 축, 범례, 데이터 의미가 약하다. Trend, 기간 변화, 완료율, 남은 업무, 위험을 한눈에 읽을 수 있도록 Data Visualization을 다시 설계한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.8. 티켓 상세

- **Wave**: W9
- **Requirement**: Metadata Strip, 본문, 첨부, 댓글 구조는 있으나 전체가 White Panel로 분절되어 있고 본문 Typography와 Content Reading Experience가 약하다. 본문 가독성, Metadata 그룹, Action Hierarchy, 첨부/댓글 관계를 다시 정리한다. 넓은 화면에서도 읽기 영역을 무작정 늘리지 말고 남는 공간은 유용한 보조 Context에 사용한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/MyTickets.jsx`, `frontend/src/screens/TeamDocs.jsx`, `frontend/src/screens/ChatRooms.jsx`, `frontend/src/ui/MirrorNotice.jsx`
- **Verification**: `frontend/src/screens/tickets-list.test.jsx`, `frontend/src/screens/cross-screen-invalidation.test.jsx`, `python -m scripts.ui_qa.run --routes user`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.9. 문서 목록

- **Wave**: W9
- **Requirement**: 일반 사용자에게 `최근 동기화 실패` 운영 Warning과 `지금 동기화` Action이 여전히 보인다. 이는 기존 요구사항 미반영이다. 일반 사용자 화면의 수동 동기화 기본 Action을 제거하고 Scheduler 기반 자동 동기화 원칙을 적용한다. 실제 사용자 조치가 필요한 장애가 아닌 내부 동기화 상태를 전폭 Warning으로 노출하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/MyTickets.jsx`, `frontend/src/screens/TeamDocs.jsx`, `frontend/src/screens/ChatRooms.jsx`, `frontend/src/ui/MirrorNotice.jsx`
- **Verification**: `frontend/src/screens/tickets-list.test.jsx`, `frontend/src/screens/cross-screen-invalidation.test.jsx`, `python -m scripts.ui_qa.run --routes user`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.10. Sprint 회의

- **Wave**: W10
- **Requirement**: 데이터가 없는데도 Burndown과 담당자 업무량의 큰 Empty Chart Panel이 유지되어 화면을 차지한다. 긴 설명문이 화면에 직접 노출되어 회의용 화면의 밀도를 떨어뜨린다. 데이터가 없으면 Chart Container를 기계적으로 유지하지 않는다. 실제 회의에서 필요한 판단, Scope, 지연, Blocked, 담당자 부담, 남은 업무, 완료 추이를 중심으로 재설계한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.11. 관리자 조직 관리

- **Wave**: W11
- **Requirement**: 조직 Tree와 Table이 상단에 작게 배치되고 아래 대부분이 비어 있다. 관리자 Sidebar도 여전히 많은 항목이 직접 노출되어 있어 IA 재구성이 충분히 끝난 것으로 보기 어렵다. Split View, 선택 Context, Detail, Search, Action을 실제 조직 관리 Workflow에 맞게 구성하고 Page Height를 의도적으로 사용한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/navConfig.js`, `frontend/src/app/AdminRoutes.jsx`, `frontend/src/screens/settings/SettingsShell.jsx`, `frontend/src/ui/TabShell.jsx`
- **Verification**: `frontend/src/app/nav-features.test.js`, 옛 주소 제자리 렌더 회귀 테스트, Gate 조건 C1b
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.12. 관리자 문서 자동 생성

- **Wave**: W12
- **Requirement**: Filter와 긴 설명, Empty State, Pagination이 상단에 몰리고 아래 화면이 비어 있다. 사용자가 항상 읽어야 할 필요가 없는 긴 설명은 Page Help로 이동한다. 현재 상태, 필요한 설정, 생성 이력, 실패/대기/완료, 다음 Action이 중심이 되어야 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.13. Global Header와 Sidebar

- **Wave**: W2
- **Requirement**: 현재 Header, Sidebar, Main Canvas가 모두 밝은 Gray/White 계열로 연결되어 Brand Identity가 크게 약화되었다. Active State도 얇은 Blue Rail 정도라 ClovirAssist의 Purple/Indigo Identity가 거의 느껴지지 않는다. Header, Sidebar, Main Canvas를 하나의 Brand System으로 다시 설계한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/AppShell.jsx`, `frontend/src/app/TopBrand.jsx`, `frontend/src/app/TopSearch.jsx`, `frontend/src/styles/root.css`
- **Verification**: `frontend/src/app/topbar-contract.test.jsx`, assertion `narrow_main`, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.14. Typography와 Control Density

- **Wave**: W1
- **Requirement**: 전체적으로 Text와 Form Control이 지나치게 작고 약하게 보이는 화면이 있다. 정보 밀도를 높인다는 이유로 가독성을 희생하지 않는다. Page Title, Section Title, Body, Caption, Table Text, Button Label의 실제 Browser 크기와 Contrast를 다시 검수한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/theme.js`, `scripts/generate_design_tokens.mjs`, `frontend/src/styles/tokens.css`, `app/static/css/tokens.css`
- **Verification**: `frontend/src/ui/theme-contract.test.js`, `frontend/src/styles/tokens-generated.test.js`, `node scripts/generate_design_tokens.mjs --check`, assertion `brand_presence`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.15. Empty State 공통 문제

- **Wave**: W7
- **Requirement**: 승인, 기능 개선 제안, 놀이, Sprint 등 여러 Page에서 데이터가 없으면 작은 Illustration/문장 하나와 거대한 Blank Canvas가 남는다. Empty State는 Page Layout의 일부로 설계한다. 빈 데이터일 때 필요 없는 Chart/Table/Panel을 Collapse하거나 대체하고 사용자가 다음에 할 수 있는 Action과 Context만 남긴다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.16. White Card 반복 문제

- **Wave**: W4
- **Requirement**: 현재 결과는 Border와 Radius를 줄였지만 여전히 White/Gray Surface와 Rectangle 조합이 화면 대부분을 지배한다. 모든 정보를 White Box로 감싸지 않는다. Section, Inline Summary, Table, Timeline, Split View, Data Visualization, Context Rail 등 정보 성격에 맞는 표현을 사용한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/kit.css`, `frontend/src/ui/adminKit.jsx`, `frontend/src/ui/density.js`
- **Verification**: `frontend/src/ui/kit.test.jsx`, `frontend/src/ui/density-contract.test.jsx`, assertion `surface_repetition`, assertion `oversized_empty_surface`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.17. Search/Filter 정렬과 프로젝트 선택 문제

- **Wave**: W5
- **Requirement**: Search, Category, Sort가 서로 다른 줄에 이유 없이 흩어지거나 Filter 하나만 다음 줄에 고립되는 화면이 있다. Project, 사용자, 담당자처럼 이름으로 찾는 Entity가 단순 Dropdown으로 남아 있는 경우도 있다. 검색 가능한 Autocomplete/Combobox 요구를 실제 Browser Interaction까지 구현하고 Filter Grouping, Height, Baseline, 줄바꿈을 함께 재설계한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/FilterBar.jsx`, `frontend/src/ui/filters.jsx`, `frontend/src/screens/TicketFilterBar.jsx`, `frontend/src/screens/DataScreen.jsx`
- **Verification**: assertion `isolated_control_row`, assertion `control_baseline_mismatch`, assertion `plain_dropdown_for_entity`, `frontend/src/ui/FilterBar.jsx` 소비처 렌더 테스트
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.18. Table과 Metadata의 균등 Width 문제

- **Wave**: W6
- **Requirement**: 제목이나 프로젝트명처럼 긴 값이 필요한 공간을 얻지 못하고 상태, 숫자, 난이도처럼 짧은 값이 같은 폭을 차지하는 화면이 있다. Column 수만큼 동일 Width로 나누는 패턴을 전수조사하고 데이터 의미와 길이에 맞는 Width Distribution으로 변경한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.19. Text와 Data Alignment 문제

- **Wave**: W6
- **Requirement**: Table Header와 Cell, 숫자, 상태, 날짜, Action, Metadata Label/Value, Form Control의 정렬이 데이터 유형에 맞지 않거나 서로 어긋난 화면이 있다. 모든 값을 일괄 Left 또는 Center 정렬하지 않고 의미 기반 Alignment Contract를 적용한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.20. Detail Page의 좌우 Balance 문제

- **Wave**: W7
- **Requirement**: 티켓과 문서 등 Detail 화면에서 주요 내용이 한쪽으로 몰리고 반대편에 활용 가능한 공간이 과도하게 남는 문제가 있다. 본문, Metadata, 첨부, 댓글, History, 관련 Context의 정보량을 기준으로 Layout을 다시 설계하고 넓은 화면과 Zoom에서 실제 Balance를 검증한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-2.21. Sprint 담당자 현황의 반복 Card와 비교성 문제

- **Wave**: W10
- **Requirement**: 담당자마다 동일한 큰 Card를 반복하여 화면을 채우는 방식이 실제 비교 목적에 적합한지 다시 판단한다. 업무량, 지연, Blocked, Capacity를 빠르게 비교할 수 있는 더 Compact하고 정보 중심의 표현을 검토한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-3. Ultracode Workflow를 적극 사용하고 단일 Agent 장기 작업으로 처리하지 않는다

- **Wave**: W0
- **Requirement**: 이 작업은 반드시 Claude Code의 Ultracode Dynamic Workflow 방식으로 수행한다. 단순히 Prompt에 `ultracode`라는 단어만 적고 내부적으로 한 Agent가 모든 작업을 순차 수행한 것으로 끝내지 않는다. 독립적으로 조사 가능한 영역은 Subagent와 Workflow로 분리하고, 서로 다른 관점의 Agent가 병렬 조사한 뒤 결과를 합치는 구조를 사용한다. 다음 역할을 최소한 분리한다. 1. Route/Source Inventory Agent 사용자/관리자 전체 Route, Page Archetype, 공통 Component, API, 권한, 상태를 조사한다. 2. Brand/Design System Agent 기존 ClovirAssist Purple/Indigo Brand 자산, Theme, Token, Header, Sidebar, Component System을 조사하고 새 Brand System을 설계한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-4. 이전 Docs와 이전 완료 기록을 신뢰하지 않는다

- **Wave**: W0
- **Requirement**: 사용자가 기존 UI Renewal 관련 Docs를 이미 삭제했다. 삭제된 과거 Audit, Backlog, PASS, Coverage 문서를 복구하거나 그것을 완료 근거로 사용하지 않는다. 현재 Source Code, 현재 Route, 실제 Browser, 실제 API/Backend 상태를 다시 조사한다. 제품의 기능 계약을 설명하는 실제 Product/API 문서는 필요하면 참고할 수 있지만 과거 UI Renewal 완료 기록은 새로운 작업의 Truth가 아니다. 문서가 없다는 이유로 기억이나 과거 Session Summary로 완료 상태를 추정하지 않는다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-5. 누락 방지를 위한 새 Control Plane을 처음부터 만든다

- **Wave**: W0
- **Requirement**: 기존 Docs를 많이 다시 만들지 않는다. 이번 작업 전용으로 아래 최소 Control Artifact만 새로 만든다. 1. docs/ui-renewal/REQUIREMENT_MATRIX.md 이 지시사항의 모든 번호와 Sub Requirement를 추적한다. 각 항목에 Requirement ID, 영향 Route/Page, 구현 위치, 상태, 검증 방법, Evidence를 기록한다. 2. docs/ui-renewal/ROUTE_COVERAGE.json 사용자/관리자 전체 Route를 기계적으로 추적한다. 각 Route에 최소한 route, archetype, role, states_checked, visual_audit, functional_audit, responsive_audit, before_capture, after_capture, status, evidence를 기록한다. 3. docs/ui-renewal/WORK_STATE.md 현재 작업 Wave, 완료된 범위, 다음 작업, 외부 Blocker만 기록한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-6. 구현 전에 전체 Route Inventory와 실제 Browser Before Capture를 다시 수행

- **Wave**: W0
- **Requirement**: 작업 시작 직후 Source의 Router 등록 정보와 실제 Navigation을 기준으로 사용자/관리자 전체 Route를 다시 추출한다. Route 수를 과거 기록에서 가져오지 않는다. 각 Route를 Dashboard, List, Detail, Form, Workflow, Chat, Report, Settings, Console, Empty-focused 등 실제 Page Archetype으로 분류한다. 각 Route에서 다음을 확인한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-7. 전역 Theme을 먼저 바꾸고 전체에 퍼뜨리지 않는다. Pilot Gate를 둔다

- **Wave**: W8
- **Requirement**: 이전 작업처럼 Design Thesis 하나를 정한 뒤 Theme부터 전면 변경하여 잘못된 방향을 전체 Route에 확산시키지 않는다. 먼저 Brand/Design Direction을 설계하고 다음 대표 Pilot Page를 실제 Browser까지 완성한다. 1. 사용자 Home 2. 프로젝트 목록 또는 Portfolio 3. Sprint 회의 4. 채팅방 5. 티켓 상세 또는 문서 상세 6. 관리자 조직/사용자 관리 7. 관리자 Settings 또는 Operations 대표 화면 Pilot은 서로 다른 Page Archetype을 대표해야 한다. Pilot 구현 후 실제 Browser Screenshot을 생성하고 다음 순서로 독립 검수한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Projects.jsx`, `frontend/src/screens/Ticket.jsx`, `frontend/src/screens/OrgConsole.jsx`
- **Verification**: 독립 Visual Reviewer 와 독립 Requirement Reviewer 서명, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 Pilot Flow PASS
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-8. 구현은 Wave 단위로 진행하고 Wave마다 독립 Audit을 통과

- **Wave**: W0
- **Requirement**: Wave 1. Brand Foundation과 Design System Purple/Indigo Brand Palette, Canvas/Surface, Typography, Spacing, Grid, Radius, Shadow, Button, Form, Badge/Tag, Table, Modal, Empty, Feedback, Chart 규칙을 설계한다. Wave 2. Global Shell Header, Logo, Global Search, Sidebar, User/Admin Navigation, Responsive Shell, Notification Entry를 재설계한다. Wave 3. 핵심 사용자 Workflow Home, Ticket, Document, Project, Sprint, Chat을 실제 업무 Flow 기준으로 재설계한다. Wave 4. 나머지 사용자 Route Approval, Activity, Stats, Profile, Board, Idea, Games 등 이름이 적히지 않은 Route까지 Route Coverage 기준으로 모두 처리한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-9. 화면별 디자인은 Page Purpose부터 다시 설계

- **Wave**: W8
- **Requirement**: 기존 Component를 먼저 보고 화면을 조립하지 않는다. 각 Page마다 먼저 아래를 답한다. 1. 사용자가 이 Page에 들어온 이유는 무엇인가 2. 첫 5초 안에 무엇을 알아야 하는가 3. 가장 중요한 Action은 무엇인가 4. 어떤 정보가 판단을 돕는가 5. 어떤 정보가 중복되거나 불필요한가 6. 어떤 데이터가 현재 빠져 있는가 7. 데이터가 없으면 무엇을 보여줘야 하는가 8. 넓은 화면의 남는 공간을 어떻게 의미 있게 사용할 것인가 현재 Backend/API/DB에 이미 있는 데이터로 유용한 정보를 제공할 수 있다면 필요한 Summary, Trend, Risk, Recent Change, Quick Action을 추가한다. Frontend에 필요한 API가 없지만 제품 내부 데이터로 합리적으로 제공할 수 있다면 Backend/API까지 End-to-End로 구현한다. 보여줄 데이터가 없다는 이유로 의미 없는 KPI, 장식용 Chart, Fake Data를 만들지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Projects.jsx`, `frontend/src/screens/Ticket.jsx`, `frontend/src/screens/OrgConsole.jsx`
- **Verification**: 독립 Visual Reviewer 와 독립 Requirement Reviewer 서명, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 Pilot Flow PASS
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-10. Blank Space와 Empty State에 대한 강제 기준

- **Wave**: W7
- **Requirement**: 넓은 화면에 빈 공간이 있다고 무조건 콘텐츠를 늘리지 않는다. 하지만 Page 목적상 사용할 수 있는 정보와 Action이 있는데 기존 Layout 때문에 상단 일부만 사용하고 화면 대부분이 비어 있으면 실패다. Empty State에서는 다음을 판단한다. 1. 데이터가 없을 때 Chart/Table/Card 자체가 필요한가 2. 필요 없으면 Container를 Collapse할 수 있는가 3. 사용자가 다음에 할 Action이 있는가 4. 최근 History나 다른 관련 Context가 유용한가 5. Page Help로 이동해야 할 설명이 본문을 차지하고 있지 않은가 작은 Mascot/Illustration과 문장만 놓고 거대한 빈 화면을 남기지 않는다. 반대로 공간을 채우기 위해 의미 없는 Card를 추가하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-11. Home/Dashboard는 업무 시작점으로 다시 설계

- **Wave**: W10
- **Requirement**: Home은 단순 Metric Dashboard가 아니다. 사용자가 하루 종일 띄워두는 상시 업무 도구라는 전제에서 다음을 우선 검토한다. 1. 지금 처리해야 하는 일 2. 지연 또는 위험 업무 3. 오늘/가까운 마감 4. 승인 또는 응답이 필요한 일 5. 현재 Sprint 상태 6. 주요 Project 위험 7. 최근 변경/업데이트 8. 최근 문서/업무 Context 9. AI 도우미를 통한 빠른 업무 시작 모든 항목을 Card로 만들지 않는다. 사용자별 실제 데이터가 없는 항목은 Compact하게 사라지거나 Empty 상태로 전환한다. Home 화면 중간에 의미 없는 대형 Blank Panel이 남지 않도록 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-12. Project와 Sprint는 의사결정 화면으로 설계

- **Wave**: W10
- **Requirement**: Project는 단순 목록이 아니라 Portfolio 상황을 파악하는 화면이다. 현재 프로젝트 수와 진행률 숫자만 보여주는 데 그치지 말고 실제 데이터가 제공하는 범위에서 Health, 일정 위험, 지연, 최근 변화, 진행률 분포, 우선 확인 대상이 보이는지 검토한다. Table은 빠른 탐색을 위해 유지할 수 있지만 Search, Filter, Sort, Status, Health 표현을 통합된 Workflow로 만든다. Sprint는 회의에서 함께 보는 화면이다. 데이터가 없을 때 큰 Chart Placeholder를 남기지 않는다. 데이터가 있을 때는 Scope, Remaining Work, Ideal vs Actual, Blocked, Delay, Assignee Load, Change를 회의 순서에 맞게 배치한다. 긴 설명문은 Page Help로 이동하고 회의 중 필요한 정보가 화면의 시각적 우선순위를 갖게 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-13. Chat은 단순 Messenger Layout에서 끝내지 않는다

- **Wave**: W9
- **Requirement**: Chat은 ClovirAssist의 중요한 Collaboration/AI Surface다. 좌측 Room List, Main Conversation, Composer라는 기본 Mental Model은 사용할 수 있지만 현재처럼 Main 영역이 대부분 빈 White Canvas인 결과는 완료가 아니다. Room이 비어 있을 때는 Context, 참여자, 사용 목적, 시작 Action을 Compact하게 제공한다. 메시지가 있을 때는 Readability, Code/Table/Attachment, AI 응답, User 응답, Timestamp, Action, Scroll Position을 실제 사용 기준으로 설계한다. AI 도우미와 일반 Team Chat이 같은 제품 언어를 사용하되 역할 차이는 명확하게 표현한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/MyTickets.jsx`, `frontend/src/screens/TeamDocs.jsx`, `frontend/src/screens/ChatRooms.jsx`, `frontend/src/ui/MirrorNotice.jsx`
- **Verification**: `frontend/src/screens/tickets-list.test.jsx`, `frontend/src/screens/cross-screen-invalidation.test.jsx`, `python -m scripts.ui_qa.run --routes user`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-14. 관리자 IA는 현재 Sidebar를 다시 정리하는 수준으로 끝내지 않는다

- **Wave**: W11
- **Requirement**: 현재 관리자 Sidebar에 많은 기능이 여전히 직접 노출되어 있다면 IA 재작업이 충분히 끝난 것으로 보지 않는다. 기존 51번 기준에 따라 Domain -> Page -> 필요한 경우에만 Tab/View/Section 순서로 다시 설계한다. Sidebar 개수를 줄이기 위해 과도한 Tab을 만들지 않는다. 각 기존 Admin Route는 독립 Page 유지, 통합, View/Tab 전환, Domain 이동, 실제 미사용 제거 중 하나로 명시적으로 분류한다. 관리자 Page도 작은 Box 몇 개를 상단에 놓고 아래를 비우는 형태로 끝내지 않는다. Operations, Settings, Organization, Integration 등 각 업무에 맞는 Split View, Detail, Status, History, Action 구조를 사용한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/navConfig.js`, `frontend/src/app/AdminRoutes.jsx`, `frontend/src/screens/settings/SettingsShell.jsx`, `frontend/src/ui/TabShell.jsx`
- **Verification**: `frontend/src/app/nav-features.test.js`, 옛 주소 제자리 렌더 회귀 테스트, Gate 조건 C1b
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-15. 일반 사용자에게 내부 운영 상태와 긴 기술 설명을 노출하지 않는다

- **Wave**: W9
- **Requirement**: 문서 동기화, Scheduler, Worker, Queue, 내부 설정 Key, Raw Error, Backend Path 등 운영 구현 정보는 일반 사용자 화면의 주요 Content가 아니다. 일반 사용자에게 필요한 것은 기능이 정상인지, 지금 무엇을 할 수 있는지, 문제가 있다면 자신이 무엇을 해야 하는지다. 문서 목록의 수동 `지금 동기화`와 정상적인 동기화 운영 정보는 제거한다. 설명이 길어지는 경우 Page Help `?` 또는 권한 있는 기술 정보 영역으로 이동한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/MyTickets.jsx`, `frontend/src/screens/TeamDocs.jsx`, `frontend/src/screens/ChatRooms.jsx`, `frontend/src/ui/MirrorNotice.jsx`
- **Verification**: `frontend/src/screens/tickets-list.test.jsx`, `frontend/src/screens/cross-screen-invalidation.test.jsx`, `python -m scripts.ui_qa.run --routes user`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-16. 디자인 Skill은 실제로 사용하고 역할을 분리

- **Wave**: W8
- **Requirement**: UI/UX Pro Max, Impeccable, Taste를 설치 여부만 확인하고 이름만 언급하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Projects.jsx`, `frontend/src/screens/Ticket.jsx`, `frontend/src/screens/OrgConsole.jsx`
- **Verification**: 독립 Visual Reviewer 와 독립 Requirement Reviewer 서명, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 Pilot Flow PASS
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-17. Visual Reviewer는 코드가 아니라 Screenshot을 먼저 본다

- **Wave**: W8
- **Requirement**: 구현 담당 Agent의 설명, Test PASS, 변경 Line 수를 보고 Visual Quality를 판단하지 않는다. 독립 Reviewer는 실제 Browser Screenshot을 보고 다음을 PASS/FAIL한다. 1. Brand Identity 2. Page Purpose 3. Visual Hierarchy 4. Space Utilization 5. Density 6. Typography 7. Surface/Component Variety 8. Empty/Loading/Error 상태 9. Action Hierarchy 10. Responsive 11. Legacy UI 잔존 12. 전체적인 Tech & SaaS 완성도 13. Table/Metadata Column Width와 데이터 의미 기반 Alignment 14. Search/Filter/Sort Grouping, Control Height, Baseline, 줄바꿈 15. Detail Page의 좌우 Balance와 긴 값/짧은 값의 공간 배분 16. Project, User, Assignee 등 검색이 필요한 Entit
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Projects.jsx`, `frontend/src/screens/Ticket.jsx`, `frontend/src/screens/OrgConsole.jsx`
- **Verification**: 독립 Visual Reviewer 와 독립 Requirement Reviewer 서명, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 Pilot Flow PASS
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-18. 테스트와 Visual Quality를 별도 Gate로 운영

- **Wave**: W15
- **Requirement**: 다음은 서로 다른 Gate다. 1. Functional Gate 기능, API, Backend, 권한, 저장/적용, E2E가 정상인가 2. Regression Gate 기존 필요한 기능이 깨지지 않았는가 3. Accessibility/Performance Gate Keyboard, Focus, Contrast, Large Data, Bundle, Rendering이 정상인가 4. Visual Gate 실제 화면이 충분히 세련되고 제품 수준인가 Functional/Regression Gate가 PASS해도 Visual Gate가 FAIL이면 작업은 미완료다. Visual Gate가 PASS해도 기능이 깨지면 미완료다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage complete`, `bash scripts/run_full_regression.sh`, `bash scripts/static_checks.sh`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-19. Test Server Browser E2E는 실제 상태까지 확인

- **Wave**: W14
- **Requirement**: 주요 Workflow는 다음 흐름으로 확인한다. Screen -> Action -> Network -> API -> Backend -> Data/DB -> UI Result -> Reload -> 관련 화면 -> 권한 상태 위험 Action은 테스트 전 상태를 저장하고 테스트 후 원상복구한다. 삭제는 기존 실제 데이터가 아니라 테스트 전용 Fixture를 사용한다. 인증서 경고나 환경 제약으로 Interactive Chrome이 막히면 가능한 Browser Automation으로 검증하되 그것을 이유로 Visual Review를 생략하지 않는다. 필요하면 Browser가 접근 가능한 환경을 구성하거나 Screenshot을 생성하여 Reviewer가 실제 렌더링을 확인한다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`
- **Verification**: `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth`, Gate 조건 C11 과 C12 와 C13 과 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-20. 완료 조건

- **Wave**: W15
- **Requirement**: 다음 조건을 모두 만족하기 전에는 PROJECT_COMPLETE, 완료, 전면 리뉴얼 완료 같은 표현을 사용하지 않는다. 1. Source 기준 전체 Route가 ROUTE_COVERAGE.json에 존재 2. 전체 Route의 Visual Audit 완료 3. 주요 Workflow Functional Audit 완료 4. 모든 Requirement가 Matrix에 Mapping됨 5. UNKNOWN/TODO/NOT_AUDITED 0건 6. Critical/High Finding 0건 7. 일반 사용자 수동 문서 동기화 제거 확인 8. Purple/Indigo Brand Identity가 Header/Navigation/Primary/AI/Data Highlight에서 실제로 확인됨 9. Home, Project, Sprint, Chat, Detail, Admin 대표 Page의 Before/After Visual Review PASS 10. Empty State에서 거대한 불필요 Blank Canvas가 남는 Route 0건 11. 긴 설명과 내부 운영 정보가 일반 사용자 주요 화면에
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage complete`, `bash scripts/run_full_regression.sh`, `bash scripts/static_checks.sh`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-21. 사람 승인 Gate를 만들지 않는다

- **Wave**: W0
- **Requirement**: Design Direction, Component 선택, Layout 선택, IA 세부 판단을 사용자에게 하나씩 물어보며 작업을 멈추지 않는다. 본 지시사항, 실제 제품 Data, Source, UI/UX Pro Max, Impeccable, Taste, 독립 Reviewer 결과를 근거로 스스로 판단하고 계속 진행한다. 단, Production 파괴 위험, 사용자만 제공할 수 있는 Secret, 외부 시스템 권한처럼 실제로 AI가 해결할 수 없는 사항만 Blocker로 보고한다. 작업 중 새로운 문제를 발견하면 별도 승인 없이 Scope에 포함하여 Root Cause를 해결한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-0-22. 최종 보고 형식

- **Wave**: W15
- **Requirement**: 완료 시 장황한 작업 일지가 아니라 다음을 명확하게 보고한다. 1. 전체 Route 수 / Audit 완료 Route 수 2. 변경된 Route 수 3. Requirement 전체 수 / 완료 수 4. Critical/High Finding 잔여 수 5. 주요 Before/After Screenshot 위치 6. Brand System 변경 요약 7. Home/Project/Sprint/Chat/Admin 핵심 UX 변경 요약 8. Functional E2E 결과 9. Regression 결과 10. Responsive/Zoom 결과 11. Coverage Gate 결과 12. 외부 Blocker가 있다면 그 항목만 작업 도중에는 상태를 숨기지 말되 Checkpoint마다 사용자에게 승인받으려고 중단하지 않는다. 아래 내용은 전체 작업 지시사항이다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/ui_qa/run.py`, `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage complete`, `bash scripts/run_full_regression.sh`, `bash scripts/static_checks.sh`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-1. UI/UX Pro Max

- **Wave**: W9
- **Requirement**: Route/Archetype Audit, Layout, Information Hierarchy, Responsive, Component System, Dashboard/Chart/Form/Search 대안을 설계할 때 사용한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/MyTickets.jsx`, `frontend/src/screens/TeamDocs.jsx`, `frontend/src/screens/ChatRooms.jsx`, `frontend/src/ui/MirrorNotice.jsx`
- **Verification**: `frontend/src/screens/tickets-list.test.jsx`, `frontend/src/screens/cross-screen-invalidation.test.jsx`, `python -m scripts.ui_qa.run --routes user`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-2. Impeccable

- **Wave**: W10
- **Requirement**: Pilot과 각 Wave의 실제 Browser 결과를 Critique하고 정렬, 밀도, 위계, 일관성, 사용성, 누락을 찾는다. 3. Taste 최종 Browser 결과의 Typography, Spacing, Surface, Color Balance, 비율, Visual Rhythm, Detail, SaaS 제품 감도를 마무리한다. Skill 결과가 본 지시사항과 충돌하면 본 지시사항을 우선한다. Skill이 기존 UI를 유지하라고 해석될 수 있는 경우 기능/일반 Affordance만 유지하고 현재 Visual은 보호하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-3. 페이지 제목 및 페이지 도움말 구조 공통화

- **Wave**: W7
- **Requirement**: 모든 페이지의 Page Header 구조를 전수조사한다. 페이지 이름 오른쪽에는 공통 Page Help 기능인 `?`가 표시되어야 하며 이를 누르면 해당 페이지의 도움말이 동일한 방식으로 제공되어야 한다. 현재 어떤 페이지에는 `?`가 있고 어떤 페이지에는 없거나, 도움말에 해당하는 문장이 본문에 직접 노출되는 구조를 정리한다. 페이지 제목, Breadcrumb, 도움말, 부가 설명, 주요 Action의 위치와 간격을 공통 Page Header 규칙으로 정의한다. 도움말이나 설명 문구에 의미 없는 강제 줄바꿈을 사용하지 않는다. 페이지 도움말은 사용자가 해당 페이지에서 무엇을 할 수 있는지 빠르게 이해할 수 있을 정도로 짧고 자연스럽게 작성한다. 4. Card, Section, Spacing, Typography 전면 재설계 현재 사용 중인 Card 디자인을 기준으로 border, radius, padding, shadow 정도만 수정하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-4. 구현 완료 후 Impeccable과 Taste 관점으로 실제 Browser 화면을 다시 검수한다.

- **Wave**: W1
- **Requirement**: 특정 화면에서 발견한 문제를 해당 화면만 수정하지 말고, 동일한 공통 컴포넌트와 패턴을 사용하는 다른 페이지까지 전수조사하여 함께 개선한다. 전체 디자인 방향은 Tech & SaaS 스타일을 기준으로 한다. 기능성과 사용성만 개선하는 것이 아니라 시각적으로도 세련되고 완성도 높은 디자인을 목표로 한다. 사용자가 처음 봤을 때 깔끔하고 현대적이며 잘 만든 상용 제품이라는 인상을 받을 수 있어야 한다. 색상, Typography, 여백, 비율, 카드 구성, 깊이감, 강조 표현, 차트, 인터랙션까지 전체적인 Visual Quality를 적극적으로 개선한다. 단순히 화려하게 꾸미는 것이 아니라 정보 구조, 가독성, 밀도, 일관성, 사용성과 함께 절제된 세련미를 갖춘 Tech & SaaS 제품을 지향한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/theme.js`, `scripts/generate_design_tokens.mjs`, `frontend/src/styles/tokens.css`, `app/static/css/tokens.css`
- **Verification**: `frontend/src/ui/theme-contract.test.js`, `frontend/src/styles/tokens-generated.test.js`, `node scripts/generate_design_tokens.mjs --check`, assertion `brand_presence`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-5. 검색 및 필터 UI 공통 시스템 재설계

- **Wave**: W5
- **Requirement**: Portal 전체 페이지의 Search, Filter, Select, Sort, Condition 영역을 전수조사한다. 현재 페이지마다 검색창 크기, 필터 순서, Select 크기, 조건 배치가 제각각인 구조를 개선한다. 공통 Search/Filter Bar 패턴을 설계하되 모든 페이지에 동일한 필터 구성을 강제로 적용하지 않는다. 검색창은 주요 탐색 기능이라면 충분한 너비와 시각적 우선순위를 갖도록 한다. 필터가 많은 경우 검색, 주요 필터, 보조 필터, 정렬 기능의 위계를 명확하게 구분한다. 문서, 자유게시판, 기능 개선 제안 등 검색, 카테고리, 상태, 정렬이 뒤섞여 있는 페이지를 우선적으로 개선한다. 프로젝트처럼 데이터가 많고 이름으로 찾는 것이 자연스러운 항목은 검색 가능한 Autocomplete 또는 Combobox 방식을 사용한다. 입력 중 일치하는 후보를 아래에 표시하고 Keyboard와 Mouse로 선택할 수 있어야 한다. 다른 필터도 동일한 방식이 더 적합한지 조사하되 모든 Select를 무조건 검색형으로 변경하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/FilterBar.jsx`, `frontend/src/ui/filters.jsx`, `frontend/src/screens/TicketFilterBar.jsx`, `frontend/src/screens/DataScreen.jsx`
- **Verification**: assertion `isolated_control_row`, assertion `control_baseline_mismatch`, assertion `plain_dropdown_for_entity`, `frontend/src/ui/FilterBar.jsx` 소비처 렌더 테스트
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-6. 전체 Page Layout 및 Responsive 구조 수정

- **Wave**: W2
- **Requirement**: 현재 티켓 상세, 문서 상세, 새 티켓 등에서 본문이 왼쪽으로 몰리고 오른쪽에 지나치게 큰 빈 공간이 생기는 현상을 공통 Layout 문제로 조사한다. 특정 페이지의 margin이나 width만 개별 수정하지 않는다. 공통 Page Container, Content Width, Grid, Breakpoint, max-width, padding, responsive behavior를 점검한다. 브라우저 Zoom이나 해상도 변화에 따라 화면이 비정상적으로 한쪽으로 몰리지 않아야 한다. FHD, QHD, 4K 등 대표적인 화면 환경과 다양한 Browser Zoom을 검증하되 특정 해상도 전용 Pixel 값을 하드코딩하지 않는다. Breakpoint 역시 페이지마다 따로 만들지 않고 공통 Responsive 정책을 사용한다. 고정 width, 고정 height, 임의 margin, 수동 줄바꿈으로 화면을 맞추는 코드는 제거한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/AppShell.jsx`, `frontend/src/app/TopBrand.jsx`, `frontend/src/app/TopSearch.jsx`, `frontend/src/styles/root.css`
- **Verification**: `frontend/src/app/topbar-contract.test.jsx`, assertion `narrow_main`, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-7. 티켓 및 문서 상세 화면 공통 Detail Layout 적용

- **Wave**: W8
- **Requirement**: 티켓 상세, 문서 상세 및 유사한 상세 화면은 공통 Detail Layout을 사용한다. 상단 전체 폭에는 해당 항목의 주요 속성과 메타데이터를 표시한다. 그 아래 Desktop Layout은 본문 영역과 보조 영역을 약 2:1 비율로 사용하는 것을 기본으로 하되 고정 Pixel Width로 구현하지 않는다. 왼쪽 주요 영역에는 본문을 표시한다. 오른쪽 보조 영역에는 첨부파일과 댓글을 표시한다. 화면이 좁아지는 경우 한 열 구조 등 적절한 Responsive Layout으로 전환한다. 본문이 현재처럼 좌측 일부 공간만 사용하고 나머지가 비어 있지 않도록 한다. 첨부파일과 댓글 데이터가 있는데 표시되지 않는 문제는 UI뿐만 아니라 데이터 연결, 조건부 Rendering, 권한 처리까지 확인한다. 유사한 Detail Page에서도 동일한 패턴을 재사용할 수 있도록 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Projects.jsx`, `frontend/src/screens/Ticket.jsx`, `frontend/src/screens/OrgConsole.jsx`
- **Verification**: 독립 Visual Reviewer 와 독립 Requirement Reviewer 서명, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 Pilot Flow PASS
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-8. 티켓 Grid 및 티켓 작성 UX 개선

- **Wave**: W6
- **Requirement**: 티켓 Grid에서 상태와 우선순위를 변경하기 위해 매번 상세 수정 화면으로 이동하지 않도록 한다. 권한이 있는 사용자는 Grid에서 상태 또는 우선순위를 클릭하여 바로 변경할 수 있도록 Inline Edit 기능을 제공한다. 변경, 저장, 실패, 권한 없음 상태까지 처리한다. 모든 값을 Inline Edit 대상으로 만들지 않는다. 실제로 빠른 변경이 유용한 항목만 대상으로 한다. `수정`, `나에게 배정`, `보기`, `처리` 등 Grid Row에 반복적으로 표시되는 Action Button도 전면 재설계한다. 현재처럼 작은 외곽선 버튼이 각 행마다 반복되는 구조를 지양한다. 자주 사용하는 핵심 Action은 빠르게 접근할 수 있도록 유지하고 낮은 빈도의 Action은 Context Menu 등 더 적합한 방식을 검토한다. 단순히 모든 Action을 아이콘 버튼으로 대체하지 않는다. 새 티켓 화면도 공통 Form Layout을 사용한다. 새 티켓 오른쪽 `작성 도움`은 아래 내용을 중심으로 자연스럽게 다시 작성한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-9. Sprint 회의 화면 전면 개선

- **Wave**: W10
- **Requirement**: Sprint 회의 화면은 실제 회의에서 판단과 논의를 돕는 화면으로 다시 설계한다. 담당자 현황 카드는 현재 반복적인 흰색 카드 구조를 그대로 사용하지 않는다. 담당자별 티켓 수, 남은 업무량, 지연 여부 등 실제 비교에 필요한 정보를 빠르게 파악할 수 있도록 한다. 계획 논의 영역에는 Sprint에 포함할 티켓을 찾기 위한 프로젝트 검색과 필요한 티켓 필터를 제공한다. 현재 Burndown 그래프는 사용자가 의미를 바로 이해하기 어려우므로 다시 설계한다. 실제 남은 업무량과 이상적인 감소선을 명확하게 구분한다. 축, 단위, 범례, 기간을 명확하게 표시한다. Ticket Count와 WD가 의미 없이 혼합되지 않도록 실제 Sprint 운영 기준을 명확하게 정의한다. Sprint 회의에서 실제 판단에 필요한 다음 정보를 검토한다. 남은 업무량 추이 Sprint 중 추가 또는 제외된 Scope 변화 담당자별 남은 업무량 지연 또는 Blocked 업무 완료 추이 그래프 수를 늘리는 것이 목적은 아니다. 실제 의사결정에 필요한 정보만 추가한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-10. Data Grid 및 Table Design System 전면 개선

- **Wave**: W6
- **Requirement**: Portal 전체 Data Grid와 Table을 전수조사하고 공통 Grid Design System을 정의한다. Header, Row Height, Typography, Hover, Selected Row, Checkbox, Sorting, Pagination, Empty State, Loading State를 통일한다. 현재처럼 단순한 Excel 표처럼 보이지 않도록 한다. 행과 열을 불필요한 Border로 모두 구분하지 않는다. 데이터 밀도는 유지하면서도 사용자가 행을 쉽게 추적할 수 있도록 Visual Rhythm을 만든다. 상태, 우선순위, 담당자, 날짜, 프로젝트, Action 등 데이터 유형별 표현 규칙을 정의한다. 긴 제목, 프로젝트명, 오류 메시지가 들어와도 Layout이 깨지지 않아야 한다. Column Width는 데이터 특성에 따라 결정한다. Pagination 역시 공통 패턴으로 통일한다. 데이터가 많은 화면은 필요하면 Pagination, Virtualization, Server-side Filtering 등 성능을 고려한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-11. Button, Action, Status, Badge 시스템 전면 개선

- **Wave**: W4
- **Requirement**: Portal 전체 Button을 전수조사한다. Primary, Secondary, Tertiary, Destructive, Inline Action의 역할을 정의한다. Button Height, Radius, Border, Font Weight, Padding을 공통 Design Token 기반으로 관리한다. 버튼이 많은 화면에서 모든 버튼이 동일한 시각적 강도를 갖지 않도록 한다. 화면의 주요 Action이 명확하게 보여야 한다. Grid 내부 Action도 동일한 Button System을 사용한다. Hover, Focus, Disabled, Loading 상태까지 설계한다. Portal 전체 Badge, Status, Tag, Pill 사용처도 전수조사한다. 현재처럼 `정상`, `위험`, `완료`, `높음`, `확인됨` 등의 값을 모두 동일한 알약 형태로 표현하지 않는다. Status, Category, Tag, Editable Value를 목적에 따라 구분한다. 단순 Text Status가 더 적합한 곳은 Badge 자체를 사용하지 않는다. 색상만으로 상태를 전달하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/kit.css`, `frontend/src/ui/adminKit.jsx`, `frontend/src/ui/density.js`
- **Verification**: `frontend/src/ui/kit.test.jsx`, `frontend/src/ui/density-contract.test.jsx`, assertion `surface_repetition`, assertion `oversized_empty_surface`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-12. Modal, Dialog, Popup 공통 구조 재설계

- **Wave**: W4
- **Requirement**: Portal 전체 Modal, Dialog, Confirm, Popup 계열을 전수조사한다. Header, Title, Close, Body, Footer, Primary Action, Secondary Action, Destructive Action의 위치와 우선순위를 통일한다. 현재 사용자 상세 Modal의 `더보기`처럼 Action이 무질서하게 여러 줄로 배치되지 않도록 한다. 버튼이 많아지는 경우 Action Group 또는 Overflow Action을 사용한다. 위험 작업과 일반 작업은 시각적, 공간적으로 구분한다. 콘텐츠가 길어져도 Modal Layout이 깨지지 않아야 한다. 필요한 경우 Body 영역만 Scroll한다. Modal 크기는 콘텐츠와 화면 크기에 따라 Responsive하게 동작하도록 하고 화면별로 임의의 Pixel Width를 반복 정의하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/kit.css`, `frontend/src/ui/adminKit.jsx`, `frontend/src/ui/density.js`
- **Verification**: `frontend/src/ui/kit.test.jsx`, `frontend/src/ui/density-contract.test.jsx`, assertion `surface_repetition`, assertion `oversized_empty_surface`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-13. Global Header 및 로고 개선

- **Wave**: W2
- **Requirement**: 좌측 상단 ClovirAssist 로고 영역을 현재보다 조금 줄인다. 단순 이미지 크기만 축소하지 말고 Header 높이, Global Search, 사용자 영역과의 균형을 함께 조정한다. Logo가 Header의 시각적 중심을 과도하게 차지하지 않도록 한다. Header, Sidebar, Main Content의 Visual Language를 통일한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/AppShell.jsx`, `frontend/src/app/TopBrand.jsx`, `frontend/src/app/TopSearch.jsx`, `frontend/src/styles/root.css`
- **Verification**: `frontend/src/app/topbar-contract.test.jsx`, assertion `narrow_main`, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-14. Global Search 전면 재설계

- **Wave**: W2
- **Requirement**: 현재 상단 검색을 클릭했을 때 표시되는 Search Overlay를 전면 재설계한다. 검색 Input, Overlay 크기, 위치, Spacing, Typography, Result Group, Selected State를 Tech & SaaS 스타일로 설계한다. 최근 방문, 메뉴, 티켓, 문서 등 검색 결과 유형을 쉽게 구분할 수 있도록 한다. 단순한 흰 Popup 안에 Text List가 나열된 형태에서 벗어난다. Keyboard Up/Down, Enter, Esc 등 Keyboard Navigation을 지원한다. 검색 중 Loading, 결과 없음, Error State도 포함한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/AppShell.jsx`, `frontend/src/app/TopBrand.jsx`, `frontend/src/app/TopSearch.jsx`, `frontend/src/styles/root.css`
- **Verification**: `frontend/src/app/topbar-contract.test.jsx`, assertion `narrow_main`, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-15. 채팅방 UI 전면 재설계

- **Wave**: W9
- **Requirement**: 현재 채팅방이 Claude 또는 다른 AI 서비스의 전형적인 UI를 모방한 것처럼 보이지 않도록 한다. 메시지 왼쪽 세로 Bar 등 특정 AI 제품을 연상시키는 패턴을 제거한다. 사용자 메시지와 AI 응답은 명확히 구분하되 과도한 Bubble, 이모지, 아이콘, 색상 장식을 사용하지 않는다. 메시지 영역, 작성 영역, 첨부파일, 코드, 표, Action을 ClovirAssist 자체의 Design Language로 다시 설계한다. Portal의 Typography, Spacing, Button, Surface System을 동일하게 사용한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/MyTickets.jsx`, `frontend/src/screens/TeamDocs.jsx`, `frontend/src/screens/ChatRooms.jsx`, `frontend/src/ui/MirrorNotice.jsx`
- **Verification**: `frontend/src/screens/tickets-list.test.jsx`, `frontend/src/screens/cross-screen-invalidation.test.jsx`, `python -m scripts.ui_qa.run --routes user`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-16. 의미 없는 줄바꿈 및 고정 Layout 전수조사

- **Wave**: W7
- **Requirement**: Portal 곳곳에서 발생하는 의미 없는 줄바꿈을 개별 문장 문제가 아닌 공통 구조 문제로 조사한다. Page Header, Help Text, Card Description, Chart Description, Form Help Text, Table Cell, Alert, Empty State 등 전체 Text Component를 조사한다. 문장을 맞추기 위한 `<br>` 또는 임의의 Width와 Height 사용을 제거한다. Container 크기에 따라 자연스럽게 wrapping되어야 한다. 짧은 문장이 불필요하게 여러 줄로 나뉘거나 충분한 공간이 있는데도 다음 줄로 내려가는 현상이 없어야 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-17. Form 및 Input UI 공통 개선

- **Wave**: W5
- **Requirement**: Portal 전체 Form을 전수조사한다. Input, Textarea, Select, Autocomplete, Date Picker, Checkbox, Radio 등 Form Control의 크기, 높이, Label, Helper Text, Error State를 통일한다. 작은 Input 여러 개가 임의의 Grid에 배치되어 화면이 비어 보이거나 정렬이 맞지 않는 구조를 개선한다. 필드 중요도와 입력 순서에 맞게 Form Layout을 구성한다. 필수 항목, 선택 항목, Validation Error를 쉽게 이해할 수 있어야 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/FilterBar.jsx`, `frontend/src/ui/filters.jsx`, `frontend/src/screens/TicketFilterBar.jsx`, `frontend/src/screens/DataScreen.jsx`
- **Verification**: assertion `isolated_control_row`, assertion `control_baseline_mismatch`, assertion `plain_dropdown_for_entity`, `frontend/src/ui/FilterBar.jsx` 소비처 렌더 테스트
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-18. Empty State 공통 개선

- **Wave**: W6
- **Requirement**: Portal 전체 Empty State를 전수조사한다. 큰 캐릭터 이미지나 Illustration으로 빈 공간을 채우는 방식을 기본 패턴으로 사용하지 않는다. 사용자가 데이터가 없는 이유와 다음 행동을 빠르게 이해할 수 있도록 한다. 필요한 경우 명확한 Primary Action을 제공한다. 페이지마다 제각각인 Empty State 문구, 이미지, Button 위치를 공통화한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-19. 사용자 세션 만료 및 인증 상태 처리 개선

- **Wave**: W6
- **Requirement**: 현재 사용자 Session이 만료되어도 기존 화면에 그대로 남아 있는 문제를 수정한다. Session 또는 Access Token이 만료되어 인증이 더 이상 유효하지 않은 경우 사용자를 로그인 화면으로 이동시켜야 한다. API 요청에서 인증 만료가 확인되는 경우 각 페이지가 개별적으로 처리하지 않고 공통 Authentication Layer에서 처리한다. Session 만료 후 화면에 이전 데이터가 정상적으로 사용 가능한 것처럼 남아 있지 않도록 한다. 인증 정보와 민감한 Client State를 적절하게 정리한 뒤 로그인 화면으로 이동한다. 로그인 후 사용자가 원래 접근하던 페이지로 돌아가는 것이 안전하고 적절한 경우 Return URL을 활용할 수 있도록 한다. 단, 로그인 화면, 인증 Callback, 권한이 없는 페이지 등에서 Redirect Loop가 발생하지 않도록 한다. `401 인증 만료`와 `403 권한 없음`을 동일하게 처리하지 않는다. Session 갱신 기능이 존재한다면 중앙에서 일관되게 처리하며 여러 요청이 동시에 Session 갱신을 시도하지 않도록 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-20. Loading, Error, Success Feedback 공통화

- **Wave**: W7
- **Requirement**: API를 사용하는 모든 주요 화면에서 Loading, Success, Error 상태를 전수조사한다. 페이지마다 임의의 Loading Text 또는 Spinner를 구현하지 않는다. 전체 화면 Loading, Section Loading, Table Loading, Button Loading 등 상황에 맞는 공통 패턴을 정의한다. 데이터가 로딩 중인데 빈 화면처럼 보이지 않도록 한다. 사용자가 실행한 작업의 성공 또는 실패를 명확하게 알 수 있도록 한다. Toast, Snackbar, Inline Error, Form Error의 역할을 구분한다. 모든 성공 작업에 불필요한 Toast를 남발하지 않는다. 사용자의 조치가 필요한 오류는 원인과 다음 행동을 이해할 수 있도록 자연스러운 문구를 제공한다. Backend Error Message를 그대로 사용자 화면에 노출하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-21. 권한 및 Action UX 공통화

- **Wave**: W14
- **Requirement**: 사용자의 역할과 권한에 따라 Button과 Action이 일관되게 표시되어야 한다. 페이지마다 권한 체크 로직을 중복 구현하지 않는다. 권한이 없는 기능을 무조건 Disabled Button으로 남겨두지 않는다. 기능을 보여줄 필요가 없는 경우 숨기고, 사용자가 기능의 존재를 알아야 하지만 권한이 없는 경우에는 이유를 알 수 있도록 한다. Frontend에서 숨기는 것만으로 권한을 보장하지 않으며 Backend Authorization과 일치해야 한다. 동일한 Action이 페이지에 따라 가능하거나 불가능하게 보이는 불일치가 없도록 전수조사한다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`
- **Verification**: `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth`, Gate 조건 C11 과 C12 와 C13 과 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-22. UX Writing 및 사용자 문구 전수조사

- **Wave**: W10
- **Requirement**: Portal 전체 사용자 노출 문구를 검토한다. AI가 자동 생성한 것처럼 장황하거나 어색한 문장, 개발자 용어, 내부 시스템 용어를 그대로 노출하지 않는다. 사용자가 실제로 이해할 수 있는 자연스러운 한국어를 사용한다. Button Label, Empty State, Help Text, Error Message, Confirm Message, Tooltip의 문체와 용어를 통일한다. 동일한 개념을 페이지마다 서로 다른 이름으로 표현하지 않는다. 시스템 내부 구현 방식, Scheduler, Queue, Worker 등 사용자가 알 필요 없는 기술 용어는 일반 사용자 화면에 불필요하게 노출하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-23. 불필요한 하드코딩 및 중복 UI 구현 제거

- **Wave**: W0
- **Requirement**: 이번 UI 개선 과정에서 Portal 전체의 반복 하드코딩을 함께 조사한다. 페이지마다 반복되는 색상, Radius, Shadow, Spacing, Width, Typography 값을 Design Token 또는 Theme으로 통합한다. Status Color, Button Variant, Badge Style 등 의미를 갖는 시각 규칙도 공통화한다. 동일한 Search, Filter, Modal, Grid, Page Header, Empty State, Form 패턴을 페이지별로 별도 구현하고 있다면 공통 컴포넌트로 통합한다. API URL, Route, Status Label, Permission Name, Date Format, Pagination Size, Timeout, Sync Interval 등 변경 가능성이 있거나 여러 위치에서 공유되는 값은 적절한 공통 위치에서 관리한다. 특정 페이지를 맞추기 위한 Magic Number와 임시 CSS Override가 누적되어 있다면 원인을 조사하고 공통 Layout 또는 Component 수준에서 해결한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-24. 상태 유지 및 화면 복귀 UX 개선

- **Wave**: W14
- **Requirement**: 검색, 필터, 정렬, Pagination을 사용하다 상세 화면으로 이동한 뒤 목록으로 돌아왔을 때 사용자의 작업 맥락을 불필요하게 잃지 않도록 한다. 목록 화면으로 돌아올 때 합리적인 범위에서 기존 검색 조건, 필터, 정렬, 페이지 위치를 유지한다. 단, 모든 UI State를 무조건 영구 저장하지 않는다. 새로운 Session에서도 유지해야 하는 사용자 Preference와 해당 탐색 과정에서만 유지하면 되는 임시 State를 구분한다. Browser Back/Forward 동작도 자연스럽게 동작하도록 한다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`
- **Verification**: `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth`, Gate 조건 C11 과 C12 와 C13 과 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-25. 접근성 및 Keyboard Interaction 검수

- **Wave**: W14
- **Requirement**: Button, Link, Input, Select, Modal, Search, Grid 등 Interactive Component를 Keyboard만으로도 사용할 수 있는지 검수한다. Focus State가 명확하게 보여야 한다. Modal이 열리면 Focus가 적절하게 이동하고 닫으면 기존 위치로 돌아와야 한다. 색상만으로 중요한 상태를 전달하지 않는다. Text Contrast와 Form Label 관계도 검수한다. 단순히 접근성 점수만 맞추는 것이 아니라 실제 사용성이 좋아지도록 한다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`
- **Verification**: `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth`, Gate 조건 C11 과 C12 와 C13 과 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-26. 성능 및 대용량 데이터 UI 검수

- **Wave**: W14
- **Requirement**: Data Grid, Search, Filter, Autocomplete 등에 데이터가 많아져도 UI가 급격히 느려지지 않도록 한다. 대량 데이터를 한 번에 Browser에 Rendering하는 구조가 있다면 Pagination, Virtualization, Server-side Search 등 적절한 방식을 검토한다. 검색 Input마다 불필요하게 API가 호출되지 않도록 Debounce 등 필요한 처리를 적용한다. 단, 임의의 Delay 값을 Component마다 하드코딩하지 않는다. UI 개선으로 불필요한 Re-render 또는 과도한 Animation이 늘어나지 않도록 한다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`
- **Verification**: `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth`, Gate 조건 C11 과 C12 와 C13 과 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-27. 최종 Visual Audit 및 완료 기준

- **Wave**: W15
- **Requirement**: 이번 작업은 코드 수정과 기능 테스트가 PASS했다고 완료된 것으로 판단하지 않는다. 구현 완료 후 사용자 영역과 관리자 영역의 주요 페이지를 실제 Browser에서 다시 확인한다. 기존 Card, Grid, Button, Filter, Modal, Badge, Form, Search 스타일이 의도치 않게 남아 있는 화면을 전수조사한다. 한두 페이지에만 새로운 스타일이 적용되고 다른 페이지에는 기존 디자인이 남아 있는 상태를 완료로 처리하지 않는다. 동일한 공통 컴포넌트를 사용하는 화면은 모두 새로운 Design System이 적용되어야 한다. UI/UX Pro Max, Impeccable 등의 Audit 관점으로 최종 화면을 다시 점검한다. 다음 항목을 반드시 검증한다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage complete`, `bash scripts/run_full_regression.sh`, `bash scripts/static_checks.sh`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-28. 이모지, 장식 문자, AI스러운 표현 전수 제거

- **Wave**: W10
- **Requirement**: 앞서 정의한 원칙이 일부 화면에만 적용된 상태로 남지 않도록 Portal 전체 사용자 노출 문자열과 컴포넌트를 다시 전수조사한다. 이모지, 장식 목적의 Unicode 문자, 불필요한 특수기호, AI가 생성한 화면에서 자주 사용하는 장식 표현이 남아 있으면 모두 제거한다. 문서 제목 앞의 자물쇠 문자처럼 기능이나 상태를 이모지로 표현하지 않는다. 기능적으로 의미가 필요한 경우에는 Design System에 정의된 아이콘 또는 명확한 Text를 사용한다. 아이콘 역시 단순 장식 목적으로 사용하지 않는다. 텍스트를 꾸미기 위한 `-`, `·` 등의 문자 반복 사용도 제거한다. 현재 화면에 보이는 부분만 수정하지 말고 Source Code의 사용자 노출 문자열, Empty State, Help Text, Alert, Tooltip, Button Label, Table Cell 등까지 전수조사한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-29. 문서 잠금 기능 제거 및 문서 동기화 UX 정리

- **Wave**: W9
- **Requirement**: 현재 Portal의 문서 잠금 기능은 제거한다. 문서 목록, 상세, 작성, 수정, 권한 처리, API, Backend Logic, Database, Cache Model 등 잠금 기능과 연결된 전체 사용처를 조사한다. 자물쇠 표시만 UI에서 숨기고 잠금 관련 Backend Logic, 상태 값, 사용하지 않는 코드가 그대로 남지 않도록 한다. 기존 데이터에 잠금 상태가 존재한다면 서비스 영향 없이 제거하거나 무시할 수 있도록 호환 처리를 검토한다. 문서 동기화는 앞서 정의한 시스템 Scheduler 기반 자동 동기화 정책을 따른다. 일반 사용자 문서 화면에는 `지금 동기화` 같은 수동 동기화 기능을 기본 Action으로 제공하지 않는다. 정상적인 마지막 동기화 시간, 동기화 완료 여부, 실행 주기 같은 내부 운영 정보도 일반 사용자에게 강조하지 않는다. 실제 동기화 문제로 사용자 기능에 영향이 발생하거나 사용자의 조치가 필요한 경우에만 필요한 상태와 안내를 제공한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/MyTickets.jsx`, `frontend/src/screens/TeamDocs.jsx`, `frontend/src/screens/ChatRooms.jsx`, `frontend/src/ui/MirrorNotice.jsx`
- **Verification**: `frontend/src/screens/tickets-list.test.jsx`, `frontend/src/screens/cross-screen-invalidation.test.jsx`, `python -m scripts.ui_qa.run --routes user`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-30. 관리자 Information Architecture 전면 재구성

- **Wave**: W11
- **Requirement**: 현재 관리자 Sidebar에는 관리 기능이 지나치게 많은 개별 페이지로 직접 노출되어 있어 기능 탐색이 어렵고 기능 간 관계도 파악하기 어렵다. 현재 메뉴 구조를 그대로 유지한 채 이름이나 디자인만 변경하지 않는다. 관리자 기능 전체를 실제 기능, 업무 Domain, 사용 빈도, 사용자 흐름을 기준으로 다시 조사하고 Information Architecture를 재설계한다. 기능 하나마다 Sidebar 메뉴 하나를 만드는 구조를 지양한다. Sidebar에는 주요 관리 영역만 노출하고 세부 기능은 각 관리 영역 내부의 Tab, Section, View 등으로 제공한다. 현재 메뉴 구조를 기준으로 다음과 같은 상위 관리 영역을 우선 검토한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/navConfig.js`, `frontend/src/app/AdminRoutes.jsx`, `frontend/src/screens/settings/SettingsShell.jsx`, `frontend/src/ui/TabShell.jsx`
- **Verification**: `frontend/src/app/nav-features.test.js`, 옛 주소 제자리 렌더 회귀 테스트, Gate 조건 C1b
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-31. 관리자 영역 전체 Design System 적용

- **Wave**: W12
- **Requirement**: 앞서 정의한 Card, Grid, Button, Search, Filter, Modal, Typography, Spacing, Surface, Responsive 개선사항은 사용자 영역뿐만 아니라 관리자 영역 전체에도 동일하게 적용한다. 관리자 화면이라고 해서 단순한 흰색 Panel과 Table만 사용하는 별도 디자인 체계를 만들지 않는다. 다만 관리자 화면은 정보 밀도와 운영 효율성이 중요하므로 사용자 화면보다 적절히 높은 Density를 사용할 수 있다. 시스템 정책, 서비스 상태, 연동, AI 설정, 기능 플래그, 메일 발송, 감사 기능 등 모든 관리자 화면을 같은 Design Language로 통일한다. 현재 관리자 페이지의 과도한 빈 공간, 큰 흰색 박스, 버튼 나열, 긴 설명문, 불균형한 Column Width를 전수조사한다. 관리자 화면도 실제 상용 Tech & SaaS 제품의 Administration Console처럼 정돈되고 세련되게 보여야 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-32. 설정 페이지 UX 전면 재설계

- **Wave**: W12
- **Requirement**: 현재 설정 페이지는 값과 설명을 단순 Table 또는 흰색 Card에 나열하고 있어 설정 가능한 값과 읽기 전용 정보의 차이가 명확하지 않다. 모든 설정 항목은 다음 정보를 기준으로 재설계한다. 현재 값 설정의 의미 변경 가능 여부 변경 방법 변경 시 영향 현재 적용 상태 필요한 경우 검증 또는 연결 테스트 읽기 전용 설정은 Input처럼 보이지 않도록 한다. 수정 가능한 설정은 어디에서 어떻게 변경할 수 있는지 명확하게 보여야 한다. 설정이 서버 환경이나 외부 Configuration에 의해 관리되어 Portal에서 변경할 수 없다면 이를 자연스러운 사용자 언어로 설명한다. 환경변수 이름이나 서버 File Path를 설정 설명의 중심으로 사용하지 않는다. 설정 저장 후 실제 적용 여부, 재시작 필요 여부, 실패 여부를 명확하게 표시한다. 설정마다 서로 다른 저장 방식과 Action 패턴을 만들지 말고 공통 Settings Interaction을 사용한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-33. OS와 서비스 동작 화면 재설계

- **Wave**: W12
- **Requirement**: 현재 `OS와 서비스 동작`의 `변경` 영역처럼 기능 이름을 Button으로 일렬 나열하는 형태를 사용하지 않는다. `TLS 인증서 교체`, `DNS 서버`, `호스트 이름`, `시간 동기화 서버`, `아웃바운드 프록시`, `타임존 수정`은 각각 독립적인 시스템 설정이며 단순 Button Group이 아니다. 각 설정의 이름, 현재 상태 또는 현재 핵심 값, 간단한 설명, 필요한 변경 Action이 자연스럽게 연결되도록 공통 Settings Pattern으로 표현한다. 사용자는 버튼을 누르기 전에 현재 어떤 설정이 적용되어 있는지 이해할 수 있어야 한다. 서비스 영역의 반복적인 `재시작` 버튼도 단순히 우측에 일렬로 배치하지 않는다. 서비스 이름, 현재 상태, 마지막 상태 확인 결과, 사용할 수 있는 Action을 하나의 구조 안에서 이해할 수 있도록 재설계한다. 서비스 재시작처럼 시스템에 영향을 줄 수 있는 작업은 일반 설정 변경과 같은 시각적 수준으로 취급하지 않는다. 사용자가 작업의 의미와 영향을 이해한 상태에서 실행할 수 있어야 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-34. 관리자 설정 Modal 및 시스템 변경 Workflow 개선

- **Wave**: W12
- **Requirement**: TLS 인증서 교체처럼 시스템에 직접 영향을 주는 설정 Modal도 공통 Modal Design System을 사용한다. 큰 Textarea 몇 개와 적용 버튼만 제공하는 형태에서 벗어난다. 각 필드의 목적, 입력 형식, Validation Error, 현재 상태, 적용 결과를 이해하기 쉽게 표시한다. 인증서와 개인키처럼 서로 관계가 있는 값은 적용 전에 기본 Validation을 수행한다. 오류가 확인 가능한 경우 저장 이후가 아니라 가능한 한 입력 또는 검증 단계에서 안내한다. 민감한 값은 저장 이후 화면에 다시 평문으로 노출하지 않는다. DNS, Hostname, Proxy, Timezone 등 시스템 설정 변경도 기능별로 서로 다른 임시 Modal을 반복 구현하지 않는다. 공통 Settings Workflow를 기반으로 한다. 변경으로 서비스 영향이나 재시작이 필요한 경우 적용 전에 명확하게 안내한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-35. Alert, Warning, Notice, Error 디자인 시스템 재설계

- **Wave**: W7
- **Requirement**: 현재 메일 발송, 연동, AI 설정 등 여러 관리자 페이지에서 큰 외곽선 Box에 `주의`, `안내`와 긴 문장을 표시하는 방식이 반복되고 있다. Portal 전체 Alert, Warning, Notice, Error, Information 표현을 전수조사하고 공통 Feedback Design System을 만든다. 모든 안내를 큰 Border Box로 표현하지 않는다. 정보 중요도에 따라 Inline Notice, Section Notice, Warning, Critical Alert 등 적절한 위계를 사용한다. 단순 참고 정보와 사용자의 실제 조치가 필요한 경고를 같은 강도로 표현하지 않는다. 경고가 필요한 경우 사용자가 다음 내용을 쉽게 이해할 수 있어야 한다. 무엇이 문제인지 어떤 영향이 있는지 필요한 경우 무엇을 해야 하는지 긴 기술 설명을 하나의 Alert 안에 모두 넣지 않는다. 필요한 기술 세부 정보는 별도의 상세 정보나 진단 영역에서 확인할 수 있도록 한다. Color만으로 Severity를 전달하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-36. 관리자 화면의 내부 구현 정보 노출 제거

- **Wave**: W12
- **Requirement**: 현재 관리자 화면에는 일반 관리자가 알 필요 없는 Backend 구현 정보가 지나치게 많이 노출되어 있다. 다음 유형의 정보를 전수조사한다. 환경변수 이름 서버 내부 File Path Database 내부 ID Backend Config Key Raw Feature Flag Key CLI 실행 방식 Secret 저장 위치 내부 Service Account 동작 방식 Backend Error 원문 내부 Code 또는 Module 이름 일반 관리자에게 필요한 것은 구현 방법이 아니라 현재 상태, 영향, 필요한 설정과 Action이다. 예를 들어 `smtp.enabled`, `{host}`, `{from_address}` 같은 내부 변수명을 사용자 안내의 중심으로 사용하지 않는다. 실제 사용자가 이해할 수 있는 자연스러운 표현으로 변경한다. 기술 정보가 운영 또는 장애 분석에 필요한 경우 기본 화면에 항상 노출하지 않는다. 적절한 권한을 가진 사용자가 `기술 정보`, `진단 정보` 등의 형태로 추가 확인할 수 있도록 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-37. 연동 설정 화면 전면 개선

- **Wave**: W12
- **Requirement**: 현재 연동 화면은 Database ID, Token 상태, 서버 환경변수 등 내부 구현 정보가 중심으로 표시되어 실제 어떤 서비스가 연결되어 있고 정상인지 파악하기 어렵다. 연동 화면은 Integration 단위로 다음 내용을 중심으로 재설계한다. 연동 대상 현재 연결 상태 필요한 설정 여부 마지막 정상 확인 연결 테스트 필요한 관리 Action Database, Notion, Ticket, Document 등 실제 Integration 단위로 상태를 이해할 수 있도록 한다. Raw Database ID나 Token 값을 주요 화면 정보로 강조하지 않는다. 사용자가 변경할 수 없는 서버 관리 값은 Form Input처럼 표시하지 않는다. Connection Test는 무엇을 검증하는지 알 수 있어야 한다. 성공, 실패, Timeout 등 결과는 공통 Feedback Pattern으로 제공한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-38. AI 관리자 설정 화면 재설계

- **Wave**: W12
- **Requirement**: 현재 AI 설정 화면은 Backend 방식, 실행 파일, Timeout, 동시 실행 수 등 내부 실행 구조가 평면적으로 나열되어 있어 관리자가 무엇을 확인하고 설정해야 하는지 이해하기 어렵다. AI 기능 사용 여부, Provider 또는 Backend 상태, Model, 사용 제한, 동시 처리 정책 등 실제 운영자가 관리해야 하는 정보를 중심으로 재구성한다. 서버 실행 파일 Path나 내부 CLI 실행 방식 등 불필요한 기술 정보는 기본 화면에서 제거한다. 서버 환경에서 결정되어 사용자가 수정할 수 없는 값은 설정 Form처럼 표시하지 않는다. 연결 테스트는 별도 큰 Card를 하나 더 만드는 방식보다 설정 Flow 안에서 자연스럽게 제공한다. 현재 상태, 정상 여부, 마지막 확인 결과를 쉽게 알 수 있어야 한다. 내부 운영 Runbook이나 서비스 계정 로그인 절차가 필요한 경우 일반 설정 화면의 주요 콘텐츠로 길게 표시하지 않는다. 별도의 도움말 또는 진단 정보로 분리한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-39. 기능 플래그 관리 구조 재검토

- **Wave**: W12
- **Requirement**: 현재 기능 플래그 화면에 내부 Key가 그대로 노출되어 있다. 기능 플래그가 일반 관리자 기능인지 개발 및 운영 전용 기능인지 먼저 판단한다. 일반 관리자가 직접 사용할 필요가 없다면 일반 관리자 Navigation에서 분리하거나 고급 시스템 설정 영역으로 이동한다. 관리자가 확인해야 하는 기능 플래그는 사람이 이해할 수 있는 기능 이름과 설명을 기본으로 표시한다. 내부 Key가 필요한 경우 보조 기술 정보로만 제공한다. 현재 값, 기본값, 실제 적용 값, 값의 출처가 서로 다르다면 그 관계를 이해할 수 있도록 한다. 변경할 수 없는 Flag는 편집 가능한 설정처럼 보이지 않도록 한다. Feature Flag 변경 기능이 실제 존재한다면 변경 영향과 실제 반영 여부를 확인할 수 있어야 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-40. 메일 발송 관리 화면 재설계

- **Wave**: W12
- **Requirement**: 현재 메일 발송 페이지는 메일이 나가지 않는 이유, 서버 설정, 발송 현황, 최근 실패가 여러 큰 Box에 나뉘어 있고 동일한 문제를 반복해서 보여준다. 메일 서비스 상태 중심으로 화면을 다시 설계한다. 현재 메일 발송 가능 여부 설정 상태 최근 성공 또는 실패 상태 필요한 Action 최근 발송 이력 이 흐름으로 사용자가 한눈에 상황을 이해할 수 있어야 한다. 메일 서버가 설정되지 않은 경우 동일한 원인을 여러 Alert와 Table Row에서 반복하지 않는다. `backend_failed` 같은 내부 상태값은 사용자에게 이해 가능한 상태명으로 표시한다. Backend Raw Error를 Table에 그대로 노출하지 않는다. 사용자가 이해할 수 있는 요약 오류를 제공하고 필요한 경우에만 기술 상세 정보를 확인하도록 한다. Raw ISO Timestamp도 Portal 공통 Date/Time Formatter를 사용한다. 시험 메일 기능은 현재 설정 상태와 연결되어 자연스럽게 제공하며 실행 결과를 명확하게 알려준다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-41. 관리자 통계 및 관리 기능 페이지 통합 검토

- **Wave**: W11
- **Requirement**: 현재 단순 Table 하나만 존재하거나 사용 빈도가 낮은 관리자 페이지가 독립 Sidebar 메뉴로 다수 존재한다. `프롬프트 사용 통계`, `정책 사용 통계`, `AI 사용 상한`, 각종 리포트 등의 기능이 독립 페이지를 유지해야 하는지 검토한다. AI 관리, 감사 및 통계, 시스템 운영처럼 더 큰 Context 안에서 Tab 또는 Section으로 제공하는 것이 더 자연스러운 경우 통합한다. 단순히 화면 수를 줄이는 것이 목표가 아니다. 특정 업무를 하려는 사용자가 어느 관리 영역으로 이동해야 하는지 쉽게 예상할 수 있도록 하는 것이 목표다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/navConfig.js`, `frontend/src/app/AdminRoutes.jsx`, `frontend/src/screens/settings/SettingsShell.jsx`, `frontend/src/ui/TabShell.jsx`
- **Verification**: `frontend/src/app/nav-features.test.js`, 옛 주소 제자리 렌더 회귀 테스트, Gate 조건 C1b
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-42. 관리자 페이지 기능 동작 전수검증

- **Wave**: W12
- **Requirement**: 관리자 페이지는 디자인만 개선하지 않는다. 현재 Sidebar와 관리자 페이지에 존재하는 모든 주요 Action과 설정이 실제로 동작하는지 전수검증한다. 다음을 포함한다. 표시되어 있지만 동작하지 않는 Button 저장 후 실제 값이 반영되지 않는 기능 Frontend 상태만 변경되고 Backend에는 반영되지 않는 기능 현재 시스템 설정상 사용할 수 없는데 정상 기능처럼 표시되는 항목 사용되지 않는 Legacy 관리 기능 중복된 관리 기능 죽은 Route 실제 Consumer가 없는 Feature Flag UI만 존재하고 Backend 구현이 없는 기능 Backend 기능은 존재하지만 UI가 연결되지 않은 기능 사용되지 않는 기능을 디자인만 새로 만들어 계속 유지하지 않는다. 실제로 필요 없는 Legacy 기능은 의존성과 영향 범위를 확인한 뒤 제거한다. 필요한 기능은 End-to-End로 정상 동작하도록 수정한다. 기능 동작 여부를 사용자가 직접 하나씩 발견하고 문제를 제보해야 하는 상태로 남겨두지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-43. 관리자 Action의 위험도와 실행 패턴 공통화

- **Wave**: W12
- **Requirement**: 서비스 재시작, 인증서 변경, 계정 정책 변경, 유지보수 모드, 외부 연동 변경 등 시스템 영향이 큰 Action을 일반 Button과 같은 수준으로 취급하지 않는다. Action을 영향도에 따라 구분한다. 단순 조회 일반 설정 변경 서비스 영향 가능 변경 Destructive Action 실행 전 확인이 필요한 작업은 무엇이 변경되고 어떤 영향이 발생할 수 있는지 이해할 수 있어야 한다. Confirm Dialog를 모든 Action에 남발하지 않는다. 실제 위험이 있거나 복구가 어려운 작업에 사용한다. 실행 중에는 중복 클릭을 방지하고 진행 상태를 표시한다. 성공 또는 실패 이후 Backend의 실제 현재 상태를 다시 확인하여 UI 상태와 실제 상태가 불일치하지 않도록 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-44. 관리자 페이지의 설명 구조 단순화

- **Wave**: W12
- **Requirement**: 현재 설정과 관리자 화면에는 Page Description, Alert, Helper Text 등이 반복되면서 설명이 과도하게 분산되어 있다. 설명은 필요한 위치에 필요한 만큼만 제공한다. 페이지 상단에서는 해당 관리 영역의 목적을 짧게 설명한다. 설정 항목에서는 사용자가 선택 또는 변경을 위해 알아야 하는 내용만 제공한다. Backend 구현 세부사항이나 운영 Runbook 수준의 내용을 일반 설정 화면에 길게 배치하지 않는다. 동일한 내용을 Page Description, Alert, Helper Text에서 반복하지 않는다. 사용자가 긴 설명을 모두 읽지 않아도 기능을 사용할 수 있고 필요한 순간에는 설명을 찾을 수 있는 구조를 목표로 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-45. 저장, 수정, 적용 상태의 일관성 확보

- **Wave**: W12
- **Requirement**: 관리자 설정에서 `저장`, `수정`, `적용`, `변경`, `재시작` 등의 Action 의미가 페이지마다 다르게 사용되지 않도록 한다. 필요한 경우 다음 상태를 공통 모델로 정의한다. 수정했지만 아직 저장되지 않은 상태 저장되었지만 아직 실제 서비스에 적용되지 않은 상태 즉시 적용된 상태 재시작이 필요한 상태 적용에 실패한 상태 사용자가 저장 버튼을 눌렀는데 언제 실제 시스템에 반영되는지 알 수 없는 상태를 만들지 않는다. 변경사항이 없는 경우 저장 Button의 상태와 동작도 공통 기준을 따른다. 서버 재시작이나 별도 적용 과정이 필요한 경우 이를 저장 이후에 갑자기 알리는 것이 아니라 변경 과정에서 미리 안내한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-46. 관리자 Navigation 및 현재 위치 인지 개선

- **Wave**: W11
- **Requirement**: 관리자 메뉴를 통합한 이후에도 사용자가 현재 어느 관리 영역에 있는지 쉽게 알 수 있어야 한다. 상위 관리 영역, 현재 Page 또는 Tab, 현재 Section의 관계가 명확해야 한다. Sidebar Active State, Page Header, Tab State가 서로 모순되지 않도록 한다. Tab을 이동할 때 Layout 구조가 크게 달라져 서로 다른 제품이나 페이지처럼 튀어 보이지 않도록 한다. 상위 Context를 유지하는 것이 더 이해하기 쉬운 경우 Page Title을 Tab 이름으로 계속 교체하지 않는다. 예를 들어 `시스템 설정`이라는 상위 Context를 유지하고 내부 Heading 또는 Tab으로 `OS와 서비스`, `연동` 등을 구분하는 방식도 검토한다. 직접 URL 접근, Refresh, Browser Back, Forward에서도 현재 위치가 정상적으로 복원되어야 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/navConfig.js`, `frontend/src/app/AdminRoutes.jsx`, `frontend/src/screens/settings/SettingsShell.jsx`, `frontend/src/ui/TabShell.jsx`
- **Verification**: `frontend/src/app/nav-features.test.js`, 옛 주소 제자리 렌더 회귀 테스트, Gate 조건 C1b
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-47. 관리자 UI 최종 Audit 추가 기준

- **Wave**: W12
- **Requirement**: 기존 전체 Visual Audit에 관리자 영역 전용 검수를 추가한다. 관리자 Sidebar가 실제 업무 기준으로 이해하기 쉽게 정리되었는지 확인한다. 비슷한 관리 기능이 여러 메뉴에 불필요하게 흩어져 있지 않은지 확인한다. 일반 사용자가 이해하기 어려운 Raw Key, 환경변수, File Path, Backend Error 등이 기본 UI에 남아 있지 않은지 확인한다. 설정 가능 값과 읽기 전용 값이 시각적으로 명확하게 구분되는지 확인한다. System Action의 위험도가 적절하게 표현되는지 확인한다. 설정 저장과 실제 적용 상태가 일치하는지 확인한다. 페이지마다 Alert, Button, Form, Table, Card가 다시 제각각 구현되지 않았는지 확인한다. 이모지, 장식 문자, 불필요한 특수기호가 남아 있지 않은지 다시 전수검사한다. 관리자 페이지의 모든 주요 Action을 실제 Browser에서 실행하여 End-to-End 동작 여부까지 확인한다. 디자인이 개선되었더라도 관리자 기능 중 동작하지 않거나 사용 목적이 불명확한 기능이 남아 있다면 완료로 판단하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/DataScreen.jsx`, `frontend/src/screens/registry/shared.js`, `frontend/src/screens/SystemOps.jsx`, `frontend/src/screens/MailStatus.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes admin`, `frontend/src/screens/datascreen.test.jsx`, Gate 조건 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-48. Sidebar 및 Navigation UI 자체 전면 재설계

- **Wave**: W3
- **Requirement**: 관리자 Information Architecture 개선은 메뉴를 재배치하는 것에서 끝내지 않는다. 현재 Sidebar 자체의 Visual Design과 Interaction도 다시 설계한다. 현재 선택 메뉴가 지나치게 큰 알약 형태의 배경으로 강조되는 방식이 적절한지 재검토한다. Group Title, Parent Navigation, Child Navigation, 현재 선택 상태의 시각적 위계를 명확하게 구분한다. 펼쳐진 Group 상태와 실제 선택된 Page 상태가 혼동되지 않아야 한다. 모든 메뉴에 아이콘을 기계적으로 붙이지 않는다. 아이콘이 탐색에 실제 도움을 주는 경우에만 사용한다. 같은 의미의 아이콘을 여러 메뉴에서 반복하거나 장식 목적으로 아이콘을 사용하지 않는다. Sidebar의 Menu Spacing, Font Weight, Indentation, Active State, Hover, Focus 상태를 Tech & SaaS Design System 기준으로 재설계한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/navConfig.js`, `frontend/src/app/navIcons.js`, `frontend/src/app/CommandPalette.jsx`
- **Verification**: `frontend/src/app/nav-active.test.js`, `frontend/src/app/nav-features.test.js`, assertion `brand_presence`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-49. 지시사항 우선순위 및 Skill 적용 원칙 보강

- **Wave**: W0
- **Requirement**: 본 지시사항은 이번 ClovirAssist 전면 리뉴얼의 프로젝트별 최상위 기준이다. UI/UX Pro Max, Impeccable, Taste Skill의 기본 지침과 본 지시사항이 충돌하는 경우 본 지시사항의 목적과 요구사항을 우선한다. 특히 기존 제품의 Visual System을 존중하거나 익숙한 형태를 유지하라는 Skill 내부 일반 원칙이 이번 작업의 `기존 시각 디자인 자체는 보존 대상이 아니다`라는 요구와 충돌하면 기존 디자인을 유지하는 근거로 사용하지 않는다. 표준적인 사용 방법, 사용자가 이미 알고 있는 일반적인 UI Affordance, 접근성 원칙을 유지하는 것과 현재 Portal의 Card, Surface, Sidebar, Color, Layout, Component Styling을 유지하는 것은 서로 다른 문제로 판단한다. 기존 업무 흐름과 사용자 Mental Model을 불필요하게 낯설게 만들 필요는 없지만 현재의 시각 디자인을 익숙하다는 이유만으로 보존하지 않는다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-50. 기능 보존과 기존 UI 및 구현 보존을 명확하게 분리

- **Wave**: W0
- **Requirement**: 이번 작업에서 보존해야 하는 것은 필요한 기능, 데이터, 권한, 보안 통제, 업무 흐름과 사용자에게 제공해야 하는 결과다. 현재의 UI Component, DOM 구조, CSS Selector, Layout 구조, Card 형태, Sidebar 형태, Chart 구현 방식, 특정 Library, 내부 Component 이름, 현재 Visual Pattern 자체는 보존 대상이 아니다. `기능을 유지한다`는 이유로 현재 Component나 현재 화면 구조를 그대로 유지하고 Styling만 변경하지 않는다. 예를 들어 권한 범위를 사용자에게 알려야 하는 기능이 필요하더라도 현재의 `ScopeBar` Component 자체를 유지해야 한다는 의미는 아니다. 사용자 Navigation 기능을 유지해야 하더라도 현재 USER_NAV의 Group 수와 메뉴 구조를 그대로 유지해야 한다는 의미는 아니다. 차트 기능을 유지해야 하더라도 현재 자체 SVG 구현을 무조건 유지해야 한다는 의미는 아니다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-51. 관리자 Information Architecture 재설계 판단 기준 보강

- **Wave**: W11
- **Requirement**: 관리자 Information Architecture 개선은 `8개 영역을 만들고 기존 페이지를 모두 내부 Tab으로 변환하는 작업`이 아니다. 기존 지시사항에서 제시한 상위 관리 영역은 조사와 설계를 위한 초기 분류 기준이며 최종 Sidebar 개수나 최종 페이지 개수를 고정하는 하드코딩된 정답이 아니다. 최종 구조는 실제 관리자 기능, Resource 관계, 사용 목적, 사용 빈도, 업무 흐름, 권한, 화면 복잡도를 조사한 뒤 결정한다. 기본 구조는 다음 순서로 판단한다. Domain Page 필요한 경우에만 Tab, View, Section 또는 Local Navigation 모든 하위 기능을 Tab으로 만드는 구조를 사용하지 않는다. Tab은 동일한 Context에서 같은 Resource 또는 강하게 연관된 업무를 서로 다른 View나 동급 하위 기능으로 전환할 때 자연스러운 경우에만 사용한다. 예를 들어 동일한 실행 데이터를 `일정`과 `달력`으로 보는 기능은 실제 구현과 사용 흐름을 조사한 결과에 따라 Tab 또는 View Toggle이 적합할 수 있다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/navConfig.js`, `frontend/src/app/AdminRoutes.jsx`, `frontend/src/screens/settings/SettingsShell.jsx`, `frontend/src/ui/TabShell.jsx`
- **Verification**: `frontend/src/app/nav-features.test.js`, 옛 주소 제자리 렌더 회귀 테스트, Gate 조건 C1b
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-52. 전체 Route, Page Archetype, 공통 Component Inventory를 구현 전에 다시 수행

- **Wave**: W0
- **Requirement**: 기존 Audit 문서, Backlog, 과거 PASS 결과만을 근거로 이미 개선이 끝난 영역이라고 판단하지 않는다. 이번 지시사항을 기준으로 현재 실제 배포 화면과 현재 Source Code를 다시 조사한다. 기존 문서에서 완료 또는 PASS로 기록된 영역도 이번 전수조사 대상에서 제외하지 않는다. 작업 구현 전에 사용자 영역과 관리자 영역의 전체 Route를 Inventory화한다. 각 Route에 대해 Page 목적, 주요 Workflow, 권한, Page Archetype, 사용 중인 공통 Component, 지역 구현 Component, Search와 Filter, Grid, Form, Modal, Empty State, Loading, Error, Help, Navigation 사용 여부를 확인한다. Page Archetype은 Dashboard, List, Detail, Form, Settings, Workflow, Console, Report 등 실제 구조를 기준으로 분류하되 필요하면 프로젝트에 더 적합한 유형을 정의한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-53. Design Direction을 구현 전에 성급하게 고정하지 않는다

- **Wave**: W1
- **Requirement**: 현재 계획에서 임의로 선택한 특정 Color, 밝은 Chrome, 2px Active Rail, Surface 개수, MetricStrip, 특정 Dashboard 배치, 특정 Chart 형태 등을 사용자 확정사항으로 간주하지 않는다. 사용자가 실제로 명시적으로 확정한 내용만 사용자 결정사항으로 기록한다. AI가 스스로 선택한 디자인 방향을 `사용자 확인 완료` 또는 이에 준하는 표현으로 기록하지 않는다. UI/UX Pro Max와 관련 Skill을 실제로 사용하여 현재 제품, 정보 밀도, 업무 특성, Tech & SaaS 방향에 적합한 Design Direction을 검토한다. 하나의 첫 아이디어를 바로 구현안으로 확정하지 않는다. 필요한 경우 서로 다른 방향을 비교하고 정보 위계, 사용성, Visual Quality, 제품 일관성, 운영 효율성, Responsive, 접근성 기준으로 가장 적합한 방향을 선택한다. 사용자의 별도 승인 절차를 만들기 위해 작업을 중단하지 말고 지시사항과 실제 제품 구조를 근거로 가장 적합한 방향을 스스로 결정하여 진행한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `frontend/src/ui/theme.js`, `scripts/generate_design_tokens.mjs`, `frontend/src/styles/tokens.css`, `app/static/css/tokens.css`
- **Verification**: `frontend/src/ui/theme-contract.test.js`, `frontend/src/styles/tokens-generated.test.js`, `node scripts/generate_design_tokens.mjs --check`, assertion `brand_presence`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-54. 기존 Baseline, Test, Selector, Library를 새 디자인의 제약으로 사용하지 않는다

- **Wave**: W0
- **Requirement**: 기존 Baseline, Screenshot, Snapshot, Test, CSS Selector, Component Contract는 현재 상태와 회귀를 확인하기 위한 자료이지 새 Visual Design을 보존하기 위한 정본이 아니다. 기존 `preview-standalone.html` 또는 이에 준하는 Baseline 파일을 새 디자인의 시각적 정본으로 간주하지 않는다. 새 Design System 구현으로 의도적으로 Palette, IA, Layout, DOM Structure, Component Structure가 변경되는 경우 기존 Test를 억지로 그대로 통과시키기 위해 새 디자인을 기존 구조에 맞추지 않는다. 기존 Test가 과거 UI 구조를 고정하고 있다면 새로 정의한 Design System과 UX Contract를 검증하도록 적절하게 갱신한다. 단, Test를 단순 삭제하거나 Assertion을 약화하여 통과시키지 않는다. 변경된 요구사항과 새 UX Contract를 실제로 검증하는 Test로 다시 작성한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-55. 보안과 권한 기능의 범위를 UI 기능 제거와 혼동하지 않는다

- **Wave**: W0
- **Requirement**: `문서 잠금 기능 제거`는 문서 잠금 상태와 잠금 Workflow를 제거하라는 요구사항이다. 이를 문서 열람 권한, 접근 제한, restricted 정책 또는 다른 보안 통제를 제거하라는 의미로 확대 해석하지 않는다. 문서 잠금 기능과 문서 열람 권한은 별개의 기능으로 조사한다. 별도의 명시적인 요구가 없는 한 기존 문서 접근 제어와 보안 권한을 약화하거나 제거하지 않는다. UI/UX 개선을 이유로 RBAC, Authorization, 접근 정책, Secret 보호, 인증 정책 등 보안 통제를 축소하지 않는다. `사용되지 않는 Legacy 기능 제거` 역시 실제 Consumer, API 사용, 데이터, 운영 의존성, 권한, 외부 연동을 확인한 뒤 수행한다. 디자인상 불필요해 보인다는 이유만으로 실제 기능을 제거하지 않는다. 보안과 권한에 영향을 주는 요구사항이 불명확한 경우에는 권한을 줄이는 방향이 아니라 기존 보안 통제를 유지하는 안전한 방향으로 해석한다. 401 인증 만료와 403 권한 없음 등 서로 다른 인증 및 권한 상태를 구분한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-56. 계획 완전성 및 Requirement Traceability를 구현 전 Gate로 사용

- **Wave**: W0
- **Requirement**: 구현 계획을 작성할 때 본 지시사항의 모든 번호를 실제 구현 계획과 검증 계획에 연결한다. 단순히 마지막 표에 요구사항 번호와 Phase 번호를 연결하는 것만으로 충족된 것으로 보지 않는다. 각 요구사항에는 실제 계획 본문에 다음 내용이 있어야 한다. 현재 확인된 문제 또는 조사 대상 변경할 기능 또는 UX 영향을 받는 Route, Page, Component, API 또는 Backend 영역 필요한 공통 Component 또는 정책 변경 검증 방법 완료 판단 기준 공통 Component 변경으로 여러 요구사항을 처리하는 경우에도 영향을 받는 주요 Consumer와 화면을 확인한다. `공통 Component에서 해결`이라는 문장만으로 관련 화면 전수 적용 계획을 생략하지 않는다. 계획에서 참조하는 모든 Phase, Sub Phase, Section 번호는 실제 계획 본문에 존재해야 한다. 존재하지 않는 `3-3`, `4-4`, `Phase 6` 등의 번호를 Mapping Table에서만 참조하는 형태를 허용하지 않는다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-57. 공통 Component 통합이 과도한 추상화로 변질되지 않도록 한다

- **Wave**: W0
- **Requirement**: 공통 Design System을 만드는 것은 모든 화면을 하나의 거대한 Component에 맞추는 작업이 아니다. 실제로 반복되는 Visual Rule, Interaction, Behavior가 확인된 경우 공통화한다. 동작과 목적이 다른 Component를 단지 모양이 비슷하다는 이유로 하나의 Component로 억지 통합하지 않는다. 하나의 공통 Component에 수많은 Boolean Prop, 예외 분기, Page별 조건이 누적되어 사실상 여러 Component 역할을 동시에 수행하게 만들지 않는다. 공통 Primitive와 목적별 Component를 적절하게 분리한다. 같은 Design Language를 사용하면서도 Dashboard, Settings, Data Grid, Detail, Workflow 등 Page Archetype에 필요한 Variant를 가질 수 있다. 반대로 동일한 역할의 Search, Filter, Modal, Empty State, Pagination 등이 Page마다 별도로 복제되어 있는 상태도 남기지 않는다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-58. 사용자 Navigation도 사전 유지 대상으로 고정하지 않는다

- **Wave**: W11
- **Requirement**: 사용자 영역 Navigation 역시 이번 전수 Audit 대상이다. 현재 사용자 Navigation의 Group 수, 메뉴 수, 메뉴 위치가 기존에 존재한다는 이유만으로 구조 유지로 미리 확정하지 않는다. 실제 사용자 업무 흐름, 메뉴 이름, 기능 관계, 사용 빈도, 현재 위치 인지, 탐색 비용을 조사한다. 현재 구조가 적절하다고 확인되면 유지할 수 있다. 개선이 필요한 경우 기능과 권한을 보존하면서 Group, 순서, Label, Navigation Hierarchy를 조정한다. 관리자 Navigation과 사용자 Navigation은 같은 Design Language를 사용하되 서로 다른 업무 구조를 억지로 동일한 IA로 만들지 않는다. Navigation에 존재하는 현재 Component 또는 Pattern을 유지할지 여부도 기능 필요성과 UX를 기준으로 판단한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/navConfig.js`, `frontend/src/app/AdminRoutes.jsx`, `frontend/src/screens/settings/SettingsShell.jsx`, `frontend/src/ui/TabShell.jsx`
- **Verification**: `frontend/src/app/nav-features.test.js`, 옛 주소 제자리 렌더 회귀 테스트, Gate 조건 C1b
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-59. 구현 방식과 기술 선택을 사전에 `유지`로 고정하지 않는다

- **Wave**: W0
- **Requirement**: 기존 구현이 있다는 이유만으로 계획 단계에서 `유지한다`고 먼저 결정하지 않는다. 현재 구현을 유지하려면 이번 요구사항을 충분히 만족할 수 있다는 근거가 있어야 한다. 현재 Chart, Grid, Search, Modal, Form, Navigation, CSS Architecture, Theme 구조, Component API 등을 각각 조사한다. 현재 구현으로 Visual Quality, 접근성, Responsive, Interaction, 유지보수성, 성능, 일관성을 충분히 달성할 수 있다면 재사용 또는 Refactor할 수 있다. 그렇지 않다면 교체 또는 재설계한다. `현재 Test가 있어서`, `이미 Component가 있어서`, `기존 코드가 많아서`, `익숙해서`는 기존 UX나 시각 구조를 유지하는 단독 근거가 될 수 없다. 반대로 새 기술이나 새 Library를 도입하는 것 자체도 개선으로 간주하지 않는다. 사용자 경험과 제품 품질을 가장 잘 만족하는 방식을 선택한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-60. 최종 Visual QA와 IA QA를 강화

- **Wave**: W15
- **Requirement**: 최종 검수에서는 단순히 각 Route가 Rendering되고 Test가 PASS하는지만 확인하지 않는다. 작업 전과 작업 후 주요 화면을 비교하여 실제 Visual System이 충분히 변경되었는지 확인한다. 현재 화면의 Card, Surface, Button, Grid, Search, Filter, Modal, Navigation, Badge, Form, Chart 패턴이 새 Design System으로 실질적으로 교체되었는지 확인한다. 기존 화면과 거의 같은 Layout과 Component 형태에 Color, Border, Radius만 바뀐 결과라면 완료로 처리하지 않는다. Dashboard는 모든 정보를 Card에서 List나 Table로 바꾸는 방식도 사용하지 않는다. 각 정보의 목적과 중요도에 따라 가장 적합한 표현을 선택하고 전체 화면이 단조로운 한 가지 Pattern으로 다시 획일화되지 않도록 한다. 관리자 IA는 Sidebar 항목 수만 줄었는지 확인하는 것이 아니라 실제로 기능 찾기가 쉬워졌는지 확인한다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage complete`, `bash scripts/run_full_regression.sh`, `bash scripts/static_checks.sh`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-61. 명명된 화면과 예시를 작업 범위로 한정하지 않는다

- **Wave**: W0
- **Requirement**: 본 지시사항에서 Dashboard, Sprint 회의, 내 업무, 문서, 티켓, 관리자 설정 등 특정 화면을 언급한 것은 현재 확인된 문제와 개선 방향을 설명하기 위한 대표 사례다. 명시적으로 이름이 적힌 화면만 수정하고 나머지 화면은 기존 상태로 유지하지 않는다. 이번 작업의 대상은 ClovirAssist의 사용자 영역과 관리자 영역 전체다. 전체 Route, Page Archetype, 공통 Component, 주요 Workflow를 조사하여 동일하거나 유사한 문제가 있는 모든 화면을 개선한다. 특정 요구사항에 화면 이름이 명시되어 있더라도 동일한 목적, 구조, Component 또는 UX Pattern을 사용하는 다른 화면이 존재한다면 함께 조사한다. 반대로 특정 화면이 지시사항에 이름으로 언급되지 않았다는 이유로 Audit 대상에서 제외하지 않는다. 지시사항에 제시된 화면, 정보, Metric, Component, Layout 예시는 최소 요구사항 또는 문제를 설명하기 위한 예시이며 전체 개선 범위의 상한선이 아니다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-62. Page 목적과 정보 완전성을 기준으로 필요한 정보 및 기능을 능동적으로 개선

- **Wave**: W10
- **Requirement**: 이번 작업은 현재 화면에 존재하는 정보를 그대로 유지한 채 위치와 디자인만 바꾸는 작업이 아니다. 각 Page가 실제 사용자에게 어떤 판단과 행동을 지원해야 하는지 먼저 정의하고 현재 제공되는 정보와 기능이 그 목적을 충분히 만족하는지 검토한다. Dashboard, 내 업무 Home, Sprint 회의, Overview, Status, Detail, 관리 Console 등 정보 중심 화면에서는 현재 표시되는 항목만 재배치하지 않는다. 실제 업무 수행에 필요한데 현재 화면에서 빠져 있는 정보, 상태, 비교, Trend, Context, Action이 있는지 조사한다. 현재 Backend, API, Database 또는 이미 수집 중인 데이터로 제공할 수 있는 정보라면 사용자 가치와 화면 복잡도를 판단하여 필요한 정보를 추가할 수 있다. 기존 데이터에서 안전하게 계산하거나 집계할 수 있는 Derived Information도 실제 의사결정에 도움이 된다면 사용할 수 있다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-63. Layout뿐만 아니라 Information Architecture와 Content Architecture까지 Page 단위로 재검수

- **Wave**: W10
- **Requirement**: 각 화면의 Layout 검수는 Width, Height, Grid, Spacing, Responsive 문제를 찾는 것에 한정하지 않는다. 사용자가 화면을 위에서 아래로 어떤 순서로 읽고 어떤 정보를 먼저 판단하며 어떤 Action으로 이어지는지까지 검토한다. 각 Page에서 다음 내용을 함께 판단한다. 가장 중요한 정보가 실제로 가장 먼저 보이는가 관련된 정보가 서로 가까이 배치되어 있는가 서로 관계없는 정보가 같은 Card 또는 Section에 섞여 있지 않은가 중요하지 않은 정보가 화면 상단의 공간을 과도하게 차지하지 않는가 사용 빈도가 높은 Action이 불필요하게 멀리 떨어져 있지 않은가 화면 목적에 비해 정보가 부족하거나 반대로 지나치게 많은가 정보가 반복되거나 동일한 상태를 여러 Component에서 중복 표시하고 있지 않은가 빈 공간이 단순 Layout 문제인지 실제로 필요한 정보가 빠져 있기 때문인지 구분한다. 화면의 세로 흐름과 가로 영역 분배가 실제 사용 순서와 맞는지 확인한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/screens/Home.jsx`, `frontend/src/screens/Sprint.jsx`, `frontend/src/screens/Board.jsx`, `frontend/src/screens/MyStats.jsx`
- **Verification**: `python -m scripts.ui_qa.run --routes user`, 화면별 vitest, assertion `dead_blank_region`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-64. design/baseline/preview-standalone.html은 폐기 대상으로 취급

- **Wave**: W0
- **Requirement**: `design/baseline/preview-standalone.html`은 이번 리뉴얼의 디자인 참고 자료, Baseline, Visual Contract, Design Source of Truth로 사용하지 않는다. 해당 파일의 디자인, Layout, Token, Component 형태, Color, Typography, Spacing 등 어떠한 내용도 새 Design Direction을 결정하는 근거로 사용하지 않는다. 해당 파일을 열어서 현재 디자인을 분석하거나 새 디자인과 비교할 필요도 없다. 해당 파일을 새 Design System의 Preview 또는 Baseline으로 다시 작성하지 않는다. 현재 Test가 해당 HTML을 파싱하고 있다는 이유로 파일을 유지하거나 새 디자인을 해당 파일 구조에 맞추지 않는다. 해당 파일을 참조하는 Test, Parser, Script가 있다면 실제 Runtime에서 사용하는 Theme, Token, Component Contract 또는 Browser Rendering 결과를 검증하도록 구조를 변경한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-65. Design Direction 확정 전에 세부 Visual Token을 고정하지 않는다

- **Wave**: W1
- **Requirement**: P0의 Design Direction 결정이 완료되기 전에 Surface 단계 수, Color 구조, Radius 값, Typography Scale, Motion Duration, Shadow 단계, Navigation Active 표현 등을 확정된 값으로 고정하지 않는다. 현재 계획에 적힌 Surface 4단, 중립색 1벌과 강조색 1개, 특정 Typography Ratio, Motion 150~250ms 등의 값은 필요한 경우 후보 또는 초기 가설로만 사용한다. UI/UX Pro Max, Impeccable 및 실제 제품 Audit 결과를 바탕으로 P0에서 전체 Design Direction을 결정한 뒤 그 결과에 맞춰 Token System을 설계한다. ClovirAssist의 기존 Purple/Indigo Brand Identity는 사용자 확정사항이며 선택 가능한 후보가 아니다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `frontend/src/ui/theme.js`, `scripts/generate_design_tokens.mjs`, `frontend/src/styles/tokens.css`, `app/static/css/tokens.css`
- **Verification**: `frontend/src/ui/theme-contract.test.js`, `frontend/src/styles/tokens-generated.test.js`, `node scripts/generate_design_tokens.mjs --check`, assertion `brand_presence`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-66. 공통 Component를 모든 Route와 Page Archetype에 기계적으로 강제하지 않는다

- **Wave**: W0
- **Requirement**: 공통 Design System을 Portal 전체에 적용하되 동일한 Component 형태를 모든 Route에 강제로 삽입하는 것으로 해석하지 않는다. PageHeader, DetailLayout, SearchFilterBar, DataTable, Settings Pattern 등의 공통 Component는 해당 Page의 목적과 Page Archetype에 적합한 경우 사용한다. `전 Route 필수`라는 이유만으로 로그인, Full-screen Workflow, Chat, Game 또는 별도의 집중형 화면에 불필요한 Page Header, Breadcrumb, 도움말, Section 구조를 강제로 추가하지 않는다. PageHeader가 필요한 일반 Page에서는 일관되게 사용하지만 해당 Component가 실제 UX를 해치는 Page Archetype에는 더 적합한 표현을 사용한다. Detail Layout의 약 2:1 구조 역시 Ticket, Document 등 적합한 상세 화면의 기본 Pattern이지 모든 Detail Page의 강제 Layout이 아니다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-67. Global Notification과 Operational Status를 구분

- **Wave**: W0
- **Requirement**: 사용자 Global Header에서 `안내`, `장애` 등의 별도 전폭 알림 영역을 제거하고 종 모양 알림을 사용자 Notification의 단일 진입점으로 사용하는 원칙은 유지한다. 하지만 이를 Portal 전체의 상태 표시, 관리자 Operational Status, 서비스 Health, 장애 상태, 조치 필요 정보까지 제거하라는 의미로 확대하지 않는다. Header에 존재하는 Legacy Component를 제거할 수는 있으나 해당 Component가 제공하던 정보 중 관리자 또는 운영자에게 실제로 필요한 상태 정보가 있다면 적절한 관리 화면과 새로운 Design System 안에서 다시 제공한다. 사용자 Notification, 시스템 Health, 관리자 운영 상태, Page 내부 Warning은 서로 목적이 다르므로 동일한 표현이나 동일한 노출 정책을 강제하지 않는다. Component 이름을 삭제하는 것이 목표가 아니라 올바른 정보가 올바른 Context에서 제공되는 것이 목표다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-68. 위험 Action의 End-to-End 검증은 상태 복구까지 포함

- **Wave**: W14
- **Requirement**: TEST SERVER에서 관리자 주요 Action을 실제 Browser로 End-to-End 검증하되 단순히 Action을 실행하고 성공 응답을 확인하는 것으로 끝내지 않는다. 서비스 재시작, 인증서 변경, DNS, Hostname, Proxy, Timezone, 계정 정책, 권한 변경, 외부 연동 변경, 삭제 등 시스템 또는 데이터에 영향을 주는 Action은 실행 전 현재 상태를 확인한다. 실행 후에는 Network, API, Backend, 실제 시스템 상태, UI 표시가 모두 일치하는지 확인한다. 원상복구가 필요한 Action은 검증 이후 기존 상태로 복구하고 복구 결과까지 확인한다. 삭제처럼 불가역성이 있는 Action은 기존 실제 데이터를 임의로 삭제하지 않고 안전하게 생성한 테스트 Fixture 또는 테스트 전용 데이터를 사용한다. 위험 Action의 테스트 때문에 다른 Workflow와 후속 E2E가 깨지는 상태를 만들지 않는다. Test Server라는 이유만으로 데이터와 시스템 상태를 무계획하게 변경하지 않는다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`
- **Verification**: `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth`, Gate 조건 C11 과 C12 와 C13 과 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-69. 계획의 구체적 구현안도 Audit 결과에 따라 수정 가능해야 한다

- **Wave**: W0
- **Requirement**: 현재 실행 계획에 적힌 파일명, Component명, 특정 Library 유지, 특정 Component 제거, 특정 Layout 구조, 특정 Token 구조는 현재 조사 결과를 바탕으로 한 구현 후보로 취급한다. 구현 과정에서 실제 Source, Browser, Consumer, 데이터 구조를 더 깊게 조사한 결과 더 적절한 방법이 확인되면 현재 계획 문장을 그대로 구현하기 위해 잘못된 구조를 유지하지 않는다. 단, 지시사항의 목적과 기능, 데이터, 권한, 보안, 업무 흐름을 임의로 변경하지 않는다. 계획의 수단과 구현 방식은 더 좋은 방법으로 변경할 수 있지만 요구사항과 완료 기준을 축소해서는 안 된다. 변경한 경우 왜 기존 계획보다 새로운 방법이 더 적절한지 근거를 남기고 Requirement Traceability를 함께 갱신한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-70. 기존 기능 재사용과 기존 Visual Design 재사용을 혼동하지 않는다

- **Wave**: W0
- **Requirement**: 현재 구현에서 기능적으로 잘 동작하거나 재사용 가치가 높은 Component, Library, Logic이 존재하더라도 현재의 Visual Design까지 그대로 유지하라는 의미로 해석하지 않는다. `이미 잘 되어 있어 보존`, `재사용`, `확장`, `기존 구현 활용`이라는 판단은 기능, Interaction Logic, 접근성 처리, 데이터 처리, 검증된 기술 구조에 대한 판단이다. 현재 화면의 모양, 배치, 색상, Card 구조, Border, Radius, Surface, Typography Hierarchy, Density, Spacing, Button 표현, Table 표현, Modal 표현, Navigation 표현까지 함께 보존한다는 의미가 아니다. 기능적으로 잘 동작하는 Component라도 이번 Design Direction과 Visual Quality 기준에 맞지 않는다면 내부 Logic은 재사용하면서 Render Structure와 Visual 표현은 적극적으로 재설계한다.
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-71. Clovi 마스코트를 핵심 Brand Asset으로 사용하고 현재처럼 지나치게 작게 축소하지 않는다

- **Wave**: W7
- **Requirement**: 이번 작업에서 Clovi는 단순 장식용 아이콘이 아니라 ClovirAssist의 핵심 Brand Character다. 사용자가 제공한 `신규 클로비 이미지.zip`을 Clovi의 Canonical Asset Package로 취급한다. 해당 ZIP 안에 이미 용도별로 정리된 로그인용 Avatar와 Hero, AI 도우미 상태별 Pose, Empty/Error State, Onboarding Illustration, 원본 Frame과 Layer가 있으므로 임의로 다른 로봇 이미지를 생성하거나 외부 이미지로 교체하지 않는다. 기존 Asset의 비율, 얼굴, 색, 몸체, 표정, Logo Mark를 임의로 다시 그리거나 스타일을 변경하지 않는다. 현재 실제 Browser 화면에서 Clovi가 지나치게 작게 표시되어 얼굴과 표정이 거의 보이지 않고 작은 장식 아이콘처럼 보이는 상태는 실패로 판단한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-72. 제품명과 Brand Naming의 단일 기준을 `ClovirAssist`로 통일하고 Legacy Product Identity를 전면 제거한다

- **Wave**: W13
- **Requirement**: 이번 작업부터 제품의 Canonical Product Name은 `ClovirAssist`다. UI Text, Accessibility Label, Browser Title, Metadata, Configuration Description, 설치 및 배포 정보, Service Description, Email Template, Generated Text 등 프로젝트가 소유하는 모든 제품명 표기는 `ClovirAssist`를 기준으로 통일한다. 공식 Logo Image 자체에 디자인된 Wordmark의 자간 또는 시각적 띄어쓰기가 포함되어 있다면 원본 Logo Asset은 훼손하지 않는다. 다만 Code, alt, aria-label, title, Product Metadata 등 Textual Identity는 `ClovirAssist`를 사용한다. DNS, Hostname, File 또는 Identifier처럼 공백을 사용할 수 없는 기술 영역의 Canonical Slug는 `clovirassist` 소문자를 사용한다.
- **Affected**: ALL
- **Implementation**: `app/core/sessions.py`, `frontend/src/app/theme-store.js`, `deploy/nginx/clovirone-web-assistant.conf`, `scripts/install-clovirone-web-assistant.sh`
- **Verification**: `openssl s_client -connect 10.100.64.71:443 -servername clovirassist.gooddi.lab`, `curl --resolve` 로 ssl_verify_result 0 확인, `pytest tests/unit/test_sysops_tls_paths.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-73. Hostname, URL, TLS Certificate와 배포 Identity를 `ClovirAssist` 기준으로 전면 Migration한다

- **Wave**: W13
- **Requirement**: 사용자가 확정한 Canonical Hostname은 `clovirassist.gooddi.lab`이다. 이 값은 후보가 아니며 `-ai` 등의 임의 접두 또는 접미사를 추가하지 않는다. 현재 Test Server와 배포 환경에서 Hostname, URL, TLS Certificate 또는 관련 설정에 Legacy Product Identity가 사용되고 있는지 전수조사한다. 새 Hostname으로 변경할 때 다음 Consumer를 전체 조사하고 함께 변경한다.
- **Affected**: ALL
- **Implementation**: `app/core/sessions.py`, `frontend/src/app/theme-store.js`, `deploy/nginx/clovirone-web-assistant.conf`, `scripts/install-clovirone-web-assistant.sh`
- **Verification**: `openssl s_client -connect 10.100.64.71:443 -servername clovirassist.gooddi.lab`, `curl --resolve` 로 ssl_verify_result 0 확인, `pytest tests/unit/test_sysops_tls_paths.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-74. Table, Grid, Metadata의 Column Width와 Alignment를 데이터 의미에 따라 전면 재설계

- **Wave**: W6
- **Requirement**: Portal 전체 Table, Data Grid, Metadata Strip, Summary Grid, Property Grid를 전수조사한다. 현재처럼 사용할 수 있는 전체 폭을 Column 개수로 균등 분배하거나 모든 Column을 비슷한 너비로 만드는 방식을 사용하지 않는다. Column Width는 데이터의 의미, 실제 데이터 길이, 중요도, Scan 빈도를 기준으로 결정한다. 제목, 문서명, 티켓명, 프로젝트명, 설명, 오류 요약, 긴 사용자 입력 값처럼 길이가 길어질 수 있고 사용자가 읽어야 하는 값은 상대적으로 넓은 Flexible Column을 우선 검토한다. Checkbox, 상태, 우선순위, 숫자, 난이도, 건수, 짧은 Code, 날짜, 아이콘, Row Action처럼 값의 범위가 작고 반복 비교가 중요한 항목은 필요한 만큼 Compact하게 사용한다. 긴 값이 있는 Column이 좁아서 불필요하게 여러 줄로 깨지는데 짧은 값의 Column이 과도하게 넓게 비어 있는 상태를 허용하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-75. Detail Page Metadata Layout을 균등 Column 방식에서 의미 기반 Layout으로 재설계

- **Wave**: W7
- **Requirement**: 티켓 상세, 문서 상세 및 유사한 Detail Page 상단의 Metadata 영역을 전수조사한다. 현재 티켓 상세처럼 상태, 우선순위, 티켓 번호, 프로젝트, 담당자, 난이도, 마감 등 서로 다른 길이와 중요도를 가진 값을 동일한 Column Width로 배치하지 않는다. Metadata 항목의 Width는 값의 길이, 정보 중요도, 사용 빈도와 비교 목적에 따라 결정한다. 프로젝트명이나 긴 식별 정보처럼 값이 길어질 수 있는 항목은 충분한 공간을 제공한다. 상태, 우선순위, 난이도, 짧은 번호처럼 값이 짧은 항목은 필요 이상의 공간을 차지하지 않는다. 긴 프로젝트명이 좁은 Column 때문에 여러 줄로 깨지는데 옆의 짧은 숫자 Column에는 큰 빈 공간이 남는 Layout은 실패다. Metadata 전체를 하나의 균등 Grid로 강제하지 않는다. 필요한 경우 Flexible Grid, Content-aware Grid, Grouping, Priority-based Layout을 사용한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-76. Search, Filter, Sort, Entity Selector 영역의 내부 Alignment와 Grouping을 다시 설계

- **Wave**: W5
- **Requirement**: Search와 Filter 영역은 Control을 한 Container 안에 넣었다는 이유만으로 완료된 것으로 판단하지 않는다. 검색, Category, Status, Project, Assignee, Sort, View 등 각 Control의 관계와 중요도를 기준으로 Layout을 구성한다. 현재 자유게시판처럼 Search Input과 Category는 위에 있고 Sort Select 하나만 아래 왼쪽에 홀로 떨어져 Container 대부분이 비는 Layout을 허용하지 않는다. 현재 Sprint처럼 여러 Filter는 첫 줄에 배치되고 담당자 하나만 다음 줄 왼쪽에 남아 전체 정렬과 리듬이 깨지는 Layout도 다시 설계한다. 상황에 따라 Primary Search, Primary Filters, Secondary Filters, Sort/View Control, Reset 또는 Saved View를 의미 단위로 Grouping한다. 서로 관련된 Control은 시각적으로 하나의 Group으로 읽혀야 한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/FilterBar.jsx`, `frontend/src/ui/filters.jsx`, `frontend/src/screens/TicketFilterBar.jsx`, `frontend/src/screens/DataScreen.jsx`
- **Verification**: assertion `isolated_control_row`, assertion `control_baseline_mismatch`, assertion `plain_dropdown_for_entity`, `frontend/src/ui/FilterBar.jsx` 소비처 렌더 테스트
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-77. KPI, Summary, 담당자 현황에서 기계적인 균등 분할과 반복 Card를 사용하지 않는다

- **Wave**: W6
- **Requirement**: KPI나 Summary 항목을 단순히 항목 수만큼 전체 폭으로 균등 분할하지 않는다. 현재 Sprint Summary처럼 완료, 진행 중, 완료 업무량, 지연 등 서로 의미와 중요도가 다른 값을 동일한 Width와 동일한 Visual Weight로 표시하는 방식이 최선인지 다시 판단한다. 핵심 Metric과 보조 Metric의 Visual Weight를 구분한다. 관련 Metric은 하나의 Summary Group으로 묶을 수 있다. 값이 0이거나 현재 Context에서 정보 가치가 낮은 Metric이 큰 공간을 계속 차지하지 않도록 한다. 값이 짧다는 이유만으로 화면 폭을 동일하게 나눠 큰 빈 영역을 만들지 않는다. 담당자 현황 역시 사람 수만큼 동일한 대형 Card를 반복하는 방식을 기본값으로 사용하지 않는다. 담당자 수가 늘어날 경우 Card Grid가 화면 대부분을 차지하고 비교가 오히려 어려워지는 구조를 피한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-78. 전체 제품의 Alignment, Width Distribution, Visual Geometry를 별도 최종 Gate로 추가

- **Wave**: W0
- **Requirement**: Portal 전체에서 Alignment와 Width Distribution을 독립적인 Visual QA 항목으로 검수한다. 최종 Reviewer는 실제 Browser Screenshot을 기준으로 다음을 전수조사한다. Page Header의 제목, Breadcrumb, Help, Action의 시작선과 Baseline Section Title과 Content 시작선 Search와 Filter Control의 수직 및 수평 정렬 Form Label, Helper Text, Input의 정렬 Table Header와 Cell 정렬 Table Column의 의미 기반 Width Distribution 숫자, Text, Status, Date, Action의 의미 기반 Alignment Metadata Label과 Value의 정렬과 Width Distribution Card 내부 Title, Metric, Description의 정렬 Button Group과 Inline Action 정렬 Empty State의 Illustration, Text, Action 정렬 Chart Title, Leg
- **Affected**: ALL
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-79. Sidebar 및 Navigation Icon System 전면 재설계

- **Wave**: W3
- **Requirement**: 현재 사용자 Sidebar와 관리자 Sidebar의 아이콘은 전체적으로 Stroke가 두껍고 시각적 무게가 강하여 Navigation Text보다 아이콘이 먼저 보이고 전체 Sidebar가 투박하고 복잡하게 느껴진다. 현재 아이콘을 그대로 유지한 채 색상만 변경하지 않는다. 사용자 영역과 관리자 영역 전체 Navigation Icon을 다시 Audit하여 하나의 일관된 Icon System으로 재설계한다. 먼저 현재 사용 중인 Icon Library, 개별 SVG, MUI Icon, Custom Icon의 사용처를 전수조사한다. 서로 다른 Icon Family와 Stroke Style이 혼용되어 있다면 특별한 이유가 없는 한 하나의 일관된 Icon Language로 통일한다. 아이콘은 Tech & SaaS 제품에 적합한 가볍고 정제된 Outline Style을 우선한다. 현재처럼 작은 크기에서 선이 뭉쳐 보이는 Heavy Stroke, Bold Icon, Filled Icon을 Navigation의 기본 표현으로 사용하지 않는다.
- **Affected**: ALL
- **Implementation**: `frontend/src/app/navConfig.js`, `frontend/src/app/navIcons.js`, `frontend/src/app/CommandPalette.jsx`
- **Verification**: `frontend/src/app/nav-active.test.js`, `frontend/src/app/nav-features.test.js`, assertion `brand_presence`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-80. Search, Filter, Sort를 기계적으로 하나의 큰 Box 안에 넣지 않는다

- **Wave**: W5
- **Requirement**: Search, Filter, Category, Sort, View Control을 하나의 기능 영역이라는 이유만으로 항상 큰 Card, Panel 또는 흰색 Rectangle 안에 감싸지 않는다. 현재 자유게시판처럼 Control은 화면 좌측 일부만 사용하지만 Container는 Page 전체 폭을 차지하여 오른쪽 대부분이 비어 있는 구조를 사용하지 않는다. Filter Surface가 실제로 필요한지 먼저 판단한다. Search, Category, Status, Sort, View Toggle처럼 단순한 탐색 기능만 존재하는 경우에는 Page Toolbar 또는 Inline Control Group 형태를 우선 검토한다. 필터 수가 적다면 Page Content 위에 자연스럽게 배치하고 별도의 Elevated Surface를 만들지 않아도 된다. Search와 주요 Filter는 좌측 또는 Content Flow의 시작점에 배치한다. Sort, View Option처럼 결과 표현을 조정하는 Control은 필요하면 우측에 배치하여 Search/Filter와 역할을 구분한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/FilterBar.jsx`, `frontend/src/ui/filters.jsx`, `frontend/src/screens/TicketFilterBar.jsx`, `frontend/src/screens/DataScreen.jsx`
- **Verification**: assertion `isolated_control_row`, assertion `control_baseline_mismatch`, assertion `plain_dropdown_for_entity`, `frontend/src/ui/FilterBar.jsx` 소비처 렌더 테스트
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-81. Reading Page와 업무 Detail Page를 구분하여 Content Width를 설계

- **Wave**: W7
- **Requirement**: 모든 Detail Page가 동일한 Content Width와 동일한 2 Column Layout을 사용하지 않는다. Ticket, Project, Settings처럼 Metadata와 보조 Context가 중요한 업무 Detail Page와 게시글, 공지, 문서 본문처럼 읽기 경험이 중요한 Reading Page를 구분한다. 자유게시판 게시글, 공지, 긴 문서 본문 등 Reading 중심 Page에서는 본문을 화면 전체 폭까지 무작정 확장하지 않는다. 반대로 현재 게시판 상세처럼 Page 좌측 일부에만 본문을 배치하고 나머지 화면 절반 이상을 의미 없이 비워두지도 않는다. 읽기 좋은 Line Length와 Content Width를 기준으로 Reading Container를 설계한다. 최종 Width 값은 Browser Audit으로 결정하되 Desktop에서 대략 900~1200px 수준의 Reading Width가 적합한지 우선 검토한다. 숫자를 고정값으로 복사하지 말고 Typography, Font Size, 실제 Content 특성에 따라 결정한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-82. Surface와 Container 사용 자체를 전체 Portal에서 다시 Audit

- **Wave**: W4
- **Requirement**: 현재 UI는 정보를 구분하기 위해 Card, Panel, Border Box를 너무 쉽게 사용하는 경향이 있다. 이번 Renewal에서는 `무엇인가를 그룹으로 묶어야 한다 = 흰색 네모 Box를 만든다`라는 규칙을 사용하지 않는다. 각 Card, Panel, Surface에 대해 다음을 확인한다. 이 Container가 실제로 필요한가 Border가 필요한가 Background가 필요한가 Elevation이 필요한가 Section Heading과 Spacing만으로 충분하지 않은가 Divider만으로 충분하지 않은가 같은 Page 안에서 Surface가 지나치게 반복되고 있지 않은가 Container 내부 Content보다 빈 공간이 더 많지 않은가 Card를 제거했을 때 오히려 정보 위계가 더 명확해지지 않는가 특히 Search/Filter, KPI, Metadata, Empty State, Form, Settings, Dashboard, Board, Sprint, Admin Console 영역을 우선 전수조사한다.
- **Affected**: ALL
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/kit.css`, `frontend/src/ui/adminKit.jsx`, `frontend/src/ui/density.js`
- **Verification**: `frontend/src/ui/kit.test.jsx`, `frontend/src/ui/density-contract.test.jsx`, assertion `surface_repetition`, assertion `oversized_empty_surface`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-83. Context Compression, /compact, Session 재시작 이후에도 작업 연속성을 잃지 않는다

- **Wave**: W0
- **Requirement**: 이번 작업은 장시간 수행될 수 있으므로 Claude Code의 Context Compression, `/compact`, Session 재시작, Agent 교체 이후에도 전체 요구사항과 현재 작업 상태를 잃지 않도록 한다. 대화 Context 자체를 작업 상태의 유일한 저장소로 사용하지 않는다. 현재 작업 상태의 정본은 다음 Control Artifact와 실제 Repository 상태다. 1. `docs/ui-renewal/REQUIREMENT_MATRIX.md` 2. `docs/ui-renewal/ROUTE_COVERAGE.json` 3. `docs/ui-renewal/WORK_STATE.md` 4. Git status, diff, commit 5. 실제 Source와 Test 6. 실제 Browser 검증 Evidence Context가 충분히 길어졌거나 `/compact`가 예상되는 경우 현재 작업 정보를 먼저 `WORK_STATE.md`에 Checkpoint한다. Checkpoint에는 최소한 다음을 기록한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84. Plan Mode에서 전체 구현 계획을 완성한 뒤 Auto 실행으로 전환한다

- **Wave**: W0
- **Requirement**: 이번 작업은 처음부터 구현을 시작하지 않는다. 먼저 Plan Mode에서 Repository, 실제 Source, Route, Component, API, Backend, 권한, 현재 Browser 상태를 충분히 조사하고 전체 작업 계획을 완성한다. Plan Mode의 목적은 단순한 작업 목록 작성이 아니다. Auto 실행 단계에서 Context가 압축되거나 Agent가 변경되어도 계획과 Control Artifact만으로 전체 구현을 끝까지 수행할 수 있을 정도로 구체적인 실행 계획을 만드는 것이 목적이다. Plan Mode에서는 기존 UI를 보고 바로 수정 방향을 추측하지 않는다. 먼저 다음 조사를 수행한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-1. Plan Mode에서 Route 전체를 먼저 분류한다

- **Wave**: W0
- **Requirement**: 전체 Route를 사용자 기억이나 기존 문서의 과거 Route 수로 판단하지 않는다. 현재 Source의 Router와 Navigation을 기준으로 다시 추출한다. 모든 Route를 최소 다음 중 적절한 Page Archetype으로 분류한다. Dashboard Home List Data Grid Reading Page Detail Form Workflow Chat Report Settings Operations Console Admin Console Empty-focused Page 기타 실제 제품에 필요한 Archetype 각 Route마다 최소 다음을 계획에 연결한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-2. Plan Mode에서 Root Cause와 공통 Consumer를 먼저 찾는다

- **Wave**: W0
- **Requirement**: 사용자가 캡처로 지적한 문제를 각각 독립적인 CSS 수정 항목으로 계획하지 않는다. 예를 들어 다음 문제는 공통 Root Cause를 먼저 조사한다. 티켓과 문서 상세의 한쪽 쏠림 불필요하게 동일한 Column Width Header와 Cell Alignment 불일치 Search/Filter의 큰 Rectangle Container 프로젝트 일반 Dropdown Navigation Icon의 Heavy Stroke Empty State의 거대한 Blank Canvas White Card 반복 작은 Clovi Purple/Indigo Brand 약화 긴 설명문 노출 수동 동기화 Action 같은 Root Cause를 사용하는 Component와 전체 Consumer Route를 계획에 기록한다. 한 화면의 CSS만 수정하는 계획이면 불완전한 계획으로 판단한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-3. Plan Mode에서 디자인 방향과 구현 기술을 분리한다

- **Wave**: W0
- **Requirement**: Plan Mode에서 다음처럼 기존 구현을 이유로 디자인을 미리 확정하지 않는다. 현재 MUI Component이므로 유지 현재 Table이므로 유지 현재 Card가 있으므로 유지 현재 Sidebar 구조를 유지 현재 CSS Selector를 유지 현재 Chart Library를 유지 현재 Test가 있으므로 Visual Structure 유지 기능적으로 재사용할 부분과 Visual Design으로 다시 설계할 부분을 각각 구분한다. 좋은 Logic, Data Handling, Permission Handling, Accessibility Logic은 재사용할 수 있다. 현재 Visual Structure는 Audit 결과에 따라 재설계한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-4. Plan Mode에서 Page별 Information Architecture와 Content Architecture를 계획한다

- **Wave**: W0
- **Requirement**: 각 주요 Page에 대해 단순히 어떤 Component를 사용할지만 계획하지 않는다. 다음 질문에 답한 결과를 구현 계획에 반영한다. 사용자는 왜 이 Page에 들어오는가 첫 5초 동안 무엇을 알아야 하는가 가장 중요한 Action은 무엇인가 현재 빠진 정보는 무엇인가 현재 중복 정보는 무엇인가 정보 우선순위는 무엇인가 어떤 정보는 Table이 적합한가 어떤 정보는 Summary가 적합한가 어떤 정보는 Chart가 필요한가 어떤 정보는 Card가 필요하지 않은가 Empty 상태에서는 무엇이 사라져야 하는가 넓은 화면의 공간을 어떻게 사용할 것인가 Reading Page인지 업무 Detail Page인지 보조 Context가 실제로 필요한가 현재 Backend/API 데이터로 추가할 가치 있는 정보가 있는가 Dashboard, Home, Sprint, Project, Chat, Ticket, Document, Board, Admin Console은 특히 이 과정을 생략하지 않는다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-5. Plan Mode에서 Design System 계획을 Page 구현 계획보다 먼저 검증한다

- **Wave**: W0
- **Requirement**: 다음 공통 규칙을 먼저 계획한다. Purple/Indigo Brand System Canvas와 Surface Typography Spacing Grid Responsive Breakpoint Button Form Search Filter Combobox/Autocomplete Table/Grid Column Width Alignment Metadata Status Badge Modal Empty State Feedback Navigation Icon Clovi Chart Reading Width Detail Layout 하지만 이 Design System을 모든 화면에 동일한 모양으로 강제하지 않는다. Page Archetype별 Variant가 필요한 항목을 계획 단계에서 구분한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-6. Plan Mode에서 Pilot 구현 대상을 구체적으로 정한다

- **Wave**: W0
- **Requirement**: 전체 Theme을 한 번에 변경하기 전에 서로 다른 Page Archetype을 대표하는 Pilot을 정한다. 최소 다음 영역을 포함한다. 사용자 Home Project Sprint Chat Ticket 또는 Document Detail Reading Page 또는 Board Detail Admin Organization/User Admin Settings 또는 Operations Pilot마다 다음을 계획한다. 현재 문제 목표 UX 새 Layout 사용 Design Component Brand 적용 Responsive 방식 Empty/Data 상태 Browser 검증 Visual Reviewer 기준 기능 회귀 테스트 Pilot을 통과한 Design Direction만 나머지 Route에 확장한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-7. Plan Mode에서 구현 Wave와 의존성을 실제 코드 기준으로 설계한다

- **Wave**: W0
- **Requirement**: 단순히 Page 이름 순서대로 구현하지 않는다. 공통 Root Cause와 의존성을 기준으로 구현 순서를 결정한다. 예를 들어 다음과 같은 순서를 검토한다. Brand Foundation Design Token과 Theme Global Shell Navigation/Icon 공통 Layout Search/Filter Table/Grid/Metadata/Alignment Empty/Feedback Pilot Page 핵심 사용자 Workflow 나머지 사용자 Route Admin IA Admin Console Cross-cutting UX Functional E2E Whole-product Visual Audit 실제 Source 의존성에 따라 더 좋은 순서가 있으면 변경할 수 있다. 계획에 각 Wave가 어떤 Requirement와 Route를 처리하는지 명시한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-8. Plan Mode에서 테스트 계획도 구현 계획과 동일한 수준으로 작성한다

- **Wave**: W0
- **Requirement**: 각 주요 변경에 대해 단순히 `테스트 수행`이라고 적지 않는다. 무엇을 어떻게 검증할지 작성한다. Component Test Route Test API Test Permission Test Empty State Loading Error Long Text Many Data Keyboard Responsive Browser Zoom Browser Screenshot Before/After Visual Reviewer Requirement Reviewer TEST SERVER E2E Hostname TLS Certificate Product Identity Migration 기능이 있는 경우 Screen -> Action -> Network -> API -> Backend -> Data -> UI Result -> Reload -> Permission 흐름까지 계획한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-9. Plan Mode 완료 Gate

- **Wave**: W0
- **Requirement**: 다음 조건을 모두 만족하기 전에는 Plan Mode의 계획이 완료된 것으로 판단하지 않는다. 1. 1번부터 84번까지 모든 Requirement가 계획과 연결됨 2. Source 기준 전체 Route Inventory 완료 3. 모든 Route가 Page Archetype으로 분류됨 4. 모든 주요 Route의 현재 문제 또는 Audit 대상이 기록됨 5. 공통 Root Cause와 Consumer가 식별됨 6. Design System 계획 존재 7. Purple/Indigo Brand 계획 존재 8. Clovi 사용 계획 존재 9. Global Shell과 Navigation 계획 존재 10. Search/Filter 계획 존재 11. Table/Grid/Metadata/Column Width/Alignment 계획 존재 12. Detail/Reading Page Layout 계획 존재 13. Empty State와 Blank Space 계획 존재 14. Admin IA 계획 존재 15. Responsive/Zoom 계획 존재 16. 기능/권한/E2E 계획 존재 17. Pilot 대상
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-10. Plan Mode에서 계획을 Control Artifact에 남긴다

- **Wave**: W0
- **Requirement**: Plan 결과가 대화 Context에만 존재하지 않도록 한다. Auto 실행 전 최소 다음 Artifact를 생성 또는 초기화한다. `docs/ui-renewal/REQUIREMENT_MATRIX.md` `docs/ui-renewal/ROUTE_COVERAGE.json` `docs/ui-renewal/WORK_STATE.md` 필요하면 별도의 실행 계획 문서를 만들 수 있으나 불필요하게 많은 Docs를 생성하지 않는다. WORK_STATE에는 다음 상태를 명확히 기록한다. PLAN_COMPLETE 계획 완료 시점의 Git SHA 전체 Requirement 수 전체 Route 수 Pilot 대상 구현 Wave 현재 Critical/High Finding Auto 실행 시 첫 작업 Plan 결과의 핵심 Design Decision 아직 확인하지 못한 외부 Blocker 대화 Context가 사라져도 이 Artifact와 Repository를 확인하면 Auto 실행 단계에서 바로 이어갈 수 있어야 한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-11. Plan Mode에서 Auto 실행으로 전환할 때 구현 계약을 다시 검수한다

- **Wave**: W0
- **Requirement**: Plan Mode 완료 후 Auto 실행으로 전환하면 바로 코드부터 수정하지 않는다. Auto 실행 시작 시 다음을 다시 확인한다. CLAUDE.md 전체 지시사항 REQUIREMENT_MATRIX.md ROUTE_COVERAGE.json WORK_STATE.md Git status와 diff 현재 Source Plan에서 지정한 첫 Wave와 Pilot 이후 Plan의 Wave와 Requirement Traceability를 기준으로 구현을 시작한다. Auto 실행 단계에서 새로운 사실이나 더 좋은 구현 방법을 발견하면 Plan을 맹목적으로 따르지 않는다. 계획의 목적과 Requirement는 유지하면서 구현 방식은 더 적절하게 수정할 수 있다. 계획이 변경되면 Requirement Matrix와 WORK_STATE도 함께 갱신한다. Auto 단계에서 Plan의 일부가 잘못됐다는 사실을 발견해도 사용자 승인 대기 상태로 멈추지 않는다. 기능, 데이터, 권한, 보안, Brand 확정사항을 보존하면서 스스로 올바른 방향으로 계획을 수정하고 작업을 계속한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-84-12. Auto 실행 중 계획 누락을 지속적으로 재검사한다

- **Wave**: W0
- **Requirement**: Plan Mode를 통과했다는 이유로 이후 Requirement 검사를 중단하지 않는다. 각 Wave 시작 전 다음을 확인한다. 이 Wave가 처리해야 하는 Requirement 처리해야 하는 Route 공통 Consumer 이전 Wave에서 발생한 새로운 Finding 각 Wave 종료 후 다음을 다시 확인한다. Requirement Mapping Route Coverage Test Evidence Browser Evidence Visual Reviewer Requirement Reviewer 새로운 Root Cause Plan 단계에서 발견하지 못한 문제는 자동으로 Backlog에만 쌓아두지 않는다. 현재 Scope와 관련된 문제라면 해당 Wave 또는 적절한 다음 Wave에 포함하여 끝까지 해결한다. 84번 역시 Requirement Matrix와 Route Coverage, Coverage Gate에 포함한다. 최종 Coverage Gate는 1번부터 84번까지 모든 Requirement가 실제 구현, 검증 방법, Browser Evidence와 연결되어 있는지 확인해야 한다.
- **Affected**: NONE (실행 방식과 Control Plane 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-85. Search·Filter·Sort·Pagination·Combobox 기능 정확성 End-to-End

- **Wave**: W5B
- **Requirement**: Search/Filter/Sort/Pagination/Autocomplete/Combobox 를 쓰는 전체 화면을 조사하고, 실제 데이터 기준으로 UI 선택 상태 → Frontend State → URL Query/Route State → API Request Parameter → Backend Query → DB 및 실제 Data Relation → API Response(Total Count 포함) → Rendering 된 목록의 여덟 단계가 전부 일치함을 확인한다. Frontend 에서 선택된 Filter 값만 바뀐 것을 정상 동작으로 판단하지 않는다.
- **Affected**: CONSOLE:user, CONSOLE:admin
- **Implementation**: `frontend/src/screens/TicketFilterBar.jsx`, `frontend/src/lib/useQueryState.js`, `app/tickets/repository.py`, `app/tickets/router.py`
- **Verification**: `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 filter/search/pagination Flow, `python -m scripts.ui_qa.run --fail-on plain_dropdown_for_entity`, Known Data 대조 transcript
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-86. Filter 단독 조건과 복합 조건 조합의 결과 정합성

- **Wave**: W5B
- **Requirement**: 존재하는 축(프로젝트·상태·우선순위·난이도·기한·담당자·카테고리·검색어)마다 단독 적용과 복합 적용 결과가 실제 데이터와 일치하는지 확인한다. 다른 Resource 와 연결된 Filter 는 표시 문자열이 아니라 실제 Relation 과 안정적 Identifier 를 기준으로 동작해야 한다. 미할당 티켓처럼 Page 기본 Scope 가 있는 화면은 기본 Scope 와 사용자 Filter 의 결합을 분리해 Known Data 와 대조한다. 누락이 나오면 Frontend 에서 멈추지 않고 API Parameter, Backend Join 과 Relation, Permission Scope, Query Condition 까지 추적해 Root Cause 를 고친다.
- **Affected**: CONSOLE:user, CONSOLE:admin
- **Implementation**: `frontend/src/screens/TicketFilterBar.jsx`, `frontend/src/lib/useQueryState.js`, `app/tickets/repository.py`, `app/tickets/router.py`
- **Verification**: `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 filter/search/pagination Flow, `python -m scripts.ui_qa.run --fail-on plain_dropdown_for_entity`, Known Data 대조 transcript
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-87. Filter 의 Pagination·Race Condition·Cache Key·Back/Forward 일관성

- **Wave**: W5B
- **Requirement**: Filter 를 바꿀 때 Pagination 이 이전 Page 에 남아 0건처럼 보이지 않아야 한다. 빠르게 Filter 를 변경했을 때 오래된 API 응답이 최신 조건을 덮어쓰지 않아야 한다. Cache 또는 Query Key 오류 때문에 다른 Filter 를 선택해도 같은 결과가 재사용되지 않아야 한다. Refresh 와 Browser Back/Forward 이후 화면에 표시된 조건과 실제 Query 조건이 일치해야 한다.
- **Affected**: CONSOLE:user, CONSOLE:admin
- **Implementation**: `frontend/src/screens/TicketFilterBar.jsx`, `frontend/src/lib/useQueryState.js`, `app/tickets/repository.py`, `app/tickets/router.py`
- **Verification**: `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 filter/search/pagination Flow, `python -m scripts.ui_qa.run --fail-on plain_dropdown_for_entity`, Known Data 대조 transcript
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-88. Filter UI 가 실제 데이터 길이와 사용 흐름을 견딘다

- **Wave**: W0
- **Requirement**: 모든 Filter 를 동일한 폭으로 기계 배치하지 않는다. 프로젝트처럼 값이 길고 주요 탐색 조건인 항목은 충분한 공간과 검색 가능한 Combobox 를 제공하고, 선택한 값이 무엇인지 알 수 없을 정도로 잘리지 않아야 한다. Dropdown 목록에서도 비슷하게 긴 이름을 서로 구분할 수 있어야 한다. 필터 지우기와 초기화가 Input 이나 Select 와 같은 Grid Cell 처럼 보이지 않아야 하고, 결과 건수는 현재 조건에 대한 결과라는 관계가 드러나는 자리에 둔다. 데이터 자체가 없는 상태와 Filter 때문에 0건인 상태를 구분한다. 25행 같은 수치를 절대 규칙으로 기계 적용하지 않고 데이터 규모와 사용 빈도와 찾기 난이도와 Filter 축 수와 업무 목적을 함께 판단한다.
- **Affected**: ARCHETYPE:list_table
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-89. 티켓 Grid Inline Edit 와 공통 Property Editing Pattern

- **Wave**: W6
- **Requirement**: 권한이 있는 사용자가 상세 수정 화면으로 이동하지 않고 Grid 에서 상태와 우선순위를 바꿀 수 있어야 한다. DataTable 이나 Status Cell 의 스타일 변경만으로 이 요구를 완료 처리하지 않는다. 현재 값, 변경 가능한 값, 선택, Saving, 성공, 실패, Rollback, 권한 없음, 중복 요청 방지를 모두 포함하는 공통 Property Editing Pattern 을 만든다. 평상시에는 Grid 가독성을 해치지 않되 변경 가능한 값임을 알 수 있어야 하고, 모든 Editable Value 를 항상 Select Box 로 노출하지 않는다. Frontend State 만 바꾸고 성공 처리하지 않으며 Backend 저장을 확인하고 필요하면 재조회해 실제 값으로 갱신한다. Frontend 의 변경 가능 여부와 Backend Authorization 이 일치해야 한다.
- **Affected**: user_my-tickets, user_team-tickets, user_unassigned, user_tickets-id, user_me
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-90. Detail Metadata 를 폭 조정이 아니라 정보 위계로 재설계

- **Wave**: W7
- **Requirement**: 상단 속성 영역에서 모든 Label 과 Value 를 동일한 중요도로 나열하는 구조를 유지하지 않는다. 사용자가 먼저 판단해야 하는 값과 보조 Metadata 를 구분하고, 모든 Property 를 Card 나 Badge 로 만들지 않으며 Compact Metadata Strip 과 Property Group 과 Definition Layout 중 적절한 표현을 고른다. 넓은 화면에서 속성 사이 간격만 늘어나 시선 이동이 커지지 않아야 하고 좁은 화면에서 중요한 값을 잘라내지 않아야 한다. 긴 프로젝트명이 든 실제 데이터로 FHD 와 QHD 와 4K 와 Browser Zoom 을 검증한다. 자주 바뀌는 Property 는 Detail 상단 Inline Edit 적절성을 판단하되 Grid 와 Detail 과 Form 이 같은 값을 서로 다른 Interaction 으로 중복 구현하지 않는다.
- **Affected**: ARCHETYPE:work_detail, ARCHETYPE:reading_page
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/Mascot.jsx`, `frontend/src/lib/assets.js`, `frontend/src/ui/charts/base.jsx`
- **Verification**: assertion `mascot_visible_size`, `frontend/src/ui/charts/donut-empty-state-height.test.jsx`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-91. 동일 값 Column 자동 제거는 Scope 근거가 있을 때만

- **Wave**: W6
- **Requirement**: 현재 렌더된 행의 값이 모두 같다는 이유만으로 Table Column 을 제거하지 않는다. Pagination 이나 Server-side Search 와 Filtering 을 쓰는 화면에서는 현재 Page 의 값이 같다고 전체 Result Set 이 같은 것이 아니며, Page 이동이나 Filter 변경마다 Column 이 생겼다 사라지는 불안정한 Layout 을 만들면 안 된다. 화면 자체가 특정 값 전용 View 이거나 사용자가 그 Filter 를 명시적으로 적용했거나 Backend Query Contract 상 그 Scope 에서 값이 불변인 경우에만 제거한다.
- **Affected**: ARCHETYPE:list_table
- **Implementation**: `frontend/src/ui/kit.jsx`, `frontend/src/ui/cells.jsx`, `frontend/src/screens/registry/shared.js`
- **Verification**: assertion `equal_column_split`, assertion `column_width_vs_content`, assertion `header_cell_alignment_mismatch`, assertion `numeric_alignment`, `frontend/src/ui/kit.test.jsx`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-92. 전체 기능 Inventory 기반 Functional E2E

- **Wave**: W14
- **Requirement**: 주요 Workflow 라는 표현으로 범위를 제한하지 않는다. 사용자 영역과 관리자 영역의 전체 Route 와 주요 Interactive Function 을 Inventory 해 Functional Coverage Matrix 를 만들고, Search 와 Filter 와 Sort 와 Pagination 과 Combobox 와 Create 와 Read 와 Edit 와 Delete 와 상태 변경과 우선순위 변경과 담당자 변경과 Inline Edit 와 Form Validation 과 Modal 및 Drawer Action 과 Row Action 과 Context 및 Overflow Action 과 Navigation 과 Deep Link 와 Refresh 와 Back/Forward 와 첨부 및 다운로드와 Notification 과 Approval 과 Settings Save/Apply/Test 와 관리자 운영 Action 과 권한별 노출과 401 과 403 과 Session Expiry 와 Loading 과 Empty 와 Error 와 Long Text 와 Many Data 를 검증한다. 실제 존재하는 기능만 검증하고 없는 기능을 테스트용으로 새로 만들지 않는다.
- **Affected**: CONSOLE:user, CONSOLE:admin
- **Implementation**: `scripts/ui_qa/run.py`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`
- **Verification**: `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth`, Gate 조건 C11 과 C12 와 C13 과 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-93. 화면 간 Resource 및 Derived Metric 정합성

- **Wave**: W14
- **Requirement**: 한 화면의 API 가 200 을 반환했다고 완료 처리하지 않는다. 티켓 상태를 바꾸면 Grid 와 상세와 내 티켓과 팀 티켓과 미할당 티켓의 포함 여부와 Dashboard 및 Home 의 Count 와 Sprint 나 업무량 집계까지 실제로 일치하는지 확인한다. Dashboard 와 Home 과 Sprint 와 관리자 Overview 의 Count 와 KPI 와 Chart 도 Rendering 여부가 아니라 Source Data 및 계산 결과와 맞는지 검증하고, 같은 Resource 나 Derived Metric 을 화면마다 다른 기준으로 계산해 숫자가 불일치하지 않는지 확인한다.
- **Affected**: user_me, admin_dashboard, user_sprint, user_my-stats, user_my-tickets, user_team-tickets, user_unassigned
- **Implementation**: `scripts/ui_qa/run.py`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`
- **Verification**: `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth`, Gate 조건 C11 과 C12 와 C13 과 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-94. 죽은 UI 와 Backend 미연결을 사용자 영역까지 전수검증

- **Wave**: W14
- **Requirement**: 관리자 기능뿐 아니라 사용자 영역에서도 눌러도 아무 동작하지 않는 Button 과 Frontend 만 값이 바뀌는 기능과 Backend 저장은 되었으나 화면이 갱신되지 않는 기능과 API 는 있는데 UI 가 연결되지 않은 기능과 UI 는 있는데 Backend 구현이 없는 기능과 죽은 Route 와 잘못된 Query Parameter 와 관계 데이터 연결 누락과 오래된 Cache 와 중복 요청과 Race Condition 과 권한 불일치를 조사한다. 발견한 문제가 이번 리뉴얼과 관련된 실제 제품 기능이면 사용자가 제보할 때까지 남겨두지 않고 Root Cause 를 고친다.
- **Affected**: CONSOLE:user, CONSOLE:admin
- **Implementation**: `scripts/ui_qa/run.py`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`
- **Verification**: `python -m scripts.ui_qa.run --base-url https://clovirassist.gooddi.lab --rebuild-auth`, Gate 조건 C11 과 C12 와 C13 과 C14
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-95. Functional Coverage 를 기계적으로 추적

- **Wave**: W15
- **Requirement**: ROUTE_COVERAGE 와 Requirement Matrix 만으로 Functional Coverage 를 대신하지 않는다. Route 가 존재하고 Screenshot 이 있다는 사실은 그 화면의 기능이 정상이라는 증거가 아니다. FUNCTIONAL_COVERAGE.json 에서 각 Route 의 주요 Action 과 Workflow 를 NOT_AUDITED 와 PASS 와 FAIL 과 BLOCKED 중 하나로 추적하고 PASS 에는 실제 Browser Action 과 Network 와 API 와 Backend 와 Data 결과를 확인한 Evidence 를 요구한다. 화면이 렌더됐다는 Evidence 만으로 Functional PASS 처리하지 않으며 최종 Gate 에서 NOT_AUDITED 가 남으면 완료하지 않는다.
- **Affected**: ALL
- **Implementation**: `scripts/ui_qa/run.py`, `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage complete`, `bash scripts/run_full_regression.sh`, `bash scripts/static_checks.sh`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-96. 계획 구조 무결성과 완료 조건 강화

- **Wave**: W0
- **Requirement**: 이름 없는 Wave 와 존재하지 않는 Phase 나 Wave 참조와 비어 있는 소유 파일 및 전제 항목과 실제와 불일치하는 진행 상태 표기가 0건이어야 한다. 각 Wave 의 종료 내용은 별도 행이 아니라 그 Wave 의 Exit Gate 안에 있어야 한다. 최종 완료 조건에 Search 와 Filter 정합성과 Filter 조합 검증과 Inline Edit E2E 와 Detail Metadata 실데이터 검수와 Functional Coverage 완료와 화면 간 정합성과 Frontend 및 Backend 상태 불일치 0 과 죽은 Action 0 과 Race Condition 검증과 NOT_AUDITED 0 을 추가한다.
- **Affected**: NONE (계획 문서와 Gate 자체에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)

---

## R-97. 프로젝트 내부 지속 문서에 최종 계획과 인계 상태를 기록

- **Wave**: W0
- **Requirement**: 최종 실행 계획과 Requirement Matrix 와 Route 및 Page 및 Archetype Coverage 와 Functional Coverage 와 현재 Git 상태와 기준 Commit 과 현재 Build Fingerprint 와 Before Evidence 와 Wave 순서 및 Exit Criteria 와 현재 Blocker 와 다음 실행 명령이 대화 Context 없이도 복구 가능해야 한다. WORK_STATE 의 압축 복구 구조와 Gate 우선 원칙을 유지한다.
- **Affected**: NONE (저장소의 Control Artifact 에 대한 요구다 — 특정 화면에 살지 않는다)
- **Implementation**: `scripts/check_ui_renewal_coverage.py`, `docs/ui-renewal/ROUTE_COVERAGE.json`, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json`, `scripts/ui_qa/routes.py`, `scripts/ui_qa/assertions.py`
- **Verification**: `python scripts/check_ui_renewal_coverage.py --stage plan`, `python -m scripts.ui_qa.run --list`, `pytest tests/regression/test_ui_qa_route_registry_completeness.py`
- **Status**: NOT_STARTED
- **Evidence**: (없음 - Status 가 DONE 이 될 때 채운다)
- **Findings**: (없음)
- **Depends on**: (없음)
