import { describe, it, expect, vi } from "vitest";
import {
  EMOJI_GROUPS, MAX_IMAGE_BYTES, PASTE_IMAGE_TYPES,
  imageFromClipboard, imageRejectReason, insertAtCursor,
} from "./chat-compose.js";

/* 컴포저 순수 로직 — 이모지 표, 커서 삽입, 클립보드 이미지 추출.
 *
 * 이 셋은 화면 없이 검증할 수 있는 규칙이고, 틀리면 사용자가 바로 느낀다:
 * 이모지가 문장 앞에 끼어들거나, Ctrl+V로 텍스트를 붙여넣었는데 업로드가 나가거나,
 * 10MB 넘는 사진을 올려 서버에서 422를 받고서야 안내를 보게 된다.
 */

describe("EMOJI_GROUPS", () => {
  it("유니코드 문자만 담는다 — 이미지 스프라이트·외부 폰트는 CSP에 걸리고 오프라인에서 깨진다", () => {
    EMOJI_GROUPS.forEach((g) => {
      expect(typeof g.label).toBe("string");
      expect(g.emojis.length).toBeGreaterThan(0);
      g.emojis.forEach((e) => {
        expect(typeof e).toBe("string");
        expect(e.length).toBeGreaterThan(0);
        // http(s)·data URI·태그가 섞이면 그건 이미지를 끌어오는 것이다.
        expect(e).not.toMatch(/https?:|data:|<|\//);
      });
    });
  });

  it("같은 이모지를 두 번 싣지 않는다", () => {
    const all = EMOJI_GROUPS.flatMap((g) => g.emojis);
    expect(new Set(all).size).toBe(all.length);
  });
});

describe("insertAtCursor", () => {
  it("커서 자리에 끼워 넣고 그 뒤 위치를 돌려준다", () => {
    // caret 은 JS 문자열 인덱스(UTF-16 코드유닛)다 — 대부분의 이모지는 서로게이트 쌍이라
    // 2를 차지한다. setSelectionRange 도 같은 단위를 쓰므로 이 값이 그대로 맞다.
    expect(insertAtCursor("안녕하세요", "👍", 2, 2)).toEqual({ text: "안녕👍하세요", caret: 4 });
  });

  it("선택 범위가 있으면 그 범위를 대체한다", () => {
    expect(insertAtCursor("abcdef", "🔥", 1, 4)).toEqual({ text: "a🔥ef", caret: 3 });
  });

  it("선택 위치를 모르면(포커스가 없던 경우) 맨 뒤에 붙인다 — 문장 앞에 끼어들지 않는다", () => {
    expect(insertAtCursor("보고서 검토", "✅", null, null)).toEqual({ text: "보고서 검토✅", caret: 7 });
    expect(insertAtCursor("보고서", "✅", undefined, undefined).text).toBe("보고서✅");
  });

  it("범위를 벗어난 값이 와도 문자열을 깨뜨리지 않는다", () => {
    expect(insertAtCursor("abc", "!", 99, 99).text).toBe("abc!");
    expect(insertAtCursor("abc", "!", -3, -1).text).toBe("abc!");
  });

  it("빈 초안·빈 삽입도 안전하다", () => {
    expect(insertAtCursor("", "😀", 0, 0)).toEqual({ text: "😀", caret: 2 });
    expect(insertAtCursor(null, null, 0, 0)).toEqual({ text: "", caret: 0 });
  });
});

function clipboard(items) {
  return { items };
}
function fileItem(type, name = "x") {
  return { kind: "file", type, getAsFile: () => ({ name, type, size: 10 }) };
}

describe("imageFromClipboard", () => {
  it("이미지 파일이 있으면 첫 장을 돌려준다", () => {
    const f = imageFromClipboard(clipboard([fileItem("image/png", "a.png")]));
    expect(f && f.name).toBe("a.png");
  });

  it("텍스트만 붙여넣으면 null — 평범한 Ctrl+V를 가로채지 않는다", () => {
    expect(imageFromClipboard(clipboard([{ kind: "string", type: "text/plain" }]))).toBeNull();
    expect(imageFromClipboard(clipboard([]))).toBeNull();
    expect(imageFromClipboard(null)).toBeNull();
    expect(imageFromClipboard({})).toBeNull();
  });

  it("허용 목록 밖 파일(PDF 등)은 무시한다 — 채팅 말풍선은 이미지 전용", () => {
    expect(imageFromClipboard(clipboard([fileItem("application/pdf")]))).toBeNull();
    expect(PASTE_IMAGE_TYPES).not.toContain("application/pdf");
  });

  it("텍스트와 이미지가 섞여 오면(브라우저가 흔히 그런다) 이미지를 고른다", () => {
    const f = imageFromClipboard(clipboard([
      { kind: "string", type: "text/html" },
      fileItem("image/jpeg", "shot.jpg"),
    ]));
    expect(f && f.name).toBe("shot.jpg");
  });

  it("getAsFile이 null을 주면(권한 없음 등) 조용히 null", () => {
    const items = [{ kind: "file", type: "image/png", getAsFile: () => null }];
    expect(imageFromClipboard(clipboard(items))).toBeNull();
  });
});

describe("imageRejectReason", () => {
  it("정상 이미지는 사유 없음", () => {
    expect(imageRejectReason({ size: 1024 })).toBeNull();
  });
  it("빈 파일·없는 파일은 막는다", () => {
    expect(imageRejectReason(null)).toMatch(/읽지 못/);
    expect(imageRejectReason({ size: 0 })).toMatch(/빈 파일/);
  });
  it("서버 상한(10MB)을 넘으면 올리기 전에 안내한다", () => {
    expect(imageRejectReason({ size: MAX_IMAGE_BYTES + 1 })).toMatch(/10MB/);
    expect(imageRejectReason({ size: MAX_IMAGE_BYTES })).toBeNull();
  });
});
