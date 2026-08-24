import React from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Typography from "@mui/material/Typography";
import { FONT_SIZE, MOTION } from "./theme.js";

/* 값을 **그 자리에서** 바꾸는 공통 계약 (C8 · R-89 · W6).
 *
 * ## 왜 공통 계층인가
 *
 * 같은 값(티켓 상태·우선순위)을 Grid 셀에서도, 상세 머리에서도, 폼에서도 바꾼다. 세 자리가
 * 각자 구현하면 **세 개의 다른 상태 기계**가 생긴다 — 한 곳은 롤백이 있고 한 곳은 없고,
 * 한 곳은 두 번 눌러도 두 번 저장되고, 한 곳은 권한 없는 사람에게 눌리는 컨트롤을 보인다.
 * 그래서 상태 기계를 여기 하나로 두고, 화면은 «무엇을 바꾸나» 만 넘긴다.
 *
 * **배선은 이 회차의 몫이 아니다** — W6 은 계약을 만들고 티켓 Grid·상세 머리 배선은 티켓
 * 도메인 회차가 한다. 계약만 있고 소비처가 없는 코드가 되지 않게, 상태 여섯을 전부 렌더
 * 시험이 고정한다(`inline-edit.test.jsx`).
 *
 * ## 상태 여섯
 *
 *   `read`    현재 값. **평상시엔 값 그대로 읽힌다** — 모든 편집 가능한 값을 select 로
 *             노출하면 표가 컨트롤 밭이 되어 훑을 수가 없다(C8). 바꿀 수 있다는 것은
 *             hover/focus 에서 드러난다.
 *   `locked`  권한이 없다. **편집 진입 자체가 없다** — 눌러 보고 403 을 받는 경로를 만들지
 *             않는다. 이유를 알아야 하는 경우에만 이유를 보인다.
 *   `open`    바꿀 수 있는 값을 제시한다.
 *   `saving`  저장 중. **이 동안의 선택은 무시한다** — 같은 저장을 두 번 보내지 않는다.
 *   `done`    성공. 화면 값은 **서버가 돌려준 값**이다(아래 §정직한 성공).
 *   `error`   실패. 값은 **이전 값으로 되돌아가고** 사유가 붙는다.
 *
 * ## 정직한 성공
 *
 * 프런트 상태만 바꾸고 성공으로 치지 않는다. `onSave(next)` 는 Promise 를 돌려주고, 그
 * **돌아온 값**이 화면의 새 값이 된다. 서버가 파생값을 함께 바꾸는 경우(상태를 완료로
 * 옮기면 진행률이 바뀐다) 화면은 서버가 말한 값을 그린다 — 넘겨준 값이 아니라.
 * 아무 것도 안 돌려주면 넘긴 값을 쓴다(값이 그대로인 단순 저장).
 */

export const INLINE_EDIT_STATES = ["read", "locked", "open", "saving", "done", "error"];

/* 상태 전이 — **순수 함수**다. 렌더 없이 시험할 수 있어야 아홉 가지 경로를 전부 고정할 수
 * 있고, 화면이 늘어도 이 표 하나만 본다. */
export function inlineEditNext(state, event) {
  switch (event) {
    case "open":
      // 권한이 없으면 열 수 없다. 「막힌 것을 눌러 보게 하지 않는다」가 이 줄이다.
      return state === "locked" ? "locked" : (state === "saving" ? "saving" : "open");
    case "cancel":
      return state === "saving" ? "saving" : "read";
    case "select":
      // 저장 중의 선택은 **버린다**. 상태로만 보면 두 갈래가 같은 값이라 구별이 안 되므로,
      // 「이 선택이 실제로 저장을 띄우는가」는 아래 `canStartSave` 가 따로 답한다.
      return "saving";
    case "ok":
      return state === "saving" ? "done" : state;
    case "fail":
      return state === "saving" ? "error" : state;
    case "settle":
      return state === "done" || state === "error" ? "read" : state;
    default:
      return state;
  }
}

/** 이 상태에서 고른 값이 **실제로 저장을 띄우는가**. 중복 요청 방지의 정본이다.
 *
 * 상태 전이만으로는 이것을 표현할 수 없다 — 저장 중에 또 고르면 상태는 `saving` 그대로라
 * 「막았다」와 「한 번 더 보냈다」가 같은 모양이 된다. 그 둘을 가르는 술어를 따로 둔다. */
export function canStartSave(state) {
  return state !== "saving";
}

