"""시험이 쓰는 **진짜 이미지**.

## 왜 1×1 PNG 로는 안 되는가

예전에는 여러 시험이 손으로 적은 1×1 PNG 상수를 썼다. 그때 서버가 사진에 하는 일은
매직바이트 판정과 저장뿐이라 픽셀이 몇 개든 상관없었다.

지금은 서버가 **디코드해서 다시 그린다**(`app/profiles/avatar_image.py`). 그래서 원본에
바닥 크기가 생겼다 — 그보다 작으면 어떤 자르기를 해도 얼굴이 뭉개지고, 그것은
「올렸는데 흐리다」라는 신고가 된 뒤에야 드러난다. 1×1 은 그 바닥 아래다.

여기서 만드는 것은 실제로 디코드되는 사진이라, 시험이 재는 것이 「바이트를 받았는가」가
아니라 「사진을 다뤘는가」가 된다.
"""

from __future__ import annotations

import io

# 아바타 바닥(64)보다 넉넉히 크다. 자르기 시험이 사분면을 구별할 수 있는 크기이기도 하다.
AVATAR_TEST_SIZE = 96


def png_bytes(width: int = AVATAR_TEST_SIZE, height: int = AVATAR_TEST_SIZE) -> bytes:
    """디코드되는 PNG. Pillow 가 없으면 시험이 스스로 건너뛴다."""
    from PIL import Image

    buf = io.BytesIO()
    image = Image.new("RGB", (width, height), (40, 70, 140))
    # 단색이면 자르기 시험이 어느 자리를 잘랐는지 못 가른다 — 왼쪽 위만 다른 색으로 둔다.
    for y in range(height // 2):
        for x in range(width // 2):
            image.putpixel((x, y), (240, 200, 40))
    image.save(buf, format="PNG")
    return buf.getvalue()
