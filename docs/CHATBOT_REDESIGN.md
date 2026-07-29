# Notion 챗봇 재설계 (#34) — 설계 문서

> 목표: 채팅을 **단순 티켓 CRUD**가 아니라, **Notion 정보를 대화로 조회·수정·생성하고 이미지까지
> 다루는 실제 챗봇**으로 재설계. 러너·n8n·플랫폼(웹)까지 일관되게 리팩토링.

## 1. 현재 아키텍처 (실측)

```
[웹 채팅] --POST--> [n8n webhook: clovirone-work-assistant]
   요청: {requester{email,user_id,display_name}, message, conversation_id, message_id}
        |
        v
  n8n: Notion 프로젝트 전체 + 작업 전체 + 작업DB 스키마 조회
        |
        v
  [러너 8789 /v1/assistant/message]  ← 규칙기반 + Claude Code CLI(초안 단계만)
   - 의도 감지(생성/수정/조회/도움말/확인) — 규칙 기반
   - 컨텍스트 영속(sqlite, requester별 대화별, interaction_history 20개)
   - claude_draft(): /usr/bin/claude -p --model … --system-prompt DRAFT_PROMPT (구조화 스키마)
   - 반환: action, response_text, write 필요 여부, write_page_id 등
        |
        v
  n8n: 필요 시 Notion 티켓 생성(POST /v1/pages) / 변경(PATCH /v1/pages/{id})
       → /context/sync → 최종 응답
```
- **Notion DB**: `작업(Tasks)`(대분류·제목·담당자·진행상태·생성/시작/마감일·우선순위·난이도·선/후행·티켓ID·프로젝트) + `프로젝트(Projects)`(진행상태·담당자·기간·우선순위·티켓/프로젝트 진행률·영업·제품·사업구분)
- **자격증명**(재사용): n8n `notionApi`(Notion account), `httpHeaderAuth`(러너). Claude는 서버의 `/usr/bin/claude` CLI.
- **한계**: 티켓 생성/수정/확인 흐름에 결합. 자유로운 조회·집계·복합 질의·이미지 없음. "예상 못한 요청"은 unsupported로 떨어짐.

## 2. 목표 능력 (챗봇)

- **조회**: "이번 주 마감 티켓", "포스코DX 진행률", "내 우선순위 높은 티켓 3개", "지연된 프로젝트", "GIT-1048 상세"
- **수정**: "GIT-1048 진행중으로", "마감 이틀 미뤄", "담당자 문의진으로", "우선순위 올려"
- **생성**: 자연어 → 티켓(제목·프로젝트·담당자·마감·우선순위 자동 추론, 부족분은 되물음)
- **집계·요약**: "이번 주 내 작업 요약", "프로젝트별 미완료 수"
- **이미지**: 캡처/사진 업로드 → (a) 비전으로 내용 추출해 티켓 필드/본문 채움, (b) 원본을 Notion 티켓에 첨부
- **대화 컨텍스트**: 후속 발화("그거 마감 미뤄") 이해, 확인 흐름, 되묻기
- **안전**: 본인 매핑 없으면 본인기준 조회 차단(기존), 쓰기는 확인/승인, 권한 밖 페이지 차단

## 3. 아키텍처 결정 (핵심 갈림길)

### 3.1 러너 방식 — **권장: LLM 에이전트(툴 호출) 로 재작성**
| 옵션 | 장점 | 단점 |
|---|---|---|
| **A. LLM 에이전트(권장)** — Claude가 `query_notion / create_ticket / update_ticket / attach_image / ask_user` 툴을 호출하며 스스로 결정 | "예상 못한 요청"에 유연, 복합질의·집계 자연스러움, 확장 쉬움 | 비결정성·프롬프트 인젝션·비용/지연 관리 필요, 가드레일 필수 |
| B. 규칙기반 확장 | 결정론적·안전 | 새 의도마다 코딩, 챗봇답지 않음, 유지보수 폭증 |

→ **A 권장**. 단, **툴 실행은 화이트리스트**(정해진 Notion DB/필드만), **쓰기는 미리보기+확인**, **본인 권한 범위** 강제. Claude Code CLI(현재 `/usr/bin/claude`) 또는 Anthropic API 중 택1(권장: 기존 CLI 재사용, 이미지·툴은 API가 유리 → §3.3).

