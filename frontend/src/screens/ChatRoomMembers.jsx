import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Popover from "@mui/material/Popover";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { api } from "../lib/api.js";
import { failureText } from "../lib/failure.js";
import { Badge, Button, Callout, EmptyState, ErrorState, FieldLabel, Modal, Skeleton, StatusDot, useConfirm, useToast } from "../ui/kit.jsx";
import { PeopleFilter, PersonPickRow, filterPeople } from "./chat/peoplePicker.jsx";
import { FONT_SIZE, FONT_WEIGHT, NUMERIC, RADIUS } from "../ui/theme.js";
import { CHAT } from "../ui/chat.js";
import { affiliation, hasDuplicateNames, needsOrg, personLabel } from "../lib/people.js";
import { PersonWithOrg, pathText } from "../ui/OrgPath.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";

/* 채팅방 참여자 — 방 머리의 요약 · 얼굴 스택, 누구나 여는 참여자 명단(팝오버), 방장만 여는 관리 대화상자.
 *
 * **명단은 방에 들어온 사람 누구나 본다** (사용자 지시 2026-09-21). 예전에는 전체 명단이 방장 전용 「관리」 창에만
 * 있어서 일반 참여자 · 1:1 · 내 팀 방에서는 누가 들어와 있는지 볼 길이 없었다. 명단이 쓰는 값(부서 · 직급 · 접속 상태 ·
 * 부서 경로 · 사진)은 방 메시지 응답이 이미 준다. 새 조회를 만들지 않고, 볼 수 있는 범위도 그 응답을 받을 권한과
 * 같다(서버의 `ensure_access`). 전체 채팅은 참여자 행이 없어서 명단도 없다 — 없는 명단을 지어내지 않는다.
 *
 * ChatRoom.jsx 에서 떼어낸 이유: 방 페이지는 헤더 + 대화창이 본체이고, 관리 화면은 가끔
 * 열리는 대화상자다. 한 파일에 두면 대화창을 한 줄 고칠 때마다 관리 폼 전체가 함께 움직인다.
 *
 * **접속 점의 뜻**: 서버가 준 `online` 은 '이 방을 열어 두고 있다'이지 '앱에 로그인해 있다'가
 * 아니다(app/team_chat/service.py). 그래서 라벨도 '접속 중'이 아니라 '이 대화 보는 중'이다 —
 * 점 하나가 실제보다 많은 것을 주장하면 사람들은 답이 없을 때 상대를 오해한다.
 * 색만으로 상태를 전하지 않는다: 점 옆에 글자가 같이 나간다(WCAG 1.4.1).
 *
 * **'자리 비움'이 이제 진짜로 자리 비움이다** (X12). 예전에는 탭만 열어 두면 폴링이 계속
 * 돌아 퇴근한 사람도 밤새 켜져 있었다 — 그래서 이 두 라벨이 사실상 '탭을 닫았는가'만
 * 구분했다. 이제 브라우저가 사람의 입력이 끊긴 것을 보고 폴링에 `idle` 을 붙이고, 서버는
 * 그 폴링을 접속으로 세지 않는다. 판정 규칙과 그 이유는 `frontend/src/lib/idle.js` 에 있다.
 *
 * **권한은 서버가 준 `can_manage` 하나만 본다.** 여기서 '그룹인가? 방장인가? 전체인가?'를
 * 다시 계산하면 서버 규칙과 어긋나는 순간 '보이는데 누르면 403'이 된다.
 *
 * **참여자 줄도 제품 전체와 같은 얼굴을 쓴다.** 예전에는 이름 옆에 접속 점만 있고 사진이
 * 없었다 — 말풍선(ChatPane.jsx)은 같은 사람을 `UserAvatar` 로 그리는데 참여자 목록만
 * 다르면, 같은 방에서 위(대화)와 아래(참여자)가 다른 사람처럼 보인다. 새로 조회를 만들지
 * 않는다: 방 메시지 응답(`GET .../messages`)이 이미 `people`(전체 신원 맵, avatar_url
 * 포함)을 함께 주므로 `ChatRoom.jsx` 가 그걸 그대로 내려 준다.
 */

