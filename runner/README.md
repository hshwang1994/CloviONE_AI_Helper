# Runner (claude-work-assistant) — 버전관리 사본

서버 `10.100.64.71:/opt/claude-work-assistant/assistant.py`(8789, User=n8n)에서 동작하는 러너의
**버전관리 사본**(`APP_VERSION = 3.57.0`). n8n 워크플로와 웹 플랫폼이 호출해 사용자 발화를 해석하고
Notion 티켓 조회/생성/변경 결정을 내린다. Claude Code CLI(`/usr/bin/claude`)를 구조화 출력으로 호출.

## 엔드포인트
- `/v1/assistant/message` — 메인 진입점. `route_request()`가 발화 의도를 라우팅한다. 조회뿐 아니라
  생성/수정(mutate)까지 지원.
- `/v1/assistant/context/sync` — 컨텍스트 영속 동기화. HTTP는 항상 200이지만 저장이 실패하면
  본문이 `{"ok": false, "error": "state_save_failed", ...}`를 돌려준다(성공을 실패로 가리지
  않는다 — `persist_context_result`, `test_a_failed_state_save_is_not_reported_as_ok`).
- `/v1/assistant/quiz` — 팀 놀이용 객관식 퀴즈 생성 전용. `QUIZ_SCHEMA`/`QUIZ_PROMPT`,
  타임아웃 45초(`ASSISTANT_QUIZ_TIMEOUT_SECONDS`).
- `/healthz`(GET) — 헬스체크. `{"status": "ok", "version", "model", "time"}`를 돌려준다.
  배포 스크립트(`dist/deploy-runner.sh`)가 이 버전 값으로 배포 성공을 게이트한다.

## 처리 방식 (하이브리드 rule + claude_query)
- `_run_claude()` — CLI 호출 단일 관문
- 조회: `is_freeform_query()`/`answer_query()`로 freeform은 `claude_query()`+`QUERY_SCHEMA`/`QUERY_PROMPT`(LLM),
  구조화 필터는 `query_tickets`(규칙엔진). 실패 시 규칙엔진 fallback, 되묻기(clarification),
  참조 티켓/프로젝트 카드 첨부.
- 생성/수정: `claude_draft`로 초안 생성, update, 확인, 컨텍스트 영속, 멱등 처리.

## 테스트
```
RUNNER_TOKEN=test python -m pytest runner/claude-work-assistant/test_assistant.py
```
(CLI subprocess 모킹 — 실제 Claude 호출 없음)

## 배포 (러너만 — n8n/플랫폼 무접촉)
이 파일만 교체하고 `claude-work-assistant.service`(8789)만 재시작하면 된다(다른 러너 8787/8788 무접촉).
**정식 경로는 `dist/deploy-runner.sh`** — py_compile 게이트 + `APP_VERSION == EXPECT` 검사 + 타임스탬프
백업 + `n8n:n8n 0644` 설치 + `/healthz` 버전 게이트 + 실패 시 자동 롤백을 한 번에 한다. 배포마다
`assistant.py`의 `APP_VERSION`과 `dist/deploy-runner.sh`의 `EXPECT`를 같은 값으로 올린다.
```
scp runner/claude-work-assistant/assistant.py cloviradmin@10.100.64.71:/home/cloviradmin/deploy-runner-assistant.py
scp dist/deploy-runner.sh cloviradmin@10.100.64.71:/home/cloviradmin/deploy-runner.sh
ssh cloviradmin@10.100.64.71 "sudo bash /home/cloviradmin/deploy-runner.sh"
```
문제 시: 스크립트가 헬스 게이트 실패를 감지하면 백업(`assistant.py.bak-<ts>`)으로 자동 롤백한다.