### 3.2 이미지 파이프라인 — **권장 흐름**
```
채팅 composer 파일 업로드 → [웹] /api/conversations/{id}/attachments (검증: 타입·크기·개수)
  → 저장: 서버 파일시스템(SECRETS_DIR와 분리된 UPLOADS_DIR, 0640, 사용자별 격리) + DB 메타(attachment 테이블)
  → 메시지에 attachment_id 연결
  → 러너/에이전트에 이미지 전달(base64 또는 서버-내부 URL) → 비전으로 텍스트/필드 추출
  → 티켓 생성 시: 추출 정보로 필드 채우고, 원본 이미지를 Notion 페이지 파일 속성/본문 이미지 블록에 첨부
```
- **결정 필요**: 원본 이미지 저장 위치(우리 서버 보관 vs Notion에만) / 보존기간 / 최대 크기·형식(png,jpg,pdf?).
- 보안: 업로드는 인증·CSRF·타입 스니핑 방지·EXIF 제거·용량 제한. 외부 노출 URL 금지(내부 참조만).

### 3.3 Claude 호출 — 비전·툴 때문에 재검토
- 현재: `/usr/bin/claude` CLI(텍스트, 구조화 스키마). 이미지·멀티툴엔 제약.
- **권장**: 러너를 Anthropic Messages API(툴 사용 + 비전) 기반으로. API 키는 기존 것 재사용(있으면). 없으면 CLI 유지 + 이미지는 별도 OCR.
- **결정 필요**: Anthropic API 키 사용 가능 여부 / 모델(권장 Claude 최신).

## 4. 강건성 — "예상 못한 상황" 체크리스트

- 모호한 지시("그거") → 컨텍스트로 해소, 안 되면 되묻기
- 다중 후보("포스코 티켓") → 후보 목록 제시 후 선택
- 부분 정보 생성 → 부족 필드 되묻기, 임의 생성 금지
- 권한: 남의 티켓/프로젝트 수정 시도 → 매핑/권한 확인, 차단
- 쓰기 오작동 방지 → **미리보기 카드 + 사용자 확인** 후 실제 write(기존 confirm 흐름 계승)
- 이미지에 텍스트 없음/저품질 → 실패 대신 "무엇을 추출할까요?" 되묻기
- Notion API 실패/율제한 → 재시도·명확한 오류 카드
- 프롬프트 인젝션(이미지 속 지시 포함) → 시스템 프롬프트에서 데이터/명령 분리, 툴 화이트리스트
- 대량 조회 → 상위 N + "더 보기"
- 동시 수정 충돌 → 최신값 재확인 후 반영
- 비-Notion 잡담/범위 밖 → 정중히 범위 안내
- 감사: 모든 write를 우리 audit_log + Notion에 기록

## 5. 단계별 구현 계획

1. **플랫폼(웹)**: 이미지 업로드(composer + `/attachments` 엔드포인트 + attachment 테이블 + 격리 저장) · 구조화 카드 렌더 확장(티켓/프로젝트/요약/미리보기-확인) · 대화 컨텍스트를 러너에 전달
2. **러너 재작성(assistant.py)**: LLM 에이전트(툴: query_notion/create/update/attach/ask) + 비전 + 화이트리스트 + 미리보기-확인 + 컨텍스트 영속 계승
3. **n8n 재작성**: 우리 webhook 계약 수신 → 필요한 Notion 데이터 선별 조회 → 러너 호출 → 다중 write_op 실행 → 카드 응답. 기존 `notionApi`/`httpHeaderAuth` 재사용. (신규 JSON 산출 → 사용자 n8n에 import)
4. **검증**: 로컬 결정론 테스트(러너 모킹) + 실서버 스모크 + 안전(권한·인젝션) 테스트

## 6. 확정된 결정 (2026-07-15)

