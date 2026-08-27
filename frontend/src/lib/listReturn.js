import React from "react";
import { useLocation } from "react-router-dom";

/* 목록 → 상세 → 수정 → 뒤로. **돌아오면 있던 그대로여야 한다** (지시 19).
 *
 * ## 무엇이 문제였나
 *
 * 상세 화면의 「목록」이 `nav("/my-tickets")` 였다. 경로만 적고 질의 문자열은 안 적으니
 * 걸어 둔 조건·정렬·페이지가 통째로 사라졌고, 팀 티켓에서 들어온 사람도 내 티켓으로
 * 떨어졌다. 스크롤은 아무 데서도 기억하지 않아서 200번째 줄을 열어 본 사람은 매번 맨
 * 위에서 다시 내려와야 했다.
 *
 * ## 왜 화면마다 안 고치는가
 *
 * 이 문제는 화면 하나의 문제가 아니라 **화면 사이의 문제**다. 목록이 자기 주소를 적고
 * 상세가 그 주소를 읽어야 하는데, 그 둘은 서로를 모른다. 화면마다 전역변수를 하나씩
 * 만들면 화면 수만큼 규칙이 갈라지고, 새 목록 화면이 생길 때마다 또 빠진다.
 *
 * ## 무엇을 기억하는가
 *
 * **주소 하나와 스크롤 하나**다. 조건·정렬·페이지·검색·탭은 이미 전부 질의 문자열에
 * 있으므로(`useQueryState`) 주소를 기억하면 그것이 함께 온다 — 값을 따로 복사해 두면
 * 두 벌이 되고, 두 벌은 갈라진다.
 *
 * 저장소는 `sessionStorage` 다. 탭을 닫으면 사라지는 것이 맞고(다음에 열 때 남의 조건이
 * 걸려 있으면 안 된다), 새로고침은 견딘다. 못 쓰는 브라우저(프라이빗 모드)에서는 조용히
 * 예전처럼 동작한다 — 기억이 없으면 `fallback` 으로 간다.
 */

const KEY = "cv.listReturn.v1";

/* 기억해 두는 목록 수. 사용자가 오가는 목록은 많아야 서넛이고, 무한히 쌓아 두면 오래전
 * 페이지 번호가 몇 주 뒤에 되살아난다. */
const LIMIT = 8;

function readAll() {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    const obj = raw ? JSON.parse(raw) : null;
    return obj && typeof obj === "object" ? obj : {};
  } catch {
    return {};
  }
}

/* 「최근」의 정본은 시계가 아니라 **번호**다.
 *
 * `Date.now()` 로 순서를 매기면 같은 밀리초에 적힌 항목들이 전부 동점이 되고, 그때
 * `sort` 는 원래 순서(=가장 오래된 것부터)를 그대로 둔다. 그 상태에서 뒤를 잘라내면
 * **가장 최근 것이 지워진다** — 방금 본 목록의 기억이 사라지는데 오류는 안 난다.
 * 이 시험이 실제로 그것을 잡았다. */
function nextSeq(map) {
  let max = 0;
  for (const k of Object.keys(map)) max = Math.max(max, map[k].seq || 0);
  return max + 1;
}

function writeAll(map) {
  try {
    const keys = Object.keys(map);
    if (keys.length > LIMIT) {
      keys.sort((a, b) => (map[b].seq || 0) - (map[a].seq || 0));
      for (const k of keys.slice(LIMIT)) delete map[k];
    }
    window.sessionStorage.setItem(KEY, JSON.stringify(map));
  } catch {
    // 저장을 못 해도 화면은 그대로 동작한다. 잃는 것은 편의뿐이다.
  }
}

/** 이 목록이 지금 어느 주소에 있는지 적는다. `url` 은 질의 문자열까지 포함한 값이다. */
export function rememberList(key, url) {
  if (!key || !url) return;
  const all = readAll();
  const prev = all[key] || {};
  // 주소가 바뀌면(조건·페이지를 바꿨다) 스크롤 기억은 버린다 — 다른 목록의 위치다.
  all[key] = {
    url,
    scrollY: prev.url === url ? prev.scrollY || 0 : 0,
    seq: nextSeq(all),
  };
  writeAll(all);
}

/** 이 목록에서 어디까지 내려가 있었는지 적는다. */
export function rememberScroll(key, scrollY) {
  if (!key) return;
  const all = readAll();
  if (!all[key]) return;
  all[key].scrollY = Math.max(0, Math.round(scrollY) || 0);
  writeAll(all);
}

/** 돌아갈 주소. 기억이 없으면 `fallback` 이다. */
export function listReturnUrl(key, fallback) {
  const entry = readAll()[key];
  return (entry && entry.url) || fallback || key;
}

/** 목록 화면이 부른다 — 지금 주소를 적고, 돌아왔으면 있던 자리로 되돌린다.
 *
 * `key` 는 목록의 **정체**다(`/my-tickets`). 주소가 아니라 정체인 이유: 조건이 바뀌면
 * 주소는 바뀌지만 그것은 여전히 같은 목록이다. */
export function useListMemory(key) {
  const loc = useLocation();
  const url = loc.pathname + loc.search;

  React.useEffect(() => {
    rememberList(key, url);
  }, [key, url]);

  /* 되돌리는 것은 **이 목록으로 돌아왔을 때 한 번**이다. 목록이 그려지기 전에 되돌리면
     문서 높이가 아직 짧아 브라우저가 그 값을 잘라 버리므로, 다음 프레임에 다시 시도한다.
     두 번으로 끝낸다 — 계속 되돌리면 사용자가 스스로 굴린 것을 화면이 도로 끌어당긴다. */
  const restored = React.useRef(false);
  React.useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const entry = readAll()[key];
    if (!entry || entry.url !== url || !entry.scrollY) return;
    const target = entry.scrollY;
    let frames = 0;
    const step = () => {
      window.scrollTo(0, target);
      if (++frames < 2) window.requestAnimationFrame(step);
    };
    window.requestAnimationFrame(step);
  }, [key, url]);

  /* 굴릴 때마다 적지 않는다 — 프레임마다 `sessionStorage` 에 쓰면 목록이 눈에 띄게
     끊긴다. 프레임 하나에 한 번으로 묶는다. */
  React.useEffect(() => {
    let pending = false;
    const onScroll = () => {
      if (pending) return;
      pending = true;
      window.requestAnimationFrame(() => {
        pending = false;
        rememberScroll(key, window.scrollY);
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [key]);
}

/** 상세 화면의 「목록」이 부른다 — 어디서 왔고 그 목록이 어떤 상태였는지.
 *
 * `from` 은 목록이 `nav(..., { state: { from } })` 로 남긴 값이다. 없으면 `fallback` 이다 —
 * 딥링크로 바로 들어온 경우가 그렇고, 그때는 기본 목록으로 보내는 것이 맞다. */
export function useListReturn(from, fallback) {
  const key = from || fallback;
  return listReturnUrl(key, key);
}
