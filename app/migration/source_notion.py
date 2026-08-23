"""Notion 을 읽는다 — 그리고 **읽은 것을 디스크에 남긴다** (S13 · R8).

## 캐시가 성능을 위한 것이 아니다

본문 재수집은 페이지 1,200건이 넘고 Notion 은 초당 3요청으로 제한한다. 즉 한 회차가
**십 분 넘게** 걸린다. 그 사이에 한 번 끊기면 처음부터 다시 받는 구현은 아무도 두 번
돌리지 않게 되고, 안 돌리는 도구는 Cutover 직전 Delta 에서 처음 실패한다.

그래서 받은 것을 디스크에 적고, 다음 회차는 **`last_edited_time` 이 같으면 다시 안
받는다**(R8 이 요구한 delta). 캐시가 없으면 전부 받고, 있으면 바뀐 것만 받는다.

## 데이터베이스 id 를 저장소에 안 적는다

옛 설정의 `notion_tasks_database_id` 는 **문서 DB 를 가리키고 있었고**
`notion_documents_database_id` 는 어느 실재 DB 와도 안 맞았다(INVENTORY 07). 그 값을
믿고 이관하면 잘못된 표에서 1,100건을 읽어 온다.

그래서 **제목으로 찾는다**(`/v1/search`). 제목은 사람이 정한 이름이라 바뀔 수 있지만,
바뀌면 **못 찾았다고 말한다** — 틀린 DB 를 조용히 읽는 것보다 낫다. 이름이 바뀌면
`--database` 로 직접 지정할 수 있다.

## 첨부는 다른 관문으로 나간다

본문·속성은 `api.notion.com` 이고 첨부 바이트는 Notion 이 내주는 임시 S3 주소다. 후자를
런타임 허용 목록에 넣지 않는 이유는 `app/core/allowlist.py` 에 적었다.
"""

from __future__ import annotations

import json
import logging
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from app.core.errors import AppError

logger = logging.getLogger("app.migration.notion")

__all__ = [
    "DB_TASKS", "DB_PROJECTS", "DB_DOCUMENTS", "DB_DOC_TYPES", "DB_CATEGORIES",
    "DATABASE_TITLES", "NotionSourceError", "NotionSource",
]

DB_TASKS = "tasks"
DB_PROJECTS = "projects"
DB_DOCUMENTS = "documents"
DB_DOC_TYPES = "doc_types"
DB_CATEGORIES = "categories"

# 워크스페이스에서 이 제목을 가진 데이터베이스를 찾는다. 제목은 실측(INVENTORY 07)이고
# 앞뒤 공백이 붙어 있는 것이 있어(` 문서 유형 `) 비교 전에 정규화한다.
DATABASE_TITLES: dict[str, str] = {
    DB_TASKS: "작업",
    DB_PROJECTS: "프로젝트",
    DB_DOCUMENTS: "문서",
    DB_DOC_TYPES: "문서 유형",
    DB_CATEGORIES: "카테고리",
}

# 제품 Domain 밖이라 이관하지 않는 셋 (U19). 목록에 두는 이유는 **발견되면 보고서에
# 적기 위해서**다 — 「워크스페이스에 이런 것도 있었다」를 사람이 알아야 다음 결정을 한다.
OUT_OF_SCOPE_TITLES: tuple[str, ...] = (
    "오라클 버그 수정", "휴일 근무 지원내역", "교육 커리큘럼",
)

_API = "https://api.notion.com"
_PAGE_SIZE = 100
_MAX_PAGES = 40          # 100 x 40 = 4,000행 상한. 실측 최대는 1,125행이다.
_MAX_BLOCK_PAGES = 20    # 페이지 하나의 블록 100 x 20 = 2,000블록
_MAX_BLOCK_DEPTH = 3     # 목록 안의 목록까지. 그 아래는 본문이 아니라 구조다.
# 이것은 **정책이 아니라 메모리 보호**다. 첨부의 크기 한도는 제품이 정하고
# (`app/core/uploads.py::MAX_UPLOAD_BYTES` = 10MB), 그 판정은 `store_bytes` 가 한다.
# 여기서 더 좁은 한도를 두면 같은 사실(「너무 크다」)이 두 곳에서 다르게 분류된다 —
# 실제로 그랬다: 34MB 회의 녹음이 **다운로드 실패(blocking)** 로 잡혔는데, 15MB PDF 는
# **업로드 거절(classified)** 로 잡혔다. 같은 이유로 못 옮기는 두 파일이 보고서에서
# 다른 무게를 가지면 사람이 무엇을 결정해야 하는지 못 읽는다.
_MAX_FILE_BYTES = 200 * 1024 * 1024


