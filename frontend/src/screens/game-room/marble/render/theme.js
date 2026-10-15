import { alpha, darken, lighten } from "@mui/material/styles";

/* 판 팔레트 — 제품 테마 토큰에서 만든다 (D-564). 색을 여기 하드코딩하지 않는다.
 *
 * 밝은 모드: 밝은 판 · 부드러운 장애물 면 + 또렷한 테두리 · 참가자별 구슬 색(HSL 고르게 분배). 어두운 모드: 어두운 판 ·
 * 장애물 대비 올림 · 구슬 명도 올림 · 결승선 · 강조색 · 테두리 조정. 테마를 바꾸면 팔레트만 바뀌고 워커 · 상태는 그대로다.
 * 깨지는 장애물(`life`)은 옅은 브랜드색 방울로, 미니맵은 판 위에 뜬 작은 판으로 그린다(D-578). 밝은 판의 바탕은 중립 안쪽 면
 * (`background.inset`)이다 — 판 틀을 다 채우는 캔버스가 브랜드 틴트면 보라 면이 화면의 절반이 된다(F7 색 쓰임, brand_area 실측).
 * 구슬의 채도 · 명도는 모드별 고정값이고 색상(hue)만 참가자마다 다르다 — 원본의 색 구성을 복제하지 않는다. */
export function boardPalette(theme) {
  const p = (theme && theme.palette) || {};
  const mode = p.mode === "dark" ? "dark" : "light";
  const primary = (p.primary && p.primary.main) || "#5A4FCF";
  const paper = (p.background && p.background.paper) || (mode === "dark" ? "#171A2E" : "#FFFFFF");
  const ink = (p.text && p.text.primary) || (mode === "dark" ? "#E6E8F2" : "#1A1D33");
  const tint = p.brandTint || (mode === "dark" ? "#1E2244" : "#E9ECFA");
  const inset = (p.background && p.background.inset) || (mode === "dark" ? "#1C2136" : "#F5F6FB");
  const success = (p.success && p.success.main) || "#2E9E6B";
  const fontFamily = (theme && theme.typography && theme.typography.fontFamily) || "Pretendard, sans-serif";
  if (mode === "dark") {
    return {
      mode, fontFamily,
      board: darken(tint, 0.18), boardEdge: alpha(ink, 0.18),
      wall: alpha(ink, 0.62),
      obstacle: lighten(paper, 0.22), obstacleEdge: alpha(ink, 0.7),
      rotor: alpha(primary, 0.85), rotorEdge: alpha(ink, 0.7),
      finish: success, finishText: ink,
      label: ink, labelHalo: alpha(darken(tint, 0.18), 0.92),
      marble: { s: 70, l: 66 }, marbleEdge: alpha("#000000", 0.5), highlight: alpha("#FFFFFF", 0.55), shadow: alpha("#000000", 0.4),
      winnerRing: lighten(primary, 0.25), winnerGlow: alpha(lighten(primary, 0.35), 0.9), goneAlpha: 0.3,
      bubble: alpha(lighten(primary, 0.3), 0.16), bubbleEdge: alpha(lighten(primary, 0.45), 0.85),
      minimapBg: alpha(darken(tint, 0.42), 0.92), minimapEdge: alpha(ink, 0.2), minimapWall: alpha(ink, 0.6),
      minimapViewport: lighten(primary, 0.35), spriteFace: lighten(paper, 0.12),
    };
  }
  return {
    mode, fontFamily,
    board: inset, boardEdge: alpha(ink, 0.12),
    wall: alpha(ink, 0.5),
    obstacle: paper, obstacleEdge: alpha(ink, 0.38),
    rotor: alpha(primary, 0.75), rotorEdge: alpha(primary, 0.9),
    finish: success, finishText: ink,
    label: ink, labelHalo: alpha(paper, 0.92),
    marble: { s: 76, l: 56 }, marbleEdge: alpha("#000000", 0.35), highlight: alpha("#FFFFFF", 0.75), shadow: alpha("#000000", 0.22),
    winnerRing: primary, winnerGlow: alpha(primary, 0.6), goneAlpha: 0.3,
    bubble: alpha(primary, 0.1), bubbleEdge: alpha(primary, 0.7),
    minimapBg: alpha(paper, 0.94), minimapEdge: alpha(ink, 0.14), minimapWall: alpha(ink, 0.55),
    minimapViewport: primary, spriteFace: inset,
  };
}

/** 참가자 색 — 색상(hue)은 엔진이 참가자 순서로 고르게 나눈다(`race.js`). 채도 · 명도는 모드의 값이다. */
export function marbleColor(hue, palette) {
  return `hsl(${Math.round(((hue % 360) + 360) % 360)} ${palette.marble.s}% ${palette.marble.l}%)`;
}

/** 그리기 밖(DOM 순위 레일 · 결과 판)에서도 같은 구슬 색을 쓴다 — 참가자 번호와 총원으로 색상을 되짚는다. */
export function participantHue(order, total) {
  return total > 0 ? (360 / total) * order : 0;
}
