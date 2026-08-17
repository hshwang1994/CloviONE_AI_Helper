# PRODUCT AUDIT — FEATURE / WORKFLOW CONTRACTS

> cycle_id=PA-20260817-072224-24b91505 · baseline=`2aacd2a2ab4a50e92d3dee8f3aba3a248e175e83`
> 이전 Cycle: `PA-20260812-171558-56c5befa` (baseline `89ac9f16`)
>
> **이 Cycle에서의 취급**: 아래 Contract(`FC-01`~`FC-09`)는 이전 Cycle들이 근거와 함께 세운
> 것이고 이번 Cycle에서 **무효화된 것이 없다** — 그대로 이어서 쓴다(WARM 증분 원칙).
> 이번 Cycle이 이 문서에 더한 것은 아래 "PA-20260816 Cycle이 행동으로 확인한 계약" 절이다.
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
| FC-07 | 오프보딩 실행 → 부분 실패 → 되돌리기 | admin+ | ③⑤⑥ | Strong |
| FC-08 | 문서 자동 생성 → 승인 대기 → 발행 | 관리자 | ③⑤⑥ | Strong |

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

<a id="fc-07"></a>
## FC-07 · 오프보딩 실행 → 부분 실패 → 되돌리기 (D축 추적 완료)

| 항목 | 내용 |
|---|---|
| **Actor/Role** | `CONSOLE_WRITE_ROLES`(admin, system_admin) — 라우터 전체가 `require_roles(*CONSOLE_WRITE_ROLES)` + `require_csrf` |
| **목적** | 퇴사자의 티켓·계정·세션을 후임에게 한 번에 넘기되, **되돌릴 수 있게** 한다 |
| **Entry point** | `/offboarding` → 미리보기(`GET /preview/{user_id}`) → 실행(`POST /run/{user_id}`) |
| **Allowed state (실행)** | `running`(끝까지 못 감) · `completed` · `partial`(부분 실패) · `undone` · `undo_partial` |
| **Allowed state (티켓 1건)** | `pending`(소스 호출 직전 표시) · `moved` · `skipped` · `failed` · `reverted` · `revert_failed` |
| **되돌리기 대상** | `REVERTIBLE_MOVES = {moved, revert_failed}` — **`revert_failed`가 포함돼 재시도가 가능하다**(`service.py:454` 주석이 "영영 재시도 못 하게 막지 않는다"고 명시). `pending`은 제외 — 직전 담당자를 모르므로 되돌릴 수 없다 |
| **Expected effect** | 되돌리기는 **계정을 먼저 살리고 그다음 티켓**을 원래 구성으로. 결과 상태는 실패가 있으면 `undo_partial`, 없으면 `undone` |
| **Failure/recovery** | 부분 실패를 `completed`로 뭉개지 않는다. 화면이 `pending`을 **"확인 필요"(warn 톤)** 로 보여 주고, 되돌리기 실패 시 *"N건을 되돌리지 못했습니다. 상세에서 사유를 확인하세요."* 로 **다음 행동을 말한다** |
| **Forbidden** | 부분 실패를 성공으로 기록하는 것 · FK로 `ticket_uid`를 묶는 것(prune이 이력을 지우거나 티켓 미러 전체를 멈춘다) |
| **Intent evidence** | ③ `app/offboarding/models.py:39-58`의 상태 상수 · ⑥ 같은 파일 1-21행 docstring이 **왜 별도 표가 필요한가**(감사 로그는 되돌리기의 입력이 될 수 없다)와 **왜 FK를 안 거는가**를 명시 · ⑤ FE `Offboarding.jsx:49-59`가 11개 상태 전부에 라벨+톤을 부여해 BE 상태집합과 1:1로 맞는다 |
| **Confidence** | **Strong** |
| **D축 판정** | **흐름이 닫혀 있다.** 되돌리기 버튼이 실행 이력 표 안에 있고(`Offboarding.jsx:480-482`), 상세 드로어가 티켓별 이동 사유 표를 보여 주며, 미리보기가 *"아직 되돌리지 않은 실행이 있습니다 … 아래 '실행 이력'에서 먼저 확인하세요"* 로 앞선 실행과 연결된다. 코드 주석이 그 이유를 스스로 적는다 — *"되돌릴 방법이 화면 안에 없으면 아무도 실행 버튼을 못 쓴다"*(`Offboarding.jsx:369`, models.py docstring과 같은 문장) |

