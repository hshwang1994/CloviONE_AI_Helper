"""AI Platform — Model Gateway · Parsing · Chunk · Index (S9).

이 패키지의 경계는 하나다: **Business Logic 은 `app/ai/gateway/contract.py` 만 안다**
(D-201). 어떤 모델을, 어떤 런타임으로, 어디에 둔 파일로 부르는지는 전부 그 뒤에 있다.

생성은 D-515 부터 `runtime.py`(AI 런타임) 하나가 맡는다. 채팅, 작업 공간, 주간 요약, 홈 요약, 퀴즈, 연결 확인이
모두 그 문을 지나고, 제공자는 `providers/` 의 어댑터다. Gateway 는 임베딩만 한다. `app/llm/` 에는 프롬프트 안전 틀
(`prompt.py`)만 남았다 - 서버에 로그인된 구독 명령줄 도구 백엔드는 공식 정책상 쓸 수 없어 걷었다.
"""
