"""옛 SQLite 를 **읽기만** 한다 (S13).

## `mode=ro` 는 예의가 아니라 계약이다

운영 DB 는 WAL 모드로 돌고 있고, 그냥 열면 SQLite 가 체크포인트를 쓸 수 있다. 읽으려고
연 파일이 쓰기로 열리는 것을 막는 것은 주석이 아니라 **URI 플래그**다. 이 파일 밖에서
`sqlite3.connect(path)` 를 부르지 않는다.

운영 파일을 직접 열지 않고 **스냅숏을 열게** 하는 것도 같은 이유다. 스냅숏은
`sqlite3 'file:…?mode=ro' ".backup"` 으로 뜬다 — 그 명령이 원본을 안 건드린다는 것은
S1 이 이미 확인했다.

## 왜 ORM 이 아닌가

옛 스키마의 모델은 이 저장소에 **없다**. S2 가 `alembic/versions/` 를 통째로 갈면서
그 모양은 `alembic/legacy_sqlite/` 로 물러났고, 그것을 다시 매핑하는 것은 「같은 도메인의
두 번째 정의」를 만드는 일이다. 여기서 필요한 것은 행이지 도메인이 아니다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

__all__ = ["SqliteSource"]


class SqliteSource:
    """스냅숏 하나를 읽는다. 컨텍스트 매니저다."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"소스 SQLite 를 찾지 못했습니다: {self.path}")
        # `uri=True` + `mode=ro`. 경로에 `?` 나 `#` 이 있으면 URI 가 깨지므로 `as_uri()` 를
        # 쓴다 — 윈도 경로(`C:\…`)도 이 함수가 옳게 만든다.
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row

    def __enter__(self) -> SqliteSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # ── 스키마 ───────────────────────────────────────────────────────────────

    def tables(self) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        return tuple(row["name"] for row in rows)

    def columns(self, table: str) -> tuple[str, ...]:
        rows = self._conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        return tuple(row["name"] for row in rows)

    def primary_key(self, table: str) -> tuple[str, ...]:
        rows = self._conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        keyed = [(row["pk"], row["name"]) for row in rows if row["pk"]]
        return tuple(name for _order, name in sorted(keyed))

    # ── 행 ───────────────────────────────────────────────────────────────────

    def count(self, table: str) -> int:
        return int(self._conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])

    def rows(self, table: str, *, batch: int = 500) -> Iterator[dict]:
        """행을 사전으로 흘려 준다. **전부 메모리에 올리지 않는다.**

        `audit_logs` 1,401행은 작지만 이 도구는 더 큰 설치에서도 돌아야 한다 —
        한 번에 올리는 구현은 그날 메모리에서 죽고, 죽는 자리는 이관 도중이다.
        """
        cursor = self._conn.execute(f'SELECT * FROM "{table}"')
        while True:
            chunk = cursor.fetchmany(batch)
            if not chunk:
                return
            for row in chunk:
                yield dict(row)

    def select(self, sql: str, params: dict | None = None) -> list[dict]:
        """읽기 질의 하나. 검증이 소스 쪽 수를 세는 데 쓴다."""
        cursor = self._conn.execute(sql, params or {})
        return [dict(row) for row in cursor.fetchall()]
