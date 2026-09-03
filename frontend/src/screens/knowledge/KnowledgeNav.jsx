import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Button, Card, Section, Skeleton } from "../../ui/kit.jsx";
import { DragItem, SortableList } from "../../ui/DragDrop.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, MOTION } from "../../ui/theme.js";
import { PROJECT_NONE } from "./constants.js";

/* 좌측 내비 — 「어느 묶음을 볼까」.
 *
 * 옛 탐색기는 보기·프로젝트·폴더·태그 네 절을 들고 있었다. 그중 보기와 태그는 위의
 * 요약 타일·필터 줄과 **같은 축의 중복 입구**였다 — 같은 상태를 두 곳이 그리면 한쪽만
 * 고치는 날이 온다. 지금 이 판이 드는 것은 위 필터 줄이 대신할 수 없는 **구조** 둘뿐이다:
 * 프로젝트(공간)와 그 안의 폴더 트리.
 *
 * 폴더는 **정리**다. 문서를 다른 폴더로 옮겨도 볼 수 있는 사람은 안 바뀐다(§5.3). 그래서
 * 폴더 줄에는 권한 표시가 하나도 없다 — 있으면 사람이 「여기로 옮기면 안 보이게 되겠구나」
 * 라고 잘못 믿는다. */

/* 트리를 평평하게 편다. 들여쓰기는 `depth` 가 만든다 — 화면이 재귀 컴포넌트를 쓰면
 * 끌어 놓기 대상이 계층마다 다른 목록이 되고, 그때부터 「형제 사이로 옮기기」를
 * 정확히 말할 수 없다. */
export function flatten(nodes, out = []) {
  for (const node of nodes || []) {
    out.push(node);
    flatten(node.children, out);
  }
  return out;
}

/** 내비 한 줄. 고른 줄은 색과 `aria-current` 둘 다로 말한다.
 *
 * `action` 은 **평소에 숨는다**(`revealAction`). 폴더 줄의 「삭제」가 늘 떠 있으면 고르는
 * 단추 바로 옆 3px 자리에 지우는 단추가 상시로 서 있고, 그 둘은 같은 크기의 같은 회색
 * 글자다 — 열두 줄이면 「삭제」가 열두 번 보인다. 마우스를 얹거나 키보드 포커스가 이 줄
 * 안에 들어올 때만 나타난다(`:focus-within` 이라 키보드로도 반드시 닿는다). */
export function NavRow({ label, count, selected, indent = 0, onClick, action, revealAction = false }) {
  return (
    <Stack
      direction="row"
      alignItems="center"
      spacing={0.5}
      sx={{
        width: "100%",
        ...(revealAction ? {
          "& .nav-row-action": {
            opacity: 0,
            transition: `opacity ${MOTION.fast} ${MOTION.ease}`,
          },
          "&:hover .nav-row-action, &:focus-within .nav-row-action": { opacity: 1 },
        } : null),
      }}
    >
      <Box
        component="button"
        type="button"
        onClick={onClick}
        aria-current={selected ? "true" : undefined}
        sx={(theme) => ({
          ...KO_WORD_BREAK,
          flex: 1,
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 1,
          textAlign: "left",
          background: selected ? theme.palette.action.selected : "none",
          border: "none",
          borderRadius: 1,
          cursor: "pointer",
          font: "inherit",
          color: "inherit",
          px: 1,
          py: 0.625,
          pl: `${0.75 + indent * 1.1}rem`,
          fontWeight: selected ? FONT_WEIGHT.semibold : FONT_WEIGHT.regular,
        })}
      >
        <Box component="span" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
          {label}
        </Box>
        {count == null ? null : (
          <Box component="span" sx={{ color: "text.secondary", fontSize: FONT_SIZE.caption }}>
            {count}
          </Box>
        )}
      </Box>
      {action ? <Box className="nav-row-action" sx={{ flexShrink: 0 }}>{action}</Box> : null}
    </Stack>
  );
}

/** 절 안의 작은 갈래 이름. `Section` 제목보다 한 단계 아래다 — 「문서 범위」 안에서
 * 프로젝트 줄들이 어디부터인지 말한다. */
function GroupLabel({ children }) {
  return (
    <Typography
      component="p"
      variant="caption"
      color="text.secondary"
      sx={{ px: 1, pt: 0.75, fontWeight: FONT_WEIGHT.semibold }}
    >
      {children}
    </Typography>
  );
}

