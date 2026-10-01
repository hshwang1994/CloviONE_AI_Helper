import { useMutation, useQueryClient } from "@tanstack/react-query";

/* 누르는 즉시 저장되는 설정(스위치 · 세그먼티드)의 저장 — 누른 순간 화면에 반영하고, 같은 대상의 요청은
 * 한 줄로 보낸다 (D-525).
 *
 * ## 왜 필요한가
 *
 * 예전 화면들은 저장이 도는 동안 **모든** 스위치를 비활성으로 바꿨다(`disabled={saving}`). 이유는 정당했다 — 목록
 * 전체를 보내는 저장(알림 유형 · 메일 유형)은 앞 요청이 끝나기 전에 다음 토글이 옛 목록에서 계산되면 앞 변경을
 * 지운다. 대가가 컸다: 스위치 하나를 바꿀 때마다 26~34개가 비활성으로 번쩍였고, 키보드로 Space 를 누른 스위치는
 * 비활성이 되며 초점을 잃었고, 응답이 올 때까지 손잡이가 움직이지 않았다. 비활성은 「조작할 수 없다」는 뜻이어야지
 * 「어딘가 저장 중」이라는 뜻이면 안 된다.
 *
 * ## 어떻게 푸는가
 *
 * - 같은 `queryKey` 의 저장은 TanStack 의 `scope` 로 **한 줄**에 선다 — 앞 요청이 끝나야 다음 요청이 나가므로
 *   순서가 뒤집히지 않는다.
 * - `onMutate` 가 쿼리 캐시에 바로 반영한다(`apply(old, vars)`). 줄에서 기다리는 동안에도 `onMutate` 는 바로 돈다
 *   (query-core `mutation.js`). 다음 토글의 본문은 이 반영된 값에서 계산되므로 앞 변경을 품는다.
 * - 서버 값으로 확정하는 것은 **줄의 마지막 요청**뿐이다 — 앞 응답을 캐시에 쓰면 줄 선 뒤 토글이 잠깐 되돌아간다.
 *   `fromResponse` 가 있으면 응답으로 캐시를 쓰고(응답이 그 자원 전체일 때), 없으면 그 쿼리를 다시 읽는다.
 * - 실패하면, 그것이 마지막일 때 이전 값으로 되돌리고 서버 값을 다시 읽는다. 뒤에 줄 선 요청이 있으면 그 요청이
 *   최신 의도를 통째로 나르므로 되돌리지 않는다. 실패 알림(`onError`)은 실패마다 부른다.
 * - 성공 알림(`onSaved`)은 줄이 빌 때 한 번만 부른다 — 연달아 바꿀 때 토스트가 쌓이는 것도 같은 소음이다.
 *
 * 돌려주는 값은 `useMutation` 과 같다. 화면은 `save.mutate(vars)` 만 부르고, 스위치의 `disabled` 에 이 저장의
 * `isPending` 을 쓰지 않는다. */
export function useInstantSave({ queryKey, mutationFn, apply, fromResponse, onSaved, onError }) {
  const qc = useQueryClient();
  const mutationKey = ["instant-save", ...queryKey];
  /* 콜백이 도는 동안 자기 자신은 아직 pending 이다 — 1 이면 뒤에 줄 선 요청이 없다. */
  const isLast = () => qc.isMutating({ mutationKey }) <= 1;
  return useMutation({
    mutationKey,
    scope: { id: JSON.stringify(mutationKey) },
    mutationFn,
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey });
      const previous = qc.getQueryData(queryKey);
      if (previous !== undefined) qc.setQueryData(queryKey, apply(previous, vars));
      return { previous };
    },
    onSuccess: (data, vars) => {
      if (!isLast()) return;
      if (fromResponse) qc.setQueryData(queryKey, (old) => fromResponse(data, old));
      else qc.invalidateQueries({ queryKey });
      if (onSaved) onSaved(data, vars);
    },
    onError: (error, vars, context) => {
      if (isLast()) {
        if (context && context.previous !== undefined) qc.setQueryData(queryKey, context.previous);
        qc.invalidateQueries({ queryKey });
      }
      if (onError) onError(error, vars);
    },
  });
}
