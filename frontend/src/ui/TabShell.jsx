import React from "react";
import Box from "@mui/material/Box";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import { useAuth } from "../app/auth.jsx";
import { Button, Card, CountChip, EmptyState, ErrorState, PageHeader, Skeleton, StateRegion } from "./kit.jsx";
import { FlowStack } from "./layout.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { HeaderActionsHost, HeaderActionsProvider, useHeaderActionsSlot } from "./HeaderSlot.jsx";

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
 * 5. **제목은 고정이고 탭은 그 아래다** (D-452). 예전에는 `PageHeader tab=` 으로 탭 라벨을
 *    h1 로 올렸고, 그래서 `/schedules` 의 h1 이 「목록」이었다. 사용자 탭 화면(승인·휴지통·
 *    프로젝트 상세)과 같은 모양으로 둔다.
 * 6. **도움말과 머리 동작은 그릇이 그린다** (D-453 · D-454). 탭 정의의 `help`(문자열·노드·
 *    `(role) => 노드`)가 제목 옆 `?` 가 되고, 탭 본문이 `HeaderActions` 로 넘긴 단추는
 *    `PageHeader` 의 오른쪽에 선다 — 단독 화면과 같은 자리다. 탭과 상관없는 화면 전체의
 *    동작(프로젝트 상세의 「엑셀 내보내기」 · 「목록」)은 `actions` 로 넘긴다 — 포털을 거치지
 *    않으므로 첫 그림부터 제자리에 선다.
 * 7. **탭 순서는 들어온 주소와 무관하다** (D-501). 주소가 `?tab=` 없이 그릇을 열 때 켜질 탭은
 *    `defaultTab` 이 정하고, 탭 줄은 언제나 정의 순서다. 예전에는 옛 주소(`/restore-drills`)로 들어오면
 *    그 탭을 앞으로 옮겨 기본 탭으로 삼았다 — 같은 그릇이 들어온 길에 따라 [복구 리허설|백업]과
 *    [백업|복구 리허설]로 서서, 사람은 탭의 자리로 화면을 기억할 수 없었다.
 * 8. **탭의 건수는 라벨 옆 칩이다** (계획 3.2 · 3.18). 탭 정의의 `count`(숫자)가 라벨 오른쪽에
 *    `CountChip` 으로 선다. 괄호 숫자(「사람 (3)」)는 쓰지 않는다 - 제목 옆 건수와 같은 부품이어야
 *    한 화면이 건수를 한 가지 모양으로 말한다. `count` 를 안 주면 칩이 없다(참고 탭은 셀 것이 없다).
 *
 * ## 쓰는 법
 *
 *   <TabShell
 *     area="운영" title="백업"
 *     tabs={[
 *       { key: "backup", label: "백업", help: (role) => …, render: () => <DataScreen config={cfg.backup} embedded /> },
 *       { key: "drills", label: "복구 리허설", render: () => <DataScreen config={cfg.drills} embedded /> },
 *     ]}
 *   />
 *
 * 탭 안에 목록 화면(`DataScreen`)을 두면 그 화면이 자기 필터를 같은 쿼리에 쓴다 —
 * `datascreen-view.js::withHashQuery` 가 **자기 키만** 갈아치우도록 고쳐 둬서 `?tab=` 이
 * 살아남는다. 그 보증이 없으면 필터를 한 칸 건드리는 순간 첫 탭으로 튕긴다.
 */
function tabLabel(t) {
  if (typeof t.count !== "number") return t.label;
  return (
    <Box component="span" data-tab-count="" sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
      {t.label}
      <CountChip value={t.count} compact ariaLabel={`${t.count}건`} />
    </Box>
  );
}

export function TabShell(props) {
  return (
    <HeaderActionsProvider>
      <TabShellBody {...props} />
    </HeaderActionsProvider>
  );
}

function TabShellBody({
  area, title, crumbRoot, tabs, ariaLabel, deniedHelp, idPrefix = "tabshell", actions, children, defaultTab, help: screenHelp,
}) {
  const defs = (tabs || []).filter(Boolean);
  /* 주소에 `?tab=` 이 없을 때 켜지는 탭. 모르는 키를 주면 첫 탭이다 — 조립 실수가 빈 그릇이 되지 않게. */
  const defaultKey = defs.some((t) => t.key === defaultTab) ? defaultTab : (defs.length ? defs[0].key : "");
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

  /* 본문이 머리 동작을 붙였을 때만 자리를 낸다(HeaderSlot.jsx 머리말). */
  const slot = useHeaderActionsSlot();
  const hasActions = !!(slot && slot.count > 0);

  if (auth.isLoading) return <Card><Skeleton /></Card>;
  if (auth.isError) return <ErrorState error={auth.error} onRetry={() => auth.refetch()} />;
  if (!activeDef) return null;

  /* 권한이 없는 탭의 도움말은 안 그린다 — 안내판이 그 자리를 대신한다. 탭이 제 도움말을 갖지 않으면 화면 전체의 도움말
     (`help`)이 그 자리에 선다 — 예전에는 그릇이 그 값을 받지 않아 조직 정합성의 화면 설명이 어디에도 없었다. */
  const rawHelp = roleDenied ? null : (activeDef.help || screenHelp || null);
  const help = typeof rawHelp === "function" ? rawHelp(role) : (rawHelp || null);

  return (
    <Box className="c-screen">
      <PageHeader
        area={area} title={title} crumbRoot={crumbRoot}
        help={help} helpTone={activeDef.helpTone || "info"}
        actions={actions || hasActions ? (
          <>
            {actions}
            {hasActions ? <HeaderActionsHost /> : null}
          </>
        ) : null}
      />
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
              <Tab key={t.key} value={t.key} label={tabLabel(t)} id={tabId(t.key)} aria-controls={panelId(t.key)} />
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
        /* 탭 판도 흐름이다(D-528) - 탭 화면의 덩어리 사이 간격 16 을 판이 주고, 덩어리마다 손으로 적던 위아래 여백을 걷는다. */
        <FlowStack role="tabpanel" id={panelId(activeKey)} aria-labelledby={tabId(activeKey)} tabIndex={0}>
          {/* 탭 판 안의 빈 상태 · 오류 상태는 그 판의 한 칸이다(D-530 — 기본 배치는 담는 쪽이 정한다). */}
          <StateRegion>{activeDef.render()}</StateRegion>
        </FlowStack>
      )}
    </Box>
  );
}

export default TabShell;
