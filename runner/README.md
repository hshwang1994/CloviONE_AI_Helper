# Runner (claude-work-assistant) — 버전관리 사본

서버 `10.100.64.71:/opt/claude-work-assistant/assistant.py`(8789, User=n8n)에서 동작하는 러너의
**버전관리 사본**. n8n 워크플로가 `/v1/assistant/message`로 호출해 사용자 발화를 해석하고
Notion 티켓 조회/생성/변경 결정을 내린다. Claude Code CLI(`/usr/bin/claude`)를 구조화 출력으로 호출.

## #34 Phase 1 변경 (조회 강화)
- `_run_claude()` — CLI 호출 단일 관문(리팩토링)
- `claude_query()` + `QUERY_SCHEMA`/`QUERY_PROMPT` — **자유 질의·요약·집계를 LLM으로 처리**(읽기 전용)
- `is_freeform_query()` / `answer_query()` — freeform은 LLM, 구조화 필터는 기존 `query_tickets`(규칙엔진)
- 실패 시 규칙엔진 fallback, 되묻기(clarification), 참조 티켓/프로젝트 카드 첨부
- 기존 create(claude_draft)·update·확인·컨텍스트 영속·멱등은 **그대로 계승**

## 테스트
```
RUNNER_TOKEN=test python -m pytest runner/claude-work-assistant/test_assistant.py
```
(CLI subprocess 모킹 — 실제 Claude 호출 없음)

## 배포 (러너만 — n8n/플랫폼 변경 없이 조회 강화 반영)
n8n이 이미 projects+tickets를 러너에 넘기고 response_text를 사용자에게 돌려주므로, **이 파일만 교체+서비스 재시작**하면 자유 질의가 동작한다.
```
scp runner/claude-work-assistant/assistant.py cloviradmin@10.100.64.71:~/assistant.py
ssh -t cloviradmin@10.100.64.71 "sudo cp /opt/claude-work-assistant/assistant.py /opt/claude-work-assistant/assistant.py.bak && sudo install -o root -g root -m 0755 ~/assistant.py /opt/claude-work-assistant/assistant.py && sudo python3 -m py_compile /opt/claude-work-assistant/assistant.py && sudo systemctl restart claude-work-assistant && systemctl is-active claude-work-assistant"
```
문제 시 롤백: `sudo cp /opt/claude-work-assistant/assistant.py.bak /opt/claude-work-assistant/assistant.py && sudo systemctl restart claude-work-assistant`
