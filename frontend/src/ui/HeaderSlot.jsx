import React from "react";
import { createPortal } from "react-dom";
import Box from "@mui/material/Box";

/* 머리 동작 자리 — **그릇이 자리를 내고, 본문이 거기에 그린다** (D-454).
 *
 * ## 왜 있는가
 *
 * 탭 그릇(`TabShell`·`SettingsShell`) 안의 목록 화면(`DataScreen embedded`)은 자기 머리
 * 동작(「추가」·「CSV 내보내기」…)을 **탭 아래 오른쪽 정렬 줄**에 그렸다. 단독 화면은 같은
 * 동작을 `PageHeader` 의 오른쪽에 두므로, 같은 화면이 탭 안에 들어가는 순간 단추의 자리가
 * 달라졌다 — 사용자 콘솔에는 없는 모양이다.
 *
 * 동작의 핸들러(`busy`·확인 대화·폼 열기)는 본문이 들고 있어 그릇이 대신 그릴 수 없다.
 * 그래서 그릇이 **DOM 자리**를 내고 본문이 `createPortal` 로 그 자리에 그린다.
 *
 * ## 계약
 *
 *   HeaderActionsProvider  그릇이 자기 화면 전체를 감싼다.
 *   HeaderActionsHost      그릇이 `PageHeader actions` 자리에 둔다 — 본문이 붙어 있을 때만
 *                          (`useHeaderActionsSlot().count > 0`). 빈 자리를 항상 두면 좁은
 *                          화면에서 `.k-page-actions` 가 빈 줄로 접혀 제목 아래가 24px 뜬다.
 *   HeaderActions          본문이 쓴다. 그릇이 없으면(시험·단독 임베드) `fallback` 을 그 자리에
 *                          그대로 그린다.
 *
 * 호스트 노드는 ref 가 아니라 **state** 로 든다 — 본문이 호스트보다 먼저 렌더돼도 노드가
 * 붙는 순간 다시 그려진다. `display: contents` 라 포털 자식이 `.k-page-actions` 의 직계
 * flex 항목이 된다(단독 화면과 같은 간격). */
const HeaderActionsCtx = React.createContext(null);

export function HeaderActionsProvider({ children }) {
  const [host, setHost] = React.useState(null);
  const [count, setCount] = React.useState(0);
  const attach = React.useCallback(() => setCount((c) => c + 1), []);
  const detach = React.useCallback(() => setCount((c) => Math.max(0, c - 1)), []);
  const value = React.useMemo(
    () => ({ host, setHost, count, attach, detach }),
    [host, count, attach, detach],
  );
  return <HeaderActionsCtx.Provider value={value}>{children}</HeaderActionsCtx.Provider>;
}

/** 그릇이 읽는다 — 본문이 동작을 붙였는지(`count`). */
export function useHeaderActionsSlot() {
  return React.useContext(HeaderActionsCtx);
}

/** 그릇이 `PageHeader actions` 자리에 두는 빈 노드. */
export function HeaderActionsHost() {
  const slot = React.useContext(HeaderActionsCtx);
  return <Box data-header-actions-host="" ref={slot ? slot.setHost : undefined} sx={{ display: "contents" }} />;
}

/** 본문이 쓴다 — 그릇이 있으면 머리에, 없으면 `fallback` 자리에 그린다. */
export function HeaderActions({ children, fallback = null }) {
  const slot = React.useContext(HeaderActionsCtx);
  const attach = slot ? slot.attach : null;
  const detach = slot ? slot.detach : null;
  React.useEffect(() => {
    if (!attach || !detach) return undefined;
    attach();
    return () => detach();
  }, [attach, detach]);
  if (!slot) return fallback;
  return slot.host ? createPortal(children, slot.host) : null;
}
