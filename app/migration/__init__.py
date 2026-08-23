"""Migration Tool — 옛 설치(SQLite + Notion)를 PostgreSQL 로 옮긴다 (S13).

## 이 패키지가 지키는 것 하나

**운영 원본은 읽기만 한다.** SQLite 는 `mode=ro` URI 로 열고(`source_sqlite.py`),
Notion 은 조회만 부른다(`source_notion.py`). 쓰기는 전부 목적지 PostgreSQL 에서만
일어난다 — Dry Run 은 그 목적지가 **임시 데이터베이스**라는 뜻이지, 원본을 만져도
된다는 뜻이 아니다.

## 파이프라인

```
Extract(SQLite + Notion) → Transform → Load(PostgreSQL) → Validate → Report
```

각 단계가 자기 모듈이다. 한 파일에 몰면 「이 값이 어디서 틀어졌나」를 물었을 때
읽어야 할 코드가 전부가 된다.

## 재실행이 설계의 중심이다 (R8)

Notion 본문 재수집은 1,200회가 넘는 외부 호출이고 중간에 끊긴다. 그래서
**같은 입력에 같은 결과**를 두 축으로 보장한다:

  * `legacy_mapping` 이 「옛 식별자 → 우리 식별자」를 들고 있어 두 번째 실행이
    같은 행을 다시 만들지 않는다.
  * 이미 번호를 받은 티켓은 **다시 번호를 매기지 않는다** — `canonical_key` 는
    외부 식별자라 움직이면 옛 링크가 죽는다(D-196 · §5.2).

## 「안 옮기는 것」은 결정이지 누락이 아니다

파생 넷(`document_chunks`·`ai_index_state`·`search_documents`·`rate_limit_buckets`)은
적재하지 않는다. 목록의 정본은 `app/backups/policy.py` 하나다 — 백업이 빼는 목록과
이관이 안 넣는 목록이 갈라지면, Cutover 뒤 첫 복구 리허설이 5단계에서 실패한다.
"""
