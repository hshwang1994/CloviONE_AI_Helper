import React, { useState } from "react";
import Box from "@mui/material/Box";
import { DataScreen } from "./DataScreen.jsx";
import { OrgTree, isOrgRow } from "./OrgTree.jsx";
import { ORG_SCREENS } from "./registry/org.js";
import { Callout, PageHeader } from "../ui/kit.jsx";

/* 조직 콘솔 — 조직 관리, 부서 관리, 조직도를 한 화면으로.
 *
 * ## 왜 합쳤나
 *
 * 사용자 지적: "조직관리랑 부서관리랑 조직도 페이지는 하나로 묶을 수 있는거아님? 조직도가
 * 왼쪽 트리로 보이고 오른쪽에서 조직이랑 부서 관리할 수 있도록 하면 되는거아님?"
 *
 * 정당한 지적이었다. 부서 하나를 다른 부서 밑으로 옮기려면 `/org-tree` 에서 계층을 확인하고,
 * `/departments` 로 이동해 그 부서를 찾아 고치고, 결과를 보려고 다시 `/org-tree` 로 돌아와야
 * 했다. 세 화면이 **같은 자료의 세 가지 보기**인데 주소가 셋이라 왕복이 생겼다.
 *
 * ## 무엇을 여기서 만들지 않았나
 *
 * 열, 필터, 생성/수정 폼, 액션은 **한 줄도 다시 적지 않는다**. 오른쪽은 기존
 * `organizations` / `departments` 화면 설정(registry/org.js)을 그대로 `DataScreen` 에
 * 넘길 뿐이다. 여기 한 벌 더 적으면 조직 화면을 고쳤을 때 콘솔만 옛 폼을 계속 보여 준다.
 *
 * ## 선택이 없을 때 무엇을 보여 주는가
 *
 * **조직 관리**다. 트리의 뿌리가 조직이고 부서는 그 아래에 속하므로, 아무것도 고르지 않은
 * 상태에서 화면은 트리와 같은 방향(위에서 아래로)을 가리켜야 한다. 부서를 기본으로 두면
 * 첫 화면이 "이 부서들은 어느 조직 것인가"라는 질문을 남긴 채 시작한다.
 * 딥링크로 들어온 경우에는 그 주소가 가리키는 쪽을 기본으로 쓴다(`defaultKind`).
 *
 * ## 트리를 눌렀을 때 상세 모달을 자동으로 열지 않는 이유
 *
 * 상세, 수정 폼은 전체 화면 대화상자다(ui/kit.jsx 의 Modal 은 배경을 덮는 MUI Dialog 다).
 * 트리를 누를 때마다 그것이 열리면 **사용자가 나란히 보고 싶다고 한 바로 그 트리**를 덮고,
 * 닫기 전까지 다음 노드를 누를 수도 없다. 그래서 누르면 오른쪽이 그 종류의 관리 화면으로
 * 바뀌고 노드가 강조될 뿐, 상세는 사용자가 열 때만 열린다.
 */

/* 왼쪽 1, 오른쪽 2.
 *
 * 기준 폭(flex-basis)까지 1:2 로 맞춘다. flex-grow 만 1:2 로 두면 남는 폭만 1:2 로 나뉘고
 * 기준 폭은 그대로 남아 실제 비율이 화면 폭마다 달라진다. 둘 다 1:2 면 어느 폭에서도 정확히
 * 1/3, 2/3 이다.
 *
 * 좁은 화면에서 위아래로 쌓는 일은 **미디어 쿼리가 아니라 줄바꿈**으로 한다. 두 기준 폭의
 * 합(48rem)이 안 들어가는 순간 오른쪽 칸이 다음 줄로 내려간다. 판단 기준이 뷰포트가 아니라
 * **이 칸에 실제로 남은 폭**이라, 사이드바가 펼쳐져 본문이 좁아진 넓은 화면에서도 맞는다.
 */
const TREE_PANE = { flexGrow: 1, flexShrink: 1, flexBasis: "16rem", minWidth: 0 };
const MANAGE_PANE = { flexGrow: 2, flexShrink: 1, flexBasis: "32rem", minWidth: 0 };

/** 트리 행의 종류 → 오른쪽에 띄울 관리 화면 키. */
const screenKeyFor = (row) => (isOrgRow(row) ? "organizations" : "departments");

export function OrgConsole({ defaultKind = "organizations" }) {
  // {id, screenKey} — 아직 아무것도 고르지 않았으면 null 이다.
  const [selected, setSelected] = useState(null);
  const screenKey = selected ? selected.screenKey : defaultKind;
  const config = ORG_SCREENS[screenKey] || ORG_SCREENS.organizations;
  /* 오른쪽 DataScreen 이 그리는 제목("조직 관리"/"부서 관리")은 없애지 않는다 — 이 화면
   * (오른쪽 절반)이 실제로 무엇을 관리하는 패널인지 알려 주는 유일한 단서라 없애면 오른쪽
   * 패널만 봤을 때 무엇을 보고 있는지 알 수 없다. 대신 두 가지를 낮춘다:
   * area — "관리자 › 사용자" 빵부스러기가 콘솔 전체 제목과 겹쳐 세로로 두 번 찍히던 것.
   * compact — PageHeader를 h4/h1(페이지 제목과 같은 무게)이 아니라 h6/h2로 낮춘다. 이전에는
   * 글자 크기가 페이지 제목과 같아 "오른쪽이 또 다른 페이지처럼" 보였다(사용자 지적:
   * "조직도가 제일 상단 왼쪽으로 올려져있음" — 실은 오른쪽 패널이 같은 무게로 맞서고 있었다). */
  const panelConfig = { ...config, area: null, compact: true };

  return (
    <div className="c-screen">
      <PageHeader area="사용자와 권한" title="조직도" />
      <Box sx={{ mb: 2.5 }}>
        <Callout>조직이나 부서를 누르면 오른쪽에서 바로 관리할 수 있습니다.</Callout>
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 2.5 }}>
        <Box data-testid="org-console-tree" sx={TREE_PANE}>
          <OrgTree
            selectedId={selected ? selected.id : null}
            onSelect={(row) => setSelected({ id: row.id, screenKey: screenKeyFor(row) })}
          />
        </Box>
        <Box data-testid="org-console-panel" sx={{ ...MANAGE_PANE, "& .k-page-head": { mb: 1.5 } }}>
          {/* key 로 갈아 끼운다 — 같은 자리에 다른 설정만 넘기면 React 는 컴포넌트를 유지해
              조직 화면에서 걸어 둔 검색어, 페이지 번호가 부서 화면에 그대로 남는다. */}
          <DataScreen key={config.key} config={panelConfig} />
        </Box>
      </Box>
    </div>
  );
}

export default OrgConsole;
