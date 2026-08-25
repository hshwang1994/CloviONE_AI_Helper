import React from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import { DebouncedTextField, EntityCombobox, FilterSelect } from "./filters.jsx";

/* 열 머리글에서 여는 필터. 헤더 아래에 입력칸을 항상 늘어놓지 않는다.
 * 값은 화면이 들고 API 로 보낸다. 지금 페이지 행만 걸러서 전체 필터처럼 보이게 하지 않는다. */

export function ColumnFilterPopover({
  open, anchorEl, onClose, column, value, onChange, options, entityOptions,
}) {
  const kind = (column && column.filter && column.filter.kind) || inferKind(column);
  const label = (column && column.label) || "";
  const set = (next) => onChange(next);

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
    >
      <Box sx={{ p: 1.5, minWidth: "16rem", maxWidth: "22rem" }}>
        <Stack gap={1.25}>
          {kind === "enum" ? (
            <FilterSelect
              multiple label={label} value={Array.isArray(value) ? value : []}
              onChange={set} options={options || []}
            />
          ) : null}
          {kind === "entity" ? (
            <EntityCombobox
              multiple label={label} value={Array.isArray(value) ? value : []}
              onChange={set} options={entityOptions || []}
            />
          ) : null}
          {kind === "text" ? (
            <DebouncedTextField label={label} value={value || ""} onCommit={set} />
          ) : null}
          {kind === "number" ? (
            <Stack direction="row" gap={1}>
              <DebouncedTextField
                kind="number" label="최소" value={(value && value.min) || ""}
                onCommit={(min) => set({ ...(value || {}), min })}
              />
              <DebouncedTextField
                kind="number" label="최대" value={(value && value.max) || ""}
                onCommit={(max) => set({ ...(value || {}), max })}
              />
            </Stack>
          ) : null}
          {kind === "date" ? (
            <Stack direction="row" gap={1}>
              <DebouncedTextField
                kind="date" label="시작" value={(value && value.from) || ""}
                onCommit={(from) => set({ ...(value || {}), from })}
                inputProps={{ type: "date" }}
              />
              <DebouncedTextField
                kind="date" label="끝" value={(value && value.to) || ""}
                onCommit={(to) => set({ ...(value || {}), to })}
                inputProps={{ type: "date" }}
              />
            </Stack>
          ) : null}
          <Button size="small" variant="text" onClick={() => { set(emptyValue(kind)); onClose(); }}>
            이 조건 지우기
          </Button>
        </Stack>
      </Box>
    </Popover>
  );
}

export function inferKind(column) {
  const declared = column && column.filter && column.filter.kind;
  if (declared) return declared;
  const type = column && column.type;
  if (type === "status" || type === "enum") return "enum";
  if (type === "name") return "entity";
  if (type === "number" || type === "count") return "number";
  if (type === "date" || type === "datetime") return "date";
  return "text";
}

function emptyValue(kind) {
  if (kind === "enum" || kind === "entity") return [];
  if (kind === "number") return { min: "", max: "" };
  if (kind === "date") return { from: "", to: "" };
  return "";
}