1. **러너 방식**: ✅ **LLM 에이전트로 재작성**. Claude가 툴(query_notion/create_ticket/(2단계)update/attach/ask)을 호출하며 판단. 화이트리스트·미리보기확인·권한제한 가드레일 필수. 기존 규칙 로직(컨텍스트 영속·수동매핑·확인 흐름)은 참고·계승.
2. **Claude 접근**: ✅ **기존 `/usr/bin/claude` CLI 유지**(Anthropic API 키 미사용). 툴/구조화는 CLI로. 이미지 비전은 CLI 지원 여부 확인 → 안 되면 2단계에서 OCR 등 보완.
3. **이미지 정책**: ✅ **원본을 우리 서버에 영구 보관하지 않음.** 티켓 생성 과정에서 (a) 이미지에서 **정보만 추출**해 필드/본문 채움(저장 불필요), (b) 원본을 남겨야 하면 **Notion 페이지에만 첨부**. 티켓 본문은 전체 대화가 아니라 **대화 요약**을 담음(기존 방식 계승) + 필요 시 이미지.
4. **출시 범위**: ✅ **1단계 = 조회(query) + 생성(create)** 먼저 안정화. **2단계 = 수정(update) + 이미지**.

## 7. 1단계 구현 계획 (조회 + 생성, LLM 에이전트 / CLI)

- **선행 조사**: `/usr/bin/claude` 실제 플래그·구조화출력·(이미지 지원?) 확인. 기존 `DRAFT_PROMPT`/`DRAFT_SCHEMA`·`build_page_children`(대화 요약→본문)·컨텍스트 영속·수동매핑 로직 정독(계승 대상).
- **러너(assistant.py) 조회+생성 에이전트화**:
  - 툴: `query_notion(filter)`(작업/프로젝트 화이트리스트 필드만, 본인권한 범위), `draft_ticket(fields)`→미리보기, `create_ticket(confirmed)`→Notion write, `ask_user(question)`.
  - Claude가 사용자 발화+대화컨텍스트+Notion 디렉터리(요약)로 툴 선택. 생성은 **미리보기 카드→확인→write**(기존 confirm 계승).
  - 조회는 read-only(안전). 본인기준 조회는 매핑 필요(기존 차단 계승).
- **n8n 재작성(1단계)**: 우리 webhook 계약 수신 → Notion 조회(필요분) → 러너 호출 → (생성 시) Notion create → 카드 응답. 기존 `notionApi`/`httpHeaderAuth` 재사용. 신규 JSON 산출.
- **플랫폼(웹)**: 조회결과/미리보기/확인 카드 렌더. (이미지 업로드 composer는 2단계.)
- **검증**: 러너 모킹 결정론 테스트 + 실서버 스모크(조회·생성 미리보기) + 권한/인젝션 안전.

## 8. Phase 1 조회(query) — 완료·배포·검증 (2026-07-15)

**결과**: 자유 질의가 실서버에서 지능형으로 동작. 예) "진행중 티켓 중 우선순위 높은 것 3개 요약해줘"
→ 라이브 Notion 데이터로 필터(진행+높음)·정렬·3개 제한·한줄 요약·마감 경과 추론.

**구현**(러너 `runner/claude-work-assistant/assistant.py`): `_run_claude`(CLI 단일 관문),
`claude_query`+`QUERY_SCHEMA`/`QUERY_PROMPT`(freeform LLM 조회, 읽기 전용, 참조 카드, 되묻기),
`is_freeform_query`/`answer_query`(freeform→LLM, 구조화→기존 규칙엔진). create/update/컨텍스트/멱등 계승.

**해결한 버그 3개**:
1. CLI 2.1.x 구조화 출력이 `result`(JSON 문자열)인데 러너는 `structured_output`만 파싱 → claude_draft(생성)도 조용히 fallback. `_run_claude`가 두 형식 모두 파싱.
2. `우선순위` 같은 단어가 `is_update_intent` 오탐 → 조회 가림. freeform 질의를 create 다음·update 이전에 우선 처리.
3. 플랫폼 `_extract_text`의 `_TEXT_KEYS`에 `response_text` 없음 → 모든 응답이 제네릭 "요청이 처리되었습니다"로 표시. `response_text` 최우선 추가.

**테스트**: 러너 6(CLI 모킹), 플랫폼 3. **배포**: 러너=sudo install+restart, 플랫폼 chat_message.py=install+worker restart. n8n은 response_text 정상 포워딩(변경 불요).

**남은 것**: Phase1 생성 e2e 검증(claude_draft 수정됨; Notion write라 주의), Phase2(수정+이미지 Notion 첨부), 채팅 티켓/프로젝트 카드 렌더 강화.
