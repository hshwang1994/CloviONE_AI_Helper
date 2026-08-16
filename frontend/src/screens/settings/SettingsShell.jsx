import React from "react";
import Box from "@mui/material/Box";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import { useAuth } from "../../app/auth.jsx";
import { PageHeader } from "../../ui/kit.jsx";
import { useQueryState } from "../../lib/useQueryState.js";
import { Settings } from "./SettingsMain.jsx";
import { SystemOps } from "../SystemOps.jsx";
import { NotionConsole } from "../NotionConsole.jsx";
import { LlmConsole } from "../LlmConsole.jsx";
import { Maintenance } from "../ops/Maintenance.jsx";

/* 설정 — 6화면 IA 정리(PA-RC-0017)의 탭 그릇.
 *
 * ## 왜 여섯 화면 중 넷만 탭이 되는가
 *
 * Handoff는 「설정·시스템 설정·초기 설정·유지보수·Notion 관리·AI 관리」 여섯을 4탭(시스템
 * 정책/OS와 서비스 동작/연동/AI)으로 묶으라 했다. 그대로 여섯을 넷에 욱여넣으면 두 가지가
 * 깨진다.
 *
 * 1. **초기 설정**(SetupWizard.jsx)은 값을 보여주는 패널이 아니라 "무엇부터 하라"는
 *    순서가 있는 체크리스트 마법사다 — 탭이라는 그릇 자체가 안 맞는다. 상단 배너의 직접
 *    링크로도 이미 닿는다. 그대로 독립 화면(/setup)에 남긴다.
 * 2. **유지보수**(Maintenance.jsx)를 시스템 설정과 한 탭에 묶으면 role 이 부서진다 — 시스템
 *    설정은 system_admin 전용인데 유지보수는 operator/admin/system_admin/auditor 까지 읽을
 *    수 있다(각 라우트의 기존 RequireRole 그대로). 한 탭에 넣으려면 둘 중 하나를 넓히거나
 *    좁혀야 하는데, 전자는 OS 특권 동작을 읽기 전용 역할에게 노출하는 권한 상승이고 후자는
 *    지금 볼 수 있는 사람이 못 보게 되는 회귀다. 대신 유지보수는 **설정과 같은 "넓게 읽고
 *    좁게 쓴다" 성격**을 공유하므로(Maintenance.jsx의 canWrite, SettingsMain.jsx의 canWrite와
 *    같은 모양) '시스템 정책' 탭 안에 설정 표 바로 아래로 이어붙인다 — role 집합이 사실상
 *    같은 화면끼리만 한 탭에 둔다.
 *
 * 남은 넷(설정·시스템 설정·Notion 관리·AI 관리)은 각자 role 이 탭 하나에 균일해 그대로
 * 매핑된다. 결과: 6화면 → 3목적지(설정 탭 그룹, 초기 설정, 그리고 없어짐)로 실질적으로
 * 줄었다 — Handoff의 수를 글자 그대로 맞추기보다, 탭마다 role 이 하나로 균일해야 한다는
 * 더 강한 제약(RBAC 회귀 없음)을 우선했다. 이 판단은 DECISIONS.md에 남긴다.
 *
 * ## role 게이트를 두 번 거는 이유
 *
 * `visibleTabs`가 이미 role 로 걸러 `tab` 이 "os"/"integration"/"ai" 가 되는 순간 role 은
 * system_admin 으로 보장된다 — 그런데도 아래 렌더 분기에 role 검사를 한 번 더 남긴다.
 * SystemOps/NotionConsole/LlmConsole 은 지금까지 라우트의 RequireRole 하나에만 기대 왔고
 * 자체 role 검사가 없다(Settings/Maintenance 와 달리) — 이 화면들이 처음으로 "라우트가
 * 아니라 탭 상태"로 접근 가능해지는 지점이라, 파생 로직 한 곳의 실수가 OS 특권 동작을
 * 그대로 노출시킬 수 있다. 실제 서버 게이트는 각 라우터가 독립적으로 걸지만(정본은 거기다),
 * 프런트에서도 이 경계만은 한 겹을 더 둔다.
 */
const TAB_SPEC = { tab: "policy" };

const TAB_DEFS = [
  { key: "policy", label: "시스템 정책", roles: null },
  { key: "os", label: "OS와 서비스 동작", roles: ["system_admin"] },
  { key: "integration", label: "연동", roles: ["system_admin"] },
  { key: "ai", label: "AI", roles: ["system_admin"] },
];

export function SettingsShell() {
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  const visibleTabs = TAB_DEFS.filter((t) => !t.roles || t.roles.includes(role));
  const [state, setState] = useQueryState(TAB_SPEC);
  const tabKeys = visibleTabs.map((t) => t.key);
  // 모르는(또는 지금 role 로는 못 보는) tab 값이 주소에 있으면 첫 탭으로 떨어진다 — 오래된
  // 북마크·손으로 고친 주소·역할이 바뀐 뒤 남은 링크가 빈 화면이나 에러 대신 항상 뭔가를
  // 보여주게 한다(Project.jsx 상세 탭과 같은 관례).
  const tab = tabKeys.includes(state.tab) ? state.tab : "policy";
  const activeLabel = (visibleTabs.find((t) => t.key === tab) || visibleTabs[0]).label;

  // Project.jsx의 상세 탭(TABS.map)에는 이 id/aria-controls 연결이 없다 — 그쪽도 같은 MUI
  // Tabs 패턴을 쓰므로 이 화면만 고친다고 전체가 나아지진 않는다(BACKLOG의 별도 항목으로
  // 남긴다). 여기서는 새로 만드는 화면이니 처음부터 WAI-ARIA Tabs 패턴대로 탭↔패널을 잇는다.
  const tabId = (key) => `settings-tab-${key}`;
  const panelId = (key) => `settings-tabpanel-${key}`;

  return (
    <Box className="c-screen">
      <PageHeader area="운영" title="설정" tab={activeLabel} />
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2.5 }}>
        <Tabs
          value={tab}
          onChange={(e, next) => setState({ tab: next })}
          variant="scrollable"
          allowScrollButtonsMobile
          aria-label="설정 탭"
        >
          {visibleTabs.map((t) => (
            <Tab key={t.key} value={t.key} label={t.label} id={tabId(t.key)} aria-controls={panelId(t.key)} />
          ))}
        </Tabs>
      </Box>

      <Box role="tabpanel" id={panelId(tab)} aria-labelledby={tabId(tab)} tabIndex={0}>
        {tab === "policy" ? (
          <>
            <Settings embedded />
            <Box sx={{ mt: 4 }}>
              <Maintenance embedded />
            </Box>
          </>
        ) : null}
        {tab === "os" && role === "system_admin" ? <SystemOps embedded /> : null}
        {tab === "integration" && role === "system_admin" ? <NotionConsole embedded /> : null}
        {tab === "ai" && role === "system_admin" ? <LlmConsole embedded /> : null}
      </Box>
    </Box>
  );
}

export default SettingsShell;
