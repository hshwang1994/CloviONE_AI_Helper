import React from "react";
import Box from "@mui/material/Box";
import Slider from "@mui/material/Slider";
import Typography from "@mui/material/Typography";

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
 * ## 손가락으로도 된다
 *
 * 끌기는 포인터 이벤트로 받는다 — 마우스·터치·펜이 한 코드에서 처리되고, 모바일에서
 * 따로 배선하지 않아도 옮길 수 있다. 확대는 슬라이더라 손가락으로도 잡힌다.
 */

/** 미리보기 원의 지름(px). 실제 잘라 낼 크기와는 무관하다 — 화면에서 보기 좋은 크기다. */
const VIEW = 260;

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

export function AvatarCropDialog({ open, file, onClose, onSave, busy }) {
  const [url, setUrl] = React.useState(null);
  const [natural, setNatural] = React.useState(null);   // { width, height }
  const [zoom, setZoom] = React.useState(1);
  /* 사진의 중심이 미리보기 원의 중심에서 얼마나 벗어나 있는가(px). 왼쪽 위 모서리가
     아니라 중심을 들고 있는 이유: 확대할 때 중심을 고정해야 손이 따라가지 않는다. */
  const [offset, setOffset] = React.useState({ x: 0, y: 0 });
  const drag = React.useRef(null);

  React.useEffect(() => {
    if (!file) { setUrl(null); setNatural(null); return undefined; }
    const next = URL.createObjectURL(file);
    setUrl(next);
    setZoom(1);
    setOffset({ x: 0, y: 0 });
    /* 만든 URL 은 반드시 되돌려준다 — 안 하면 사진을 고를 때마다 그 바이트가 탭이 닫힐
       때까지 메모리에 남는다. */
    return () => URL.revokeObjectURL(next);
  }, [file]);

  /* 사진의 짧은 변이 미리보기 원을 꽉 채우는 배율. 여기서 출발해야 확대 1.0 이
     「원본 짧은 변 전부」와 같은 뜻이 된다 — 서버의 zoom 과 같은 축이다. */
  const base = natural ? VIEW / Math.min(natural.width, natural.height) : 1;
  const drawnW = natural ? natural.width * base * zoom : 0;
  const drawnH = natural ? natural.height * base * zoom : 0;

  /* 원 밖으로 사진이 밀려나 흰 자리가 생기지 않게 한다. 사용자가 아무리 끌어도
     잘라 낼 사각형은 언제나 사진 안이다. */
  const limitX = Math.max(0, (drawnW - VIEW) / 2);
  const limitY = Math.max(0, (drawnH - VIEW) / 2);
  const shown = {
    x: clamp(offset.x, -limitX, limitX),
    y: clamp(offset.y, -limitY, limitY),
  };

  function onPointerDown(e) {
    if (!natural) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, from: shown };
  }
  function onPointerMove(e) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    setOffset({ x: d.from.x + (e.clientX - d.x), y: d.from.y + (e.clientY - d.y) });
  }
  function onPointerUp(e) {
    if (drag.current && drag.current.id === e.pointerId) drag.current = null;
  }

  /* 화면 좌표 → 원본 비율. 원본 짧은 변을 1.0 으로 본 왼쪽 위 모서리를 낸다. */
  function cropValues() {
    if (!natural) return { crop_x: 0, crop_y: 0, crop_zoom: 1 };
    const short = Math.min(natural.width, natural.height);
    // 미리보기에서 원이 덮는 사진의 폭(원본 픽셀 기준).
    const sideInSource = VIEW / (base * zoom);
    // 사진 중심이 원 중심에서 `shown` 만큼 밀려 있으므로, 원의 왼쪽 위는 그 반대다.
    const left = (drawnW / 2 - shown.x - VIEW / 2) / (base * zoom);
    const top = (drawnH / 2 - shown.y - VIEW / 2) / (base * zoom);
    return {
      crop_x: clamp(left / short, 0, 1),
      crop_y: clamp(top / short, 0, 1),
      crop_zoom: clamp(short / sideInSource, MIN_ZOOM, 8),
    };
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="사진 자르기"
      size="sm"
      footer={
        <ModalFooter
          onCancel={onClose}
          onSubmit={() => onSave(cropValues())}
          submitLabel="저장"
          busy={busy}
        />
      }
    >
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        사진을 끌어서 옮기고 아래에서 크기를 맞춥니다. 원 안에 들어온 부분이 프로필 사진이 됩니다.
      </Typography>

      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
        <Box
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          sx={{
            width: VIEW, height: VIEW, maxWidth: "100%",
            position: "relative", overflow: "hidden", borderRadius: "50%",
            bgcolor: "background.inset",
            cursor: natural ? "grab" : "default",
            /* 끌기 중에 브라우저가 화면을 함께 스크롤하지 않게 한다 — 모바일에서 이것이
               없으면 사진은 안 움직이고 페이지만 움직인다. */
            touchAction: "none",
            boxShadow: (t) => `inset 0 0 0 1px ${t.palette.divider}`,
          }}
        >
          {url ? (
            <Box
              component="img"
              src={url}
              alt=""
              draggable={false}
              onLoad={(e) => setNatural({ width: e.target.naturalWidth, height: e.target.naturalHeight })}
              sx={{
                position: "absolute", left: "50%", top: "50%",
                width: drawnW || "auto", height: drawnH || "auto",
                transform: `translate(calc(-50% + ${shown.x}px), calc(-50% + ${shown.y}px))`,
                userSelect: "none", pointerEvents: "none",
                maxWidth: "none",
              }}
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
