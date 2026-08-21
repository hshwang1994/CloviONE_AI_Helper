# -*- coding: utf-8 -*-
"""S1 / P-04 — VARCHAR(n) 길이 감사.

선언 길이의 정본은 **모델**(`app/models_registry`)이고, 실데이터 길이는 접근 가능한
최신 스냅샷에서 잰다. 둘의 지문을 함께 적는다.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath("."))

from sqlalchemy import String  # noqa: E402

import app.models_registry  # noqa: F401,E402
from app.core.models_base import Base  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else "var/web.sqlite3"

declared: list[tuple[str, str, int]] = []
for table in Base.metadata.sorted_tables:
    for col in table.columns:
        t = col.type
        if isinstance(t, String) and getattr(t, "length", None):
            declared.append((table.name, col.name, int(t.length)))

con = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
con.text_factory = str
live_tables = {r[0] for r in con.execute(
    "select name from sqlite_master where type='table'")}

rows = []
for tbl, colname, n in sorted(declared):
    if tbl not in live_tables:
        rows.append(dict(table=tbl, column=colname, declared=n, rows=None,
                         maxlen=None, over=None, note="table not in snapshot"))
        continue
    cols = {r[1] for r in con.execute('pragma table_info("%s")' % tbl)}
    if colname not in cols:
        rows.append(dict(table=tbl, column=colname, declared=n, rows=None,
                         maxlen=None, over=None, note="column not in snapshot"))
        continue
    q = ('select count(*), coalesce(max(length("%s")),0), '
         'sum(case when length("%s") > %d then 1 else 0 end) '
         'from "%s" where "%s" is not null') % (colname, colname, n, tbl, colname)
    total, maxlen, over = con.execute(q).fetchone()
    rows.append(dict(table=tbl, column=colname, declared=n, rows=total,
                     maxlen=maxlen, over=over or 0, note=""))

out = dict(
    db=DB,
    tables_in_snapshot=len(live_tables),
    declared_varchar_columns=len(declared),
    rows=rows,
)
json.dump(out, open(sys.argv[2] if len(sys.argv) > 2 else "varchar_audit.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=1)

nonempty = [r for r in rows if r["rows"]]
risky = [r for r in nonempty if r["maxlen"] and r["maxlen"] > r["declared"] * 0.5]
print("declared VARCHAR(n) columns: %d" % len(declared))
print("measurable (non-empty tables): %d" % len(nonempty))
print("over-limit rows anywhere: %d" % sum(r["over"] for r in nonempty))
print()
print("%-34s %-30s %6s %8s %8s %6s" % ("table", "column", "n", "rows", "maxlen", "use%"))
for r in sorted(risky, key=lambda r: -(r["maxlen"] / r["declared"])):
    print("%-34s %-30s %6d %8d %8d %5.0f%%" % (
        r["table"], r["column"], r["declared"], r["rows"], r["maxlen"],
        100.0 * r["maxlen"] / r["declared"]))
