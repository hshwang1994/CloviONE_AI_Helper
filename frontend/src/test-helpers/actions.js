import { screen, within } from "@testing-library/react";

/* 시험용 헬퍼 — **앱 코드가 아니다.** 시험만 import 한다(번들 그래프에 안 들어간다).
 *
 * ## 왜 있나
 *
 * 액션 위계를 도입하면서(지시 8 · 11 · 12 · 43) 같은 동작이 화면 폭·개수·위험도에 따라
 * **버튼일 수도 있고 넘침 메뉴 항목일 수도** 있게 됐다. 파괴적 동작은 항상 메뉴로 내려간다.
 *
 * 시험이 그 차이를 하나하나 알고 있으면, 위계를 한 칸 조정할 때마다 상관없는 시험 스무 개가
 * 같이 깨진다. 시험이 실제로 재려는 것은 대개 **"그 동작을 실행하면 무슨 일이 일어나는가"**
 * 이고 "그 동작이 지금 버튼이냐 메뉴 항목이냐"가 아니다. 그 관심사를 여기 한 곳에 모은다.
 *
 * 표현 자체를 재는 시험은 이 헬퍼를 쓰지 않는다 — 예를 들어
 * `users-detail.test.jsx`("파괴적 작업은 펼치기 전에는 화면에 없다")나
 * `admin-tab-groups.test.jsx` 는 버튼/메뉴를 **직접** 질의한다. 그것이 그 시험의 주제다.
 */

/** 이름이 `name` 인 동작을 실행한다. 버튼이면 누르고, 없으면 넘침 메뉴를 열어 그 안에서 누른다. */
export async function clickAction(user, scope, name) {
  const root = scope || document.body;
  const inline = within(root).queryByRole("button", { name });
  if (inline) {
    await user.click(inline);
    return;
  }
  const more = within(root).getByRole("button", { name: /더 보기$/ });
  await user.click(more);
  // 메뉴는 Portal 로 body 에 붙는다 — `scope` 안에서 찾으면 못 찾는다.
  await user.click(await screen.findByRole("menuitem", { name }));
}

/** 그 동작이 지금 실행 가능한 자리에 있는가(버튼이든 메뉴 항목이든). 열지는 않는다. */
export function hasAction(scope, name) {
  const root = scope || document.body;
  if (within(root).queryByRole("button", { name })) return true;
  // 닫힌 메뉴의 항목은 DOM 에 없다 — 열어 보지 않고 알 수 있는 것은 "메뉴가 있다"까지다.
  return !!within(root).queryByRole("button", { name: /더 보기$/ });
}
