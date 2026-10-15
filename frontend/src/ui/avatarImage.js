import { avatarDataUri, preloadAvatarStyles, resolveAvatarKey } from "./DefaultAvatar.jsx";

/* 캔버스용 얼굴 그림 (D-577) — DOM 의 `UserAvatar` 와 **같은 얼굴**을 캔버스가 그릴 수 있게 `HTMLImageElement` 로 준다.
 *
 * 규칙은 `UserAvatar` 와 같다: 사진 주소(`avatar_url`)가 있으면 그것, 없으면 그 사람 id 로 배정한(또는 직접 고른) 기본 그림의
 * `data:` URI(`DefaultAvatar.avatarDataUri`). 기본 그림 모듈은 지연 로딩이라 처음 한 번은 `preloadAvatarStyles()` 를 기다린다.
 * 사진이 404 · 오류면 상태가 `error` 가 되고, 부르는 쪽(구슬 스프라이트)은 색 원 + 머리글자로 물러난다 — 깨진 그림 아이콘을
 * 그리지 않는다.
 *
 * 한 사람의 그림은 한 번만 받는다(주소 열쇠). 상한 256 을 넘으면 오래된 것부터 버린다. 상태가 바뀌면 구독자에게 알린다 —
 * 캔버스는 그때 스프라이트를 다시 만든다. 그림은 `decoding="async"` 로 받아 그리기 스레드를 막지 않는다. */

export const AVATAR_IMAGE_LIMIT = 256;

/** 사람 하나의 그림 주소 열쇠 — 사진이 있으면 그 주소, 없으면 기본 그림의 키(스타일:변형)와 씨앗. */
export function avatarSourceKey(person) {
  const p = person || {};
  if (p.avatar_url) return `url:${p.avatar_url}`;
  const seed = p.user_id || p.id || "";
  if (!seed) return null;
  return `dice:${resolveAvatarKey(seed, p.avatar_default_key)}|${seed}`;
}

export class AvatarImageCache {
  constructor({ limit = AVATAR_IMAGE_LIMIT, createImage } = {}) {
    this.limit = limit;
    this.entries = new Map(); // key → { img, status }
    this.listeners = new Set();
    this.createImage = createImage || (() => (typeof Image === "function" ? new Image() : null));
    this.stylesReady = false;
    this.stylesPending = null;
  }

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  notify() {
    for (const fn of this.listeners) {
      try { fn(); } catch (e) { /* 구독자 오류는 다른 구독자를 막지 않는다 */ }
    }
  }

  /** `{ img, status }` — status 는 `loading` · `ready` · `error` · `none`(얼굴을 정할 수 없는 사람: 자유 이름). */
  get(person) {
    const key = avatarSourceKey(person);
    if (!key) return { img: null, status: "none" };
    const hit = this.entries.get(key);
    if (hit) {
      // 최근에 쓴 것을 뒤로 — 상한에서 버리는 순서가 「오래 안 쓴 것」이 된다.
      this.entries.delete(key);
      this.entries.set(key, hit);
      return hit;
    }
    const entry = { img: null, status: "loading" };
    this.entries.set(key, entry);
    this.trim();
    this.load(key, person, entry);
    return entry;
  }

  trim() {
    while (this.entries.size > this.limit) {
      const oldest = this.entries.keys().next().value;
      this.entries.delete(oldest);
    }
  }

  load(key, person, entry) {
    const p = person || {};
    const start = (src) => {
      const img = this.createImage();
      if (!img || !src) {
        entry.status = "error";
        this.notify();
        return;
      }
      try { img.decoding = "async"; } catch (e) { /* 오래된 브라우저 */ }
      img.onload = () => { entry.img = img; entry.status = "ready"; this.notify(); };
      img.onerror = () => { entry.img = null; entry.status = "error"; this.notify(); };
      img.src = src;
    };
    if (p.avatar_url) {
      start(p.avatar_url);
      return;
    }
    const seed = p.user_id || p.id || "";
    const make = () => start(avatarDataUri(seed, p.avatar_default_key));
    const now = avatarDataUri(seed, p.avatar_default_key);
    if (now) {
      start(now);
      return;
    }
    if (!this.stylesPending) {
      this.stylesPending = Promise.resolve(preloadAvatarStyles()).then(() => { this.stylesReady = true; });
    }
    this.stylesPending.then(make, () => { entry.status = "error"; this.notify(); });
  }
}

/** 앱 하나에 하나 — 구슬 스프라이트 · 선두 칩이 같은 그림을 나눠 쓴다. */
export const avatarImages = new AvatarImageCache();