/* 접속 상태 셋 — 줄 끝 글자 · 접속 점 색 · 얼굴 이름표 · 명단 순서가 모두 이 표 하나를 읽는다.
 *
 * 서버의 `presence` 는 `online` 을 세 갈래로 나눈 값이다(`app/team_chat/service.py::presence_for`). 방해금지를 켠 사람은
 * **보고 있지만 지금은 곤란한** 사람이라 꺼진 점으로 그리지 않는다(그건 거짓말이다). 이 방을 보고 있지 않은 사람에게는
 * 서버가 방해금지를 붙이지 않는다. `presence` 가 없는 옛 응답에서는 `online` 두 갈래로 선다. */
const PRESENCE = {
  online: { rank: 0, text: "이 대화 보는 중", accent: "success.main" },
  dnd: { rank: 1, text: "방해금지", accent: "warning.main" },
  away: { rank: 2, text: "자리 비움", accent: "action.disabled" },
};

function presenceOf(person) {
  if (!person || !person.online) return PRESENCE.away;
  return person.presence === "dnd" ? PRESENCE.dnd : PRESENCE.online;
}

/* 참여자 한 명 = 신원(`people` — 사진 · 부서 경로)에 참여 사실(`members` — 이름 · 역할 · 접속)을 얹은 것이다. 두 값은 같은
 * 응답에서 온다. 얼굴 스택 · 명단 · 관리 창이 모두 이 합성을 써야 같은 사람이 세 자리에서 같은 얼굴과 같은 소속으로 선다. */
function personOf(member, people) {
  return { ...(people && people[member.user_id]), ...member };
}

/* 명단 순서 — 보는 중 → 방해금지 → 자리 비움이고, 같은 상태 안에서는 이름순이다. 지금 궁금한 것은 누가 이 대화를 보고
 * 있는가다. 얼굴 스택도 같은 순서라 스택의 얼굴 여덟이 명단의 첫 여덟 줄이다. */
function rosterOrder(rows) {
  const nameOf = (p) => p.display_name || p.name || "";
  return [...rows].sort((a, b) => (presenceOf(a).rank - presenceOf(b).rank) || nameOf(a).localeCompare(nameOf(b), "ko"));
}

/** 참여자 한 줄 — 제품 전체에서 **한 벌**이다. 명단 팝오버(동작 칸 없음)와 「관리」 창(동작 칸 있음)이 같이 쓴다.
 *
 * 접속 점 + 사진 + 이름(「(나)」 · 보관됨 · 직급)과 둘째 줄 부서 경로(`PersonWithOrg`) + 방장 배지 + 접속 상태 글자 + 동작 칸.
 * `person` 은 `personOf` 가 합친 값이다. 가리키면 떠오르는 것은 동작 칸을 받는 줄(「관리」 창)뿐이다 — 누를 것이 없는 줄이
 * 떠오르면 누를 수 있는 줄로 읽힌다. */
