import React from "react";

/* 기본 아바타 — **DiceBear 로 제품이 직접 그린다. 받아 오지 않는다.**
 *
 * ## 왜 로컬 생성인가
 *
 * DiceBear 에는 `api.dicebear.com` 이라는 공개 HTTP API 가 있고, 그것을 쓰면 이 파일이
 * 열 줄로 끝난다. **쓰지 않는다.** 이 제품은 인터넷이 없는 망에도 설치되고, 그때 아바타가
 * 안 그려지는 것은 「기능 하나가 조용히 없다」가 아니라 **모든 목록에서 모든 사람이
 * 사라지는 것**이다. CDN·외부 이미지 URL·외부 폰트도 같은 이유로 안 쓴다.
 *
 * 그래서 `@dicebear/core` 와 스타일 패키지 다섯을 제품 의존성으로 들이고 브라우저 안에서
 * SVG 를 만든다. 만들어진 결과는 `data:` URI 라 네트워크를 한 번도 안 탄다. 운영 서버는
 * 이미 빌드된 번들(`app/static/react/`)만 받으므로 설치 시점에도 npm 이 필요 없다.
 *
 * ## 그림은 **따로 받는다** — 그리고 그것이 이 파일의 구조를 정한다
 *
 * 스타일 다섯의 SVG 경로 데이터는 gzip 284KB 다. 그것을 진입 번들에 넣으면 초기 예산
 * 320KB 를 그것 하나로 거의 다 써버린다(`scripts/check_bundle_size.sh` 실측: 45KB → 324KB).
 * 아바타는 **그림**이지 배치가 아니므로, 첫 페인트를 그것 때문에 기다릴 이유가 없다.
 *
 * 그래서 이 파일은 둘로 나뉜다.
 *
 *   · **이름과 배정은 동기다.** 어느 스타일인지, 어느 변형인지는 문자열 계산이라 무게가
 *     없다. 저장·검증·후보 목록이 전부 이 축에서 돈다.
 *   · **그림만 지연이다.** 스타일 모듈은 `import()` 로 한 번 받고 그 뒤로는 메모리에
 *     남는다. 도착하기 전에는 **씨앗에서 뽑은 색 원**이 선다 — 빈 구멍이 아니라 이미
 *     그 사람의 자리다.
 *
 * 묶음(`@dicebear/collection`)에서 꺼내지 않는 이유도 같은 축이다: 그 배럴은 스타일
 * 서른한 개를 namespace 로 다시 내보내서 쓰지 않는 스물여섯 개까지 함께 실린다.
 *
 * ## `<img src>` 이지 `innerHTML` 이 아니다
 *
 * SVG 문자열을 `dangerouslySetInnerHTML` 로 꽂으면 이 저장소가 여러 번 금지한 그 모양이
 * 된다(§6). 지금 그 문자열은 우리 코드가 씨앗 하나로 만든 것이라 안전하지만, **안전한
 * 자리에 그 관용을 한 번 들이면 다음 사람이 안 안전한 자리에 복사한다.** `data:` URI 로
 * 내보내면 그럴 자리가 애초에 없다(CSP 의 `img-src 'self' data: blob: https:` 안이다).
 *
 * ## 스타일은 CC0 만 쓴다
 *
 * 아래 다섯은 전부 **CC0 1.0** 이다 — 값은 지어낸 것이 아니라 패키지가 스스로 신고하는
 * `style.meta.license` 이고, `default-avatar-keys-match-backend.test.js` 가 실행 시점에
 * 그것을 다시 읽어 확인한다. 상업적 사용이 되는 라이선스는 더 있지만(CC BY 4.0 계열),
 * 그쪽은 **표시 의무**가 따라온다 — 화면 어딘가에 저작자 표시를 유지해야 하고, 그 의무는
 * 다음 회차에 조용히 잊힌다. CC0 은 그 부담이 없다.
 */

/* 스타일의 **이름**은 여기 있고 그림은 아래에서 따로 받는다. 이름이 동기여야 저장값을
 * 검증하고 후보 목록을 만드는 일이 첫 페인트에서 바로 된다. */
