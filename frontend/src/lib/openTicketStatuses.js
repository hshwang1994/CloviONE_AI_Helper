/* 내 티켓 기본 상태 집합.

워크플로 정본(`/api/work/statuses` 의 category·terminal)에서 **종료가 아닌** 상태만
고른다. 화면이 "계획·이슈·진행·검증" 같은 이름을 하드코딩하면 표에 상태가 늘거나
이름이 바뀌는 날 기본 필터가 틀린 이름을 보낸다. */

export function openStatusKeys(statuses) {
  return (Array.isArray(statuses) ? statuses : [])
    .filter((s) => s && s.key && s.terminal !== true)
    .map((s) => s.key);
}
