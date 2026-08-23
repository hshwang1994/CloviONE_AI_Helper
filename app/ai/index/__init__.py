"""색인 파이프라인 — Upload → 원본 저장 → 검사 → Parsing → 구조 추출 → Chunk →
Embedding → Search Ready (MASTER_PLAN §5.4).

전용 `index` worker lane 에서 돈다. 배치·대화형과 분리하는 이유는 하나다 —
**임베딩이 배치 틱을 굶기지 않게** (D-203).
"""
