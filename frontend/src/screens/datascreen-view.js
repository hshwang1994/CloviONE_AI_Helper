/* 목록 화면의 '지금 보고 있는 뷰' ↔ URL 쿼리 변환 (순수 함수).
 *
 * 왜 URL 인가: 관리자 화면들은 이미 필터를 **API URL** 로 조립한다(DataScreen 의 buildUrl).
 * 그런데 **화면 주소**에는 그 상태가 안 남아 있어서, 같은 필터를 다시 보려면 매번 손으로
 * 다시 골라야 했고 동료에게 "감사 로그에서 이 사람 로그인 실패만 봐" 라고 링크를 줄 수도
 * 없었다. 여기서 화면 주소에도 같은 상태를 실으면 두 가지가 한꺼번에 해결된다:
 *   1) **저장된 뷰**는 그냥 이 쿼리 문자열을 이름 붙여 보관하는 일이 된다(서버는 값을
 *      해석하지 않는다 — 화면의 필터 정의가 바뀌어도 저장된 뷰를 고칠 필요가 없다).
 *   2) **링크 공유**가 공짜로 따라온다. 주소를 복사해 주면 상대가 같은 화면을 본다.
 *
 * 해시 라우터라 화면 주소는 `#/audit?action=user.login` 모양이다. `?` 앞이 라우트 경로이고
 * 뒤가 이 파일이 다루는 부분이다.
 *
 * **아는 키만 다룬다.** config.filters 에 정의된 키와 `q`/`page` 뿐이다. 모르는 키(예:
 * 다른 화면이 딥링크로 넘긴 `?id=`)는 읽지도 쓰지도 않는다 — 그건 DataScreen 의
 * config.onQuery 가 소비하고 지우는 별개의 규약이다.
 */

/** 해시 문자열에서 `?` 뒤 쿼리만. 없으면 "". */
export function hashQuery(hash) {
  const raw = String(hash || "");
  const at = raw.indexOf("?");
  return at < 0 ? "" : raw.slice(at + 1);
}

/** 해시 문자열에서 `?` 앞 경로만(선행 `#` 포함). */
export function hashPath(hash) {
  const raw = String(hash || "");
  const at = raw.indexOf("?");
  return at < 0 ? raw : raw.slice(0, at);
}

/** config.filters 의 키 집합. filters 가 없으면 빈 배열. */
function filterKeys(config) {
  return ((config && config.filters) || []).map((f) => f.key).filter(Boolean);
}

/**
 * 쿼리 문자열 → { q, page, filters }.
 * 값이 비었거나 모르는 키는 버린다. page 는 1 이상 정수만 인정한다(그 외는 1).
 */
export function parseView(query, config) {
  const known = filterKeys(config);
  const out = { q: "", page: 1, filters: {} };
  let params;
  try {
    params = new URLSearchParams(String(query || ""));
  } catch (e) {
    return out;
  }
  params.forEach((value, key) => {
    if (!value) return;
    if (key === "q") { out.q = value; return; }
    if (key === "page") {
      const n = parseInt(value, 10);
      if (Number.isFinite(n) && n >= 1) out.page = n;
      return;
    }
    if (known.includes(key)) out.filters[key] = value;
  });
  return out;
}

/**
 * { q, page, filters } → 쿼리 문자열.
 *
 * 기본값은 싣지 않는다 — `page=1` 이나 빈 검색어까지 주소에 붙으면, 아무것도 안 건드린
 * 사람의 주소가 계속 길어지고 '기본 화면'과 '기본값을 고른 화면'이 서로 다른 링크가 된다.
 * 키 순서는 config.filters 순서를 따른다(같은 뷰가 항상 같은 문자열이 되어야 저장된 뷰의
 * 중복 판정과 링크 비교가 흔들리지 않는다).
 */
export function buildViewQuery(view, config) {
  const parts = [];
  const q = (view && view.q) || "";
  if (q) parts.push("q=" + encodeURIComponent(q));
  const filters = (view && view.filters) || {};
  filterKeys(config).forEach((key) => {
    const value = filters[key];
    if (value == null || value === "") return;
    parts.push(key + "=" + encodeURIComponent(value));
  });
  const page = (view && view.page) || 1;
  if (page > 1) parts.push("page=" + page);
  return parts.join("&");
}

