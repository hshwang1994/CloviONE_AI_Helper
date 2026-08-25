"""부분 캡처가 전량 라벨 포인터를 옮기지 않는가.

qa-contract-change: collect_evidence 는 부분 실행에서 capture_labels.after 를
--promote 없이 바꾸지 않는다. ROUTE_COVERAGE.json 원본은 이 시험이 쓰지 않는다.
"""

from __future__ import annotations

import pytest

from scripts.collect_evidence import apply_label_pointer, results_are_partial

pytestmark = pytest.mark.unit


def test_partial_scope_is_detected():
    assert results_are_partial({"scope": {"partial": True, "full": False}})
    assert not results_are_partial({"scope": {"partial": False, "full": True}})
    assert not results_are_partial({})  # 옛 파일은 전량으로 본다


def test_partial_run_does_not_move_after_label():
    cov = {"capture_labels": {"after": "w7-after"}}
    moved = apply_label_pointer(
        cov, {"label": "s18-local"}, "after", promote=False)
    assert moved is False
    assert cov["capture_labels"]["after"] == "w7-after"


def test_promote_moves_the_label():
    cov = {"capture_labels": {"after": "w7-after"}}
    moved = apply_label_pointer(
        cov, {"label": "s22-final"}, "after", promote=True)
    assert moved is True
    assert cov["capture_labels"]["after"] == "s22-final"
