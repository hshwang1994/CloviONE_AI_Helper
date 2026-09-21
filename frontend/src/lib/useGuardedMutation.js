import React from "react";
import { useMutation } from "@tanstack/react-query";

/* 같은 요청은 끝나기 전에 한 번만 나간다 — 더블클릭 · Enter 연타의 둘째 활성화를 버린다.
 *
 * ## 왜 `isPending` 만으로는 모자라는가
 *
 * TanStack Query 는 `isPending` 을 알림 관리자(`notifyManager`)의 **다음 매크로태스크**에서
 * 화면에 알린다. 그래서 첫 활성화가 `mutate()` 를 부른 뒤 그 알림이 화면을 다시 그리기 전에
 * 둘째 활성화가 오면, 둘째 처리기는 아직 `isPending === false` 인 옛 렌더를 보고 요청을 한 번
 * 더 보낸다. 단추는 다시 그려진 뒤에야 꺼지고, 키보드 처리기(채팅 입력의 Enter · 폼의 Enter)는
 * 단추가 꺼져도 그대로 불린다. 그 결과가 같은 티켓 둘 · 같은 메시지 둘 · 「이미 있습니다」
 * 409 다 — 사용자에게는 자기가 한 적 없는 실패로 보인다.
 *
 * ## 무엇을 막고 무엇을 통과시키는가
 *
 * 진행 중인 요청을 **변수의 안정 키**로 기억하는 동기 ref 를 둔다. 같은 키의 요청이 아직
 * 끝나지 않았으면 새로 보내지 않고, `mutateAsync` 는 진행 중인 그 약속을 그대로 돌려준다 —
 * 부르는 쪽이 기다리는 결과는 첫 요청의 결과와 같다. 키가 다르면 통과한다: 빠르게 연달아
 * 친 서로 다른 채팅 두 줄은 둘 다 나간다. 요청이 끝나면(성공이든 실패든) 키를 풀어서 같은
 * 값을 다시 보낼 수 있다.
 *
 * 키는 기본으로 변수 자체에서 만든다(`stableKey` — 객체의 키 순서와 `undefined` 값은
 * 무시한다. JSON 본문과 같은 규칙이다). 파일 · FormData 처럼 값으로 비교할 수 없는 것은
 * **그 객체 자신**이 키다. 뜻이 다른 기준이 필요하면 `key(variables)` 를 준다 — 예를 들어
 * 붙여넣은 그림은 매번 새 File 이라 값으로는 못 가르므로 `key: () => "image"` 로 「한 번에
 * 하나」를 말한다.
 *
 * 돌려주는 값은 `useMutation` 과 같다(`isPending` · `variables` · `error` · `reset` …).
 * 바뀌는 것은 `mutate` · `mutateAsync` 둘뿐이고, 버려진 호출의 호출별 콜백
 * (`mutate(vars, { onSuccess })`)은 부르지 않는다 — 그 요청은 나가지 않았다. */

const NOOP = () => {};

const objectIds = new WeakMap();
const symbolIds = new Map();
let identitySeq = 0;

function identityKey(value) {
  const table = typeof value === "symbol" ? symbolIds : objectIds;
  let id = table.get(value);
  if (id == null) {
    identitySeq += 1;
    id = identitySeq;
    table.set(value, id);
  }
  return "#" + id;
}

function isPlainObject(value) {
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/* 변수 → 안정 키. 같은 요청을 만드는 변수는 같은 키를 받는다. */
export function stableKey(value, seen = new WeakSet()) {
  if (value === undefined) return "u";
  if (value === null) return "n";
  const type = typeof value;
  if (type === "string") return "s" + JSON.stringify(value);
  if (type === "number" || type === "boolean" || type === "bigint") return type[0] + String(value);
  if (type === "function" || type === "symbol") return identityKey(value);
  if (value instanceof Date) return "d" + value.getTime();
  // 순환 참조는 JSON 본문이 될 수 없다 — 값으로 비교하지 않고 그 객체 자신을 키로 쓴다.
  if (seen.has(value)) return identityKey(value);
  if (Array.isArray(value)) {
    seen.add(value);
    const inner = value.map((item) => stableKey(item, seen)).join(",");
    seen.delete(value);
    return "[" + inner + "]";
  }
  if (isPlainObject(value)) {
    seen.add(value);
    const inner = Object.keys(value)
      .filter((k) => value[k] !== undefined)
      .sort()
      .map((k) => JSON.stringify(k) + ":" + stableKey(value[k], seen))
      .join(",");
    seen.delete(value);
    return "{" + inner + "}";
  }
  return identityKey(value);
}

export function useGuardedMutation(options, queryClient) {
  const { key, ...mutationOptions } = options || {};
  const mutation = useMutation(mutationOptions, queryClient);
  const inFlight = React.useRef(new Map());
  const keyRef = React.useRef(key);
  keyRef.current = key;
  const rawMutateAsync = mutation.mutateAsync;

  const mutateAsync = React.useCallback((variables, mutateOptions) => {
    const keyOf = keyRef.current;
    const k = typeof keyOf === "function" ? String(keyOf(variables)) : stableKey(variables);
    const running = inFlight.current.get(k);
    if (running) return running;
    const promise = rawMutateAsync(variables, mutateOptions);
    inFlight.current.set(k, promise);
    const release = () => {
      if (inFlight.current.get(k) === promise) inFlight.current.delete(k);
    };
    promise.then(release, release);
    return promise;
  }, [rawMutateAsync]);

  const mutate = React.useCallback((variables, mutateOptions) => {
    mutateAsync(variables, mutateOptions).catch(NOOP);
  }, [mutateAsync]);

  return { ...mutation, mutate, mutateAsync };
}
