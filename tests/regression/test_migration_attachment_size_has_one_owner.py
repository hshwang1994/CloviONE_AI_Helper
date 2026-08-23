"""같은 사실을 두 곳이 다르게 분류하지 않는다 — 첨부 크기 (S13).

## 실 회차가 드러낸 것

운영 데이터로 Dry Run 을 돌렸더니 첨부 아홉 중 둘이 못 넘어왔는데, **둘의 무게가
달랐다**:

| 파일 | 크기 | 그때 분류 |
|---|---|---|
| `Network_TCPIP.pdf` | 15MB | `classified/attachment_rejected` — 업로드 한도 초과 |
| `4월 20일 암센터 회의.m4a` | 34MB | 🔴 `blocking/attachment_download_failed` |

이유는 같다: **제품이 받는 크기를 넘었다.** 그런데 하나는 「사람이 정할 일」이고
하나는 「이관이 실패했다」로 보였다. 내려받는 쪽이 제품과 **다른 한도**(25MB)를 따로
갖고 있었기 때문이다.

한도가 둘이면 무엇을 결정해야 하는지 못 읽는다. 그래서 내려받는 쪽의 수는 정책이
아니라 메모리 보호로 물러났고, 크기 판정은 `app/core/uploads.py` 하나가 한다.
"""

from __future__ import annotations

import pytest

from app.core.uploads import MAX_UPLOAD_BYTES
from app.migration import source_notion

pytestmark = pytest.mark.regression


def test_the_downloader_does_not_hold_its_own_upload_policy():
    """내려받는 쪽의 수가 제품 한도보다 **훨씬 커야** 정책이 하나로 유지된다.

    같거나 작으면 「제품이 거절한다」가 「못 받았다」로 뒤바뀐다.
    """
    assert source_notion._MAX_FILE_BYTES > MAX_UPLOAD_BYTES * 10, (
        "내려받기 한도가 제품 업로드 한도에 가깝다 — 같은 사실이 두 이름으로 분류된다"
    )


def test_the_product_limit_is_where_the_decision_lives():
    """크기 판정의 정본은 `app/core/uploads.py` 다."""
    assert MAX_UPLOAD_BYTES == 10 * 1024 * 1024


def test_a_file_between_the_two_reaches_the_product_and_is_classified_there():
    """**반례** — 15MB·34MB 둘 다 내려받기를 지나 제품 판정까지 간다."""
    from app.storage.service import store_bytes

    for size in (15 * 1024 * 1024, 34 * 1024 * 1024):
        assert size > MAX_UPLOAD_BYTES
        assert size < source_notion._MAX_FILE_BYTES, (
            f"{size} 바이트가 내려받기에서 먼저 막힌다 — 제품 판정까지 못 간다"
        )
    # 판정이 실제로 「너무 크다」인지 확인한다. 저장소가 없어도 크기 검사가 먼저다.
    with pytest.raises(Exception) as caught:
        store_bytes(None, filename="x.pdf", content=b"0" * (MAX_UPLOAD_BYTES + 1))
    assert "너무 큽니다" in str(getattr(caught.value, "message", caught.value))
