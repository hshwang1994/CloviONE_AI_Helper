# WORKFLOW REGISTRY — n8n Workflow 관리 (spec §16)

n8n의 webhook workflow를 플랫폼에서 **메타데이터로** 등록·관리한다. n8n 자체(에디터,
workflow 정의)는 무접촉 — 이 레지스트리는 "어떤 webhook을, 어떤 성격으로, 호출해도
되는가"를 선언하는 계층이다. 모든 실제 호출은 `OutboundClient`를 통해
workflows allowlist 검사를 받는다.

## 필드 (`app/workflows/models.py`)

| 필드 | 설명 |
|---|---|
| `name` | 고유 이름 (`notion-user-mapping`은 예약 — `docs/NOTION_MAPPING.md`) |
| `purpose` | 용도 설명 |
| `webhook_url` / `http_method` | 호출 대상 (기본 POST). URL은 **workflows allowlist** 통과 필수 |
| `payload_schema` / `response_schema` | 문서화용 스키마 (선택) |
| `operation_mode` | **`read`** 또는 **`write`** — 부수효과 유무 선언 |
| `approval_required` | write workflow의 자동 실행 승인 요구 여부 |
| `enabled` | 비활성 workflow는 invoke 시 409 `workflow_disabled` |
| `owner`, `tags` | 메타데이터 |
| `last_test_status` / `last_test_at` / `config_version` | 테스트/버전 상태 |

## read/write 모드와 approval_required

- `read`: 조회 전용 — 스케줄 등에서 자유롭게 자동 실행 가능
- `write`: 생성/수정 부수효과 있음. **`approval_required=true`인 write workflow는
  스케줄러가 자동 실행하지 않는다** — `schedule_run` 핸들러가 payload에 승인 표식이
  없으면 영구 실패("승인이 필요한 write workflow는 자동 실행되지 않습니다")로 끝낸다.
  문서 발행처럼 승인 흐름을 통과한 실행만 write가 수행된다

## 테스트는 도달성 확인만 (spec §16.4)

`POST /api/admin/workflows/{id}/test` (operator+) →
`N8nWorkflowProvider.test`:

- webhook URL에 **GET** 요청만 보낸다 — POST webhook에 GET을 보내면 n8n이 404로
  응답하는데, **그 404 자체가 "서비스 살아있음"의 증거**다. 어떤 HTTP 응답이든
  `reachable`, timeout/연결 실패만 `unreachable`
- 따라서 테스트는 **write workflow를 절대 실행시키지 않는다.** 실제 실행 검증이
  필요하면 read workflow를 대상으로 스케줄 dry-run/run-now를 사용한다

결과는 `last_test_status`/`last_test_at`에 기록되어 목록에서 보인다.

## 채팅 workflow (초기 시드)

설치 시 `seed_known_workflows`가 이름 기준 idempotent로 등록한다:

| 항목 | 값 |
|---|---|
| name | `ClovirONE AI 업무 도우미` |
| purpose | 티켓·프로젝트 조회와 생성, 도움말 — 사용자 채팅의 백엔드 workflow |
| webhook_url | `http://127.0.0.1:5678/webhook/clovirone-work-assistant` |
| operation_mode | `write` (티켓 생성 가능) |
| approval_required | `false` — 사용자 대화형 요청은 본인이 직접 지시한 작업이므로 |
| enabled | `true` |

주의: 채팅 핸들러는 URL을 `Settings.n8n_work_assistant_url`에서 직접 읽는다
(레지스트리 조회가 아님). 두 값이 어긋나지 않게 관리한다 — 어느 쪽이든
allowlist(`allowed-workflows.json`, 기본 `127.0.0.1:5678`)는 동일하게 강제된다.

## 버전 관리

Runner와 동일 패턴: 생성/수정마다 `config_versions`(object_type=`workflow`) 스냅샷 +
`config_version` 증가. `GET .../versions` 조회, `POST .../rollback` `{"version": N}`은
스냅샷을 재검증 후 일반 수정 경로로 적용(롤백도 새 버전, 감사 기록).

## 권한

| 작업 | 역할 |
|---|---|
| 목록/상세/버전 | operator, admin, system_admin, auditor |
| 테스트 | operator, admin, system_admin |
| 생성/수정/활성·비활성/롤백 | admin, system_admin |

## 새 workflow 등록 절차

1. n8n에서 webhook workflow 작성, URL 확보 (기존 n8n 관리 절차)
2. URL의 host:port가 `/etc/clovirone-web-assistant/allowed-workflows.json`에 있는지
   확인, 없으면 추가 (즉시 반영)
3. 레지스트리에 등록 — read/write와 approval_required를 **정직하게** 선언
4. 테스트로 도달성 확인 (`reachable`)
5. 스케줄/문서 자동화/매핑 등에서 workflow id로 참조
