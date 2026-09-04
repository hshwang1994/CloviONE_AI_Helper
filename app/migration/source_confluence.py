"""Confluence 를 읽는다 — 그리고 **읽은 것을 디스크에 남긴다** (문서 개편 14~20번).

`source_notion.py` 와 **같은 계약**이다: 조회만 하고, 받은 것을 캐시에 적고, 초당 요청을
스스로 누르고, 바이트는 공용 Outbound Client 를 지난다. 계약을 맞춰 두는 이유는 두
소스가 같은 `runner`·`report`·`validate` 를 쓰기 때문이다 — 한쪽만 다르게 생기면 그
차이를 아는 사람이 코드에만 남는다.

## 인증이 Notion 과 다르다 — 그리고 그 차이가 하루를 먹는다

Atlassian Cloud 는 `이메일:API토큰` **Basic** 만 받는다. Bearer 로 보내면 헤더가
**조용히 무시되고** 익명과 똑같은 403 이 온다(실측: 익명·유효 토큰·아무 문자열 셋이
같은 응답이었다). 그래서 「인증이 틀렸다」가 「권한이 없다」로 보인다. 시크릿 파일은
`이메일:토큰` 한 줄이고, 헤더를 만드는 자리는 `app/core/http_client.py::AUTH_BASIC` 이다.

## 본문은 ADF 로 받는다 — XHTML 을 파싱하지 않는다

`body-format=atlas_doc_format` 은 Atlassian Document Format, 즉 **JSON 노드 트리**다.
우리 본문(ProseMirror)과 어휘가 거의 1:1 이라 변환기가 짧고 정확하다. 저장 포맷
(`storage`)은 매크로가 섞인 XHTML 이라 파서를 새로 들여야 하고, 그 파서가 틀리는
자리는 본문이 잘린 채로 조용히 들어온다 — 이 회차가 고치려는 바로 그 사고다.

## 첨부는 **받기 전에** 크기로 거른다

목록 응답에 `fileSize` 가 들어 있다. 그래서 3MB 이상은 바이트를 한 번도 안 받고
건너뛴다(문서 개편 18번) — 받아 놓고 버리면 231MB 중 큰 것부터 시간을 쓴다.

## 무엇을 안 하는가

동기화를 안 한다(13·20번). 이 파일에는 쓰기 호출이 없고, 주기 실행도 변경 감지도 없다.
한 번 가져오면 그 문서는 ClovirAssist 것이다.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.errors import AppError

__all__ = ["ConfluenceSourceError", "ConfluenceStats", "ConfluenceSource"]

_API = "https://goodmit.atlassian.net"

#: 한 번에 받는 개수. v2 는 커서 페이징이라 상한이 곧 요청 수를 정한다.
_PAGE_SIZE = 250
#: 안전 상한. 실측은 CMP 312 + ClovirONE 212 = 524 쪽이다.
_MAX_PAGES = 60

#: 첨부 하나의 상한. **이 값을 넘으면 받지 않는다**(문서 개편 18번).
#: 제품 업로드 상한(`app/core/uploads.py::MAX_UPLOAD_BYTES`, 10MB)과 **다른 값**이고
#: 다른 뜻이다 — 저것은 「사람이 올릴 수 있는 크기」이고 이것은 「한 번 가져오기가
#: 옮길 크기」다. 같은 상수로 묶으면 한쪽을 고칠 때 다른 쪽이 조용히 따라 바뀐다.
MAX_ATTACHMENT_BYTES = 3 * 1024 * 1024

#: 메모리 보호. 상한 검사를 지난 뒤에도 서버가 더 큰 바이트를 줄 수 있다.
_HARD_BYTE_CEILING = 32 * 1024 * 1024

#: 첨부 주소가 미디어 CDN 으로 넘어갈 때 따라갈 홉 수. 위 머리말의 이유로 **자동 추적이
#: 아니라 새 요청**이고, 그래서 홉마다 allowlist 검사를 다시 지난다.
_MAX_REDIRECT_HOPS = 3


class ConfluenceSourceError(AppError):
    status_code = 502
    code = "confluence_source_error"
    default_message = "Confluence 를 읽지 못했습니다."


@dataclass
class ConfluenceStats:
    """이 회차가 실제로 무엇을 했는가. 보고서가 그대로 싣는다."""

    api_calls: int = 0
    spaces_found: dict[str, str] = field(default_factory=dict)
    pages_listed: int = 0
    pages_by_status: dict[str, int] = field(default_factory=dict)
    blogposts_listed: int = 0
    bodies_fetched: int = 0
    bodies_from_cache: int = 0
    attachments_seen: int = 0
    attachments_too_large: int = 0
    comments_seen: int = 0
    bytes_downloaded: int = 0

    def as_dict(self) -> dict:
        return {
            "api_calls": self.api_calls,
            "spaces_found": dict(self.spaces_found),
            "pages_listed": self.pages_listed,
            "pages_by_status": dict(self.pages_by_status),
            "blogposts_listed": self.blogposts_listed,
            "bodies_fetched": self.bodies_fetched,
            "bodies_from_cache": self.bodies_from_cache,
            "attachments_seen": self.attachments_seen,
            "attachments_too_large": self.attachments_too_large,
            "comments_seen": self.comments_seen,
            "bytes_downloaded": self.bytes_downloaded,
        }


class ConfluenceSource:
    """조회 전용 Confluence 클라이언트 + 디스크 캐시."""

    def __init__(
        self,
        outbound,
        *,
        secret_ref: str,
        cache_dir: str | Path,
        api_base: str = _API,
        throttle_seconds: float = 0.12,
        sleep=None,
    ) -> None:
        self._outbound = outbound
        self._secret_ref = secret_ref
        self._api_base = api_base.rstrip("/")
        # Notion(0.34초)보다 여유롭다 — Atlassian 의 제한이 훨씬 느슨하다. 그래도 0 은
        # 아니다: 524쪽 × (본문+첨부+댓글) 이면 1,600 요청이고, 제한에 걸린 뒤 기다리는
        # 것보다 안 걸리는 편이 빠르다.
        self._throttle = throttle_seconds
        self._sleep = sleep or time.sleep
        self.cache = Path(cache_dir)
        (self.cache / "confluence" / "bodies").mkdir(parents=True, exist_ok=True)
        (self.cache / "confluence" / "attachments").mkdir(parents=True, exist_ok=True)
        (self.cache / "confluence" / "comments").mkdir(parents=True, exist_ok=True)
        self.stats = ConfluenceStats()

    # ── 낮은 층 ──────────────────────────────────────────────────────────────

    def _call(self, path: str) -> dict:
        """GET 하나. **이 클래스에 다른 메서드는 없다** — 쓰기 경로 자체를 안 만든다."""
        if self.stats.api_calls and self._throttle:
            self._sleep(self._throttle)
        self.stats.api_calls += 1
        url = path if path.startswith("http") else f"{self._api_base}{path}"
        try:
            response = self._outbound.request(
                "GET", url,
                allowlist="migration",
                headers={"Accept": "application/json"},
                timeout=30.0,
                auth_type="basic",
                secret_ref=self._secret_ref,
                rate_limit_retries=5,
            )
        except AppError:
            raise
        except Exception as exc:  # 전송 오류
            raise ConfluenceSourceError(
                f"Confluence 호출 실패: {type(exc).__name__}"
            ) from exc
        if response.status_code in (401, 403):
            # 🔴 이 두 상태를 **구별해서 말한다.** Atlassian 은 헤더가 무시됐을 때도
            # 403 을 주므로, 그냥 「권한이 없다」로 적으면 토큰 문제를 권한 문제로 읽는다.
            raise ConfluenceSourceError(
                f"Confluence 인증에 실패했습니다(HTTP {response.status_code}). "
                "시크릿이 «이메일:API토큰» 한 줄인지, 그 계정에 Confluence 접근 권한이 "
                "있는지 확인해 주세요."
            )
        if response.status_code >= 400:
            raise ConfluenceSourceError(
                f"Confluence 응답 오류: HTTP {response.status_code} ({path})"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ConfluenceSourceError(f"Confluence 응답이 JSON 이 아닙니다: {path}") from exc

    def _paged(self, path: str, *, what: str) -> list[dict]:
        """커서 페이징 전부. **잘렸으면 예외다.**

        잘린 채로 넘어가면 그 뒤 대조가 「원본에 없다」로 읽고, 존재하는 페이지를
        「가져올 것이 없었다」로 분류한다. 그 침묵이 이 회차가 고치려는 사고의 모양이다.
        """
        rows: list[dict] = []
        url = path
        for _ in range(_MAX_PAGES):
            data = self._call(url)
            rows.extend(r for r in (data.get("results") or []) if isinstance(r, dict))
            nxt = ((data.get("_links") or {}).get("next")) or ""
            if not nxt:
                return rows
            url = nxt if nxt.startswith("http") else f"{self._api_base}{nxt}"
        raise ConfluenceSourceError(
            f"{what}: {_MAX_PAGES}쪽 상한에 걸렸습니다. 잘린 목록으로 가져오면 "
            "남은 페이지가 「원본에 없었다」가 됩니다."
        )

    # ── 캐시 ─────────────────────────────────────────────────────────────────

    def _cache_path(self, kind: str, name: str) -> Path:
        return self.cache / "confluence" / kind / f"{name}.json"

    def _read_cache(self, kind: str, name: str):
        path = self._cache_path(kind, name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_cache(self, kind: str, name: str, payload) -> None:
        try:
            self._cache_path(kind, name).write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            # 캐시는 편의다. 못 적어도 회차는 계속 돈다.
            pass

    # ── Space 와 페이지 ──────────────────────────────────────────────────────

    def find_spaces(self, keys: list[str]) -> dict[str, str]:
        """Space key → id. **못 찾으면 예외다** (D-213: 빈 결과는 통과가 아니다)."""
        found: dict[str, str] = {}
        for key in keys:
            rows = self._paged(
                f"/wiki/api/v2/spaces?keys={key}&limit=50", what=f"space({key})"
            )
            match = next((r for r in rows if r.get("key") == key), None)
            if match is None or not match.get("id"):
                raise ConfluenceSourceError(
                    f"Confluence 에서 Space 를 찾지 못했습니다: {key}"
                )
            found[key] = str(match["id"])
        self.stats.spaces_found = dict(found)
        self._write_cache("bodies", "_spaces", found)
        return found

    def list_pages(self, space_id: str, *, space_key: str) -> list[dict]:
        """그 Space 의 **모든** 페이지 — 계층과 무관하게 평평한 한 목록이다.

        `status` 를 안 건다. 기본값은 보관된(archived) 페이지를 빼는데, 요구는 「CMP 에
        존재하는 모든 문서」다(14번) — 실측으로 CMP 3건 · ClovirONE 2건이 보관 상태이고,
        그 다섯을 조용히 빼면 「전부 가져왔다」가 거짓이 된다.

        하위 페이지를 따로 훑지 않는 이유: 이 입구가 이미 Space 안의 모든 깊이를 준다
        (실측 524쪽 중 root 는 7쪽뿐이고 나머지 517쪽이 하위다).
        """
        rows = self._paged(
            f"/wiki/api/v2/spaces/{space_id}/pages"
            f"?limit={_PAGE_SIZE}&status=current&status=archived",
            what=f"pages({space_key})",
        )
        for row in rows:
            row["_space_key"] = space_key
            status = str(row.get("status") or "unknown")
            self.stats.pages_by_status[status] = self.stats.pages_by_status.get(status, 0) + 1
        self.stats.pages_listed += len(rows)
        self._write_cache("bodies", f"_pages_{space_key}", rows)
        return rows

    def list_blogposts(self, space_id: str, *, space_key: str) -> list[dict]:
        """블로그 글. 실측은 두 Space 다 **0건**이지만 세어서 보고한다 —
        「0이었다」와 「안 봤다」는 다른 사실이다."""
        rows = self._paged(
            f"/wiki/api/v2/spaces/{space_id}/blogposts?limit={_PAGE_SIZE}",
            what=f"blogposts({space_key})",
        )
        self.stats.blogposts_listed += len(rows)
        return rows

    def author_name(self, account_id: str | None) -> str:
        """Atlassian 계정 id → **표시 이름.** 못 받으면 빈 문자열이다.

        🔴 이메일이 아니라 이름만 받는다. 실측: 작성자 8명 중 이메일을 주는 것은 1명뿐이고
        (나머지는 프로필 공개 설정이 막는다) 그 하나도 우리 계정에 없다. 즉 Confluence
        작성자를 우리 계정으로 **이을 수 없다.** 그렇다고 실행 계정을 작성자로 적으면
        화면이 「이 관리자가 524건을 썼다」고 거짓말한다 — 이름이라도 남기는 것이 답이다.

        서로 다른 작성자는 23명뿐이라(실측) 한 회차에 스물 몇 번 부르고 캐시에 남는다.
        """
        key = (account_id or "").strip()
        if not key:
            return ""
        cached = self._read_cache("users", key)
        if cached is not None:
            return str(cached.get("name") or "")
        name = ""
        for path in (f"/wiki/rest/api/user?accountId={key}",
                     f"/rest/api/3/user?accountId={key}"):
            try:
                data = self._call(path)
            except ConfluenceSourceError:
                continue
            name = str(data.get("publicName") or data.get("displayName") or "").strip()
            if name:
                break
        # 못 받아도 캐시에 적는다 — 다음 회차가 같은 실패를 다시 사지 않게.
        self._write_cache("users", key, {"name": name})
        return name

    def page_body(self, page_id: str, *, version: int | None = None) -> dict:
        """한 페이지의 ADF 본문과 판 정보. 판 번호가 같으면 캐시를 쓴다."""
        cached = self._read_cache("bodies", str(page_id))
        if cached and version is not None and cached.get("_version") == version:
            self.stats.bodies_from_cache += 1
            return cached
        data = self._call(
            f"/wiki/api/v2/pages/{page_id}?body-format=atlas_doc_format"
        )
        raw = ((data.get("body") or {}).get("atlas_doc_format") or {}).get("value") or ""
        try:
            adf = json.loads(raw) if raw else {"type": "doc", "content": []}
        except ValueError:
            # 본문을 못 읽었으면 **빈 본문으로 넘기지 않는다.** 빈 본문은 「원본이
            # 비어 있었다」와 구별되지 않고, 그 혼동이 이 회차가 고치는 사고다.
            raise ConfluenceSourceError(
                f"Confluence 본문(ADF)이 JSON 이 아닙니다: page {page_id}"
            ) from None
        out = {
            "_version": (data.get("version") or {}).get("number"),
            "id": data.get("id"),
            "title": data.get("title"),
            "status": data.get("status"),
            "parentId": data.get("parentId"),
            "spaceId": data.get("spaceId"),
            "version": data.get("version") or {},
            "authorId": data.get("authorId"),
            "createdAt": data.get("createdAt"),
            "adf": adf,
        }
        self.stats.bodies_fetched += 1
        self._write_cache("bodies", str(page_id), out)
        return out

    def page_attachments(self, page_id: str) -> list[dict]:
        """첨부 **목록**. 바이트는 안 받는다 — 크기로 거르는 판단이 먼저다."""
        rows = self._paged(
            f"/wiki/api/v2/pages/{page_id}/attachments?limit={_PAGE_SIZE}",
            what=f"attachments({page_id})",
        )
        self.stats.attachments_seen += len(rows)
        self._write_cache("attachments", str(page_id), rows)
        return rows

    def page_comments(self, page_id: str) -> list[dict]:
        """바닥 댓글과 인라인 댓글을 한 목록으로. 실측은 바닥 15건 · 인라인 0건이다."""
        out: list[dict] = []
        for kind in ("footer-comments", "inline-comments"):
            rows = self._paged(
                f"/wiki/api/v2/pages/{page_id}/{kind}"
                f"?limit={_PAGE_SIZE}&body-format=atlas_doc_format",
                what=f"{kind}({page_id})",
            )
            for row in rows:
                row["_kind"] = kind
            out.extend(rows)
        self.stats.comments_seen += len(out)
        self._write_cache("comments", str(page_id), out)
        return out

    # ── 바이트 ───────────────────────────────────────────────────────────────

    def download(self, download_link: str, *, declared_size: int | None = None) -> bytes | None:
        """첨부 하나의 바이트. **상한을 넘으면 `None`** 이고 그것은 실패가 아니다.

        크기를 목록에서 먼저 보고 거르므로, 3MB 짜리 하나 때문에 그 문서의 본문·댓글·
        다른 첨부가 함께 죽는 일이 없다(문서 개편 18번).
        """
        if declared_size is not None and int(declared_size) >= MAX_ATTACHMENT_BYTES:
            self.stats.attachments_too_large += 1
            return None
        url = download_link
        if not url.startswith("http"):
            # v2 의 `downloadLink` 는 `/rest/api/content/.../download` 같은 상대 주소다.
            url = f"{self._api_base}/wiki{url}" if not url.startswith("/wiki") \
                else f"{self._api_base}{url}"
        response = None
        for hop in range(_MAX_REDIRECT_HOPS + 1):
            if self.stats.api_calls and self._throttle:
                self._sleep(self._throttle)
            self.stats.api_calls += 1
            try:
                response = self._outbound.request(
                    "GET", url,
                    allowlist="migration",
                    timeout=120.0,
                    # 🔴 미디어 CDN 의 주소는 **서명 토큰을 자기 안에 들고** 있다. 거기에
                    # Basic 헤더를 다시 붙이면 Atlassian 이 그 조합을 거절한다. 그래서
                    # 첫 홉만 인증을 붙이고 뒤는 안 붙인다.
                    auth_type=("basic" if hop == 0 else "none"),
                    secret_ref=(self._secret_ref if hop == 0 else None),
                    rate_limit_retries=3,
                )
            except AppError:
                raise
            except Exception as exc:
                raise ConfluenceSourceError(
                    f"첨부를 받지 못했습니다: {type(exc).__name__}"
                ) from exc
            if response.status_code not in (301, 302, 303, 307, 308):
                break
            location = response.headers.get("Location") or ""
            if not location:
                raise ConfluenceSourceError(
                    f"첨부가 {response.status_code} 로 넘어가는데 Location 이 없습니다."
                )
            # 새 요청이라 allowlist 를 **다시** 지난다 — 자동 추적을 켜면 그 검사가 사라진다.
            url = location
        else:
            raise ConfluenceSourceError(
                f"첨부 주소가 {_MAX_REDIRECT_HOPS}번 넘게 넘어갑니다."
            )
        if response.status_code >= 400:
            raise ConfluenceSourceError(
                f"첨부 응답 오류: HTTP {response.status_code}"
            )
        payload = response.content
        # 🔴 목록이 크기를 말했는데 0바이트를 받았으면 그것은 「빈 파일」이 아니라
        # **실패**다. 조용히 넘기면 「못 가져왔다」가 「원래 없었다」와 같은 모양이 된다 —
        # 실측에서 첨부 1,458개가 정확히 그렇게 사라졌다.
        if declared_size and not payload:
            raise ConfluenceSourceError(
                f"첨부가 {declared_size}바이트라는데 0바이트를 받았습니다."
            )
        if len(payload) >= MAX_ATTACHMENT_BYTES:
            # 선언한 크기가 거짓이었다. 받고 나서라도 버린다 — 상한의 뜻은 「저장하지
            # 않는다」이지 「묻지 않는다」가 아니다.
            self.stats.attachments_too_large += 1
            return None
        if len(payload) > _HARD_BYTE_CEILING:  # pragma: no cover - 위에서 이미 걸린다
            raise ConfluenceSourceError("첨부가 메모리 상한을 넘었습니다.")
        self.stats.bytes_downloaded += len(payload)
        return payload