<a id="fc-08"></a>
## FC-08 · 문서 자동 생성 → 승인 대기 → 발행 (D축 추적 완료)

| 항목 | 내용 |
|---|---|
| **Actor/Role** | 관리자 콘솔(`/documents`), 발행은 `/approvals` |
| **Allowed state** | `pending` · `preview_ready` · `quality_failed` · `awaiting_approval` · `published` · `failed` (6종) |
| **핵심 계약** | **`awaiting_approval` 문서는 이 화면에서 발행할 수 없다** — 백엔드에 문서별 발행 API가 없고, 발행은 승인 워크플로를 지난다 |
| **Expected navigation** | 그래서 화면이 **막다른 길을 만들지 않는다**: `awaiting_approval` 행에만 나타나는 액션 `"승인 대기 목록으로"` → `#/approvals?status=pending` (`registry/automation.js:322`) |
| **Intent evidence** | ③ `app/documents/models.py:17-22` 상태 6종 · ⑤ FE 필터·렌더가 6종 전부를 같은 어휘로 매핑(`automation.js:265,280,287`) · ⑥ `automation.js:312` 주석이 *"'승인 대기' 문서는 여기서 발행할 수 없다(백엔드에 문서별 발행 API 없음) — 승인 화면으로 안내한다"* 라고 **부재를 의도로 명시** |
| **Confidence** | **Strong** |
| **D축 판정** | **흐름이 닫혀 있다.** 빈 상태(`emptySteps`)가 3단계 절차를 글로 안내하고, 상태별 다음 행동이 화면 안에 있다. `IA-02`(스케줄↔달력↔작업 큐↔문서 생성 상호 이동)가 고친 계열과 같은 배선이 여기서도 성립한다 |

## 아직 Contract를 세우지 못한 주요 Workflow (정직한 UNKNOWN)

아래는 **의도 근거를 아직 확보하지 못한** 것이다. "코드가 이러니 이게 의도"라고 적지 않는다.

| Workflow | 왜 아직 UNKNOWN인가 | 다음 조사 |
|---|---|---|
| 티켓 생성 → 배정 → 완료 | Notion 캐시(`ticket_cache` 1077행)가 정본인지 이 제품이 정본인지에 대한 정책 근거를 아직 못 찾음 | `docs/NOTION_MAPPING.md` + `app/tickets` 동기화 방향 확인 |
| 백업 → 복구 리허설 | `docs/BACKUP_RESTORE.md`(분기 1회)가 주기는 정하지만 **성공 판정 기준**이 없음 | 리허설 결과 스키마 확인 |
| n8n / Claude Runner 실패 전파 | 외부 시스템 경계의 **기대 동작**이 문서화된 곳을 못 찾음 | `docs/WORKFLOW_REGISTRY.md` + `app/runners` |

> **2026-08-15 갱신**: 위 UNKNOWN 5건 중 **2건을 닫았다** — 오프보딩(→ FC-07)과 문서 자동
> 생성(→ FC-08). 둘 다 D축 추적 결과 **흐름이 닫혀 있었고**, 의도 근거도 데이터 모델 + FE/BE
> 일치 + 상세 주석으로 Strong까지 올라갔다. 남은 3건은 아래 그대로다.
>
> **이 표 자체가 산출물이다.** 이 제품에서 명시적 스펙 조항을 근거로 댈 수 있는 계약은
> FC-03(프롬프트 §17.1) 하나뿐이고, 나머지는 코드 주석·테스트·FE/BE 일치로 역산한 것이다.
> 이것은 결함이 아니라 **위험**이다 — 주석을 지우거나 리팩터링하면 의도의 유일한 기록이 사라진다.

---

# PA-20260816 Cycle이 행동으로 확인한 계약

## FC-09 — AI 요청 실패 전파 (이전 Cycle의 UNKNOWN 3건 중 1건을 닫는다)

