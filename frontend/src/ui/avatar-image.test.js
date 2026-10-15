import { describe, it, expect, vi } from "vitest";
import { AvatarImageCache, avatarSourceKey } from "./avatarImage.js";
import { preloadAvatarStyles } from "./DefaultAvatar.jsx";

/* 캔버스용 얼굴 그림 (D-577) — DOM 의 `UserAvatar` 와 같은 규칙: 사진 주소가 있으면 그것, 없으면 그 사람 id 로 배정한 기본 그림.
 * 한 사람의 그림은 한 번만 받고, 실패하면 `error` 로 물러나며(부르는 쪽이 색 원 + 머리글자), 상태가 바뀌면 구독자에게 알리고, 256 개를
 * 넘으면 오래 안 쓴 것부터 버린다. */

function fakeImageFactory() {
  const made = [];
  const createImage = () => {
    const img = { decoding: "", onload: null, onerror: null, _src: "" };
    Object.defineProperty(img, "src", { get: () => img._src, set: (v) => { img._src = v; } });
    made.push(img);
    return img;
  };
  return { made, createImage };
}

describe("열쇠", () => {
  it("사진 주소가 있으면 그것, 없으면 기본 그림 키 + 씨앗, 사람이 아니면 없음", () => {
    expect(avatarSourceKey({ user_id: "u1", avatar_url: "/api/profile/avatar/u1?v=3" })).toBe("url:/api/profile/avatar/u1?v=3");
    expect(avatarSourceKey({ user_id: "u1", avatar_default_key: "thumbs:12" })).toBe("dice:thumbs:12|u1");
    expect(avatarSourceKey({ user_id: "u1" })).toMatch(/^dice:[a-zA-Z]+:\d+\|u1$/);
    expect(avatarSourceKey({ name: "자유 이름" })).toBeNull();
  });
});

describe("저장소", () => {
  it("사진은 한 번만 받고, 다 받으면 ready + 알림", () => {
    const { made, createImage } = fakeImageFactory();
    const cache = new AvatarImageCache({ createImage });
    const seen = vi.fn();
    cache.subscribe(seen);
    const p = { user_id: "u1", avatar_url: "/a.png" };
    expect(cache.get(p).status).toBe("loading");
    expect(cache.get(p).status).toBe("loading");
    expect(made).toHaveLength(1);
    expect(made[0].src).toBe("/a.png");
    expect(made[0].decoding).toBe("async");
    made[0].onload();
    expect(cache.get(p)).toMatchObject({ status: "ready", img: made[0] });
    expect(seen).toHaveBeenCalledTimes(1);
  });

  it("실패하면 error — 깨진 그림 대신 부르는 쪽이 색 원으로 물러난다", () => {
    const { made, createImage } = fakeImageFactory();
    const cache = new AvatarImageCache({ createImage });
    const p = { user_id: "u2", avatar_url: "/gone.png" };
    cache.get(p);
    made[0].onerror();
    expect(cache.get(p)).toMatchObject({ status: "error", img: null });
  });

  it("자유 이름(사람이 아님)은 그림이 없다", () => {
    const cache = new AvatarImageCache({ createImage: () => { throw new Error("부르면 안 된다"); } });
    expect(cache.get({ name: "김하나" })).toEqual({ img: null, status: "none" });
  });

  it("사진이 없는 사람은 기본 그림(data: URI)을 받는다", async () => {
    await preloadAvatarStyles();
    const { made, createImage } = fakeImageFactory();
    const cache = new AvatarImageCache({ createImage });
    cache.get({ user_id: "u3" });
    expect(made).toHaveLength(1);
    expect(made[0].src).toMatch(/^data:image\/svg\+xml/);
  });

  it("상한을 넘으면 오래 안 쓴 것부터 버린다", () => {
    const { createImage } = fakeImageFactory();
    const cache = new AvatarImageCache({ createImage, limit: 3 });
    for (const i of [1, 2, 3]) cache.get({ user_id: `u${i}`, avatar_url: `/${i}.png` });
    cache.get({ user_id: "u1", avatar_url: "/1.png" }); // 다시 썼다 — 가장 최근
    cache.get({ user_id: "u4", avatar_url: "/4.png" });
    expect(cache.entries.size).toBe(3);
    expect(cache.entries.has("url:/2.png")).toBe(false);
    expect(cache.entries.has("url:/1.png")).toBe(true);
  });
});
