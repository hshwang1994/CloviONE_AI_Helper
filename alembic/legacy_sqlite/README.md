# legacy_sqlite — 비활성 보관 (D-189)

SQLite 시절의 alembic revision **61개**다. **이 디렉터리는 alembic 이 읽지 않는다** —
`alembic.ini` 의 `script_location` 이 `alembic/` 이고 실행되는 것은 `alembic/versions/` 뿐이다.

## 왜 이식하지 않았나

체인을 PG 에서 재생하려 하면 실측된 장애물이 그대로 남는다:

| 장애물 | 수 | PG 에서 무슨 일이 |
|---|---|---|
| boolean `server_default=sa.text("0"\|"1")` | 31곳 | 타입 오류 |
| FTS5 virtual table + trigger DDL (0030 · 0050) | 2 revision | **PG 에 문법 자체가 없다** |
| `sqlite_where=` 부분 유니크 인덱스 | 3개 | **`WHERE` 가 조용히 사라져 전체 유니크가 된다** |
| `recreate="always"` | 3곳 | PG 에서도 전체 테이블 재작성 |
| 0055 의 전제 | 1 | 「SQLite 는 기존 데이터를 새 FK 로 소급 검사하지 않는다」에 의존한다 — PG 에서는 거짓 |

세 번째가 특히 조용하다. 부분 유니크가 전체 유니크가 되면 승인 재요청·프롬프트 두 번째
버전·같은 사용자 두 번째 offboarding 이 전부 막힌다. 에러 메시지는 「이미 있습니다」일 것이고
원인은 마이그레이션 파일 안에 있다.

## 그래서 무엇이 정본인가

`alembic/versions/0001_pg_baseline.py` 하나가 목표 스키마를 만든다. 이후 revision 은 PG 기준으로
새로 쌓는다.

## 이 파일들을 지우지 않는 이유

**S13 Migration Tool 이 운영 SQLite 를 읽는다.** 그 표의 모양(어느 컬럼이 언제 생겼고 무엇을
백필했는지)을 알아야 하는 순간이 오고, 그때 이 61개가 유일한 기록이다. 이관이 끝나면(S14)
함께 정리한다.
