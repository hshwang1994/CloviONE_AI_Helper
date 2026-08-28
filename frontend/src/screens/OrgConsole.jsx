import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { DataScreen } from "./DataScreen.jsx";
import { OrgTree, isOrgRow } from "./OrgTree.jsx";
import { ORG_SCREENS } from "./registry/org.js";
import { Badge, Card, EmptyState, ErrorState, SectionTitle, Skeleton, PageHeader } from "../ui/kit.jsx";
import { Note } from "../ui/adminKit.jsx";

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
/* 셋째 판 — **관련 컬렉션**. 분할 뷰 원형의 계약이 «≥1920 에서 3번째 pane» 이다.
   그 폭이 안 되면 아예 안 그린다(줄바꿈으로 아래에 쌓으면 그건 3판이 아니라 목록 하나가
   더 생긴 것이다). 기준 폭은 두 판의 합(48rem)에 이 판(20rem)을 더한 값이라,
   판단 기준이 뷰포트가 아니라 **이 칸에 남은 폭**이다 — 위 두 판과 같은 규칙이다. */
const PEOPLE_PANE = { flexGrow: 1, flexShrink: 1, flexBasis: "20rem", minWidth: 0,
                      display: { xs: "none", xl: "block" } };

/** 트리 행의 종류 → 오른쪽에 띄울 관리 화면 키. */
const screenKeyFor = (row) => (isOrgRow(row) ? "organizations" : "departments");

/* 이 부서에 **누가 있는가** — 분할 뷰의 셋째 판.
 *
 * 계획서가 이 화면에 적은 가장 값진 숫자는 「부서 미지정 12명」이었다. 트리는 부서마다
 * 인원수를 이미 말하는데, 그 수를 눌러 **사람 목록으로 내려갈 길이 없었다** — 그래서
 * 관리자는 「이 부서에 누가 있지」를 물으려고 사용자 화면으로 나가 필터를 다시 걸었다.
 * 필요한 엔드포인트는 이미 있다(`/api/admin/users?department_id=`).
 *
 * 목록을 다시 만들지 않는다. 여기서 보여 주는 것은 «이 마디에 속한 사람» 여덟까지고,
 * 그보다 많으면 그 조건이 걸린 사용자 화면으로 보낸다 — 같은 목록을 두 화면이 각자
 * 그리기 시작하면 언젠가 두 화면이 다른 답을 한다.
 */
const PEOPLE_PREVIEW = 8;

function DepartmentPeople({ node }) {
  const departmentId = node && node.screenKey === "departments" ? node.id : null;
  const q = useQuery({
    queryKey: ["org-console", "people", departmentId],
    queryFn: () => api("/api/admin/users?department_id=" + encodeURIComponent(departmentId)),
    enabled: !!departmentId,
    retry: false,
  });

  if (!departmentId) {
    return (
      <Card>
        <SectionTitle component="h2" title="소속 인원" />
        <EmptyState
          layout="inline"
          title="부서를 고르면 그 부서 사람이 보입니다"
          help="조직을 고른 상태에서는 인원이 부서별로 나뉘어 있어 한 줄로 셀 수 없습니다."
        />
      </Card>
    );
  }
  const items = (q.data && q.data.items) || [];
  const total = q.data && q.data.total != null ? q.data.total : items.length;
  return (
    <Card>
      <SectionTitle component="h2" title={"소속 인원 " + (q.isPending ? "" : total + "명")} />
      {q.isPending ? <Skeleton lines={4} /> : null}
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
      {!q.isPending && !q.isError && items.length === 0 ? (
        <EmptyState
          layout="inline"
          title="이 부서에 배치된 사람이 없습니다"
          help="사용자 화면에서 부서를 지정하면 여기에 표시됩니다."
        />
      ) : null}
      {items.length ? (
        <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
          {items.slice(0, PEOPLE_PREVIEW).map((u) => (
            <Box component="li" key={u.id} sx={{ display: "flex", gap: 1, alignItems: "baseline",
                                                 justifyContent: "space-between", minWidth: 0 }}>
              <Link href={"#/users/" + u.id} underline="hover"
                    sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {u.display_name || u.email}
              </Link>
              <Badge value={u.title || u.role} />
            </Box>
          ))}
        </Box>
      ) : null}
      {total > PEOPLE_PREVIEW ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
          {PEOPLE_PREVIEW}명만 표시했습니다.{" "}
          <Link href={"#/users?department_id=" + encodeURIComponent(departmentId)} underline="hover">
            사용자 화면에서 {total}명 모두 보기
          </Link>
        </Typography>
      ) : null}
    </Card>
  );
}

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
      <PageHeader
        area="사용자와 권한" title="조직도"
        description="조직도를 보면서 같은 화면에서 조직과 부서를 관리합니다."
      />
      <Box sx={{ mb: 2.5 }}>
        <Note sx={{ mt: 0 }}>조직이나 부서를 누르면 오른쪽에서 바로 관리할 수 있습니다.</Note>
      </Box>
      {/* **전체 높이 판**이다 (B11 · S18).
          예전에는 세 판이 각자 자기 내용 높이에서 멈춰, 조직 하나·부서 셋인 조직에서
          트리가 y≈490 에서 끝나고 그 아래 590px 가 죽은 채 남았다(하단 공백 46% — S18
          실측). 분할 뷰의 계약은 «2~3 전체 높이 pane» 이다: 판이 화면 높이를 차지하고
          그 안에서 내용이 흐른다. 좁은 화면에서는 줄바꿈으로 쌓이므로 그때는 높이를
          강요하지 않는다(내용 높이 그대로). */}
      <Box sx={{
        display: "flex", flexWrap: "wrap", alignItems: "stretch", gap: 2.5,
        minHeight: { xs: "auto", lg: "calc(100vh - 16rem)" },
        "& > * > .MuiPaper-root": { height: "100%" },
      }}>
        <Box data-testid="org-console-tree" sx={TREE_PANE}>
          <OrgTree
            selectedId={selected ? selected.id : null}
            onSelect={(row) => setSelected({ id: row.id, screenKey: screenKeyFor(row) })}
          />
        </Box>
        <Box data-testid="org-console-panel" sx={{ ...MANAGE_PANE, "& .k-page-head": { mb: 1.5 } }}>
          {/* key 로 갈아 끼운다 — 같은 자리에 다른 설정만 넘기면 React 는 컴포넌트를 유지해
              조직 화면에서 걸어 둔 검색어, 페이지 번호가 부서 화면에 그대로 남는다.

              `inSplitView` — **왼쪽 트리가 이미 검색이다.** 그 한 줄이 이 판의 검색 상자와
              저장된 뷰를 내린다(DataScreen 의 같은 이름 주석에 이유를 적었다). 이 화면에는
              같은 엔티티를 찾는 상자가 둘 있었고, 계획서가 그것을 이 화면의 결함으로 이름
              대어 적어 두었다. 조건 축(상태 필터)은 **그대로 둔다** — 트리가 대신하지 않는
              축이라, 지우면 그건 중복 제거가 아니라 기능 삭제다. */}
          <DataScreen key={config.key} config={panelConfig} inSplitView />
        </Box>
        <Box data-testid="org-console-people" sx={PEOPLE_PANE}>
          <DepartmentPeople node={selected} />
        </Box>
      </Box>
    </div>
  );
}

export default OrgConsole;
