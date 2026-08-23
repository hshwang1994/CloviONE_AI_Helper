"""Adapter 구현. **밖에서 직접 import 하지 않는다** — `registry.py` 가 고른다.

Adapter 는 원문(사용자·문서에서 온 내용)을 안 받는다. 프롬프트 조립과 난스 방어는
`contract.Gateway.generate()` 가 이미 끝낸 뒤다(D-202). `scripts/check_ai_prompt_boundary.py`
가 이 경계를 정적으로 지킨다.
"""
