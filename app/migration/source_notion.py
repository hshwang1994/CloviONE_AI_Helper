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
# 페이지 하나의 댓글 100 x 20 = 2,000건. 실측 최대는 한 페이지 10건이다.
_MAX_COMMENT_PAGES = 20
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


# 바이트를 들고 있는 블록. 어휘의 정본은 `transform.MEDIA_BLOCKS` 이고 여기서는 그것을
# 읽기만 한다 — 두 벌로 적으면 새 종류를 더한 날 한쪽만 낡는다.
def _media_block_types() -> frozenset[str]:
    from app.migration.transform import MEDIA_BLOCKS

    return MEDIA_BLOCKS


# Notion 서명 주소의 수명은 한 시간이다(`X-Amz-Expires=3600`). 회차 하나가 십 분 넘게
# 걸리므로 여유를 크게 둔다 — 캐시를 읽은 시각과 바이트를 받는 시각이 같지 않다.
MEDIA_CACHE_TTL_SECONDS = 20 * 60


def _has_media(blocks) -> bool:
    kinds = _media_block_types()
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") in kinds:
            return True
        if _has_media(block.get("_children")):
            return True
    return False


def _is_fresh(fetched_at) -> bool:
    """이 캐시를 언제 받았는가. **모르면 안 신선하다.**

    옛 캐시 파일에는 이 값이 없다. 없는 것을 「방금 받았다」로 읽으면 만료된 주소를
    그대로 쓰게 되고, 그것이 정확히 막으려는 상태다.
    """
    if not isinstance(fetched_at, (int, float)):
        return False
    return (time.time() - float(fetched_at)) < MEDIA_CACHE_TTL_SECONDS


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
    # 캐시가 있는데도 다시 받은 수. 이미지가 든 페이지의 서명 주소가 늙었다는 뜻이다.
    blocks_refetched_for_media: int = 0
    comments_fetched: int = 0
    comments_from_cache: int = 0
    comments_seen: int = 0
    bytes_downloaded: int = 0
    databases: dict[str, str] = field(default_factory=dict)
    out_of_scope: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "api_calls": self.api_calls,
            "pages_fetched": self.pages_fetched,
            "blocks_fetched": self.blocks_fetched,
            "blocks_from_cache": self.blocks_from_cache,
            "blocks_refetched_for_media": self.blocks_refetched_for_media,
            "comments_fetched": self.comments_fetched,
            "comments_from_cache": self.comments_from_cache,
            "comments_seen": self.comments_seen,
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
        (self.cache / "comments").mkdir(parents=True, exist_ok=True)
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
        """페이지 본문 블록(중첩 포함). `last_edited` 가 같으면 캐시를 쓴다.

        ## 🔴 이미지가 든 페이지는 캐시가 **늙으면 못 쓴다**

        블록 JSON 안의 파일 주소는 서명이 붙어 있고 한 시간이면 죽는다. `last_edited` 는
        그 사실을 모른다 — 본문이 안 바뀌었으면 몇 주 전 캐시도 「같다」고 답한다. 그
        캐시로 바이트를 받으러 가면 403 이 돌아오고, 보고서에는 「이미지를 못 받았다」만
        남는다. 원인이 만료라는 것은 아무 데도 안 나온다.

        그래서 **파일이 든 페이지만** 나이를 함께 본다. 글자만 있는 페이지는 예전처럼
        캐시를 그대로 쓴다 — 재수집이 십 분 넘게 걸리는 이유가 그쪽 1,200건이다.
        """
        path = self.cache / "blocks" / f"{page_id}.json"
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                cached = None
            if cached and cached.get("last_edited") == last_edited:
                blocks = cached.get("blocks") or []
                if not _has_media(blocks) or _is_fresh(cached.get("fetched_at")):
                    self.stats.blocks_from_cache += 1
                    return blocks
                self.stats.blocks_refetched_for_media += 1

        blocks = self._children(page_id, depth=0)
        self.stats.blocks_fetched += 1
        path.write_text(
            json.dumps(
                {
                    "last_edited": last_edited,
                    "fetched_at": time.time(),
                    "blocks": blocks,
                },
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

    # ── 댓글 ─────────────────────────────────────────────────────────────────

    def page_comments(self, page_id: str, *, refresh: bool = False) -> list[dict]:
        """페이지에 달린 댓글 전부(스레드 답글 포함). **캐시가 있으면 안 받는다** (D11).

        ## 왜 `last_edited` 로 신선도를 안 재는가

        블록 캐시는 페이지의 `last_edited_time` 이 같으면 다시 안 받는다. 댓글에는 그
        규약을 쓸 수 없다 — **댓글이 달려도 페이지의 그 값이 안 움직이는 경우가 있다.**
        내려받아 둔 1,235쪽을 대조해 보면 151쪽 중 5쪽에서 가장 새 댓글이 페이지의
        `last_edited_time` 보다 늦다. 그 값을 신선도로 믿으면 그 5쪽의 댓글을 영원히
        놓치고, 놓쳤다는 사실은 어디에도 안 남는다.

        그래서 규약은 **파일이 있으면 그것이 원장**이다. 다시 받아야 하면 `refresh` 로
        분명히 말한다 — 「혹시 몰라서 매번 받는다」는 1,235회 왕복이고, 그 비용은
        아무도 이 도구를 두 번 안 돌리게 만든다.

        캐시 파일의 모양은 **Notion 이 준 배열 그대로**다. 이미 그 모양으로 1,235개가
        디스크에 있고, 새로 받은 것만 다른 모양으로 적으면 읽는 쪽이 두 규약을 영원히
        알고 있어야 한다.
        """
        path = self.cache / "comments" / f"{page_id}.json"
        if path.exists() and not refresh:
            cached = self._read_comment_cache(path)
            if cached is not None:
                self.stats.comments_from_cache += 1
                self.stats.comments_seen += len(cached)
                return cached

        rows: list[dict] = []
        cursor: str | None = None
        for _ in range(_MAX_COMMENT_PAGES):
            query = f"?block_id={page_id}&page_size={_PAGE_SIZE}" + (
                f"&start_cursor={cursor}" if cursor else ""
            )
            data = self._call("GET", f"/v1/comments{query}")
            rows.extend(
                row for row in data.get("results", []) if isinstance(row, dict)
            )
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        else:
            # 잘린 목록을 캐시에 적으면 그 페이지는 다음 회차에도 잘린 채로 읽힌다.
            raise NotionSourceError(
                f"댓글 {_MAX_COMMENT_PAGES * _PAGE_SIZE}건 상한에 걸렸습니다: {page_id}"
            )
        self.stats.comments_fetched += 1
        self.stats.comments_seen += len(rows)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return rows

    @staticmethod
    def _read_comment_cache(path: Path) -> list[dict] | None:
        """캐시 파일 하나. **모양이 다르면 「댓글이 없다」로 읽지 않는다.**

        빈 목록을 돌려주면 그 페이지는 조용히 이관 대상에서 빠지고, 검증은 「원본에
        댓글이 없었다」로 통과한다. 못 읽으면 `None` 을 내서 다시 받게 한다.
        """
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            logger.warning("댓글 캐시를 읽을 수 없어 다시 받는다: %s", path)
            return None
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        logger.warning("댓글 캐시의 모양이 배열이 아니라 다시 받는다: %s", path)
        return None

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
