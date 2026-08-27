import { describe, it, expect, beforeAll } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  AVATAR_VARIANT_MAX,
  DEFAULT_AVATAR_STYLES,
  DEFAULT_AVATAR_STYLE_LABELS,
  autoAvatarKey,
  avatarDataUri,
  loadAvatarLicenses,
  parseAvatarKey,
  placeholderColor,
  preloadAvatarStyles,
  resolveAvatarKey,
} from "./DefaultAvatar.jsx";

/* 기본 아바타는 **DiceBear 로 브라우저 안에서 만든다.**
 *
 * 여기서 지키는 것은 다섯이다.
 *
 * 1. **스타일 어휘가 서버와 같다.** 갈라지면 화면에만 있는 값을 고를 때 서버가 거절하고,
 *    서버에만 있는 값이 저장돼 있으면 화면이 그 사람에게 아무 그림도 못 그린다. 둘 다
 *    오류 화면 없이 조용히 잘못된다.
 * 2. **라이선스가 CC0 다.** 값을 여기 손으로 옮겨 적지 않고 패키지가 스스로 신고하는
 *    `meta.license` 를 읽는다 — 옮겨 적으면 패키지가 바뀐 날 이 시험도 같이 통과한다.
 * 3. **배정이 안정적이다.** 같은 사람은 로그인·재부팅·재배포 뒤에도 같은 그림이다.
 * 4. **네트워크를 안 탄다.** 만들어진 것이 `data:` URI 여야 폐쇄망에서 그려진다.
 * 5. **그림이 오기 전에도 자리가 있다.** 그 자리의 색도 씨앗에서 나온다.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MODELS = path.resolve(HERE, "../../../app/profiles/models.py");
const SEED = "3bac5c5a-5684-8187-9dec-f71de8c1d024";

function backendStyles() {
  const source = fs.readFileSync(MODELS, "utf-8");
  const m = source.match(/AVATAR_DEFAULT_STYLES:\s*tuple\[str, \.\.\.\]\s*=\s*\(([\s\S]*?)\)/);
  if (!m) throw new Error("AVATAR_DEFAULT_STYLES 를 app/profiles/models.py 에서 못 찾았다");
  return (m[1].match(/"([A-Za-z]+)"/g) || []).map((s) => s.replace(/"/g, ""));
}

function backendVariantMax() {
  const source = fs.readFileSync(MODELS, "utf-8");
  const m = source.match(/AVATAR_VARIANT_MAX\s*=\s*(\d+)/);
  if (!m) throw new Error("AVATAR_VARIANT_MAX 를 app/profiles/models.py 에서 못 찾았다");
  return Number(m[1]);
}

describe("어휘가 서버와 같다", () => {
  it("🔴 화면의 스타일 목록과 서버의 목록이 같다", () => {
    expect([...DEFAULT_AVATAR_STYLES].sort()).toEqual(backendStyles().sort());
  });

  it("변형 상한도 같다 — 화면이 고른 값을 서버가 거절하면 안 된다", () => {
    expect(AVATAR_VARIANT_MAX).toBe(backendVariantMax());
  });

  it("모든 스타일에 사람이 읽을 이름이 있다 — 고를 때 화면에 쓴다", () => {
    for (const style of DEFAULT_AVATAR_STYLES) {
      expect(DEFAULT_AVATAR_STYLE_LABELS[style], `${style} 의 이름이 없다`).toBeTruthy();
    }
  });
});

describe("라이선스", () => {
  it("🔴 쓰는 스타일이 전부 CC0 다 — 표시 의무가 따라오는 것은 안 쓴다", async () => {
    // 값은 패키지가 스스로 신고하는 것이다(`style.meta.license`). 여기 적어 두면
    // 패키지가 바뀐 날 이 시험도 같이 통과해 버린다.
    const licenses = await loadAvatarLicenses();
    for (const style of DEFAULT_AVATAR_STYLES) {
      expect(licenses[style], `${style} 의 라이선스`).toBe("CC0 1.0");
    }
  });
});

describe("배정은 안정적이다", () => {
  it("🔴 같은 사람은 언제 물어도 같은 그림이다", () => {
    // 로그인·재부팅·재배포마다 바뀌면 그것은 식별 요소가 아니라 장식이다.
    const first = autoAvatarKey(SEED);
    for (let i = 0; i < 50; i++) expect(autoAvatarKey(SEED)).toBe(first);
  });

  it("사람이 다르면 스타일도 변형도 갈린다", () => {
    const styles = new Set();
    const keys = new Set();
    for (let i = 0; i < 300; i++) {
      const key = autoAvatarKey(`user-${i}`);
      styles.add(parseAvatarKey(key).style);
      keys.add(key);
    }
    expect(styles.size).toBe(DEFAULT_AVATAR_STYLES.length);
    // 조합이 스타일 수에 갇히지 않는다 — 그것이 「고정 여덟 종」을 없앤 이유다.
    expect(keys.size).toBeGreaterThan(DEFAULT_AVATAR_STYLES.length * 10);
  });

  it("직접 고른 값이 이긴다", () => {
    expect(resolveAvatarKey(SEED, "pixelArt:37")).toBe("pixelArt:37");
  });

  it("모르는 값은 무시하고 씨앗으로 돌아간다 — 빈 원을 만들지 않는다", () => {
    for (const bad of ["unicorn:1", "pixelArt", "pixelArt:9999", "", null]) {
      expect(parseAvatarKey(bad)).toBeNull();
      expect(resolveAvatarKey(SEED, bad)).toBe(autoAvatarKey(SEED));
    }
  });
});

describe("그림이 오기 전에도 자리가 있다", () => {
  it("🔴 자리의 색도 씨앗에서 나온다 — 같은 사람은 같은 색이다", () => {
    expect(placeholderColor(SEED)).toBe(placeholderColor(SEED));
    expect(placeholderColor(SEED)).not.toBe(placeholderColor("다른 사람"));
    expect(placeholderColor(SEED)).toMatch(/^hsl\(/);
  });
});

describe("폐쇄망에서 그려진다", () => {
  beforeAll(async () => {
    // 그림은 지연 청크다 — 받은 뒤에야 만들 수 있다(초기 예산을 지키는 값이다).
    await preloadAvatarStyles();
  });

  it("🔴 만들어진 아바타가 `data:` URI 다 — 네트워크를 한 번도 안 탄다", () => {
    const uri = avatarDataUri(SEED, null);
    expect(uri.startsWith("data:image/svg+xml")).toBe(true);
    // 외부 주소가 한 글자도 안 들어간다. 들어가면 인터넷 없는 망에서 얼굴이 전부 사라진다.
    expect(uri).not.toMatch(/https?:\/\/(?!www\.w3\.org)/);
  });

  it("스타일 다섯이 전부 실제로 그려진다 — 이름만 있고 그림이 없는 것이 없다", () => {
    for (const style of DEFAULT_AVATAR_STYLES) {
      const uri = avatarDataUri(SEED, `${style}:1`);
      expect(uri, `${style} 이 안 그려졌다`).toBeTruthy();
      expect(uri.length, `${style} 이 빈 그림이다`).toBeGreaterThan(200);
    }
  });

  it("같은 키는 같은 그림을 낸다 — 캐시가 사람을 바꾸지 않는다", () => {
    expect(avatarDataUri(SEED, "lorelei:5")).toBe(avatarDataUri(SEED, "lorelei:5"));
    expect(avatarDataUri(SEED, "lorelei:5")).not.toBe(avatarDataUri(SEED, "lorelei:6"));
  });
});
