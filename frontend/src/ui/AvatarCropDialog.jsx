import React from "react";
import Box from "@mui/material/Box";
import Slider from "@mui/material/Slider";
import Typography from "@mui/material/Typography";
import Cropper from "react-easy-crop";

import { Modal, ModalFooter } from "./kit.jsx";
import { FONT_SIZE } from "./theme.js";

/* 사진을 올릴 때 **어디를 쓸지 사람이 정한다** (지시: Avatar 시스템).
 *
 * ## 왜 자동 가운데 자르기로 끝내지 않는가
 *
 * 프로필 사진은 대개 사람이 가운데에 없다. 단체 사진에서 자기를 오려 오고, 세로 사진의
 * 얼굴은 위쪽에 있다. 가운데를 잘라 주면 어깨나 배경만 남는 일이 흔하고, 그때 사용자가
 * 할 수 있는 일은 **밖에서 사진을 미리 잘라 다시 올리는 것뿐**이다.
 *
 * ## 좌표의 뜻
 *
 * 화면에서 옮기는 것은 사진이고, 서버에 보내는 것은 **원본의 어느 사각형인가**다.
 * 둘은 다르다 — 화면 미리보기는 편의상 어떤 크기여도 되지만 잘라 낼 자리는 원본 기준의
 * 비율이어야 한다(원본 짧은 변을 1.0 으로 본다). 그래서 저장 직전에 한 번 환산한다.
 * 서버 쪽 같은 계약은 `app/profiles/avatar_image.py::_square_box` 다.
 *
 * ## `react-easy-crop`(§15.6)
 *
 * 예전에는 포인터 이벤트로 끌기만 손으로 짰고, 확대는 슬라이더뿐이라 **모바일에서 두
 * 손가락으로 확대(핀치)가 안 됐다** — 화면 크기는 자유로운데 정작 손가락이 더 자연스러운
 * 자리에서 슬라이더를 더듬어야 했다. 이 라이브러리는 끌기·휠·핀치를 전부 기본으로 준다
 * (의존성 0, MIT). 슬라이더는 지운 것이 아니라 **같은 `zoom` 값을 공유하는 또 하나의
 * 입력**으로 남긴다 — 마우스 사용자도 정밀한 값을 칠 수 있어야 한다.
 *
 * `objectFit="cover"` 를 쓰는 이유: 이 값이 없으면(기본 "contain") 세로 사진이 정사각형
 * 틀 안에 통째로 들어오면서 좌우에 빈 자리가 생긴다 — 그러면 사람이 짧은 변 바깥(원본에
 * 없는 자리)을 보게 된다. `cover` 는 **짧은 변이 틀을 꽉 채우고** 긴 변만 끌어서 보게
 * 한다 — 예전 수식(`base = VIEW / Math.min(width, height)`)이 하던 일과 정확히 같다.
 *
 * `onCropComplete` 가 주는 `croppedAreaPixels`(`{x, y, width, height}`)는 **원본 픽셀
 * 기준**이다(라이브러리 소스 `computeCroppedArea` — `mediaNaturalBBoxSize` 로 계산한다).
 * 정사각형 자르기(`aspect={1}`)라 `width === height` 이고, 그 값을 서버 축(비율 + 배율의
 * 역수)으로 환산만 하면 된다 — 아래 `pixelsToServerCrop()`.
 */

/** 미리보기 원의 지름(px). 실제 잘라 낼 크기와는 무관하다 — 화면에서 보기 좋은 크기다. */
const VIEW = 260;

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

/** 원본 비율 → 서버 축. 원본 짧은 변을 1.0 으로 본 왼쪽 위 모서리 + 배율의 역수.
 *
 * 순수 함수로 뺀 이유: `react-easy-crop` 의 `<Cropper>` 는 실제 레이아웃(getBoundingClientRect)에
 * 기대므로 jsdom(테스트 환경)에서는 제스처를 재현할 신뢰할 방법이 없다 — 반대로 이 환산
 * 자체는 산수라 입력(`natural`·`area`)만 주면 어느 환경에서나 같은 값을 낸다. 잘못되면
 * "보이는 화면 그대로 안 잘리는" 조용한 결함이라(avatar-crop-dialog.test.jsx) 여기서 직접 잰다.
 */
