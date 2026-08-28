import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

/* AvatarCropDialog — react-easy-crop 교체(REAUDIT_PLAN §15.6).
 *
 * 두 갈래로 나눠 검증한다.
 *
 *  1. `pixelsToServerCrop()` — 순수 함수. `react-easy-crop` 이 주는 `croppedAreaPixels`
 *     (원본 픽셀 사각형)를 서버 축(crop_x/crop_y/crop_zoom, `app/profiles/avatar_image.py`
 *     와 같은 뜻)으로 정확히 환산하는가. **이 계산이 이 부품 교체의 핵심 위험**이다 —
 *     틀리면 사용자가 원 안에서 본 자리와 실제로 저장되는 사진이 어긋나는데, 겉보기(대화상자
 *     자체는 정상으로 보인다)로는 드러나지 않는다.
 *
 *  2. `<AvatarCropDialog>` 자체는 최소 렌더 계약만 확인한다. `<Cropper>` 는
 *     `getBoundingClientRect`(jsdom 이 항상 0 을 준다)에 기대는 실제 레이아웃 컴포넌트라,
 *     끌기·휠·핀치를 이 환경에서 재현해도 그 결과를 신뢰할 수 없다 — 그래서 여기서는
 *     "연다·이름표가 맞다·자리를 아직 못 받았으면 저장이 잠겨 있다"만 본다. 핀치 확대가
 *     실제로 되는지는 실브라우저로만 확인할 수 있다(자동화 시험 불가 — 이 사실 자체가
 *     이 파일이 명시하는 한계다).
 */
import { AvatarCropDialog, pixelsToServerCrop } from "./AvatarCropDialog.jsx";

describe("pixelsToServerCrop — 원본 픽셀 사각형 → 서버 축", () => {
  it("입력이 없으면 원본 그대로(자르지 않음)를 뜻하는 기본값을 낸다", () => {
    expect(pixelsToServerCrop(null, null)).toEqual({ crop_x: 0, crop_y: 0, crop_zoom: 1 });
    expect(pixelsToServerCrop({ width: 100, height: 100 }, null)).toEqual({ crop_x: 0, crop_y: 0, crop_zoom: 1 });
  });

  it("정사각형 원본 — 짧은 변이 곧 전체 변이라 계산이 가장 단순하다", () => {
    // 1000x1000 원본에서 왼쪽 위 (100,100)부터 500x500 을 골랐다.
    const out = pixelsToServerCrop({ width: 1000, height: 1000 }, { x: 100, y: 100, width: 500, height: 500 });
    expect(out.crop_x).toBeCloseTo(0.1, 6);   // 100 / 1000
    expect(out.crop_y).toBeCloseTo(0.1, 6);
    expect(out.crop_zoom).toBeCloseTo(2, 6);  // 1000 / 500
  });

  it("세로 사진(짧은 변은 가로) — 짧은 변 기준으로 비율을 낸다", () => {
    // 1200(가로) x 2000(세로) 원본. 짧은 변은 가로 1200.
    const out = pixelsToServerCrop({ width: 1200, height: 2000 }, { x: 120, y: 800, width: 400, height: 400 });
    expect(out.crop_x).toBeCloseTo(120 / 1200, 6);
    expect(out.crop_y).toBeCloseTo(800 / 1200, 6);
    expect(out.crop_zoom).toBeCloseTo(1200 / 400, 6);
  });

  it("가로 사진(짧은 변은 세로) — 짧은 변 기준으로 비율을 낸다", () => {
    // 2400(가로) x 1600(세로) 원본. 짧은 변은 세로 1600.
    const out = pixelsToServerCrop({ width: 2400, height: 1600 }, { x: 900, y: 300, width: 800, height: 800 });
    expect(out.crop_x).toBeCloseTo(900 / 1600, 6);
    expect(out.crop_y).toBeCloseTo(300 / 1600, 6);
    expect(out.crop_zoom).toBeCloseTo(1600 / 800, 6);
  });

  it("crop_x/crop_y 는 [0,1] 을 벗어나지 않는다 — 서버가 사각형을 원본 밖으로 못 내는 것과 같은 안전망", () => {
    const out = pixelsToServerCrop({ width: 1000, height: 1000 }, { x: -50, y: 1500, width: 500, height: 500 });
    expect(out.crop_x).toBe(0);
    expect(out.crop_y).toBe(1);
  });

  it("crop_zoom 은 1(원본 짧은 변 전부) 아래로 안 내려간다", () => {
    // 잘라 낼 사각형이 짧은 변보다 큰 경우(이론상 크롭퍼가 안 주지만, 방어적으로 clamp).
    const out = pixelsToServerCrop({ width: 1000, height: 1000 }, { x: 0, y: 0, width: 2000, height: 2000 });
    expect(out.crop_zoom).toBe(1);
  });

  it("crop_zoom 은 8을 넘지 않는다 — 서버의 MIN_SOURCE_PIXELS 방어선과 같은 상한", () => {
    const out = pixelsToServerCrop({ width: 1000, height: 1000 }, { x: 0, y: 0, width: 1, height: 1 });
    expect(out.crop_zoom).toBe(8);
  });
});

describe("<AvatarCropDialog> — 최소 렌더 계약", () => {
  const file = new File(["x"], "photo.png", { type: "image/png" });

  // jsdom은 Blob URL 확장(createObjectURL/revokeObjectURL)을 구현하지 않는다 — 이 부품이
  // 사진을 미리보기로 띄우려고 마운트 즉시 부르는 API라 없으면 useEffect가 처리되지 않은
  // 예외로 죽는다(이 컴포넌트만의 문제가 아니라 jsdom 자체의 공백).
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:mock-url");
    URL.revokeObjectURL = vi.fn();
  });

  it("열리면 제목이 '사진 자르기'이고, 아직 잘라 낼 자리를 못 받았으면 저장이 잠겨 있다", async () => {
    render(
      <AvatarCropDialog open file={file} onClose={() => {}} onSave={vi.fn()} busy={false} />
    );
    expect(await screen.findByRole("heading", { name: "사진 자르기" })).toBeInTheDocument();
    // onCropComplete 가 아직 한 번도 안 불렸으므로(레이아웃 의존 — 위 파일 머리말 참고)
    // 저장 버튼은 비활성 상태로 시작한다. cropValues() 의 기본값을 그대로 보내는 사고를 막는다.
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
  });

  it("닫혀 있으면 아무것도 그리지 않는다", () => {
    render(
      <AvatarCropDialog open={false} file={null} onClose={() => {}} onSave={vi.fn()} busy={false} />
    );
    expect(screen.queryByRole("heading", { name: "사진 자르기" })).not.toBeInTheDocument();
  });
});
