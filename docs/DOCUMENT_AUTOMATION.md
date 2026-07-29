# DOCUMENT AUTOMATION — 문서 자동화 (spec §19)

Notion 데이터로 보고서류 문서를 생성·발행하는 기능. 핵심 원칙 (spec §19.1):

> **웹 앱은 Notion 토큰을 보유하지 않는다.** 문서 생성/발행은 승인된 n8n
> workflow가 수행하고, 웹 앱은 payload 구성·품질 게이트·승인·이력 관리만 담당한다.

기능 전체는 feature flag `document_automation_enabled`(기본 true,
`feature-flags.json`)로 끌 수 있다.

## 모드 (mode)

| 모드 | 흐름 |
|---|---|
| `preview_only` | preview 생성 → `preview_ready`에서 종료 (발행 없음) |
| `preview_then_approve` | preview → 품질 게이트 통과 시 `awaiting_approval` + `document.publish` 승인 생성 → 승인 시 발행 |
| `auto_publish` | preview → 품질 게이트 통과 시 즉시 publish |

상태: `pending → preview_ready | quality_failed | awaiting_approval | published | failed`.

## 요청과 처리

`POST /api/admin/documents/generate` (admin+, 202) →
`document_generations` 행 생성 + `document_generate` Job enqueue →
worker 핸들러(`app/jobs/handlers/document_generate.py`)가:

1. workflow를 `action="preview"`로 호출해 미리보기 획득
2. 품질 게이트 실행 — 실패 시 `quality_failed`로 **정상 종료**(재시도·발행 없음)
3. 모드에 따라 종료 / 승인 생성 / `action="publish"` 재호출

## config 스키마 (요청 본문의 `config`)

`build_workflow_payload`가 사용하는 키:

```json
{
  "source_database": "프로젝트 DB",
  "filter": {"status": ["진행"]},
  "grouping": null,
  "date_range": "last_week",
  "prompt_template": "weekly-project-report",
  "output_format": "markdown",
  "target_parent_page": "<Notion 페이지 ID>",
  "target_database": null,
  "title_rule": "주간 보고서 {week}",
  "template_id": null, "template_version": 1, "schedule_id": "manual", 
  "period": "(요청 파라미터로 별도 전달)"
}
```

## n8n workflow 계약 (spec §19.6)

### 요청 (웹 → n8n) — preview와 publish 공통 형태

```json
{
  "action": "preview" | "publish",
  "source": {"database": ..., "filter": ..., "grouping": ..., "date_range": ...},
  "prompt_template": "<이름>",
  "output_format": "markdown",
  "target": {"parent_page": ..., "database": ...},
  "title_rule": "<규칙>",
  "requester": {"user_id": ..., "email": ..., "name": ...},
  "content": {"title": ..., "body": ...}
}
```

`content`는 **승인 발행에만 실린다**(`action="publish"`). "이 내용을 그대로 발행하라"는
뜻이며, **workflow는 이때 문서를 다시 생성하지 않고 받은 content를 그대로 발행해야 한다**.
승인은 승인자가 검토한 그 시점의 산출물에 대한 것이므로, 발행 시점에 재생성하면
승인받지 않은 문서가 발행된다.

### preview 응답 (기대)

```json
{"title": "...", "body": "...", "source_row_count": 12, "notion_links": ["https://..."]}
```

### publish 응답 (기대)

```json
{"published_ref": "https://notion.so/...", "title": "..."}
```

## 품질 게이트 (spec §19.5, `app/documents/quality.py`)

preview에 대해 순수 함수 `check_document`가 위반 목록을 반환한다(빈 목록=통과):

- **빈 제목** 금지
- **본문 최소 30자** (`MIN_BODY_LENGTH`)
- **source_row_count ≤ 0 금지** — 소스 데이터 없는 빈 문서 생성 차단
- **민감정보 패턴** 감지 시 차단: 주민등록번호(`\d{6}-\d{7}`), 카드번호 형태(13~16자리),
  `password|secret|api_key = ...` 형태
- **notion_links 검증**: `https://*.notion.so|notion.site`만 유효

위반 시 `quality_failed` + `quality_problems_json`에 사유 저장. **read-back 검증**:
publish 응답에 `published_ref`가 없으면 발행 실패로 처리한다(발행됐다는 증거 없이는
published로 표시하지 않음).

## 발행 승인 (preview_then_approve)

품질 통과 시 `document.publish` 승인(만료 72h)이 생성되고 admin들에게 알림이 간다.
Approvals에서 approve하면 실행기가 `publish_approved` Job을 **1회만**
(idempotency `docpublish:{gen.id}`) 큐에 넣는다. 이 Job은 **다시 렌더하지 않고**
저장된 preview(=승인자가 검토한 그 내용)를 `content`에 실어 `action="publish"`로
호출한다. 자기 승인 금지 규칙 동일 적용.

**왜 재생성하지 않는가**: 승인은 그 시점의 산출물에 대한 것이다. 발행 시점에 다시
만들면 (a) 승인자가 검토한 것과 다른 문서가 발행될 수 있고, (b) 재생성이 품질 게이트에
걸리면 승인은 완료인데 발행만 조용히 사라진다. 발행 실패는 Job 실패로 드러난다 —
generation은 `failed` + 사유가 남고 요청자에게 알림이 간다.

승인 후 발행 Job을 operator가 취소하면 generation은 `failed`로 종결된다
(`awaiting_approval`에 고착되지 않는다).

## 중복 생성 방지 (spec §19.4)

idempotency key: `doc:{schedule_id}:{period}:{target_ref}:v{template_version}`
(`duplicate_key`). 같은 스케줄·기간·대상·템플릿 버전의 재요청은 409
"이미 생성된 문서입니다"로 거부된다. 수동 요청은 schedule_id가 `manual`.

## 예시 템플릿 (비활성 배포)

`EXAMPLE_TEMPLATE`(`app/documents/service.py`) — "[예시] 주간 프로젝트 보고서 (비활성)".
input_schema에 위 config 형태와 `approval_rule: preview_then_approve`가 담겨 있고
`approval_policy.required=true`다. **임의 Notion Write workflow는 자동 생성되지
않는다** — n8n에 문서 생성 workflow를 만들어 연결한 뒤 활성화하는 것이 운영 절차다.

## 조회

- `GET /api/admin/documents` — 생성 이력(모드/상태/품질 문제/발행 링크)
- `GET /api/admin/documents/{id}` — preview 본문 포함 상세 (읽기: operator+/auditor)
