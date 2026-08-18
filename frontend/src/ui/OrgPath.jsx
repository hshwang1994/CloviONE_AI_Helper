import React from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { FONT_SIZE } from "./theme.js";

/* 조직 경로 한 줄 — **사람과 자원이 어디 소속인지**를 화면 어디서나 같은 모양으로 (0060 §5).
 *
 * ## 왜 컴포넌트로 두는가
 *
 * 소속 표기가 화면마다 제각각이면 사용자는 그것이 같은 뜻인지 매번 다시 읽어야 한다.
 * 그리고 더 실질적으로는, 경로 문자열을 화면마다 조립하다 보면 어딘가는 저장된 문자열을
 * 쓰게 되고 그 순간 조직 개편이 그 화면만 조용히 낡게 만든다.
 *
 * ## 경로는 **id 목록**으로 받는다
 *
 * `[{id, name}, ...]` (root → leaf). 서버가 지금 조직 트리에서 계산해 보낸 값이다.
 * 여기서는 그리기만 한다 — 이 값을 저장하거나 비교하거나 권한 판정에 쓰지 않는다.
 *
 * ## 두 가지 길이
 *
 *   variant="short"  마지막 두 칸만 (`A › A-1`) — 목록·표처럼 자리가 좁은 곳
 *   variant="full"   전체 (`굿모닝아이텍 › A › A-1`) — 상세·헤더
 *
 * 짧게 그릴 때도 **전체 경로는 tooltip 으로 닿을 수 있어야 한다.** 줄이는 것은 화면을
 * 깨끗하게 하려는 것이지 정보를 없애려는 것이 아니다.
 */

// 구분자. 가운뎃점(·)은 이 제품에서 화면에 쓰지 않기로 했다(app/core/people.py::affiliation).
export const PATH_SEP = " › ";

export function pathText(path) {
  return (path || []).map((n) => n.name).filter(Boolean).join(PATH_SEP);
}

/** 짧은 표기: 마지막 두 칸. 한 칸뿐이면 그 하나. */
export function shortPathText(path) {
  const names = (path || []).map((n) => n.name).filter(Boolean);
  return names.slice(-2).join(PATH_SEP);
}

export function OrgPath({ path, variant = "short", org, sx, component = "div" }) {
  const full = [org?.name, ...(path || []).map((n) => n.name)].filter(Boolean).join(PATH_SEP);
  const shown = variant === "full" ? full : shortPathText(path);
  if (!shown) return null;
  const body = (
    <Typography
      component={component}
      sx={{
        fontSize: FONT_SIZE.caption,
        color: "text.secondary",
        // 경로는 한 줄로 읽혀야 뜻이 있다 — 접히면 계층이 아니라 단어 나열로 보인다.
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        minWidth: 0,
        ...sx,
      }}
    >
      {shown}
    </Typography>
  );
  // 짧게 줄였을 때만 tooltip 을 단다. 전체를 이미 보여 주는데 같은 값을 또 띄우면 소음이다.
  return shown === full ? body : <Tooltip title={full}>{body}</Tooltip>;
}

/** 이름 + 조직 경로. 사람이 나오는 자리(선택기·목록·댓글)의 기본 표기.
 *
 *  동명이인은 이 제품에서 **스키마상 정상**이다(`users.display_name` 에 유일 제약이 없다).
 *  이름만 그리면 같은 줄이 두 번 뜨고 어느 쪽이 내가 찾는 사람인지 화면에 답이 없다. */
export function PersonWithOrg({ person, showTitle = true, sx }) {
  if (!person) return null;
  const name = person.display_name || person.name || "";
  const title = showTitle ? (person.title || "") : "";
  return (
    <Box sx={{ minWidth: 0, ...sx }}>
      <Typography variant="body2" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
        {name}
        {person.archived ? " (보관됨)" : ""}
        {title ? ` ${title}` : ""}
      </Typography>
      <OrgPath path={person.dept_path} org={person.org ? { name: person.org } : null} />
    </Box>
  );
}