export function MemberRow({ person, meId, withOrg = false, actions }) {
  const presence = presenceOf(person);
  const me = person.user_id === meId;
  return (
    <Box
      role="listitem"
      data-member-row=""
      sx={{
        display: "flex", alignItems: "center", gap: 1, minWidth: 0,
        px: 1, py: 0.75, borderRadius: `${RADIUS.sm}px`,
        ...(actions !== undefined ? { "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) } } : null),
      }}
    >
      {/* 접속 점은 제품 공통 점이다(`StatusDot`) — 이 화면만 지역 점(8px)을 따로 그렸다. 색만으로 전하지 않는다: 줄 끝 글자가 같은 사실을 말한다. */}
      <StatusDot accent={presence.accent} />
      <UserAvatar person={person} name={person.display_name || person.name} size="sm" />
      {/* 이름 옆에 직급, 아래에 부서 경로가 선다. 방을 만들 때 쓰는 디렉터리는 부서를 보여 주는데 정작 **만들어진 방의
          참여자 목록은 이름만** 보여 줘서, 같은 이름 두 사람을 초대하면 누가 누구인지 구분할 수 없었다(사용자 지시
          2026-08-04). 떠난 사람에게는 보관됨이 붙는다 — 안 하면 답이 안 오는 대화를 며칠 기다린다(N3). 같은 방의
          말풍선(ChatPane.jsx)이 이미 같은 표시를 하므로, 줄만 빠지면 같은 사람이 위아래에서 다른 말을 하게 된다. */}
      <PersonWithOrg person={person} bold={me} suffix={me ? "(나)" : ""} withOrg={withOrg} />
      {person.role === "owner" ? (
        <Badge value="방장" kind="info" />
      ) : null}
      <Typography sx={{ flexShrink: 0, ml: "auto", fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
        {presence.text}
      </Typography>
      {actions}
    </Box>
  );
}

/* 방 머리의 참여자 요약 — 몇 명이 지금 이 대화를 보고 있는지 + 얼굴 스택. 전체 채팅은 참여자 개념이 없다.
 *
 * 얼굴은 최대 STRIP_NAMES 개만 겹쳐 세운다(26 · −8 겹침, 핸드오프 RULES §9 · `ui/chat.js::CHAT`). 정원이 50명이라
 * 전부 늘어놓으면 머리가 여러 줄이 되어 대화창을 밀어낸다 — 숫자(참여자 N명)가 이미 전체를 말하고, 남은 수는 「+N」,
 * 전체 명단은 요약 단추와 얼굴 스택이 여는 명단 팝오버(`MemberRoster`)에 있다. 순서는 명단과 같다(`rosterOrder` — 보는 중이
 * 먼저다). 얼굴마다 이름과 접속 상태(「이 대화 보는 중」 · 「방해금지」 · 「자리 비움」 — 명단 줄과 같은 말)를 이름표로 든다 —
 * 예전 한 줄 요약의 이름 · 접속 점이 들던 사실을 얼굴이 이어 받는다.
 */
const STRIP_NAMES = 8;

/** 명단 팝오버의 열림 상태 — 요약 단추와 얼굴 스택 두 자리가 **같은** 팝오버를 연다.
 *
 * 팝오버는 누른 자리에 붙어 열리고, 닫히면 초점은 언제나 요약 단추로 돌아간다. MUI 는 열기 직전에 초점이 있던 곳으로
 * 초점을 돌려준다. 얼굴 스택은 초점을 받지 않는 자리라 그대로 두면 초점이 문서 몸통으로 떨어지므로, 열기 전에 초점을 요약
 * 단추로 먼저 옮긴다. 요약 단추를 눌렀을 때도 같은 일을 한다 — 사파리는 단추를 눌러도 초점을 주지 않는다.
 * 닫을 때 앵커는 그대로 둔다. 앵커를 비우면 닫히며 사라지는 동안 팝오버가 화면 왼쪽 위로 튄다. */
export function useMemberRoster() {
  const summaryRef = React.useRef(null);
  const popoverId = React.useId();
  const [state, setState] = React.useState({ open: false, anchor: null });
  const openFrom = React.useCallback((event) => {
    const anchor = event.currentTarget;
    if (summaryRef.current) summaryRef.current.focus({ preventScroll: true });
    setState({ open: true, anchor });
  }, []);
  const close = React.useCallback(() => setState((s) => ({ ...s, open: false })), []);
  return { summaryRef, popoverId, open: state.open, anchor: state.anchor, openFrom, close };
}

/** 방 머리 둘째 줄 — 「참여자 N명, 보는 중 M명」(0.75rem muted). 얼굴 스택과 **따로** 선다(방 머리 두 줄, UI 3차 조합 계약 C-6 ·
 * 채팅방 시안). 예전에는 글자와 얼굴이 한 묶음(`MemberStrip`)이라 제목 줄 오른쪽에 한 줄로 서서 제목 · 배지 · 요약 · 얼굴 · 단추
 * 다섯이 한 줄을 다퉜다.
 *
 * **이 글자가 명단을 여는 단추다.** 보이는 글자가 그대로 단추 이름이고(`aria-haspopup="dialog"` · `aria-expanded`), 모양은 요약
 * 글자 그대로 둔다. 가리키면 글자가 짙어지고 밑줄이 선다. 얼굴 스택을 눌러도 같은 팝오버가 열리지만 단추는 이것 하나다 —
 * 단추가 둘이면 같은 말을 두 번 읽는다. `roster` 는 `useMemberRoster()` 의 값이다. */
export function MemberSummary({ members, roster }) {
  const rows = members || [];
  if (!rows.length) return null;
  const online = rows.filter((m) => m.online).length;
  return (
    <Typography
      component="button"
      type="button"
      ref={roster.summaryRef}
      data-member-summary=""
      aria-haspopup="dialog"
      aria-expanded={roster.open ? "true" : "false"}
      aria-controls={roster.open ? roster.popoverId : undefined}
      onClick={roster.openFrom}
      sx={{
        justifySelf: "start", maxWidth: "100%", minWidth: 0, m: 0, p: 0, border: 0, bgcolor: "transparent",
        textAlign: "start", cursor: "pointer", borderRadius: `${RADIUS.xs}px`,
        fontSize: FONT_SIZE.micro, color: "text.secondary", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        "&:hover": { color: "text.primary", textDecoration: "underline", textUnderlineOffset: "0.15em" },
      }}
    >
      참여자 {rows.length}명, 보는 중 {online}명
    </Typography>
  );
}

/** 방 머리 오른쪽 얼굴 스택 — 동작 단추 앞에 선다. 눌러도 요약 단추와 같은 명단 팝오버가 열린다.
 *
 * 누르는 자리일 뿐 단추는 아니다. `role="list"` 와 얼굴별 이름표를 그대로 지키고 탭 순서에도 서지 않는다 — 목록을 단추 안에
 * 넣으면 목록 뜻이 사라진다. 키보드와 스크린리더는 요약 단추 하나로 같은 팝오버를 연다. */
export function MemberFaces({ members, people, roster }) {
  const rows = (members || []).map((m) => personOf(m, people));
  const dupNames = hasDuplicateNames(rows);
  if (!rows.length) return null;
  const ordered = rosterOrder(rows);
  const shown = ordered.slice(0, STRIP_NAMES);
  const rest = rows.length - shown.length;
  /* 얼굴 둘레의 판 색 선 — 겹친 얼굴끼리의 경계를 가른다(시안의 흰 테두리 2px). 판 면 토큰이라 다크에서도 판 색이다. */
  const ring = (t) => `0 0 0 2px ${t.palette.background.plate}`;
  return (
    <Box data-member-faces="" onClick={roster.openFrom} sx={{ display: "flex", alignItems: "center", minWidth: 0, cursor: "pointer" }}>
      <Box role="list" aria-label="참여자" sx={{ display: "flex", alignItems: "center", pl: 0.25 }}>
        {shown.map((m, i) => {
          /* 이름표는 **이름이 겹칠 때만** 소속을 붙인다 — 그때가 이름만으로 못 고르는 유일한 경우다. */
          const name = dupNames && affiliation(m) ? personLabel(m) : (m.name || "알 수 없음");
          const label = `${name}, ${presenceOf(m).text}`;
          return (
            <Box
              key={m.user_id} role="listitem" aria-label={label} title={label}
              sx={{ display: "inline-flex", borderRadius: `${RADIUS.full}px`, boxShadow: ring, ...(i ? { ml: CHAT.stackOverlap } : null) }}
            >
              <UserAvatar person={m} name={m.name} size={CHAT.stackAvatar} label={label} />
            </Box>
          );
        })}
        {rest > 0 ? (
          <Box
            role="listitem" aria-label={`외 ${rest}명`}
            sx={{
              ml: CHAT.stackOverlap, height: CHAT.stackAvatar, minWidth: CHAT.stackAvatar, px: 0.75,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              borderRadius: `${RADIUS.full}px`, bgcolor: "background.inset", boxShadow: ring,
              fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold, color: "text.secondary", ...NUMERIC,
            }}
          >
            +{rest}
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}

/** 참여자 명단 — 대화를 떠나지 않고 훑어보는 팝오버다. 관리(이름 · 초대 · 내보내기 · 방장 넘기기)는 계속 방장의 「관리」 창이 맡는다.
 *
 * 그릇은 알림 팝오버와 같은 조합이다(`app/NotificationBell.jsx`). 판 자체가 `role="dialog"` 이고 이름은 「참여자 N명」이며,
 * 폭은 `min(22rem, 화면 - 2rem)`, 높이는 `min(30rem, 70vh)` 안에서 목록만 스크롤한다. Esc · 바깥 클릭으로 닫히고 초점은 요약
 * 단추로 돌아간다(`useMemberRoster`). `aria-modal` 은 켜지 않는다 — 알림 팝오버에 적힌 것과 같은 이유다.
 *
 * 여덟 명을 넘으면 목록 위에 좁히기 칸이 선다(`PeopleFilter` — 이름 · 부서 · 직급을 검색 접기로 대조한다). 그룹 방 정원은
 * 50명이고 내 팀 방은 상한이 없지만, 줄이 가벼워 가상화하지 않고 찾는 일은 좁히기에 맡긴다. 목록은 초점을 받는다
 * (`tabIndex=0`). 줄에는 누를 것이 없어서, 그러지 않으면 키보드로는 넘친 줄까지 스크롤할 수 없다.
 *
 * 닫히면 안쪽이 통째로 걷혀 좁히기 조건도 함께 사라진다 — 다시 열면 전체 명단부터 보인다. */
export function MemberRoster({ roster, members, people, meId }) {
  const rows = members || [];
  return (
    <Popover
      open={roster.open && rows.length > 0}
      anchorEl={roster.anchor}
      onClose={roster.close}
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{
        paper: {
          id: roster.popoverId, role: "dialog", "aria-label": `참여자 ${rows.length}명`, "data-member-roster": "",
          sx: {
            mt: 0.5, width: "min(22rem, calc(100vw - 2rem))", maxHeight: "min(30rem, 70vh)",
            display: "flex", flexDirection: "column", overflow: "hidden",
          },
        },
      }}
    >
      <RosterBody members={rows} people={people} meId={meId} />
    </Popover>
  );
}

/* 좁히기는 줄에 **보이는 글자**로 찾는다. 명단 줄의 둘째 줄은 부서 한 칸이 아니라 부서 경로라서, 대조(`filterPeople`)에
 * 넘기는 `dept` 를 경로 전체 글자로 바꿔 넘긴다 — 줄에 「플랫폼개발팀 › QA파트」가 보이는데 「플랫폼개발」이 안 걸리면 칸이
 * 고장 난 것으로 읽힌다. 경로 칸 사이의 「›」는 접어도 남아서, 칸 둘을 이어 붙인 글자(「개발팀QA」)는 걸리지 않는다. 조직은
 * 줄에 보일 때만 넣는다. 대조 규칙 자체는 한 벌 그대로다. */
function searchablePath(person, withOrg) {
  const path = [...(withOrg && person.org ? [{ name: person.org }] : []), ...(person.dept_path || [])];
  return pathText(path) || person.dept || "";
}

function RosterBody({ members, people, meId }) {
  const rows = React.useMemo(() => rosterOrder(members.map((m) => personOf(m, people))), [members, people]);
  const withOrg = needsOrg(rows);
  const [q, setQ] = React.useState("");
  const filterable = rows.length > STRIP_NAMES;
  const shown = React.useMemo(() => {
    if (!filterable) return rows;
    const hit = new Set(filterPeople(rows.map((p) => ({ ...p, dept: searchablePath(p, withOrg) })), q).map((p) => p.user_id));
    return rows.filter((p) => hit.has(p.user_id));
  }, [rows, q, filterable, withOrg]);
  return (
    <>
      <Box sx={{ flexShrink: 0, px: 2, py: 1.25, borderBottom: 1, borderColor: "divider" }}>
        <Typography component="span" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body }}>
          참여자 {rows.length}명
        </Typography>
      </Box>
      {filterable ? (
        <Box sx={{ flexShrink: 0, px: 1.5, pt: 1.25 }}>
          <PeopleFilter value={q} onChange={setQ} count={shown.length} total={rows.length} placeholder="이름, 부서로 좁히기" />
        </Box>
      ) : null}
      {shown.length ? (
        <Box
          role="list" aria-label="참여자 명단" tabIndex={0}
          sx={{ flex: "1 1 auto", minHeight: 0, overflowY: "auto", p: 0.5, "&:focus-visible": { outlineOffset: "-2px" } }}
        >
          {shown.map((p) => <MemberRow key={p.user_id} person={p} meId={meId} withOrg={withOrg} />)}
        </Box>
      ) : (
        /* 「참여자가 없다」가 아니라 「조건 때문에 0명」이다(C1) — 관리 창의 초대 후보와 같은 말을 쓴다. */
        <Box sx={{ px: 0.5, pb: 0.5 }}>
          <EmptyState size="compact" title="조건에 맞는 사람이 없습니다" help="이름이나 부서 일부로 다시 찾아보세요." />
        </Box>
      )}
    </>
  );
}

/* `INPUT_SX` 는 지웠다 (W5 · F-W5D-143).
 *
 * 그 안의 `"&:focus": { outline: "none" }` 이 전역 `:focus-visible` 링을 이겼다 — emotion 이
 * 만드는 `.css-x:focus` 는 특이도가 (0,2,0) 이고 시트에서 더 뒤라, **키보드로 이 칸에 오면
 * 아무 표시도 없었다.** 입력은 이제 MUI `TextField` 를 쓴다: 높이·모서리·포커스 링이 전부
 * `theme.js` 의 토큰에서 온다. 손으로 만든 입력은 만든 날에는 같아 보이고 토큰이 바뀌는 날
 * 갈라진다. */

/* 사람 고르기 — 검색이 먼저다. 부품은 `ChatRooms.jsx` 가 소유한다(같은 디렉터리를 고르는
   같은 문제라 두 벌로 두면 한쪽만 고쳐진다). */
const PICKER_SX = {
  display: "flex", flexDirection: "column", gap: 0.25, maxHeight: "14rem", overflowY: "auto",
  /* 모서리는 입력칸 토큰이다(6) — 예전 `borderRadius: 2` 는 테마 배율로 16px 이 되어 창 안에서만 둥글었다. */
  border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px`, p: 0.5,
};

export function ManageRoomModal({ open, onClose, roomId, title, members, meId, people }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [name, setName] = React.useState(title || "");
  const [picked, setPicked] = React.useState({});
  /* 열릴 때만 초기화한다(step 9 #6) — `title`을 의존성에 넣으면, 이미 열려 있는 채로
   * 이름을 저장했을 때(rename.onSuccess → refresh() → room 쿼리 재조회 → title prop 갱신)
   * 이 효과가 다시 돌아 방금 골라 둔 초대 대상(picked)까지 조용히 날아간다. 초대 성공
   * 경로는 이미 `setPicked({})`를 명시적으로 부르므로(위 invite.onSuccess), 여기서 title
   * 변화에 반응할 이유가 없다 - 모달이 열리는 순간의 값으로 한 번만 채우면 된다(그 시점에는
   * title 이 이미 최신값이다 - "관리" 버튼 자체가 room 데이터 로딩 후에만 보인다). */
  React.useEffect(() => {
    if (open) {
      setName(title || ""); setPicked({});
      // 다시 열 때 지난 실패를 걷는다 — 모달은 닫혀도 자리를 지키므로 요청 상태가 남는다.
      [rename, invite, remove, handOver].forEach((m) => m.reset());
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["team-chat-msgs", roomId] });
    qc.invalidateQueries({ queryKey: ["team-chat-rooms"] });
  };

  const dir = useQuery({
    queryKey: ["team-chat-directory"],
    queryFn: () => api("/api/team-chat/directory"),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const rename = useMutation({
    mutationFn: () => api(`/api/team-chat/rooms/${roomId}/rename`, { method: "POST", body: { title: name.trim() } }),
    onSuccess: () => { refresh(); toast("방 이름을 바꿨습니다.", "success"); },
  });
  const invite = useMutation({
    mutationFn: (ids) => api(`/api/team-chat/rooms/${roomId}/members/add`, { method: "POST", body: { user_ids: ids } }),
    onSuccess: (r) => {
      refresh();
      setPicked({});
      // 서버는 '실제로 새로 들어온 수'를 돌려준다 — 이미 있던 사람은 조용히 건너뛴다.
      toast(r && r.added ? `${r.added}명을 초대했습니다.` : "이미 모두 참여 중입니다.", "success");
    },
  });
  const remove = useMutation({
    mutationFn: (userId) => api(`/api/team-chat/rooms/${roomId}/members/remove`, { method: "POST", body: { user_id: userId } }),
    onSuccess: () => { refresh(); toast("참여자를 내보냈습니다.", "success"); },
  });
  const handOver = useMutation({
    mutationFn: (userId) => api(`/api/team-chat/rooms/${roomId}/owner`, { method: "POST", body: { user_id: userId } }),
    onSuccess: () => { refresh(); onClose(); toast("방장을 넘겼습니다. 이제 이 방을 관리할 수 없습니다.", "info"); },
  });
  /* 관리 동작(이름 · 초대 · 내보내기 · 방장 넘기기)의 실패는 이 모달 안에 남는다 — 가장 나중에 누른 동작
     하나만 말하고, 다음 동작을 누르면 걷힌다(`lib/failure.js`). */
  const manageFailure = failureText(
    [rename, "이름을 바꾸지 못했습니다. 다시 시도해 주세요."],
    [invite, "초대하지 못했습니다. 다시 시도해 주세요."],
    [remove, "내보내지 못했습니다. 다시 시도해 주세요."],
    [handOver, "방장을 넘기지 못했습니다. 다시 시도해 주세요."],
  );

  const rows = members || [];
  const withOrg = needsOrg(rows);
  const memberIds = new Set(rows.map((m) => m.user_id));
  const candidates = ((dir.data && dir.data.users) || []).filter((u) => !memberIds.has(u.user_id));
  /* 초대 후보를 **좁히는** 조건. 이미 받은 목록을 거르는 것이라 네트워크가 안 간다. */
  const [pickQ, setPickQ] = React.useState("");
  const shownCandidates = React.useMemo(() => filterPeople(candidates, pickQ), [candidates, pickQ]);
  const chosen = Object.keys(picked).filter((k) => picked[k]);
  const busy = rename.isPending || invite.isPending || remove.isPending || handOver.isPending;
  // 이름을 고쳐 썼거나(저장 안 함) 초대할 사람을 골랐으면(초대 안 보냄) Esc·바깥 클릭·X·'닫기'
  // 전부에서 확인을 받는다(VIS-88) — 이 두 초안은 각자 자기 버튼(저장/초대)을 눌러야만 반영되고,
  // `Modal`의 `dirty` prop은 Esc/바깥클릭/X만 지킨다 — 하단 '닫기' 버튼은 onClose를 직접 불러 그
  // 가드를 우회하므로(Games.jsx가 이미 겪은 문제) 여기서도 requestClose로 감싼다.
  const dirty = name.trim() !== (title || "").trim() || chosen.length > 0;
  async function requestClose() {
    if (!dirty) { onClose(); return; }
    const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?",
      { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
    if (ok) onClose();
  }

  const askRemove = async (m) => {
    const ok = await confirm(`${m.name || "이 참여자"}님을 내보냅니다. 이 방의 대화를 더는 볼 수 없게 됩니다.`,
      { title: "참여자 내보내기", confirmLabel: "내보내기", danger: true });
    if (ok) remove.mutate(m.user_id);
  };
  const askHandOver = async (m) => {
    const ok = await confirm(
      `${m.name || "이 참여자"}님에게 방장을 넘깁니다. 넘기면 나는 일반 참여자가 되고 이 방을 관리할 수 없습니다.`,
      { title: "방장 넘기기", confirmLabel: "넘기기", danger: true });
    if (ok) handOver.mutate(m.user_id);
  };

  return (
    <Modal open={open} onClose={onClose} title="채팅방 관리" size="md" dirty={dirty} footer={<Button onClick={requestClose}>닫기</Button>}>
      {manageFailure ? <Callout tone="danger" compact sx={{ mb: 2 }}>{manageFailure}</Callout> : null}
      {/* 이 창은 따로 확정하는 입력 영역 둘이다(`data-form-scope`) — 이름 「저장」과 「초대」는 각 영역의 채움이라 창 안 채움 둘이
          한 확정을 다투는 것이 아니다(조합 계약 C-4 · 댓글 쓰는 칸과 같은 규칙). 창 발은 닫기 하나다. */}
      <Box component="section" data-form-scope="" sx={{ mb: 3 }}>
        <FieldLabel htmlFor="tc-rename">방 이름</FieldLabel>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
          {/* maxLength는 서버(app/team_chat/schemas.py::MAX_TITLE)와 같은 값이어야 한다 — 여기가
              더 짧으면 서버는 받아 줄 이름을 화면이 미리 못 치게 막는 것이 된다. */}
          <TextField id="tc-rename" size="small" value={name}
            onChange={(e) => setName(e.target.value)}
            inputProps={{ maxLength: 200 }}
            sx={{ flex: 1, minWidth: "12rem" }} />
          <Button variant="primary" disabled={busy || !name.trim() || name.trim() === title}
            onClick={() => rename.mutate()}>저장</Button>
        </Box>
      </Box>

      <Box component="section" sx={{ mb: 3 }}>
        <Typography component="h3" sx={{ mb: 0.75, fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold }}>
          참여자 {rows.length}명
        </Typography>
        {/* 줄은 명단 팝오버와 같은 `MemberRow` 이고 동작 칸만 더 받는다. 순서는 서버가 준 그대로다 — 접속 상태로 다시
            세우면 폴링마다 줄이 움직여, 「내보내기」를 누르려던 순간 옆 사람의 줄이 손 밑으로 들어온다. */}
        <Box role="list" sx={PICKER_SX}>
          {rows.map((m) => (
            <MemberRow
              key={m.user_id} person={personOf(m, people)} meId={meId} withOrg={withOrg}
              actions={m.user_id === meId ? null : (
                <Box sx={{ display: "flex", gap: 0.5, flexShrink: 0 }}>
                  <Button size="sm" disabled={busy} onClick={() => askHandOver(m)}>방장 넘기기</Button>
                  <Button size="sm" variant="danger" disabled={busy} onClick={() => askRemove(m)}>내보내기</Button>
                </Box>
              )}
            />
          ))}
        </Box>
        {/* 방장이 스스로 빠지는 길은 '방장 넘기기'와 '나가기' 둘뿐이다 — 스스로 내보내기는
            서버가 409로 막는다(주인 없는 방이 생기기 때문). 그래서 내 줄에는 버튼이 없다. */}
        <Typography sx={{ mt: 0.75, fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
          방장은 스스로 내보낼 수 없습니다. 빠지려면 방장을 넘기거나 방을 나가세요(마지막 한 명이 나가면 방이 사라집니다).
        </Typography>
      </Box>

      <Box component="section" data-form-scope="">
        <Typography component="h3" sx={{ mb: 0.75, fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold }}>초대하기</Typography>
        {dir.isPending ? <Skeleton lines={3} />
          : dir.isError ? <ErrorState layout="region" error={dir.error} onRetry={() => dir.refetch()} />
          : candidates.length === 0 ? (
            <EmptyState size="compact" title="초대할 다른 사용자가 없습니다" />
          ) : (
            <>
              <PeopleFilter value={pickQ} onChange={setPickQ} count={shownCandidates.length} total={candidates.length} />
              {shownCandidates.length === 0 ? (
                /* 「초대할 사람이 없다」와 「조건 때문에 0명」은 다른 사실이다(C1). */
                <EmptyState size="compact" title="조건에 맞는 사람이 없습니다" help="이름이나 이메일 일부로 다시 찾아보세요." />
              ) : (
              <Box sx={PICKER_SX}>
                {shownCandidates.map((u) => (
                  <PersonPickRow
                    key={u.user_id} person={u} checked={!!picked[u.user_id]}
                    onToggle={(on) => setPicked((p) => ({ ...p, [u.user_id]: on }))}
                  />
                ))}
              </Box>
              )}
              <Box sx={{ mt: 1 }}>
                <Button variant="primary" disabled={busy || chosen.length === 0} onClick={() => invite.mutate(chosen)}>
                  {chosen.length > 0 ? `${chosen.length}명 초대` : "초대"}
                </Button>
              </Box>
            </>
          )}
      </Box>
    </Modal>
  );
}