이전 Cycle은 *"n8n / Claude Runner 실패 전파 — 외부 시스템 경계의 **기대 동작**이 문서화된
곳을 못 찾음"* 을 UNKNOWN으로 남겼다. 이번 Cycle이 **실제 실패 데이터로 그 계약을 관측**했다
(`PA-F-057`). 이 인스턴스에 12일 전 영구 실패한 `chat_message` 잡 3건이 남아 있었다.

| 필드 | 값 |
|---|---|
| **Feature/Workflow** | AI 어시스턴트 요청의 백엔드 실패가 사용자에게 전달되는 경로 |
| **Actor/Role** | `user` 이상 전체(대화 소유자) · 운영 측은 `operator` 이상이 `/jobs`에서 본다 |
| **목적** | 외부 시스템(n8n·Claude Runner) 장애가 **조용한 무응답으로 남지 않게** 한다 |
| **Entry point** | 채팅 입력(`/chat`, `/me`의 AI 도우미 패널) → `chat_message` 잡 |
| **Precondition** | 대화와 사용자 메시지가 이미 저장돼 있고 잡이 그 `conversation_id`·`message_id`를 들고 있다 |
| **Allowed state** | 잡: `queued → running → succeeded \| failed \| cancelled`. 메시지: `pending/processing → done \| failed` |
| **Input/validation** | 해당 없음(이 계약은 실패 경로다) |
| **Expected transition/effect** | 재시도 소진(`attempt_count == max_attempts`) 시 ① 잡 `status=failed` + `last_error` 보존 ② 사용자 메시지 `processing_status=failed`, `error_code=assistant_error` ③ **어시스턴트 역할 메시지로 한국어 설명이 기록됨** |
| **Success feedback/navigation** | 해당 없음 — 이 계약의 성공은 "실패가 정확히 보이는 것"이다 |
| **Failure behavior/recovery** | 대화에 3요소 문구 표시 — *"업무 처리 서버와의 연결에 문제가 있어 요청을 완료하지 못했습니다. '다시 시도' 버튼을 누르면 같은 내용으로 다시 처리합니다. 계속 실패하면 관리자에게 알려주세요."* + 「다시 시도」 버튼. **재시도가 무의미한 분류(`assistant_rejected`)는 다른 문구**로 안내한다 |
| **Forbidden behavior** | 내부 예외 문자열(`RuntimeError: n8n 연결 실패`)을 사용자에게 노출하지 않는다 — 실측에서 노출되지 않았다. 사용자를 무응답 상태로 방치하지 않는다 |
| **Data/API/RBAC/integration deps** | `jobs`(`job_type`·`attempt_count`·`max_attempts`·`last_error`·`conversation_id`·`message_id`) · `messages`(`processing_status`·`error_code`) · `app/jobs/handlers/chat_message.py::on_failure` · `frontend/src/screens/chat/MessageThread.jsx:39-129` · 외부 n8n/Runner |
| **Intent evidence** | ④ **테스트가 계약을 표현한다** — `processing_status`/`assistant_error`를 다루는 테스트 5파일(`message-thread-actions`·`message-thread-inline-cards`·`message-thread-response-time`·`chat-state`·`assistant-drawer-parity`). ⑤ FE/BE 흐름 일치 — 핸들러가 쓰는 상태를 UI가 그대로 분기한다. ⑥ `MessageThread.jsx:121-129` 주석이 `assistant_rejected`와 `assistant_error`를 **왜** 다르게 다루는지 명시. **명시적 정책 문서는 여전히 없다**(①②③ 없음) |
| **Confidence** | **Strong** — 실제 실패 데이터 3건으로 ①잡 ②메시지 ③문구 세 계층을 모두 관측했고 테스트가 계약을 고정한다. Confirmed로 올리지 않는 이유는 **성공 경로와 「다시 시도」 클릭 이후를 측정하지 못했기 때문**이다(이 인스턴스의 유일한 러너가 `enabled=0`) |

> **UNKNOWN 표 갱신**: 위 3건 중 이 건이 닫혔다. **남은 UNKNOWN은 2건** —
> 「티켓 정본 정책」과 「복구 리허설 성공 판정 기준」이다. 둘 다 이번 Cycle에서 조사하지 않았다.

---