/* 그릇(탭 셸)이 소유한 쿼리 키 — 목록 화면은 이 키를 **읽지도 지우지도 않는다**.
 *
 * 목록 화면은 자기 뷰를 주소에 되쓰고(withHashQuery), 딥링크 쿼리를 한 번 쓰고 지운다.
 * 둘 다 예전에는 쿼리 **전체**를 다뤘다 — 그래서 목록을 탭 그릇 안에 넣는 순간 필터를 한 칸
 * 건드리거나 딥링크로 들어오는 것만으로 `?tab=` 이 사라지고 화면이 첫 탭으로 튕겼다. */
export const SHELL_QUERY_KEYS = ["tab"];

/** 쿼리 문자열에서 주어진 키만 **원문 그대로** 남긴다(재직렬화하지 않는다). */
export function keepQueryKeys(query, keys) {
  const kept = [];
  for (const part of String(query || "").split("&")) {
    if (!part) continue;
    let key = part.split("=")[0];
    try { key = decodeURIComponent(key); } catch (e) { /* 깨진 조각은 원문 키로 비교한다 */ }
    if (keys.includes(key)) kept.push(part);
  }
  return kept.join("&");
}

/** 이 화면이 **자기 것이라고 주장하는** 쿼리 키. 나머지는 남의 규약이다. */
export function ownedQueryKeys(config) {
  return ["q", "page", ...filterKeys(config)];
}

/** 경로는 그대로 두고 쿼리만 바꾼 새 해시 문자열.
 *
 * `ownedKeys` 를 주면 **그 키들만 갈아치우고 나머지는 그대로 둔다.** 목록 화면이 탭 그릇
 * 안에서 그려질 때 필요하다 — 예전에는 쿼리 전체를 자기 뷰로 덮어써서, 필터를 한 칸
 * 건드리는 순간 그릇이 쓴 `?tab=…` 이 사라지고 화면이 첫 탭으로 튕겼다.
 *
 * 보존하는 조각은 **원문 그대로** 다시 붙인다(다시 파싱해 직렬화하지 않는다). URLSearchParams
 * 는 공백을 `+` 로 쓰는데 이 화면들의 뷰 문자열은 `encodeURIComponent`(`%20`)로 만들어져
 * 있어서, 왕복시키면 같은 뷰가 다른 문자열이 된다 — 저장된 뷰의 중복 판정과 링크 비교가
 * 그 문자열을 그대로 쓴다. */
export function withHashQuery(hash, query, ownedKeys) {
  const path = hashPath(hash) || "#";
  if (!ownedKeys) return query ? path + "?" + query : path;
  const kept = [];
  for (const part of hashQuery(hash).split("&")) {
    if (!part) continue;
    let key = part.split("=")[0];
    try { key = decodeURIComponent(key); } catch (e) { /* 깨진 조각은 원문 키로 비교한다 */ }
    if (!ownedKeys.includes(key)) kept.push(part);
  }
  // 화면 소유 키가 앞이다 — 저장된 뷰 문자열이 그 순서를 전제한다(buildViewQuery 주석).
  const merged = [query, ...kept].filter(Boolean).join("&");
  return merged ? path + "?" + merged : path;
}

/**
 * 저장된 뷰의 사람용 요약 — "검색 '실패' · 상태: 실패 · 2쪽".
 *
 * 이름만 보고는 그 뷰가 무엇인지 잊는다(석 달 뒤의 '내 뷰 2'). 목록 옆에 실제 조건을
 * 한 줄로 적어 두면 지울지 말지 판단할 수 있다. 라벨은 config.filters 의 label 을 쓰고,
 * select 필터는 options 에서 표시 문구를 찾아 준다 — 원시 값('failed')만 보이면 화면에서
 * 고른 것('실패')과 다른 말로 읽힌다.
 */
export function describeView(query, config) {
  const view = parseView(query, config);
  const bits = [];
  if (view.q) bits.push(`검색 "${view.q}"`);
  ((config && config.filters) || []).forEach((f) => {
    const value = view.filters[f.key];
    if (value == null || value === "") return;
    // options 는 배열이지만 화면에 따라 함수(optionsFrom)나 undefined 일 수 있다 —
    // 요약 한 줄 때문에 목록 화면이 통째로 크래시하면 안 된다.
    const options = Array.isArray(f.options) ? f.options : [];
    const option = options.find((o) => o && String(o.value) === String(value));
    bits.push(`${f.label || f.key}: ${option ? option.label : value}`);
  });
  if (view.page > 1) bits.push(`${view.page}쪽`);
  return bits.join(", ");
}
