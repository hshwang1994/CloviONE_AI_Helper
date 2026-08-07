import React from "react";
import { useSearchParams } from "react-router-dom";

/* 화면 상태(필터·정렬·페이지)를 **URL 쿼리스트링**에 두는 훅.
 *
 * ## 왜 useState 가 아닌가
 *
 * 사용자가 같은 말을 두 화면(티켓 목록·문서 목록)에서 했다: "상세를 보고 돌아오면 필터가
 * 풀린다". 원인은 하나다 — 필터가 `React.useState` 에만 살아서, 화면이 언마운트되는 순간
 * 같이 사라진다. 주소로 옮기면 세 가지가 **한꺼번에** 해결된다: 뒤로가기, 새로고침,
 * 그리고 링크 공유("이 필터로 보라"고 주소를 건네는 일).
 *
 * 관리자 화면은 이미 같은 결론에 도달해 있었다(`screens/datascreen-view.js`). 다만 그쪽은
 * 해시 문자열을 직접 파싱하는 화면 전용 코드라 다른 화면이 가져다 쓸 수 없었다. 이 훅은
 * 라우터의 `useSearchParams` 위에 얹어 어떤 화면이든 쓰게 만든 것이다.
 *
 * ## 상태를 따로 들지 않는다
 *
 * 값을 `useState` 에 복사해 두고 `useEffect` 로 주소와 맞추는 방식(문서 화면의 예전 코드)은
 * 두 개의 진실을 만든다. 그래서 브라우저 뒤로가기처럼 **주소만 바뀌는** 이동에서는 화면이
 * 따라오지 않았다. 여기서는 주소가 유일한 진실이고 상태는 그것을 읽은 값이다.
 *
 * ## 스펙
 *
 * `spec` 은 `{ 키: 기본값 }` 이다. 기본값의 **타입이 곧 파서**다(문자열·숫자·불리언).
 * 기본값과 같은 값은 주소에 쓰지 않는다 — 아무것도 안 고른 화면의 주소가 깨끗해야
 * "지금 필터가 걸려 있나" 를 주소만 보고 알 수 있다.
 *
 * `spec` 은 **모듈 상수로** 넘겨라. 렌더마다 새 객체를 만들면 아래 메모가 매번 깨진다.
 * (그래도 인라인으로 넘어올 수 있으니 첫 값을 ref 에 고정해 둔다 — 조용히 느려지는 것보다
 *  낫다. 스펙을 렌더 도중 바꾸는 화면은 이 저장소에 없다.)
 *
 * 스펙에 **없는** 키는 읽지도 쓰지도 지우지도 않는다. 알림 딥링크(`?id=`)처럼 다른 규약이
 * 실어 둔 값이 필터를 한 번 건드렸다고 사라지면 안 된다.
 */

const NO_RESET = [];

const isNum = (v) => typeof v === "number";
const isBool = (v) => typeof v === "boolean";

/** 쿼리 한 칸을 기본값의 타입대로 읽는다. 못 읽으면 기본값으로 떨어진다. */
function decodeOne(raw, def) {
  if (raw == null) return def;
  if (isBool(def)) return raw === "1" || raw === "true";
  if (isNum(def)) {
    const n = Number.parseInt(raw, 10);
    // 주소에 실리는 숫자는 지금 페이지 번호뿐이고 0 이나 음수는 뜻이 없다. 이상한 값은
    // 거절하지 않고 기본값으로 떨어뜨린다 — 남이 준 링크가 조금 망가졌다고 화면이
    // 오류로 죽는 것보다, 기본 화면이라도 보이는 편이 낫다.
    return Number.isFinite(n) && n >= 1 ? n : def;
  }
  return String(raw);
}

/** URLSearchParams → 스펙 모양의 평범한 객체. */
export function decodeQuery(params, spec) {
  const out = {};
  for (const key of Object.keys(spec)) out[key] = decodeOne(params.get(key), spec[key]);
  return out;
}

