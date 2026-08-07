/* 설정 주도 화면 목록 — 화면 키 → DataScreen 설정.
 *
 * ## 이 파일이 얇아진 이유 (E-10 · PF7)
 *
 * 예전에는 여기 한 파일에 2,534줄이 있었다. 관리자 화면 스물여덟 개의 설정 전부와, 그것들이
 * 함께 쓰는 어휘·열·액션 조립까지 한 덩어리였다. 저장소 규칙(200~400줄, 최대 800)을 세 배로
 * 넘었고, 화면 하나를 고치려 해도 무엇이 어디 있는지 찾는 데 먼저 시간을 썼다.
 *
 * **쪼갠 축은 줄 수가 아니라 '관리자가 한 번에 함께 보는 묶음'이다.** 연동을 고치는 사람은
 * 러너·워크플로도 같이 본다. 프롬프트를 고치는 사람은 정책·템플릿을 같이 본다. 줄 수를 맞추려
 * 아무 데나 자르면 한 화면을 고치는 데 파일 셋을 열게 되어 오히려 더 나빠진다.
 *
 * ## 그리고 사용자 콘솔은 이 파일을 읽지 않는다
 *
 * 알림(`/notifications`)은 관리자 화면이면서 사용자 콘솔의 화면이기도 하다. 그 하나 때문에
 * `UserRoutes.jsx` 가 이 파일 전체를 정적으로 들여왔고, 평범한 사용자가 관리자 설정
 * 스물일곱 개를 함께 내려받았다 — 평생 열지 않을 화면들이다. 이제 사용자 콘솔은
 * `registry/notifications.js` 만 들여온다.
 *
 * 그래서 **여기에 새 화면을 직접 적지 않는다.** 도메인 파일에 적고 아래 조립에만 더한다.
 */
import { INTEGRATION_SCREENS } from "./registry/integrations.js";
import { AUTHORING_SCREENS } from "./registry/authoring.js";
import { AUTOMATION_SCREENS } from "./registry/automation.js";
import { ORG_SCREENS } from "./registry/org.js";
import { GOVERNANCE_SCREENS } from "./registry/governance.js";
import { PLATFORM_SCREENS } from "./registry/platform.js";
import { NOTIFICATIONS_SCREEN } from "./registry/notifications.js";

/* 순서는 관리자 사이드바가 아니라 **읽는 사람**을 위한 것이다 — 바깥 배관에서 시작해
 * 조직·권한으로, 마지막이 이 설치 자체를 돌보는 화면이다. 키가 겹치면 나중 것이 이기므로,
 * 새 화면을 더할 때 이름이 이미 있는지 아래 조립을 눈으로 확인한다(같은 키 두 개는
 * 조용히 한쪽을 지운다). */
export const REGISTRY = {
  ...INTEGRATION_SCREENS,
  ...AUTHORING_SCREENS,
  ...AUTOMATION_SCREENS,
  ...ORG_SCREENS,
  ...GOVERNANCE_SCREENS,
  ...PLATFORM_SCREENS,
  ...NOTIFICATIONS_SCREEN,
};
