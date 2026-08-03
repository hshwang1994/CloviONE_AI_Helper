"""Body-aware fake for the Notion REST API ("작업" tasks database).

Why this exists: ``tests/fakes/http.py::FakeHTTP`` routes on the URL prefix only
and ignores the POST body, so *every* tasks-DB query (mine / unassigned / team)
gets the identical canned rows back. Any golden captured against that fake is a
false baseline — it cannot tell "the filter works" from "the filter is ignored".

``FakeNotionTasksDB`` holds a fixed list of Notion-shaped page rows and actually
interprets the request body: ``filter`` (people.contains / people.is_empty /
date.on_or_after / date.before / date.is_not_empty / select+status equals, with
``and``/``or`` composition), ``sorts``, and cursor pagination at ``page_size``
(default 100, matching Notion). It also serves the endpoints the read paths
touch alongside the query: database schema (GET /v1/databases/{id}), the
relation-target DB used for project titles, single pages, and page children.

The property names it reads are the ones ``app/reports/notion_source.py``
consumes — imported from there rather than duplicated, so a rename in the app
breaks these tests loudly instead of silently drifting.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx

from app.reports.notion_source import (
    PROP_ACT,
    PROP_DIFFICULTY,
    PROP_DUE,
    PROP_EST,
    PROP_PEOPLE,
    PROP_PRIORITY,
    PROP_PROJECT,
    PROP_STATUS,
    PROP_TICKET_ID,
    PROP_TITLE,
)

NOTION_BASE = "https://api.notion.com"
DEFAULT_TASKS_DB = "262c5c5a568481fa9697ee5691cb558d"
DEFAULT_PROJECTS_DB = "projects-db-0001"

# Schema served by GET /v1/databases/{tasks_db}. Shape matches what
# app/tickets/notion_write.py reads (type + options + relation.database_id).
DEFAULT_TASKS_SCHEMA: dict[str, Any] = {
    PROP_TITLE: {"type": "title", "title": {}},
    PROP_STATUS: {
        "type": "status",
        "status": {"options": [
            {"name": "계획"}, {"name": "진행"}, {"name": "검증"},
            {"name": "이슈"}, {"name": "완료"}, {"name": "취소"},
        ]},
    },
    PROP_PRIORITY: {
        "type": "select",
        "select": {"options": [{"name": "높음"}, {"name": "보통"}, {"name": "낮음"}]},
    },
    PROP_DIFFICULTY: {
        "type": "select",
        "select": {"options": [{"name": "1"}, {"name": "3"}, {"name": "5"}]},
    },
    PROP_DUE: {"type": "date", "date": {}},
    PROP_EST: {"type": "number", "number": {"format": "number"}},
    PROP_ACT: {"type": "number", "number": {"format": "number"}},
    PROP_PEOPLE: {"type": "people", "people": {}},
    PROP_TICKET_ID: {"type": "unique_id", "unique_id": {"prefix": "T"}},
    PROP_PROJECT: {"type": "relation", "relation": {"database_id": DEFAULT_PROJECTS_DB}},
}


# ── row builders ──────────────────────────────────────────────────────────────

def task_row(
    *,
    page_id: str,
    tid: int | None = None,
    title: str = "",
    status: str | None = None,
    due: str | None = None,
    people: list[str] | None = None,
    est_wd: float | None = None,
    act_wd: float | None = None,
    difficulty: str | None = None,
    priority: str | None = None,
    project_ids: list[str] | None = None,
    url: str | None = None,
) -> dict:
    """One Notion page in the exact shape ``notion_source._parse_row`` consumes."""
    return {
        "object": "page",
        "id": page_id,
        "url": url or f"https://www.notion.so/{page_id}",
        "properties": {
            PROP_TICKET_ID: {"type": "unique_id",
                             "unique_id": {"prefix": "T", "number": tid}},
            PROP_TITLE: {"type": "title",
                         "title": [{"type": "text", "plain_text": title}] if title else []},
            PROP_STATUS: {"type": "status",
                          "status": {"name": status} if status else None},
            PROP_DUE: {"type": "date", "date": {"start": due} if due else None},
            PROP_PEOPLE: {"type": "people",
                          "people": [{"object": "user", "id": p} for p in (people or [])]},
            PROP_EST: {"type": "number", "number": est_wd},
            PROP_ACT: {"type": "number", "number": act_wd},
            PROP_DIFFICULTY: {"type": "select",
                              "select": {"name": difficulty} if difficulty else None},
            PROP_PRIORITY: {"type": "select",
                            "select": {"name": priority} if priority else None},
            PROP_PROJECT: {"type": "relation",
                           "relation": [{"id": p} for p in (project_ids or [])]},
        },
    }


def project_row(*, page_id: str, name: str, title_prop: str = "이름") -> dict:
    """A row of the relation-target (projects) DB — only its title is read."""
    return {
        "object": "page",
        "id": page_id,
        "url": f"https://www.notion.so/{page_id}",
        "properties": {
            title_prop: {"type": "title",
                         "title": [{"type": "text", "plain_text": name}] if name else []},
        },
    }


# ── write-payload readers ─────────────────────────────────────────────────────
# ``app/tickets/notion_write.property_value`` builds these shapes. The fake reads
# them back so a created/patched page comes out of a later query looking exactly
# like one that had always been there — otherwise a write-through test would be
# asserting against a page the fake invented rather than the one the app sent.

def _w_title(prop) -> str:
    segs = (prop or {}).get("title") or []
    return "".join(
        (s.get("text") or {}).get("content", "") or s.get("plain_text", "")
        for s in segs if isinstance(s, dict)
    )


def _w_named(prop, kind: str) -> str | None:
    container = (prop or {}).get(kind)
    return container.get("name") if isinstance(container, dict) else None


def _w_date(prop) -> str | None:
    date = (prop or {}).get("date")
    return date.get("start") if isinstance(date, dict) else None


def _w_ids(prop, kind: str) -> list[str]:
    return [
        v.get("id") for v in ((prop or {}).get(kind) or [])
        if isinstance(v, dict) and v.get("id")
    ]


# ── filter evaluation ─────────────────────────────────────────────────────────

def _prop(row: dict, name: str) -> dict:
    value = (row.get("properties") or {}).get(name)
    return value if isinstance(value, dict) else {}


def _people_ids(row: dict, name: str) -> list[str]:
    return [p.get("id") for p in (_prop(row, name).get("people") or []) if isinstance(p, dict)]


def _date_start(row: dict, name: str) -> str | None:
    date = _prop(row, name).get("date")
    return date.get("start") if isinstance(date, dict) else None


def _named(row: dict, name: str, kind: str) -> str | None:
    container = _prop(row, name).get(kind)
    return container.get("name") if isinstance(container, dict) else None


def _match_people(row: dict, prop: str, cond: dict) -> bool:
    ids = _people_ids(row, prop)
    if "contains" in cond:
        return cond["contains"] in ids
    if "does_not_contain" in cond:
        return cond["does_not_contain"] not in ids
    if cond.get("is_empty"):
        return not ids
    if cond.get("is_not_empty"):
        return bool(ids)
    raise NotImplementedError(f"people filter not supported by the fake: {cond}")


def _match_date(row: dict, prop: str, cond: dict) -> bool:
    value = _date_start(row, prop)
    if cond.get("is_empty"):
        return value is None
    if cond.get("is_not_empty"):
        return value is not None
    if value is None:
        return False  # Notion never matches a comparison against an empty date
    for key, ok in (
        ("equals", lambda v, o: v == o),
        ("before", lambda v, o: v < o),
        ("after", lambda v, o: v > o),
        ("on_or_before", lambda v, o: v <= o),
        ("on_or_after", lambda v, o: v >= o),
    ):
        if key in cond:
            return ok(value, cond[key])
    raise NotImplementedError(f"date filter not supported by the fake: {cond}")


def _match_named(row: dict, prop: str, cond: dict, kind: str) -> bool:
    value = _named(row, prop, kind)
    if cond.get("is_empty"):
        return value is None
    if cond.get("is_not_empty"):
        return value is not None
    if "equals" in cond:
        return value == cond["equals"]
    if "does_not_equal" in cond:
        return value != cond["does_not_equal"]
    raise NotImplementedError(f"{kind} filter not supported by the fake: {cond}")


def match_filter(row: dict, flt: dict | None) -> bool:
    """Evaluate a Notion filter object against one page row."""
    if not flt:
        return True
    if "and" in flt:
        return all(match_filter(row, f) for f in flt["and"])
    if "or" in flt:
        return any(match_filter(row, f) for f in flt["or"])
    prop = flt.get("property")
    if not prop:
        raise NotImplementedError(f"filter without a property: {flt}")
    if "people" in flt:
        return _match_people(row, prop, flt["people"])
    if "date" in flt:
        return _match_date(row, prop, flt["date"])
    if "status" in flt:
        return _match_named(row, prop, flt["status"], "status")
    if "select" in flt:
        return _match_named(row, prop, flt["select"], "select")
    raise NotImplementedError(f"filter condition not supported by the fake: {flt}")


def _sort_value(row: dict, prop: str):
    """Best-effort scalar for sorting — mirrors the property kinds we serve."""
    raw = _prop(row, prop)
    if "date" in raw:
        return _date_start(row, prop)
    if "number" in raw:
        return raw.get("number")
    for kind in ("status", "select"):
        if kind in raw:
            return _named(row, prop, kind)
    if "title" in raw:
        return "".join(s.get("plain_text", "") for s in (raw.get("title") or []))
    return None


def apply_sorts(rows: list[dict], sorts: list[dict] | None) -> list[dict]:
    """Stable multi-key sort. Empty values always sort last, as Notion does."""
    out = list(rows)
    for spec in reversed(sorts or []):
        prop = spec.get("property")
        if not prop:
            raise NotImplementedError(f"sort without a property: {spec}")
        reverse = spec.get("direction") == "descending"
        filled = [r for r in out if _sort_value(r, prop) is not None]
        empties = [r for r in out if _sort_value(r, prop) is None]
        filled.sort(key=lambda r: _sort_value(r, prop), reverse=reverse)
        out = filled + empties
    return out


# ── the fake itself ───────────────────────────────────────────────────────────

class FakeNotionTasksDB:
    """A body-aware stand-in for the Notion endpoints the read paths call.

    ``always_has_more=True`` makes every query page report ``has_more: True``
    with a fresh cursor, so the caller's page cap (``notion_source._MAX_PAGES``)
    is what stops the loop — that is how truncation behaviour gets exercised.
    ``fail_status`` turns every endpoint into a Notion error response.
    """

    def __init__(
        self,
        rows: list[dict] | None = None,
        *,
        base: str = NOTION_BASE,
        tasks_db: str = DEFAULT_TASKS_DB,
        projects_db: str = DEFAULT_PROJECTS_DB,
        projects: list[dict] | None = None,
        schema: dict | None = None,
        blocks: dict[str, list[dict]] | None = None,
        page_size: int = 100,
        always_has_more: bool = False,
        fail_status: int | None = None,
        fail_message: str = "fake notion failure",
    ) -> None:
        self.rows = list(rows or [])
        self.base = base.rstrip("/")
        self.tasks_db = tasks_db
        self.projects_db = projects_db
        self.projects = list(projects or [])
        self.schema = dict(schema) if schema is not None else dict(DEFAULT_TASKS_SCHEMA)
        self.blocks = dict(blocks or {})
        self.page_size = page_size
        self.always_has_more = always_has_more
        self.fail_status = fail_status
        self.fail_message = fail_message
        # Recorded for assertions: every parsed tasks-DB query body, in order.
        self.queries: list[dict] = []
        # …and every write, so a test can assert what the app actually sent.
        self.created: list[dict] = []
        self.patched: list[tuple[str, dict]] = []
        self._next_seq = 0
        self.created_page_prefix = "fake-created-"
        self.created_tid_base = 9000

    # -- registration ---------------------------------------------------------

    def install(self, fake_http) -> "FakeNotionTasksDB":
        """Register on a ``FakeHTTP`` instance; returns self for chaining."""
        fake_http.on_handler(self.base + "/", self.handle)
        return self

    def handler(self) -> Callable[[httpx.Request], Any]:
        return self.handle

    # -- dispatch -------------------------------------------------------------

    def handle(self, request: httpx.Request):
        if self.fail_status is not None:
            return (self.fail_status, {
                "object": "error", "status": self.fail_status,
                "code": "fake_error", "message": self.fail_message,
            })
        path = request.url.path
        method = request.method.upper()
        if method == "POST" and path == f"/v1/databases/{self.tasks_db}/query":
            return self._query_tasks(self._body(request))
        if method == "POST" and path == f"/v1/databases/{self.projects_db}/query":
            return self._query_projects(self._body(request))
        if method == "GET" and path == f"/v1/databases/{self.tasks_db}":
            return {"object": "database", "id": self.tasks_db, "properties": self.schema}
        if method == "POST" and path == "/v1/pages":
            return self._create_page(self._body(request))
        if method == "PATCH" and path.startswith("/v1/pages/"):
            return self._patch_page(path.rsplit("/", 1)[-1], self._body(request))
        if method == "GET" and path.startswith("/v1/pages/"):
            return self._page(path.rsplit("/", 1)[-1])
        if method == "GET" and path.startswith("/v1/blocks/"):
            return self._children(path.split("/")[3])
        return None  # decline — FakeHTTP falls through to its prefix routes

    @staticmethod
    def _body(request: httpx.Request) -> dict:
        raw = request.content or b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    # -- endpoints ------------------------------------------------------------

    def _query_tasks(self, body: dict):
        self.queries.append(body)
        rows = [r for r in self.rows if match_filter(r, body.get("filter"))]
        rows = apply_sorts(rows, body.get("sorts"))
        return self._paginate(rows, body)

    def _query_projects(self, body: dict):
        rows = [r for r in self.projects if match_filter(r, body.get("filter"))]
        return self._paginate(rows, body)

    def _paginate(self, rows: list[dict], body: dict) -> dict:
        size = min(int(body.get("page_size") or self.page_size), self.page_size)
        offset = self._offset(body.get("start_cursor"))
        page = rows[offset:offset + size]
        if self.always_has_more:
            # Keep handing out rows forever so the *caller's* page cap is what
            # stops the loop — an empty page would end it for the wrong reason.
            if not page and rows:
                page = rows[:size]
            return {"object": "list", "results": page, "has_more": True,
                    "next_cursor": self._cursor(offset + size)}
        has_more = offset + size < len(rows)
        return {
            "object": "list",
            "results": page,
            "has_more": has_more,
            "next_cursor": self._cursor(offset + size) if has_more else None,
        }

    @staticmethod
    def _cursor(offset: int) -> str:
        return f"fake-cursor-{offset}"

    @staticmethod
    def _offset(cursor: str | None) -> int:
        if not cursor:
            return 0
        try:
            return int(str(cursor).rsplit("-", 1)[-1])
        except ValueError:
            return 0

    def _row_from_write(self, page_id: str, tid, props: dict) -> dict:
        """Notion write payload → a query-shaped page row (the fake's whole point)."""
        return task_row(
            page_id=page_id,
            tid=tid,
            title=_w_title(props.get(PROP_TITLE)),
            status=_w_named(props.get(PROP_STATUS), "status"),
            due=_w_date(props.get(PROP_DUE)),
            people=_w_ids(props.get(PROP_PEOPLE), "people"),
            est_wd=(props.get(PROP_EST) or {}).get("number"),
            act_wd=(props.get(PROP_ACT) or {}).get("number"),
            difficulty=_w_named(props.get(PROP_DIFFICULTY), "select"),
            priority=_w_named(props.get(PROP_PRIORITY), "select"),
            project_ids=_w_ids(props.get(PROP_PROJECT), "relation"),
        )

    def _create_page(self, body: dict) -> dict:
        """POST /v1/pages — append a real row so the next query returns it."""
        self.created.append(body)
        self._next_seq += 1
        page_id = f"{self.created_page_prefix}{self._next_seq:04d}"
        row = self._row_from_write(page_id, self.created_tid_base + self._next_seq,
                                   body.get("properties") or {})
        self.rows.append(row)
        return row

    def _patch_page(self, page_id: str, body: dict):
        """PATCH /v1/pages/{id} — merge the sent properties into the stored row.

        ``{"archived": true}`` removes the row, matching Notion: an archived page
        stops appearing in database queries.
        """
        self.patched.append((page_id, body))
        for index, row in enumerate(self.rows):
            if row.get("id") != page_id:
                continue
            if body.get("archived"):
                self.rows.pop(index)
                return {**row, "archived": True}
            merged = {**(row.get("properties") or {})}
            merged.update(body.get("properties") or {})
            tid = ((row.get("properties") or {}).get(PROP_TICKET_ID) or {}).get(
                "unique_id", {}
            ).get("number")
            # ``merged`` already carries every untouched property, so rebuilding
            # from it keeps values the caller did not send.
            updated = self._row_from_write(page_id, tid, merged)
            self.rows[index] = updated
            return updated
        return (404, {"object": "error", "status": 404, "code": "object_not_found",
                      "message": "Could not find page."})

    def _page(self, page_id: str):
        for row in self.rows:
            if row.get("id") == page_id:
                return row
        return (404, {"object": "error", "status": 404, "code": "object_not_found",
                      "message": "Could not find page."})

    def _children(self, page_id: str) -> dict:
        return {"object": "list", "results": self.blocks.get(page_id, []),
                "has_more": False, "next_cursor": None}
