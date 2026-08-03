/* 브랜드 자산 경로 — SPA와 서버 렌더(Jinja) 페이지가 같은 파일을 쓴다.
 *
 * 자산은 frontend/public이 아니라 app/static/brand/에 둔다. 이유가 두 가지 있다:
 *   1) 로그인·비밀번호 변경은 SPA가 아니라 Jinja 서버 렌더라, 프런트 빌드 산출물 안에
 *      있으면 그쪽에서 못 쓴다. 로고와 파비콘은 양쪽이 같아야 한다.
 *   2) app/static/* 는 scripts/stage-static-update.sh로 서비스 재시작 없이 교체된다.
 *
 * Vite의 base가 /static/react/ 라서 상대 경로를 쓰면 /static/react/... 로 다시 쓰인다.
 * 절대 경로로 고정한다.
 */

export const BRAND = "/static/brand";

export const LOGO = {
  mark: `${BRAND}/logo/clovirassist-mark.svg`,
  horizontal: `${BRAND}/logo/clovirassist-logo-horizontal.svg`,
  horizontalDark: `${BRAND}/logo/clovirassist-logo-horizontal-dark.svg`,
  stacked: `${BRAND}/logo/clovirassist-logo-stacked.svg`,
};

/* 마스코트 '클로비'. 런타임에는 **완성된 포즈 PNG만 교체**한다.
 * brand/mascot/frames/ 와 layers/ 는 참고용 보존 자산이고 런타임 합성은 금지다
 * (docs/mascot-animation-spec.md §5 — 합성하면 손목이 분리되거나 배경색이 어긋난다).
 * scripts/static_checks.sh가 이 규칙을 검사한다. */
export const MASCOT = {
  idle: `${BRAND}/mascot/clovi-idle.png`,
  blink: `${BRAND}/mascot/clovi-idle-blink.png`,
  wave: `${BRAND}/mascot/clovi-wave.png`,
  happy: `${BRAND}/mascot/clovi-happy.png`,
  think: `${BRAND}/mascot/clovi-think.png`,
  talking: `${BRAND}/mascot/clovi-talking.png`,
  error: `${BRAND}/mascot/clovi-error.png`,
  love: `${BRAND}/mascot/clovi-love.png`,
  sleep: `${BRAND}/mascot/clovi-sleep.png`,
  avatar: `${BRAND}/mascot/clovi-avatar.png`,
  button: `${BRAND}/mascot/clovi-button.png`,
};

/* 빈 화면·오류 상태 일러스트.
 * 자산은 처음부터 12종이 다 있었는데 어디에도 연결돼 있지 않았다 — "파일이 있다"와
 * "화면에 나온다"는 다른 일이다. EmptyState/ErrorState가 art 키로 골라 쓴다. */
export const ART = {
  tickets: `${BRAND}/empty-states/empty-tickets.png`,
  docs: `${BRAND}/empty-states/empty-docs.png`,
  trash: `${BRAND}/empty-states/empty-trash.png`,
  chat: `${BRAND}/empty-states/empty-chat.png`,
  board: `${BRAND}/empty-states/empty-board.png`,
  notify: `${BRAND}/empty-states/empty-notify.png`,
  search: `${BRAND}/empty-states/empty-search.png`,
  notFound: `${BRAND}/empty-states/state-404.png`,
  serverError: `${BRAND}/empty-states/state-500.png`,
  noPermission: `${BRAND}/empty-states/state-no-permission.png`,
  sessionExpired: `${BRAND}/empty-states/state-session-expired.png`,
  offline: `${BRAND}/empty-states/state-offline.png`,
  success: `${BRAND}/empty-states/state-success.png`,
};

/* 섹션 헤더용 스팟 일러스트. 4K에서 남는 폭을 의미 있는 밀도로 채우는 수단이기도 하다. */
export const SPOT = {
  mywork: `${BRAND}/spot/spot-mywork.png`,
  docs: `${BRAND}/spot/spot-docs.png`,
  teamspace: `${BRAND}/spot/spot-teamspace.png`,
  games: `${BRAND}/spot/spot-games.png`,
  sprint: `${BRAND}/spot/spot-sprint.png`,
  chat: `${BRAND}/spot/spot-chat.png`,
  board: `${BRAND}/spot/spot-board.png`,
  assistant: `${BRAND}/spot/spot-assistant.png`,
};

export const MISC = {
  onboarding: `${BRAND}/misc/onboarding-welcome.png`,
  celebrate: `${BRAND}/misc/celebrate-winner.png`,
  loading: `${BRAND}/misc/loading.png`,
};
