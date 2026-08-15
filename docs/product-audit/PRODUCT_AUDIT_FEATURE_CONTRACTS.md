# PRODUCT AUDIT — FEATURE / WORKFLOW CONTRACTS

> cycle_id=PA-20260812-171558-56c5befa · baseline=`89ac9f16d42e8bd0bab8c4ca97b15d6563b03fde`
>
> **코드의 현재 동작을 그대로 '의도'라고 적지 않는다.** 각 Contract는 의도의 근거
> (Intent evidence)와 confidence를 함께 단다. 근거가 코드밖에 없으면 `INFERRED`로 표시하고
> confidence를 낮춘다 — 그 상태로는 Handoff로 승격하지 않는다.
>
> 근거 우선순위(이 Audit 프롬프트 3절): ① 명시적 제품 정책 ② CLAUDE.md/SSOT 문서
> ③ API schema·데이터 모델 ④ 신뢰할 수 있는 테스트 ⑤ 일치하는 FE/BE 흐름 ⑥ 주석·명명.

## 요약

| # | Contract | Actor | Intent 근거 등급 | Confidence |
|---|---|---|---|---|
| FC-01 | 승인 결재 (승인/반려/취소) | operator+ · 위임 수임자 | ③④⑥ | Strong |
| FC-02 | 기능 제안 게시글 상태 전이 | 중재자군 | ③⑥ | Strong |
| FC-03 | 프롬프트 수명주기 | admin+ | ①③⑥ | Strong |
| FC-04 | AI 어시스턴트 4탭(결정적 집계 + 선택적 문장) | 로그인 사용자 | ③⑤⑥ | Strong |
| FC-05 | 화면 역할 게이트 (사이드바 ↔ 라우트 ↔ 백엔드) | 전 역할 | ②⑤⑥ | Strong |
| FC-06 | AI 사용 상한(쿼터) 소비 | 로그인 사용자 | ⑥ + 부분 ③ | **Probable** |

---

<a id="fc-01"></a>
## FC-01 · 승인 결재 (승인 / 반려 / 취소)

| 항목 | 내용 |
|---|---|
| **Actor/Role** | `CONSOLE_WRITE_ROLES`(admin, system_admin) **또는** 활성 위임을 받은 사람. 취소는 `CONSOLE_OPS_ROLES`(operator, admin, system_admin) |
| **목적** | 되돌릴 수 없는 업무 결정(인사·오프보딩 등)을 권한자가 기록과 함께 확정한다 |
| **Entry point** | `/approvals` 화면 · `POST /api/admin/approvals/{id}/{approve,reject,cancel}` |
| **Precondition** | 대상 `Approval.status == "pending"` |
| **Allowed state** | `pending → approved / rejected / expired / cancelled`. 종료 상태에서 나가는 전이는 **없다** |
| **Input/validation** | `DecisionRequest.comment` 최대 2000자(선택). 목록 `status` 필터는 5개 알려진 값만 허용하고 그 외는 **400** — 조용한 빈 목록 대신 사유를 말한다 |
| **Expected effect** | 상태 확정 + `record_audit_from_request(action="approval.approve"/"approval.reject")` 감사 기록. 위임 결재면 **누구를 대신했는가**(`on_behalf_of`)가 함께 남는다 |
| **Failure/recovery** | 이미 종료된 건이면 거절(`row.status != APPROVAL_PENDING` 가드). 범위 밖이면 **404**(403 아님) |
| **Forbidden** | ⓐ 권한 없는 사람이 id를 찍어 **큐의 존재를 열거**하는 것 ⓑ 남의 범위 승인 결재 ⓒ 자가 승인(`self_approval_allowed` 플래그가 꺼져 있으면) |
| **RBAC/Scope 의존** | `delegation_service.require_decider` → `get_scoped_approval_or_404(visible_user_ids(scope))`. **권한 판정이 조회보다 먼저**이고, 이 순서가 계약의 일부다 |
| **Intent evidence** | ③ `app/approvals/models.py:12-16` 상태 상수 · ④ `tests/security/test_approval_scope.py`(주석이 이 파일을 계약의 근거로 지목) · ⑥ `app/approvals/router.py::_decide` 의 12줄 주석이 "왜 `require_roles` 데코레이터를 안 쓰는가"(위임자는 WRITE_ROLES가 아닐 수 있다)와 "왜 권한이 조회보다 먼저인가"(열거 방지)를 명시 |
| **Confidence** | **Strong** |
| **Audit 결과** | 이 계약은 코드와 일치한다. `approve`/`reject`에 `require_roles`가 **없는 것**은 결함이 아니라 위임 기능의 필요조건이며 그 사실이 문서화돼 있다 — 재확인함(오탐 방지) |

