"""Hybrid Retrieval — 권한이 먼저이고, 셋을 융합하고, 인용을 함께 낸다 (S10 · D-202).

    query.py     세 레인의 SQL 조건 하나씩 (trgm · FTS · vector)
    fusion.py    RRF — 순위 셋을 점수 하나로. Re-rank 는 없다 (D-212 · D-255)
    citation.py  앵커 → 사람이 읽는 인용과 눌러서 갈 수 있는 자리
    service.py   권한 → 후보 → 세 레인 → 융합 → 인용
    answer.py    Context 조립 → `Gateway.generate(task=, data=)`
"""
