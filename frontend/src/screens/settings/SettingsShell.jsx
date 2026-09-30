import React from "react";
import Box from "@mui/material/Box";
import { useAuth } from "../../app/auth.jsx";
import { TabShell } from "../../ui/TabShell.jsx";
import { Settings } from "./SettingsMain.jsx";
import { SystemOps, HELP as SYSTEM_OPS_HELP } from "../SystemOps.jsx";
import { AiSettings } from "./AiSettings.jsx";
import { StorageProviders, HELP as STORAGE_HELP } from "../StorageProviders.jsx";
import { Maintenance } from "../ops/Maintenance.jsx";

/* 설정 — 6화면 IA 정리(PA-RC-0017)의 탭 그릇.
 *
 * ## 왜 여섯 화면 중 셋만 탭이 되는가
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
 * 남은 셋(설정·시스템 설정·AI 관리)은 각자 role 이 탭 하나에 균일해 그대로 매핑된다.
 * Handoff의 수를 글자 그대로 맞추기보다, 탭마다 role 이 하나로 균일해야 한다는 더 강한
 * 제약(RBAC 회귀 없음)을 우선했다. 이 판단은 DECISIONS.md에 남긴다.
 *
 * ## 「연동」 탭이 사라진 이유
 *
 * 이 그릇에는 넷째 탭 「연동」이 있었고 그 안에는 Notion 관리 화면 하나만 들어 있었다.
 * 티켓과 문서와 프로젝트가 이 서버의 데이터베이스에서 나오게 되면서 그 화면이 고치던
 * 값(노션 토큰과 데이터베이스 id)이 제품에서 없어졌고, 화면도 함께 없어졌다. 그래서 탭도
 * 뺀다 — 누를 수는 있는데 아무것도 안 들어 있는 탭은 사용자에게 「여기에 무언가 있는데 내가
 * 못 보는 것」으로 읽히고, 그것은 없는 것을 있는 척 그리는 일이다. 외부 연동은 원래부터
 * 자기 화면(`#/integrations`)과 자기 사이드바 항목을 갖고 있으므로 이 탭이 없어져도 갈 곳을
 * 잃지 않는다.
 *
 * ## role 게이트를 두 번 거는 이유
 *
 * `visibleTabs`가 이미 role 로 걸러 `tab` 이 "os"/"ai" 가 되는 순간 role 은 system_admin 으로
 * 보장된다 — 그런데도 아래 렌더 분기에 role 검사를 한 번 더 남긴다. SystemOps/AiSettings 는
 * 지금까지 라우트의 RequireRole 하나에만 기대 왔고 자체 role 검사가 없다(Settings/Maintenance
 * 와 달리) — 이 화면들이 처음으로 "라우트가 아니라 탭 상태"로 접근 가능해지는 지점이라,
 * 파생 로직 한 곳의 실수가 OS 특권 동작을 그대로 노출시킬 수 있다. 실제 서버 게이트는 각
 * 라우터가 독립적으로 걸지만(정본은 거기다), 프런트에서도 이 경계만은 한 겹을 더 둔다.
 *
 * ## 그릇은 `TabShell` 이다
 *
 * 이 파일이 탭 그릇 로직(역할로 거르기 · 모르는 탭과 못 보는 탭 구별 · 딥링크 · 탭↔패널
 * 연결 · 머리 동작 자리)을 먼저 만들었고, `ui/TabShell.jsx` 가 그것을 공용으로 옮겼다. 두
 * 사본이 따로 고쳐지지 않게 여기서도 그 그릇을 쓴다(핸드오프 계획 B-7 「페이지 탭 = TabShell」).
 * 탭 id 는 `settings-tab-*` · `settings-tabpanel-*` 그대로다(`idPrefix`).
 */

/* `help` 는 그릇이 제목 옆 `?` 로 그린다(D-453) — 탭 본문이 자기 첫 줄에 설명 문단을 두지
   않는다. 문장이 없는 탭은 `?` 도 없다. */
export const TAB_DEFS = [
  { key: "policy", label: "시스템 정책", roles: null },
  { key: "os", label: "OS와 서비스 동작", roles: ["system_admin"], help: SYSTEM_OPS_HELP },
  /* 파일 저장소 (S20). S8 이 만든 `/api/storage/*` 는 **부르는 화면이 없었다** — 관리자는
     업로드가 어디로 가는지, 그 자리가 지금 붙어 있는지, 운영과 백업이 같은 장치에 있는지를
     서버에 들어가야만 알 수 있었다. 여기 두는 이유는 목표 IA(`MASTER_PLAN.md` §14.1)가
     「일반 설정 · File Storage · AI 설정」을 한 묶음으로 적었기 때문이고, 권한도 그 이웃들과
     같다: `STORAGE_CONFIGURE` 는 `SYSTEM_ADMIN_ONLY`(app/authz/permissions.py)라 os·ai 탭과
     정확히 같은 집합이다 — 탭마다 role 이 균일해야 한다는 이 그릇의 제약을 그대로 만족한다. */
  { key: "storage", label: "파일 저장소", roles: ["system_admin"], help: STORAGE_HELP },
  { key: "ai", label: "AI", roles: ["system_admin"] },
];
/** 탭 키만 뽑은 목록 — 커버리지 대조용(`registry-surface-parity.test.js`). */
export const SETTINGS_TAB_KEYS = TAB_DEFS.map((t) => t.key);

const SYSTEM_ADMIN_TAB_HELP = "이 화면은 시스템 관리자만 사용할 수 있습니다.";

export function SettingsShell() {
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  /* 본문 분기에 role 을 한 번 더 건다(위 「role 게이트를 두 번 거는 이유」). 탭 줄에서 이미
     걸렀어도 탭 상태 한 곳의 실수가 OS 특권 화면을 그리지 않게 한다. */
  const isSystemAdmin = role === "system_admin";
  const render = {
    policy: () => (
      <>
        <Settings embedded />
        <Box sx={{ mt: 4 }}>
          <Maintenance embedded />
        </Box>
      </>
    ),
    os: () => (isSystemAdmin ? <SystemOps embedded /> : null),
    storage: () => (isSystemAdmin ? <StorageProviders embedded /> : null),
    ai: () => (isSystemAdmin ? <AiSettings /> : null),
  };
  /* 사이드바가 이 화면을 「설정」 묶음에 두므로 빵부스러기도 「설정」이다(S20). 제목은 고정이고
     탭은 아래다(D-452) — 예전에는 탭 라벨이 h1 이라 「AI」가 제목이었다. 전환할 곳이 없는 탭
     줄(system_admin 이 아니면 항상 1개)은 그릇이 그리지 않는다. */
  return (
    <TabShell
      area="설정"
      title="설정"
      ariaLabel="설정 탭"
      idPrefix="settings"
      deniedHelp={SYSTEM_ADMIN_TAB_HELP}
      tabs={TAB_DEFS.map((t) => ({ ...t, render: render[t.key] }))}
    />
  );
}

export default SettingsShell;
