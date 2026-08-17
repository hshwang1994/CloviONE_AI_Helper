/* PA-RC-0034: react-query 기본 retry(3회)가 확정적 4xx(예: 없는 상세 id의 404)에도
 * 그대로 적용돼 /board/<없는 id>가 4번(1+3) 왕복한 뒤에야 "찾을 수 없습니다"가 떴다
 * (20~30초). 4xx는 다시 불러도 같은 응답이 온다 — 재시도로 나아질 수 있는 건
 * 5xx·네트워크 오류(err.status 없음, lib/api.js)뿐이라 그 경우만 최대 2번 재시도한다.
 *
 * main.jsx(createRoot().render()를 최상위에서 부르는 진입점이라 테스트에서 안전하게
 * import할 수 없다)의 QueryClient defaultOptions에서 쓰는데, 그 판정 로직만 여기 따로
 * 뺀 이유는 그래서다 — 이 함수 자체는 순수 함수라 직접 단위 테스트할 수 있다.
 *
 * 화면 대다수는 이 기본값을 상속하지만 일부는 각자 retry를 이미 지정하고 있다 — 그
 * 화면들은 이 함수를 안 거치므로(react-query가 로컬 옵션을 우선한다) 그대로 둔다.
 */
export function shouldRetryQuery(failureCount, error) {
  const status = error && error.status;
  if (status != null && status >= 400 && status < 500) return false;
  return failureCount < 2;
}