# §PA-20260817 Cycle — 이 Cycle이 근거와 함께 세운 Contract (FC-10 ~ FC-15)

> `FC-01`~`FC-09` 는 이전 Cycle들이 세운 것이고 **이번 Cycle에서 무효화된 것이 없다** —
> 그대로 이어서 쓴다. 아래는 이번 Cycle의 Root Cause 가 실제로 판정 근거로 삼은 계약이다.
> 각 Contract 는 이 Cycle 이 **실행으로 확인한 것**만 담는다.

## 요약

| # | Contract | Actor | Intent 근거 등급 | Confidence |
|---|---|---|---|---|
| FC-10 | 내 티켓 요약 표시 (판정 불가 상태 포함) | 로그인 사용자 | ②③⑤⑥ | **Confirmed** |
| FC-11 | 최초 로그인 강제 비밀번호 변경 | 신규·재설정 계정 | ②③④ | **Confirmed** |
| FC-12 | 운영 상태 조회 대 진단 번들 수집 | operator+ | ①③⑥ | Strong |
| FC-13 | 화면 위치 표시 (breadcrumb ↔ 사이드바) | 전 역할 | ⑤⑥ | Strong |
| FC-14 | 목록의 빈 상태 (결과 없음 대 데이터 없음) | 전 역할 | ⑤⑥ | Strong |
| FC-15 | 없는 레코드 요청에 대한 응답 | 전 역할 | ③⑤ | Strong |

### RC 가 쓴 이름 ↔ Contract 대응

이번 Cycle의 `PA-RC-*` 블록은 `feature_contracts:` 에 서술형 이름을 썼다. 대응은 다음과 같다.

| RC 가 쓴 이름 | Contract |
|---|---|
| FC-홈-오늘(내 티켓 요약) · FC-내업무량(완료 통계) | **FC-10** |
| FC-최초로그인-비밀번호변경 | **FC-11** |
| FC-AI대화전송 | **FC-04**(AI 어시스턴트) + **FC-11** 과 같은 쓰기 경합 계열 |
| FC-운영대시보드 · FC-진단번들 | **FC-12** |
| FC-관리자내비게이션 · FC-사용자내비게이션 · FC-사용자콘솔내비게이션 | **FC-13** |
| FC-공용빈상태 · FC-승인워크플로 | **FC-14** (+ 승인 자체는 **FC-01**) |
| FC-공용오류표시 · FC-게시판상세 | **FC-15** |
| FC-사용자관리 · FC-조직관리 · FC-감사로그 · FC-시스템설정 · FC-오프보딩 · FC-티켓생성 · FC-권한거부표현 | **FC-05**(역할 게이트) · **FC-07**(오프보딩) 및 위 신규 계약의 조합 |

---

## FC-10 · 내 티켓 요약 표시 (판정 불가 상태 포함)

| 필드 | 값 |
|---|---|
| Actor / Role | 로그인 사용자 본인 |
| 목적 | 오늘 무엇을 해야 하는지 숫자로 먼저 보여준다 |
| Entry point | `/me` 상단 타일 6종, `/my-stats` 타일 6종, `/dashboard` 「내 업무」 |
| Precondition | 로그인. Notion 사용자 매핑은 **있을 수도 없을 수도 있다** |
| Allowed state | `configured` × `ok` × `mapped` 세 불리언의 조합 |
| Expected effect | `ok and mapped` 일 때만 버킷을 센다. 아니면 **버킷을 응답에 싣지 않는다** |
| Success feedback | 숫자 타일. 판정 불가면 `-` (프런트가 `null` 을 그렇게 그린다) |
| Failure behavior | 티켓이 죽어도 문서·게시판·알림 위젯은 그대로 나온다(§17.4 장애 격리) |
| **Forbidden** | **판정 불가를 `0` 으로 그리는 것.** 「0건」과 「모른다」는 다른 말이다 |
| Data/API 의존 | `GET /api/home/today`, `GET /api/me/stats`, `user_notion_mappings` |
| Intent evidence | ② `docs/DASHBOARD_METRICS.md` §3(「소스 장애면 버킷 자체가 없다 → `-`」, 서두의 「안 쟀다를 0으로 그리면…」) · ③ 응답 스키마의 `mapped` 플래그 · ⑤ `Home.jsx:309` 가 이미 `null`→`-` 처리 · ⑥ `service.py:110`·`work.py:236` 주석이 불변식을 명시 |
| Confidence | **Confirmed** — 문서·코드 주석·형제 구현·API 원문 네 가지가 일치한다 |
| 현재 위반 | `PA-RC-0027` (호출부 2곳에 가드 없음) |