---

<a id="fc-02"></a>
## FC-02 · 기능 개선 제안 게시글 상태 전이

| 항목 | 내용 |
|---|---|
| **Actor/Role** | 중재자군(`MODERATOR_ROLES`) |
| **목적** | 제안이 "검토를 건너뛰고 진행" 같은 경로로 조용히 넘어가지 않게 한다 — 진행은 **티켓을 만들기 때문에** 되돌리기 어렵다 |
| **Entry point** | `/ideas` → 게시글 상세 |
| **Allowed state** | `제안 → 검토·보류` / `검토 → 진행·보류·제안` / `진행 → 완료·보류` / `완료 → 진행`(잘못 닫은 것 재개) / `보류 → 제안·검토` |
| **Forbidden** | **완료 → 제안** (되돌리기가 아니라 이력 삭제라서 의도적으로 없다) |
| **Expected effect** | `app/board/service.py:170` 이 `IDEA_TRANSITIONS` 에 없는 전이를 거절 |
| **Intent evidence** | ③ `app/board/models.py:93-99` 전이표 · ⑥ 바로 위 6줄 주석이 각 금지 전이의 **이유**를 적는다("아무 데서나 아무 데로 갈 수 있으면 상태는 그냥 라벨") |
| **Confidence** | **Strong** |

---

<a id="fc-03"></a>
## FC-03 · 프롬프트 수명주기

| 항목 | 내용 |
|---|---|
| **Actor/Role** | admin+ (`/prompts`) |
| **Allowed state** | `draft → test·archived` / `test → review·draft·archived` / `review → published·draft·archived` / `published → archived` / `archived → (없음)` |
| **Forbidden** | `draft → published` 직행 · `archived` 에서의 모든 전이 |
| **롤백 의미** | 옛 버전을 **새 버전으로 다시 발행**하는 것이지 상태를 되돌리는 것이 아니다 |
| **Intent evidence** | ① `spec §17.1`(코드 주석이 명시적으로 인용) · ③ `app/prompts/models.py:20-26` · ⑥ `Lifecycle (spec §17.1). Rollback = republish an old version as a NEW version.` |
| **Confidence** | **Strong** — 이 저장소에서 **명시적 스펙 조항을 근거로 댄 몇 안 되는 계약**이다 |

---

<a id="fc-04"></a>
## FC-04 · AI 어시스턴트 4탭

| 항목 | 내용 |
|---|---|
| **Actor/Role** | 로그인 사용자 전체 |
| **Entry point** | `AssistantPanel.jsx` 4탭 → `GET /api/assistant/{briefing,standup,weekly-digest,triage}` |
| **핵심 계약** | **숫자는 결정적 집계, 문장은 선택**이다. `narrate=true` 일 때만 LLM 문장을 만든다 |
| **`triage` 만 다른 점** | `narratable: false`. 서버 주석: *"'이 티켓은 아무개에게' 라는 문장은 결정처럼 읽히고, 그 순간 '제안만'이라는 계약이 화면에서 깨진다"* — 순서와 근거(부하 수)만 준다. `auto_assign: false` |
| **Failure/recovery** | 문장 생성이 실패해도 숫자는 그대로 반환. **문장이 안 나온 경우 쿼터를 깎지 않는다**(`text`가 있고 `error`가 없을 때만 `slot.record()`) |
| **Intent evidence** | ③ 엔드포인트 4개 + 응답 구조 · ⑤ FE `AssistantPanel.jsx:27-30` 의 `narratable` 플래그가 BE `triage`(narrate 파라미터 없음)와 정확히 일치 · ⑥ 라우터 docstring |
| **Confidence** | **Strong** |
| **Audit 결과** | 초기 orphan 스캔이 이 4개를 "UI 없음"으로 오탐했다. 실제로는 `` `/api/assistant/${tab.path}` `` 템플릿 리터럴로 전부 배선돼 있다 — **폐기함** |

---

<a id="fc-05"></a>
## FC-05 · 화면 역할 게이트

