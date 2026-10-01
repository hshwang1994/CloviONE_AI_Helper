import React from "react";
import { Button, EmptyState, ErrorState } from "./kit.jsx";
import { LIST_STATE_COPY } from "./listState.js";

/* 목록이 표 대신 그리는 네 갈래 — 권한 없음 · 기능 꺼짐 · 연결 장애 · 서버 오류 (F4 · D-530).
 *
 * 판정은 `listState.js::resolveListState` 하나이고, 이 부품은 그 갈래를 말로 바꾼다. 불러오는 중 · 조건 0건 · 행은 표가 그린다
 * (표 모양 뼈대 · 머리 아래 한 줄 띠). 자료 없음(조건 없이 0건)은 그 화면의 말(레지스트리 문장 · 만드는 동작)이라 화면이 그린다.
 *
 *   forbidden    「이 목록을 볼 권한이 없습니다.」 — 다시 시도가 없다(같은 요청은 같은 답이다). 401 은 세션 문제라 오류 상태의
 *                「로그인 화면으로」를 그대로 쓴다.
 *   disabled     서버 문장(어느 기능이 꺼졌는가) + 「관리자가 기능을 켜면 목록을 볼 수 있습니다.」, 설정 권한이 있으면 그 화면 링크.
 *                오류가 아니라 상태다 — 빈 상태 부품으로 그린다(빨간 오류 표지를 붙이지 않는다).
 *   unreachable  「서버에 연결하지 못했습니다.」 + 다시 시도
 *   error        「목록을 불러오지 못했습니다.」 + 다시 시도 + 문의 번호(오류 상태가 그린다). 429 는 기다릴 시간을 아는 오류 상태의
 *                말을 그대로 쓴다.
 *
 * `layout` 을 안 주면 담는 쪽이 정한다(`kit.jsx::StateRegion`). */
export function ListStateView({ state, error, onRetry, layout, settingsHref, settingsLabel = "기능 설정 열기" }) {
  const status = error && error.status;
  if (state === "forbidden") {
    if (status === 401) return <ErrorState layout={layout} error={error} />;
    const c = LIST_STATE_COPY.forbidden;
    return <ErrorState layout={layout} error={error} title={c.title} help={c.help} action={null} />;
  }
  if (state === "disabled") {
    const c = LIST_STATE_COPY.disabled;
    const said = error && typeof error.message === "string" && error.message.trim() ? error.message.trim() : "";
    return (
      <EmptyState
        layout={layout}
        title={said || c.title}
        help={c.help}
        action={settingsHref ? <Button size="sm" href={settingsHref}>{settingsLabel}</Button> : null}
      />
    );
  }
  if (state === "unreachable") {
    const c = LIST_STATE_COPY.unreachable;
    return <ErrorState layout={layout} error={error} onRetry={onRetry} title={c.title} help={c.help} />;
  }
  if (state === "error") {
    if (status === 429) return <ErrorState layout={layout} error={error} onRetry={onRetry} />;
    const c = LIST_STATE_COPY.error;
    const help = error && error.requestId ? `${c.help} 계속되면 아래 문의 번호를 관리자에게 알려 주세요.` : c.help;
    return <ErrorState layout={layout} error={error} onRetry={onRetry} title={c.title} help={help} />;
  }
  return null;
}

export default ListStateView;