class NotionSourceError(AppError):
    status_code = 502
    code = "notion_source_error"
    default_message = "Notion 을 읽지 못했습니다."


def _norm(text: str | None) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def _title_of(row: dict) -> str:
    return "".join(
        seg.get("plain_text", "")
        for seg in (row.get("title") or [])
        if isinstance(seg, dict)
    )


@dataclass
class NotionStats:
    """이 회차가 실제로 무엇을 했는가. 보고서가 그대로 싣는다."""

    api_calls: int = 0
    pages_fetched: int = 0
    blocks_fetched: int = 0
    blocks_from_cache: int = 0
    bytes_downloaded: int = 0
    databases: dict[str, str] = field(default_factory=dict)
    out_of_scope: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "api_calls": self.api_calls,
            "pages_fetched": self.pages_fetched,
            "blocks_fetched": self.blocks_fetched,
            "blocks_from_cache": self.blocks_from_cache,
            "bytes_downloaded": self.bytes_downloaded,
            "databases": dict(self.databases),
            "out_of_scope": list(self.out_of_scope),
        }


class NotionSource:
    """조회 전용 Notion 클라이언트 + 디스크 캐시."""

    def __init__(
        self,
        outbound,
        *,
        secret_ref: str,
        cache_dir: str | Path,
        api_version: str = "2022-06-28",
        api_base: str = _API,
        throttle_seconds: float = 0.34,
        sleep=None,
    ) -> None:
        self._outbound = outbound
        self._secret_ref = secret_ref
        self._api_version = api_version
        self._api_base = api_base.rstrip("/")
        # Notion 은 초당 평균 3요청이다. `OutboundClient` 가 429 를 재시도하지만, 맞고
        # 나서 기다리는 것보다 안 맞는 편이 훨씬 빠르다 — 1,200회에서 그 차이가 크다.
        self._throttle = throttle_seconds
        self._sleep = sleep or time.sleep
        self.cache = Path(cache_dir)
        (self.cache / "blocks").mkdir(parents=True, exist_ok=True)
        (self.cache / "files").mkdir(parents=True, exist_ok=True)
        self.stats = NotionStats()

    # ── 낮은 층 ──────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Notion-Version": self._api_version,
            "Content-Type": "application/json",
        }

    def _call(self, method: str, path: str, *, json_body: dict | None = None) -> dict:
        if self.stats.api_calls and self._throttle:
            self._sleep(self._throttle)
        self.stats.api_calls += 1
        try:
            response = self._outbound.request(
                method,
                f"{self._api_base}{path}",
                allowlist="migration",
                json=json_body,
                headers=self._headers(),
                timeout=30.0,
                auth_type="bearer",
                secret_ref=self._secret_ref,
                rate_limit_retries=5,
            )
        except AppError:
            raise
        except Exception as exc:  # 전송 오류
            raise NotionSourceError(f"Notion 호출 실패: {type(exc).__name__}") from exc
        if response.status_code == 401:
            raise NotionSourceError("Notion 토큰이 유효하지 않습니다(401).")
        if response.status_code >= 400:
            raise NotionSourceError(
                f"Notion 응답 오류: HTTP {response.status_code} ({path})"
            )
        return response.json()

    # ── 데이터베이스 찾기 ────────────────────────────────────────────────────

    def discover(self, *, overrides: dict[str, str] | None = None) -> dict[str, str]:
        """제목으로 데이터베이스 id 를 찾는다. **못 찾으면 예외다.**

        조용히 빈 사전을 돌려주면 그 다음 단계가 「행이 0건이다」로 통과한다 — 그것이
        D-213 이 말한 「빈 결과는 통과가 아니다」의 자리다.
        """
        wanted = dict(overrides or {})
        found: dict[str, str] = {}
        by_title: dict[str, str] = {}
        cursor: str | None = None
        for _ in range(_MAX_PAGES):
            body: dict = {
                "filter": {"value": "database", "property": "object"},
                "page_size": _PAGE_SIZE,
            }
            if cursor:
                body["start_cursor"] = cursor
            data = self._call("POST", "/v1/search", json_body=body)
            for row in data.get("results", []):
                if isinstance(row, dict) and row.get("id"):
                    by_title[_norm(_title_of(row))] = row["id"]
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break

        missing: list[str] = []
        for role, title in DATABASE_TITLES.items():
            if role in wanted:
                found[role] = wanted[role]
                continue
            database_id = by_title.get(_norm(title))
            if database_id is None:
                missing.append(f"{role}({title})")
            else:
                found[role] = database_id
        if missing:
            raise NotionSourceError(
                "Notion 워크스페이스에서 데이터베이스를 찾지 못했습니다: "
                + ", ".join(missing)
            )

        self.stats.databases = dict(found)
        self.stats.out_of_scope = [
            title for title in OUT_OF_SCOPE_TITLES if _norm(title) in by_title
        ]
        self._write_cache("databases.json", {
            "found": found, "out_of_scope": self.stats.out_of_scope,
        })
        return found

    # ── 행 ───────────────────────────────────────────────────────────────────

    def query_database(self, database_id: str, *, role: str) -> list[dict]:
        """데이터베이스 하나의 원시 행 전부. 잘렸으면 예외다.

        잘린 채로 넘어가면 그 뒤 검증이 「소스에 없다」로 읽고, 존재하는 티켓을
        「Notion 에서 삭제됨」으로 분류한다. 미러 동기화가 `truncated` 를 두는 이유와
        같은 함정이다.
        """
        rows: list[dict] = []
        cursor: str | None = None
        for _ in range(_MAX_PAGES):
            body: dict = {"page_size": _PAGE_SIZE}
            if cursor:
                body["start_cursor"] = cursor
            data = self._call(
                "POST", f"/v1/databases/{database_id}/query", json_body=body
            )
            rows.extend(row for row in data.get("results", []) if isinstance(row, dict))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        else:
            raise NotionSourceError(
                f"{role}: {_MAX_PAGES * _PAGE_SIZE}행 상한에 걸렸습니다. "
                "잘린 목록으로 이관하면 남은 행이 「원본에서 삭제됨」이 됩니다."
            )
        self.stats.pages_fetched += len(rows)
        self._write_cache(f"{role}.json", rows)
        return rows

    def cached_rows(self, role: str) -> list[dict] | None:
        return self._read_cache(f"{role}.json")

    # ── 본문 블록 ────────────────────────────────────────────────────────────

    def page_blocks(self, page_id: str, *, last_edited: str | None) -> list[dict]:
        """페이지 본문 블록(중첩 포함). `last_edited` 가 같으면 캐시를 쓴다."""
        path = self.cache / "blocks" / f"{page_id}.json"
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                cached = None
            if cached and cached.get("last_edited") == last_edited:
                self.stats.blocks_from_cache += 1
                return cached.get("blocks") or []

        blocks = self._children(page_id, depth=0)
        self.stats.blocks_fetched += 1
        path.write_text(
            json.dumps(
                {"last_edited": last_edited, "blocks": blocks},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return blocks

    def _children(self, block_id: str, *, depth: int) -> list[dict]:
        out: list[dict] = []
        cursor: str | None = None
        for _ in range(_MAX_BLOCK_PAGES):
            query = f"?page_size={_PAGE_SIZE}" + (
                f"&start_cursor={cursor}" if cursor else ""
            )
            data = self._call("GET", f"/v1/blocks/{block_id}/children{query}")
            for block in data.get("results", []):
                if not isinstance(block, dict):
                    continue
                if block.get("has_children") and depth < _MAX_BLOCK_DEPTH:
                    block = dict(block)
                    block["_children"] = self._children(block["id"], depth=depth + 1)
                out.append(block)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return out

    # ── 첨부 ─────────────────────────────────────────────────────────────────

    def download(self, url: str) -> bytes:
        """첨부 바이트. **`external` 링크는 부르는 쪽이 거른다.**

        이 함수는 URL 이 허용 목록에 있는지만 본다 — 그 검사는 `OutboundClient` 가 한다.
        SharePoint 링크처럼 우리가 자격증명을 갖지 않은 주소는 여기 오기 전에 걸러진다.
        """
        host = urlsplit(url).hostname or "?"
        response = self._outbound.get(
            url, allowlist="migration", timeout=60.0,
        )
        if response.status_code >= 400:
            raise NotionSourceError(
                f"첨부를 내려받지 못했습니다: HTTP {response.status_code} ({host})"
            )
        content = response.content
        if len(content) > _MAX_FILE_BYTES:
            # 여기까지 오면 파일 하나가 200MB 를 넘는다. 제품 한도(10MB)와 무관하게
            # 메모리에 들고 있을 수 없는 크기다.
            raise NotionSourceError(
                f"첨부가 메모리 보호 한도를 넘습니다: {len(content)} 바이트 ({host})"
            )
        self.stats.bytes_downloaded += len(content)
        return content

    # ── 캐시 ─────────────────────────────────────────────────────────────────

    def _write_cache(self, name: str, payload) -> None:
        (self.cache / name).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def _read_cache(self, name: str):
        path = self.cache / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            logger.warning("캐시를 읽을 수 없어 무시한다: %s", path)
            return None