export function KnowledgeNav({
  entries, value, hasSpace, tree, folderId,
  onSelect, onFolder, onNewFolder, onDeleteFolder, onReorderFolder,
}) {
  const folders = flatten(tree.data?.folders || []);
  const labelOf = (id) => (folders.find((f) => f.id === id) || {}).name || "";
  // 지금 고른 자리의 이름 — 폴더 절 부제로 붙여 「이 폴더는 이 프로젝트의 것」임을
  // 말한다. 안 붙이면 프로젝트 행과 폴더 행이 같은 카드에 같은 모양으로 쌓여
  // 「이 트리가 프로젝트인가」로 읽힌다.
  const selectedLabel = !value
    ? ""
    : (entries || []).find((e) => e.value === value)?.label || "";
  /* 🔴 「공통 문서」는 프로젝트가 아니다. 예전에는 둘이 「프로젝트」 제목 아래 같은
     모양으로 나란히 서서, 이 판이 무엇의 목록인지 제목이 거짓말을 했다. 문서가 앉는
     자리의 축은 **범위**이고 그 값이 「공통 문서」이거나 프로젝트 하나다 — 갈래를 나눠
     그대로 그린다. */
  const common = (entries || []).filter((e) => e.value === PROJECT_NONE);
  const projects = (entries || []).filter((e) => e.value !== PROJECT_NONE);

  return (
    <Card sx={{ display: "grid", gap: 2.5, alignContent: "start" }}>
      {/* 「공간」이라는 낱말은 화면에서 쓰지 않는다(§11.2) — 여기는 프로젝트와 공통
          문서다. 「공간 추가」 단추도 걷었다: 조직 공간은 이관이 만들었고 프로젝트
          공간은 첫 문서를 만들 때 서버가 만든다(§14.2) — 사람이 추가할 공간이 없다. */}
      <Section title="문서 범위" help="문서가 어느 업무 범위에 속하는지 고릅니다.">
        <Stack spacing={0.25}>
          <NavRow label="전체" selected={!value} onClick={() => onSelect("")} />
          {common.map((entry) => (
            <NavRow
              key={entry.value}
              label={entry.label}
              selected={value === entry.value}
              onClick={() => onSelect(entry.value)}
            />
          ))}
        </Stack>
        {projects.length > 0 ? (
          <>
            <GroupLabel>프로젝트</GroupLabel>
            {/* 프로젝트가 스물이 넘으면 이 판이 페이지를 통째로 밀어 내린다 — 폴더 트리와
                같은 규칙으로 **이 칸 안에서만** 굴린다. */}
            <Box sx={{ maxHeight: "20rem", overflowY: "auto" }}>
              <Stack spacing={0.25}>
                {projects.map((entry) => (
                  <NavRow
                    key={entry.value}
                    label={entry.label}
                    selected={value === entry.value}
                    onClick={() => onSelect(entry.value)}
                  />
                ))}
              </Stack>
            </Box>
          </>
        ) : null}
      </Section>

      {/* 폴더는 자리(프로젝트/공통)를 골랐고 그 자리에 실제 공간이 있을 때만 뜻이 있다.
          안 골랐는데 빈 칸을 남겨 두면 「폴더가 없다」로 읽힌다 — 실제로는 아직 안
          물어본 것이다(지시 22.4). */}
      {hasSpace ? (
        <Section
          title="폴더"
          rule
          help={selectedLabel
            ? `${selectedLabel} 안에서 문서를 정리하는 폴더입니다.`
            : "고른 범위 안에서 문서를 정리하는 폴더입니다."}
          action={<Button size="small" variant="ghost" onClick={onNewFolder}>폴더 추가</Button>}
        >
          {tree.isLoading ? <Skeleton kind="section" lines={3} /> : null}
          {!tree.isLoading && folders.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              폴더를 만들면 문서를 주제별로 모아 둘 수 있습니다.
            </Typography>
          ) : null}
          {folders.length > 0 ? (
            /* 트리가 길어지면 **이 칸 안에서만** 굴러간다 (지시 22.4). 이 칸이 페이지를
               늘리면 목록을 보려고 폴더를 지나쳐 내려가야 한다. */
            <Box sx={{ maxHeight: "22rem", overflowY: "auto" }}>
              <SortableList items={folders} labelOf={labelOf} onReorder={onReorderFolder}>
                {(folder) => (
                  <DragItem key={folder.id} id={folder.id} label={folder.name}>
                    <NavRow
                      label={folder.name}
                      indent={folder.depth}
                      selected={folderId === folder.id}
                      onClick={() => onFolder(folder.id)}
                      revealAction
                      action={(
                        <Button
                          size="small"
                          variant="ghost"
                          aria-label={`${folder.name} 폴더 삭제`}
                          onClick={() => onDeleteFolder(folder)}
                        >
                          삭제
                        </Button>
                      )}
                    />
                  </DragItem>
                )}
              </SortableList>
            </Box>
          ) : null}
        </Section>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          {value
            ? "아직 문서가 없는 프로젝트입니다. 첫 문서를 만들면 폴더를 정리할 수 있습니다."
            : "프로젝트를 고르면 그 안의 폴더가 여기에 나타납니다."}
        </Typography>
      )}
    </Card>
  );
}
