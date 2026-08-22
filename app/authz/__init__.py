"""Identity & Access — Permission 모델과 가시성 판정 (S5).

이 패키지가 답하는 질문은 둘이고, 둘은 직교한다.

    무엇을 할 수 있는가   →  permissions.py · models.py · service.py
    무엇이 보이는가       →  resources.py · visibility.py

`app/core/authz.py` 와 헷갈리지 않게: 저쪽은 **역할 그룹 상수**(누가 한 무리인가)의 정본이고,
여기는 그 무리에 **권한(Permission)** 을 붙이고 DB 로 옮긴 층이다. 역할 이름의 목록은
여전히 저쪽 한 곳에만 있다 — 여기서 다시 나열하면 `tests/security/test_authz_single_source.py`
가 잡는다.
"""
