import React from "react";
import Box from "@mui/material/Box";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import { useAuth } from "../app/auth.jsx";
import { Button, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "./kit.jsx";
import { useQueryState } from "../lib/useQueryState.js";

/* 탭 그릇 — 성격이 같은 화면 둘 이상을 한 주소 아래 모을 때 쓴다 (지시 30 · 46 · 51).
 *
 * ## 왜 공용인가
 *
 * `screens/settings/SettingsShell.jsx` 가 이 로직을 먼저 만들었고, 그 안에는 쉽게 틀리는
 * 판단이 여럿 들어 있다 — 역할로 탭을 거르는 것, "모르는 탭"과 "권한 때문에 못 보는 탭"을
 * 다르게 다루는 것, 딥링크 주소를 그대로 두는 것, 탭이 하나뿐이면 탭 줄 자체를 안 그리는
 * 것, WAI-ARIA 탭↔패널 연결. 관리자 IA 를 합치면서 이 판단을 화면마다 다시 쓰면 반드시
 * 한쪽만 고쳐진다(이 저장소가 여러 번 겪은 모양이다). 한 곳에 둔다.
 *
 * ## 지키는 계약
 *
 * 1. **역할.** 탭마다 `roles` 를 줄 수 있다. 못 보는 탭은 탭 줄에서 사라지고, 그 탭을
 *    주소로 직접 열면 **주소는 그대로 둔 채** 권한 안내를 보여 준다(PA-RC-0024 딥링크 계약).
 *    조용히 첫 탭으로 떨어뜨리면 "왜 다른 화면이 뜨지"가 된다.
 * 2. **모르는 탭 값**은 주소를 기본 탭으로 정정한다(오타·삭제된 탭). `replace` 라
 *    뒤로가기가 이전 화면으로 간다.
 * 3. **세션 만료(401)** 는 역할이 아직 안 온 것뿐이라 "권한 없음"으로 오판하지 않는다 —
 *    재로그인 경로가 있는 오류 화면을 먼저 본다.
 * 4. **프런트의 역할 판정은 표시일 뿐이다.** 권한의 정본은 서버다(불변규칙 §5). 각 탭
 *    내용이 스스로 게이트를 갖고 있다면 그것도 그대로 둔다 — 여기서 한 겹을 더 얹는 것이지
 *    대신하는 것이 아니다.
 *
 * ## 쓰는 법
 *
 *   <TabShell
 *     area="운영" title="백업"
 *     tabs={[
 *       { key: "backup", label: "백업", render: () => <DataScreen config={cfg.backup} /> },
 *       { key: "drills", label: "복구 리허설", render: () => <DataScreen config={cfg.drills} /> },
 *     ]}
 *   />
 *
 * 탭 안에 목록 화면(`DataScreen`)을 두면 그 화면이 자기 필터를 같은 쿼리에 쓴다 —
 * `datascreen-view.js::withHashQuery` 가 **자기 키만** 갈아치우도록 고쳐 둬서 `?tab=` 이
 * 살아남는다. 그 보증이 없으면 필터를 한 칸 건드리는 순간 첫 탭으로 튕긴다.
 */
export function TabShell({
  area, title, crumbRoot, tabs, ariaLabel, deniedHelp, idPrefix = "tabshell", children,
}) {
  const defs = (tabs || []).filter(Boolean);
  const defaultKey = defs.length ? defs[0].key : "";
  /* `spec` 은 모듈 상수여야 메모가 안 깨진다(useQueryState 주석) — 화면마다 기본 탭이
     다르므로 여기서 만들되 기본 탭 값에만 의존하게 고정한다. */
  const spec = React.useMemo(() => ({ tab: defaultKey }), [defaultKey]);
  const [state, setState] = useQueryState(spec);

  const auth = useAuth();
  const role = auth.data && auth.data.role;
  const visible = defs.filter((t) => !t.roles || t.roles.includes(role));
  const visibleKeys = visible.map((t) => t.key);

  const requested = defs.find((t) => t.key === state.tab);
  const roleDenied = !!requested && !visibleKeys.includes(requested.key);
  const unknownTab = state.tab !== defaultKey && !requested;
  React.useEffect(() => {
    if (unknownTab) setState({ tab: defaultKey });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unknownTab, state.tab, defaultKey]);

  const activeKey = roleDenied
    ? requested.key
    : (visibleKeys.includes(state.tab) ? state.tab : defaultKey);
  const activeDef = roleDenied ? requested : (visible.find((t) => t.key === activeKey) || visible[0]);

  const tabId = (key) => `${idPrefix}-tab-${key}`;
  const panelId = (key) => `${idPrefix}-tabpanel-${key}`;

  if (auth.isLoading) return <Card><Skeleton /></Card>;
  if (auth.isError) return <ErrorState error={auth.error} onRetry={() => auth.refetch()} />;
  if (!activeDef) return null;

  return (
    <Box className="c-screen">
      <PageHeader area={area} title={title} tab={activeDef.label} crumbRoot={crumbRoot} />
      {children}
      {/* 전환할 곳이 없는 탭 줄은 장식이다. */}
      {visible.length > 1 ? (
        <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2.5 }}>
          <Tabs
            value={activeKey}
            onChange={(e, next) => setState({ tab: next })}
            variant="scrollable"
            allowScrollButtonsMobile
            aria-label={ariaLabel || `${title} 탭`}
          >
            {visible.map((t) => (
              <Tab key={t.key} value={t.key} label={t.label} id={tabId(t.key)} aria-controls={panelId(t.key)} />
            ))}
          </Tabs>
        </Box>
      ) : null}

      {roleDenied ? (
        <EmptyState
          title="권한이 없습니다"
          help={deniedHelp || requested.deniedHelp || "이 탭을 볼 권한이 없습니다."}
          art="noPermission"
          action={<Button variant="primary" href="#/dashboard">대시보드로 이동</Button>}
        />
      ) : (
        <Box role="tabpanel" id={panelId(activeKey)} aria-labelledby={tabId(activeKey)} tabIndex={0}>
          {activeDef.render()}
        </Box>
      )}
    </Box>
  );
}

export default TabShell;