/**
 * 값 하나를 그 자리에서 바꾼다.
 *
 * props
 *   `value`     지금 값(문자열). 화면에 그대로 읽힌다.
 *   `render`    값을 그리는 함수. 안 주면 값 그대로 — 배지로 그리고 싶으면 여기서 그린다.
 *   `options`   `[{ value, label }]` — 바꿀 수 있는 값. 비면 열리지 않는다.
 *   `canEdit`   서버가 준 권한. **프런트가 스스로 추측하지 않는다** (C8: 프런트의 변경
 *               가능 여부와 백엔드 Authorization 이 일치해야 한다).
 *   `deniedReason` 권한이 없는 이유. 주면 `title` 로 붙고, 안 주면 아무 말도 안 한다 —
 *               알아야 할 이유가 없는데 「권한 없음」을 늘어놓지 않는다.
 *   `label`     무엇을 바꾸는가(접근 이름에 쓴다). 예: "상태"
 *   `rowName`   어느 행의 값인가. 스무 행이 전부 "상태 바꾸기" 로 읽히지 않게 한다.
 *   `onSave(next)` 저장. Promise 를 돌려준다. 돌아온 값이 새 값이 된다(§정직한 성공).
 */
export function InlineEdit({ value, render, options, canEdit, deniedReason, label, rowName, onSave }) {
  const [state, setState] = React.useState(canEdit ? "read" : "locked");
  const [shown, setShown] = React.useState(value);
  const [reason, setReason] = React.useState("");
  const [anchor, setAnchor] = React.useState(null);
  // 저장 중인지를 **ref 로도** 든다. 상태 갱신은 비동기라, 빠르게 두 번 고르면 두 번째가
  // 아직 `read` 인 state 를 보고 통과한다 — 그 경로가 곧 중복 저장이다.
  const busy = React.useRef(false);

  // 바깥에서 값이 바뀌면(목록 재조회 등) 그 값이 정본이다.
  React.useEffect(() => { setShown(value); }, [value]);
  React.useEffect(() => { setState((s) => (canEdit ? (s === "locked" ? "read" : s) : "locked")); }, [canEdit]);

  const list = Array.isArray(options) ? options.filter(Boolean) : [];
  const openable = canEdit && list.length > 0;

  const open = (e) => {
    if (!openable || busy.current) return;
    setAnchor(e.currentTarget);
    setState((s) => inlineEditNext(s, "open"));
  };
  const close = () => {
    setAnchor(null);
    setState((s) => inlineEditNext(s, "cancel"));
  };

  const choose = async (next) => {
    if (busy.current) return;                       // 중복 요청 차단
    busy.current = true;
    const before = shown;
    setAnchor(null);
    setState("saving");
    setReason("");
    try {
      const got = await onSave(next);
      // 서버가 돌려준 값이 정본이다. 안 돌려주면 넘긴 값을 쓴다.
      setShown(got == null || got === "" ? next : got);
      setState("done");
    } catch (err) {
      setShown(before);                             // 롤백 — 이전 값으로 안전 복구
      setReason((err && (err.userMessage || err.message)) || "저장하지 못했습니다.");
      setState("error");
    } finally {
      busy.current = false;
    }
  };

  const name = (rowName ? rowName + " " : "") + (label || "값");
  const body = render ? render(shown) : (shown == null || shown === "" ? "-" : shown);

  if (!canEdit) {
    return (
      <Box component="span" data-inline-edit="locked" title={deniedReason || undefined}>
        {body}
      </Box>
    );
  }

  return (
    <>
      <Box
        component="button"
        type="button"
        data-inline-edit={state}
        aria-haspopup="listbox"
        aria-expanded={state === "open"}
        aria-label={name + " 바꾸기"}
        aria-busy={state === "saving" ? "true" : undefined}
        disabled={!openable || state === "saving"}
        onClick={open}
        sx={(t) => ({
          font: "inherit", color: "inherit", p: 0.25, mx: -0.25, borderRadius: 1,
          border: 0, background: "none", display: "inline-flex", alignItems: "center", gap: 0.5,
          cursor: openable ? "pointer" : "default", minWidth: 0, maxWidth: "100%",
          transition: `background-color ${MOTION.instant} ${MOTION.ease}`,
          /* 평상시엔 값 그대로다. **가리키거나 포커스가 왔을 때만** 바꿀 수 있다는 것이
             드러난다 — 그래야 표가 컨트롤 밭이 되지 않는다(C8). */
          "&:hover": openable ? { bgcolor: t.palette.background.inset } : undefined,
          "&:focus-visible": { outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 },
        })}
      >
        {body}
        {state === "saving" ? <CircularProgress size={12} aria-hidden="true" /> : null}
      </Box>
      {state === "error" && reason ? (
        /* 실패는 값 **옆에** 말한다. 토스트로만 말하면 어느 행이 실패했는지 사라진다. */
        <Typography component="span" role="status" sx={{ ml: 0.75, fontSize: FONT_SIZE.caption, color: "error.strong" }}>
          {reason}
        </Typography>
      ) : null}
      <Menu open={state === "open"} anchorEl={anchor} onClose={close}
            slotProps={{ list: { role: "listbox", "aria-label": name } }}>
        {list.map((o) => (
          <MenuItem key={o.value} role="option" aria-selected={o.value === shown}
                    selected={o.value === shown} onClick={() => choose(o.value)}>
            {o.label == null ? o.value : o.label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
