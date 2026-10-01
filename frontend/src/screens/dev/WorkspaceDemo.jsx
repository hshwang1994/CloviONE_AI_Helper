import React from "react";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Typography from "@mui/material/Typography";
import { DataTable, PageHeader } from "../../ui/kit.jsx";
import { SearchBox } from "../../ui/filters.jsx";
import { PaneHead, PaneToolbar, Workspace, WorkspacePane } from "../../ui/Workspace.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../../ui/theme.js";

/* 작업 공간 견본 (F5 · D-531) — 채움 모드 · 판 굴림 · 표 채움을 실브라우저로 재는 개발용 화면이다(`scripts/ui_qa/workspace_e2e.py`).
 *
 * 서버를 부르지 않는다 — 왼쪽은 트리 행 200줄, 오른쪽은 구성원 150명을 50명씩 「받는」 표다(받기는 150ms 늦춘 화면 안 계산).
 * 제품 화면(조직 관리)이 같은 부품을 쓰기 전에, 부품만으로 문서 높이 · 판 아래 끝 · 판의 독립 굴림 · 고정 영역 · 판 안 무한 받기를
 * 잴 수 있게 한다. */
const TREE = Array.from({ length: 200 }, (_, i) => ({ id: `n${i}`, name: `부서 ${i + 1}`, depth: i % 4, count: (i * 7) % 23 }));
const PEOPLE = Array.from({ length: 150 }, (_, i) => ({
  id: `u${i}`,
  name: `구성원 ${String(i + 1).padStart(3, "0")}`,
  email: `member${i + 1}@example.com`,
  dept: `부서 ${(i % 12) + 1}`,
  state: i % 9 === 0 ? "비활성" : "활성",
}));
const CHUNK = 50;

const COLUMNS = [
  { key: "name", label: "이름", type: "name" },
  { key: "email", label: "이메일", type: "identifier" },
  { key: "dept", label: "부서", type: "text", tier: "context" },
  { key: "state", label: "상태", type: "status", values: ["활성", "비활성"] },
];

export function WorkspaceDemo() {
  const [picked, setPicked] = React.useState(TREE[0].id);
  const [chunks, setChunks] = React.useState(1);
  const [fetching, setFetching] = React.useState(false);
  const rows = PEOPLE.slice(0, chunks * CHUNK);
  const more = React.useCallback(() => {
    if (fetching) return;
    setFetching(true);
    window.setTimeout(() => {
      setChunks((c) => Math.min(Math.ceil(PEOPLE.length / CHUNK), c + 1));
      setFetching(false);
    }, 150);
  }, [fetching]);

  return (
    <Workspace header={<PageHeader area="개발" title="작업 공간 견본" help="작업 공간 부품이 창 높이 안에 서고 판마다 따로 굴러가는지 재는 개발용 화면입니다." />}>
      <WorkspacePane
        label="트리"
        toolbar={<SearchBox value="" onSearch={() => {}} placeholder="부서 검색" ariaLabel="부서 검색" layout="fill" />}
        bodyLabel="부서 트리"
        flowMaxHeight="min(50vh, 28rem)"
      >
        <Box component="ul" data-demo-tree="" sx={{ listStyle: "none", m: 0, p: 0.5 }}>
          {TREE.map((n) => (
            <Box component="li" key={n.id}>
              <ButtonBase
                onClick={() => setPicked(n.id)}
                aria-current={picked === n.id ? "true" : undefined}
                sx={{
                  width: "100%", height: "2.25rem", justifyContent: "space-between", px: 1.5, pl: 1.5 + n.depth * 2,
                  borderRadius: 1, fontSize: FONT_SIZE.body,
                  bgcolor: picked === n.id ? "primary.light" : "transparent",
                  "&:hover": { bgcolor: picked === n.id ? "primary.light" : "background.inset" },
                }}
              >
                <span>{n.name}</span>
                <Typography component="span" variant="caption" color="text.secondary">{n.count}명</Typography>
              </ButtonBase>
            </Box>
          ))}
        </Box>
      </WorkspacePane>
      <WorkspacePane
        label="구성원"
        head={<PaneHead title={`${TREE.find((n) => n.id === picked).name}`} above={<Typography variant="caption" color="text.secondary">견본 조직 › 견본 본부</Typography>} />}
        toolbar={(
          <PaneToolbar>
            <Typography component="h3" sx={{ fontWeight: FONT_WEIGHT.semibold }}>구성원 {PEOPLE.length}명</Typography>
            <SearchBox value="" onSearch={() => {}} placeholder="이름, 이메일 검색" ariaLabel="구성원 검색" />
          </PaneToolbar>
        )}
        body="table"
      >
        <DataTable
          fill
          stickyHeader
          columns={COLUMNS}
          rows={rows}
          rowKey={(r) => r.id}
          list={{ total: PEOPLE.length, loaded: rows.length, hasNext: rows.length < PEOPLE.length, isFetchingNext: fetching, onMore: more, unit: "명", moreLabel: "구성원 더 보기" }}
        />
      </WorkspacePane>
    </Workspace>
  );
}

export default WorkspaceDemo;
