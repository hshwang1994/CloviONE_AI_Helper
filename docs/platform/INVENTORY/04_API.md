# INVENTORY 04 — API

**정본**: `app/**/router.py` Source
**측정**: 2026-08-20 (Plan Mode) — **경로별 전량 열거는 S1 이 채운다**

## 측정

| 항목 | 값 |
|---|---|
| Route decorator | **318** |
| Router 모듈 | **45** |
| 프레임워크 | FastAPI (**sync**) · SQLAlchemy (**sync**) |
| Uvicorn | `--workers 1` **고정** (D-192 로 풀린다) |
| Bind | 127.0.0.1:8080 (nginx 뒤) |

## 유지하는 계약 — 재작성하지 않는다

| 계약 | 자리 |
|---|---|
| **Outbound 단일 관문** — SSRF allowlist · secret-ref 주입 · 429-only retry | `app/core/http_client.py::OutboundClient` |
| Scope/Ownership 계산 엔진 | `app/core/scope.py` · `app/core/ownership.py` |
| **Prompt Trust Boundary** — nonce delimiter + `neutralize()` + tool 거부 | `app/llm/prompt.py` |
| Upload 방어 — magic-byte sniffing · traversal guard · RFC 6266 | `app/core/uploads.py` |
| 인증 — argon2id · opaque session + CSRF · lockout · impersonation | `app/auth/**` |
| Error envelope · audit masking · approval executor registry | 전역 |

**Model Gateway 의 HTTP Adapter 는 `OutboundClient` 관문을 그대로 쓴다** — 새 경로를 뚫지 않는다.

## 이번 전환이 API 에 남기는 변화

| 변화 | Session |
|---|---|
| `ticket_view()` 가 `"id": t.page_id`(Notion page-id)를 반환한다 → **UUID + canonical_key 로 교체** | S6 |
| 티켓 폼 허용값이 **요청 시점 Notion 스키마 조회**에서 온다 → 자체 `ticket_statuses` 로 교체 | S6 |
| `notion_version` / `base_notion_version` 이 **공개 API 필드**다 → 순수 도메인 `version` 으로 교체 | S6 |
| `MAX_BLOCKS=100` · `MAX_LINE_CHARS=1900` 이 본문 길이를 거절한다 → **삭제** | S7 |
| 감사 `object_type` 이 Notion 명사다 (`notion_task`·`notion_document`·`notion_token`) | S14 |
| `effective_visibility_clause` 단일화 — 목록·상세·Search·**AI** 가 같은 함수를 쓴다 | S5 |

## 미확인 항목과 Owner

**S1 것은 프로브 하나뿐이다.** 318 decorator 의 전수 열거는 S1 결정에 필요하지 않다.

| 미확인 | Owner | 언제 필요한가 |
|---|---|---|
| `check_scope_gates.py` 의 중첩 라우터 사각지대 (`glob` → `rglob` + 헬퍼 본문 추적) | **S1** (P-01, 우선순위 2) | 공유 헬퍼 안에서 게이트를 지워도 통과한다 — 손으로 확인됐다 |
| 318 decorator 의 **경로 · 메서드 · 권한 게이트 · 소비 화면 전수 표** | **S2 · S5** | PG 이식과 `effective_visibility_clause` 단일화를 실제로 할 때. **미리 열거하지 않는다** |
