import React from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { ARCHIVED_SUFFIX } from "../lib/format.js";
import { FONT_SIZE, FONT_WEIGHT } from "./theme.js";

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
 * ## 세 가지 길이
 *
 *   variant="short"  마지막 두 칸만 (`A › A-1`) — 목록·표처럼 자리가 좁은 곳
 *   variant="full"   전체 (`굿모닝아이텍 › A › A-1`) — 상세·헤더
 *   variant="leaf"   조직 + 마지막 칸 (`굿모닝아이텍 › A-1`) — 조직까지 가려야 하는 좁은 목록. 조직이 둘 이상 섞인
 *                    채팅방 명단처럼 22rem 줄에서 전체 경로를 그리면 말줄임이 **가장 구체적인 끝 칸**을 먼저 자른다.
 *                    조직과 끝 칸이 사람을 가르는 두 글자라 둘만 남긴다(`lib/people.js::affiliation` 의 조직 + 부서와 같은 뜻).
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
  const leaf = (path || []).map((n) => n.name).filter(Boolean).slice(-1);
  const shown = variant === "full" ? full
    : variant === "leaf" ? [org?.name, ...leaf].filter(Boolean).join(PATH_SEP)
    : shortPathText(path);
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
 *  이름만 그리면 같은 줄이 두 번 뜨고 어느 쪽이 내가 찾는 사람인지 화면에 답이 없다.
 *
 *  첫 줄은 이름이고, 뒤에 붙는 표지(`suffix` — 「(나)」 같은 것) · 보관됨 · 직급은 muted 글자로 이름보다 한 단 물러선다.
 *  둘째 줄은 부서 경로다. 경로를 모르는 응답(`dept_path` 가 빈 옛 신원)에서는 부서 이름 한 칸으로 선다 — 부서가
 *  있는데 줄이 비면 동명이인을 가를 글자가 사라진다. 조직은 `withOrg` 일 때만 보인다(`lib/people.js::needsOrg` —
 *  조직이 하나뿐인 설치에서 모든 줄에 같은 조직명을 붙이면 줄만 길어진다). 그때 줄은 조직 + 끝 칸이다(`OrgPath`
 *  의 `leaf`). 조직 앞에 전체 경로를 다 세우면 좁은 줄에서 말줄임이 끝 칸부터 잘라 사람을 가르는 글자가 사라진다.
 *
 *  두 줄 다 한 줄에서 말줄임된다. 첫 줄의 전체 글자는 `title` 이 들고, 줄인 경로의 전체는 `OrgPath` 의 풍선이 든다.
 *  소비처: 채팅방 참여자 줄(`screens/ChatRoomMembers.jsx::MemberRow`). */
export function PersonWithOrg({ person, showTitle = true, withOrg = false, bold = false, suffix = "", sx }) {
  if (!person) return null;
  const name = person.display_name || person.name || "알 수 없음";
  const title = showTitle ? (person.title || "") : "";
  const extras = [suffix, person.archived ? ARCHIVED_SUFFIX : "", title].filter(Boolean);
  const deptPath = person.dept_path && person.dept_path.length
    ? person.dept_path
    : (person.dept ? [{ id: null, name: person.dept }] : []);
  const org = withOrg && person.org ? { name: person.org } : null;
  return (
    <Box sx={{ minWidth: 0, ...sx }}>
      <Typography variant="body2" noWrap title={[name, ...extras].join(" ")} sx={{ minWidth: 0 }}>
        <Box component="span" sx={bold ? { fontWeight: FONT_WEIGHT.bold } : undefined}>{name}</Box>
        {extras.map((text, i) => (
          <Box key={i} component="span" sx={{ color: "text.secondary" }}>{` ${text}`}</Box>
        ))}
      </Typography>
      <OrgPath path={deptPath} org={org} variant={org ? "leaf" : "short"} />
    </Box>
  );
}
