import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Button, Card, Section, Skeleton } from "../../ui/kit.jsx";
import { DragItem, SortableList } from "../../ui/DragDrop.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { spaceDisplayName } from "./constants.js";

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

/** 내비 한 줄. 고른 줄은 색과 `aria-current` 둘 다로 말한다. */
export function NavRow({ label, count, selected, indent = 0, onClick, action }) {
  return (
    <Stack direction="row" alignItems="center" spacing={0.5} sx={{ width: "100%" }}>
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
      {action}
    </Stack>
  );
}

export function KnowledgeNav({
  entries, value, hasSpace, tree, folderId,
  onSelect, onFolder, onNewFolder, onDeleteFolder, onReorderFolder,
}) {
  const folders = flatten(tree.data?.folders || []);
  const labelOf = (id) => (folders.find((f) => f.id === id) || {}).name || "";

  return (
    <Card sx={{ display: "grid", gap: 2.5, alignContent: "start" }}>
      {/* 「공간」이라는 낱말은 화면에서 쓰지 않는다(§11.2) — 여기는 프로젝트와 공통
          문서다. 「공간 추가」 단추도 걷었다: 조직 공간은 이관이 만들었고 프로젝트
          공간은 첫 문서를 만들 때 서버가 만든다(§14.2) — 사람이 추가할 공간이 없다. */}
      <Section title="프로젝트">
        <Stack spacing={0.25}>
          <NavRow label="전체" selected={!value} onClick={() => onSelect("")} />
          {(entries || []).map((entry) => (
            <NavRow
              key={entry.value}
              label={entry.label}
              selected={value === entry.value}
              onClick={() => onSelect(entry.value)}
            />
          ))}
        </Stack>
      </Section>

      {/* 폴더는 자리(프로젝트/공통)를 골랐고 그 자리에 실제 공간이 있을 때만 뜻이 있다.
          안 골랐는데 빈 칸을 남겨 두면 「폴더가 없다」로 읽힌다 — 실제로는 아직 안
          물어본 것이다(지시 22.4). */}
      {hasSpace ? (
        <Section
          title="폴더"
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
                      action={(
                        <Button size="small" variant="ghost" onClick={() => onDeleteFolder(folder)}>
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