function sameAsDefault(value, def) {
  if (isBool(def)) return !!value === !!def;
  if (isNum(def)) return Number(value) === Number(def);
  return String(value == null ? "" : value) === String(def == null ? "" : def);
}

/** 스펙 모양의 객체 → URLSearchParams. `base` 에 있던 **모르는 키는 그대로 둔다**. */
export function encodeQuery(state, spec, base) {
  const next = new URLSearchParams(base || "");
  for (const key of Object.keys(spec)) {
    const def = spec[key];
    const value = state[key];
    if (sameAsDefault(value, def)) { next.delete(key); continue; }
    next.set(key, isBool(def) ? (value ? "1" : "0") : String(value));
  }
  return next;
}

/**
 * `[state, setState]`.
 *
 * `setState(patch)` 는 바꿀 키만 담은 조각을 받는다. `options.reset` 에 적은 키(보통
 * `["page"]`)는 **다른 키를 건드리면 기본값으로 돌아간다** — 필터를 바꿨는데 이전 필터의
 * 3페이지에 머무르면 사용자는 빈 목록을 보고 "필터가 잘못됐다"고 읽는다.
 *
 * 기본은 `replace` 다. 글자 하나·선택 하나마다 히스토리가 쌓이면 뒤로가기 한 번으로
 * 목록을 벗어날 수 없다. 되돌아갈 수 있어야 하는 이동은 `setState(patch, { push: true })`.
 */
export function useQueryState(spec, options) {
  const [sp, setSp] = useSearchParams();
  const specRef = React.useRef(spec);
  const resetRef = React.useRef((options && options.reset) || NO_RESET);
  // 주소 문자열을 메모 키로 쓴다 — 같은 주소면 같은 객체를 돌려줘야 이 값을 의존성으로
  // 쓰는 질의 키와 `React.memo` 가 매 렌더마다 깨지지 않는다.
  const search = sp.toString();
  const state = React.useMemo(
    () => decodeQuery(new URLSearchParams(search), specRef.current),
    [search],
  );
  /* react-router 의 setSearchParams 갱신 함수는 그 훅이 이 컴포넌트를 마지막으로 렌더했을
   * 때 캡처한 옛 검색어를 기준으로 다음 값을 계산한다(react-router-dom useSearchParams:
   * `nextInit(new URLSearchParams(searchParams))`, `searchParams` 는 useCallback 의존성이라
   * 그 렌더에 고정된다) — React의 `setState(prev => ...)` 처럼 "가장 최신" 값을 주지 않는다.
   * 그래서 리렌더 없이 setState 를 두 번 연달아 부르면(같은 핸들러에서 필터 두 개를 바꾸는
   * 식) 두 번째 호출이 첫 번째 호출의 patch 를 못 보고 옛 주소 위에 다시 얹어 먼저 바꾼
   * 값을 조용히 지운다. 우리가 마지막으로 쓴 값을 직접 기억해 두고 그걸 기준으로 삼는다 —
   * 렌더마다 최신 주소로 다시 맞추고(뒤로가기 등 외부 이동을 따라가고), 같은 틱 안의
   * 연속 호출은 서로의 결과를 이어받는다. */
  const pendingRef = React.useRef(search);
  pendingRef.current = search;
  const setState = React.useCallback((patch, opts) => {
    setSp(() => {
      const s = specRef.current;
      const base = new URLSearchParams(pendingRef.current);
      const touched = Object.keys(patch || {});
      const next = { ...decodeQuery(base, s), ...patch };
      const resets = resetRef.current;
      if (touched.some((k) => !resets.includes(k))) {
        for (const k of resets) if (!touched.includes(k)) next[k] = s[k];
      }
      const result = encodeQuery(next, s, base);
      pendingRef.current = result.toString();
      return result;
    }, { replace: !(opts && opts.push) });
  }, [setSp]);
  return [state, setState];
}