## FC-11 · 최초 로그인 강제 비밀번호 변경

| 필드 | 값 |
|---|---|
| Actor / Role | 신규 계정, 관리자가 비밀번호를 재설정한 계정 |
| 목적 | 임시 비밀번호로 제품에 들어오지 못하게 막는 **관문** |
| Entry point | 로그인 성공 직후 `/change-password` 로 강제 이동 |
| Precondition | `users.must_change_password = true` |
| Input/validation | 현재 비밀번호 + 새 비밀번호 + 확인. 정책은 최소 길이·문자 종류(서버가 정본) |
| Expected transition | 성공 시 `must_change_password → false`, **다른 세션 전부 폐기 + 세션 회전**(spec §11.3) |
| Success feedback | 원래 가려던 화면 또는 홈으로 이동 |
| Failure behavior | 정책 위반은 필드별 안내. **쓰기 경합은 사용자에게 보이면 안 된다** — 서버가 재시도로 흡수한다 |
| **Forbidden** | 통과하지 못한 계정이 제품 화면에 도달하는 것. 그리고 **경합을 raw 500 으로 흘리는 것** |
| Data/API 의존 | `POST /change-password`, `users`, `sessions`, `audit_logs` |
| Intent evidence | ② CLAUDE.md §3-10(공용 classifier/retry 규약 재사용 의무) · ③ spec §11.3 세션 규약 · ④ `app/core/db.py:183` 이 재시도 기본값을 「실측으로 검증된 유일한 값」이라며 승격하고 같은 파일 `login()` 이 그 기준 구현을 갖는다 |
| Confidence | **Confirmed** |
| 현재 위반 | `PA-RC-0032` (이 경로에만 공용 관용이 없다) |

## FC-12 · 운영 상태 조회 대 진단 번들 수집

| 필드 | 값 |
|---|---|
| Actor / Role | operator · admin · system_admin (`CONSOLE_OPS_ROLES`) |
| 목적 | `/dashboard` = 「지금 조치할 것」(상시·자동 갱신) / `/diagnostics` = 「지원팀에 넘길 마스킹된 스냅샷」(요청 시 수집) |
| Entry point | `/dashboard`, `/diagnostics` |
| Expected effect | 번들은 그 시점 운영 상태를 **데이터로** 포함한다(`build_dashboard()` 내장은 의도) |
| **Forbidden** | 번들의 `recent_critical_audit` 슬라이스를 `SENSITIVE_READ_ROLES` 밖에 노출하는 것(`PA-RC-0026` 이 만든 분기) · 번들 페이로드를 화면 정리를 이유로 줄이는 것 |
| Data/API 의존 | `GET /api/admin/dashboard`, `GET /api/admin/diagnostics/bundle` |
| Intent evidence | ① spec §14.7(마스킹된 진단, no secrets/raw journals) · ③ `include_critical_audit` 파라미터 · ⑥ `health/service.py:390` docstring |
| Confidence | Strong — **화면이 번들을 어떻게 보여야 하는지에 대한 명시적 의도는 없다**(그 부분은 INFERRED) |
| 현재 위반 | `PA-RC-0028` (화면이 번들을 그대로 펼쳐 그려 본문 68% 중복) |

## FC-13 · 화면 위치 표시 (breadcrumb ↔ 사이드바)

