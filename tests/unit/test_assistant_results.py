"""도구 결과 봉투를 칸 상한에 맞추기 — `results.fit` (AI 채팅 개선 회차).

예전에는 런타임이 봉투 글을 8,000자에서 글자째 잘라 마지막 항목의 따옴표가 열린 채로 모델에 갔다. 지금은 뒤 항목부터 덜어
`returned` · `truncated` · `note` 를 고치고(모델이 offset 으로 이어 본다), 그래도 넘치면 가장 긴 글 칸을 넘친 만큼 줄인다.
"""

from __future__ import annotations

import json

from app.ai.assistant import results

NOTE = "(결과가 길어 앞부분만 실었습니다.)"


def _envelope(n: int, pad: int = 300) -> str:
    items = [{"ref": f"d{i}", "title": f"문서 {i}", "text": "가" * pad} for i in range(n)]
    return results.ok("search_documents", items, total=50, note="찾아본 낱말: vmware").content


def test_fit_leaves_short_content_alone():
    content = _envelope(2, pad=10)
    assert results.fit(content, 8000, cut_note=NOTE) == content


def test_fit_drops_trailing_items_and_keeps_valid_json():
    content = _envelope(10)
    fitted = results.fit(content, 1500, cut_note=NOTE)
    assert len(fitted) <= 1500
    body = json.loads(fitted)
    assert [i["ref"] for i in body["items"]] == [f"d{i}" for i in range(len(body["items"]))]
    assert 1 <= len(body["items"]) < 10


def test_fit_updates_returned_truncated_and_note():
    body = json.loads(results.fit(_envelope(10), 1500, cut_note=NOTE))
    assert body["returned"] == len(body["items"])
    assert body["truncated"] is True
    assert body["total"] == 50
    assert body["note"].startswith("찾아본 낱말: vmware") and NOTE in body["note"] and "offset" in body["note"]


def test_fit_shrinks_one_huge_item_only_as_much_as_needed():
    content = results.ok("get_document", [{"ref": "d1", "text": "나" * 20_000}]).content
    fitted = results.fit(content, 8000, cut_note=NOTE)
    body = json.loads(fitted)
    assert 7000 < len(fitted) <= 8000, "반으로 자르면 칸을 다 쓰지 않는다"
    assert body["items"][0]["text"].endswith("…")
    assert NOTE in body["note"]


def test_fit_falls_back_to_a_cut_for_non_envelope_text():
    fitted = results.fit("x" * 500, 100, cut_note=NOTE)
    assert len(fitted) <= 100 and fitted.endswith(NOTE)


def test_error_envelopes_are_short_and_untouched():
    content = results.error("my_documents", results.ERROR_NOT_FOUND).content
    assert results.fit(content, 8000, cut_note=NOTE) == content
