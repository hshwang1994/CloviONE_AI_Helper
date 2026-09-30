"""임베딩 Adapter 구현. **밖에서 직접 import 하지 않는다** — `registry.py` 가 고른다.

생성 Adapter 는 여기 없다 - 생성은 AI 런타임(`app/ai/runtime.py`)과 제공자 어댑터(`app/ai/providers/`)가 맡는다
(D-515). 제공자는 원문(사용자·문서에서 온 내용)을 안 받고, 프롬프트 조립과 난스 방어는 런타임이 끝낸 뒤다(D-202).
그 경계는 `scripts/check_domain_single_source.py` 의 「프롬프트 조립」 규칙이 정적으로 지킨다.
"""
