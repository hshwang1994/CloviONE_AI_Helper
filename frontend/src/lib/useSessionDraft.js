import React from "react";

/* 작성 중인 값을 **세션 저장소**에 붙잡아 둔다 (D-483).
 *
 * 회의록을 반쯤 적다가 티켓 하나를 확인하러 나가면 그 글이 사라졌다 — 입력이 `useState`
 * 에만 살아서 화면이 언마운트되는 순간 함께 죽었다. 주소에 실을 값은 아니다(글이 길고
 * 공유할 것도 아니다). 그래서 `sessionStorage` 다: 탭을 닫으면 사라지고, 새로고침과
 * 화면 이동은 견딘다. 못 쓰는 브라우저(프라이빗 모드)에서는 조용히 `useState` 처럼 동작한다.
 *
 * `key` 가 초안의 **범위**다 — 회의록은 `cv.meetingDraft.v1:<회차 id>` 라서 팀·회차를
 * 오가도 각 회차의 초안이 따로 남고, 다른 회차의 글이 이 회차 칸에 나타나지 않는다.
 * `key` 가 비면(아직 회차를 안 골랐다) 저장하지 않는다.
 *
 * 저장 성공 뒤에는 `clear()` 로 지운다 — 보낸 글이 다음에 다시 뜨면 두 번 적힌다. */

function read(key) {
  if (!key) return undefined;
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw == null ? undefined : JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function write(key, value) {
  if (!key) return;
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 저장을 못 해도 화면은 그대로 동작한다. 잃는 것은 편의뿐이다.
  }
}

function remove(key) {
  if (!key) return;
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // 위와 같다.
  }
}

/** 값이 초기값과 같은가 — 빈 초안은 저장하지 않는다(저장소에 빈 껍데기가 쌓이지 않게). */
function isBlank(value, initial) {
  return JSON.stringify(value) === JSON.stringify(initial);
}

/** `[value, setValue, clear]`. `setValue` 는 `useState` 처럼 값이나 갱신 함수를 받는다. */
export function useSessionDraft(key, initial) {
  const initialRef = React.useRef(initial);
  const [value, setValueState] = React.useState(() => {
    const saved = read(key);
    return saved === undefined ? initialRef.current : saved;
  });
  // 범위(key)가 바뀌면 그 범위의 초안을 다시 읽는다 — 다른 회차의 글을 들고 가지 않는다.
  const keyRef = React.useRef(key);
  React.useEffect(() => {
    if (keyRef.current === key) return;
    keyRef.current = key;
    const saved = read(key);
    setValueState(saved === undefined ? initialRef.current : saved);
  }, [key]);

  const setValue = React.useCallback((next) => {
    setValueState((prev) => {
      const resolved = typeof next === "function" ? next(prev) : next;
      if (isBlank(resolved, initialRef.current)) remove(keyRef.current);
      else write(keyRef.current, resolved);
      return resolved;
    });
  }, []);

  const clear = React.useCallback(() => {
    remove(keyRef.current);
    setValueState(initialRef.current);
  }, []);

  return [value, setValue, clear];
}

/** 시험·진단용 — 저장소에 남은 초안을 그대로 읽는다. */
export function readSessionDraft(key) {
  return read(key);
}
