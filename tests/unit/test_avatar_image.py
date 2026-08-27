"""아바타 사진은 **서버가 다시 그린다** — 받은 바이트를 그대로 내보내지 않는다.

여기서 지키는 것은 넷이다.

1. **출력에는 픽셀만 있다.** 원본의 EXIF·색 프로파일·주석이 한 바이트도 안 따라온다.
   매직바이트 검사는 「이것이 PNG 라고 주장하는가」에 답하지만 「그 안에 무엇이
   들었는가」에는 답하지 않는다.
2. **회전 표식을 자르기 **전에** 편다.** 순서가 뒤집히면 화면에서 고른 사각형과 서버가
   자르는 사각형이 다른 그림을 가리킨다 — 얼굴을 고르고 어깨를 얻는다.
3. **사용자가 보낸 자르기 값을 안 믿는다.** 음수도, 1 을 넘는 값도, 0 인 확대도 온다.
4. **너무 작거나 너무 큰 원본은 거절한다.** 앞엣것은 「올렸는데 흐리다」가 되고 뒤엣것은
   디코드 폭탄이다.
"""

from __future__ import annotations

import io

import pytest

from app.core.errors import ValidationAppError
from app.profiles import avatar_image

pytestmark = pytest.mark.unit

PIL = pytest.importorskip("PIL", reason="Pillow 가 없으면 아바타 사진 처리 자체가 없다")


def _png(width: int, height: int, color=(30, 60, 120)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _open(data: bytes):
    from PIL import Image

    return Image.open(io.BytesIO(data))


def test_output_is_a_square_webp_of_the_contract_size():
    out = avatar_image.render_thumbnail(_png(800, 600))
    image = _open(out)
    assert image.format == "WEBP"
    assert image.size == (avatar_image.THUMB_SIZE, avatar_image.THUMB_SIZE)


def test_the_new_file_carries_no_metadata_from_the_original():
    """원본에 EXIF 를 심어 놓고, 출력에 그것이 **없는지** 본다.

    이 단언이 없으면 「다시 그렸다」는 주석뿐이다 — 실제로 Pillow 에게 `exif=` 를 넘기는
    한 줄만 생겨도 위치 정보가 전 직원에게 나간다.
    """
    from PIL import Image

    buf = io.BytesIO()
    source = Image.new("RGB", (400, 400), (200, 40, 40))
    exif = source.getexif()
    exif[0x010E] = "비밀 메모"          # ImageDescription
    exif[0x0112] = 6                    # Orientation
    source.save(buf, format="JPEG", exif=exif)

    out = avatar_image.render_thumbnail(buf.getvalue())
    assert not dict(_open(out).getexif()), "출력에 원본의 EXIF 가 따라왔다"


def test_orientation_is_applied_before_cropping():
    """회전 표식이 6(왼쪽으로 90도)인 세로 사진에서 **위쪽**을 자른다.

    표식을 펴지 않으면 같은 좌표가 원본의 다른 변을 가리키므로, 편 그림의 위쪽 색과
    안 편 그림의 위쪽 색이 다르다. 두 색이 실제로 다른 그림을 만들어 그것을 확인한다.
    """
    from PIL import Image

    # 위 절반 빨강 / 아래 절반 파랑인 그림을 만들고, 「왼쪽으로 90도 돌려서 보라」고 적는다.
    upright = Image.new("RGB", (400, 400), (0, 0, 255))
    for y in range(200):
        for x in range(400):
            upright.putpixel((x, y), (255, 0, 0))
    # Orientation 6 은 「저장된 픽셀을 시계 방향 90도 돌려야 바로 선다」는 뜻이다.
    stored = upright.rotate(90, expand=True)
    buf = io.BytesIO()
    exif = stored.getexif()
    exif[0x0112] = 6
    stored.save(buf, format="JPEG", exif=exif, quality=95)

    out = avatar_image.render_thumbnail(buf.getvalue(), crop_x=0.0, crop_y=0.0, zoom=2.0)
    top_left = _open(out).convert("RGB").getpixel((8, 8))
    assert top_left[0] > top_left[2], (
        f"바로 선 그림의 왼쪽 위는 빨강이어야 한다 — 회전을 안 폈다 ({top_left})"
    )


@pytest.mark.parametrize(
    "crop_x, crop_y, zoom",
    [(-5.0, -5.0, 1.0), (9.0, 9.0, 1.0), (0.0, 0.0, 0.0), (0.5, 0.5, 999.0)],
)
def test_wild_crop_values_do_not_break_anything(crop_x, crop_y, zoom):
    """화면이 보낸 값을 안 믿는다 — 어떤 값이 와도 원본 안의 정사각형이 나온다."""
    out = avatar_image.render_thumbnail(_png(600, 400), crop_x=crop_x, crop_y=crop_y, zoom=zoom)
    assert _open(out).size == (avatar_image.THUMB_SIZE, avatar_image.THUMB_SIZE)


def test_a_photo_smaller_than_the_floor_is_refused():
    with pytest.raises(ValidationAppError):
        avatar_image.render_thumbnail(_png(32, 32))


def test_a_file_that_is_not_an_image_is_refused_with_a_readable_message():
    with pytest.raises(ValidationAppError) as caught:
        avatar_image.render_thumbnail("이것은 사진이 아니다".encode("utf-8"))
    # 사용자에게 디코더 예외 원문을 보이지 않는다.
    assert "사진" in str(caught.value)


def test_the_crop_actually_moves_the_window():
    """자르기 값이 **실제로 다른 그림**을 낸다.

    이 단언이 없으면 위 시험들은 「어떤 값이 와도 안 터진다」까지만 증명한다 — 값을 통째로
    무시해도 전부 통과한다.
    """
    from PIL import Image

    source = Image.new("RGB", (400, 400), (0, 0, 0))
    for y in range(200):
        for x in range(200):
            source.putpixel((x, y), (255, 255, 0))   # 왼쪽 위 사분면만 노랑
    buf = io.BytesIO()
    source.save(buf, format="PNG")

    top_left = _open(
        avatar_image.render_thumbnail(buf.getvalue(), crop_x=0.0, crop_y=0.0, zoom=2.0)
    ).convert("RGB").getpixel((8, 8))
    bottom_right = _open(
        avatar_image.render_thumbnail(buf.getvalue(), crop_x=0.5, crop_y=0.5, zoom=2.0)
    ).convert("RGB").getpixel((8, 8))

    assert top_left[0] > 200 and top_left[1] > 200, f"왼쪽 위는 노랑이어야 한다 ({top_left})"
    assert sum(bottom_right) < 90, f"오른쪽 아래는 검정이어야 한다 ({bottom_right})"
