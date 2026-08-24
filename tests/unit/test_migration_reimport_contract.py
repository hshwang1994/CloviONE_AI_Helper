"""「본문만 다시 넣기」의 계약 두 가지 (S14 · D4 · D5).

## 왜 이 둘이 시험할 값어치가 있는가

둘 다 **성공한 것처럼 보이면서 틀리는** 자리다.

1. `reimport-bodies` 가 소스 SQLite 를 받으면 누군가는 언젠가 그것을 함께 돌린다.
   그 회차는 표 63개를 컷오버 시각의 사진으로 덮고, 되돌릴 수 없다. 인자가 없으면
   그 실수가 **아예 불가능**하다.
2. 블록 캐시는 `last_edited_time` 만 본다. 이미지가 든 페이지는 본문이 안 바뀌어도
   그 안의 서명 주소가 한 시간이면 죽는다 — 그 캐시로 바이트를 받으러 가면 403 이고,
   보고서에는 「이미지를 못 받았다」만 남는다.
"""

from __future__ import annotations

import json
import time

import pytest

from app.cli import migrate_cli
from app.migration.source_notion import NotionSource

pytestmark = [pytest.mark.unit]


# ── CLI 계약 (D5) ────────────────────────────────────────────────────────────


def test_reimport_has_its_own_subcommand():
    args = migrate_cli.build_parser().parse_args(["reimport-bodies"])
    assert args.command == "reimport-bodies"
    assert args.func is migrate_cli.cmd_reimport_bodies
    assert args.dry_run is False


def test_reimport_supports_dry_run():
    args = migrate_cli.build_parser().parse_args(["reimport-bodies", "--dry-run"])
    assert args.dry_run is True


def test_reimport_refuses_a_source_snapshot():
    """🔴 표 복사를 함께 돌릴 길 자체가 없어야 한다."""
    with pytest.raises(SystemExit):
        migrate_cli.build_parser().parse_args(
            ["reimport-bodies", "--sqlite", "legacy.sqlite3"]
        )


def test_the_full_run_still_requires_a_source_snapshot():
    """반례. 위 검사가 「인자 이름을 틀렸다」로 통과하지 않게 한다."""
    args = migrate_cli.build_parser().parse_args(
        ["dry-run", "--sqlite", "legacy.sqlite3"]
    )
    assert args.sqlite == "legacy.sqlite3"


# ── 블록 캐시의 나이 (D4) ────────────────────────────────────────────────────


class _CountingSource(NotionSource):
    """`_children` 만 세는 얇은 껍데기. 네트워크는 안 탄다."""

    def __init__(self, cache_dir) -> None:
        super().__init__(
            object(), secret_ref="", cache_dir=cache_dir, throttle_seconds=0,
        )
        self.calls = 0

    def _children(self, block_id: str, *, depth: int):
        self.calls += 1
        return [{"id": "fresh", "type": "paragraph",
                 "paragraph": {"rich_text": []}}]


def _write_cache(source: NotionSource, page_id: str, blocks, *, age_seconds: float):
    (source.cache / "blocks" / f"{page_id}.json").write_text(
        json.dumps({
            "last_edited": "2026-08-20T00:00:00.000Z",
            "fetched_at": time.time() - age_seconds,
            "blocks": blocks,
        }, ensure_ascii=False),
        encoding="utf-8",
    )


_TEXT_ONLY = [{"id": "p", "type": "paragraph", "paragraph": {"rich_text": []}}]
_WITH_IMAGE = [{
    "id": "t", "type": "toggle", "toggle": {"rich_text": []},
    "_children": [{"id": "img", "type": "image",
                   "image": {"file": {"url": "https://old/signed"}}}],
}]


def test_a_text_only_page_still_comes_from_the_cache(tmp_path):
    """글자만 있는 페이지까지 다시 받으면 회차가 십 분 넘게 길어진다."""
    source = _CountingSource(tmp_path)
    _write_cache(source, "page-1", _TEXT_ONLY, age_seconds=60 * 60 * 24 * 30)
    blocks = source.page_blocks("page-1", last_edited="2026-08-20T00:00:00.000Z")
    assert source.calls == 0
    assert blocks[0]["id"] == "p"
    assert source.stats.blocks_from_cache == 1


def test_a_page_with_an_image_is_refetched_when_the_cache_is_old(tmp_path):
    """🔴 서명 주소가 죽은 캐시로 받으러 가면 403 만 돌아온다."""
    source = _CountingSource(tmp_path)
    _write_cache(source, "page-2", _WITH_IMAGE, age_seconds=60 * 60 * 2)
    blocks = source.page_blocks("page-2", last_edited="2026-08-20T00:00:00.000Z")
    assert source.calls == 1, "늙은 이미지 캐시를 그대로 썼다"
    assert blocks[0]["id"] == "fresh"
    assert source.stats.blocks_refetched_for_media == 1


def test_a_page_with_an_image_reuses_a_young_cache(tmp_path):
    """반례. 「이미지가 있으면 무조건 다시 받는다」면 캐시가 있으나 마나가 된다."""
    source = _CountingSource(tmp_path)
    _write_cache(source, "page-3", _WITH_IMAGE, age_seconds=5)
    source.page_blocks("page-3", last_edited="2026-08-20T00:00:00.000Z")
    assert source.calls == 0
    assert source.stats.blocks_from_cache == 1


def test_a_cache_without_a_timestamp_is_never_trusted_for_media(tmp_path):
    """옛 캐시 파일에는 받은 시각이 없다. 모르는 것을 「방금」으로 읽지 않는다."""
    source = _CountingSource(tmp_path)
    (source.cache / "blocks" / "page-4.json").write_text(
        json.dumps({"last_edited": "2026-08-20T00:00:00.000Z", "blocks": _WITH_IMAGE}),
        encoding="utf-8",
    )
    source.page_blocks("page-4", last_edited="2026-08-20T00:00:00.000Z")
    assert source.calls == 1


def test_a_new_fetch_records_when_it_happened(tmp_path):
    """나이를 못 재면 위 규칙이 언제나 「안 신선하다」로 굳는다."""
    source = _CountingSource(tmp_path)
    source.page_blocks("page-5", last_edited="2026-08-20T00:00:00.000Z")
    written = json.loads(
        (source.cache / "blocks" / "page-5.json").read_text(encoding="utf-8")
    )
    assert isinstance(written["fetched_at"], (int, float))
    assert abs(written["fetched_at"] - time.time()) < 60
