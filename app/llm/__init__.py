"""LLM 요약 (§L) — 서버에 로그인된 **구독 CLI** 를 부른다.

층은 넷이다. 위에서 아래로 부르고, 아래는 위를 모른다.

    prompt.py       무엇을 보내는가 (순수 함수. 프로세스도 네트워크도 모른다)
    cli_backend.py  구독 CLI 를 어떻게 띄우는가 (subprocess, argv 고정, stdin)
    api_backend.py  같은 일을 API 로 (전환용. 지금은 꺼져 있다)
    service.py      워커에서 한 번에 하나만, 실패하면 규칙 기반으로 (예외를 안 던진다)
    provider.py     인터페이스 + 어느 백엔드를 쓸지 고르기 + 결과 어휘

여기에 `__init__` 이 아무것도 import 하지 않는 이유: `app.llm.prompt` 하나만 쓰는
순수 테스트가 subprocess 나 httpx 를 끌고 오지 않게 하려고. 층을 나눈 이유가 그거다.
"""