| 필드 | 값 |
|---|---|
| Actor / Role | 전 역할 |
| 목적 | 사용자가 지금 어느 콘솔의 어느 그룹에 있는지 알려준다 |
| Expected effect | breadcrumb 뿌리 = 현재 **콘솔**, 그다음 = 사이드바 **그룹**, 탭이 있으면 3단(`PA-RC-0017`) |
| **Forbidden** | 일반 사용자에게 「관리자」라고 말하는 것. 사이드바가 말하는 위치와 화면이 말하는 위치가 다른 것 |
| Intent evidence | ⑤ 사용자 콘솔 12화면 중 10화면이 이미 그렇게 한다 · ⑥ `Trash.jsx:173`·`Profile.jsx:449` 가 `crumbRoot` 를 **명시적으로** 넘기는 것은 기본값이 사용자 콘솔에서 틀리다는 것을 알고 있었다는 증거 |
| Confidence | Strong — 기본값을 무엇으로 두어야 하는가는 문서에 없다(INFERRED) |
| 현재 위반 | `PA-RC-0039` (`PageHeader` 기본값이 `"관리자"`), `PA-RC-0031` (그룹 분류 자체가 업무와 어긋남) |

## FC-14 · 목록의 빈 상태 (결과 없음 대 데이터 없음)

| 필드 | 값 |
|---|---|
| Actor / Role | 전 역할 |
| 목적 | 목록이 비었을 때 **왜** 비었는지와 **무엇을 하면 되는지**를 말한다 |
| Allowed state | (a) 필터·검색으로 0건 (b) 데이터 자체가 0건 — **둘은 다른 사실이다** |
| Expected effect | (a) 「조건에 해당하는 ~가 없습니다」 + 필터를 지울 수단 / (b) 무엇이 여기 나타나는지 설명 |
| **Forbidden** | 필터 때문에 비었는데 무조건형(「~가 없습니다」)으로 말하는 것. **기본 필터도 활성 필터로 센다** |
| Intent evidence | ⑤ `/users` 가 (a)를 정확히 구현하고 `/approval-delegations` 가 (b)를 모범적으로 구현한다 · ⑥ `useQueryState` 가 기본값을 주소에 쓰지 않는 규약 |
| Confidence | Strong |
| 현재 위반 | `PA-RC-0038` (`/approvals` 가 (a) 상황에서 (b) 문장을 쓴다) |

## FC-15 · 없는 레코드 요청에 대한 응답

| 필드 | 값 |
|---|---|
| Actor / Role | 전 역할 |
| 목적 | 주소가 가리키는 것이 없으면 그렇다고 말한다(딥링크가 성립하려면 필수) |
| Entry point | 모든 `:id` 상세 라우트(사용자 6 · 관리자 3) |
| Expected effect | 서버 404 → 화면이 공용 `ErrorState`(「찾을 수 없습니다」 + 설명 + 「홈으로」) |
| **Forbidden** | 목록을 대신 그리고 침묵하는 것 · 확정된 404 를 재시도하며 사용자를 기다리게 하는 것 |
| Intent evidence | ③ 서버가 이미 404 를 옳게 답한다(`{"error":{"code":"not_found"}}`) · ⑤ 사용자 콘솔 5종 + `RouteNotFound` 가 공용 표현을 쓴다 |
| Confidence | Strong |
| 현재 위반 | `PA-RC-0033` (관리자 3종 침묵), `PA-RC-0034` (4xx 재시도로 30초 지연) |

## 이 Cycle이 **닫지 못한** UNKNOWN (정직하게)

| 무엇 | 왜 못 닫았나 | 다음에 무엇을 보면 되나 |
|---|---|---|
| `/approvals` 목록의 **범위** | 원시 API 는 다른 사람이 결재자인 건을 돌려주는데 화면은 0건이었다. 「내가 결재자인 건만」인지 「전체」인지 확정하지 못했다 | `app/approvals/` 의 목록 질의와 `principal.scope` 적용 여부. `PA-RC-0038` `acceptance_criteria` (5)가 이것을 요구한다 |
| `change_password` 500 이후 **부분 쓰기** 잔존 여부 | 실패 뒤 DB 상태를 직접 읽어 확인하지 않았다 | `users.password_hash`·`must_change_password`·`sessions` 를 실패 직후 조회. `PA-RC-0032` `acceptance_criteria` (5) |
| 이전 Cycle의 `FC-06`(AI 사용 상한) | 이번 Cycle에서 이 축을 조사하지 않았다 — 근거 등급 ⑥ + 부분 ③, **Probable** 그대로 승계 | 쿼터 소비 시점·경계의 명시적 정책 문서 |
