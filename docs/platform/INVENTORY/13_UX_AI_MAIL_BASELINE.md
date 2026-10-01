# 13. UI/UX · AI · 조직 · 초기 설정 · 메일 회차의 기준선 (P0)

> 측정 2026-10-01, 랩 운영 설치 `10.100.64.71`(배포 `5aadfbb6`, alembic `0041_ai_policies`), **읽기 전용**.
> 계획 정본: `C:/Users/hshwa/.claude/plans/pasted-content-id-c7b8-clovirassist-ui-cheerful-wozniak.md` 의 P0.
> 질의는 `psql`(postgres 계정) `SELECT` 만 썼고 설정 값 중 비밀은 읽지 않았다(키 이름과 비밀이 아닌 값만).
> 메일 구성 요소와 망 점검은 [`../EVIDENCE/mail/2026-10-01-lab-preflight.md`](../EVIDENCE/mail/2026-10-01-lab-preflight.md) 에 따로 둔다.

## AI — 채팅이 답을 못 하는 까닭을 데이터로 확인했다

| 항목 | 값 |
|---|---|
| AI 설정 | 제공자 `openai`, 인증 `chatgpt`, 모델 `gpt-5.5`, `ai_generation_enabled=true`, 홈 문장 요약 · 게임 퀴즈 켜짐, `chat_enabled` 는 행 없음(기본 켜짐) |
| 연결 상태(`ai_credential_state`) | `openai/chatgpt = ok`, 최근 확인 · 최근 성공 10-01 05:05 UTC, 연속 실패 0 |
| 사용 기록 60일(`ai_usage_records`) | `chat.answer` ok 38(마지막 08-16 — 0039 가 옮긴 옛 기록), `home.narrative` ok 2, `system.connection_test` ok 1(10-01 05:05). 전체 41행 중 40행은 제공자가 비어 있다(0039 이관분) |
| 채팅 메시지 60일 | 도우미 `done` 66, 사용자 `done` 56, 사용자 `failed` 4(`assistant_error` 3 · 08-16, `assistant_disabled` 1 · 08-31) |
| 고정 거절 답 | 「질문에 답할 근거를 사내 문서에서 찾지 못했습니다…」 18건, 마지막 10-01 05:05 |
| 잡 30일 | `chat_message` succeeded 10 |

**결론(계획 A1 ② 를 실측으로 확인)**: 연결은 정상인데, 새 런타임으로 바뀐 뒤 `chat.answer` 호출 기록이 한 건도 없다.
채팅 잡은 「성공」으로 끝나지만 문서 검색이 0건이라 모델을 부르지 않고 고정 거절 답을 저장했다. 연결 확인 성공과 채팅 성공은 서로 무관했다.

| 검색 재료 | 값 |
|---|---|
| 문서 조각(`document_chunks`) | 2,237 |
| 임베딩이 있는 조각 | 0 — 의미 검색 레인은 돌지 않고 낱말 레인(트라이그램 · FTS)만 돈다 |
| 대화(`conversations`) | 92, 그중 63 이 옛 실행기 대화 id(`backend_conversation_id`)를 갖는다 — 0046 에서 열을 지운다 |

## 프롬프트 · 정책 — 0044 · 0046 이 바꿀 행

| 분류(계획 A7) | 랩 행 수 | 처리 |
|---|---|---|
| 프롬프트: 사용처 없음 · 보관 · 시드 내용 | 3 — 셋 다 `created_by` 가 있다 | 「죽은 시드」가 아니다(만든 사람 있음). 「관리자가 쓴 연결 없는 보관본」으로 그대로 둔다 |
| 프롬프트: 죽은 시드(만든 사람 없음 · 참조 없음) | **0** | 0046 이 지울 행이 랩에는 없다 |
| 정책: 업그레이드가 옮긴 초안 | 3 — 승인 `["workspace.draft"]`, 응답 제한 `["*"]`, 개인정보 가리기 `["*"]` | 그대로(정책 화면 메시지 상자에 「아직 적용되지 않은 초안 3건」) |
| 정책: 옛 형식 원본(`kind='legacy'`, 보관) | 2 | API 기본에서 숨긴다 |
| 정책: 발행본 | **0** — 지금 걸린 정책이 없다 | — |
| 0044 의 대상 옮기기(`chat.answer` · `workspace.ask` → `assistant.chat`) | 바꿀 행 0 | 회귀 시험으로만 지킨다 |
| `usage_events` 의 `ai.call` | 40 | 0039 가 이미 옮겼다. 0046 이 지운다 |

## 메일 — 한 번도 설정한 적이 없다

| 항목 | 값 |
|---|---|
| `smtp` 설정 행 | 없음 |
| `allowed_email_domains` 설정 행 | 없음 |
| 발송 기록 | 승인 요청 14 · 백업 실패 89 · 초대 2, **전부 `unconfigured`** |
| 실패 문장 | 「메일 발송이 꺼져 있습니다. 메일 설정에서 발송을 켜세요. / 메일 서버 주소가 비어 있습니다. / 보내는 사람 주소가 비어 있습니다.」 |
| `sync_status` 의 메일 행 | 없음 |
| 비밀 디렉터리 파일 이름 | `assistant_runner_token` · `confluence_token` · `game_runner_token` · `notion_docs_token` · `notion_report_token` · `smb_matrix` — SMTP 비밀번호 파일 없음 |

## 화면 기준선

- `ux-before` 캡처: 계획 8.2 의 17개 화면 × 1366×768 · 1600×900 · 1920×1080 · 2560×1440(라이트), 결과 `dist/ui-qa/ux-before/`.
- 자연어 검색 기준 측정은 P8 을 시작할 때 같은 코드로 잰다. 검색 코드는 P8 전까지 바뀌지 않으므로 그때 잰 값이 이 기준선이다.

## 미확인 항목과 Owner

| 항목 | Owner |
|---|---|
| ChatGPT 요금제가 함수 도구를 받는지 | P10 연결 확인의 도구 시험 · P18 랩 E2E |
| 바깥 25번으로 Exchange Online 이 이 서버의 메일을 받아 주는지(PTR 없음) | P18 E2E-3 |