const STYLE_LIST = [
  ["lorelei", "사람 (선화)"],
  ["notionists", "사람 (스케치)"],
  ["openPeeps", "사람 (손그림)"],
  ["pixelArt", "픽셀"],
  ["thumbs", "형태"],
];

export const DEFAULT_AVATAR_STYLES = STYLE_LIST.map(([key]) => key);

/** 사람이 고를 때 화면에 쓰는 이름. */
export const DEFAULT_AVATAR_STYLE_LABELS = Object.fromEntries(STYLE_LIST);

/* 고른 값의 모양은 `<style>:<variant>` 다.
 *
 * 스타일만 저장하면 「같은 스타일 안에서 다른 얼굴」을 고를 수 없다 — 그러면 후보가
 * 다섯 개뿐인 셈이고, 이 회차가 없애려던 「고정 여덟 종」과 같은 제약이 된다.
 * `variant` 는 씨앗을 흔드는 수라서, 스타일 하나에 후보가 1,000 개 있다. */
export const AVATAR_VARIANT_MAX = 999;
const KEY_RE = /^([A-Za-z]+):(\d{1,3})$/;

/** 저장된 값을 스타일과 변형으로 가른다. 모르는 값이면 `null` — 지어내지 않는다. */
export function parseAvatarKey(key) {
  const m = KEY_RE.exec(String(key || ""));
  if (!m) return null;
  if (!DEFAULT_AVATAR_STYLES.includes(m[1])) return null;
  if (Number(m[2]) > AVATAR_VARIANT_MAX) return null;
  return { style: m[1], variant: Number(m[2]) };
}

export function formatAvatarKey(style, variant) {
  return `${style}:${Math.max(0, Math.min(AVATAR_VARIANT_MAX, Number(variant) || 0))}`;
}

/* 씨앗 → 정수. 문자열 해시는 **안정적이어야 한다** — 세션마다 다른 값이 나오면 같은
 * 사람이 화면마다 다른 그림을 갖는다. FNV-1a 는 짧고 결정적이다. */
function hashSeed(seed) {
  let h = 0x811c9dc5;
  const s = String(seed || "");
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h >>> 0;
}

/** 이 사람이 아무것도 안 골랐을 때의 그림. **user UUID 하나가 정한다.**
 *
 * 같은 사람은 로그인·재부팅·재배포·업그레이드 뒤에도 같은 그림이다 — 여기 들어가는 것이
 * 시계도 난수도 아니라 그 사람의 id 뿐이기 때문이다. */
export function autoAvatarKey(seed) {
  const h = hashSeed(seed);
  const style = DEFAULT_AVATAR_STYLES[h % DEFAULT_AVATAR_STYLES.length];
  // 스타일과 **다른 자리의 비트**를 쓴다 — 둘이 함께 움직이면 조합이 다섯 줄로 줄어든다.
  return formatAvatarKey(style, (h >>> 7) % (AVATAR_VARIANT_MAX + 1));
}

/** 이 사람에게 실제로 그릴 그림. 고른 값이 있으면 그것이, 없으면 id 가 정한 것이 이긴다. */
export function resolveAvatarKey(seed, chosen) {
  return parseAvatarKey(chosen) ? String(chosen) : autoAvatarKey(seed);
}

/** 그림이 오기 전에 서는 색. 씨앗에서 뽑으므로 **그 사람의 자리**이지 빈 구멍이 아니다. */
export function placeholderColor(seed) {
  const h = hashSeed(seed);
  // 채도·명도를 낮게 고정한다 — 목록 한 줄에 스무 개가 서므로 원색이면 화면이 그것으로 덮인다.
  return `hsl(${h % 360}deg 42% 86%)`;
}

/* ── 그림 (지연) ────────────────────────────────────────────────────────────
 *
 * 모듈은 **한 번만** 받는다. 받는 동안 두 번째·세 번째 아바타가 또 부르지 않게 약속을
 * 들고 있고, 도착하면 기다리던 컴포넌트 전부에 알린다. */
let STYLES = null;
let PENDING = null;
const WAITING = new Set();