| 항목 | 내용 |
|---|---|
| **목적** | *"눌렀더니 403"* 막다른 길을 없앤다 — 사이드바 노출 역할과 백엔드 라우터 권한을 **정확히 같은 집합**으로 맞춘다 |
| **3중 구조** | ⓐ `NAV`/`USER_NAV` 항목의 `roles` (보이는가) ⓑ `SCREEN_ROLES` + `RequireRole` (직접 주소 진입 시 라우트 게이트) ⓒ 백엔드 라우터 `require_roles` (정본) |
| **Forbidden** | 프런트 게이트만으로 권한을 주장하는 것. `navConfig.js:23-24` 가 명시 — *"나브만 숨기면 해시 직접 진입 시 껍데기가 그려지고 API가 raw 403을 뱉는다"* |
| **Intent evidence** | ② CLAUDE.md §3-5(*"권한 판단은 서버가 정본이며 프런트 권한 표시는 보조"*) · ⑤ `navConfig.js:26-30` 이 각 화면의 백엔드 게이트를 파일:역할로 대조해 적어 둠 · ⑥ |
| **Confidence** | **Strong** |
| **Audit 결과 (실측 검증)** | `var/product-audit/scan_nav.py` 로 3계층을 기계 대조했다: **메뉴는 있는데 라우트가 없는 항목 0건**, **라우트는 있는데 메뉴가 없는 항목**은 전부 의도된 것(`/departments`·`/org-tree`는 `/organizations` 로 통합, `/search`는 Ctrl+K·상단바로 진입, `:id` 상세는 목록에서 진입). `roles` 가 선언되지 않은 관리자 메뉴 9개는 `SCREEN_ROLES` 의 `(operator, admin, system_admin, auditor)` 와 **집합이 같다**(관리자 콘솔 자체가 그 역할군에만 보이므로). **불일치 0건** — 이 계약은 지켜지고 있다 |

---

<a id="fc-06"></a>
## FC-06 · AI 사용 상한(쿼터) 소비 — **의도 근거 부족**

| 항목 | 내용 |
|---|---|
| **관측된 동작** | 문장 생성이 성공한 경우에만 `slot.record()` 후 `db.commit()`. 잠금 해제 전에 커밋한다(`UB-08` 주석) |
| **불명확한 것** | ⓐ 상한 **값**이 어디서 오는지, 상한 초과 시 사용자에게 무엇을 보여줄지에 대한 **제품 정책 문서가 없다** ⓑ `docs/WORK_STATE.md` 실측에 따르면 `ai_quotas` 테이블은 **0행**이다 — 즉 이 기능은 운영 데이터가 한 번도 없었다 ⓒ `BACKLOG` `UB-10` 이 *"지금 실제 cap이 없어 화면 가정이 유효함"* 이라고 적는다 |
| **Expected behavior** | **INFERRED** — 코드 동작 외에 근거가 없다 |
| **Confidence** | **Probable** → **Handoff로 승격하지 않는다**(이 프롬프트 8절) |
| **다음 조사** | 상한 정책의 출처(스펙 §? / 사용자 요구)를 찾거나, 없다면 "정책 미정 기능"으로 분류하고 화면이 그 사실을 정직하게 말하는지 본다 |

---

## 아직 Contract를 세우지 못한 주요 Workflow (정직한 UNKNOWN)

아래는 **의도 근거를 아직 확보하지 못한** 것이다. "코드가 이러니 이게 의도"라고 적지 않는다.

| Workflow | 왜 아직 UNKNOWN인가 | 다음 조사 |
|---|---|---|
| 티켓 생성 → 배정 → 완료 | Notion 캐시(`ticket_cache` 1077행)가 정본인지 이 제품이 정본인지에 대한 정책 근거를 아직 못 찾음 | `docs/NOTION_MAPPING.md` + `app/tickets` 동기화 방향 확인 |
| 오프보딩 실행 → undo | `undo` 가 **어디까지** 되돌리는지(티켓 이동·권한·메일) 계약이 코드에만 있음. `offboarding_runs` 0행이라 실측 사례도 없음 | `app/offboarding/service.py` + `docs/USER_LIFECYCLE.md` 대조 |
| 백업 → 복구 리허설 | `docs/BACKUP_RESTORE.md`(분기 1회)가 주기는 정하지만 **성공 판정 기준**이 없음 | 리허설 결과 스키마 확인 |
| 문서 자동 생성 → 승인 → 재시도 | `document_generations` 0행. `STATUS_AWAITING_APPROVAL → STATUS_FAILED` 경로만 코드로 확인 | `app/documents/models.py` 상태 전수 |
| n8n / Claude Runner 실패 전파 | 외부 시스템 경계의 **기대 동작**이 문서화된 곳을 못 찾음 | `docs/WORKFLOW_REGISTRY.md` + `app/runners` |

> **이 표 자체가 산출물이다.** 이 제품에서 명시적 스펙 조항을 근거로 댈 수 있는 계약은
> FC-03(프롬프트 §17.1) 하나뿐이고, 나머지는 코드 주석·테스트·FE/BE 일치로 역산한 것이다.
> 이것은 결함이 아니라 **위험**이다 — 주석을 지우거나 리팩터링하면 의도의 유일한 기록이 사라진다.
