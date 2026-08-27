"""아바타 이미지 — **서버가 다시 그린다.** 받은 바이트를 그대로 내보내지 않는다.

## 왜 다시 그리는가

업로드한 파일을 그대로 저장하고 그대로 서빙하면, 우리는 **남이 만든 바이트를 우리
도메인에서 브라우저에 먹이는** 일을 하게 된다. 매직바이트 검사(`app/core/uploads.py`)는
「이것이 PNG 라고 주장하는가」에 답하지만 「이 PNG 안에 무엇이 들었는가」에는 답하지
않는다 — EXIF, 색 프로파일, 주석 청크, 다른 포맷의 꼬리가 전부 따라 들어온다.

여기서 하는 일은 하나다: **디코드해서 픽셀만 꺼내고, 그 픽셀로 새 파일을 만든다.**
원본의 메타데이터는 한 바이트도 새 파일에 안 들어간다.

## EXIF 회전을 먼저 편다

휴대전화 사진은 픽셀을 돌려 저장하지 않고 「이만큼 돌려서 보라」는 표식만 남긴다.
그 표식을 버리고 픽셀만 쓰면 옆으로 누운 얼굴이 나온다 — 그래서 **자르기 전에** 편다.
순서가 중요하다: 사용자가 화면에서 고른 사각형은 「바로 선 그림」 기준이다.

## 자르기 값의 뜻

`crop_x`·`crop_y` 는 **원본 짧은 변을 1.0 으로 본 비율**이고 잘라 낼 정사각형의 왼쪽 위
모서리다. `zoom` 은 그 정사각형이 짧은 변의 몇 분의 일인가의 역수다(1.0 이면 짧은 변
전부, 2.0 이면 절반). 픽셀로 저장하지 않는 이유: 원본 해상도가 바뀌면 픽셀 좌표의 뜻이
같이 바뀌는데, 비율은 안 바뀐다.

## Pillow 는 함수 안에서 부른다

깔려 있지 않은 설치에서 **웹이 통째로 안 뜨면 안 된다.** AI 런타임이 같은 이유로 같은
모양을 하고 있다(`requirements-ai.txt` 머리말). 없으면 아바타 업로드만 못 하고 나머지
제품은 그대로 돈다.
"""

from __future__ import annotations

import io

from app.core.errors import ValidationAppError

# 표시용 정사각형 한 변. 목록의 20px 부터 프로필의 96px 까지 한 파일로 덮는다 — 고해상도
# 화면에서 2배로 그려도 뭉개지지 않는 가장 작은 값이다.
THUMB_SIZE = 256

# 원본에 요구하는 최소 크기. 이보다 작으면 어떤 자르기를 해도 얼굴이 뭉개진다 —
# 「올렸는데 흐리다」는 신고가 되고, 그때는 이미 원본이 없다.
MIN_SOURCE_PIXELS = 64

# 원본 상한. 픽셀 수로 막는다(변 길이가 아니라) — 1×100,000,000 같은 모양이 변 길이
# 검사를 통과하면서 메모리를 다 먹는다. 「디코드 폭탄」의 표준 방어다.
MAX_SOURCE_PIXELS = 40_000_000

# 새로 만드는 파일의 형식. WebP 는 같은 화질에서 PNG 보다 작고, 이 제품이 이미 허용하는
# 형식이다(`uploads.IMAGE_MEDIA_TYPES`).
OUTPUT_MEDIA_TYPE = "image/webp"
OUTPUT_EXTENSION = ".webp"


def _pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover — 설치 상태에 달린 갈래
        raise ValidationAppError(
            "이 서버에서는 지금 사진을 처리할 수 없습니다. 관리자에게 문의해 주세요."
        ) from exc
    return Image, ImageOps


def _open(content: bytes):
    Image, ImageOps = _pillow()
    try:
        image = Image.open(io.BytesIO(content))
        # 크기는 **디코드 전에** 읽는다. `load()` 를 먼저 부르면 폭탄이 이미 펼쳐진 뒤다.
        width, height = image.size
        if width * height > MAX_SOURCE_PIXELS:
            raise ValidationAppError("사진이 너무 큽니다. 더 작은 사진을 올려 주세요.")
        if min(width, height) < MIN_SOURCE_PIXELS:
            raise ValidationAppError(
                f"사진이 너무 작습니다. 가로세로 {MIN_SOURCE_PIXELS}픽셀 이상이어야 합니다."
            )
        image.load()
    except ValidationAppError:
        raise
    except Exception as exc:  # noqa: BLE001 — 어떤 디코더 오류든 사용자에게는 같은 말이다
        raise ValidationAppError(
            "사진을 읽지 못했습니다. jpg, png, webp 파일인지 확인해 주세요."
        ) from exc
    # 회전 표식을 픽셀에 반영하고 표식은 버린다. 자르기 좌표는 바로 선 그림 기준이다.
    return ImageOps.exif_transpose(image)


def _square_box(width: int, height: int, crop_x: float, crop_y: float, zoom: float):
    """비율 좌표 → 원본 픽셀 사각형. **원본 밖으로 안 나간다.**

    사용자가 보낸 값을 믿지 않는다 — 음수도, 1 을 넘는 값도, 0 인 zoom 도 올 수 있고
    그중 하나라도 그대로 쓰면 `crop` 이 예외를 던지거나 빈 이미지를 만든다.
    """
    short = min(width, height)
    z = max(1.0, min(float(zoom or 1.0), 8.0))
    side = max(MIN_SOURCE_PIXELS, int(round(short / z)))
    side = min(side, width, height)
    left = int(round(max(0.0, min(float(crop_x or 0.0), 1.0)) * short))
    top = int(round(max(0.0, min(float(crop_y or 0.0), 1.0)) * short))
    left = max(0, min(left, width - side))
    top = max(0, min(top, height - side))
    return (left, top, left + side, top + side)


def render_thumbnail(
    content: bytes, *, crop_x: float = 0.0, crop_y: float = 0.0, zoom: float = 1.0
) -> bytes:
    """원본 바이트 → 표시용 정사각형 WebP. **원본의 메타데이터는 안 따라온다.**"""
    Image, _ = _pillow()
    image = _open(content)
    image = image.convert("RGB")
    box = _square_box(image.width, image.height, crop_x, crop_y, zoom)
    square = image.crop(box)
    if square.width != THUMB_SIZE:
        square = square.resize((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
    out = io.BytesIO()
    # `exif` 도 `icc_profile` 도 안 넘긴다 — 새 파일에는 픽셀만 있다.
    square.save(out, format="WEBP", quality=88, method=4)
    return out.getvalue()
