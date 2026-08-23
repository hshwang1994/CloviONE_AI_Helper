"""AI Platform — Model Gateway · Parsing · Chunk · Index (S9).

이 패키지의 경계는 하나다: **Business Logic 은 `app/ai/gateway/contract.py` 만 안다**
(D-201). 어떤 모델을, 어떤 런타임으로, 어디에 둔 파일로 부르는지는 전부 그 뒤에 있다.

`app/llm/` 과의 관계도 적어 둔다. 그쪽은 주간 리포트 요약 하나를 위한 CLI/API 백엔드고,
S9 는 그것을 **없애지 않고 Adapter 로 감싼다**(`gateway/adapters/claude_cli.py`).
지우면 지금 도는 기능이 멈추고, 두 벌로 두면 프롬프트 방어가 한쪽에만 걸린다.
"""