export function pixelsToServerCrop(natural, area) {
  if (!natural || !area) return { crop_x: 0, crop_y: 0, crop_zoom: 1 };
  const short = Math.min(natural.width, natural.height);
  return {
    crop_x: clamp(area.x / short, 0, 1),
    crop_y: clamp(area.y / short, 0, 1),
    crop_zoom: clamp(short / area.width, MIN_ZOOM, 8),
  };
}

export function AvatarCropDialog({ open, file, onClose, onSave, busy }) {
  const [url, setUrl] = React.useState(null);
  const [natural, setNatural] = React.useState(null);   // { width, height } — 원본 픽셀
  const [zoom, setZoom] = React.useState(1);
  /* `Cropper` 가 받는 `crop` — 사진이 틀 중심에서 얼마나 벗어나 있는가(px, 라이브러리 계약). */
  const [crop, setCrop] = React.useState({ x: 0, y: 0 });
  /* 실제로 잘라 낼 원본 픽셀 사각형 — 끌기·휠·핀치가 멈출 때마다 `onCropComplete` 가 갱신한다.
     저장 버튼을 누르는 시점에 다시 계산하지 않고 이미 알고 있는 값을 그대로 쓴다. */
  const [area, setArea] = React.useState(null);

  React.useEffect(() => {
    if (!file) { setUrl(null); setNatural(null); setArea(null); return undefined; }
    const next = URL.createObjectURL(file);
    setUrl(next);
    setZoom(1);
    setCrop({ x: 0, y: 0 });
    setArea(null);
    /* 만든 URL 은 반드시 되돌려준다 — 안 하면 사진을 고를 때마다 그 바이트가 탭이 닫힐
       때까지 메모리에 남는다. */
    return () => URL.revokeObjectURL(next);
  }, [file]);

  const onCropComplete = React.useCallback((_percentArea, pixels) => setArea(pixels), []);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="사진 자르기"
      size="sm"
      footer={
        <ModalFooter
          onCancel={onClose}
          onSubmit={() => onSave(pixelsToServerCrop(natural, area))}
          submitLabel="저장"
          busy={busy}
          // 잘라 낼 자리를 아직 못 받았으면(사진 로딩 중) 저장을 막는다 — 그 사이에 눌리면
          // cropValues() 가 기본값(원본 그대로)을 보내 사용자가 고른 자리를 무시하게 된다.
          disabled={!area}
        />
      }
    >
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        사진을 끌어서 옮기고 아래에서 크기를 맞춥니다. 원 안에 들어온 부분이 프로필 사진이 됩니다.
      </Typography>

      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
        <Box
          sx={{
            width: VIEW, height: VIEW, maxWidth: "100%",
            position: "relative", overflow: "hidden", borderRadius: "50%",
            bgcolor: "background.inset",
            boxShadow: (t) => `inset 0 0 0 1px ${t.palette.divider}`,
          }}
        >
          {url ? (
            <Cropper
              image={url}
              crop={crop}
              zoom={zoom}
              aspect={1}
              objectFit="cover"
              cropShape="round"
              showGrid={false}
              minZoom={MIN_ZOOM}
              maxZoom={MAX_ZOOM}
              onCropChange={setCrop}
              onZoomChange={setZoom}
              onCropComplete={onCropComplete}
              onMediaLoaded={(media) => setNatural({ width: media.naturalWidth, height: media.naturalHeight })}
            />
          ) : null}
        </Box>

        <Box sx={{ width: "100%", maxWidth: VIEW, display: "flex", alignItems: "center", gap: 1.5 }}>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: FONT_SIZE.bodySm }}>크기</Typography>
          <Slider
            value={zoom}
            min={MIN_ZOOM}
            max={MAX_ZOOM}
            step={0.01}
            onChange={(_, v) => setZoom(Array.isArray(v) ? v[0] : v)}
            aria-label="사진 크기"
            disabled={!natural}
          />
        </Box>
      </Box>
    </Modal>
  );
}