function loadStyles() {
  if (STYLES) return Promise.resolve(STYLES);
  if (!PENDING) {
    PENDING = Promise.all([
      import("@dicebear/core"),
      import("@dicebear/lorelei"),
      import("@dicebear/notionists"),
      import("@dicebear/open-peeps"),
      import("@dicebear/pixel-art"),
      import("@dicebear/thumbs"),
    ]).then(([core, lorelei, notionists, openPeeps, pixelArt, thumbs]) => {
      STYLES = {
        createAvatar: core.createAvatar,
        byKey: { lorelei, notionists, openPeeps, pixelArt, thumbs },
      };
      for (const notify of WAITING) notify();
      WAITING.clear();
      return STYLES;
    });
  }
  return PENDING;
}

/** 스타일이 실제로 신고하는 라이선스. 시험이 이 값을 읽어 확인한다. */
export async function loadAvatarLicenses() {
  const loaded = await loadStyles();
  return Object.fromEntries(
    DEFAULT_AVATAR_STYLES.map((key) => [key, loaded.byKey[key].meta.license.name]),
  );
}

/** 그림이 준비될 때까지 기다린다. 시험과 미리 받아 두려는 자리가 쓴다. */
export function preloadAvatarStyles() {
  return loadStyles();
}

/* 만든 그림은 **다시 만들지 않는다.**
 *
 * 목록 한 화면에 아바타가 200개고, 스크롤할 때마다 그 200개가 다시 그려진다. SVG 생성은
 * 공짜가 아니라서 그대로 두면 굴릴 때 눈에 띄게 끊긴다. 키가 같으면 결과도 같으므로
 * (그것이 이 파일의 계약이다) 한 번 만든 것을 그대로 쓴다.
 *
 * 상한에 닿으면 통째로 비운다 — LRU 를 흉내 내는 것보다 정직하고, 비운 뒤의 비용은
 * 「한 번 더 만든다」뿐이다. */
const CACHE = new Map();
const CACHE_LIMIT = 400;

/** 아바타 하나의 `data:` URI. 스타일이 아직 안 왔으면 `null`. 네트워크를 타지 않는다. */
export function avatarDataUri(seed, chosen) {
  if (!STYLES) return null;
  const key = resolveAvatarKey(seed, chosen);
  const cacheKey = `${key}|${seed}`;
  const hit = CACHE.get(cacheKey);
  if (hit) return hit;
  const parsed = parseAvatarKey(key);
  const made = STYLES.createAvatar(STYLES.byKey[parsed.style], {
    // 변형이 씨앗을 흔든다 — 같은 사람이 같은 스타일 안에서 다른 얼굴을 고를 수 있다.
    seed: `${seed}#${parsed.variant}`,
    size: 128,
  }).toDataUri();
  if (CACHE.size >= CACHE_LIMIT) CACHE.clear();
  CACHE.set(cacheKey, made);
  return made;
}

/** 스타일이 도착하면 다시 그린다. 이미 와 있으면 아무 일도 안 한다. */
function useAvatarStyles() {
  const [, bump] = React.useReducer((n) => n + 1, 0);
  React.useEffect(() => {
    if (STYLES) return undefined;
    WAITING.add(bump);
    loadStyles();
    return () => WAITING.delete(bump);
  }, []);
  return STYLES;
}

/** 기본 아바타 한 장. 크기는 부모가 정한다(`width`·`height` 100%). */
export function DefaultAvatar({ seed, avatarKey, title }) {
  useAvatarStyles();
  const key = resolveAvatarKey(seed, avatarKey);
  const src = avatarDataUri(seed, key);
  if (!src) {
    /* 그림이 오기 전. **빈 구멍이 아니라 그 사람의 색**이다 — 목록에서 줄마다 회색
       원이 깜빡이면 그것이 로딩인지 사진 없는 사람인지 구별되지 않는다. */
    return (
      <span
        aria-hidden="true"
        data-avatar-pending={key}
        style={{ display: "block", width: "100%", height: "100%", backgroundColor: placeholderColor(seed) }}
      />
    );
  }
  return (
    <img
      src={src}
      alt={title || ""}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : "true"}
      draggable={false}
      data-avatar-key={key}
      style={{ width: "100%", height: "100%", display: "block", objectFit: "cover" }}
    />
  );
}
