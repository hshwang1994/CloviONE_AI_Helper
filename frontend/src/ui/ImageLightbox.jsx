import React from "react";
import Box from "@mui/material/Box";
import Lightbox from "yet-another-react-lightbox";
import Zoom from "yet-another-react-lightbox/plugins/zoom";
import Captions from "yet-another-react-lightbox/plugins/captions";
import "yet-another-react-lightbox/styles.css";
import "yet-another-react-lightbox/plugins/captions.css";

/* 이미지 확대 보기 — 티켓 본문, 게시판 첨부, 채팅 이미지가 함께 쓴다.
 *
 * 사용자 지시 §4: "이미지를 클릭했을 때 내용을 확인할 수 있도록 구성하라."
 *
 * 그동안 이 앱에는 확대 보기가 **아예 없었다**. 게시판 첨부는 새 탭으로 열렸고(앱을 떠난다),
 * 채팅 이미지는 클릭조차 되지 않았고, 티켓 이미지는 애초에 화면에 오지도 않았다.
 *
 * 직접 만들지 않은 이유: 제대로 하려면 핀치줌, 키보드(←/→/Esc), 포커스 트랩, 스크린리더
 * 레이블, 터치 스와이프를 다 만들어야 한다. 그 다섯 가지가 이미 들어 있는 것을 쓴다
 * (2026-08-04 사용자 지시로 외부 라이브러리 허용).
 *
 * 사용법 — 한 화면에서 여러 장을 넘겨 볼 수 있게 slides 배열과 시작 위치를 받는다:
 *   const lb = useLightbox();
 *   <img onClick={() => lb.open(images, i)} />
 *   <ImageLightbox {...lb.props} />
 */

/** 확대 보기 상태. slides 는 [{src, title?}] 모양. */
export function useLightbox() {
  const [state, setState] = React.useState({ open: false, slides: [], index: 0 });
  const open = React.useCallback((slides, index = 0) => {
    setState({ open: true, slides: slides || [], index: Math.max(0, index) });
  }, []);
  const close = React.useCallback(() => setState((s) => ({ ...s, open: false })), []);
  return { open, close, props: { ...state, onClose: close } };
}

export function ImageLightbox({ open, slides, index, onClose }) {
  if (!open || !slides || slides.length === 0) return null;
  return (
    <Lightbox
      open={open}
      close={onClose}
      slides={slides}
      index={index}
      plugins={[Zoom, Captions]}
      /* 한 장뿐이면 좌우 화살표를 감춘다 — 눌러도 아무 일이 없는 버튼을 두지 않는다. */
      carousel={{ finite: slides.length <= 1 }}
      render={slides.length <= 1 ? { buttonPrev: () => null, buttonNext: () => null } : undefined}
      /* 배경을 완전 불투명하게 두지 않는다 — 뒤 화면이 비쳐야 '위에 떠 있는 것'으로 읽힌다. */
      styles={{ container: { backgroundColor: "rgba(10, 16, 38, .92)" } }}
      controller={{ closeOnBackdropClick: true }}
    />
  );
}

/* 클릭할 수 있는 이미지 — 확대 보기를 여는 공통 표면.
 * button 으로 감싸는 이유: div+onClick 은 키보드로 못 연다(Tab 이 안 서고 Enter 도 안 먹는다). */
export function ClickableImage({ src, alt, onOpen, sx }) {
  return (
    <Box
      component="button"
      type="button"
      onClick={onOpen}
      aria-label={(alt || "이미지") + " 크게 보기"}
      sx={{
        p: 0, border: 0, background: "none", cursor: "zoom-in", display: "block",
        minWidth: 0, maxWidth: "100%", borderRadius: 2, overflow: "hidden",
        "&:focus-visible": { outline: "3px solid", outlineColor: "primary.main", outlineOffset: 2 },
        ...sx,
      }}
    >
      <Box component="img" src={src} alt={alt || ""} loading="lazy" decoding="async"
        sx={{ display: "block", maxWidth: "100%", height: "auto" }} />
    </Box>
  );
}
