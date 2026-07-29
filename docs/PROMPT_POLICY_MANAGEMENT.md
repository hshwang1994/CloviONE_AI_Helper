# PROMPT / POLICY / TEMPLATE 관리 (spec §17)

Prompt(실행기용 프롬프트 본문)와 Policy(JSON 정책)는 **불변 버전 행** 모델을 쓴다:
한 이름(name) 아래 version 1, 2, 3…이 각각 별도 행으로 존재하고
(`UNIQUE(name, version)`), **published된 내용은 절대 덮어쓰지 않는다** (spec §17.1).
공용 로직은 `app/prompts/service.py` — Prompt와 Policy가 동일 수명주기를 공유한다.

## 수명주기

```
draft ──▶ test ──▶ review ──▶ published ──▶ archived
  ▲         │         │
  └─────────┴─────────┘  (반려: test/review → draft)
draft/test/review → archived (폐기)
archived → (전이 없음, 종착)
```

허용 전이는 `VALID_TRANSITIONS`(`app/prompts/models.py`)가 강제한다 —
그 밖의 전이는 409. 규칙:

- **내용 수정은 draft에서만** 가능 (`update_content`)
- **published는 이름당 1개** — 새 버전을 publish하면 기존 published가
  자동으로 `archived`로 전환된다 (삭제·덮어쓰기 아님)
- published에서 할 수 있는 것은 archive뿐

## API (prompts / policies 동일 형태)

`/api/admin/prompts`, `/api/admin/policies` — 읽기는 operator+/auditor,
쓰기는 admin+.

| 작업 | 엔드포인트 |
|---|---|
| 목록/상세 | `GET ""` / `GET /{row_id}` |
| 신규 이름 v1 생성 (draft) | `POST ""` |
| draft 내용 수정 | `PATCH /{row_id}` |
| 상태 전이 | `POST /{row_id}/transition` `{"status": "test"}` |
| 기존 행 기반 새 draft 버전 | `POST /{row_id}/new-version` (version = max+1) |
| 버전 간 diff | `GET /diff/view?name=&from_version=&to_version=` — unified diff 텍스트 |
| 롤백 | `POST /rollback` `{"name": ..., "version": N}` |

Policy 전용 검증: 내용이 **JSON 객체**여야 저장된다(`validate_policy_content`).
Prompt는 자유 텍스트이며 `runner_id`로 대상 실행기를 참조할 수 있다.

## 롤백 = 재발행 (rollback as republish)

`rollback_to_version`은 과거 버전의 **내용을 복사한 새 버전**을 만들고
test → review → published를 즉시 통과시킨다(관리자의 명시적 행위이므로 fast-track).
결과:

- 히스토리는 append-only — "v2로 돌아감"이 아니라 "v2 내용의 v5가 발행됨"
- 기존 published는 규칙대로 자동 archived
- 어떤 시점에 무엇이 발행 상태였는지 감사 추적이 항상 성립

## Automation Template (spec §17.3)

Template은 버전 수명주기가 아니라 단순 활성/비활성 모델이다
(`app/templates/models.py`, `/api/admin/templates`).

| 필드 | 설명 |
|---|---|
| `name` | 고유 이름 |
| `description` | 설명 |
| `input_schema` | 입력 파라미터 정의(JSON) — 문서 자동화 설정 등이 여기 담긴다 |
| `target_type` / `target_ref` | `workflow` 또는 `runner` + 대상 id (**존재 검증**됨) |
| `prompt_id` / `policy_id` | 참조 Prompt/Policy (prompt_id는 존재 검증) |
| `approval_policy` | 승인 정책(JSON, 예: `{"required": true}`) |
| `enabled` | 활성 여부 |

읽기는 operator+/auditor, 생성/수정/활성·비활성은 admin+.
문서 자동화의 예시 템플릿(비활성)은 `docs/DOCUMENT_AUTOMATION.md` 참조.

## 운영 절차 예시 — 프롬프트 개정

1. Prompts에서 현재 published 행 선택 → **new-version** (draft 생성)
2. draft 내용 수정 → transition `test` → 실행 결과 확인 → `review`
3. diff로 published 대비 변경분 검토
4. transition `published` — 이전 버전 자동 archive
5. 문제 발생 시 `rollback`으로 직전 버전 내용을 재발행

모든 전이/수정은 감사 로그에 남는다.
