import { screen, waitFor, within } from "@testing-library/react";

/* 시험용 헬퍼 — **앱 코드가 아니다.** 시험만 import 한다(번들 그래프에 안 들어간다).
 *
 * ## 왜 있나 — REAUDIT §15.5, `ui/DateField.jsx`
 *
 * 날짜 칸을 `@mui/x-date-pickers` 로 옮기면서 시험이 그 칸을 채우는 방법이 두 군데서
 * 똑같이 깨졌다(`projects.test.jsx`, 그리고 이 파일을 쓰는 화면들). 원인은 화면마다 다르지
 * 않고 부품 하나(`DateField`)에서 나오므로 여기 한 곳에서만 고친다.
 *
 * (1) `DateField` 는 지연 로드다 — 첫 렌더에는 비활성 자리표시 `<input>` 뿐이고, 청크가
 *     오면 Suspense 가 그 서브트리를 통째로 실제 필드로 바꿔 끼운다(자리표시 DOM 노드는
 *     버려진다). 그 전에 잡은 참조로 계속 조작하면 이미 떨어져 나간 옛 노드를 건드리는
 *     셈이라 아무 값도 안 남는다 — 그래서 비활성이 풀릴 때까지 먼저 기다린 뒤에 새로 찾는다.
 * (2) 진짜 필드로 바뀐 뒤에도 라벨이 가리키는 것은 MUI 의 숨은 `aria-hidden` 입력(폼
 *     제출용 그림자 값)이라 `user.clear()`/`user.type()` 이 그 자리를 포커스하지 못한다.
 *     실제로 누르고 치는 표면은 그 부모(`role="group"`) 안에 있는 구간(연·월·일)
 *     `role="spinbutton"` span 셋이다. 첫 구간을 누르고 숫자만 이어 치면 구간이 찰 때마다
 *     다음 구간으로 자동으로 넘어간다(MUI v9 부터 이 구조가 유일한 선택지다 — 단일 input
 *     으로 돌아가는 옵션 자체가 없다).
 *
 * 아직 네이티브 `input[type=date]` 로 남은 자리가 있어도(있다면 이관 누락이다) 이 헬퍼는
 * 그대로 동작한다 — `aria-hidden` 여부로 갈라 원래 방식(clear+type)으로 되돌아간다.
 *
 * 하나 더: `label` 을 직접 받는 독립 사용처(예: `MyTickets.jsx`)는 MUI 자신의 내부 라벨
 * 배선도 같이 켜져서, 같은 이름으로 **구간 그룹**과 **숨은 입력** 둘 다 걸린다(FormModal
 * 처럼 외부 `FieldLabel` 만 쓰는 자리는 숨은 입력 하나만 걸린다). 그래서 하나가 아니라
 * `getAllByLabelText` 로 받아 그 중 `aria-hidden` 인 것을 고른다 — 있으면 그것, 없으면
 * 첫 `<input>` 이 원래(네이티브) 필드다. */
export async function fillDateField(user, label, isoValue) {
  const pick = (matches) =>
    matches.find((el) => el.getAttribute("aria-hidden") === "true")
    || matches.find((el) => el.tagName === "INPUT")
    || matches[0];
  await waitFor(() => {
    const input = pick(screen.getAllByLabelText(label));
    expect(input).not.toBeDisabled();
  });
  const input = pick(screen.getAllByLabelText(label));
  if (input.getAttribute("aria-hidden") === "true") {
    const firstSection = within(input.parentElement).getAllByRole("spinbutton")[0];
    await user.click(firstSection);
    await user.keyboard(isoValue.replace(/-/g, ""));
    return;
  }
  await user.clear(input);
  await user.type(input, isoValue);
}
