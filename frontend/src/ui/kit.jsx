import React from "react";
import MuiAlert from "@mui/material/Alert";
import MuiButton from "@mui/material/Button";
import MuiCard from "@mui/material/Card";
import MuiChip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import MuiDialog from "@mui/material/Dialog";
import MuiDialogActions from "@mui/material/DialogActions";
import MuiDialogContent from "@mui/material/DialogContent";
import MuiDialogTitle from "@mui/material/DialogTitle";
import MuiSkeleton from "@mui/material/Skeleton";
import MuiSnackbar from "@mui/material/Snackbar";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import useMediaQuery from "@mui/material/useMediaQuery";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import MoreHorizRoundedIcon from "@mui/icons-material/MoreHorizRounded";
import HelpOutlineRoundedIcon from "@mui/icons-material/HelpOutlineRounded";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import CheckCircleOutlineRoundedIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import ErrorOutlineRoundedIcon from "@mui/icons-material/ErrorOutlineRounded";
import Collapse from "@mui/material/Collapse";
import { keyframes } from "@mui/system";
import GlobalStyles from "@mui/material/GlobalStyles";
import { ART } from "../lib/assets.js";
import { MASCOT_PLACE, mascotBoxSx } from "./Mascot.jsx";
import { maxLengthFor } from "../lib/fieldLimits.js";
import { apiToKstLocal, kstLocalToApi, objectParticle, topicParticle } from "../lib/format.js";
import { declaredRowName, rowNameOf } from "./rowName.js";
import { ANYWHERE_BREAK, OVERFLOW, SHRINK, columnLayoutWidth, planColumnCollapse, resolveColumn, rootFontPx, tableMinWidth } from "./columnTypes.js";
import { planColumns } from "./columnPlan.js";
import { CONTROL, densityVars, EMPTY_STATE_MAX_CH, ERROR_STATE_MAX_CH, FONT_SIZE, FONT_WEIGHT, ICON, KO_WORD_BREAK, LINE_HEIGHT, MOTION, NUMERIC, RADIUS, SCROLL_BOX_STICKY_TOP, TABLE_CARD_QUERY, remPx, stickyTopSx } from "./theme.js";
import { WorkspaceModeContext } from "./workspaceMode.js";
import { CARD_PADDING, CARD_PADDING_COMPACT, SECTION_GAP, FORM_FIELD_CONTAINER, FORM_FIELD_GAP, FORM_FIELD_GRID_12, fieldSpan } from "./density.js";
import { FlowStack, HeadRow } from "./layout.jsx";
export { FLOW_GAP, FlowStack, HeadRow, centerPad } from "./layout.jsx";
import { EntityCombobox } from "./filters.jsx";
import { TableHeaderCell } from "./TableHeaderCell.jsx";
import { DateField } from "./DateField.jsx";
import { VirtualTableBody, WindowVirtualTableBody, useScrollMargin } from "./VirtualRows.jsx";
import { useListFooter } from "./listFooter.js";
import { SESSION_EXPIRED_ERROR, expireSession, isSessionExpired, loginUrl, subscribeSessionExpired } from "../lib/sessionRedirect.js";

/* ClovirONE 공통 UI 키트 — 카드/배지/버튼/상태/빈 화면/스켈레톤을 한 규칙으로 그린다.
 *
 * 2026-08 재설계: 안쪽 구현을 MUI로 바꾸되 **export 이름과 prop 시그니처는 그대로 둔다**.
 * 화면 21개가 전부 이 파일에서 컴포넌트를 가져다 쓰기 때문에, 여기만 바꾸면 화면 파일을
 * 한 줄도 건드리지 않고 보이는 표면의 대부분이 새 디자인으로 바뀐다. 기존 vitest도 역할/텍스트로
 * 조회하므로 그대로 통과한다.
 *
 * 표(DataTable)도 MUI로 옮겼다. 예전에는 화면별 열 너비를 screens.css가
 * `.docs-table .k-table th:nth-child(n)`으로 잡았는데, 열 순서가 바뀔 때마다 조용히 어긋났다
 * (체크박스 열이 생기면서 실제로 한 칸씩 밀려 제목 폭을 먹은 적이 있다). 이제 폭은 열 정의에
 * `width`로 함께 적는다 — 열을 옮기면 폭도 같이 따라간다.
 *
 * MUI import는 전부 별칭(MuiXxx)이다 — 이 파일이 같은 이름(Badge/Button/Card/Modal…)을
 * 밖으로 내보내기 때문에 충돌한다.
 */

// ── 상태 어휘 ────────────────────────────────────────────────────────────────
// 상태 원본값 → 한국어 표시 + 톤(색은 톤으로만). 바닐라 common.js와 같은 어휘.
const STATUS_TEXT = {
  up: "정상", down: "중단", stale: "응답 없음", degraded: "성능 저하", ok: "정상",
  active: "사용 중", enabled: "활성화", disabled: "비활성화", verified: "확인됨",
  unmapped: "미연결", unknown: "알 수 없음", processing: "처리 중", running: "실행 중",
  queued: "대기 중", succeeded: "완료", success: "성공", failed: "실패", failure: "실패",
  error: "오류", conflict: "충돌", pending: "대기", approved: "승인됨", rejected: "거절됨",
  expired: "만료", cancelled: "취소됨", published: "발행됨", draft: "초안", read: "읽기",
  write: "쓰기", maintenance: "점검", normal: "정상", awaiting_approval: "승인 대기",
  quality_failed: "품질 미달", passed: "통과", not_run: "미실행", untested: "미검증",
  // 문서 화면 상태 필터 라벨('미리보기 완료')과 같은 값이라 배지도 같은 말을 쓴다(어긋나면 필터 결과가 배지와 안 맞아 보인다).
  preview_ready: "미리보기 완료", skipped: "건너뜀",
  // 라이프사이클 중간 상태(프롬프트·정책·템플릿) — 한국어 표시가 없으면 원시 영어가 새어 나온다.
  test: "테스트", review: "검토", archived: "보관됨",
  // 워크플로 테스트 도달성 — reachable/unreachable가 매핑되지 않으면 영어 그대로 회색으로 뜬다.
  reachable: "연결됨", unreachable: "연결 안 됨",
  // secret_ref 상태(연동·러너 배지) — 매핑 없으면 영어 'configured'/'missing'이 회색으로 샌다.
  configured: "등록됨", missing: "없음",
  // Notion 티켓 워크플로 상태(채팅 결과 카드) — 관리자 상태 어휘엔 없어 영어/무채색으로 뜨던 값들.
  "Not started": "시작 전", "In progress": "진행 중", "Done": "완료", "Todo": "할 일",
  "시작 전": "시작 전", "진행 중": "진행 중", "할 일": "할 일",
  // 조직마다 Notion 보드에서 흔히 쓰는 그 밖의 상태값 — 위 4종만 있으면 실제 워크스페이스가
  // 쓰는 'In Review'/'Blocked' 등이 여전히 원시 영어로 새어 나온다.
  "In Review": "검토 중", "Blocked": "막힘", "Cancelled": "취소됨", "On Hold": "보류",
  "Backlog": "백로그", "검토 중": "검토 중", "막힘": "막힘", "백로그": "백로그",
  // 이 제품의 Workflow Status 여섯. **저장값과 표시값이 다른 것이 하나 있다** —
  // `진행` 은 화면에서 `진행 중` 이다(app/work/workflow.py::STATUSES 의 label).
  // 저장값을 옮기면 옛 링크·옛 필터·옛 감사 기록이 함께 갈리므로 표시만 바꾼다.
  "계획": "계획", "진행": "진행 중", "검증": "검증", "완료": "완료",
  "보류": "보류", "취소": "취소",
};
const STATUS_KIND = {
  up: "ok", verified: "ok", succeeded: "ok", success: "ok", published: "ok", active: "ok",
  enabled: "ok", approved: "ok", ok: "ok", normal: "ok", passed: "ok", reachable: "ok",
  "true": "ok",
  down: "danger", failed: "danger", failure: "danger", error: "danger", conflict: "danger", rejected: "danger",
  unreachable: "danger",
  degraded: "warn", stale: "warn", pending: "warn", queued: "warn", awaiting_approval: "warn",
  quality_failed: "warn", write: "warn", review: "warn", missing: "warn",
  // Notion 매핑 화면의 'unmapped'는 이 화면 존재 이유인 실행 가능한 상태다 — missing과 같은
  // 톤(주의/주황)으로 회색(중립, archived/disabled와 동급)과 구분한다(product-quality-audit AREA=D).
  unmapped: "warn",
  // 유지보수 모드('점검')는 사용자 쓰기를 막는 능동 상태다. STATUS_TEXT엔 있으나 톤이 없어
  // 회색(neutral)으로 떠, 정상(up=green)보다 덜 위험해 보이던 역전을 바로잡는다.
  maintenance: "warn",
  running: "info", processing: "info", read: "info", test: "info", preview_ready: "info",
  archived: "neutral", disabled: "neutral", "false": "neutral",
  // secret_ref: 등록됨=정상 / 없음=주의(위 missing:warn). 티켓 상태 톤.
  configured: "ok", "Done": "ok",
  "In progress": "info", "진행 중": "info",
  "Not started": "neutral", "시작 전": "neutral", "Todo": "neutral", "할 일": "neutral",
  "In Review": "info", "검토 중": "info", "Blocked": "danger", "막힘": "danger",
  "Cancelled": "neutral", "취소됨": "neutral", "On Hold": "warn",
  "Backlog": "neutral", "백로그": "neutral",
  // Workflow Status 여섯 — **서로 다른 색** (사용자 요청 · D-349 유지).
  // 빨강은 차단 신호 전용. 상태 여섯이 회색끼리 겹치면 표에서 구분이 안 된다.
  "계획": "indigo", "진행": "info", "검증": "warn", "완료": "ok",
  "보류": "purple", "취소": "teal",
};
export function statusText(v) {
  if (v === true) return "예"; if (v === false) return "아니오";
  // 빈 문자열도 null/undefined와 같이 취급한다 — 안 그러면 배지가 텍스트 없이(스크린리더도
  // 낭독할 게 없이) 빈 채로 그려진다(product-quality-audit AREA=D).
  const s = String(v == null || v === "" ? "unknown" : v);
  if (STATUS_TEXT[s]) return STATUS_TEXT[s];
  // 매핑에 없는 값(조직마다 다른 Notion 보드 커스텀 상태명 등) — 원시 snake_case/kebab-case를
  // 그대로 새어 나가게 두지 않고 사람이 읽는 형태로 다듬는다("in_review" → "In Review").
  if (/^[a-z0-9]+([_-][a-z0-9]+)+$/i.test(s)) {
    return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return s;
}
// 상태값 → 톤(ok/danger/warn/info/neutral). 배지 밖에서도 같은 색 언어를 쓰게 공유.
export function statusKind(v) {
  const raw = String(v == null ? "" : v);
  return STATUS_KIND[raw] || "neutral";
}

const TONE_SEVERITY = { danger: "error", warn: "warning", success: "success", info: "info" };
// MUI Chip color 팔레트 밖의 톤(문서 종류·게시판 분류 등) — tokens.css의 --badge-*-bg/fg 변수를
// 그대로 쓴다(다크모드 대응·대비 검증 이미 돼 있는 값). lib/badges.js가 이 네 톤을 배정하는데
// 예전엔 여기 목록이 없어 전부 회색 필 칩으로 뭉개졌다(DS-09).
export const EXTRA_TONE_VARS = {
  purple: { bg: "var(--badge-purple-bg)", fg: "var(--badge-purple-fg)" },
  teal: { bg: "var(--badge-teal-bg)", fg: "var(--badge-teal-fg)" },
  indigo: { bg: "var(--badge-indigo-bg)", fg: "var(--badge-indigo-fg)" },
  pink: { bg: "var(--badge-pink-bg)", fg: "var(--badge-pink-fg)" },
};

/* 배지가 **어디에 서 있는가** — 표와 목록 안인가, 그 밖인가 (확정 규약 §9).
 *
 * 규칙 자체는 오래 있었다: 「표 안에서는 배지 대신 점 + 낱말」. 그런데 그것을 지키는 일이
 * **호출부 106곳**의 기억에 맡겨져 있었고, 그래서 새지 않을 수가 없었다 — AI 도우미의
 * 「지연 N일」이 그렇게 샜고, 개발 리포트의 「지연」 열도 같은 자리였다. 규칙을 기억에서
 * 그릇으로 옮긴다: 표와 목록이 스스로 「여기는 면을 쓰지 않는 자리다」라고 말하고, 그 안의
 * 배지는 아무 prop 없이 그 말을 따른다.
 *
 * 호출부가 이길 수 있다 — 목록 안에서도 `emphasis="strong"` 을 적으면 면을 갖는다. 문맥이
 * 기본을 정하는 것이지 금지하는 것이 아니다. 반대로 목록 밖에서 면을 끄고 싶으면
 * `emphasis="plain"` 이다. */
const BadgeSurfaceCtx = React.createContext(null);

/** 이 안의 배지는 면을 갖지 않는다 — 표(`DataTable`)와 손으로 만든 목록이 감싼다. */
export function FlatBadgeSurface({ children }) {
  return <BadgeSurfaceCtx.Provider value="flat">{children}</BadgeSurfaceCtx.Provider>;
}

export function Badge({ value, kind, emphasis }) {
  /* 상태 표시 — **알약을 기본형으로 쓰지 않는다** (지시 11).
   *
   * 예전에는 `정상`·`활성`·`사용 중`·`미연결`·`아니요`·`전체 관리자`가 전부 같은 색 알약이었다.
   * 표 한 줄에 알약이 셋씩 들어가면서 "무엇이 상태이고 무엇이 분류인지" 구분이 사라졌고,
   * 목록 전체가 알약 죽이 됐다.
   *
   * 지금은 **표지(marker) + 글자**다. 배경 없음이 기본이고, 조치가 필요한 것(danger)만
   * 옅은 바탕을 갖는다 — 화면에서 눈에 띄어야 하는 것은 나머지가 조용할 때만 눈에 띈다.
   *
   * 색만으로 상태를 전달하지 않는다(WCAG 1.4.1): 라벨 글자가 항상 함께 있고
   * (`statusText` 가 ~80개 값을 한국어로 옮긴다), 표지는 색 + **모양**을 같이 쓴다.
   *
   * 분류(문서 종류·업무 분야)는 상태가 아니다 — `Tag` 를 쓴다.
   */
  const raw = String(value == null ? "" : value);
  const k = kind || STATUS_KIND[raw] || "neutral";
  const extra = EXTRA_TONE_VARS[k];
  const palette = { ok: "success", danger: "error", warn: "warning", info: "info" }[k];
  /* 면을 갖는가 — **호출부 → 자리 → 톤** 순서로 정해진다.
   *
   * ① 호출부가 `plain`/`strong` 을 적으면 그것이 이긴다.
   * ② 안 적었으면 **자리**가 정한다: 표·목록 안이면 면이 없다(위 `BadgeSurfaceCtx`).
   * ③ 그 밖에서는 danger 만 옅은 면을 갖는다 — 조치가 필요한 것이 눈에 띄어야 하는 자리다.
   *
   * 한 줄에서 어휘가 갈리면 읽는 사람은 그 둘이 다른 종류의 사실이라고 읽는다. AI 도우미의
   * 「지연 18일」만 붉은 면이고 바로 옆 「검증」·「계획」은 점 + 낱말이던 것이 그 예다. */
  const flat = React.useContext(BadgeSurfaceCtx) === "flat";
  const strong = emphasis === "plain" ? false
    : emphasis === "strong" ? true
      : (k === "danger" && !flat);

  /* 표지 모양이 톤마다 다르다 — 흑백으로 인쇄하거나 색을 못 봐도 구분된다. */
  const marker = { ok: "50%", danger: "2px", warn: "2px", info: "50%" }[k] || "1px";

  return (
    <Box
      component="span"
      className="k-badge"
      data-tone={k}
      sx={{
        display: "inline-flex", alignItems: "center", gap: 0.625,
        /* **알약은 자기 라벨보다 작아지지 않는다** (A3 재검수). 감싸는 사슬(InlineEdit 의
           버튼 등)이 `flex` 컨테이너일 때 `flex-shrink` 기본값(1)이 이 칸을 라벨보다
           좁게 눌렀고, 그 압축이 `overflow:hidden` 인 라벨 자리에 닿으면 "검…"처럼
           글자가 잘렸다(내 티켓 실측: 칸 126px 인데 알약 34.4px). 알약은 칸 하나에서
           "상태"를 나르는 유일한 표지라 줄어들 값이 아니다 — 칸이 좁으면 칸을 넓히지,
           알약을 안 줄인다. */
        /* 칸보다 길면 칸 폭 안에서 말줄임이다 — 예전 `minWidth: max-content` 는 긴 상태 낱말이 옆 칸 위로 넘쳤다(계획 6절 9).
           줄어들지는 않는다(`flexShrink: 0`): 칸이 넉넉하면 언제나 라벨 전체 폭이다. 칸 폭은 열 배분(D-529)이 값 길이로 정한다. */
        flexShrink: 0, minWidth: 0, maxWidth: "100%",
        fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.medium, lineHeight: 1.4,
        whiteSpace: "nowrap",
        color: extra ? extra.fg : palette ? `${palette}.strong` : "text.secondary",
        /* 면을 가진 배지는 **알약 하나의 규약**이다(확정 규약 §9): 높이 22, 좌우 8,
           Radius 4, 0.75rem/600, 옅은 면 + 진한 글자. 그 안에서는 표지 점을 안 그린다 —
           면 자체가 이미 「여기가 한 덩어리다」를 말하고, 6px 점이 22px 알약 안에 또 들어가면
           낱말이 밀려 알약이 길어지기만 한다. 점은 면이 없는 자리(표·목록)의 어휘다. */
        ...(strong && {
          height: remPx(CONTROL.pill), px: 1, py: 0, borderRadius: `${RADIUS.xs}px`,
          bgcolor: extra ? extra.bg : palette ? `${palette}.bg` : "background.inset",
          fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold, lineHeight: 1,
        }),
      }}
    >
      {strong ? null : (
        <Box
          aria-hidden="true"
          component="span"
          sx={{
            flexShrink: 0, width: 6, height: 6, borderRadius: marker,
            bgcolor: extra ? extra.fg : palette ? `${palette}.main` : "text.faint",
          }}
        />
      )}
      <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>{statusText(value)}</Box>
    </Box>
  );
}

/** 분류 표시 — 상태가 아니다 (지시 11: Status / Category / Tag / Editable Value 를 구분한다).
 *
 * 문서 종류(매뉴얼·참고자료·회의록)·업무 분야(인프라·개발·운영) 같은 것. 좋고 나쁨이 없으므로
 * 상태색을 쓰지 않는다.
 *
 * 🔴 **배지와 태그는 면으로 갈린다** (확정 규약 §9 · 갤러리 대조 D-2/D-3).
 *
 * 규약은 처음부터 둘을 갈라 놓았다 — 배지는 **옅은 면에 테두리 없음**, 태그는 **흰 면에
 * 1px 테두리**. 그런데 이 부품이 배지 쪽 면(`background.inset`)을 쓰고 있었고 높이도 20 대
 * 22 로 어긋나 있었다. 그 결과 문서 목록 한 줄에서 「계획」 배지와 「Docker」 태그가 같은
 * 부품으로 보였다 — 어휘가 둘이라는 사실 자체가 화면에서 사라진 것이다.
 *
 * 톤이 있는 태그(문서 종류)도 **면은 흰색 하나**다. 색은 글자만 받는다 — 면을 톤마다 주면
 * 그 순간 태그가 다시 배지가 되고, DS-09 가 고친 「분류에 의미색을 매기지 않는다」도 함께
 * 흔들린다. */
export function Tag({ label, tone, title }) {
  const extra = EXTRA_TONE_VARS[tone];
  return (
    <Box
      component="span"
      className="k-tag"
      data-tone={tone || "neutral"}
      /* 한 줄에서 말줄임되는 부품이라 전체 낱말을 `title` 로 든다(계획 §0-3). */
      title={title !== undefined ? (title || undefined) : (typeof label === "string" ? label : undefined)}
      sx={{
        display: "inline-flex", alignItems: "center", maxWidth: "100%", minWidth: 0,
        height: remPx(CONTROL.pill), px: 1, py: 0, borderRadius: `${RADIUS.sm}px`,
        border: 1, borderColor: "divider",
        /* 굵기 400 (핸드오프 D-8). 배지(600)와 굵기까지 같으면 면만으로 둘을 갈라야 하는데,
           흰 면과 옅은 면은 다크에서 한 단 차이라 거기서 두 어휘가 붙는다. */
        fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.regular, lineHeight: 1,
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        bgcolor: "background.paper",
        color: extra ? extra.fg : "text.secondary",
      }}
    >
      {label}
    </Box>
  );
}

/* 상태의 색을 나르는 **유일한** 자리 — 7px 점. 라벨 글자 옆에 서고 글자를 대신하지 않는다
 * (WCAG 1.4.1: 색만으로 뜻을 전하지 않는다). `aria-hidden` 인 이유가 그것이다.
 * `accent` 는 팔레트 경로(`error.main`)이거나 `--badge-*` 변수다(`TONE_ACCENT` 가 톤을 푼다).
 * 상태 요약 칩 · 회의 갈래 칩 · 점+낱말이 **같은 점**을 쓴다 — 각자 그리면 크기가 갈린다. */
export function StatusDot({ accent }) {
  return (
    <Box
      aria-hidden="true"
      component="span"
      data-status-dot=""
      sx={{
        flexShrink: 0, width: 7, height: 7, borderRadius: `${RADIUS.full}px`,
        bgcolor: (theme) => paletteAt(theme, accent),
      }}
    />
  );
}

/** 점 + 낱말 — 표 · 칸반 카드 · 목록 행 안의 **정해진 축 값**(상태 · 분류 · 우선순위 · 신호 ·
 * 방 종류). 핸드오프 D-21 · RULES §2: 그 자리에서는 면 배지를 쓰지 않는다 — 한 화면에 면이
 * 스무 개 서면 어디가 중요한지 사라진다. 목록 **밖**(카드 머리 · 제목 옆)은 `Badge` 다.
 *
 * `tone` 은 키트 톤(`ok` · `danger` · `warn` · `info` · `neutral` · 분류 톤)이다. 위험(`danger`)은
 * 필요하면 `strong` 으로 낱말을 600 으로 세운다 — 배지로 키우지 않는다.
 * 긴 낱말은 한 줄에서 말줄임되고 전체는 `title` 이 든다.
 *
 * `size="caption"` — 목록 행 · 칸반 카드 안의 작은 글자(0.8125rem) 자리. 예전에는 화면마다 `sx` 로 글자 크기를
 * 덮어썼다(채팅 방 목록 · 대화 속 티켓 카드). 크기는 부품이 갖고 화면은 이름만 고른다. */
export function DotLabel({ label, tone = "neutral", strong = false, size, title, sx, ...rest }) {
  const accent = tone === "neutral" ? "text.faint" : (TONE_ACCENT[tone] || tone);
  return (
    <Box
      component="span"
      className="k-dot-label"
      data-dot-label={tone}
      {...rest}
      title={title !== undefined ? (title || undefined) : (typeof label === "string" ? label : undefined)}
      sx={{
        display: "inline-flex", alignItems: "center", gap: 0.75, minWidth: 0, maxWidth: "100%",
        whiteSpace: "nowrap", verticalAlign: "middle",
        fontWeight: strong ? FONT_WEIGHT.semibold : "inherit",
        ...(size === "caption" ? { fontSize: FONT_SIZE.caption } : null),
        ...sx,
      }}
    >
      <StatusDot accent={accent} />
      <Box component="span" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{label}</Box>
    </Box>
  );
}

/** 건수 미니 칩 — 「3」 · 안 읽음 수 (핸드오프 README §9 · RULES §2).
 *
 * 함몰면 + 테두리, 등폭 숫자, **높이 20 한 값**이다(`compact` 18 은 이름 붙은 갈래 — 쓰는 자리를
 * 대장에 적는다). 같은 갈래는 내용과 무관하게 같은 높이로 선다. 안 읽음만 Primary 채움이다.
 * 예전에는 같은 뜻의 칩이 아홉 얼굴이었다(Badge 건수 · MUI Chip · 손 알약 · MUI Badge …).
 * 숫자만으로 뜻이 모자라는 자리는 호출부가 `ariaLabel` 로 온전한 문장을 준다. */
export function CountChip({ value, unread = false, compact = false, ariaLabel, sx }) {
  const h = compact ? 18 : 20;
  return (
    <Box
      component="span"
      className="k-count-chip"
      data-count-chip={compact ? "compact" : ""}
      aria-label={ariaLabel}
      sx={{
        display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        height: remPx(h), minWidth: remPx(h), px: 0.75, boxSizing: "border-box",
        borderRadius: `${RADIUS.full}px`, border: 1,
        borderColor: unread ? "primary.main" : "divider",
        bgcolor: unread ? "primary.main" : "background.inset",
        color: unread ? "primary.contrastText" : "text.secondary",
        fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold, lineHeight: 1,
        whiteSpace: "nowrap", ...NUMERIC, ...sx,
      }}
    >
      {value}
    </Box>
  );
}

/* 버튼 강도 계약 (지시 11 · R-11 · F-W1R-04) — **파괴적 동작은 주 행동을 이기지 않는다.**
 *
 * 예전에는 `danger` 가 `contained error` 였다. 그래서 실측에서 이런 화면이 나왔다:
 * `user_chat-rooms` 방 헤더 우상단의 «나가기» 가 페이지에서 **가장 채도 높은 면**(#B3261E)
 * 이고, 같은 화면의 진짜 주 행동 «새 그룹» 은 그보다 약했다. 다크에서는 `error.main` 이
 * 밝은 살몬(#FF8A80)으로 뒤집혀 근검정 캔버스 위 **가장 밝은 물체**가 됐다(캔버스 대비
 * 7.7:1 대 primary 3.0:1 — 2.5배). F 패턴의 시작점인 우상단을 파괴적 동작이 점유한 것이다.
 *
 * 강도는 넷이고 **채운 면은 둘뿐**이다.
 *
 *   primary        채운 브랜드 면. 화면당 하나. "여기서 할 일"
 *   danger         **외곽선 + error 잉크.** 눈에 띄되 주 행동을 이기지 않는다
 *   dangerConfirm  채운 error 면. **확인 대화 안에서만** — 이미 결정한 뒤의 마지막 버튼이라
 *                  거기서는 그것이 그 화면(모달)의 주 행동이다
 *   default        외곽선 중립 · ghost 맨 텍스트
 *
 * `danger` 라는 **이름은 그대로 둔다** — `scripts/check_button_hierarchy.py` 가 registry 의
 * 삭제·비활성화·보관 액션이 이 이름을 쓰는지 검사하고 있고, 이름을 바꾸면 그 가드가
 * 조용히 아무것도 안 지키게 된다. 바뀐 것은 이름이 아니라 강도다.
 */
const BUTTON_VARIANT = {
  primary: { variant: "contained", color: "primary" },
  danger: { variant: "outlined", color: "error" },
  dangerConfirm: { variant: "contained", color: "error" },
  ghost: { variant: "text", color: "inherit" },
  default: { variant: "outlined", color: "inherit" },
};
/* 핸드오프 어휘의 **Secondary** 는 이 키트의 `default` 다(흰 면 + 테두리). 화면 18곳이
   `variant="secondary"` 로 불렀는데 이 표에 그 이름이 없어 MUI 속성만 기본값으로 떨어지고,
   아래 `default` 전용 면 · 테두리 규칙은 못 받았다 — 그 버튼들의 테두리가 MUI 기본
   `currentColor`(17:1)로 서 있었다. 이름을 한 곳에서 풀어 준다. */
const BUTTON_VARIANT_ALIAS = { secondary: "default" };
/* loading: 라벨을 "처리 중…"으로 바꿔치기하지 않는다(예전 DataScreen/ModalFooter 관행) —
 * 텍스트만 바뀌면 스피너도 없고 버튼 폭도 라벨 길이 따라 흔들린다(DS-04). 라벨은 그대로 두고
 * visibility만 숨겨 폭을 고정한 채 스피너를 겹쳐 그린다. */
// forwardRef: MUI 컴포넌트(Tooltip 등)가 자식 DOM 노드에 직접 ref를 걸어야 하는 경우가 있다
// (Tooltip은 호버 위치를 앵커에서 계산한다) — 일반 함수 컴포넌트면 그 ref가 조용히 버려진다.
export const Button = React.forwardRef(function Button({ variant: askedVariant = "default", size, loading = false, disabled, truncate = false, children, sx, ...rest }, ref) {
  const variant = BUTTON_VARIANT_ALIAS[askedVariant] || askedVariant;
  if (import.meta.env.DEV && !BUTTON_VARIANT[variant]) {
    // eslint-disable-next-line no-console
    console.warn(`Button: 모르는 variant "${askedVariant}". 고를 수 있는 이름은 ${Object.keys(BUTTON_VARIANT).join(", ")}, secondary 중에서 고른다.`);
  }
  const v = BUTTON_VARIANT[variant] || BUTTON_VARIANT.default;
  /* `sm` 은 키트 옛 어휘, `small` 은 MUI 어휘다. 둘 다 같은 작은 버튼(30)이다 —
     `small` 만 빠지면 ChatRooms 「1:1」처럼 이름만 작고 높이는 medium(34)이 된다. */
  const isSm = size === "sm" || size === "small";
  return (
    <MuiButton
      ref={ref}
      type="button"
      size={isSm ? "small" : "medium"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...v}
      {...rest}
      /* 잘리는 칸에서만 쓰는 `truncate` — 라벨 전체를 `title` 로 든다(§0-3). */
      title={truncate && typeof children === "string" && !rest.title ? children : rest.title}
      sx={(theme) => ({
        position: "relative",
        /* **라벨은 한 줄이고 버튼은 자기 폭을 지킨다** (핸드오프 §0-3 줄바꿈 계약).
           높이가 34/30 인 조작기가 두 줄이 되면 그 줄의 모든 버튼이 어긋나고, flex 줄 안에서
           쉽게 줄어들면 정상 공간에서도 라벨이 잘린다. 줄이 모자라면 버튼이 아니라 **줄**이
           접힌다(`ToolbarEnd` 는 묶음째 내려간다). 표 칸처럼 실제로 좁은 자리만 `truncate` 로
           말줄임을 켠다. */
        whiteSpace: "nowrap",
        flexShrink: truncate ? 1 : 0,
        ...(truncate ? { minWidth: 0, maxWidth: "100%" } : null),
        /* 보조와 파괴 단추의 면 · 테두리는 **핸드오프 값**이다(README §2 · 다크 모드 절 · RULES §3 · ACCEPTANCE K3).
             보조  라이트 흰 면 + 판 경계선(`divider` #DCDFEC), hover 함몰면 + 강한 경계선(#BCC2D9)
                   다크   투명 면 + 강한 경계선(`dividerStrong` #333B5E), hover 함몰면(#1C2136)
             파괴  라이트 흰 면 + `error.line`(#E6B0AC) + `error.main` 글자(#B3261E), hover `error.bg`(#FAEBEC)
                   다크   투명 면 + `error.line`(#5F3330) + `error.main` 글자(#FF8A80), hover `error.bg`(#2E1A18)
           예전 규칙(R-11)은 테두리에 비텍스트 3:1 을 걸어 `text.faint` · 불투명 `error.main` 을 썼다. 이 단추들은
           글자 라벨이 컨트롤을 알린다 — 테두리는 컨트롤을 알아보는 데 필요한 유일한 신호가 아니라 WCAG 1.4.11 의
           대상이 아니고, 핸드오프가 그 자리를 옅은 경계선으로 정했다. R-11 이 막으려던 두 역전은 그대로 막힌다:
           MUI 기본 `currentColor`(본문 잉크 17:1)로 돌아가지 않고, 파괴 테두리가 중립 보조보다 흐리지 않다
           (판 위 라이트 1.88 대 1.33, 다크 1.68 대 1.62 — `kit.test.jsx` 「버튼 강도」가 계산값으로 잰다).
           꺼진 단추의 면 · 선 · 글자는 `theme.js` 의 `MuiButton` `&.Mui-disabled` 규칙이 이긴다(선택자가 더 구체적이다). */
        ...(variant === "default" ? {
          bgcolor: theme.palette.mode === "dark" ? "transparent" : theme.palette.background.paper,
          borderColor: theme.palette.mode === "dark" ? theme.palette.dividerStrong : theme.palette.divider,
          "&:hover": { bgcolor: theme.palette.background.inset, borderColor: theme.palette.dividerStrong },
        } : null),
        ...(variant === "danger" ? {
          bgcolor: theme.palette.mode === "dark" ? "transparent" : theme.palette.background.paper,
          borderColor: theme.palette.error.line,
          /* MUI 도 같은 값을 변수(`--variant-outlinedColor`)로 칠하지만, 글자색이 이 단추 계약의 일부라 여기에 적는다. */
          color: theme.palette.error.main,
          "&:hover": { bgcolor: theme.palette.error.bg, borderColor: theme.palette.error.line },
        } : null),
        ...(typeof sx === "function" ? sx(theme) : sx),
      })}
    >
      {/* 진행 중에도 **라벨을 그대로 둔다.**
       *
       * 예전에는 라벨을 `visibility: hidden` 으로 감추고 그 자리에 원형 진행 표시를 겹쳤다.
       * 시각적으로는 그럴듯한데 두 가지가 깨진다:
       *   1. `visibility: hidden` 인 글자는 접근성 트리에서 빠진다 — 누른 순간 이 버튼의
       *      **접근 가능한 이름이 사라진다.** 스크린리더는 "버튼"만 읽는다(실측: 시험이
       *      `getByRole("button", { name: "내보내기" })` 로 못 찾는다).
       *   2. 눈으로도 "무엇을 눌렀는지"가 사라진다 — 라벨을 "처리 중…"으로 바꿔치기하는
       *      관행을 이 앱이 금지한 이유와 정확히 같다.
       * 진행 표시를 라벨 **앞에** 붙이고 라벨은 그대로 읽히게 둔다. */}
      {loading ? (
        <CircularProgress
          size={isSm ? 14 : 16}
          color="inherit"
          sx={{ mr: 0.75, flexShrink: 0 }}
          aria-hidden="true"
        />
      ) : null}
      <Box
        component="span"
        sx={{
          display: "inline-flex", alignItems: "center", minWidth: 0,
          ...(truncate ? { display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } : null),
        }}
      >
        {children}
      </Box>
    </MuiButton>
  );
});

/* 안쪽 여백은 기준선 `.card.pad`(20px)다. 예전에는 `p: 3`(=1.5rem, 기본 루트에서 24px)이었다.
 * 한 변에 4px 이지만 **앱의 모든 카드**가 높이도 폭도 8px 씩 커지는 값이라
 * "담은 정보에 비해 카드가 너무 크다"로 보였다. 게다가 이 앱은 4K에서 루트 폰트를 올리므로
 * 24px 이 2560에서 27px, 3840에서 30px 로 더 벌어진다(기준선은 화면 폭과 무관하게 20px 다). */
/* 넘침 메뉴 — 한 자리의 동작이 셋을 넘거나, 파괴적 동작이 섞일 때 쓴다 (지시 11 · 12 · 43).
 *
 * 이 화면들이 겪던 문제는 "버튼이 많다"가 아니라 **무게가 같다**는 것이었다. 티켓 상세
 * 머리에는 목록·수정·원본 열기·삭제 넷이 나란히 있었고, 그중 삭제는 빨간 solid 버튼이라
 * 가장 자주 하는 일(수정)과 시선을 다퉜다. 파괴적 동작은 같은 줄에서 경쟁하지 않는다.
 *
 * 규칙: 주 동작 하나(+ 필요하면 보조 하나)만 버튼으로 두고 나머지는 여기로 넣는다.
 * 파괴적 항목은 `tone: "danger"` 로 표시하고 목록 끝에 실선으로 갈라 둔다.
 *
 * items: `{ key, label, onClick, href, tone, disabled, hint }[]` — `null`/`false` 는 걸러 낸다
 * (호출부가 권한 분기를 그대로 인라인으로 쓸 수 있게). `href` 가 있으면 항목은 링크(`<a>`)로 선다 —
 * 서버가 그리는 화면(비밀번호 변경)으로 가는 항목은 새 탭 열기 · 주소 복사가 되어야 한다.
 * `onPick(item)` 은 항목을 누를 때마다 불린다(보통 팝오버 닫기) — 누른 항목을 받으므로 결과를 그 자리에
 * 남겨야 하는 항목(로그아웃 실패)만 열어 둘 수 있다.
 */
/* `size` 는 **이웃이 정한다** (W5 재정정 — 복원된 프로브가 잡았다).
 *
 * 예전에는 `size="small"` 이 박혀 있었고, 그때는 `MuiIconButton` 의 최소 높이가 34 라 결과가
 * 우연히 옆 기본 버튼(34)과 맞았다. W5 가 「`size` 가 높이를 정한다」로 고치자 그 우연이
 * 깨져 화면 머리 동작 줄에서 30 vs 34 가 됐다(실측 `/team-docs`·`/users`·`/policies` 2560,
 * 4.5px). 기본은 이웃이 기본 버튼인 자리(화면 머리)라 **medium(34)** 이고, 작은 버튼과
 * 나란히 서는 자리(행 동작 줄)는 호출부가 `size="small"` 또는 `size="sm"` 이라고 말한다.
 * 둘 다 MUI IconButton 의 `small`(30)이다 — `sm` 을 그대로 넘기면 MUI 가 무시해 34 가 된다. */
/** 팝오버 **안의 항목 목록**. 머리도 발도 없이 이것만으로 선다 (확정 규약: 팝오버 = 항목 목록).
 *
 * 컴포넌트가 아니라 **배열을 돌려주는 함수**인 이유: MUI `Menu` 는 자식을 `MenuList` 에
 * 그대로 넘기고, `MenuList` 는 그 자식들을 훑어 키보드 이동을 붙인다. 목록을 컴포넌트 하나로
 * 감싸면 `MenuList` 눈에는 항목이 **하나**로 보여 화살표 키 이동이 죽는다.
 *
 * 내보내는 이유: 「메뉴 항목 한 줄은 어떻게 생겼나」를 확인하려면 메뉴를 여는 화면을 하나씩
 * 열어야 했다. 대조표(`/kit`)가 같은 함수를 불러 열린 상태를 붙박이로 세운다 — 값을 베끼지
 * 않고 실제 항목을 그린다. */
export function overflowMenuItems(items, onPick, idBase = "menu") {
  const list = (items || []).filter(Boolean);
  return list.map((it, i) => {
    const danger = it.tone === "danger";
    /* 파괴적 항목은 앞의 항목들과 실선으로 가른다 — 마우스가 미끄러져 바로 위 항목을
       누르려다 삭제를 누르는 일을 막는 물리적 간격이다. `divider` 는 같은 선을 다른 묶음 앞에 긋는다
       (예: 대상 동작 · 옮겨 가는 링크 · 상세 정보). */
    const firstDanger = danger && !(list[i - 1] && list[i - 1].tone === "danger");
    const rule = (firstDanger || it.divider) && i > 0;
    /* 할 수 없는 동작은 지우지 않고 까닭 한 줄과 함께 비활성으로 둔다 — 항목 이름은 동작 낱말 그대로이고(`aria-label`),
       까닭은 설명(`aria-describedby`)이다. 비활성 항목의 흐린 처리는 이름만 받고 까닭은 읽히는 굵기로 남긴다. */
    const helpId = it.help ? `${idBase}-help-${it.key || i}` : undefined;
    return (
      <MenuItem
        key={it.key || it.label || i}
        disabled={it.disabled}
        aria-label={it.help ? it.label : undefined}
        aria-describedby={helpId}
        {...(it.href ? { component: "a", href: it.href } : null)}
        onClick={() => { if (onPick) onPick(it); if (it.onClick) it.onClick(); }}
        sx={{
          fontSize: FONT_SIZE.bodySm,
          color: danger ? "error.strong" : "text.primary",
          borderTop: rule ? 1 : 0,
          borderColor: "divider",
          mt: rule ? 0.5 : 0,
          pt: rule ? 1 : undefined,
          ...(it.help ? {
            flexDirection: "column", alignItems: "flex-start", whiteSpace: "normal", maxWidth: "20rem",
            "&.Mui-disabled": { opacity: 1 },
          } : null),
        }}
      >
        {it.help ? (
          <>
            <Box component="span" sx={{ color: it.disabled ? "text.disabled" : "inherit" }}>{it.label}</Box>
            <Box component="span" id={helpId} sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>{it.help}</Box>
          </>
        ) : it.label}
      </MenuItem>
    );
  });
}

export function OverflowMenu({ items, ariaLabel = "더 보기", size }) {
  const list = (items || []).filter(Boolean);
  const [anchorEl, setAnchorEl] = React.useState(null);
  const idBase = React.useId();
  /* 까닭이 달린 비활성 항목은 키보드로도 닿아야 까닭이 읽힌다 — 그런 항목이 있을 때만 비활성 항목에 초점이 선다. */
  const reachDisabled = list.some((it) => it.disabled && it.help);
  if (!list.length) return null;
  const iconSize = size === "sm" || size === "small" ? "small" : size;

  const close = () => setAnchorEl(null);
  return (
    <>
      <IconButton
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={anchorEl ? true : undefined}
        onClick={(e) => setAnchorEl(e.currentTarget)}
        size={iconSize}
        sx={{ border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px`, color: "text.secondary" }}
      >
        <MoreHorizRoundedIcon fontSize="small" />
      </IconButton>
      <Menu
        anchorEl={anchorEl}
        open={!!anchorEl}
        onClose={close}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { minWidth: "12rem" } }, list: { disabledItemsFocusable: reachDisabled } }}
      >
        {overflowMenuItems(list, close, idBase)}
      </Menu>
    </>
  );
}

/* ── 면(Surface) — PLAN «Surface 위계» 를 코드로 ─────────────────────────────
 *
 * 지시 82 가 금지한 것은 규칙이 아니라 **반사**다: "무언가를 묶어야 한다 = 흰 네모를
 * 만든다". 그 반사를 문서로 막으면 다음 화면에서 그대로 다시 나온다. 그래서 판정을
 * 부품 하나로 옮긴다 — 무엇을 담을 수 있고 테두리·모서리·그림자를 갖는지가 여기 한 표에
 * 있고, 화면은 tone 하나만 고른다.
 *
 *   none       Section 제목·Divider·격자 간격이 사는 자리. **컨테이너를 그리지 않는다.**
 *   plate      자기 생명주기(save/cancel·독립 확장·독립 error/empty/loading)를 가진 경계 객체
 *   inset      표 머리·읽기전용·code·diff·hover/selected 행
 *   sunken     track·skeleton·chart band
 *   brandTint  AI/Assistant/Brand 순간. 앞머리 3px `brand.core` edge 를 함께 갖는다
 *   overlay    메뉴·팝오버·툴팁
 *   modal      다이얼로그·드로어
 *
 * ## 구획별 판정 체크리스트 (첫 Yes 에서 멈춘다)
 *
 *   ① 자체 Action 이나 생명주기가 있나                  -> plate
 *   ② 페이지와 독립적으로 스크롤/오버플로하나           -> plate
 *   ③ 떠 있나                                           -> overlay / modal
 *   ④ 입력/읽기전용 함몰면인가                          -> inset (더 깊으면 sunken)
 *   ⑤ AI/Brand 순간인가                                 -> brandTint
 *   ⑥ 그 외                                             -> **컨테이너 없음** (`none`)
 *                                                          `SectionTitle` + `SECTION_GAP`,
 *                                                          목록이면 제목 아래 1px divider
 *
 * ## 하드 금지 중 하나는 코드가 강제한다 — **판 안의 판**
 *
 * `plate` 가 이미 `plate` 안이면 자동으로 `none` 으로 내려간다. 흔적은 남긴다:
 * `data-surface="plate>none"` 이 그 자리에 붙어 하네스가 **몇 곳이 그랬는지 셀 수 있다**.
 * 조용히 고치면 다음 사람은 자기가 판 안에 판을 그렸다는 사실을 영영 모른다.
 *
 * 떠 있는 것(`overlay`·`modal`)은 깊이를 **0 으로 되돌린다** — 판 위에서 연 모달 안의
 * 카드는 판 안의 판이 아니다. React Context 는 Portal 을 통과하므로 이 초기화가 없으면
 * 모달 안의 모든 판이 조용히 사라진다(그것이 바로 이 파일이 겪을 뻔한 함정이다).
 */
/* 세그먼티드 — **같은 자리를 여러 보기가 나눠 쓸 때**의 전환기 (확정 규약 §2).
 *
 * 밑줄 탭과 무엇이 다른가: 밑줄 탭은 «지금 어디에 있는가» 를 선 하나로 말하고 나머지 칸은
 * 배경 없이 떠 있다. 그래서 칸이 넷쯤 되면 어디까지가 이 묶음인지 경계가 사라지고, 좁은
 * 폭에서는 밑줄이 글자보다 먼저 잘린다. 세그먼티드는 **묶음 자체가 면**이라 경계가 언제나
 * 보이고, 고른 칸만 그 면 위로 한 겹 올라온다.
 *
 * 치수는 규약이 정한 값 그대로다 — 컨테이너 안쪽 여백 3px, 안쪽 버튼은 컨테이너 높이
 * (`CONTROL.button` 34)에서 그 여백 둘을 뺀 28px, 모서리는 컨테이너 6px / 버튼 4px.
 * 새 숫자를 만들지 않고 있는 토큰에서 뺀다.
 *
 * 면은 두 단계다: 컨테이너가 함몰면(light #F5F6FB / dark #1C2136), 고른 칸이 판면
 * (#FFFFFF / #141829) + `raised` 그림자. 다크에서도 같은 두 토큰이 그대로 성립한다.
 *
 * 역할은 `tablist`/`tab` 이다 — 이 부품이 대신하는 것이 탭이고, 바꾸는 것은 **보기**이지
 * 상태가 아니다. `aria-selected` 가 지금 고른 칸을 말한다.
 *
 * options: `[{ value, label, count? }]`
 */
export function Segmented({ value, onChange, options, ariaLabel, sx }) {
  const list = (options || []).filter(Boolean);
  const refs = React.useRef([]);
  if (!list.length) return null;
  /* 탭 목록의 키보드 계약(WAI-ARIA Tabs) — 칸 여럿이 탭 순서에 **한 번만** 서고(roving
     tabindex), 화살표 · Home · End 로 옮기면 그 칸이 곧 선택된다. 예전에는 칸마다 탭 정거장이
     있어서 여섯 칸짜리 세그먼티드를 지나려면 Tab 을 여섯 번 눌러야 했다(`DiscussBucketRow` 가
     먼저 이 계약을 가졌다). */
  const current = Math.max(0, list.findIndex((o) => o.value === value));
  const move = (to) => {
    const next = (to + list.length) % list.length;
    onChange(list[next].value);
    const el = refs.current[next];
    if (el) el.focus();
  };
  const onKeyDown = (e) => {
    const at = list.findIndex((o) => o.value === value);
    const from = at < 0 ? 0 : at;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(from + 1); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(from - 1); }
    else if (e.key === "Home") { e.preventDefault(); move(0); }
    else if (e.key === "End") { e.preventDefault(); move(list.length - 1); }
  };
  return (
    <Box
      role="tablist"
      aria-label={ariaLabel}
      className="k-segmented"
      /* **보기 전환의 선택은 중립이다**(핸드오프 D-22 · C6 — 고른 칸만 흰 면으로 한 겹 올라온다). 그래서 이 줄은
         선택의 **브랜드 자리가 아니다** — 프로브(`scripts/ui_qa/brand.py`)가 흰 칸을 「회색인 선택 자리」로 세지 않게
         의미를 선언한다. 억제가 아니라 선언이라 마크업에 남고 grep 으로 셀 수 있다. 제품의 선택 브랜드는 사이드바
         레일 · 상태 칩 선택이 나른다. */
      data-brand-role="none"
      onKeyDown={onKeyDown}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: "2px",
        p: "3px",
        maxWidth: "100%",
        overflowX: "auto",
        bgcolor: "background.inset",
        /* **바깥 34 = 안쪽 28 + 여백 3 × 2** (핸드오프 D-22 · C6). 테두리를 상자에 그리면 1px 씩
           더해져 36 이 된다 — 그래서 선을 상자 **안쪽 그림자**로 그린다(`UserAvatar` 의 선과
           같은 방법). 높이 계산에서 선이 빠진다. */
        border: 0,
        boxShadow: (t) => `inset 0 0 0 1px ${t.palette.divider}`,
        borderRadius: `${RADIUS.sm}px`,
        ...sx,
      }}
    >
      {list.map((o, i) => {
        const on = o.value === value;
        return (
          <Box
            key={o.value}
            ref={(el) => { refs.current[i] = el; }}
            component="button"
            type="button"
            role="tab"
            aria-selected={on}
            tabIndex={i === current ? 0 : -1}
            onClick={() => onChange(o.value)}
            sx={{
              flexShrink: 0,
              display: "inline-flex",
              alignItems: "center",
              gap: 0.75,
              height: remPx(CONTROL.button - 6),
              px: 1.5,
              border: 0,
              borderRadius: `${RADIUS.sm - 2}px`,
              font: "inherit",
              fontSize: FONT_SIZE.bodySm,
              fontWeight: FONT_WEIGHT.semibold,
              whiteSpace: "nowrap",
              cursor: "pointer",
              color: on ? "text.primary" : "text.secondary",
              bgcolor: on ? "background.plate" : "transparent",
              /* 테마 토큰이 없는 자리(테마 없이 부품을 격리해 그리는 시험)에서 죽지 않는다 — `UserAvatar` 와 같은 이유. */
              boxShadow: (t) => (on ? (t.shadowTokens && t.shadowTokens.raised) || "none" : "none"),
              transition: `background-color ${MOTION.fast} ${MOTION.ease}, color ${MOTION.fast} ${MOTION.ease}`,
              "&:hover": on ? null : { color: "text.primary" },
              "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
            }}
          >
            {o.label}
            {o.count != null ? (
              <>
                {/* 낱말과 숫자 사이 공백은 **글자로** 둔다 — 간격(gap)만 두면 접근 이름이 「티켓1」로
                    붙어 읽힌다. flex 칸 안의 공백만 있는 글자는 그려지지 않으므로 모양은 그대로다. */}
                {" "}
                {/* 건수는 언제나 보조 잉크다 — `faint` 는 AA-large 자리 전용이라 이 크기에
                    못 쓴다(`scripts/check_ink_scale.py`). 라벨과의 위계는 굵기가 만든다. */}
                <Box component="span" sx={{ color: "text.secondary", fontWeight: FONT_WEIGHT.regular, ...NUMERIC }}>{o.count}</Box>
              </>
            ) : null}
          </Box>
        );
      })}
    </Box>
  );
}

export const SURFACE_EDGE_WIDTH = 3;

export const SURFACE_TONES = {
  none: {},
  plate: { fill: "background.plate", border: true, radius: RADIUS.md, holds: true },
  inset: { fill: "background.inset", radius: RADIUS.sm },
  sunken: { fill: "background.sunken", radius: RADIUS.sm },
  brandTint: { fill: "background.brandTint", radius: RADIUS.md, edge: "brand.core" },
  overlay: { fill: "background.plate", border: true, radius: RADIUS.md, shadow: "overlay", floats: true },
  modal: { fill: "background.plate", border: true, radius: RADIUS.md, shadow: "modal", floats: true },
};

/* 팔레트 경로("brand.core")를 실제 색으로. `borderInlineStartColor` 는 MUI 의 border 설정
   목록에 없어 팔레트 경로를 해석해 주지 않는다 — 그래서 여기서 직접 푼다.

   🔴 경로가 아닌 값은 **그대로 돌려준다.** 브랜드 밖 톤(보라·틸·인디고)의 색은 팔레트가
   아니라 `--badge-*-fg` CSS 변수다(아래 `EXTRA_TONE_VARS` 와 같은 값이다). 예전에는 그것을
   경로로 읽어 `theme.palette["var(--badge-purple-fg)"]` 를 찾았고, 없으니 `undefined` 가
   나갔다. `border-color` 에 undefined 를 주면 속성이 아예 안 실리고 CSS 기본값
   `currentColor` 로 떨어진다 — 보라 띠를 부탁한 자리에 **글자색 띠**가 그려지고 아무
   오류도 안 난다. KPI 타일과 논의 갈래 카드의 위색 띠가 그 상태였다. */
export function paletteAt(theme, path) {
  const found = String(path).split(".").reduce((o, k) => (o == null ? o : o[k]), theme.palette);
  return found == null ? String(path) : found;
}

/* 톤 이름 → 강조색. **같은 의미는 제품 전체에서 같은 색이다** — 신호 어휘
   (`lib/ticketSignals.js`)가 고른 톤을 KPI 타일과 논의 갈래 카드가 같은 표로 푼다.
   예전에는 두 부품이 각자 ternary 사슬을 갖고 있어서 한쪽만 톤을 알았다. */
export const TONE_ACCENT = {
  ok: "success.main",
  danger: "error.main",
  warn: "warning.main",
  info: "info.main",
  primary: "brand.core",
  brand: "brand.core",
  indigo: EXTRA_TONE_VARS.indigo.fg,
  purple: EXTRA_TONE_VARS.purple.fg,
  teal: EXTRA_TONE_VARS.teal.fg,
  pink: EXTRA_TONE_VARS.pink.fg,
};

/* 지금 이 자리가 판 안인가. 0 = 캔버스 위. */
const SurfaceDepthCtx = React.createContext(0);

/* ── 상태 자리 — 빈 상태 · 오류 상태의 기본 배치는 **담는 쪽**이 정한다 (F4 · D-530) ─────────────────────────
 *
 * 판(카드 · 구획 · 목록 판) · 판 안 묶음 · 탭 판 · 모달 · 표 틀 안에 선 상태는 그 자리의 한 칸이다(region — 왼쪽 · 위 정렬,
 * 작은 그림). 그 밖(화면 본문에 바로 선 상태)은 화면 전체가 그 상태다(page — 가운데, 큰 그림). 예전에는 `ErrorState` 의 기본이
 * 언제나 page 라 판 안에서 실패한 목록(조직 구성원 · 정합성 목록)이 판 가운데에 큰 오류로 섰다. 자리를 아는 부품(`Surface` ·
 * `SubGroup` · `TabShell` 의 탭 판 · `Modal`)이 이 문맥을 깔고, 상태 부품은 `layout` 을 안 받으면 문맥을 본다. */
const StateRegionCtx = React.createContext(false);

/** 이 아래의 빈 상태 · 오류 상태는 자리의 한 칸(region)이다. */
export function StateRegion({ children }) {
  return <StateRegionCtx.Provider value>{children}</StateRegionCtx.Provider>;
}

/** 지금 자리가 판 · 탭 판 · 모달 안인가. */
export function useStateRegion() {
  return React.useContext(StateRegionCtx);
}

/* 표 안 빈 띠 — `DataTable` 이 빈 표의 머리 아래 줄(또는 좁은 화면의 판)에 깐다. 그 안의 `EmptyState` 는 어떤 `layout` 을
   받았든 한 줄 띠로 선다(D-530 — 판을 흰 면으로 채우지 않는다). `inset` 이면 판 여백 안이라 띠가 좌우 여백을 따로 두지 않는다. */
const TableEmptyBandCtx = React.createContext(null);
const BAND_IN_CELL = Object.freeze({ inset: false });
const BAND_IN_PLATE = Object.freeze({ inset: true });

function surfaceSx(theme, spec) {
  return {
    ...(spec.fill ? { bgcolor: spec.fill } : null),
    ...(spec.radius ? { borderRadius: `${spec.radius}px` } : null),
    ...(spec.border ? { border: 1, borderColor: "divider" } : null),
    ...(spec.shadow ? { boxShadow: theme.shadowTokens[spec.shadow] } : null),
    /* 논리 테두리는 MUI 가 펴 주지 않는다 — style·width·color 를 따로 적어야 그려진다.
       `scripts/check_logical_border_props.py` 가 이 형태를 강제한다(F-W2R-01). */
    ...(spec.edge
      ? {
        borderInlineStartStyle: "solid",
        borderInlineStartWidth: `${SURFACE_EDGE_WIDTH}px`,
        borderInlineStartColor: paletteAt(theme, spec.edge),
      }
      : null),
  };
}

export function Surface({ tone = "plate", component, className, children, sx, ...rest }) {
  const depth = React.useContext(SurfaceDepthCtx);
  const wanted = SURFACE_TONES[tone] ? tone : "plate";
  const degraded = wanted === "plate" && depth > 0;
  const spec = degraded ? SURFACE_TONES.none : SURFACE_TONES[wanted];
  const nextDepth = spec.floats ? 0 : (spec.holds ? depth + 1 : depth);

  const merged = (theme) => ({
    ...surfaceSx(theme, spec),
    ...(typeof sx === "function" ? sx(theme) : sx),
  });

  /* `plate` 는 MUI Card 로 그린다 — theme.js 의 `MuiCard` 오버라이드가 이미 판 토큰
     (1px divider · radius md · 그림자 없음)과 **같은 값**이고, 화면 시험 몇 개가
     `.MuiCard-root` 로 판을 짚는다. 떠 있는 것은 Paper(그림자 계층), 나머지는 Box 다. */
  const Comp = spec.holds && !degraded ? MuiCard : (spec.floats ? Paper : Box);
  const extra = Comp === MuiCard || Comp === Paper ? { elevation: 0 } : null;

  return (
    <SurfaceDepthCtx.Provider value={nextDepth}>
      <Comp
        className={className}
        data-surface={degraded ? `${wanted}>none` : wanted}
        component={component}
        {...extra}
        sx={merged}
        {...rest}
      >
        <StateRegionCtx.Provider value>{children}</StateRegionCtx.Provider>
      </Comp>
    </SurfaceDepthCtx.Provider>
  );
}

/** 지금 이 자리가 판 안인가. 0 이면 캔버스 위다. */
export function useSurfaceDepth() {
  return React.useContext(SurfaceDepthCtx);
}

/** 떠 있는 것 안에서는 깊이를 0 으로 되돌린다 — 판 위에서 연 모달 안의 카드는 판 안의 판이
 * 아니다. React Context 는 Portal 을 통과하므로 이 초기화가 없으면 판 위에서 연 모달의
 * 카드가 조용히 사라진다. `Modal` 이 이것을 쓴다. */
export function SurfaceReset({ children }) {
  /* 떠 있는 판(모달)의 안도 그 판의 한 칸이다 — 상태는 region 으로 선다. */
  return (
    <SurfaceDepthCtx.Provider value={0}>
      <StateRegionCtx.Provider value>{children}</StateRegionCtx.Provider>
    </SurfaceDepthCtx.Provider>
  );
}

/* 판 — `Surface tone="plate"` 에 판 안쪽 여백을 더한 것. 소비처 170여 곳이 이 이름을 쓴다.
 *
 * 안쪽 여백은 `density.js::CARD_PADDING`(24px)이다. W4 가 20 에서 올렸다 — 19px 구획
 * 제목이 20px 여백 안에서 테두리에 붙어 읽혔다.
 *
 * **판 안에서는 여백도 함께 사라진다.** 판정이 `none` 으로 내려갔는데 24px 여백만 남으면
 * 부모 판의 24px 와 겹쳐 48px 들여쓰기가 된다 — 없앤 테두리가 공백으로 되살아나는 셈이다. */
/* `stack` — 자식 사이 세로 간격 14 를 판이 준다(RULES §0 「카드 안은 14px」, D-528). 자식의 위아래 바깥 여백은 지운다. 판에
   여러 덩어리(메시지 상자 · 폼 · 표)를 쌓을 때 화면이 덩어리마다 여백을 적지 않게 한다. 시각 프로브는 `Surface` 가 이미 다는
   `data-surface="plate"` 로 카드 안 카드(F7 카드 규율)를 찾는다 - 판 안에서 눕은 판은 `plate>none` 이라 세지 않는다.
   `padding` — 판 안쪽 여백의 단계다. `normal`(20) · `compact`(10, 칸반 카드 · 회의 목록처럼 판이 한 줄 행인 자리) ·
   `none`(판 안을 목록 · 대화 창이 가장자리까지 채우는 자리). 화면이 `sx={{ p }}` 로 덮지 않는다(primitive-geometry-override). */
const CARD_PADDINGS = { normal: CARD_PADDING, compact: CARD_PADDING_COMPACT, none: 0 };

export function Card({ className, children, sx, stack = false, padding = "normal", ...rest }) {
  const nested = useSurfaceDepth() > 0;
  // 판 안의 판은 여백도 함께 사라진다(위). 단계를 직접 고른 판(compact · none)은 그 단계를 그대로 쓴다.
  const base = padding !== "normal" && padding in CARD_PADDINGS ? { p: CARD_PADDINGS[padding] } : nested ? null : { p: CARD_PADDING };
  const stacked = stack ? { display: "flex", flexDirection: "column", rowGap: 1.75, "&& > *": { marginBlockStart: 0, marginBlockEnd: 0 } } : null;
  /* 판 발(`ActionFooter placement="card"`)이 판의 마지막 줄이면 발은 **판 바닥**에 선다 (UI 3차 P4).
     짝 격자(stretch)에서 판이 내용보다 길어지면 발이 판 가운데에 뜨고 아래가 비었다 — 점검의 두 판은 발이 109px 어긋났다.
     판을 세로 흐름으로 두고 본문을 한 상자로 묶어 남는 높이를 먹게 한다. 본문 상자 안은 예전과 같은 보통 흐름이다. */
  const items = React.Children.toArray(children);
  const last = items[items.length - 1];
  const footed = !nested && React.isValidElement(last) && last.type === ActionFooter && last.props.placement === "card";
  const layout = footed ? { display: "flex", flexDirection: "column" } : null;
  /* 발이 있는 판의 쌓기 간격은 본문 상자가 준다 - 발은 자기 윗선과 위 여백으로 본문과 갈린다(판 바닥에 선다). */
  const rootStack = footed ? null : stacked;
  const merged = typeof sx === "function"
    ? (theme) => ({ ...base, ...rootStack, ...layout, ...sx(theme) })
    : { ...base, ...rootStack, ...layout, ...sx };
  return (
    <Surface tone="plate" className={className} sx={merged} {...rest}>
      {footed ? (
        <>
          <Box data-card-body="" sx={{ flex: "1 1 auto", minWidth: 0, ...stacked }}>{items.slice(0, -1)}</Box>
          {last}
        </>
      ) : children}
    </Surface>
  );
}

/* 목록 표를 담는 판 — **자기 안을 자르지 않는다.**
 *
 * 🔴 왜 `Card` 와 따로 있는가. `Card` 는 `Surface tone="plate"` 이고 그것은 MUI `Card` 로
 * 그려지는데, MUI `Card` 의 root 는 `overflow: hidden` 이다. `overflow` 가 `visible` 이
 * 아닌 조상은 **`position: sticky` 의 스크롤 컨테이너가 된다** — 그래서 표에 `stickyHeader`
 * 를 켜도 열 이름이 이 판 안에 붙박이고 페이지를 굴려도 절대 안 따라온다.
 *
 * 실측: `/audit` 이 `stickyHeader: true` 를 켜 둔 채로 그 상태였다. 아무도 신고하지 않은
 * 이유는 속성만 재는 검사에는 `position: sticky` 가 그대로 보이기 때문이다(D-347 이 같은
 * 부류를 «속성은 sticky 인데 굴리면 열 이름이 사라진다» 로 이미 한 번 적었다).
 *
 * 가로 넘침은 이 판이 아니라 표 안의 `TableContainer` 가 맡는다(`DataTable` 참고). 예전 주석은 「`.c-list-card` 의
 * 안쪽 여백(6px 8px)이 있어 둥근 모서리에 표가 닿지 않는다」고 했는데, 그 CSS 는 `Card` 의 sx 여백(20)에 늘 져서
 * 한 번도 그려지지 않았다 — 규칙은 걷었다(UI 3차 P3).
 *
 * **표를 담는 목록은 이 판을 쓰지 않는다** — `DataTable placement="surface"` 가 판을 그린다(조합 계약 C-3). 이 판이
 * 남는 자리는 표가 아닌 목록(내 활동의 날짜 묶음처럼 판 안에 고정 머리를 두는 목록)이다. */
export function ListCard({ className, children, sx, ...rest }) {
  const merged = typeof sx === "function"
    ? (theme) => ({ overflow: "visible", ...sx(theme) })
    : { overflow: "visible", ...sx };
  return (
    <Card className={className ? `c-list-card ${className}` : "c-list-card"} sx={merged} {...rest}>
      {children}
    </Card>
  );
}

/** 계속 늘어나는 **보조 목록**만 담는 스크롤 칸.
 *
 * ## 아무 데나 쓰지 않는다
 *
 * 판마다 안쪽 스크롤을 만들면 한 화면에 스크롤 축이 서넛 생기고, 사용자는 지금 무엇을
 * 굴리고 있는지 모른다. 이 부품이 맞는 자리는 **하나뿐**이다: 서버가 상한을 두지 않아
 * 길이가 예측되지 않는 목록. 서버가 이미 잘라 주는 목록(홈의 최근 문서 5건, 대시보드의
 * 최근 주요 변경 5건)은 그대로 다 그리고 「전체 보기」로 넘긴다 — 다섯 줄짜리 스크롤 칸은
 * 굴릴 것이 없는 스크롤바를 만들 뿐이다.
 *
 * **핵심 지표·그래프에는 쓰지 않는다.** 값 하나를 보려고 굴려야 하는 KPI 는 KPI 가 아니다.
 *
 * ## 지키는 것 셋
 *
 * 1. **내용이 짧으면 스크롤바가 없다** — `overflow-y: auto` 라 넘칠 때만 생긴다.
 * 2. **스크롤바가 글자를 덮지 않는다** — `scrollbar-gutter: stable` 이 자리를 미리 잡아
 *    두므로, 목록이 길어져 스크롤바가 생기는 순간에도 글자가 옆으로 밀리지 않는다.
 * 3. **넘칠 때만 초점을 받는다** — 스크롤 영역은 키보드로 굴릴 수 있어야 하고(WCAG 2.1.1),
 *    그러려면 초점을 받아야 한다. 그런데 **굴릴 것이 없는 칸까지 초점을 받으면** 탭 순서에
 *    아무 일도 안 하는 정거장이 하나 생긴다. 그래서 실제 넘침을 재서 그때만 `tabIndex` 를
 *    준다 — 덕분에 「지금은 안 넘치지만 자료가 늘면 넘치는 자리」에도 안심하고 쓸 수 있다.
 */
export function ScrollArea({ maxHeight, ariaLabel, children, sx }) {
  const ref = React.useRef(null);
  const [overflows, setOverflows] = React.useState(false);
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => setOverflows(el.scrollHeight > el.clientHeight + 1);
    measure();
    if (typeof ResizeObserver !== "function") return undefined;
    // 칸 자체가 줄어들 때와 내용이 늘어날 때를 모두 본다.
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    if (el.firstElementChild) ro.observe(el.firstElementChild);
    return () => ro.disconnect();
  });
  return (
    <Box
      ref={ref}
      className="k-scrollarea"
      data-overflows={overflows ? "true" : "false"}
      role={overflows ? "group" : undefined}
      tabIndex={overflows ? 0 : undefined}
      aria-label={overflows ? ariaLabel : undefined}
      sx={(t) => ({
        maxHeight,
        overflowY: "auto",
        /* **이 칸이 스크롤 창이라는 사실을 안쪽에 알린다.** 안에 든 표가 `stickyHeader` 를
           켜면 그 열 이름은 이 칸의 **위쪽**에 붙어야 한다 — 기본값(상단바 높이)은 윈도가
           굴러갈 때의 값이라, 여기서 그대로 쓰면 열 이름이 52px 내려앉고 그 위로 행이
           굴러 올라가 겹친다(`theme.js::STICKY_TOP_VAR`). */
        ...SCROLL_BOX_STICKY_TOP,
        // 바깥(브라우저) 스크롤로 이어지지 않게 한다 — 칸 끝에서 페이지가 함께 튀면
        // 사용자는 자기가 무엇을 굴렸는지 모른다.
        overscrollBehavior: "contain",
        // 자리는 넘칠 때만 잡는다. 안 넘치는 칸에까지 8px 를 비워 두면 옆 줄과 오른쪽
        // 끝이 어긋나 보인다.
        scrollbarGutter: overflows ? "stable" : "auto",
        pr: overflows ? 0.5 : 0,
        "&:focus-visible": { outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 },
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
    >
      {children}
    </Box>
  );
}

/** 기술 정보 — 원문·내부 키·경로처럼 **평소에는 화면의 내용이 아닌 것**을 접어 둔다.
 *
 * 지시 36 이 요구하는 것은 기술 정보의 **삭제가 아니라 강등**이다: 장애를 분석하려면
 * `SMTPAuthenticationError: (535, ...)` 원문이 필요하고, 그것을 지우면 운영자에게서 유일한
 * 단서를 빼앗는다. 다만 그것이 화면의 주된 내용이 되면 읽는 사람은 매번 우리 구현을 먼저
 * 읽는다. 그래서 요약이 앞에 서고 원문은 이 안에 접힌다 — 열기 전에는 한 줄도 차지하지 않는다.
 *
 * `Callout` 안에만 두면 표·카드·상세가 각자 `<details>` 를 다시 만든다(그러면 라벨과
 * 포커스 표시가 화면마다 갈라진다). 그래서 primitive 로 둔다.
 */
/** 짧은 상태 면의 사실 줄 — 단계 · 속성 띠 뒤 끝에 「기술 정보」(`TechDetail trailing`)가 접힌 채 붙는 한 줄이다. 펼치면 기술 정보가
 *  제 줄로 내려간다. 「기술 정보」에 줄 하나를 따로 주면 상태 면이 그만큼 길어져 첫 폼 칸이 1366 첫 화면 기준(420px) 아래로 밀렸다(P17V). */
export const FACTS_ROW_SX = { display: "flex", flexWrap: "wrap", alignItems: "baseline", columnGap: 3, rowGap: 0.75, minWidth: 0 };

export function TechDetail({ label = "기술 정보", children, sx, trailing = false }) {
  if (children == null || children === "" || children === false) return null;
  return (
    <Box
      component="details"
      className="k-techdetail"
      data-trailing={trailing ? "" : undefined}
      sx={{
        /* `trailing` — 사실 줄(`FACTS_ROW_SX`)의 마지막 칸으로 접힌 채 오른쪽 끝에 선다. 펼치면 줄 전체 폭을 받아 제 줄로 내려간다. */
        ...(trailing ? {
          flex: "0 0 auto", marginInlineStart: "auto",
          "&[open]": { flexBasis: "100%", marginInlineStart: 0 },
        } : null),
        "& > summary": {
          cursor: "pointer", fontSize: FONT_SIZE.bodySm, color: "text.secondary",
          listStyle: "revert", width: "fit-content",
        },
        "& > summary:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
        ...sx,
      }}
    >
      <Box component="summary">{label}</Box>
      <Box sx={{ mt: 0.75, fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}>
        {children}
      </Box>
    </Box>
  );
}

/* 네 종의 아이콘. 색만으로 심각도를 전하지 않는다(WCAG 1.4.1) — 모양이 넷 다 다르고,
 * 그 옆의 **글자 라벨**은 그대로 남는다. 아이콘은 글자를 대신하는 것이 아니라 거든다. */
const CALLOUT_ICON = {
  info: InfoOutlinedIcon,
  success: CheckCircleOutlineRoundedIcon,
  warn: WarningAmberRoundedIcon,
  danger: ErrorOutlineRoundedIcon,
};

/* 메시지 상자의 바로 위 그릇이 **간격을 주는 그릇**인가 — flex · grid 이고 줄 간격(gap)이 0 보다 크다(D-528).
 *
 * 흐름 밖 메시지 상자는 형제와 12px 한 간격을 스스로 갖는다(`styles/screens.css` 의 `.k-callout` 형제 규칙). 블록 흐름에서는
 * 위아래 여백이 겹쳐 12 가 되지만, flex · grid 에서는 여백이 겹치지 않고 그릇의 gap 에 **더해진다** - 격자 안의 두 상자 사이가
 * gap + 24 로 벌어졌다(부품 갤러리 실측 34px). 그 그릇은 이미 간격을 주므로 상자가 여백을 더하지 않게 표지를 단다.
 * 첫 그림 전에(`useLayoutEffect`) 한 번 잰다 - 그릇의 배치는 화면이 그릇을 바꿀 때만 바뀐다. */
function useGapParent() {
  const ref = React.useRef(null);
  const [on, setOn] = React.useState(false);
  React.useLayoutEffect(() => {
    const parent = ref.current && ref.current.parentElement;
    if (!parent || typeof getComputedStyle !== "function") return;
    const st = getComputedStyle(parent);
    const layout = /(?:^|-)(?:flex|grid)$/.test(st.display || "");
    const gap = (parseFloat(st.rowGap) || 0) > 0 || (parseFloat(st.columnGap) || 0) > 0;
    setOn(layout && gap);
  }, []);
  return { ref, on };
}

export function Callout({
  tone = "info", variant = "block", compact = false, title, action,
  detail, detailLabel = "기술 정보", children, role, toneLabel, className, sx,
}) {
  /* `className` 은 시험 · 프로브가 자리를 붙잡는 표지다(폼 서버 오류 `k-form-err` 처럼). 모양은 바꾸지 않는다. */
  const rootClass = className ? `k-callout ${className}` : "k-callout";
  const gapParent = useGapParent();
  /* 안내 — **큰 외곽선 상자를 기본형으로 쓰지 않는다** (지시 35).
   *
   * 예전에는 tone 과 무관하게 전부 `MuiAlert variant="outlined"` 였다. 호출부 67곳 중
   * **43곳이 warn** 이었으니, 화면에서 주황 테두리 상자가 기본값이었다는 뜻이다 — 전부
   * 경고면 아무것도 경고가 아니다. 참고와 조치 필요가 같은 강도로 보이던 원인이다.
   *
   * 새 위계:
   *   info    앞머리 실선 하나. 바탕 없음. 가장 조용하다.
   *   success 옅은 바탕 + 앞머리 실선.
   *   warn    옅은 바탕 + 앞머리 실선(색이 다르다).
   *   danger  옅은 바탕 + 앞머리 실선 + 라벨 굵게. 페이지 전폭 빨간 테두리는 쓰지 않는다.
   *
   * 심각도를 색만으로 구분하지 않는다(WCAG 1.4.1) — 아이콘 **모양**이 넷 다 다르고
   * (동그라미 i · 체크 · 삼각형 · 동그라미 느낌표) 그 아이콘이 **접근 이름**(안내 · 성공 ·
   * 주의 · 오류)을 갖는다. 낭독기는 그 이름을 읽고, 색을 못 보는 사람은 모양으로 가른다.
   *
   * 구조는 넷이다 — **아이콘 · 제목 · 본문 · 동작**(지시 20). `action` 은 본문 아래 한 줄이다.
   *
   * `detail` 은 긴 기술 설명을 접어 둔다(지시 35: "긴 기술 설명을 하나의 Alert 안에 모두
   * 넣지 않는다"). 표현은 `TechDetail` 이 맡는다 - 표·카드도 같은 접기를 쓴다.
   */
  const kind = tone === "ok" ? "success" : tone;
  /* 톤의 이름은 **아이콘의 접근 이름**으로만 남는다 — 화면에는 안 적는다.
   *
   * 예전에는 `title` 이 없으면 이 낱말이 제목 줄로 올라왔다. 그 한 줄이 두 가지를 망쳤다:
   * 한 줄짜리 안내 상자의 높이가 **두 배**(49 → 98px)가 됐고, 더 나쁘게는 **제목 자리를
   * 일반 낱말이 차지해** 진짜 제목을 넣을 곳이 없어졌다 — 「안내 / 진행 중인 회차가
   * 없습니다」처럼 아무 정보도 없는 머리 아래 정작 할 말이 앉았다.
   * 색만으로 나르지 않는다는 요구(WCAG 1.4.1)는 아이콘의 **모양 넷**과 이 접근 이름이
   * 이미 만족한다. 낭독기는 「경고 아이콘, 주의」를 읽고 화면에는 낱말이 겹치지 않는다. */
  /* `toneLabel` — 아이콘의 접근 이름을 화면의 판정 낱말로 준다(대시보드의 「위험 · 주의 · 정상」). 같은 화면의
     조치 목록 심각도 태그와 같은 말이어야 낭독기가 한 뜻을 두 낱말로 읽지 않는다(재감사 C16). */
  const toneWord = toneLabel || (kind === "danger" ? "오류" : kind === "warn" ? "주의" : kind === "success" ? "성공" : "안내");
  const paletteKey = kind === "danger" ? "error" : kind === "warn" ? "warning" : kind === "success" ? "success" : "info";
  const Icon = CALLOUT_ICON[kind] || InfoOutlinedIcon;

  if (variant === "inline") {
    /* 문장 흐름 안에 놓이는 한 줄. 상자도 바탕도 없다 — 여기서는 제목과 본문이 한 줄에 이어지는
       것이 맞다. 구조(아이콘·제목·본문·동작)는 아래 판형의 계약이다.
       🔴 **톤 이름 낱말을 그리지 않는다**(핸드오프 D-11). 예전에는 제목이 없으면 「안내」 「주의」가
       색 글자로 앞에 섰다 — 판형에서 걷어 낸 톤 이름 줄이 이 갈래에만 남아 있었다. 상태는 앞의
       작은 아이콘 모양과 그 접근 이름이 말한다. */
    return (
      <Typography
        ref={gapParent.ref}
        className={rootClass}
        data-gap-parent={gapParent.on ? "" : undefined}
        data-tone={kind}
        data-variant="inline"
        component="p"
        sx={{ fontSize: FONT_SIZE.bodySm, display: "flex", alignItems: "flex-start", gap: 0.75, ...KO_WORD_BREAK, ...sx }}
      >
        <Icon titleAccess={toneWord} sx={{ flexShrink: 0, fontSize: remPx(ICON.mark), color: `${paletteKey}.main`, mt: "0.125rem" }} />
        <Box component="span" sx={{ minWidth: 0 }}>
          {title ? (
            <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, mr: 1.25, color: "text.primary" }}>{title}</Box>
          ) : null}
          <Box component="span" className="k-callout-body">{children}</Box>
        </Box>
      </Typography>
    );
  }

  return (
    <Box
      ref={gapParent.ref}
      className={rootClass}
      data-gap-parent={gapParent.on ? "" : undefined}
      data-tone={kind}
      /* 오류는 지금 끼어들어야 하는 사실이고(`alert`), 나머지는 알리되 흐름을 끊지 않는다
         (`status` — 암묵적으로 `aria-live="polite"`). 예전에는 오류 아닌 것이 `note` 라
         낭독기가 새로 나타난 안내를 아예 말하지 않았다.
         호출부가 덮을 수 있다: **목록 안에 놓이면 `listitem` 이라야** 그 목록이 깨지지 않고,
         사용자가 스스로 열어 본 목록은 낭독을 따로 할 이유가 없다(알림함이 그렇다). */
      role={role || (kind === "danger" ? "alert" : "status")}
      /* **하나의 박스, 아이콘만 다르다.**
       *
       * 예전에는 톤마다 앞머리 실선(2px)과 바탕(`*.bg`)이 달랐다. 그래서 같은 목적의
       * 상자가 화면마다 네 가지 무게로 나타났고, 카드 안에 놓이면 판이 겹쳐 보였다.
       * 지금은 면·테두리·모서리·여백·글자가 **넷 다 같고** 상태는 아이콘의 모양과 색만
       * 말한다. 색을 못 봐도 아이콘 모양이 넷을 가르고, 그 위에 짧은 텍스트 라벨이
       * 언제나 함께 있다(WCAG 1.4.1).
       *
       * 격자는 `auto minmax(0,1fr) auto` 다 — 아이콘 · 글 · 오른쪽 동작. 동작이 오른쪽
       * 칸에 서는 것은 이 상자가 대개 한 줄이기 때문이다(닫기·다시 시도·자세히 보기).
       * 글이 여러 줄이면 동작은 첫 줄 옆에 붙는다(`align-items: start`).
       * `minmax(0,1fr)` 이 글 칸의 바닥을 0 으로 열어 두므로 동작이 넓어도 글이 안 밀린다. */
      data-variant={variant}
      sx={(t) => ({
        /* 머리 줄(`HeadRow`)이 아이콘 · 첫 줄 · 동작을 한 가운데선에 세운다(D-528). 예전 격자는 `align-items: start` 라
           한 줄 글(24px) 옆 30px 단추가 3 ~ 5px 내려가 「목록 보기」가 글보다 아래에 따로 섰다. 동작은 언제나 오른쪽 끝이고
           30 이다 - 화면이 34 단추를 넘겨도 이 상자 안에서는 30 으로 선다(한 줄은 한 밀도, D-526).
           여백은 좌우 14 · 위아래 12(compact 10 · 7). 높이는 동작이 있으면 56(compact 46), 없으면 50. 바깥 여백은 이 상자가
           갖지 않는다 - 흐름 그릇이 형제 사이 간격을 주고, 흐름 밖에서는 아래 `k-callout` 형제 규칙 하나가 준다(styles/kit.css). */
        px: compact ? 1.25 : 1.75,
        py: compact ? 0.875 : 1.5,
        borderRadius: `${RADIUS.sm}px`,
        border: `1px solid ${t.palette.divider}`,
        bgcolor: "background.inset",
        fontSize: compact ? FONT_SIZE.caption : FONT_SIZE.body,
        lineHeight: compact ? LINE_HEIGHT.caption : LINE_HEIGHT.body,
        ...KO_WORD_BREAK,
        "& .k-head-action .MuiButton-root": {
          minHeight: remPx(CONTROL.controlDense), height: remPx(CONTROL.controlDense), py: 0,
        },
        /* `variant="bleed"` — 판 밖 전폭 띠(대리 보기 · 상태 알림 · 팔레트의 실패 줄). 같은 1a
           얼굴에서 모서리와 좌우 · 위 선만 걷고 아래 실선으로 본문과 가른다. 화면마다 손으로
           `borderRadius: 0` 을 적던 자리를 이름 하나로 모은다. */
        ...(variant === "bleed" ? { borderRadius: 0, borderInline: 0, borderBlockStart: 0 } : null),
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
    >
      <HeadRow
        gap={compact ? 1 : 1.25}
        lineHeightPx={compact ? 13 * LINE_HEIGHT.caption : 15 * LINE_HEIGHT.body}
        leadPx={ICON.mark}
        actionPx={CONTROL.controlDense}
        /* 아이콘은 색만 상태를 말하는 **유일한** 자리이고, 그래서 이것만은 `aria-hidden` 이 아니다: 모양이 나르는 뜻을
           낭독기에도 같은 낱말로 준다. */
        lead={(
          <Icon
            role="img"
            aria-label={toneWord}
            sx={{ display: "block", flexShrink: 0, fontSize: remPx(ICON.mark), color: `${paletteKey}.main` }}
          />
        )}
        action={action || null}
      >
        <Box sx={{ minWidth: 0, display: "grid", rowGap: 0.25 }}>
          {/* 제목은 **호출부가 줄 때만** 선다. 안 주면 본문이 곧 그 상자의 말이다. */}
          {title ? (
            <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, color: "text.primary" }}>
              {title}
            </Box>
          ) : null}
          {/* 제목이 있으면 본문은 보조 잉크다 — 둘의 색이 갈려야 한 덩어리로 안 뭉친다.
              제목이 없으면 본문이 그 상자의 유일한 말이므로 본문 잉크로 선다.
              상태별 색 변화는 없다(그것은 아이콘의 일이다). 본문 아래 목록(`ul`)은 글 칸 시작점에 선다(RULES §1). */}
          <Box
            component="span"
            className="k-callout-body"
            sx={{
              minWidth: 0, color: title ? "text.secondary" : "text.primary",
              "& ul": { mt: 0.75, mb: 0, pl: 2.5 }, "& li + li": { mt: 0.5 },
            }}
          >
            {children}
          </Box>
          <TechDetail label={detailLabel}>{detail}</TechDetail>
        </Box>
      </HeadRow>
    </Box>
  );
}


/* 판독 줄(`MetricStrip`)은 걷었다 — 핸드오프 RULES §6 「판독 줄(dl 형태 KPI 나열)은 쓰지 않는다」. 데이터의 뜻에 따라
 * 상태 구성은 `StatusSummaryCard`, 독립 측정값은 `StatusKpiStrip`, 값 하나는 큰 숫자, 속성은 아래 `MetaBar` 가 맡는다
 * (계획 표 7). 마지막 소비처였던 문서 목록의 요약 넷은 보기 전환 세그먼티드의 건수가 됐다(계획 D). */

/* 속성 줄 — 상세 화면 맨 위의 전폭 메타 (지시 7).
 *
 * 걷어 낸 판독 줄(`MetricStrip`)과 판 모양은 같았지만 **읽는 순서가 반대**다: 지표는 숫자를 먼저 보고 그게
 * 무엇인지 확인하지만, 속성은 "마감이 언제지"처럼 **찾는 이름이 먼저** 있다. 그래서 라벨이
 * 위, 값이 아래다. 값도 지표처럼 크게 내지 않는다 — 여기서 큰 글자는 본문 몫이다.
 * 하나에 두 역할을 겸하게 하지 않고 따로 둔다(지시 57).
 *
 * 왜 위인가: 예전에는 속성이 오른쪽 레일 맨 위에 있었고 첨부는 본문 아래였다. 그래서
 * 본문을 읽다가 마감을 확인하려면 시선이 화면 오른쪽 끝까지 갔다가 돌아와야 했고, 첨부는
 * 본문이 길면 화면 밖으로 밀렸다. 속성은 훑는 정보라 한 줄로 위에 눕히는 편이 짧고,
 * 그 자리를 비워 준 레일은 본문과 나란히 읽는 것(첨부·댓글)이 갖는다.
 *
 * items: `{ key, label, value, type }[]` — `null`/`false` 는 걸러 낸다.
 *
 * ## 폭은 균등이 아니다 (C3 · W6)
 *
 * 예전에는 모든 칸이 `flex: 1 1 9rem` 이었다 — 「높음」 두 글자와 「ClovirAssist 플랫폼
 * 전환」 열두 글자가 **같은 폭**을 받고, 화면이 넓어지면 둘 다 같이 늘어난다. 그래서 넓은
 * 화면일수록 속성 사이가 벌어져 훑는 데 시선이 더 많이 움직였다(지시 75).
 *
 * 이제 칸이 표의 열과 **같은 어휘**로 자기 성질을 말한다. 이름·제목형은 남는 폭을 가져가고
 * (`grow`), 닫힌 집합·수치·날짜는 자기 내용 폭만 쓴다. `type` 을 안 준 칸은 예전과 같이
 * 균등하게 늘어난다 — 배선하지 않은 화면의 렌더는 안 바뀐다.
 */
const META_GROW_TYPES = ["title", "name", "text", "identifier"];

/* 칸 사이 실선. 세 속성으로 적어야 실제로 그려진다(F-W2R-01). */
const META_DIVIDERS = (t) => ({
  "& > *:not(:first-of-type)": {
    borderInlineStartStyle: "solid",
    borderInlineStartWidth: "1px",
    borderInlineStartColor: t.palette.divider,
  },
});

/** 먼저 판단할 값들 — 라벨 위, 값 아래. 훑는 단위가 «속성 하나» 다. */
function MetaPrimaryRow({ list }) {
  const flexOf = (it) => {
    if (!it.type) return "1 1 9rem";                         // 선언 안 한 칸 — 옛 동작 그대로
    if (META_GROW_TYPES.indexOf(it.type) >= 0) return "1 1 12rem";
    return "0 0 auto";                                       // 상태·수치·날짜는 내용 폭만
  };
  return (
    <Box sx={(t) => ({ display: "flex", flexWrap: "wrap", ...META_DIVIDERS(t) })}>
      {list.map((it, i) => (
        <Box
          key={it.key || it.label || i}
          className="k-metacell"
          data-meta-type={it.type || undefined}
          data-meta-rank="primary"
          sx={{ flex: flexOf(it), maxWidth: "20rem", minWidth: 0, px: 2, py: 1.25, display: "grid", gap: 0.25, alignContent: "start" }}
        >
          <Typography component="div" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
            {it.label}
          </Typography>
          <Box sx={{ fontSize: FONT_SIZE.body, color: "text.primary", minWidth: 0, ...KO_WORD_BREAK,
                     ...(it.type && resolveColumn(it).numeric ? NUMERIC : null) }}>
            {it.value == null || it.value === "" ? "-" : it.value}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

/** 참조용 값들 — 라벨과 값이 한 줄에 붙는 압축 띠. 찾을 때만 읽는다. */
function MetaSecondaryRow({ list, bare = false }) {
  return (
    <Box sx={(t) => ({
      display: "flex", flexWrap: "wrap", alignItems: "baseline",
      /* 위 줄과 갈라 놓는 실선 하나. 상자를 만들지 않는다 — 보조 정보에 컨테이너를 주면
         그것이 다시 «판» 이 되고, 판이 둘이면 무엇이 위인지 알 수 없다. 띠 하나만 서면(`bare`) 위 줄이 없어 선도 없다. */
      ...(bare ? null : { borderTop: 1, borderColor: "divider", mt: 0.25, pt: 0.75 }),
      ...META_DIVIDERS(t),
      /* 띠 하나만 서면 첫 칸의 이름이 위 줄의 글과 같은 시작점에 선다(칸 사이 여백은 둘째 칸부터다). */
      ...(bare ? { "& > :first-of-type": { pl: 0 } } : null),
    })}>
      {list.map((it, i) => (
        <Box
          key={it.key || it.label || i}
          className="k-metacell"
          data-meta-type={it.type || undefined}
          data-meta-rank="secondary"
          sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0, px: 2, py: 0.5 }}
        >
          <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", whiteSpace: "nowrap" }}>
            {it.label}
          </Typography>
          <Box component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.primary", minWidth: 0, ...KO_WORD_BREAK,
                     ...(it.type && resolveColumn(it).numeric ? NUMERIC : null) }}>
            {it.value == null || it.value === "" ? "-" : it.value}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

export function MetaBar({ items, ariaLabel, sx, strip = false }) {
  const list = (items || []).filter(Boolean);
  if (!list.length) return null;
  /* `strip` — 모든 칸이 압축 띠(이름과 값이 한 줄에 붙는다) 한 줄이다. 짧은 상태 면(높이 상한 약 120px, F7)처럼 속성을 읽기만
     하는 자리가 쓴다 — 이름 위 · 값 아래 칸은 줄마다 두 줄을 먹어, AI 연결 상태 면이 190px 가 되고 첫 폼 칸이 1366 첫 화면 기준
     (420px)을 넘었다(P17V). */
  if (strip) {
    return (
      <Box className="k-metabar" role="group" aria-label={ariaLabel} data-meta-strip="true" sx={sx}>
        <MetaSecondaryRow list={list} bare />
      </Box>
    );
  }
  /* ## 위계는 폭이 아니라 **무게**다 (C9 · R-90 · 지시 75)
   *
   * S16 이 칸의 **폭**을 고쳤다 — 「높음」 두 글자와 긴 프로젝트 이름이 같은 폭을 받지
   * 않는다. 그런데 폭을 고쳐도 남는 문제가 있었다: 아홉 개 속성이 **전부 같은 무게**로
   * 한 줄에 늘어서서, 티켓을 열었을 때 먼저 봐야 하는 「상태·담당자·마감」과 지원 문의
   * 때나 부르는 「티켓 번호」가 시각적으로 구별되지 않았다. 4K 에서는 그 줄이 2,880px 라
   * 아홉 칸을 다 훑어야 원하는 값을 찾는다.
   *
   * 그래서 화면이 `rank: "primary"` 로 **먼저 판단할 값**을 선언한다. 선언한 것만 라벨 위·값
   * 아래의 속성 묶음으로 서고, 나머지는 아래 줄의 압축 띠로 내려간다(라벨과 값이 한 줄에
   * 붙는다). `rank` 를 아무 칸도 선언하지 않은 호출부의 렌더는 **안 바뀐다** — 표의 열에
   * `type` 을 안 준 화면이 그대로인 것과 같은 규칙이다(호출부가 적은 값이 이긴다).
   *
   * 모든 속성을 Card/Badge 로 만들지 않는다. 위쪽은 Property Group, 아래쪽은 Compact Strip
   * 이고 둘 다 컨테이너가 없다 — 판독 줄과 같은 판정을 받는다(**속성 줄에 plate 금지**).
   */
  const primary = list.filter((it) => it.rank === "primary");
  const secondary = list.filter((it) => it.rank !== "primary");
  const ranked = primary.length > 0 && secondary.length > 0;
  return (
    <Box
      className="k-metabar"
      role="group"
      aria-label={ariaLabel}
      data-meta-ranked={ranked ? "true" : undefined}
      sx={(t) => ({
        display: ranked ? "grid" : "flex",
        ...(ranked ? null : { flexWrap: "wrap", ...META_DIVIDERS(t) }),
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
    >
      {ranked ? (
        <>
          <MetaPrimaryRow list={primary} />
          <MetaSecondaryRow list={secondary} />
        </>
      ) : (
        /* 선언이 없거나 한쪽뿐이면 예전처럼 한 줄이다. 위계가 없는 것을 있는 척하지 않는다. */
        list.map((it, i) => (
          <Box
            key={it.key || it.label || i}
            className="k-metacell"
            data-meta-type={it.type || undefined}
            sx={{
              flex: !it.type ? "1 1 9rem" : (META_GROW_TYPES.indexOf(it.type) >= 0 ? "1 1 12rem" : "0 0 auto"),
              maxWidth: "20rem", minWidth: 0, px: 2, py: 1.25, display: "grid", gap: 0.25, alignContent: "start",
            }}
          >
            <Typography component="div" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
              {it.label}
            </Typography>
            <Box sx={{ fontSize: FONT_SIZE.body, color: "text.primary", minWidth: 0, ...KO_WORD_BREAK,
                       ...(it.type && resolveColumn(it).numeric ? NUMERIC : null) }}>
              {it.value == null || it.value === "" ? "-" : it.value}
            </Box>
          </Box>
        ))
      )}
    </Box>
  );
}

/* 로딩 자리표시자 — **들어올 것의 모양**을 한다 (지시 20).
 *
 * 예전에는 어느 화면에서나 회색 줄 N개였다. 표가 들어올 자리에도, 지표 줄이 들어올 자리에도
 * 같은 줄무늬가 그려지니 화면이 무엇을 준비 중인지 알 수 없었고, 실제 내용이 도착하는 순간
 * 배치가 통째로 튀었다(자리표시자가 자리를 안 잡아 준다는 뜻이다).
 *
 * 모양은 넷이다. 다섯째(버튼)는 `Button` 의 `loading` 이 이미 맡는다 - 버튼 자리에 회색 알약을
 * 그리면 그 버튼이 사라진 것처럼 보인다.
 *
 *   `section` (기본) 구역 안 본문. 예전 동작 그대로 - `lines` 로 줄 수를 준다.
 *   `page`          화면 전체. 제목 줄 + 판독값 줄 + 본문 판. 셸이 이미 그린 자리를 흉내 낸다.
 *   `table`         표. 머리행 + 행들. `cols` 만큼 칸을 나눠 열 리듬까지 맞춘다.
 *   `chart`         그림. 바닥선 위에 높이가 다른 막대들 + 범례 줄. `height` 로 높이를 준다.
 *
 * `chart` 가 필요한 이유 (PLAN «빈 데이터 규칙» ⓐ): 그림이 들어올 자리에 회색 줄 여덟 개를
 * 그리면 「불러오는 중」과 「값이 없다」가 **같아 보인다.** 값이 없을 때 그림은 이제 통째로
 * 접히므로(`charts/base.jsx::ChartNoData`), 로딩 자리가 같은 높이의 **차트 모양**이라야
 * 그 둘이 구별된다. 점선 상자가 아니다 — 점선 상자는 폐기한 그 형태다.
 *
 * 스켈레톤 자체는 장식(aria-hidden)이라 스크린리더엔 침묵이다 - 별도 live 노드로 낭독한다.
 */
/* 늦게 드러내기 — 뼈대가 빠른 응답에 번쩍였다 사라지지 않게 300ms 뒤에 보인다(D-530). 자리는 처음부터 차지해 내용이 들어와도
   높이가 튀지 않는다. 시간은 CSS 애니메이션 지연이 잰다(타이머 · 상태가 없다). */
const REVEAL = keyframes`from { opacity: 0; } to { opacity: 1; }`;

export function DelayedReveal({ children, delayMs = 300 }) {
  return (
    <Box data-delayed-reveal="" sx={{ animation: `${REVEAL} 1ms linear ${delayMs}ms both` }}>
      {children}
    </Box>
  );
}

export function Skeleton({ kind = "section", lines = 3, rows = 5, cols = 4, height = "9rem" }) {
  const live = <span className="sr-only" aria-live="polite">불러오는 중…</span>;

  if (kind === "chart") {
    /* 막대 높이는 고정 배열이다 — 무작위로 흔들면 다시 그릴 때마다 모양이 바뀌어
       «데이터가 들어오는 중» 이 아니라 «무언가 움직인다» 로 읽힌다. */
    const bars = [62, 88, 45, 74, 96, 58, 81];
    return (
      <>
        {live}
        <Box aria-hidden="true" className="k-skeleton-chart" sx={{ display: "grid", gap: 1, py: 1 }}>
          <Box sx={{
            height, display: "flex", alignItems: "flex-end", gap: 1.5,
            borderBottom: 1, borderColor: "divider", px: 0.5,
          }}>
            {bars.map((h, i) => (
              <MuiSkeleton key={i} variant="rounded" sx={{ flex: 1, minWidth: 0 }} height={`${h}%`} />
            ))}
          </Box>
          {/* 범례 줄 — 이 제품의 그림은 언제나 숫자를 글자로 함께 낸다(charts/base.jsx §2). */}
          <Box sx={{ display: "flex", gap: 2 }}>
            <MuiSkeleton variant="rounded" height={12} width="6rem" />
            <MuiSkeleton variant="rounded" height={12} width="4.5rem" />
          </Box>
        </Box>
      </>
    );
  }

  if (kind === "table") {
    const count = Math.max(1, cols);
    return (
      <>
        {live}
        <Box aria-hidden="true" className="k-skeleton-table" sx={{ px: 2, py: 1.5 }}>
          {Array.from({ length: Math.max(1, rows) + 1 }).map((_, r) => (
            <Box
              key={r}
              sx={{
                display: "grid", gap: 2, alignItems: "center",
                gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))`,
                py: 1.25,
                borderBottom: r === 0 ? 1 : 0, borderColor: "divider",
              }}
            >
              {Array.from({ length: count }).map((__, c) => (
                <MuiSkeleton
                  key={c} variant="rounded" height={r === 0 ? 12 : 16}
                  /* 열마다 폭을 조금씩 달리한다 - 모든 칸이 같은 길이면 표가 아니라 격자로
                     보인다. 실제 표의 값 길이가 열마다 다르다는 사실을 흉내 낸다. */
                  width={r === 0 ? "55%" : ["85%", "70%", "60%", "45%"][c % 4]}
                />
              ))}
            </Box>
          ))}
        </Box>
      </>
    );
  }

  if (kind === "page") {
    return (
      <>
        {live}
        <Box aria-hidden="true" className="k-skeleton-page" sx={{ display: "grid", gap: 2.5, py: 1 }}>
          <Box sx={{ display: "grid", gap: 1 }}>
            <MuiSkeleton variant="rounded" height={12} width="8rem" />
            <MuiSkeleton variant="rounded" height={26} width="min(22rem, 60%)" />
          </Box>
          <MuiSkeleton variant="rounded" height={76} />
          <Box sx={{ display: "grid", gap: 1.5 }}>
            {Array.from({ length: Math.max(1, lines) }).map((_, i) => (
              <MuiSkeleton key={i} variant="rounded" height={18} />
            ))}
          </Box>
        </Box>
      </>
    );
  }

  return (
    <>
      {live}
      <Box aria-hidden="true" sx={{ display: "grid", gap: 1.5, py: 1 }}>
        {Array.from({ length: Math.max(1, lines) }).map((_, i) => (
          <MuiSkeleton key={i} variant="rounded" height={18} />
        ))}
      </Box>
    </>
  );
}

/* 빈 화면 — 아이콘+제목만 두지 않고 "지금 무엇을 하면 되는지"를 설명한다(§9).
 * 하위호환: 기존 호출부의 {icon,title,help,action}은 그대로 동작한다.
 * 추가 prop:
 *   art — 일러스트 키(lib/assets.js의 ART). 자산 12종이 처음부터 있었는데 어디에도
 *         연결돼 있지 않았다. 좁은 화면에서는 세로 공간을 아끼려고 숨긴다.
 *   size="compact" — 팝오버·모달 하위목록·사이드바처럼 세로/가로가 제약된 맥락용(DS-14/15).
 *         일러스트를 아예 빼고 여백·글자를 줄인다. 기본(undefined)은 전체 페이지 크기 그대로.
 */
/* ── 0건의 **두 얼굴** (PLAN C1 · 지시 0-2.17) ─────────────────────────────
 *
 * 「데이터가 아예 없다」와 「필터 때문에 0건이다」는 **다른 사실**이고, 사용자가 다음에 할
 * 일도 다르다 — 앞의 것은 «만들어야» 하고 뒤의 것은 «조건을 풀어야» 한다. 같은 문장으로
 * 말하면 신규 설치는 존재하지 않는 데이터를 찾아 헤매고, 필터를 건 사람은 자기가 건 조건을
 * 잊는다.
 *
 * 실측(W5 조사 F-W5D-122): 이 분기가 제품 안에 **여섯 벌**로 갈라져 있었고 문구·복구 수단이
 * 제각각이었다 — 셋(`/chat-rooms`·조직도·대화 목록)은 조건을 푸는 **버튼이 아예 없었고**,
 * `/projects` 는 분기 자체가 없어 부서 필터로 0건이 된 화면을 「프로젝트가 없습니다」라고
 * 말했다. 반대로 `/offboarding` 은 검색어가 없어도 언제나 「조건에 해당하는…」이라고 했다.
 *
 * 그래서 **필터 갈래만** 이 부품이 소유한다. 「정말 없다」 갈래는 화면마다 안내가 다른 것이
 * 정상이라(온보딩 문구·권한별 CTA) `EmptyState` 의 props 를 그대로 흘려보낸다.
 */
export function ListEmptyState({
  filtered, onClear, clearLabel = "필터 지우기", filteredTitle, filteredHelp, ...rest
}) {
  if (!filtered) return <EmptyState {...rest} />;
  return (
    <EmptyState
      size={rest.size}
      layout={rest.layout}
      title={filteredTitle || "조건에 맞는 항목이 없습니다"}
      /* 「없다」로 끝내지 않는다 — 무엇을 하면 되는지까지가 빈 상태다(지시 18). */
      help={filteredHelp || "지금 걸린 조건에 맞는 항목이 없습니다. 조건을 지우면 전체를 볼 수 있습니다."}
      /* 조건 0건의 지우기는 **30 보조 단추**다(RULES §1 「30px 조건 지우기」 · 조합 계약 C-4). 채움이었을 때 문서 ·
         프로젝트 · DataScreen 은 머리의 「새 문서」 같은 채움과 한 화면에 채움 둘을 세웠다. */
      action={onClear ? <Button size="sm" onClick={onClear}>{clearLabel}</Button> : null}
    />
  );
}

/* 준비물·절차·기대 결과 — 「이 화면을 쓰려면 무엇이 먼저인가」를 말하는 세 줄.
 *
 * 예전에는 `EmptyState` 안에만 있었다. 그래서 목록 화면의 절차 산문이 **빈 상태에서만**
 * 보였고(대리 보기 화면의 여섯 줄 절차), 사용자 화면의 빈 상태(제목 + 한 문장 + 동작)와
 * 모양이 달랐다. 이제 같은 부품을 제목 옆 `?` 도움말이 쓴다(D-456) — 빈 상태는 짧아지고,
 * 절차는 목록이 차 있어도 읽을 수 있다. 셋 다 비면 아무것도 그리지 않는다.
 *
 *   rule  위에 실선 하나를 긋는다(문장형 도움말 아래에 붙을 때). 상자는 만들지 않는다. */
export function GuidanceBlock({ prerequisite, steps, expected, rule = true, sx }) {
  const stepList = Array.isArray(steps) ? steps.filter((s) => s != null && s !== "") : null;
  if (![prerequisite, stepList && stepList.length, expected].some(Boolean)) return null;
  const bodySx = { maxWidth: `${EMPTY_STATE_MAX_CH}ch`, fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK };
  return (
    <Box
      data-guidance=""
      sx={{
        display: "grid", gap: 0.5, textAlign: "left",
        ...(rule ? { mt: 0.5, pt: 1, borderTop: 1, borderColor: "divider" } : null),
        ...sx,
      }}
    >
      {prerequisite ? (
        <Typography color="text.secondary" sx={bodySx}>
          <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, mr: 1 }}>필요한 것</Box>{prerequisite}
        </Typography>
      ) : null}
      {stepList && stepList.length ? (
        <Box
          component="ol"
          sx={{ m: 0, pl: 2.5, color: "text.secondary", fontSize: FONT_SIZE.bodySm, display: "grid", gap: 0.25, maxWidth: `${EMPTY_STATE_MAX_CH}ch`, ...KO_WORD_BREAK }}
        >
          {stepList.map((s, i) => <li key={i}>{s}</li>)}
        </Box>
      ) : null}
      {expected ? (
        <Typography color="text.secondary" sx={bodySx}>
          <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, mr: 1 }}>기대 결과</Box>{expected}
        </Typography>
      ) : null}
    </Box>
  );
}

/* 다크 모드의 클로비 바탕 — 빈 상태 · 오류 상태 그림은 밝은 바탕을 기준으로 그린 자산이라 다크에서는 **함몰면
   (#1C2136) 위에 그대로 놓는다**(핸드오프 README 다크 모드 절 · RULES §13 · 다크 시안 「빈 상태」, 색 반전 · 필터는 쓰지
   않는다). 치수는 두 모드가 같아야 하므로(RULES §13) 여백은 그대로 두고 면 · 모서리 · 안쪽 선만 칠한다 — 선은 상자 안쪽
   그림자라 크기에 들어가지 않는다. 라이트는 칠하지 않는다(공통 컴포넌트 시안의 판 안 빈 상태는 면이 없다).
   그림이 없는 빈 상태(조건 0건 · 좁은 자리)는 바탕을 받지 않는다 — 이 면은 그림을 위한 것이다. */
function mascotGroundSx(theme) {
  if (theme.palette.mode !== "dark") return null;
  return {
    bgcolor: "background.inset",
    borderRadius: `${RADIUS.sm}px`,
    boxShadow: `inset 0 0 0 1px ${theme.palette.divider}`,
  };
}

/** `EmptyState` 가 실제로 받는 prop 전체 — 아래 개발 모드 검사의 정본이다. */
const EMPTY_STATE_PROPS = [
  "icon", "title", "help", "situation", "prerequisite", "steps", "expected",
  "action", "relatedLink", "art", "size", "layout",
];

export function EmptyState(props) {
  const {
    icon = null, title = "표시할 항목이 없습니다", help, situation, prerequisite,
    steps, expected, action, relatedLink, art, size, layout = "region",
    ...rest
  } = props;
  const band = React.useContext(TableEmptyBandCtx);
  /* 🔴 **모르는 prop 은 개발 모드에서 조용히 사라지지 않는다** (A2 · RC2).
   *
   * `screens/Sprint.jsx` 가 이 컴포넌트에 없는 `hint` 를 넘겼는데, 구조 분해는 목록에
   * 없는 키를 그냥 버린다 — 화면은 "안내 문장을 줬다"고 믿고, 실제로는 그 문장이 통째로
   * 없어져 회차 0건일 때 빈 상태가 **아무 문장도 없이** 한 줄로만 떴다(§3 A2 실측).
   * 「선언은 있는데 화면에는 없다」는 이 계약이 처음이 아니다 — 여기서는 조용히 넘어가지
   * 않고 개발 모드에서 바로 멈춘다. 프로덕션 빌드는 `import.meta.env.DEV` 가 정적으로
   * `false` 라 이 블록 자체가 번들에서 제거된다(트리 셰이킹) — 실사용자 화면은 안 죽는다. */
  if (import.meta.env.DEV) {
    const unknown = Object.keys(rest);
    if (unknown.length) {
      throw new Error(
        `EmptyState: 모르는 prop [${unknown.join(", ")}] 을 받았다. 이 컴포넌트가 받는 것은 ` +
        `[${EMPTY_STATE_PROPS.join(", ")}] 뿐이다. 오타이거나, 이 요구를 표현하려면 ` +
        `기존 prop(help/action 등)으로 옮겨야 한다.`,
      );
    }
  }
  /* 표 안이면 어떤 자리를 말했든 한 줄 띠다(위 `TableEmptyBandCtx`). 그림 · 절차는 그리지 않는다. */
  if (band || layout === "band") {
    return (
      <EmptyBand
        title={title} help={situation || help} action={action} relatedLink={relatedLink}
        icon={typeof icon === "string" ? null : icon} inset={!!(band && band.inset)}
      />
    );
  }
  /* `layout` — **이 빈 상태가 무엇을 대신하는가** (PLAN «C1»).
   *
   *   page    **화면 전체가 비었다.** 콘텐츠 영역 안에서 가운데 구성으로 선다 —
   *           클로비 → 제목 → 짧은 설명 → (필요하면) 다음 행동, 위에서 아래로.
   *   card    **그 화면의 주요 판 하나가 비었다.** `page` 와 같은 세로 가운데 구성인데,
   *           높이를 스스로 만들지 않고 **부모 판이 이미 가진 높이를 채운다**. 카드가
   *           안정적인 높이 범위를 갖는 자리(홈의 「오늘 마감」)에서, 0건이 «작은 그림과
   *           한 줄이 왼쪽 위에 몰리고 나머지가 빈 흰 판» 이 되지 않게 한다.
   *   region  **판·카드 하나가 비었다**(기본). 그 카드의 문맥 안에 왼쪽으로 붙는다 —
   *           대시보드의 칸 하나가 비었을 때 그 칸만 조용히 비어 있으면 된다.
   *   inline  팝오버·모달 하위목록처럼 폭도 높이도 좁은 자리. `size="compact"` 와 같은 뜻이다.
   *
   * 🔴 **자리마다 다르게 그리는 이유** (S19). 예전에는 `page` 를 아무 화면도 안 썼다 —
   * 선언만 있고 배선이 없으면 그 자리는 존재하지 않는 것과 같다. 그래서 화면 전체가 빈
   * 상태(승인·놀이·검색·옛 문서 주소)가 전부 `region` 으로 그려졌고, 큰 빈 화면의
   * **왼쪽 위 구석에 작은 그림과 한 줄**만 놓여 화면이 미완성처럼 보였다. 카드 안의 빈
   * 상태는 그대로 둔다 — 거기서는 왼쪽 정렬이 맞다(그 카드의 다른 내용과 같은 축이다).
   *
   * 크기(`size`)와 자리(`layout`)를 따로 두는 이유: 좁은 팝오버 안의 빈 상태와 4K 전면의
   * 빈 상태는 **글자 크기**가 아니라 **놓이는 방식**이 다르다. 한 prop 에 둘을 겹치면
   * "작게" 와 "가운데" 를 따로 고를 수 없다. */
  const compact = size === "compact" || layout === "inline";
  /* 화면 전체가 빈 자리. 이 하나가 방향(세로)·정렬(가운데)·높이(남은 화면)를 함께 정한다 —
     화면마다 크기와 자리를 따로 적으면 같은 상태가 화면마다 다르게 보인다. */
  const page = layout === "page";
  /* 판 하나를 채우는 가운데 배치. `page` 와 **모양은 같고 높이의 출처만 다르다** — 여기서는
     부모 판이 높이를 정하고 이 빈 상태는 그 안에서 가운데에 선다. 그래서 `minHeight` 를
     스스로 만들지 않는다(만들면 판의 높이 계약을 빈 상태가 덮어쓴다). */
  const card = layout === "card";
  const centered = page || card;
  /* compact 는 여전히 그림을 안 그린다(DS-15). 팝오버·모달 하위목록은 폭도 높이도 좁아서
     그림이 «다음에 무엇을 하면 되는지» 를 밀어낸다. 그 자리에 캐릭터가 필요한 화면은
     `icon` 으로 직접 넘긴다 — `ResultsRail` 이 그렇게 하고 그 포즈는 `emptyCompact` 밴드다. */
  const artSrc = !compact && art && ART[art] ? ART[art] : null;
  /* 그림 크기는 «보이는 캐릭터» 에서 파생한다 (지시 71 · `Mascot.jsx::MASCOT_PLACE`).
     예전에는 `width: {sm:72, xxl:88, uhd:112}` 였는데, 그 72 는 자산마다 다른 크기로 보였다 —
     `empty-notify`(잉크 84%)는 60px 인데 `empty-tickets`(62%)는 45px 였다. 같은 자리에서
     그림이 두 크기로 나오는 것이고, 박스를 재는 검사로는 안 보인다. */
  const artPlace = page ? "emptyPage" : card ? "emptyCard" : "emptyRegion";
  const artBox = artSrc ? mascotBoxSx(artPlace, artSrc) : null;
  /* 칸 폭은 EMPTY_STATE_MAX_CH. 문구 한도는 COPY_LIMIT.emptyHelp — 폭을 바꾸면 한도가 따라간다. */
  const bodySx = {
    maxWidth: `${EMPTY_STATE_MAX_CH}ch`,
    fontSize: compact ? FONT_SIZE.bodySm : FONT_SIZE.body,
    ...KO_WORD_BREAK,
    ...(centered ? { mx: "auto" } : null),
  };

  /* 빈 상태 — 읽는 순서가 **제목 → 다음 행동 → 보조 설명**이다 (지시 18).
   *
   * 예전에는 일러스트가 맨 위에 160~320px 로 오고, 그 아래 설명이 쌓이고, 정작 다음
   * 행동(action)은 맨 끝에 있었다. 4K 에서 세로 450px 를 마스코트가 차지해 "내 티켓이
   * 왜 비었지"보다 "그림이 크다"가 먼저 읽혔다.
   *
   * **클로비는 그대로 둔다.** 사용자가 "제품의 정체성"이라고 확정했다. 바뀌는 것은 크기와
   * 자리다 — 위가 아니라 옆, 화면을 채우는 크기가 아니라 표지 크기. 지시 18 의 실제 요구는
   * "캐릭터를 쓰지 말라"가 아니라 "빈 공간을 캐릭터로 때우지 말라"이고, 둘을 모두 만족하는
   * 답이 이 배치다.
   *
   * 가운데 정렬도 걷어냈다. 읽을 것이 두 줄을 넘으면 가운데 정렬은 매 줄 시작점이 달라져
   * 훑기 어렵다 — 왼쪽 정렬이 목록·표와도 같은 축을 쓴다(D-141 RAISE, mesophotic). */
  return (
    <Box
      className="k-empty"
      role="status"
      aria-live="polite"
      sx={(theme) => ({
        display: "flex", alignItems: "flex-start", gap: compact ? 1.5 : 2.5,
        py: compact ? 2 : 3.5, px: compact ? 1.5 : 2,
        /* page — 남은 높이를 실제로 차지하고 그 안에서 **가운데**에 선다. `minHeight` 는
           본문 열의 남은 높이를 겨냥한 값이고, 마스코트 밴드의 분모이기도 하다 — 그림이
           컨테이너 높이를 정하면 어떤 비율 규칙도 성립하지 않는다(`Mascot.jsx::emptyPage`). */
        ...(centered
          ? {
              flexDirection: "column", alignItems: "center", justifyContent: "center",
              textAlign: "center", gap: card ? 2 : 2.5, px: 3,
              // `page` 는 남은 화면을 실제로 차지한다. `card` 는 부모가 준 높이를 채운다 —
              // 자기 높이를 만들면 판의 높이 계약을 빈 상태가 덮어쓴다.
              // 높이는 창의 절반까지다(P11 캡처) — 60vh 였을 때 1366×768 에서 필터 줄이 두 줄로 접힌 목록(AI 호출 기록)은
              // 빈 화면인데도 문서가 창보다 53px 길어 스크롤이 생겼다. 1080 이상에서는 그대로 30rem 이다.
              ...(card ? { height: "100%", py: 4 } : { py: 6, minHeight: "min(30rem, 50vh)" }),
            }
          : null),
        ...(artSrc ? mascotGroundSx(theme) : null),
      })}
      data-empty-layout={layout}
    >
      {artSrc ? (
        <Box
          component="img" src={artSrc} alt="" aria-hidden="true" loading="lazy" decoding="async"
          /* 이 그림이 어느 밴드로 판정받는지를 **화면이 선언한다.** 선언이 없으면 프로브가
             DOM 모양으로 자리를 짐작하는데, 분류가 곧 판정이라 짐작이 틀리면 통과·실패가
             통째로 뒤집힌다. */
          data-mascot-context={MASCOT_PLACE[artPlace].context}
          sx={{
            display: { xs: "none", sm: "block" }, flexShrink: 0,
            ...artBox, objectFit: "contain",
          }}
        />
      ) : icon ? (
        <Box aria-hidden="true" sx={{ flexShrink: 0, fontSize: compact ? FONT_SIZE.pageTitle : FONT_SIZE.readout, color: "text.faint", lineHeight: 1 }}>{icon}</Box>
      ) : null}

      <Box sx={{ display: "grid", gap: compact ? 0.5 : 0.75, minWidth: 0, ...(centered ? { justifyItems: "center" } : null) }}>
        <Typography
          role="heading"
          aria-level={2}
          sx={{ fontWeight: FONT_WEIGHT.semibold, fontSize: compact ? FONT_SIZE.body : FONT_SIZE.title, ...KO_WORD_BREAK }}
        >
          {title}
        </Typography>

        {/* 한 줄 요약. 상황과 도움말이 둘 다 있으면 상황이 먼저다(무엇이 일어났는가). */}
        {situation ? <Typography color="text.secondary" sx={bodySx}>{situation}</Typography> : null}
        {help ? <Typography color="text.secondary" sx={bodySx}>{help}</Typography> : null}

        {/* 다음 행동이 설명보다 위에 온다. */}
        {action || (relatedLink && relatedLink.href) ? (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", mt: centered ? 1 : 0.25, justifyContent: centered ? "center" : "flex-start" }}>
            {action}
            {relatedLink && relatedLink.href ? (
              <Link href={relatedLink.href} underline="hover" sx={{ fontSize: compact ? FONT_SIZE.bodySm : FONT_SIZE.body }}>
                {relatedLink.label || "관련 화면으로"}
              </Link>
            ) : null}
          </Box>
        ) : null}

        {/* 준비물·절차·기대 결과는 보조다. 실선 하나로 아래에 붙인다(상자를 만들지 않는다).
            같은 부품을 제목 옆 `?` 도움말이 쓴다(D-456) — 목록 화면의 절차는 그쪽으로 갔다. */}
        <GuidanceBlock
          prerequisite={prerequisite} steps={steps} expected={expected}
          sx={{ justifySelf: centered ? "center" : "stretch", ...(centered ? { mx: "auto" } : null) }}
        />
      </Box>
    </Box>
  );
}

/* 표 안 빈 띠 (F4 · D-530) — [아이콘 16] [한 문장 + 짧은 도움말] [30 동작], 표의 왼쪽 축에 선다. 높이는 56 ~ 72 다(한 줄이면
   56, 도움말이 접혀도 두 줄). 판을 흰 면으로 채우지 않는다 — 머리는 그대로 서 있고, 그 아래 한 줄이 「왜 비었는지 · 무엇을 하면
   되는지」를 말한다. 큰 그림은 화면 전체가 빈 page 상태에서만 쓴다. */
const EMPTY_BAND_MIN_HEIGHT = remPx(56);

function EmptyBand({ title, help, action, relatedLink, icon, inset }) {
  return (
    <Box
      className="k-empty"
      role="status"
      aria-live="polite"
      data-empty-layout="band"
      sx={{
        display: "flex", alignItems: "center", flexWrap: "wrap", columnGap: 1.5, rowGap: 0.5,
        minHeight: EMPTY_BAND_MIN_HEIGHT, py: 1, px: inset ? 0 : 2,
      }}
    >
      <Box aria-hidden="true" sx={{ display: "inline-flex", flexShrink: 0, color: "text.secondary", "& svg": { fontSize: remPx(ICON.mark) } }}>
        {icon || <InfoOutlinedIcon />}
      </Box>
      <Box sx={{ minWidth: 0, flex: "1 1 16rem", display: "flex", flexWrap: "wrap", alignItems: "baseline", columnGap: 1 }}>
        <Typography role="heading" aria-level={2} sx={{ fontWeight: FONT_WEIGHT.semibold, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}>
          {title}
        </Typography>
        {help ? <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }}>{help}</Typography> : null}
      </Box>
      {action || (relatedLink && relatedLink.href) ? (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexShrink: 0 }}>
          {action}
          {relatedLink && relatedLink.href ? (
            <Link href={relatedLink.href} underline="hover" sx={{ fontSize: FONT_SIZE.bodySm }}>{relatedLink.label || "관련 화면으로"}</Link>
          ) : null}
        </Box>
      ) : null}
    </Box>
  );
}

/* 429 의 두 부류를 가르는 경계(초). 앱 리미터의 retry_after 는 「토큰 하나 회복 시간」이라
 * 구조적으로 12초 이내이고(login 6s · chat 2s · game_ai 12s · narrate 5s), AI 사용 상한은
 * 자정·월초까지라 시간~월 단위다. 코드가 둘 다 rate_limited 여서 시간으로만 가를 수 있다. */
const RATE_LIMIT_COUNTDOWN_MAX_S = 300;

/* size="compact" — EmptyState와 같은 이유(DS-15): 팝오버·모달 하위목록처럼 폭이 좁은 맥락에서
 * 일러스트를 빼고 여백·글자를 줄인다. 예전엔 이 크기 차이를 소비 측 CSS(global.css 등)가
 * `.noti-pop-error .k-empty { padding:... }` 식으로 소유권 밖에서 되짚어 맞췄다 — 컴포넌트가
 * 직접 size를 받으면 그 특이도 전쟁 CSS가 필요 없어진다. */
/* `layout` — **이 오류가 무엇을 대신하는가**. `EmptyState` 와 같은 어휘를 쓴다.
 *
 * 🔴 기본값이 `page` 인 이유. 이 부품의 호출부 87곳은 대부분 **라우트 전체**가 실패한
 * 자리다(`if (q.isError) return <ErrorState …/>`). 거기서는 가운데가 맞다. 그런데
 * `EmptyState` 와 달리 이 부품에는 자리를 말할 축이 **아예 없어서**, 판 하나가 실패한
 * 자리(문서 목록·댓글·채팅방 목록)까지 전면 오류의 크기와 정렬로 그려졌다 — 카드 안에서
 * 홀로 가운데 정렬된 채 위아래로 96px 씩 벌어진다. 축을 만들고 기본값은 지금 동작으로 둔다:
 * 87곳을 한 번에 뒤집는 것은 이 회차의 일이 아니다. 판 안의 호출부는 `layout="region"` 을
 * 적는다. */
const ERROR_STATE_LAYOUTS = ["page", "card", "region", "inline"];

/* `error.kind` 두 갈래는 **요청 실패가 아니라 화면 실패**다(셸의 본문 경계가 준다 — `App.jsx`).
 *   render  화면을 그리는 코드가 예외를 던졌다. 서버와 무관하다
 *   chunk   화면 코드를 담은 파일을 못 받았다. 거의 언제나 **그 사이 새 버전이 배포**돼 옛 파일이
 *           사라진 경우다 — 다시 시도가 아니라 새로고침이 답이다
 * `secondaryAction` — 주 동작 옆의 보조 동작 하나(렌더 실패의 「새로고침」).
 * `retryLabel` — 「다시 시도」가 실제로 하는 일이 다를 때의 이름(되감을 수 없는 셸 경계는 「새로고침」). */
/* 자리를 안 말하면 **담는 쪽**이 정한다(위 `StateRegionCtx`, D-530) — 판 · 탭 판 · 모달 안이면 region, 화면 본문에 바로 서면 page 다.
   `title` · `help` · `action` 은 그 자리가 더 정확한 말을 아는 때(목록 상태 일곱 갈래 — `ListStateView`)에만 준다. */
export function ErrorState({
  error, onRetry, size, layout: layoutProp, secondaryAction, retryLabel = "다시 시도",
  title: titleProp, help: helpProp, action: actionProp,
}) {
  const inRegion = React.useContext(StateRegionCtx);
  const layout = layoutProp || (inRegion ? "region" : "page");
  /* 모르는 크기 · 자리는 개발 모드에서 멈춘다 — `size="sm"` 은 조용히 전면 오류 크기로 떨어져
     판 안에서 96px 여백의 가운데 오류가 섰다(`EmptyState` 의 모르는 prop 검사와 같은 규율). */
  if (import.meta.env.DEV) {
    if (size != null && size !== "compact") {
      throw new Error(`ErrorState: 모르는 size "${size}". 받는 값은 "compact" 하나다(자리는 layout 이 말한다).`);
    }
    if (!ERROR_STATE_LAYOUTS.includes(layout)) {
      throw new Error(`ErrorState: 모르는 layout "${layout}". 받는 값은 ${ERROR_STATE_LAYOUTS.join(", ")} 중 하나다.`);
    }
  }
  const compact = size === "compact" || layout === "inline";
  const msg = (error && error.message) || "문제가 발생했습니다.";
  const status = error && error.status;
  const code = error && error.body && error.body.error && error.body.error.code;
  const kind = error && error.kind;
  const requestId = (error && error.requestId) || null;
  const isAuth = status === 401;
  const isForbidden = status === 403;
  const isGone = status === 404;
  const isOffline = kind === "network";
  const isRender = kind === "render";
  const isChunk = kind === "chunk";
  const isServer = typeof status === "number" && status >= 500;
  // password_change_required는 403이지만 '권한 부족'이 아니라 '본인이 비번을 안 바꿔서' 막힌
  // 것이다 — 일반 권한부족 문구로 뭉개면 정반대로 오해하게 만든다.
  const isPwChange = isForbidden && code === "password_change_required";
  /* 429 — 「불러오지 못했습니다」+「다시 시도」는 정반대의 안내다: 그 버튼을 누를 때마다
     제한이 유지된다(사용자가 스스로 rate limit 을 강화하는 루프). 서버가 준 대기 시간
     (api.js 의 retryAfterSeconds)만큼 버튼을 잠그고, 그 시간이 아주 길면(AI 사용 상한 —
     자정·월초까지 안 풀린다) 재시도 자체를 주지 않는다. 코드는 둘 다 rate_limited 라
     코드로는 못 가르고 시간으로 가른다: 앱 리미터의 회복은 구조적으로 12초 이내다. */
  const isRateLimited = status === 429;
  const retryAfter =
    isRateLimited && typeof (error && error.retryAfterSeconds) === "number" && error.retryAfterSeconds > 0
      ? error.retryAfterSeconds : null;
  const isQuota = retryAfter != null && retryAfter > RATE_LIMIT_COUNTDOWN_MAX_S;
  const waitSeconds = isQuota ? null : retryAfter;
  const [cooling, setCooling] = React.useState(Boolean(waitSeconds));
  React.useEffect(() => {
    if (!waitSeconds) { setCooling(false); return undefined; }
    setCooling(true);
    // 매초 카운트다운을 그리지 않는다 — 이 뿌리는 role="alert" 라 내부 텍스트가 바뀔
    // 때마다 스크린리더가 전체를 재낭독한다. 정적 「약 N초」 + 만료 시 한 번만 푼다.
    const t = setTimeout(() => setCooling(false), Math.ceil(waitSeconds) * 1000);
    return () => clearTimeout(t);
  }, [waitSeconds, error]);
  // 401/403/404는 재시도해도 같은 실패가 반복된다 — '다시 시도'는 일시적 오류에만 준다.
  const noRetry = isAuth || isForbidden || isGone || isQuota;
  const title = titleProp != null ? titleProp : isAuth ? "로그인이 필요합니다"
    : isPwChange ? "비밀번호 변경이 필요합니다"
    : isForbidden ? "권한이 없습니다"
    : isGone ? "찾을 수 없습니다"
    : isOffline ? "서버에 연결하지 못했습니다"
    : isRateLimited ? "요청이 너무 잦습니다"
    : isChunk ? "새 버전이 배포됐습니다"
    : isRender ? "화면을 표시하지 못했습니다"
    : "불러오지 못했습니다";
  const help = helpProp != null ? helpProp : isPwChange ? msg
    : isForbidden ? "이 항목에 접근할 권한이 없습니다. 관리자에게 문의하세요."
    : isGone ? "요청한 항목을 찾을 수 없습니다. 이미 삭제되었거나 이동했을 수 있습니다."
    : isQuota ? msg
    : isRateLimited && waitSeconds
      ? `약 ${Math.ceil(waitSeconds)}초 뒤에 다시 시도할 수 있습니다.`
    : isRateLimited ? "짧은 시간에 요청이 몰렸습니다. 잠시 기다렸다가 다시 시도해 주세요."
    : isChunk ? "새로고침하면 새 버전의 화면이 열립니다."
    : msg;
  /* 상태마다 다른 그림을 준다. 🔴 **「500」 팻말 그림은 서버가 정말 5xx 를 냈을 때만이다.**
     예전에는 401 · 403 · 404 · 연결 끊김이 아닌 실패가 전부 이 그림이라, 화면 코드의 예외 ·
     요청 제한(429) · 프록시의 이상한 응답까지 사용자에게 「서버 오류 500」으로 보였다 — 서버
     로그에 500 이 한 건도 없는데 사용자는 「두 번 누르면 500 이 난다」고 말했다(2026-09-21). */
  const art = isAuth ? "sessionExpired"
    : isForbidden ? "noPermission"
    : isGone ? "notFound"
    : isOffline ? "offline"
    : isServer ? "serverError"
    : (isRateLimited || isChunk) ? "wait"
    : "trouble";
  const artSrc = ART[art];
  /* 그림 크기는 자리의 계층이 정한다 — 화면 전체가 실패하면 `errorPage`(132, 짧은 화면 112),
     판 하나가 실패하면 `errorRegion`(72). 예전에는 자리와 무관하게 112 한 값이었다. */
  const errorPlace = layout === "page" ? "errorPage" : "errorRegion";
  const errorArtBox = mascotBoxSx(errorPlace, artSrc);
  /* 화면 전체가 실패했을 때만 가운데다. 판 하나가 실패한 자리는 그 판의 다른 내용과 같은
     축을 쓴다 — 왼쪽 정렬 · 위 정렬(위 `layout` 주석이 정본이다). */
  const centered = layout === "page" || layout === "card";
  /* 기술 정보는 접어 둔다. 화면에 보이는 `help` 는 **사람에게 할 말**이고 서버가 준 원문은
     그것과 다르다 — 「NetworkError: Failed to fetch」 를 제목 아래 그대로 올리면 안내가 아니고,
     지우면 문제를 옮겨 적을 수가 없다. 메시지 박스의 `detail` 과 **같은 부품**을 쓴다. */
  /* 화면 실패는 호출부가 옮겨 적을 문장을 따로 준다(`error.detail` — 예외 이름 · 첫 스택 몇 줄 ·
     주소 · 빌드 · 시각). 그 문장이 문의할 때 넘겨줄 전부다. */
  const detailText = error && typeof error.detail === "string" ? error.detail : "";
  const tech = detailText ? (
    /* 여러 줄 그대로 · 긴 줄은 이 상자 안에서만 굴린다 · 한 번에 골라 복사할 수 있다. */
    <Box
      component="pre" data-error-detail=""
      sx={{
        m: 0, maxWidth: `${ERROR_STATE_MAX_CH + 20}ch`, maxHeight: "12rem", overflow: "auto",
        whiteSpace: "pre-wrap", wordBreak: "break-all", textAlign: "left", userSelect: "all",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: FONT_SIZE.caption,
      }}
    >
      {detailText}
    </Box>
  ) : [
    status ? `HTTP ${status}` : null,
    code ? `code ${code}` : null,
    msg && msg !== help ? msg : null,
  ].filter(Boolean).join("   ");
  /* 동작 단추는 **30(인라인)** 이다 — 오류 상태 안의 다음 행동은 페이지 동작이 아니라 그 자리의
     동작이다(핸드오프 ACCEPTANCE I2: 다시 시도 30). 채움은 화면 전체가 막혔을 때(page)만 준다 —
     판 하나의 오류가 그 화면의 주 행동을 가져가지 않는다. */
  const actionVariant = layout === "page" ? "primary" : "default";
  const action = actionProp !== undefined ? actionProp : isAuth
    /* 되돌아올 곳을 실어 보낸다 — 재로그인 뒤 보던 화면으로 돌아온다(지시 19). */
    ? <Button variant={actionVariant} size="sm" href={loginUrl()}>로그인 화면으로</Button>
    // "홈으로"(#/)는 이 SPA 안이라 다시 같은 403을 부른다 — 실제 페이지 이동이 필요하다.
    : isPwChange ? <Button variant={actionVariant} size="sm" href="/change-password">비밀번호 변경하기</Button>
    // 403/404는 재시도해도 소용없지만 아무 동작도 없으면 막다른 길이다.
    : (isForbidden || isGone) ? <Button variant={actionVariant} size="sm" href="#/">홈으로</Button>
    // 새 버전이 배포된 것은 다시 시도로 안 풀린다 — 새 파일을 받는 새로고침이 그 자리의 동작이다.
    : isChunk ? (onRetry ? <Button variant={actionVariant} size="sm" onClick={onRetry}>새로고침</Button> : null)
    // 429 대기 중에는 버튼을 잠근다 — 눌리는 「다시 시도」는 제한을 스스로 연장시킨다.
    : (!noRetry && onRetry ? <Button variant={actionVariant} size="sm" onClick={onRetry} disabled={cooling}>{retryLabel}</Button> : null);

  // role="alert"로 오류 전환을 즉시 낭독한다. 제목은 heading으로.
  return (
    // VIS-50/VIS-52와 같은 이유(EmptyState 주석 참고) — ErrorState도 같은 삽화 자산과
    // 여백 규칙을 공유하므로 같은 값으로 맞춘다.
    <Box
      className="k-empty"
      role="alert"
      data-error-layout={layout}
      sx={(theme) => ({
        ...(centered
          ? { display: "grid", justifyItems: "center", textAlign: "center", gap: compact ? 0.75 : 1.5, py: compact ? 2 : { xs: 6, uhd: 14 }, px: compact ? 1.5 : 3 }
          : { display: "flex", alignItems: "flex-start", gap: compact ? 1.5 : 2.5, py: compact ? 2 : 3.5, px: compact ? 1.5 : 2 }),
        /* 그림이 서는 오류 상태만 다크 바탕을 받는다(위 `mascotGroundSx`). */
        ...(!compact ? mascotGroundSx(theme) : null),
      })}
    >
      {!compact ? (
        <Box
          component="img" src={artSrc} alt="" aria-hidden="true" loading="lazy" decoding="async"
          data-mascot-context={MASCOT_PLACE[errorPlace].context}
          /* 4K 에서 320px 짜리 상자였다 — 그리고 그 상자 안의 그림은 자산마다 65~78% 만
             채웠다. 이제 «보이는 캐릭터 112px»(PLAN «Clovi 계약») 하나가 세 단계를 대신한다. */
          sx={{ display: { xs: "none", sm: "block" }, flexShrink: 0, ...errorArtBox, objectFit: "contain" }}
        />
      ) : null}
      <Box sx={{ display: "grid", gap: compact ? 0.75 : 1.5, minWidth: 0, ...(centered ? { justifyItems: "center" } : null) }}>
        {/* 🔴 제목 왼쪽의 오류 표지. 이 부품에는 상태 아이콘이 **하나도 없었다** — 마스코트는
            어느 오류인지(404·403·연결 끊김)를 말하지 그 상자가 오류라는 것을 말하지 않는다.
            메시지 박스와 같은 아이콘·같은 색·같은 접근 이름을 쓴다. */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
          <ErrorOutlineRoundedIcon
            role="img"
            aria-label="오류"
            sx={{ flexShrink: 0, fontSize: remPx(ICON.mark), color: "error.main" }}
          />
          <Typography role="heading" aria-level={2} sx={{ minWidth: 0, fontWeight: FONT_WEIGHT.bold, fontSize: compact ? FONT_SIZE.body : FONT_SIZE.sectionTitle, ...KO_WORD_BREAK }}>{title}</Typography>
        </Box>
        {/* 칸 폭은 ERROR_STATE_MAX_CH. 문구 한도는 COPY_LIMIT.errorHelp. */}
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: `${ERROR_STATE_MAX_CH}ch`, fontSize: compact ? FONT_SIZE.bodySm : undefined }}>{help}</Typography>
        {action || secondaryAction || tech ? (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", justifyContent: centered ? "center" : "flex-start", mt: compact ? 0 : 0.25 }}>
            {action}
            {secondaryAction || null}
            <TechDetail>{tech || null}</TechDetail>
          </Box>
        ) : null}
        {/* 문의 번호 (Z8). 서버는 요청마다 id 를 만들어 오류 봉투와 `X-Request-ID` 에 실어
            보내고 감사 로그도 그 값을 저장하는데, 화면이 한 번도 보여 주지 않아 **사용자가
            불러 줄 수가 없었다.** 새벽 3시에 "화면이 안 나와요" 를 받으면 경로와 상태 코드밖에
            단서가 없었다. 접기 안에 넣지 않는다 — 접힌 번호는 불러 줄 수 없다.
            로그인·권한 문제처럼 원인이 뻔한 것에는 붙이지 않는다. compact에선 더 뺀다. */}
        {requestId && !isAuth && !isForbidden && !isGone && !compact ? (
          <Typography
            variant="body2" color="text.disabled"
            sx={{ fontSize: FONT_SIZE.caption, userSelect: "all" }}
          >
            문의 번호 {requestId}
          </Typography>
        ) : null}
      </Box>
    </Box>
  );
}

/** 세션이 끊기면 본문 자리가 **오류 상태(401 갈래)** 로 바뀐다 — 동작 중 401 을 맞은 화면이
 * `expireSession()` 을 부르면 서는 자리다(`lib/sessionRedirect.js`). 셸의 본문 열이 이것으로 화면을
 * 감싼다. 떠나는 것(1.2초 뒤 로그인 화면)은 `expireSession` 이 이미 예약했다. */
export function SessionExpiredOutlet({ children }) {
  const expired = React.useSyncExternalStore(subscribeSessionExpired, isSessionExpired, isSessionExpired);
  return expired ? <ErrorState error={SESSION_EXPIRED_ERROR} /> : children;
}

/* 반응형 표 — 넓은 화면은 표, 좁은 화면(≤760px)은 카드 목록으로 CSS가 전환한다(§21).
 * columns: [{key,label,render?}], rows: [obj], rowKey: (row)=>id. onRow: 행 클릭(상세).
 *
 * 이 컴포넌트만 legacy 마크업/클래스를 유지한다. screens.css가 화면별로 열 너비를
 * .k-table th:nth-child(n)으로 고정하고(문서 표) 좁은 화면 카드 전환도 그 CSS가 담당하기
 * 때문이다. 표는 DataScreen 재설계(A3)에서 CSS까지 함께 옮긴다.
 *
 * 접근성: 행은 표 의미(row)를 유지한다 — 상세 열기는 행 자체의 클릭/Enter·Space가
 * 담당한다(PA-RC-0023). 예전엔 마지막 칸의 실제 <button>("상세")이 유일한 진입점이었는데,
 * 그 버튼이 하는 일이 행 클릭과 완전히 같아 잉크만 쓰고 정보를 더하지 않았다 — 버튼 없이도
 * 키보드로 도달 가능해진 뒤(tabIndex+aria-label+onKeyDown, 아래) 열을 지웠다. */
function rowOpenLabel(columns, row) {
  /* 열 정의가 '행을 구별하는 값'을 명시했으면(rowName) 그것이 가장 정확하다 — 첫 열이
     무엇이든 화면이 정한 식별 열을 쓴다(ui/rowName.js). 표식이 없는 표는 아래 옛 규칙
     그대로 둔다: 폴백을 여기서 넓히면 첫 열이 render() 인 표들의 이름이 한꺼번에 바뀐다. */
  const declared = declaredRowName(columns, row);
  if (declared) return "상세 보기: " + declared;
  const primary = columns[0];
  if (!primary) return "상세 보기";
  // 첫 열이 커스텀 render()를 쓰면 원시 값을 텍스트로 못 쓴다 — 화면 쪽에서 openLabel(row)를
  // 넘기면 render 유무와 무관하게 그 값을 우선 쓴다(product-quality-audit AREA=D).
  if (typeof primary.openLabel === "function") {
    try { const v = primary.openLabel(row); if (v) return v; } catch (e) { /* ignore */ }
  }
  if (primary.render) return "상세 보기";
  const v = row[primary.key];
  if (v == null || v === "") return "상세 보기";
  return "상세 보기: " + String(v);
}
/* 열의 폭·정렬·자릿수·넘침은 **`columnTypes.js` 의 어휘표**가 정한다 (C3 · W6).
 *
 * 예전에는 여기 두 상수(`DEFAULT_COL_MIN_WIDTH`·`IDENTIFIER_COL_MIN_WIDTH`)와 호출부의
 * `width`/`align` 숫자가 그 일을 나눠 했다. 그래서 같은 뜻의 값이 화면마다 다른 폭과 다른
 * 정렬로 나왔고, 「개수인데 자릿수가 세로로 안 맞는」 열이 여덟 개 남아 있었다.
 * 상수는 그 파일로 옮겼고 이 자리에는 **해석 결과를 쓰는 함수**만 남는다.
 * `type` 을 안 준 열은 예전과 정확히 같은 값을 받는다(회귀 0). */

/* 셀 하나의 폭·정렬·자릿수·넘침을 한 번에 만든다 — 머리글 칸과 본문 칸이 **같은 함수**를
 * 본다. 예전에는 둘이 따로 계산해서 한쪽만 설정하는 경로가 실제로 존재했고, 그게
 * `header_cell_alignment_mismatch` 가 잡는 결함의 구조적 원인이었다(kit.jsx:1036/1124). */
function colCellSx(c, { truncate, head } = {}) {
  const s = resolveColumn(c);
  const sx = { minWidth: s.minWidth, verticalAlign: "middle" };
  /* 자릿수 고정은 **`td` 자신**이 들어야 한다 — QA 의 `numeric_alignment` 가 셀의
     computed style 을 읽고, 안쪽 `<span>` 에만 걸면 그 검사는 없다고 본다. */
  if (s.numeric) Object.assign(sx, NUMERIC);
  /* 폭은 머리글 칸에만 적는다. `<table>` 의 열 폭은 열 전체에서 하나로 정해지므로 한 칸만
     말하면 충분하고, 본문 칸의 말줄임은 `maxWidth: 0` 이 맡는데 그 둘을 한 칸에 함께 걸면
     서로를 무력화한다(말줄임이 안 되거나 폭이 안 줄거나 — 브라우저마다 다르다).

     🔴 머리글 칸에 `overflow:hidden` 을 걸지 않는다. `table-cell` 은 기본이
     `vertical-align:baseline` 이라, hidden 을 거는 순간 칸 높이가 **글자 줄상자**로
     줄어들고 안쪽 32px 정렬·필터 단추와 한글 받침이 아래쪽에서 잘린다(내 티켓 실측).
     옆 머리글과 겹치는 문제는 `table-layout:fixed` + `columnLayoutWidth` 가 맡는다.
     이름은 `TableHeaderCell` 이 자르지 않는다(A4). */
  if (head) {
    const layoutW = columnLayoutWidth(c);
    return {
      ...sx,
      ...(layoutW ? { width: layoutW } : null),
      whiteSpace: "nowrap",
      verticalAlign: "middle",
      overflow: "visible",
      lineHeight: 1.5,
      ...(c.help ? { cursor: "help" } : null),
    };
  }
  if (truncate) {
    return { ...sx, textAlign: s.align, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 0 };
  }
  /* 자르지도 접지도 않는 열(개수·날짜)도 **넘치면 자른다.** 값이 짧다는 전제가 깨지는
     날 — 새 상태 낱말이 길어지거나 좁은 화면에서 열이 눌릴 때 — 그 값이 옆 칸 위에 그려진다.
     행 동작 묶음(`actions`)과 선택 칸은 제외한다: 그 안은 글이 아니라 누를 것이라 잘리면
     닿을 수 없게 된다.
     **`render` 가 있는 열도 제외한다** — 배지·신호·태그·인라인 편집은 자기 폭을 스스로
     관리한다(위 `renderDataRow` 주석). `nowrap` 타입에 `overflow:hidden` 을 걸면 알약·표지가
     칸 중간에서 잘려 「반쯤 깨진 알약」처럼 보인다 — 상태·신호 열에서 실제로 그랬다.
     단 **수치 · 날짜 열은 `render` 가 있어도 자른다.** 그 칸의 내용은 알약이 아니라 글자이고,
     빈 값을 문장으로 채운 칸이 옆 칸 위로 넘쳐 그려졌다(프로젝트 목록의 진행률 · Health, 계획 3.1).
     넘치면 말줄임이 되는 편이 남의 칸을 덮는 것보다 낫다. */
  if (s.overflow === OVERFLOW.nowrap) {
    const clip = s.type !== "actions" && s.type !== "select" && (!c.render || s.numeric);
    return {
      ...sx, textAlign: s.align, overflowWrap: "normal", whiteSpace: "nowrap",
      ...(clip ? { overflow: "hidden", textOverflow: "ellipsis" } : null),
    };
  }
  if (s.overflow === OVERFLOW.anywhere) return { ...sx, textAlign: s.align, ...ANYWHERE_BREAK };
  return { ...sx, textAlign: s.align, ...KO_WORD_BREAK };
}

/* 식별자형 열은 **우정렬 대상이 아니다** — 티켓번호·포트·버전은 크기를 비교하지 않는다.
 * QA 가 그 예외를 읽는 표식이 `data-col-role="identifier"` 인데, 그 표식을 내보내는 소스가
 * 이 저장소에 **한 곳도 없었다**(assertions.py:1126 이 찾는 속성이 어디에도 안 붙어 있었다).
 * 선언만 있고 배선이 없으면 그 예외는 존재하지 않는 것과 같다 — 여기서 붙인다. */
function colRole(c) {
  return resolveColumn(c).identifier ? "identifier" : undefined;
}

/* 표 칸 하나에 붙는 것 전부 — 정렬·역할 표식·sx 를 한 번에 준다.
 *
 * 이 저장소에는 열 정의를 읽어 `<td>` 를 그리는 자리가 **둘**이다: 여기 `DataTable` 과
 * `MyTickets` 의 묶음 목록(`GroupedList` — 묶음 머리행이 있어서 표 컴포넌트로 못 접는다).
 * 규칙을 두 곳에 적으면 한쪽만 고쳐진다 — W5 가 카드 접기에서 이미 그렇게 잃었고
 * (`cardFieldLabel`·`cardHeaderControls` 가 그때 생긴 함수다), 정렬 규칙에서 같은 일이
 * 다시 일어나면 «`/board` 는 맞는데 `/my-tickets` 는 틀린» 상태가 된다.
 */
export function tableCellProps(col, opts) {
  return {
    align: resolveColumn(col).align,
    "data-col-role": colRole(col),
    sx: colCellSx(col, opts),
  };
}

/* 셀 렌더러에 넘기는 두 번째 인자(ctx)는 **그 행에 대한 표의 지식**이다. 지금은 rowName
 * 하나뿐이다: 선택 체크박스처럼 셀 안에 있으면서 '자기 행이 무엇인지' 알아야 하는 컨트롤이
 * 쓴다. 화면이 열 정의마다 라벨을 손으로 적지 않게 하려면 표가 알려 주는 수밖에 없다
 * (열은 자기 옆 열들을 모른다). 기존 render 들은 인자를 하나만 받으므로 그대로 동작한다. */
function cellValue(c, row, ctx) {
  if (c.render) return c.render(row, ctx);
  /* 그리는 함수가 없으면 열의 글 값(`value(row)`)이 곧 그림이다 — 열 배분(D-529)이 잰 글과 칸에 선 글이 같은 함수에서 나온다. */
  const v = typeof c.value === "function" ? c.value(row) : row[c.key];
  return v == null || v === "" ? "-" : String(v);
}

/* 정렬 화살표는 호출부가 `onSort` 를 줄 때만 그린다.
 *
 * 서버가 페이지를 자르는 목록은 **전체 결과**를 서버가 정렬해야 한다. 보이는 20건만
 * 화면에서 바꾸면 사용자는 전체 순서를 봤다고 믿는다. `onSort` 는 그 서버 질의를
 * 바꾸라는 뜻이다. 전량을 들고 있는 화면만 화면에서 정렬해도 된다.
 *
 * `sort` = `{ key, dir }`(dir: "asc" | "desc"), `onSort(key)` 는 호출부가 방향을 뒤집는다.
 * `onFilter` 도 같은 규칙이다. 안 주면 예전 머리글과 같다.
 */
/* ── 표를 카드로 접을 때의 두 규칙 (W5) ─────────────────────────────────────
 *
 * 이 저장소에는 «표를 카드로 접는» 자리가 **둘**이다: 여기 `DataTable` 과 `MyTickets` 의
 * 묶음 목록(`GroupedList`). 규칙을 두 곳에 적으면 한쪽만 고쳐진다 — 실제로 그랬다.
 * W5 가 `DataTable` 만 고쳤더니 `/my-tickets`·`/unassigned` 는 그대로 결함이 남았다
 * (`control_baseline_mismatch` 390px). 그래서 규칙을 함수 두 개로 내려 둔다.
 *
 * ① **이름 자리에는 낱말이 온다.** 열이 `cardLabel` 로 말해 주면 그것을 쓴다. 선택 열의
 *    `label` 은 이름이 아니라 「전체 선택」 체크박스라, 그대로 그리면 카드마다 복제된다.
 * ② **목록 전체의 조작기는 목록 위에 한 번.** 열이 `cardHeader` 로 그것을 든다. */
export function cardFieldLabel(col) {
  return col && col.cardLabel != null ? col.cardLabel : (col ? col.label : null);
}
export function cardHeaderControls(cols) {
  return (cols || []).filter((c) => c && c.cardHeader);
}

/* ── 표 배치는 **하나**다: `fixed` + `columnLayoutWidth` (S19 → 사용자 요청) ─────
 *
 * 예전 auto 배치 + `SHRINK="1%"` 는 열 폭이 흔들리고 머리글이 겹쳤다. fixed 배치에서
 * `1%` 를 그대로 쓰면 바닥 minWidth 가 무시되므로, `columnTypes.columnLayoutWidth` 가
 * `title` 을 제외한 열에 **rem 바닥값**을 준다. `title` 은 남는 폭을 먹는다.
 *
 * 긴 값은 말줄임 + `title` hover(전역). 배지·버튼·인라인 편집 열은 자르지 않는다. */
export const TABLE_FIXED_LAYOUT_SX = { tableLayout: "fixed", width: "100%" };

/* 이 열 목록으로 그리는 표의 배치 — 고정 배치 + **줄어들 바닥**.
 *
 * `width: 100%` 만으로는 칸이 좁아질 때 표가 같이 좁아지고, 그러면 남는 폭을 먹기로 한
 * 제목 열이 0 이 된다(`columnTypes.tableMinWidth` 의 실측표). 바닥을 함께 주면 표는
 * 안 줄고 `TableContainer` 가 가로로 굴러간다 — 그 거래는 이 파일이 이미 여러 번 적어
 * 뒀지만 실제로 만드는 값이 없었다.
 *
 * **열이 정해진 뒤에 부른다.** 좁은 화면에서 빠지는 열(`hideNarrow`)까지 세면 바닥이
 * 실제보다 넓어져, 안 그려지는 열 때문에 표가 가로로 밀린다. */
export function tableLayoutSx(columns, plan) {
  /* 열 배분(D-529)을 쟀으면 그 폭이 정본이다 — 칸에 들어가면 표 폭 = 칸 폭(100%), 필수 열 바닥 합이 칸보다 크면 표가 그
     합 폭으로 서고 표 상자가 가로로 굴린다. 못 쟀으면(첫 그림) 옛 바닥(`tableMinWidth`)이다. */
  if (plan && plan.widths) {
    return plan.scroll
      ? { tableLayout: "fixed", width: `${plan.tableWidth}px`, minWidth: `${plan.tableWidth}px` }
      : { ...TABLE_FIXED_LAYOUT_SX, minWidth: `${plan.tableWidth}px` };
  }
  return { ...TABLE_FIXED_LAYOUT_SX, minWidth: tableMinWidth(columns) };
}

/* 이 칸에 들어가는 열만 남긴다 — `DataTable` 과 `GroupedTickets` 가 **같은 함수**를 본다.
 *
 * 규칙을 두 곳에 적으면 한쪽만 고쳐진다. 이 파일이 이미 두 번 그렇게 잃었고(카드 접기의
 * `cardFieldLabel`·`cardHeaderControls`, 그리고 정렬의 `tableCellProps`), 열 접기에서 같은
 * 일이 나면 「팀 티켓은 접히는데 내 티켓은 안 접히는」 상태가 된다.
 *
 * `boxEl` 은 표를 담은 `TableContainer` 다. 그 칸의 폭은 우리가 그리는 열 수와 **무관**
 * 하므로(폭은 바깥 배치가 정한다) 열을 빼도 되먹임이 없다 — 행 높이도 안 변한다, 긴 값은
 * 접히지 않고 말줄임이기 때문이다.
 *
 * 못 재는 동안에는 아무 것도 안 빼고 폭도 나누지 않는다(`columnPlan.planColumns` — 첫 그림은 옛 바닥 배치다). */
export function useFittedColumns(columns, boxEl, { sortKey, sortGlyph = false, filterGlyph = false, rows } = {}) {
  const [avail, setAvail] = React.useState(0);
  const [rootPx, setRootPx] = React.useState(() => rootFontPx());
  React.useLayoutEffect(() => {
    if (!boxEl) return undefined;
    /* 관찰을 끊은 뒤에 오는 알림은 버린다. `ResizeObserver` 는 마지막 알림이 큐에 남은
       채로 `disconnect()` 될 수 있고, 그때 이미 떨어져 나간 노드의 폭(0)을 읽어 「칸이
       0 이 됐다」로 한 번 더 그린다 — 화면에서는 열이 깜빡이고 시험에서는 act 경고다. */
    let live = true;
    const measure = () => {
      if (!live) return;
      setAvail(boxEl.clientWidth || 0);
      setRootPx(rootFontPx());
    };
    measure();
    if (typeof ResizeObserver === "undefined") return () => { live = false; };
    const ro = new ResizeObserver(measure);
    ro.observe(boxEl);
    return () => { live = false; ro.disconnect(); };
  }, [boxEl]);
  /* 열 배분(D-529) — 바닥 · 비중 · 상한과 머리글 · 값 길이로 폭을 나누고, 좁으면 등급 순서(문맥 → 보조)대로 숨긴다. 머리글의
     정렬 · 필터 표지는 그 표에서 실제로 서는 것만 센다(`TableHeaderCell` 과 같은 조건). */
  return React.useMemo(
    () => planColumns(columns, avail, {
      rootPx,
      sortKey,
      rows,
      glyphsOf: (c) => (sortGlyph && c.sortable ? 1 : 0) + (filterGlyph && c.filter ? 1 : 0),
    }),
    [columns, avail, rootPx, sortKey, sortGlyph, filterGlyph, rows],
  );
}

/* 열이 조용히 사라지면 사용자는 그 값을 못 봤다는 사실조차 모른다 (PA-RC-0037).
 * 무엇이 왜 없는지를 표가 직접 말한다 — 두 표가 **같은 문장**을 쓴다.
 *
 * 🔴 「행을 열면」은 **행을 열 수 있는 표에서만** 사실이다. 그 문장을 무조건 적으면,
 * 행이 안 열리는 표(`onRow` 를 안 주는 화면 — 휴지통이 그렇다)에서 사용자는 열 방법을
 * 찾다가 못 찾는다. 안내가 없는 것보다 **없는 길을 가리키는 안내**가 더 나쁘다.
 * 열 수 없으면 그 자리에는 창을 넓히라고 말한다 — 그것이 그 표에서 실제로 되는 일이다. */
export function HiddenColumnsNote({ columns, openable = false, inline = false }) {
  const names = (columns || []).map((c) => c.label).filter(Boolean);
  if (!names.length) return null;
  /* `inline` — 목록 판 발 안에서 건수 문장 옆에 한 토막으로 선다(조합 계약 C-3). 판 없는 표(모달 · 서랍)는
     예전처럼 표 위 한 줄이다. */
  return (
    <Typography
      variant="caption"
      color="text.secondary"
      data-hidden-columns={inline ? "" : undefined}
      sx={inline ? { display: "inline" } : { display: "block", px: 2, pt: 1.5 }}
    >
      표 폭이 좁아 {names.join(", ")} 열을 숨겼습니다.{" "}
      {openable ? "행을 열면 숨긴 값도 볼 수 있습니다." : "창을 넓히면 다시 보입니다."}
    </Typography>
  );
}

/** 말줄임 대상 열인가 — DataTable·GroupedTickets 가 같은 규칙을 쓴다.
 *
 * 🔴 **행 동작·선택 열은 어떤 경우에도 아니다.** 바로 위 `colCellSx` 의 `nowrap` 갈래가
 * 그 둘을 이미 제외해 두었는데(「그 안은 글이 아니라 누를 것이라 잘리면 닿을 수 없게
 * 된다」), 호출부가 `ellipsis` 를 넘기면 이 함수가 참을 내면서 **그 가드를 통째로
 * 우회했다** — `truncate` 갈래는 `maxWidth: 0; overflow: hidden` 을 무조건 건다.
 * 그래서 휴지통처럼 표 전체에 `ellipsis` 를 건 화면에서 「복원 / 영구 삭제」 단추와
 * 체크박스가 칸이 좁아지는 순간 잘렸다.
 *
 * 가드를 **호출부가 아니라 여기**에 둔다. 호출부에서 `ellipsis` 를 빼는 것으로 고치면
 * 같은 실수를 하는 다음 화면에서 다시 난다. */
export function columnShouldTruncate(col, ellipsis) {
  const c = col || {};
  if (c.type === "actions" || c.type === "select") return false;
  /* 호출부가 낱말 단위 접기(`overflow: "word"`)를 **직접 적은** 산문 열은 자르지 않고 접는다. 예전에는 이 함수가 산문 열을
     언제나 말줄임으로 보내 그 설정이 한 번도 적용되지 않았다(계획 6절 9). 타입의 기본 넘침(제목의 word)은 그대로 말줄임이다. */
  if (c.overflow === OVERFLOW.word) return false;
  return !!(ellipsis || !c.render || c.type === "title" || c.type === "name" || c.type === "text" || c.type === "enum");
}

/** 잘린 셀 hover 시 보여 줄 전체 문자열.
 *
 * `render` 가 있는 열은 칸에 그린 글자와 행의 원래 값이 다를 수 있다 — 역할 · 상태 배지는 `system_admin` 을 「시스템
 * 관리자」로 그린다. 그런 열은 `hint(row)` 로 **그린 글자**를 말한다. 없으면 원래 값(`plain`)으로 떨어지는데, 예전에는
 * 그 갈래만 있어서 사용자 목록 역할 칸에 마우스를 올리면 한국어 배지 위로 `system_admin` 이 떴다(P7b 발견). */
export function columnCellHint(col, row, ctx, { truncate, raw, plain } = {}) {
  const c = col || {};
  if (!truncate) return undefined;
  if (raw && raw !== "-") return raw;
  if (typeof c.rowName === "function") {
    try { const v = c.rowName(row, ctx); if (v) return String(v); } catch (e) { /* ignore */ }
  }
  if (typeof c.hint === "function") {
    try { const v = c.hint(row, ctx); return v != null && v !== "" ? String(v) : undefined; } catch (e) { /* ignore */ }
  }
  if (plain) return plain;
  if (c.key === "assignee_names" && row) {
    const names = (row.assignee_names || []).join(", ");
    return names || undefined;
  }
  return undefined;
}

export function TableColGroup({ columns, widths, meta }) {
  const cols = Array.isArray(columns) ? columns : [];
  return (
    <colgroup>
      {cols.map((c) => {
        /* 배분 폭(px, D-529)이 있으면 그것이 정본이고, 못 쟀으면(첫 그림) 옛 바닥 폭이다. */
        const w = widths && widths[c.key] != null ? `${widths[c.key]}px` : columnLayoutWidth(c);
        /* 배분의 근거(등급 · 종류 · 바닥 · 상한)를 표식으로 남긴다 — QA 프로브 `column_balance` 가 읽는다(값은 px). */
        const m = meta && meta[c.key];
        return (
          <col
            key={c.key}
            style={w ? { width: w } : undefined}
            data-col-key={m ? c.key : undefined}
            data-col-tier={m ? m.tier : undefined}
            data-col-kind={m ? m.kind : undefined}
            data-col-content={m && m.content ? "" : undefined}
            data-col-min={m ? m.min : undefined}
            data-col-max={m && m.max != null ? m.max : undefined}
          />
        );
      })}
    </colgroup>
  );
}

/* 가로로 굴러가는 표(필수 열만으로도 칸이 모자람)의 첫 열은 붙박이다 — 행이 무엇인지 말하는 열이 굴리는 동안 사라지지 않는다.
   선택 칸이 앞에 있으면 그 칸까지 붙박이고, 왼쪽 자리는 배분 폭(px)으로 정한다. */
function stickyColumnsOf(cols, plan) {
  if (!plan || !plan.scroll || !plan.widths) return null;
  const out = {};
  let left = 0;
  for (const c of cols) {
    out[c.key] = left;
    left += plan.widths[c.key] || 0;
    if (resolveColumn(c).type !== "select") break;
  }
  return out;
}

const ELLIPSIS_CELL_SX = {
  display: "block", minWidth: 0, maxWidth: "100%",
  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  textAlign: "inherit",
};

function wrapTableCellContent(content, { truncate, hint }) {
  if (!truncate) return content;
  if (hint) {
    return <Box component="span" title={hint} sx={ELLIPSIS_CELL_SX}>{content}</Box>;
  }
  return content;
}
/* REAUDIT A9 — 행에 실제 `<a href>` 가 하나도 없어 새 탭·가운데 클릭·주소 복사가 안 됐다.
 * `onRow` 는 클릭·키보드만 처리하는 진짜 링크가 아니다.
 *
 * `rowHref` 를 준 화면만 opt-in 으로 받는다(`resultScope` 와 같은 원칙 — 안 쓰는 화면은
 * 한 픽셀도 안 바뀐다). `type:"title"` 열 하나에만 건다 — 행 전체를 앵커로 덮으면 그
 * 안의 실제 버튼·링크(행 액션)를 가린다, 위 PA-RC-0023 주석이 이미 그 이유로 행 자체에
 * `role="button"` 을 안 준다.
 *
 * 🔴 이 앱은 `HashRouter` 다(`app/App.jsx`) — `rowHref` 가 주는 값은 **진짜 `href`** 로
 * 그대로 나가므로 반드시 `"#/..."` 로 시작해야 한다. `"/projects/…"` 처럼 `#` 를 빠뜨리면
 * 평범한 클릭(=`onRow`/`nav()` 경로)은 멀쩡히 동작해 눈에 안 띄지만, 새 탭·가운데 클릭·
 * 주소 복사(이 opt-in 을 만든 바로 그 이유)는 서버가 모르는 실제 경로로 나가 조용히
 * 깨진다.
 *
 * 평범한 왼쪽 클릭만 가로챈다(preventDefault 뒤 `onRow` 로 SPA 이동) — 수정자 키·가운데
 * 클릭은 막지 않고 브라우저 기본 동작(새 탭 등)에 맡긴다. `tabIndex=-1` 로 tab 정지점을
 * 늘리지 않는다 — 행 자신이 이미 `tabIndex=0`+`aria-label` 로 키보드 진입을 준다(이중
 * 정지점을 만들지 않는다). 바깥 행의 `closest("a,button")` 가드가 이미 있어 이중 nav
 * 걱정은 없다. */
function rowAnchorProps(href, onActivate) {
  return {
    href,
    tabIndex: -1,
    onClick: (e) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onActivate();
    },
  };
}

/* 열 접힘 판정을 **앞 묶음으로만** 한다 (무한 스크롤).
 *
 * `planColumnCollapse` 는 지금 보이는 행 전체에서 「값이 전부 같은가」를 본다. 목록이 굴릴수록
 * 자라면 그 판정이 **스크롤 도중에 뒤집혀** 열 폭이 통째로 재배치된다 — 읽던 표가 눈앞에서
 * 움직인다. 조건이 바뀌어 열이 달라지는 것은 사용자가 유발한 변화라 예측 가능하지만, 굴리는
 * 것은 그렇지 않다.
 *
 * 표본으로 줄여도 **정보를 잃지 않는다**: 서버가 쪽을 자르는 목록(`serverPaged`)에서 열을
 * 실제로 **빼는** 갈래는 `structural && same`(=그 열이 지금 걸린 조건이다) 하나뿐이고, 그것은
 * 서버가 거른 결과라 어느 묶음에서나 참이다. 「전부 비었다」로 빼는 갈래는 그 목록에서 애초에
 * 안 돈다. 전량을 받는 목록은 표본을 쓰지 않는다 — 거기서는 51번째 행의 값이 진짜 반례다. */
const COLLAPSE_SAMPLE = 50;

/* 묶음 머리행이 받는 값 — 문자열 하나만 줘도 된다.
 * `{ key, label, count, note }` 에서 `key` 는 «묶음이 바뀌었는가» 판정에만 쓰고 화면에는
 * `label` 이 나온다. `count` 를 안 주면 표가 직접 센다(같은 key 를 가진 행 수).
 * `note` 는 그 묶음의 한 줄 요약이다 — 이름 옆에 여린 글씨로 붙는다. */
function normalizeGroup(g) {
  if (g == null || g === false) return null;
  if (typeof g === "string" || typeof g === "number") return { key: String(g), label: String(g) };
  if (g.key == null && g.label == null) return null;
  const key = String(g.key != null ? g.key : g.label);
  return { key, label: g.label != null ? g.label : key, count: g.count, note: g.note };
}

/* 묶음 머리행 — 프로젝트·담당자처럼 **행 여럿을 한 이름 아래 묶는** 줄.
 *
 * 예전에는 이 줄이 필요한 표(`MyTickets` 의 묶음 목록, `DevReport` 의 담당자별 상세)가
 * `DataTable` 을 못 쓰고 자기 `<Table>` 을 따로 그렸다 — 그래서 정렬·말줄임·열 접기 규칙이
 * 두 벌이 됐고 한쪽만 고쳐지는 일이 실제로 여러 번 있었다(`tableCellProps` 주석의 그 이력).
 * 줄 하나가 없어서 표 구현이 갈라지느니 표가 그 줄을 갖는 편이 낫다.
 *
 * `<th scope="colgroup">` 이다 — 스크린 리더가 아래 행들이 이 이름에 속한다고 읽는다. */
function GroupHeaderRow({ group, colSpan, collapsible, open, onToggle }) {
  const inner = (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
      {collapsible ? (
        <ExpandMoreRoundedIcon
          fontSize="small" aria-hidden="true"
          sx={{ flexShrink: 0, transform: open ? "none" : "rotate(-90deg)", transition: `transform ${MOTION.fast} ${MOTION.ease}` }}
        />
      ) : null}
      <Box
        component="span"
        sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.bold, color: "text.primary", ...KO_WORD_BREAK }}
      >
        {group.label}
      </Box>
      <GroupHeaderMeta group={group} />
    </Box>
  );
  return (
    <TableRow data-group-row={group.key}>
      <TableCell
        component="th"
        scope="colgroup"
        colSpan={colSpan}
        sx={{
          height: remPx(CONTROL.tableGroupRow),
          /* 묶음 줄은 몸 안의 `th` 라 넓은 화면의 몸 칸 여백(테마 `body`, 미디어 규칙)을 받는다 — 선택자를 한 단 세게 적어 그 여백을
             이긴다(2560 에서 묶음 줄이 36 이 아니라 44 로 섰다, P17V). */
          "&&": { paddingTop: 0, paddingBottom: 0 },
          ...(collapsible ? { px: 0 } : null),
          textAlign: "start",
          background: "background.inset",
          borderBottom: (t) => `1px solid ${t.palette.rule || t.palette.divider}`,
        }}
      >
        {/* 접을 수 있으면 **진짜 `<button>`** 으로 감싼다 — `<th scope="colgroup">` 의 뜻은
            그대로 두고(스크린 리더의 표 탐색용) 그 안에 버튼을 얹는다. 기본 버튼 크롬은
            지워 원래 글자처럼 보이게 한다. */}
        {collapsible ? (
          <Box
            component="button" type="button" aria-expanded={!!open} onClick={onToggle}
            sx={{
              all: "unset", display: "block", width: "100%", cursor: "pointer",
              px: 2, boxSizing: "border-box",
              "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: -2 }),
            }}
          >
            {inner}
          </Box>
        ) : inner}
      </TableCell>
    </TableRow>
  );
}

/* 묶음 이름 뒤에 붙는 것 둘 — 건수 칩과 한 줄 요약. 표 머리행과 카드 머리가 **같은 것**을
 * 그린다(좁은 화면에서만 다른 말을 하지 않게). */
function GroupHeaderMeta({ group }) {
  return (
    <>
      {/* 건수는 **건수 미니 칩** 하나다(핸드오프 README §4 · P-7) — 「프로젝트명」 옆에 「N건」. */}
      {group.count != null ? <CountChip value={`${group.count}건`} /> : null}
      {group.note != null ? (
        <Box
          component="span"
          sx={{
            minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.regular, color: "text.secondary",
          }}
        >
          {group.note}
        </Box>
      ) : null}
    </>
  );
}

/* ── 선택 묶음 — 「N개 선택」 · 일괄 동작 · 「해제」 (핸드오프 README §4 · RULES §5 · 조합 계약 C-3) ─────────
 *
 * 목록 판 발의 오른쪽 칸이다. 예전에는 같은 묶음(`bulkSelect.jsx::BulkActions`)이 `PageHeader` 의 동작 자리에
 * 나타났다 사라졌고(내 티켓 · 미할당 · 휴지통), 사용자 화면은 목록 위에 따로 막대를 세웠다. 고른 행과 그 행에 할
 * 일이 화면 맨 위와 표 끝으로 갈라져, 긴 목록을 내려가며 고르면 동작이 화면 밖에 있었다.
 *
 * 역할은 `toolbar` 다(SEM-02) — 제목 계층이 아니라 상태에 따라 나타나는 컨트롤 묶음이라 스크린리더가 「일괄 작업」
 * 으로 식별하고 건너뛸 수 있게 한다. 선택이 없으면 아무것도 그리지 않는다(발의 오른쪽은 비운다). 일괄 동작은 30 이고
 * 채움이 필요하면 이 묶음 **안에서만** 하나다(`data-list-selection` — 화면 채움 수에 안 센다).
 *
 * 이 묶음은 밀집 줄(30)이다(D-526) — 안에 선 고르개 · 입력도 컨트롤 높이 변수(`densityVars("dense")`)를 받아 30 단추와 같은
 * 높이 · 같은 윗선에 선다. 예전에는 「일괄 지정」 칸이 34 로 서서 옆 30 단추와 2px 씩 어긋났다. */
export function SelectionBar({ count, unit = "개", clearLabel = "해제", onClear, children, sx }) {
  if (!count) return null;
  return (
    <Box
      data-list-selection=""
      role="toolbar"
      aria-label="일괄 작업"
      sx={{ display: "inline-flex", alignItems: "center", flexWrap: "wrap", gap: 1, minWidth: 0, ...densityVars("dense"), ...sx }}
    >
      {/* 단위는 목록이 센다 — 사람 목록은 「명」이다. 문구는 화면이 원래 쓰던 낱말 그대로다. */}
      <Typography component="span" variant="caption" color="text.secondary" sx={{ ...NUMERIC, whiteSpace: "nowrap" }}>
        {`${count}${unit} 선택`}
      </Typography>
      {children}
      {onClear ? <Button size="sm" variant="ghost" onClick={onClear}>{clearLabel}</Button> : null}
    </Box>
  );
}

/* 따라오는 발이 키보드 초점을 가리지 않게(WCAG 2.4.11) — 발이 서 있는 동안만 문서 스크롤 여백 아래를 발 높이 + 8 로 둔다.
   Tab 으로 아래 요소에 닿으면 브라우저는 그 요소를 화면 아래 끝에 붙여 보여 주는데, 거기에 발이 앉아 있다. 발이 걷히면
   규칙도 걷힌다. 목록 판 발(`ListFootBar`)과 폼 판 발(`ActionFooter sticky`)이 같이 쓴다. */
function StickyBottomPadding({ height }) {
  return <GlobalStyles styles={(theme) => ({ html: { scrollPaddingBottom: `calc(${height} + ${theme.spacing(1)})` } })} />;
}

/* 목록 판 안쪽 모서리 — 판 테두리(1px) 안에서 머리 · 발 칸이 둥근 모서리를 든다. 판이 `overflow: visible` 이라
   (sticky 머리 · 발이 서려면 그래야 한다) 판이 모서리를 잘라 주지 않는다. */
const LIST_INNER_RADIUS = `${RADIUS.md - 1}px`;

/* ── 목록 판 발 — 판 안 마지막 줄 (핸드오프 README §4 「발 줄 44px」 · RULES §5 · 조합 계약 C-3) ──────────────
 *
 * 왼쪽은 이 목록에 대해 **말하는 것**: 받은 건수 문장 · 숨긴 열 안내 · 뺀 열 안내 · 화면이 덧붙이는 한 줄.
 * 오른쪽은 **누르는 것**: 선택 묶음 · 「더 보기」(30 보조).
 *
 * 예전에는 받은 건수와 「더 보기」가 표 **밖** 가운데 상자(`ListFooter`)였고, 숨긴 열 안내는 표 **위**, 일괄 동작은
 * 화면 머리였다 — 한 목록의 끝을 말하는 것 넷이 세 자리에 흩어져 있었다. 이제 한 줄이다.
 *
 * `sticky` — 목록 판(surface)에서는 긴 목록을 내려가도 발이 화면 아래에 따라온다(`bottom: 0`). 그래서 이 줄 안에
 * 무한 스크롤 센티널을 두지 않는다 — 센티널은 표 끝 흐름에 선다(`listFooter.js` 머리 주석). */
function ListFootBar({ sentence, notes, selection, hasNext, isFetchingNext, onMore, moreLabel = "더 보기", sticky = false, rounded = false }) {
  return (
    <>
    {/* 🔴 따라오는 발은 키보드 초점을 가리면 안 된다(WCAG 2.4.11). Tab 으로 아래 행에 닿으면 브라우저는 그 행을 화면 아래
        끝에 붙여 보여 주는데, 거기에 발이 앉아 있다. 발이 서 있는 동안만 문서의 스크롤 여백 아래를 발 높이 + 8 만큼 비워
        초점이 발 위에 서게 한다. 발이 걷히면 규칙도 걷힌다. */}
    {sticky ? <StickyBottomPadding height={remPx(CONTROL.tableFooter)} /> : null}
    <Box
      data-list-footer=""
      data-list-footer-sticky={sticky ? "" : undefined}
      sx={{
        display: "flex", alignItems: "center", flexWrap: "wrap", columnGap: 1.5, rowGap: 0.5,
        minHeight: remPx(CONTROL.tableFooter), boxSizing: "border-box", px: 2, py: 0.75,
        borderTop: 1, borderColor: "divider", bgcolor: "background.plate",
        ...(sticky ? { position: "sticky", bottom: 0, zIndex: 2 } : null),
        ...(rounded ? { borderBottomLeftRadius: LIST_INNER_RADIUS, borderBottomRightRadius: LIST_INNER_RADIUS } : null),
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", columnGap: 1.5, rowGap: 0.25, minWidth: 0, flex: "1 1 auto" }}>
        {/* 묶음이 붙을 때마다 이 숫자가 다시 낭독된다. **포커스는 안 옮긴다** — 굴리던 자리를 화면이 빼앗지 않는다. */}
        {sentence ? (
          <Typography component="span" variant="caption" color="text.secondary" aria-live="polite" sx={NUMERIC}>
            {sentence}
          </Typography>
        ) : null}
        {notes}
      </Box>
      {selection}
      {hasNext ? <Button size="sm" loading={isFetchingNext} onClick={onMore}>{moreLabel}</Button> : null}
    </Box>
    </>
  );
}

/* ── 제목 칸 — 행을 여는 이름 (핸드오프 RULES §5 · 조합 계약 C-3) ────────────────────────────────────────
 *
 * 링크색(`primary.dark`) 600 한 줄, 넘치면 말줄임 + `title`. 예전에는 티켓 표만 이 모양이었고(`MyTickets.jsx` 의 지역
 * 부품), 게시판 · 휴지통 · 프로젝트 표의 제목은 잉크 글자라 **어느 것을 눌러야 열리는지** 표마다 달랐다.
 *
 *   onOpen  주면 진짜 단추(`Link component="button"`)다. 행 전체 클릭이 없는 표에서 여는 길이다
 *   href    주면 진짜 링크(`<a>`)다 — 새 탭으로 여는 자리(휴지통의 문서: 고른 줄과 일괄 선택을 들고 있는 표라 같은 탭에서
 *           나갔다 오면 선택이 사라진다). `target` · `rel` 을 함께 받는다
 *   link    `onOpen` · `href` 없이 링크색만 — 표가 행에 `<a href>` 를 이미 걸어 둔 자리(`DataTable rowHref`)
 *   셋 다 없으면 잉크 600 이다 — 열리지 않는 이름을 링크처럼 칠하지 않는다.
 *
 * QAH-03: 색을 `primary.main` 으로 주면 `MuiLink` 의 대비 보강(`primary.dark`)을 inline sx 가 덮어 다크 면에서 AA 에
 * 못 미쳤다. 값은 대비가 검증된 별칭이다. */
export function TitleCell({ title, fallback = "제목 없음", onOpen, href, target, rel, link = false, children, sx }) {
  const text = title || fallback;
  const base = {
    fontWeight: FONT_WEIGHT.semibold, textAlign: "left", display: "block", maxWidth: "100%",
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  };
  if (href) {
    return (
      <Link href={href} target={target} rel={rel} underline="hover" data-title-cell="anchor" title={text} sx={{ ...base, color: "primary.dark", ...sx }}>
        {children || text}
      </Link>
    );
  }
  if (onOpen) {
    return (
      <Link
        component="button"
        type="button"
        underline="hover"
        data-title-cell="button"
        onClick={onOpen}
        title={text}
        sx={{ font: "inherit", ...base, color: "primary.dark", ...sx }}
      >
        {children || text}
      </Link>
    );
  }
  return (
    <Box component="span" data-title-cell={link ? "link" : "text"} title={text} sx={{ ...base, ...(link ? { color: "primary.dark" } : null), ...sx }}>
      {children || text}
    </Box>
  );
}

/* ── 행 동작 — 표 행 안의 단추 묶음 (핸드오프 RULES §5 「행 안 동작은 30px, 둘을 넘으면 더 보기 하나」 · 조합 계약 C-4) ──
 *
 * `actions`: `[{ key, label, onClick, variant: "default" | "danger", disabled, loading, ariaLabel, icon }]`
 *
 * - 둘 이하면 30 단추로 선다. **채움은 없다** — 「나에게 배정」「복원」「승인」이 행마다 채움이었을 때 목록 한 화면에
 *   채움이 스무 개 섰고, 화면의 할 일(머리의 채움 하나)이 어디인지 사라졌다. `variant` 는 보조(default)와 파괴(danger)
 *   둘뿐이고, 다른 값은 보조로 선다.
 * - 셋 이상이면 「더 보기」(`OverflowMenu size="sm"`) 하나로 접는다. 파괴 항목은 메뉴 안에서 실선으로 갈린다.
 * - `icon` 을 준 항목은 30 아이콘 단추다(좁은 열 — 홈의 핵심 열 표). 이름은 `ariaLabel` 이 든다.
 *
 * `data-row-actions` 는 실브라우저 조합 검사(`row_actions`)가 행 동작을 찾는 표식이다. */
export function RowActions({ actions, ariaLabel = "행 작업 더 보기", max = 2 }) {
  const list = (actions || []).filter(Boolean);
  if (!list.length) return null;
  const wrap = { display: "inline-flex", alignItems: "center", gap: 1, flexWrap: "nowrap", verticalAlign: "middle" };
  if (list.length > max) {
    return (
      <Box data-row-actions="" sx={wrap}>
        <OverflowMenu
          size="sm"
          ariaLabel={ariaLabel}
          items={list.map((a, i) => ({
            key: a.key || a.label || i, label: a.label, onClick: a.onClick, disabled: a.disabled,
            tone: a.variant === "danger" ? "danger" : undefined,
          }))}
        />
      </Box>
    );
  }
  return (
    <Box data-row-actions="" sx={wrap}>
      {list.map((a, i) => (a.icon ? (
        <IconButton
          key={a.key || a.label || i}
          size="small"
          aria-label={a.ariaLabel || a.label}
          disabled={a.disabled}
          onClick={a.onClick}
        >
          {a.icon}
        </IconButton>
      ) : (
        <Button
          key={a.key || a.label || i}
          size="sm"
          variant={a.variant === "danger" ? "danger" : "default"}
          disabled={a.disabled}
          loading={a.loading}
          aria-label={a.ariaLabel}
          onClick={a.onClick}
        >
          {a.label}
        </Button>
      )))}
    </Box>
  );
}

/* ── 표의 자리 — `placement` (UI 3차 · 조합 계약 C-3) ────────────────────────────────────────────────
 *
 *   surface  목록 화면의 주 목록. **판 = 표 상자**다 — 판 여백 0, 머리 40 이 판 윗변 · 좌우 가장자리에 붙고, 발(최소 44)이
 *            판 안 마지막 줄이며 긴 목록에서 화면 아래에 따라온다(sticky). 빈 상태 · 불러오는 중은 판 안 여백 20 이다.
 *   card     제목 있는 판(`Card`) 안의 보조 표. 머리 · 발이 판 여백을 거슬러 판 가장자리까지 편다(`ActionFooter card` 와
 *            같은 규칙). 발은 따라오지 않는다.
 *   plain    (기본) 모달 · 서랍 · 보호 화면(홈 · 내 업무량)의 표. 예전 모양 그대로다 — 판을 그리지 않는다.
 *
 * 예전에는 표에 판 계약이 없었다. 주 목록 스무 곳이 `Card`(여백 20)/`ListCard` 로 감싸 머리 줄이 판 가장자리에서
 * 떨어졌고, 받은 건수와 「더 보기」는 판 밖 가운데, 숨긴 열 안내는 표 위, 일괄 동작은 화면 머리에 섰다. 부품은 전부
 * 정본인데 조합이 화면마다 달랐다. 이제 표가 자기 자리를 안다.
 *
 * 발에 들어가는 것:
 *   list       `{ total, loaded, hasNext, isFetchingNext, onMore, moreLabel, unit, autoMaxRows, root }` — 쪽을 나눠 받는
 *              목록. 받은 건수 문장 · 「더 보기」 · 자동 로딩(센티널은 표 끝 흐름). 판이 있는 표에서 안 주면 받은 행
 *              수로 같은 문장을 쓴다(두 줄 미만이면 안 그린다).
 *   selection  `{ count, onClear, actions }` — 고른 행에 할 일(`SelectionBar`).
 *   note       발 왼쪽에 덧붙는 한 토막(프로젝트 문서의 「총 N건 가운데 …」 같은 결과 문장).
 * 발에 그릴 것이 하나도 없으면 발 줄 자체를 안 그린다. */
/* `fill` — 작업 공간 판 몸을 채우는 표(F5 · D-531). 표 상자가 남은 높이를 받아 두 축으로 직접 굴리고, 열 이름은 그 상자 위에 붙으며,
   무한 받기 감시점은 상자 안에 서고(판을 열자마자 끝까지 받지 않게), 발(건수 · 「더 보기」)은 상자 아래에 고정이다. 판(`WorkspacePane
   body="table"`) 안에서만 쓴다 — 문서 흐름 페이지의 표는 창이 굴린다. */
const FILL_FRAME = { flex: "1 1 auto", minHeight: 0, display: "flex", flexDirection: "column" };

export function DataTable({ columns, rows, rowKey, onRow, rowHref, rowSelected, groupOf, groupCollapsible, groupSlots, empty, emptyState, emptyAction, ellipsis, stickyHeader, loading, sort, onSort, resultScope, filters, filterValueOf, onFilter, filterOptions, entityOptions, virtualize, total, rowHeight, placement = "plain", list, selection, note, fill: fillAsked = false }) {
  /* `fill` 은 「채움 작업 공간이면 판 몸을 채워 직접 굴린다」다(D-531). 흐름(좁거나 낮은 창)의 판은 문서와 함께 흐르므로 표도
     흐른다 — 높이 제한 없는 표 상자를 스크롤 창으로 두면 굴러가지 않고, 그 안의 감시점이 늘 보여 끝까지 받는다. */
  const workspaceMode = React.useContext(WorkspaceModeContext);
  const fill = fillAsked && workspaceMode !== false;
  // §15.1 재검수 — `VirtualTableBody` 는 스크롤 창을 스스로 안 만든다(문서 전체가 표
  // 흐름을 지키게, `VirtualRows`와 다른 이유는 그 부품 docblock 참고). 이 상자가 그 창
  // 이다 — `virtualize` 를 안 쓰면 아무도 안 읽는다(회귀 0).
  //
  // 🔴 평범한 `useRef` 가 아니라 `useState` + 콜백 ref 다. `TableContainer`(조상)의 DOM
  // 노드는 이 컴포넌트 자신이 아니라 그 **자손**(`VirtualTableBody`)이 읽는데, React 는
  // 커밋을 자손→조상 순서로 처리한다(레이아웃 이펙트도 같다) — 평범한 ref 였다면
  // `VirtualTableBody` 의 첫 레이아웃 이펙트가 도는 시점에 이 조상 ref 는 아직 안 붙어
  // 있어, react-virtual 이 그 순간의 null 값을 그대로 확정해 버리고 다시 안 돈다(제
  // 라이브러리 소스로 확인함 — 실제로 겪은 결함이다: 60건 넘는 표가 행을 하나도 못
  // 그렸다). 콜백 ref 로 노드를 state 에 담으면, 그 노드가 실제로 붙는 순간 **state
  // 갱신 → 리렌더**가 일어나 `VirtualTableBody` 가 이번에는 값이 있는 채로 다시 돈다. */
  const [scrollEl, setScrollEl] = React.useState(null);
  /* 접을 수 있는 묶음은 **닫힌 채 시작한다**(`groupCollapsible`). 스프린트 회의처럼 담당자가
     많으면 표 하나가 11,000px 를 넘어 한 화면에 다 들어가던 자리다 — 한 사람씩 펼쳐 가는
     흐름을 준다. 「열린 묶음」만 추적하는 이유: 묶음 이름 전체를 state 초기화 시점에 몰라도
     되고, 행이 바뀌어 새 묶음이 생겨도 자동으로 닫힌 채 시작한다. */
  const [openGroups, setOpenGroups] = React.useState(() => new Set());
  const isGroupOpen = (key) => !groupCollapsible || openGroups.has(key);
  const toggleGroup = (key) => setOpenGroups((s) => {
    const next = new Set(s);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  /* 스크롤 창이 어디인가 — 이 표의 두 모드.
   *
   *   window(기본) 문서가 굴러간다. 이 앱의 셸이 그렇다(`AppShell` 은 `main` 에 overflow 를
   *                안 준다). 스크롤바가 하나이고, `lib/listReturn.js` 의 스크롤 복원이 그대로
   *                산다(그 파일은 `window.scrollY` 만 안다).
   *   box          이 상자가 굴러간다. **스스로 높이를 가진 자리**만 쓴다 — 작업 보드 레인은
   *                「칸 안에서만 굴러가고 페이지는 안 밀린다」가 요구다.
   *
   * `height` 를 주면 box 다(옛 호출부 호환). 아무것도 안 주면 window 다. */
  /* 채움 표는 상자가 스크롤 창이라 가상화도 상자 갈래다(높이는 판이 준다). */
  const virtualBox = !!(virtualize && (virtualize.mode === "box" || virtualize.height || fill));
  const virtualWindow = !!virtualize && !virtualBox;
  const scrollMargin = useScrollMargin(virtualWindow ? scrollEl : null);
  /* 표가 자기 칸보다 넓은가 — 넘침을 바깥으로 넘길지 말지가 여기서 갈린다.
   *
   * 🔴 CSS 는 `overflow-x: auto; overflow-y: visible` 을 허용하지 않는다 — 한쪽이 `visible`
   * 이 아니면 나머지 `visible` 도 `auto` 로 계산된다. 그래서 「가로는 이 상자가 굴리고
   * 세로 넘침은 바깥에 넘긴다」는 **한 요소 안에서 성립할 수 없다.** 둘 중 하나다.
   *
   * 그러면 무엇을 고르는가. 표가 칸 안에 들어가면 가로 스크롤 창이 애초에 필요 없으니
   * 넘김(=고정 열 이름이 바깥 창을 따라간다)을 고른다. 표가 칸보다 넓으면 다르다 —
   * 넘김을 고르면 표가 판 밖으로 삐져나와 **옆 사이드바 위에 겹쳐 그려진다**(문서 목록에서
   * 130px 을 쟀다). 그 자리는 오늘처럼 이 상자가 가로로 굴러야 한다. 고정 열 이름은
   * 그 화면에서 원래도 안 따라왔으므로 잃는 것이 없다.
   *
   * 되먹임은 없다: 두 모드 다 표 너비도 칸 너비도 안 바꾼다(가로 스크롤바는 높이만 먹는다). */
  const measureRef = React.useRef(null);
  const [xOverflow, setXOverflow] = React.useState(false);
  React.useLayoutEffect(() => {
    const box = scrollEl;
    const table = measureRef.current;
    if (!box || !table || typeof ResizeObserver === "undefined") return undefined;
    const measure = () => {
      setXOverflow(Math.ceil(table.getBoundingClientRect().width) > box.clientWidth + 1);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(box);
    ro.observe(table);
    return () => ro.disconnect();
  }, [scrollEl]);
  // 방어: 비정상 입력이 와도 렌더 중 throw하지 않고 빈-목록 안내로 폴백한다.
  // 공용 표라 한 화면의 실수나 API shape 변화가 전역 크래시로 번지지 않게 한다.
  const declaredCols = Array.isArray(columns) ? columns : [];
  const safeRows = Array.isArray(rows) ? rows : [];
  /* 열을 뺄지 말지는 **호출부가 준 질의 계약**으로만 판단한다 (R-91).
     `resultScope` 가 없으면 `removed` 가 언제나 비어 있어 이 줄은 아무 것도 안 한다 —
     즉 이 기능을 안 쓰는 화면 28개의 렌더는 한 픽셀도 안 바뀐다. */
  const collapse = planColumnCollapse(
    declaredCols,
    resultScope && resultScope.serverPaged ? safeRows.slice(0, COLLAPSE_SAMPLE) : safeRows,
    resultScope,
  );
  const dropped = collapse.removed.map((r) => r.key);
  const shrunk = collapse.shrink;
  /* 「우연히 같다」로 판정된 열은 **빼지 않고 줄인다** — 폭을 내용만큼으로 좁히고 좁은
     화면의 숨김 후보로 표시한다. 사용자는 열이 사라지는 것을 못 따라가지만, 좁아지는
     것은 따라간다. */
  const baseCols = (dropped.length
    ? declaredCols.filter((c) => dropped.indexOf(c.key) < 0)
    : declaredCols
  ).map((c) => (shrunk.indexOf(c.key) >= 0 ? { ...c, width: SHRINK, hideNarrow: true } : c));
  const cols = baseCols;
  const keyOf = typeof rowKey === "function" ? rowKey : (_, i) => i;
  const narrow = useMediaQuery(TABLE_CARD_QUERY);
  /* 열을 접는 판단은 **이 표가 받은 칸**이 한다 (D-380). 뷰포트가 아니다 — 문서 목록의
     표는 1920 에서도 자기 칸이 902px 이라 넘쳤고, 옛 규칙(900~1200)은 그때 아무 열도
     안 뺐다. 카드 뷰는 안 건드린다: 폭 제약이 없는 카드에서 열을 빼면 정보만 준다. */
  /* 🔴 **지금 정렬 중인 열은 숨기지 않는다.**
   *
   * 열 배분(`planColumns`)은 칸이 좁으면 문맥 · 보조 열을 숨긴다. 그런데 그 열이 지금 목록을 세우고 있는 축이면, 머리행이
   * `wideCols` 로만 그려지므로 **정렬 화살표와 정렬 단추와 `aria-sort` 가 통째로 사라진다** — 휴지통에서 기본 축(삭제일)이
   * 정확히 그렇게 가장 먼저 빠졌다. 정렬 중인 열은 필수 등급이다(`columnPlan.columnTier`) — 그 열이 자리를 차지하므로 다른
   * 보조 열이 대신 숨는다. */
  const sortKey = sort && sort.key;
  const fit = useFittedColumns(baseCols, narrow ? null : scrollEl, {
    sortKey, sortGlyph: !!onSort, filterGlyph: !!onFilter, rows: safeRows,
  });
  const wideCols = fit.shown;
  const stickyCols = stickyColumnsOf(wideCols, fit);
  // 값 자체는 행을 열면(onRow) 상세에서 그대로 보인다 — 여기서는 "더 있다"는 사실만 알린다.
  const hiddenCols = fit.hidden;

  /* 판이 있는 표(surface · card)는 발이 표의 일부다. 쪽을 나누는 목록은 `list` 가, 전량 목록은 받은 행 수가 건수를
     말한다. 판 없는 표(plain)는 `list` 를 줄 때만 발을 그린다 — 모달 · 서랍 · 보호 화면의 표가 조용히 바뀌지 않게. */
  const framed = placement === "surface" || placement === "card";
  /* 결과 문장을 스스로 가진 목록(프로젝트 문서의 「총 N건 가운데 …」 · 오프보딩 대상의 「N명 중 M명을 보여 줍니다」)은
     `note` 가 발 문장이다 — 쪽을 나누지 않는 목록에 받은 행 수 문장을 한 번 더 세우지 않는다. */
  /* `list={false}` — 서버가 앞 몇 건만 잘라 주는 미리보기 목록(대시보드 「최근 주요 변경」 · 「전체 보기」로 넘기는 판)은
     건수를 말하지 않는다. 「5건 중 5건」은 그 목록에서 사실이 아니다. */
  const footSpec = list === false ? null : (list
    || (framed && !note ? { total: total != null ? total : safeRows.length, loaded: safeRows.length } : null));
  /* 채움 표의 감시점은 표 상자(실제로 굴리는 조상)를 기준으로 본다. */
  const foot = useListFooter(footSpec ? (fill ? { ...footSpec, root: "auto" } : footSpec) : { enabled: false });
  const selectionBar = selection && selection.count
    ? (
      <SelectionBar count={selection.count} unit={selection.unit} clearLabel={selection.clearLabel} onClear={selection.onClear}>
        {selection.actions}
      </SelectionBar>
    )
    : null;
  const footNotes = [];
  /* 발이 있는 표(판 위 표 · 작업 공간 판의 채움 표)는 숨긴 열 안내를 발에 둔다 — 채움 표의 발은 판 아래 고정 줄이다(D-531). 표 위
     한 줄로 두면 고정 도구 줄이 그만큼 길어져 1366 판에서 표 행 하나를 먹었다(P17V). */
  const footed = framed || fill;
  if (footed && hiddenCols.length) {
    footNotes.push(<HiddenColumnsNote key="hidden" inline columns={hiddenCols} openable={!!onRow || !!rowHref} />);
  }
  if (footed && collapse.caption) {
    footNotes.push(
      <Typography key="collapsed" component="span" variant="caption" color="text.secondary" data-collapsed-columns={dropped.join(",")}>
        {collapse.caption}
      </Typography>,
    );
  }
  if (note) {
    footNotes.push(
      <Typography key="note" component="span" variant="caption" color="text.secondary" data-list-note="">{note}</Typography>,
    );
  }
  const hasFoot = !!(foot.sentence || footNotes.length || selectionBar || foot.hasNext);
  const footBar = (sticky) => (hasFoot ? (
    <ListFootBar
      sentence={foot.sentence}
      notes={footNotes}
      selection={selectionBar}
      hasNext={foot.hasNext}
      isFetchingNext={foot.isFetchingNext}
      onMore={foot.more}
      moreLabel={list && list.moreLabel}
      sticky={sticky}
      rounded={placement === "surface"}
    />
  ) : null);
  /* 자동 로딩 센티널 — 표 끝 **흐름**에 선다(발 안이 아니다, `listFooter.js` 머리 주석). 1px 을 위로 겹쳐 자리를 안
     먹는다. 🔴 `height: 1` 이 아니라 `"1px"` 이다 — MUI sx 는 1 이하 숫자를 백분율로 옮긴다. */
  const sentinel = foot.hasNext ? (
    <Box ref={foot.sentinelRef} aria-hidden="true" data-list-sentinel="" sx={{ height: "1px", mt: "-1px", pointerEvents: "none" }} />
  ) : null;
  /* 판 — surface 는 표 상자 자체, card 는 판 여백을 거슬러 가장자리까지 편 띠. `state` 가 있으면(불러오는 중 · 빈 목록)
     안에 표가 없으므로 판 여백 20 안에 선다. */
  /* `padded` — 판 여백 안에 서는가. 표가 없는 상태(불러오는 중)는 여백 안이고, 표가 있으면(빈 표의 머리 + 빈 띠 포함) 표가
     판 가장자리에 붙는다. */
  const frame = (children, state, padded = !!state) => {
    if (placement === "surface") {
      return (
        <Surface
          tone="plate"
          data-list-surface=""
          data-table-placement="surface"
          data-list-state={state}
          sx={{ p: padded ? CARD_PADDING : 0, overflow: "visible", minWidth: 0, ...(fill && !padded ? FILL_FRAME : null) }}
        >
          {children}
        </Surface>
      );
    }
    if (placement === "card") {
      return (
        <Box
          data-table-placement="card"
          data-list-state={state}
          /* 좌우만 판 여백을 거스른다. 아래를 함께 거스르면(`:last-child` 음수 여백) 표를 감싼 상자 뒤에 오는 줄을 20px
             끌어올려 겹친다 — 판 아래 여백은 판의 것으로 둔다. */
          sx={padded ? { minWidth: 0 } : { minWidth: 0, mx: `calc(-1 * ${CARD_PADDING})`, ...(fill ? FILL_FRAME : null) }}
        >
          {children}
        </Box>
      );
    }
    return padded ? children : (
      <Box data-table-placement="plain" data-list-state={state} data-table-fill={fill ? "" : undefined} sx={{ minWidth: 0, ...(fill ? FILL_FRAME : null) }}>
        {children}
      </Box>
    );
  };

  /* 로딩 모양을 표가 스스로 안다 (지시 20). 호출부가 각자 `<Skeleton lines={6} />` 을 두면
     열 수도 행 높이도 표와 다르고, 무엇보다 **빈 목록과 아직 안 온 목록이 같아 보인다** -
     "없다"와 "아직 모른다"는 다른 사실이다. */
  /* 뼈대는 300ms 뒤에 보인다(D-530) — 빠른 응답에 뼈대가 번쩍였다 사라지지 않게. 자리는 처음부터 차지한다. */
  if (loading) return frame(<DelayedReveal><Skeleton kind="table" cols={wideCols.length || baseCols.length} /></DelayedReveal>, "loading");

  /* 빈 표 (F4 · D-530) — 머리는 그대로 서고, 그 아래 한 줄 띠가 「왜 비었는지 · 무엇을 하면 되는지」를 말한다.
     「정말 없다」와 「조건 때문에 없다」는 다른 사실이고, 그 판정은 필터를 든 화면이 안다 — `emptyState` 를 주면 그것을 띠 자리에
     그리고(그 안의 `EmptyState` 는 띠로 선다), 안 주면 `empty` 문장과 `emptyAction`(30 단추)이다. 예전에는 머리 없이 판 안에 빈 상태
     부품이 섰고, 화면마다 큰 그림 · 긴 설명이 판을 흰 면으로 채웠다. */
  const isEmpty = safeRows.length === 0;
  const bandContent = isEmpty
    ? (emptyState || <EmptyState title={empty || "표시할 항목이 없습니다."} action={emptyAction} />)
    : null;
  if (isEmpty && narrow) {
    /* 좁은 화면(카드 목록)에는 머리가 없다 — 판 여백 안에 띠만 선다. 이 묶음이 통째로 걸러져 비었는데 서버에 더 있으면
       「더 보기」는 남긴다 — 키보드 · 스크린리더 사용자는 무한 스크롤에 닿을 수 없다. */
    const emptyFoot = foot.hasNext ? <>{sentinel}{footBar(false)}</> : null;
    return frame(<><TableEmptyBandCtx.Provider value={BAND_IN_PLATE}>{bandContent}</TableEmptyBandCtx.Provider>{emptyFoot}</>, "empty");
  }

  /* 행을 묶음 순서로 훑어 «머리행이 설 자리»를 찾는다 — 표와 카드가 **같은 계산**을 본다.
     좁은 화면에서만 다른 묶음이 보이거나 건수가 달라지면 그 자체가 결함이다. */
  const groupPlan = groupOf
    ? (() => {
      const items = safeRows.map((row, i) => normalizeGroup(groupOf(row, i)));
      const counts = new Map();
      items.forEach((g) => { if (g) counts.set(g.key, (counts.get(g.key) || 0) + 1); });
      return { items, counts };
    })()
    : null;
  /** 이 행 앞에 묶음 머리행이 서야 하는가 — 서야 하면 그 묶음을 돌려준다. */
  const groupOpeningAt = (i, prevKey) => {
    const g = groupPlan && groupPlan.items[i];
    if (!g || g.key === prevKey) return null;
    return { ...g, count: g.count != null ? g.count : groupPlan.counts.get(g.key) };
  };
  /* 비어 있어도 서는 묶음(`groupSlots`, 선택) — 묶음의 갈래가 정해진 표(정책의 종류 셋, D-542)는 행이 없는 갈래도
     머리와 한 줄(「이 종류의 규칙이 없습니다.」)로 세운다. 그래야 「승인 필요 규칙이 없다」가 「그런 종류가 없다」와
     갈린다. 순서는 `groupSlots` 의 순서이고, 행이 있는 묶음 사이 제자리에 끼운다. 표와 카드가 같은 계산을 본다. */
  const slotPlan = groupPlan && Array.isArray(groupSlots) && groupSlots.length
    ? (() => {
      const slots = groupSlots
        .map((s, order) => { const g = normalizeGroup(s); return g ? { ...g, order, emptyText: s.emptyText } : null; })
        .filter(Boolean);
      return {
        empties: slots.filter((s) => !groupPlan.counts.has(s.key)),
        orderOf: new Map(slots.map((s) => [s.key, s.order])),
      };
    })()
    : null;
  /** `untilKey` 묶음 앞에 와야 하는 빈 묶음들(아직 안 그린 것). `untilKey` 가 없으면 남은 전부. */
  const emptySlotsBefore = (untilKey, drawn) => {
    if (!slotPlan) return [];
    const limit = untilKey == null ? Infinity : (slotPlan.orderOf.has(untilKey) ? slotPlan.orderOf.get(untilKey) : Infinity);
    const due = slotPlan.empties.filter((s) => !drawn.has(s.key) && s.order < limit);
    due.forEach((s) => drawn.add(s.key));
    return due;
  };
  const EMPTY_SLOT_TEXT = "이 묶음에 항목이 없습니다.";

  /* 좁은 화면에서는 표를 카드 목록으로 바꾼다. 가로 스크롤되는 표는 손가락으로 훑기 어렵고,
   * 열 이름이 화면 밖으로 나가면 어떤 값인지 알 수 없다. 카드에서는 라벨을 값 옆에 붙인다. */
  if (narrow) {
    /* 카드 뷰에서 **머리행에 해당하는 것**을 목록 위에 한 번 둔다 (W5). 열 `label` 이
       낱말이 아니라 조작기인 열(선택 열)이 있고, 그것을 카드마다 반복하면 조작기가 행 수만큼
       늘어난다 — 「전체 선택」이 카드마다 하나씩 생겨 아무거나 누르면 전부가 선택됐다.
       열이 스스로 `cardHeader` 로 «이건 목록 전체의 조작기다» 라고 말하게 한다. */
    const cardHeads = cardHeaderControls(cols);
    let seenGroup = null;
    const drawnSlots = new Set();
    const emptySlotCards = (due) => due.map((s) => (
      <Box key={`clv-group-empty:${s.key}`} data-group-empty={s.key}>
        <Typography component="h3" sx={{ fontSize: FONT_SIZE.body }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
            <Box component="span" sx={{ fontWeight: FONT_WEIGHT.bold, ...KO_WORD_BREAK }}>{s.label}</Box>
            <GroupHeaderMeta group={{ ...s, count: 0 }} />
          </Box>
        </Typography>
        <Typography sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", mt: 0.5, ...KO_WORD_BREAK }}>
          {s.emptyText || EMPTY_SLOT_TEXT}
        </Typography>
      </Box>
    ));
    return (
      <FlatBadgeSurface>
      <Stack gap={1.5}>
        {cardHeads.length ? (
          <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1.5, px: 0.5 }}>
            {cardHeads.map((c) => <React.Fragment key={c.key}>{c.cardHeader}</React.Fragment>)}
          </Box>
        ) : null}
        {safeRows.map((row, i) => {
          const ctx = { rowName: rowNameOf(baseCols, row) };
          /* 카드에서도 묶음은 묶음이다 — 표에서만 묶고 좁은 화면에서는 한 줄로 쏟아 놓으면
             같은 목록이 두 개의 이야기를 한다. 머리는 `<h3>` 이라 개요 탐색에도 남는다. */
          const opening = groupOpeningAt(i, seenGroup);
          if (opening) seenGroup = opening.key;
          const g = groupPlan && groupPlan.items[i];
          const heading = opening ? (
            <Typography component="h3" key={`clv-group:${opening.key}`} sx={{ fontSize: FONT_SIZE.body, mt: i ? 1 : 0 }}>
              {groupCollapsible ? (
                <Box
                  component="button" type="button" aria-expanded={isGroupOpen(opening.key)}
                  onClick={() => toggleGroup(opening.key)}
                  sx={{
                    all: "unset", display: "block", width: "100%", cursor: "pointer",
                    "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
                  }}
                >
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
                    <ExpandMoreRoundedIcon
                      fontSize="small" aria-hidden="true"
                      sx={{ flexShrink: 0, transform: isGroupOpen(opening.key) ? "none" : "rotate(-90deg)", transition: `transform ${MOTION.fast} ${MOTION.ease}` }}
                    />
                    <Box component="span" sx={{ fontWeight: FONT_WEIGHT.bold, ...KO_WORD_BREAK }}>{opening.label}</Box>
                    <GroupHeaderMeta group={opening} />
                  </Box>
                </Box>
              ) : (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
                  <Box component="span" sx={{ fontWeight: FONT_WEIGHT.bold, ...KO_WORD_BREAK }}>{opening.label}</Box>
                  <GroupHeaderMeta group={opening} />
                </Box>
              )}
            </Typography>
          ) : null;
          const before = opening ? emptySlotCards(emptySlotsBefore(opening.key, drawnSlots)) : null;
          if (g && !isGroupOpen(g.key)) return before && before.length ? <React.Fragment key={`clv-gwrap:${i}`}>{before}{heading}</React.Fragment> : heading;
          const card = (
            <Paper
              key={keyOf(row, i)}
              variant="outlined"
              onClick={onRow ? (e) => { if (e.target.closest("a,button")) return; onRow(row); } : undefined}
              onKeyDown={onRow ? (e) => { if (e.target.closest("a,button")) return; if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRow(row); } } : undefined}
              tabIndex={onRow ? 0 : undefined}
              aria-label={onRow ? rowOpenLabel(baseCols, row) : undefined}
              sx={{ p: 2, display: "grid", gap: 0.75, cursor: onRow ? "pointer" : "default" }}
            >
              {cols.map((c) => {
                /* `overflowWrap:anywhere` 만 걸면 한글이 음절 단위로 끊긴다 - 영문에서는
                   안 생기는 일이라 눈에 잘 안 띈다. 단어는 지키고 긴 토큰만 끊는다. */
                const value = rowHref && onRow && (c.type === "title" || c.rowLink) ? (
                  <Box
                    component="a"
                    {...rowAnchorProps(rowHref(row), () => onRow(row))}
                    sx={{ minWidth: 0, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK, display: "block", color: "inherit", textDecoration: "none" }}
                  >
                    {cellValue(c, row, ctx)}
                  </Box>
                ) : (
                  <Box sx={{ minWidth: 0, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}>{cellValue(c, row, ctx)}</Box>
                );
                /* 이름이 없는 열(선택 체크박스·행 작업)은 **이름 자리를 비우지 않고 없앤다** —
                   빈 7rem 트랙을 남기면 값이 카드 한가운데에서 시작해 다른 줄과 안 맞는다. */
                if (!c.label) return <Box key={c.key} sx={{ minWidth: 0 }}>{value}</Box>;
                return (
                  <Box key={c.key} sx={{ display: "grid", gridTemplateColumns: "7rem minmax(0,1fr)", gap: 1, alignItems: "start" }}>
                    {/* 이름 자리에는 **낱말**만 온다. 열이 `cardLabel` 로 말해 주면 그것을 쓴다
                        — `label` 이 조작기인 열(선택 열)이 이 자리에 오면 카드마다 그 조작기가
                        복제된다(위 `cardHeads` 주석). */}
                    <Typography variant="caption" color="text.secondary">{cardFieldLabel(c)}</Typography>
                    {value}
                  </Box>
                );
              })}
            </Paper>
          );
          if (!heading) return card;
          return <React.Fragment key={`clv-grouped:${opening.key}`}>{before}{heading}{card}</React.Fragment>;
        })}
        {emptySlotCards(emptySlotsBefore(null, drawnSlots))}
      </Stack>
      {/* 카드 뷰에도 목록의 끝은 있다 — 받은 건수 · 「더 보기」 · 선택 묶음. 판이 없는 카드 목록이라 따라오지 않는다. */}
      {sentinel}
      {hasFoot ? <Box data-table-placement={placement} sx={{ mt: 1.5 }}>{footBar(false)}</Box> : null}
      </FlatBadgeSurface>
    );
  }

  /* 셀 안의 링크/버튼 클릭이 행 클릭(상세 열기)으로 번지지 않게 막는다 —
     문서 '발행 링크'를 누르면 새 탭이 열리면서 상세까지 같이 열리던 이중 동작.
     같은 이유로 키보드 Enter/Space도 셀 안의 실제 버튼·링크에서 눌렀으면
     행 전체의 onRow를 다시 부르지 않는다(그 버튼 자신의 키보드 활성화가
     이미 처리한다). PA-RC-0023: role="button"은 일부러 안 준다 — 이 행 안에
     재시도/취소 같은 진짜 버튼이 함께 있는 표가 있어(registry 행 액션),
     role=button 위에 포커스 가능한 자손을 두는 것은 WAI-ARIA 금지다
     (StatusTile의 같은 이유 참고, adminKit.jsx). tabIndex + aria-label +
     Enter 처리만으로 키보드 도달을 준다.
     `virtualize`(§15.1)와 평범한 렌더 둘 다 이 함수 하나를 쓴다 — 가상화가
     행 하나를 다르게 그리면 그 자체가 회귀다. */
  function renderDataRow(row, i) {
    // 행마다 한 번만 구한다 — 셀마다 다시 구하면 열 수만큼 같은 계산을 반복한다.
    const ctx = { rowName: rowNameOf(baseCols, row) };
    return (
      <TableRow
        key={keyOf(row, i)}
        hover={!!onRow}
        /* 고른 행은 **hover 와 같은 한 단계**로만 말한다(아래 `Mui-selected` 규칙).
           MUI 기본값은 primary 를 옅게 깐 면이라 hover 와 색이 갈리는데, 표에서 그 둘이
           다른 색이면 「고른 것」과 「지금 마우스가 있는 것」이 같은 세기로 경쟁한다. */
        selected={rowSelected ? !!rowSelected(row) : undefined}
        onClick={onRow ? (e) => { if (e.target.closest("a,button")) return; onRow(row); } : undefined}
        onKeyDown={onRow ? (e) => { if (e.target.closest("a,button")) return; if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRow(row); } } : undefined}
        tabIndex={onRow ? 0 : undefined}
        aria-label={onRow ? rowOpenLabel(baseCols, row) : undefined}
        /* `rowHeight="tall"` — 제목 + 요약 + 태그처럼 두 줄 이상인 행의 **바닥** 76(`CONTROL.tableRowTall`).
           고정 높이가 아니다: 표 칸의 `height` 는 최솟값이라 내용이 더 필요하면 행이 자란다. */
        sx={{ cursor: onRow ? "pointer" : "default" }}
      >
        {wideCols.map((c) => {
          /* HOST-01/HOST-02/VIS-73 — 열 폭이 순수하게 내용에서 파생되던 게 두 방향 모두에서
             문제였다: ① 값 하나가 길면 그 셀이 51px×2,353px까지 벌어지고 같은 행의 다른
             셀도 그 높이로 끌려간다(HOST-01, truncateCol이 있는 자리에만 부분 적용돼 있었다)
             ② 열이 많으면 `overflowWrap:anywhere`가 각 열을 '한 글자' 폭까지 짜부라뜨린다
             (VIS-73). `c.render`가 있는 열(배지·버튼·직접 JSX)은 이미 자기 폭을 스스로
             관리하므로 건드리지 않는다 — 값을 있는 그대로 보여주는 순수 텍스트 열만 기본을
             말줄임으로 바꾼다(`truncateCol`이 문자 수 기준으로 이미 하던 것과 같은 방향,
             이제 그걸 안 쓴 나머지 열에도 `DataTable` 자신이 최소한의 보호를 준다).
             `title`로 전체 값은 그대로 hover에 남는다 — truncateCol과 같은 힌트 패턴. */
          const truncate = columnShouldTruncate(c, ellipsis);
          const raw = !c.render ? cellValue(c, row, ctx) : null;
          const plain = c.render && (typeof row[c.key] === "string" || typeof row[c.key] === "number")
            ? String(row[c.key])
            : null;
          const hint = columnCellHint(c, row, ctx, { truncate, raw, plain });
          const content = raw != null ? raw : cellValue(c, row, ctx);
          const body = wrapTableCellContent(
            rowHref && onRow && (c.type === "title" || c.rowLink) ? (
              <Box
                component="a"
                {...rowAnchorProps(rowHref(row), () => onRow(row))}
                sx={{ display: "block", color: "inherit", textDecoration: "none" }}
              >
                {content}
              </Box>
            ) : content,
            { truncate, hint },
          );
          const sticky = stickyCols && stickyCols[c.key] != null
            ? { position: "sticky", left: stickyCols[c.key], zIndex: 1 } : null;
          return (
            <TableCell
              key={c.key}
              align={resolveColumn(c).align}
              data-col-role={colRole(c)}
              data-sticky-col={sticky ? "" : undefined}
              title={!truncate && hint ? hint : undefined}
              sx={{
                ...colCellSx(c, { truncate }),
                ...(rowHeight === "tall" ? { height: remPx(CONTROL.tableRowTall) } : null),
                ...sticky,
              }}
            >
              {body}
            </TableCell>
          );
        })}
      </TableRow>
    );
  }

  /* 묶음 머리행을 끼운 본문.
   *
   * 🔴 **가상화와 함께 쓸 수 없다.** 가상화는 행 하나를 인덱스로 세어 높이를 추정하는데,
   * 중간에 다른 높이의 줄이 끼면 그 추정이 틀어져 스크롤이 튄다. 지금 묶음이 필요한 표
   * 둘(내 티켓 묶음 목록·개발 리포트 담당자별)은 가상화를 안 쓰고, 가상화를 쓰는 표
   * (문서·작업 보드)는 묶음이 없다 — 두 요구가 실제로 겹치지 않는다. 겹치는 날이 오면
   * 그때는 「묶음을 아는 가상화」를 만들어야 하지, 여기서 조용히 한쪽을 버리면 안 된다.
   * 그래서 가상화 갈래에서는 `groupOf` 를 아예 안 읽는다(무시가 아니라 도달 불가다). */
  function renderBodyRows() {
    if (!groupPlan) return safeRows.map((row, i) => renderDataRow(row, i));
    const out = [];
    let seen = null;
    const drawn = new Set();
    const pushEmptySlots = (due) => due.forEach((s) => {
      out.push(<GroupHeaderRow key={`clv-group:${s.key}`} group={{ ...s, count: 0 }} colSpan={wideCols.length} collapsible={false} open />);
      out.push(
        <TableRow key={`clv-group-empty:${s.key}`} data-group-empty={s.key}>
          <TableCell colSpan={wideCols.length} sx={{ color: "text.secondary", fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }}>
            {s.emptyText || EMPTY_SLOT_TEXT}
          </TableCell>
        </TableRow>,
      );
    });
    safeRows.forEach((row, i) => {
      const opening = groupOpeningAt(i, seen);
      if (opening) {
        pushEmptySlots(emptySlotsBefore(opening.key, drawn));
        seen = opening.key;
        out.push(
          <GroupHeaderRow
            key={`clv-group:${opening.key}`}
            group={opening}
            colSpan={wideCols.length}
            collapsible={!!groupCollapsible}
            open={isGroupOpen(opening.key)}
            onToggle={() => toggleGroup(opening.key)}
          />,
        );
      }
      const g = groupPlan.items[i];
      if (!g || isGroupOpen(g.key)) out.push(renderDataRow(row, i));
    });
    pushEmptySlots(emptySlotsBefore(null, drawn));
    return out;
  }

  return (
    /* 🔴 표 안에서는 배지가 면을 갖지 않는다 (확정 규약 §9). 규칙을 호출부 106곳의 기억에
       맡기지 않고 **그릇이 선언한다** — 새 열을 더하는 사람이 이 규칙을 몰라도 지켜진다. */
    <FlatBadgeSurface>
      {frame(<>
      {/* 판 위 표와 채움 표는 이 두 안내를 발에 둔다(위 `footNotes`). 발이 없는 표(모달 · 서랍)만 예전처럼 표 위 한 줄이다. */}
      {footed ? null : <HiddenColumnsNote columns={hiddenCols} openable={!!onRow || !!rowHref} />}
      {/* 뺀 열은 **한 번 적는다** (R-91). 열이 조용히 사라지면 사용자는 그 값을 못 봤다는
          사실조차 모른다 — 무엇이 왜 없는지를 표가 직접 말한다. */}
      {!footed && collapse.caption ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", px: 2, pt: 1.5 }} data-collapsed-columns={dropped.join(",")}>
          {collapse.caption}
        </Typography>
      ) : null}
      {/* 🔴 `stickyHeader` 는 «바깥에 굴러가는 상자가 있다» 는 뜻이다. 그런데 MUI
          `TableContainer` 는 기본이 `overflow-x: auto` 라 **자기가 스크롤 컨테이너가
          된다** — 그 순간 `position: sticky` 한 열 이름이 붙는 대상이 바깥 상자가 아니라
          이 상자가 되고, 이 상자에는 높이 제한이 없어 절대 굴러가지 않는다. 결과는
          「속성은 sticky 인데 굴리면 열 이름이 사라진다」다.
          실측(2026-08-26 · 홈 「오늘 마감」 12행): 176px 굴렸더니 열 이름이 정확히 176px
          위로 사라졌다. 속성만 재는 검사로는 안 보인다 — `getComputedStyle(th).position`
          은 그때도 `sticky` 였다.
          그래서 이 경우에만 넘침을 바깥에 넘긴다. **다만 표가 칸 안에 들어갈 때만이다** —
          넓은 표까지 넘기면 판 밖으로 삐져나온다(`xOverflow` 주석).

          🔴 넘김을 못 고른 갈래에서는 **이 상자가 스크롤 창이라고 안쪽에 알린다**
          (`SCROLL_BOX_STICKY_TOP`). 안 알리면 열 이름이 `stickyTopSx()` 의 대체값인 상단바
          높이(52px)를 그대로 받는데, 그 52px 는 «윈도가 굴러갈 때 fixed AppBar 를 피하라»는
          뜻이라 이 상자 안에서는 피할 대상이 없다 — 열 이름 줄이 상자 위쪽에서 52px 내려온
          자리에 붙박이고 그 아래 첫 행을 통째로 덮는다. 실측(2026-09-06 · 1600x900
          `#/schedules`): th rect 451-496, 첫 행 rect 444-479, 행 가로폭의 93%가 머리행에
          가려 `elementFromPoint` 가 THEAD 를 돌려줬다(클릭도 그 줄이 먼저 받는다). 1280 에서는
          승인 목록이 90% 로 같아졌다. 값을 아는 쪽이 스크롤 창을 만드는 쪽이라는 계약을
          (`theme.js::STICKY_TOP_VAR`) 표 컨테이너에도 그대로 적용한다 — `ScrollArea` 가 이미
          같은 선언을 쓴다. */}
      <TableContainer
        ref={setScrollEl}
        data-table-box={fill ? "fill" : undefined}
        sx={{
          ...(fill
            /* 채움 — 상자가 판 몸의 남은 높이를 받아 두 축으로 굴린다. 끝에서 휠을 더 굴려도 판 · 문서가 따라 움직이지 않는다. */
            ? { flex: "1 1 auto", minHeight: 0, overflow: "auto", overscrollBehavior: "contain", ...SCROLL_BOX_STICKY_TOP }
            : virtualBox
            ? { maxHeight: virtualize.height || "32rem", overflowY: "auto", ...SCROLL_BOX_STICKY_TOP }
            : ((stickyHeader || virtualWindow) && !xOverflow
              ? { overflowX: "visible", overflowY: "visible" }
              : SCROLL_BOX_STICKY_TOP)),
          /* 목록 판 안쪽 모서리 — 굴러가는 상자는 자기 모서리로 머리 면 · 마지막 행 hover 면을 자른다. 넘김을 고른
             갈래(sticky 머리)는 자르지 않으므로 아래 머리 칸 모서리가 같은 일을 한다. */
          ...(placement === "surface" ? {
            borderTopLeftRadius: LIST_INNER_RADIUS,
            borderTopRightRadius: LIST_INNER_RADIUS,
            ...(hasFoot ? null : { borderBottomLeftRadius: LIST_INNER_RADIUS, borderBottomRightRadius: LIST_INNER_RADIUS }),
          } : null),
        }}
      >
      {/* 표 리듬 (지시 10) — 세로 괘선이 없고, 행 사이는 실선 하나로만 나눈다. 마지막 행의
          아래 선은 지운다(판의 테두리와 겹쳐 두 줄로 보인다). 행 추적은 괘선이 아니라
          **hover 면**과 머리행의 굵은 선이 만든다 — 엑셀 표가 아니라 계기판 판독부다. */}
      <Table
        ref={measureRef}
        size="small"
        stickyHeader={stickyHeader}
        // `VirtualRows` 와 같은 QA 프로브 계약(§18.2) — 가상화 중엔 그려진 <tr> 수 대신
        // 이 총 건수를 본다. `VirtualTableBody` 자신은 Fragment 라 붙일 단일 요소가 없어
        // 전체 행 수를 이미 아는 이 자리(`DataTable`)에서 낸다.
        data-virtual-total={virtualize ? safeRows.length : undefined}
        /* 두 숫자는 **다른 질문**이다. `data-virtual-total` 은 「그려질 수 있는 행이 몇인가」
           (=지금까지 받은 행 수)이고, 이것은 「전체가 몇 건인가」다. 한 속성에 두 뜻을 실으면
           `ui/virtual-rows.test.jsx` 와 `scripts/ui_qa/assertions.py` 가 함께 깨진다. */
        data-list-total={total != null ? total : undefined}
        /* 숨긴 열(「키:등급」)과 가로 굴림 여부 — QA 프로브 `column_balance` 가 「필수 열이 숨었나」를 읽는다. */
        data-hidden-cols={fit.meta ? (fit.hidden || []).map((c) => c.key + ":" + ((fit.meta[c.key] || {}).tier || "")).join(",") : undefined}
        data-plan-scroll={fit.meta ? (fit.scroll ? "true" : "false") : undefined}
        sx={{
          ...tableLayoutSx(wideCols, fit),
          "& td, & th": { borderInline: 0 },
          /* 붙박이 첫 열 — 굴러가는 칸이 비치지 않게 판 면을 깔고, hover · 선택 행에서는 행과 같은 면이다. */
          ...(stickyCols ? {
            "& tbody td[data-sticky-col]": { bgcolor: "background.paper" },
            "& tbody tr.MuiTableRow-hover:hover td[data-sticky-col], & tbody tr.Mui-selected td[data-sticky-col]": { bgcolor: "background.inset" },
          } : null),
          "& tbody tr:last-of-type td": { borderBottom: 0 },
          "& tbody tr": { transition: `background-color ${MOTION.instant} ${MOTION.ease}` },
          "& tbody tr.MuiTableRow-hover:hover": { bgcolor: "background.inset" },
          /* hover 와 선택이 **같은 한 단계**다. 색 테두리로 고른 행을 두르지 않는다 —
             표 안에서 색 테두리는 열 경계와 싸운다. */
          "& tbody tr.Mui-selected, & tbody tr.Mui-selected:hover": { bgcolor: "background.inset" },
          /* 키보드로 닿은 행의 초점 고리. MUI `TableRow` 는 뿌리에 `outline: 0` 을 걸어 전역 `:focus-visible` 고리를
             지운다(특이도가 같고 부품 규칙이 나중에 들어간다) — `onRow` 가 있는 행은 Tab 으로 닿고 Enter 로 여는데 초점이
             보이지 않았다(핸드오프 G 키보드 실측: 작업 큐 · 게시판 행의 계산 외곽선 `none 0px`). 고리는 행 안쪽에 그려
             가로로 굴러가는 표 상자에 잘리지 않게 한다. */
          "& tbody tr:focus-visible": (t) => ({
            outline: `2px solid var(--clovir-focus-ring, ${t.palette.focusRing})`,
            outlineOffset: -2,
          }),
          ...(placement === "surface" ? {
            "& thead tr:first-of-type th:first-of-type": { borderTopLeftRadius: LIST_INNER_RADIUS },
            "& thead tr:first-of-type th:last-of-type": { borderTopRightRadius: LIST_INNER_RADIUS },
          } : null),
        }}
      >
        <TableColGroup columns={wideCols} widths={fit.widths} meta={fit.meta} />
        <TableHead>
          <TableRow>
            {wideCols.map((c) => (
              <TableHeaderCell
                key={c.key}
                column={c}
                sort={sort}
                onSort={onSort}
                /* 조건 값을 어디서 읽는가는 **도메인이 안다** — 기간·범위 조건은 한 필드가
                   아니라 `created_from`/`created_to` 두 칸에 흩어져 사는 화면이 있다.
                   기본은 같은 이름의 칸 하나이고, 다르면 화면이 `filterValueOf` 로 말한다.
                   예전에는 이 조회가 표마다 따로였고, 그래서 같은 열이 한 화면에서는 조건이
                   걸린 것으로 다른 화면에서는 안 걸린 것으로 보였다. */
                filterValue={filters
                  ? (filterValueOf
                    ? filterValueOf(filters, (c.filter && c.filter.field) || c.key)
                    : filters[(c.filter && c.filter.field) || c.key])
                  : undefined}
                onFilter={onFilter}
                filterOptions={filterOptions && (filterOptions[(c.filter && c.filter.field) || c.key])}
                entityOptions={entityOptions && (entityOptions[(c.filter && c.filter.field) || c.key])}
                colRole={colRole(c)}
                /* 🔴 여기 `align={resolveColumn(c).align}` 이 있었다. `TableHeaderCell` 은
                   그 prop 을 **받지 않는다** — 머리글 정렬은 열마다 다르면 안 되는 값이라
                   `HEADER_ALIGN` 하나로 고정돼 있다(`ui/columnTypes.js` 의 그 문단).
                   조용히 버려지는 prop 이 남아 있으면 코드가 「머리 정렬은 열을 따른다」고
                   거짓말을 하고, 다음 사람이 그 거짓말을 근거로 고친다. */
                cellSx={{
                  ...colCellSx(c, { head: true }),
                  /* 🔴 고정 열 이름은 **상단바 아래**에 선다.
                     이 앱의 스크롤 창은 윈도다(`AppShell` 은 본문에 overflow 를 안 준다).
                     그래서 MUI 가 붙이는 `top: 0` 은 «뷰포트 맨 위» 이고, 거기에는
                     `position: fixed` 인 AppBar 가 이미 앉아 있다 — 열 이름을 보려고 켠
                     sticky 가 열 이름을 가린다. 값은 리터럴이 아니라 셸과 같은 토큰이다
                     (`theme.js::APPBAR_HEIGHT` · `stickyTopSx`).
                     면은 **고정이어도 함몰면**이다(핸드오프 README §4 「머리 줄 배경 #F5F6FB」). 예전에는 굴러가는 행이
                     비치지 않게 판 면(`background.paper`)으로 덮어, 고정 머리를 켠 표(사용자 · 감사 · 문서)만 머리가
                     흰 줄로 섰다. 함몰면도 불투명 토큰이라 행이 비치지 않는다. */
                  ...(stickyHeader ? { bgcolor: "background.inset", ...stickyTopSx() } : null),
                  ...(stickyCols && stickyCols[c.key] != null ? {
                    position: "sticky", left: stickyCols[c.key], zIndex: stickyHeader ? 3 : 2, bgcolor: "background.inset",
                  } : null),
                }}
              />
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {isEmpty ? (
            <TableRow data-empty-band="">
              {/* 띠의 여백은 띠가 갖는다 — 넓은 화면의 몸 칸 여백(테마 `body` 미디어 규칙)을 한 단 센 선택자로 이긴다(2560 에서 띠가
                  위아래 10 을 더 받아 84px 로 섰다, P17V). */}
              <TableCell colSpan={wideCols.length || 1} sx={{ p: 0, borderBottom: 0, "&&": { paddingTop: 0, paddingBottom: 0 } }}>
                <TableEmptyBandCtx.Provider value={BAND_IN_CELL}>{bandContent}</TableEmptyBandCtx.Provider>
              </TableCell>
            </TableRow>
          ) : virtualWindow ? (
            <WindowVirtualTableBody
              items={safeRows}
              estimateSize={virtualize.estimateSize}
              overscan={virtualize.overscan}
              colSpan={wideCols.length}
              scrollMargin={scrollMargin}
              getItemKey={(row, i) => keyOf(row, i)}
              renderRow={renderDataRow}
            />
          ) : virtualBox ? (
            <VirtualTableBody
              items={safeRows}
              estimateSize={virtualize.estimateSize}
              overscan={virtualize.overscan}
              colSpan={wideCols.length}
              scrollElement={scrollEl}
              getItemKey={(row, i) => keyOf(row, i)}
              renderRow={renderDataRow}
            />
          ) : renderBodyRows()}
        </TableBody>
      </Table>
      {/* 채움 표의 감시점은 굴러가는 상자 **안** 표 끝에 선다 — 상자 밖이면 늘 「보여」 끝까지 받는다. */}
      {fill ? sentinel : null}
      </TableContainer>
      {/* 발은 가로로 굴러가는 표 상자 **밖**, 판 안 마지막 줄이다 — 넓은 표를 가로로 굴려도 건수와 「더 보기」가 제자리다.
          빈 표는 「더 보기」가 남을 때만 발을 그린다(받은 0건을 문장으로 다시 말하지 않는다). */}
      {fill ? null : sentinel}
      {/* 채움 표의 발은 굴러가는 상자 아래에 고정이라 sticky 가 아니다. */}
      {isEmpty ? (foot.hasNext ? footBar(false) : null) : footBar(placement === "surface" && !fill)}
      </>, isEmpty ? "empty" : undefined, false)}
    </FlatBadgeSurface>
  );
}

/* 공통 모달 — 모든 생성/수정/확인/상세가 중앙 모달을 쓴다.
 * 예전에는 포커스 트랩·Esc 스택·배경 스크롤 잠금을 직접 구현했다. MUI Dialog가 셋 다
 * 정확히 처리하므로(중첩 모달 포함) 그 코드는 지웠다 — 직접 구현이 남아 있으면 MUI와
 * 이중으로 걸려 Esc 한 번에 두 개가 닫히는 예전 버그가 다시 난다.
 * size: sm|md|lg|fit. 모바일에서는 전체 화면. */
/* 모달 폭 — **레이아웃 브레이크포인트와 분리한다** (M7).
 *
 * 예전에는 `maxWidth={SIZE_MAP[size]}` 로 MUI 브레이크포인트 키를 넘겼다. 그런데 이 테마의
 * 브레이크포인트는 **화면 격자용**으로 커스텀돼 있다(`md:900, lg:1200`). 그래서 '중간 크기
 * 모달' 이 900px, '큰 모달' 이 1200px 이 됐다 — 1366px 화면에서 상세 패널 하나가 화면을
 * 거의 다 덮는다. 서로 상관없는 두 체계를 한 이름으로 묶은 결과다.
 *
 * 모달에는 모달의 척도를 준다. 값은 '한 줄에 몇 글자가 들어가는가' 로 정했다:
 *   sm 30rem — 확인 대화상자. 한 문장과 버튼 둘.
 *   md 45rem — 폼·상세. 산문 78ch 보다 좁다(모달 안은 라벨+값이라 더 좁아도 읽힌다).
 *   lg 62rem — 표·CSV 미리보기처럼 열이 여럿인 것.
 *   fit     — 내용 폭. 아바타 고르기처럼 칸 수가 고정된 격자만 쓴다. 폼에는 쓰지 않는다
 *             (`width:auto` 가 화면마다 다른 폭을 만들던 그 버그를 다시 열지 않기 위해
 *             이름이 따로다).
 */
const MODAL_MAX_WIDTH = { sm: "30rem", md: "45rem", lg: "62rem" };

/* 모달 머리 — 제목은 **판 제목과 같은 단계**(1.0625rem/700, 핸드오프 D-12)다. 예전에는 19px/800
 * 이라 모달이 뜨면 그 제목이 페이지 제목(28px)과 판 제목(17px) 사이 어디에도 없는 단계로 섰다.
 * 닫기는 인라인 30. `tone="danger"` 인 확인 창은 제목 앞에 오류 표지를 단다(RULES §8 — 위험
 * 확인 모달은 아이콘 + 제목 + 결과 문장). */
export function ModalHeader({ title, onClose, titleId, tone }) {
  /* 머리 줄(표지 · 제목 · 닫기)은 상자이고, **제목 요소는 제목 글자만** 든다. MUI `DialogTitle` 은
     대화상자의 `aria-labelledby` id 를 스스로 달기 때문에(DialogContext), 표지를 그 안에 넣으면 위험 확인의
     이름이 「주의 확인」이 된다 — 이름으로 대화상자를 찾는 쪽(낭독기의 대화상자 목록 · 시험)이 전부
     어긋났다. 표지는 머리 줄에 남아 읽는 순서대로 낭독된다. 여백은 MUI 제목의 기본값(24 · 16)을 줄이 갖는다. */
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, pl: 3, pr: 1.5, py: 2, flex: "0 0 auto" }}>
      {tone === "danger" ? (
        /* `titleAccess` 라야 MUI 가 `aria-hidden` 을 걷는다 — `aria-label` 만 주면 표지가 낭독에서 빠진다. */
        <ErrorOutlineRoundedIcon titleAccess="주의" sx={{ flexShrink: 0, fontSize: remPx(ICON.action), color: "error.main" }} />
      ) : null}
      <MuiDialogTitle
        id={titleId}
        sx={{ p: 0, flex: 1, minWidth: 0, fontSize: FONT_SIZE.cardTitle, fontWeight: FONT_WEIGHT.bold, lineHeight: LINE_HEIGHT.title }}
      >
        {title}
      </MuiDialogTitle>
      <IconButton onClick={onClose} aria-label="닫기" size="small"><CloseRoundedIcon fontSize="small" /></IconButton>
    </Box>
  );
}
/* 몸통은 **위 선 하나**만 긋는다. 아래 선은 발(`ActionFooter`)이 자기 면과 함께 긋는다 — 둘 다
 * 그으면 발 위에 2px 선이 서고, 「면 · 선 · 여백의 주인이 하나」라는 발 계약이 깨진다. */
export function ModalBody({ children }) {
  return <MuiDialogContent dividers sx={{ minWidth: 0, borderBottom: 0 }}>{children}</MuiDialogContent>;
}
/* 모달 모서리 반지름 — 사용자 지적 P4("전체적으로 눌렀을 때 라운드가 너무 크다").
 *
 * 예전 값은 `borderRadius: 2.5` 였는데, MUI 는 이 숫자에 `shape.borderRadius`(14)를 곱하므로
 * 실제로는 **35px** 이었다. 기준 목업의 카드는 `--radius-lg: 18px` 이고 모달도 같은 계열이다.
 * 하네스에 클릭을 붙여 실제로 연 모달 47개가 **예외 없이 35px** 이었다.
 *
 * 절댓값으로 적는 이유: 배수로 두면 `shape.borderRadius` 를 나중에 건드리는 순간 다시
 * 틀어진다. 이 값은 "카드와 같은 반지름" 이라는 뜻이지 "shape 의 2.5배" 가 아니다.
 * 핸드오프 D-13: 팝오버 · 모달 · 토스트 모서리는 모두 8 — 카드(`RADIUS.md`)와 같은 값이다. */
const MODAL_RADIUS = `${RADIUS.md}px`;

/* ── 카드 발 · 모달 발 — `ActionFooter` (핸드오프 D-12 · RULES §7 · §8) ─────────────────
 *
 * 저장 · 확정 · 취소가 서는 마지막 줄은 **한 부품**이다. 함몰면(`background.inset`) + 위 1px 실선
 * (`rule`), 오른쪽 정렬, 버튼 사이 8, 버튼은 34(페이지 동작). 왼쪽 `extra` 칸은 보조 동작(회차
 * 작업 · 빠른 수정 · 초기화)이 선다.
 *
 * 예전에는 같은 줄이 여러 벌이었다: `ModalFooter`(면 없음 · 취소 ghost), `kit.css .k-footer-row`
 * 를 손으로 조립한 화면 일곱, `footer` 변수를 스스로 그린 화면 열. 모양이 화면마다 달랐고,
 * 무엇보다 몸통의 아래 선과 발의 위 선이 겹쳐 2px 선이 서는 자리가 있었다.
 *
 * ## 면 · 선 · 여백의 주인은 하나다
 *
 * 발 하나에는 면과 위 선과 여백을 그리는 요소가 **정확히 하나**다(`data-action-footer`).
 * 겹치면 그리지 않는 쪽이 정해져 있다: `Modal` 이 받은 `footer` 가 이미 발이면 모달은 감싸지
 * 않고(바깥이 물러난다), 발 안에 또 발이 들어오면 안쪽이 맨 줄(`bare`)로 선다.
 *
 * `placement`
 *   modal   모달 발 — 좌우 24 · 위아래 16.
 *   card    판 안 마지막 줄 — 판 여백(20)을 거슬러 판 가장자리까지 면을 편다. 아래 모서리는 판 안쪽 반경을 든다(판이
 *           넘침을 자르지 않을 때도 모서리가 판을 따른다).
 *   inline  그 밖(서랍 · 판 없는 폼).
 *
 * `sticky` — 화면보다 긴 폼에서 확정 단추가 화면 아래에 따라온다(새 티켓 · 조합 계약 C-5). 판이 넘침을 자르면(MUI Card
 * 뿌리의 `overflow: hidden`) sticky 가 서지 않으므로 부르는 판은 `overflow: visible` 이어야 한다.
 */
const ActionFooterCtx = React.createContext(false);

export function ActionFooter({ children, extra, placement = "inline", sticky = false, sx }) {
  const nested = React.useContext(ActionFooterCtx);
  const row = {
    display: "flex", alignItems: "center", justifyContent: "flex-end",
    flexWrap: "wrap", gap: 1, rowGap: 1, minWidth: 0,
  };
  const body = (
    <>
      {extra ? (
        <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1, marginInlineEnd: "auto", minWidth: 0 }}>
          {extra}
        </Box>
      ) : null}
      {children}
    </>
  );
  if (nested) {
    return <Box sx={{ ...row, ...sx }}>{body}</Box>;
  }
  const face = { bgcolor: "background.inset", borderTop: 1, borderColor: "rule" };
  const pad = placement === "modal"
    ? { px: 3, py: 2, m: 0 }
    : placement === "card"
      ? { mx: `calc(-1 * ${CARD_PADDING})`, mb: `calc(-1 * ${CARD_PADDING})`, mt: 2, px: CARD_PADDING, py: 1.5 }
      : { px: 2, py: 1.5 };
  const Comp = placement === "modal" ? MuiDialogActions : Box;
  const corner = placement === "card"
    ? { borderBottomLeftRadius: LIST_INNER_RADIUS, borderBottomRightRadius: LIST_INNER_RADIUS }
    : null;
  const stick = sticky ? { position: "sticky", bottom: 0, zIndex: 2 } : null;
  return (
    <ActionFooterCtx.Provider value>
      {/* 발 높이 = 페이지 동작 단추 34 + 위아래 여백 12 × 2. */}
      {sticky ? <StickyBottomPadding height={`calc(${remPx(CONTROL.button)} + 1.5rem)`} /> : null}
      <Comp
        data-action-footer={placement}
        data-action-footer-sticky={sticky ? "" : undefined}
        sx={{ ...row, ...face, ...pad, ...corner, ...stick, ...sx }}
      >
        {body}
      </Comp>
    </ActionFooterCtx.Provider>
  );
}

/* 표준 하단 작업줄 — 취소(Secondary), 기본 작업(오른쪽). 전 화면 동일 위치·크기. */
/* 모달의 마지막 줄. `disabled` 는 **감추는 것과 다르다.**
 *
 * 필수 칸을 아직 안 채운 사람에게 필요한 것은 단추가 사라지는 것이 아니라 「무엇이
 * 모자란가」다. 단추가 없어지면 그 사람은 자기가 잘못 들어온 화면이라고 읽는다 — 그래서
 * 조건을 못 채운 상태는 **꺼진 단추**로 말하고, `onSubmit` 을 아예 안 주는 것은 「이
 * 모달에는 확인 동작이 없다」는 다른 뜻으로 남긴다. */
/* 취소는 **흰 면 + 테두리(default)** 다 — ghost 가 아니다(핸드오프 D-12). 발에서 글자만 있는
 * 취소는 「누를 수 있는 것」으로 안 읽혀 확정 버튼 하나만 서 있는 발처럼 보였다.
 * `cancelAutoFocus` — 되돌릴 수 없는 확인에서는 취소가 기본 포커스다(RULES §8). Enter 한 번이
 * 삭제가 되지 않게 한다. */
export function ModalFooter({ onCancel, onSubmit, submitLabel = "저장", cancelLabel = "취소", busy, disabled, submitVariant = "primary", cancelAutoFocus = false, extra }) {
  return (
    <ActionFooter placement="modal" extra={extra}>
      {onCancel ? <Button variant="default" onClick={onCancel} disabled={busy} autoFocus={cancelAutoFocus || undefined}>{cancelLabel}</Button> : null}
      {onSubmit ? <Button variant={submitVariant} onClick={onSubmit} disabled={busy || disabled} loading={busy}>{submitLabel}</Button> : null}
    </ActionFooter>
  );
}

/* footer 를 항상 `MuiDialogActions` 안에 넣는다 — 단, 이미 넣어 온 것은 그대로 둔다.
 *
 * 예전에는 `Modal` 이 `{footer}` 를 그대로 뱉었다. 그러면 버튼이 dialog 의 flex 열 **직계
 * 자식**이 되어 좌우로 늘어난 색띠가 세로로 쌓인다 — 사용자가 "모달 상태가 이상한데?" 라고
 * 한 그 모양이고, 하네스에 클릭을 붙이고 나서야 7개 화면에서 실제로 확인됐다(P6/K1/M1).
 *
 * 호출부에서 고치지 않고 여기서 판단하는 이유: `footer=` 를 넘기는 곳이 20군데이고 그중
 * 넷은 이미 `ModalFooter` 를 넘긴다. 호출부마다 규칙을 지키게 하면 **새 모달을 만들 때
 * 빠뜨린다** — 지금 상태가 정확히 그 결과다. 부품이 스스로 판단하면 빠뜨릴 수가 없다.
 * 이미 감싸 온 것을 또 감싸면 패딩이 두 배가 되고 flex 가 중첩되므로 그것도 막는다. */
function ModalActions({ children }) {
  if (React.isValidElement(children)) {
    if (children.type === ModalFooter || children.type === MuiDialogActions) return children;
    /* 이미 발이면 모달이 감싸지 않는다 — 자리만 모달 발로 맞춘다(주인은 그 발 하나). */
    if (children.type === ActionFooter) {
      return children.props.placement ? children : React.cloneElement(children, { placement: "modal" });
    }
  }
  return <ActionFooter placement="modal">{children}</ActionFooter>;
}

/* `dirty` 를 주면 **닫기 전에 확인**한다 (E11).
 *
 * `FormModal` 은 값 스냅샷으로 더티를 스스로 판정하지만, 이 저수준 `Modal` 은 내용을 모른다.
 * 그래서 부르는 쪽이 알려 준다. 안 주면 예전과 똑같이 그냥 닫힌다 - 기존 호출부를 깨지 않는다.
 *
 * 이게 없어서 실제로 아팠던 자리: 퀴즈 방 만들기(최대 20문항)를 다 쓰고 Esc 나 바깥을 한 번
 * 누르면 **전부 사라졌다.** 되돌릴 방법도 없다. 확인 문구는 FormModal 과 같은 것을 쓴다 -
 * 같은 상황에 다른 말이 나오면 사용자는 다른 일이 일어난다고 읽는다. */
export function Modal({ open, onClose, title, size = "md", children, footer, dirty = false, tone }) {
  const titleId = React.useId();
  const confirm = useConfirm();
  const isFit = size === "fit";
  const requestClose = React.useCallback(async (...args) => {
    if (!dirty) return onClose && onClose(...args);
    const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?",
                             { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
    if (ok && onClose) onClose(...args);
    return undefined;
  }, [dirty, onClose, confirm]);
  if (!open) return null;
  return (
    <MuiDialog
      open={!!open}
      onClose={requestClose}
      /* `maxWidth={false}` + sx 로 직접 준다 — MUI 의 브레이크포인트 척도를 쓰지 않는다. */
      maxWidth={false}
      fullWidth={!isFit}
      aria-labelledby={titleId}
      /* 모바일에서는 전체 화면 — 좁은 화면에서 폼이 잘려 스크롤조차 안 되던 문제.
       *
       * 폼 모달은 `width` 를 지정하지 않는다(M7). 예전에는 `sm` 이상에서 `width:"auto"` 였는데,
       * 그것이 바로 위 `fullWidth` 를 **무력화**했다 — 폭이 내용 길이로 정해져 같은 성격의
       * 모달이 화면마다 다른 크기가 됐다(실측: 한 화면에서 폭 7~8가지, `+ 직책 추가` 286px vs
       * `+ 공지 추가` 1200px 로 4배 차이). 이제 `maxWidth`(sm/md/lg) 세 등급만 남는다 —
       * 크기를 고르는 일이 `size` prop 한 곳으로 모인다.
       *
       * `fit` 만 내용 폭이다. 칸 수가 고정된 격자(아바타 고르기)처럼, 등급 폭이 오른쪽에
       * 빈 칸을 만드는 자리에 쓴다. 폼에는 쓰지 않는다.
       *
       * xs 는 그대로 전체 화면이다(좁은 화면에서 등급 폭을 쓰면 좌우가 잘린다). */
      sx={{ "& .MuiDialog-paper": {
        m: { xs: 0, sm: 4 },
        width: { xs: "100%", sm: isFit ? "max-content" : undefined },
        maxWidth: { xs: "100%", sm: isFit ? "calc(100% - 4rem)" : (MODAL_MAX_WIDTH[size] || MODAL_MAX_WIDTH.md) },
        maxHeight: { xs: "100%", sm: "calc(100% - 4rem)" },
        height: { xs: "100%", sm: "auto" },
        borderRadius: { xs: 0, sm: MODAL_RADIUS },
      } }}
    >
      <SurfaceReset>
        <ModalHeader title={title} onClose={requestClose} titleId={titleId} tone={tone} />
        <ModalBody>{children}</ModalBody>
        {footer ? <ModalActions>{footer}</ModalActions> : null}
      </SurfaceReset>
    </MuiDialog>
  );
}

/* ── 폼 칸 하나 — **라벨 20 · 필드 36 · 도움말 auto 의 고정 세로 트랙** (핸드오프 README 정렬 규약 1 · RULES §7) ──
 *
 * 도움말이 있는 칸과 없는 칸이 한 줄에 섞이면, 트랙이 없을 때 도움말 한 줄이 그 칸만 늘려 옆 칸의
 * 입력 상자와 윗선이 어긋난다. 트랙을 고정하면 도움말이 없어도 셋째 줄이 남고, 한 줄에 선 입력칸
 * 윗선이 언제나 같은 y 에서 시작한다. 필드 높이의 정본은 `CONTROL.input` 이다(MUI 외곽선 입력은
 * 테두리를 상자 안에 그리므로 36 이 곧 보이는 높이다).
 *
 * `/profile` 이 이 트랙을 먼저 만들었고(`FIELD_ROWS`), 새 티켓이 둘째 소비처라 키트로 올린다.
 * 도움말과 오류는 셋째 줄 한 자리를 나눠 쓴다 — 오류가 있으면 오류가 선다(`aria-describedby` 는
 * 입력 쪽이 `helpId` 를 가리킨다). */
/* 필드 줄은 컨트롤 높이(34, 밀집 줄 30)가 **바닥**이다 — 한 줄 칸은 정확히 그 높이로 서고, 고른 칩이 여럿이라 두 줄로
   접히는 칸(담당자)은 그만큼 자라 아래 도움말과 겹치지 않는다. 라벨 줄이 20 으로 고정이라 같은 줄의 입력칸 윗선은 그대로
   같다(D-527). 높이의 정본은 `theme.js::controlHeight` 하나다 - 그릇이 `densityVars("dense")` 로 30 을 주면 함께 준다. */
export const FIELD_ROWS = `${remPx(20)} minmax(var(--clovir-control-h, ${remPx(CONTROL.control)}), auto) auto`;

/* 폼 칸 폭 토큰(D-527). 칸 하나가 혼자 설 때의 상한이다 - 줄(`FieldRow`) 안에서는 격자가 폭을 정한다. */
export const FIELD_WIDTH = { sm: "10rem", md: "16rem", lg: "24rem", xl: "32rem", full: "none" };

/**
 * 폼 칸 하나 — **라벨 20 · 컨트롤 34 · 도움말 auto 의 고정 세로 트랙**에 **동작 칸**이 붙는다 (핸드오프 README 정렬 규약 1 ·
 * RULES §7, D-527).
 *
 * 열은 `minmax(0,1fr) [auto]` 다. 라벨이 두 칸 전체, 컨트롤과 `action`(단추 하나 이상)이 둘째 줄에서 **윗선 · 높이가 같고**,
 * 도움말 · 오류가 셋째 줄 **두 칸 전체**에 선다(단추 밑으로도 이어진다). 예전에는 공용 칸에 동작 자리가 없어 화면마다
 * 단추를 `flex-end` · `flex-start` · `center` 로 따로 줄 세웠고, AI 모델 칸의 「다시 불러오기」는 도움말 바닥에 붙어 도움말 끝
 * 뒤로 밀렸다.
 *
 * 도움말과 오류는 셋째 줄 한 자리를 나눠 쓴다 — 오류가 있으면 오류가 선다(두 줄이 쌓여 높이가 흔들리지 않는다).
 * `aria-describedby` 는 입력 쪽이 `helpId` 를 가리킨다. `width` 는 혼자 설 때의 상한(sm 10 · md 16 · lg 24 · xl 32rem), `span`
 * 은 `FieldRow` 의 12칸 격자에서 문턱별로 차지할 칸 수(`fieldSpan`), `density="dense"` 는 컨트롤 줄을 30 으로 낮춘다.
 */
export function Field({
  label, htmlFor, labelId, required, help, error, helpId, action, width = "full", span, density, fit = false, children,
  className, sx,
}) {
  return (
    <Box
      data-form-field=""
      className={className ? `k-field ${className}` : "k-field"}
      sx={{
        display: "grid",
        gridTemplateColumns: action ? "minmax(0,1fr) auto" : "minmax(0,1fr)",
        gridTemplateRows: FIELD_ROWS,
        columnGap: 1,
        alignContent: "start",
        minWidth: 0,
        maxWidth: FIELD_WIDTH[width] || width,
        ...densityVars(density),
        ...(span ? fieldSpan(span) : null),
        ...sx,
      }}
    >
      <FieldLabel
        htmlFor={htmlFor} id={labelId} required={required}
        sx={{ gridColumn: "1 / -1", gridRow: 1, mb: 0, lineHeight: 1.25, alignSelf: "start" }}
      >
        {label}
      </FieldLabel>
      <Box
        className="k-field-control"
        /* `fit` — 제 폭을 갖는 컨트롤(세그먼티드처럼 선택지 수가 폭인 것)은 칸을 채우지 않는다. 늘이면 선택지 둘짜리가 칸 끝까지
           벌어져 빈 띠가 된다(P10 캡처). 입력 · 선택 칸은 그대로 채운다. */
        sx={{ gridColumn: 1, gridRow: 2, minWidth: 0, display: "flex", alignItems: "stretch",
          "& > *": { flex: fit ? "0 0 auto" : "1 1 auto", minWidth: 0 } }}
      >
        {children}
      </Box>
      {action ? (
        <Box
          className="k-field-action"
          sx={{ gridColumn: 2, gridRow: 2, display: "flex", alignItems: "flex-start", gap: 1, alignSelf: "start" }}
        >
          {action}
        </Box>
      ) : null}
      {/* 셋째 줄은 도움말 · 오류가 있거나, 입력이 가리키는 자리(`helpId`)가 있을 때 선다 - 나중에 오류가 들어설 자리가 늘
          같은 노드라야 `aria-describedby` 가 끊기지 않는다. 둘 다 없으면 빈 줄이 4px 를 더하지 않는다. */}
      {error || help || helpId ? (
      <Box id={helpId} sx={{ gridColumn: "1 / -1", gridRow: 3, minWidth: 0, pt: 0.5 }}>
        {error ? (
          <Typography
            component="p"
            role="alert"
            sx={{ m: 0, display: "flex", alignItems: "flex-start", gap: 0.5, fontSize: FONT_SIZE.micro, color: "error.strong", ...KO_WORD_BREAK }}
          >
            <ErrorOutlineRoundedIcon aria-hidden="true" sx={{ fontSize: remPx(ICON.mark), mt: "0.0625rem", flexShrink: 0 }} />
            <span>{error}</span>
          </Typography>
        ) : help ? (
          <Typography component="p" sx={{ m: 0, fontSize: FONT_SIZE.micro, color: "text.secondary", ...KO_WORD_BREAK }}>{help}</Typography>
        ) : null}
      </Box>
      ) : null}
    </Box>
  );
}

/* 옛 이름. 내 프로필과 새 티켓이 먼저 만든 칸이고, 이제 `Field` 가 그린다. */
export function FormFieldCell(props) {
  return <Field {...props} />;
}

/**
 * 관련 칸을 한 줄에 — 12칸 컨테이너 질의 격자(`FORM_FIELD_GRID_12`). 칸마다 `span={{ wide, mid }}` 로 차지할 칸 수를 말하고,
 * 칸이 좁아지면 2칸 · 1칸으로 접힌다. 줄 단위 `action` 은 칸 묶음 오른쪽의 제 칸이고, 라벨 줄을 비운 같은 세로 트랙
 * (`FIELD_ROWS`)이라 첫 줄 입력과 윗선 · 높이가 같다(D-527). 칸이 한 열로 접혀도 동작은 첫 입력 줄에 남는다.
 *
 * `columns` 는 값이 폭을 정하는 짧은 칸(시각 · 포트처럼)의 줄이다 - `["9.5rem", "9.5rem"]` 처럼 칸마다 상한을 말하면 칸과
 * 동작이 왼쪽에 붙어 선다(남는 폭을 나누지 않는다). 이때는 컨테이너 질의가 필요 없다.
 */
export function FieldRow({ children, action, columns, sx }) {
  const fixed = Array.isArray(columns) && columns.length > 0;
  const fields = fixed
    ? (
      <Box sx={{ display: "grid", gap: FORM_FIELD_GAP, alignItems: "start", gridTemplateColumns: columns.map((c) => `minmax(0, ${c})`).join(" ") }}>
        {children}
      </Box>
    )
    : (
      <Box sx={{ ...FORM_FIELD_CONTAINER, minWidth: 0 }}>
        <Box sx={FORM_FIELD_GRID_12}>{children}</Box>
      </Box>
    );
  return (
    <Box
      data-field-row=""
      sx={{
        display: "grid",
        gridTemplateColumns: action ? (fixed ? "auto auto" : "minmax(0, 1fr) auto") : "minmax(0, 1fr)",
        justifyContent: fixed ? "start" : undefined,
        columnGap: FORM_FIELD_GAP,
        alignItems: "start",
        minWidth: 0,
        ...sx,
      }}
    >
      {fields}
      {action ? (
        <Box className="k-field-row-action" sx={{ display: "grid", gridTemplateRows: FIELD_ROWS, minWidth: 0 }}>
          <span aria-hidden="true" />
          <Box className="k-field-row-action-slot" sx={{ gridRow: 2, display: "flex", alignItems: "flex-start", gap: 1 }}>
            {action}
          </Box>
        </Box>
      ) : null}
    </Box>
  );
}

/**
 * 폼의 구획 — **카드가 아니다**(F7 카드 규율). 머리(제목 1.0625rem/700 + 필요할 때만 한 문장 설명) → 1px 선 → 칸 목록(간격
 * 20). 연속된 구획(메일 · AI 연결 · 초기 설정)은 한 판 위에서 머리와 선으로만 나뉜다 - 구획마다 카드를 두르지 않는다.
 * 구획과 구획 사이는 담는 쪽 간격에 12px 를 더한 거리다(`screens.css` 의 `.k-form-section + .k-form-section`, 페이지 흐름 28 ·
 * 판 안 26) - 앞 구획의 마지막 칸과 다음 구획의 머리가 붙어 보이지 않게 한다.
 */
export function FormSection({ title, description, action, titleAs = "h3", children, sx }) {
  return (
    <Box
      component="section"
      className="k-form-section"
      data-form-section=""
      sx={{ minWidth: 0, display: "flex", flexDirection: "column", rowGap: 1.5, ...sx }}
    >
      <SectionHeader title={title} help={description} action={action} component={titleAs} sx={{ mb: 0 }} />
      <Box sx={{ borderTop: 1, borderColor: "rule" }} />
      <Box sx={{ display: "flex", flexDirection: "column", rowGap: 2.5, minWidth: 0, pt: 0.5 }}>{children}</Box>
    </Box>
  );
}

/* 공통 입력 필드 — 라벨/필수(*)/도움말/오류를 한곳에서. 라벨은 htmlFor/id로 입력과 연결해
 * 스크린리더가 이름을 읽게 한다(체크박스는 라벨이 입력을 감싸 이미 연결됨).
 *
 * maxLength(PA-RC-0005) — lib/fieldLimits.js가 백엔드 Pydantic 스키마에서 유도한 값이다(손으로
 * 옮기지 않는다). 붙여넣기로 상한을 넘기면 브라우저가 조용히 자르기만 하는데, 그러면 사용자는
 * 잘린 줄 모른다 — onPaste에서 미리 계산해 잘릴 상황이면 토스트로 알린다(막지는 않는다, 자르고
 * 알린다). 긴 텍스트(textarea/json)는 helperText에 남은 글자 수도 함께 보여준다. */
/* 입력 위의 라벨 (지시 17 · Taste §4.6 "Label-above-input").
 *
 * MUI 기본은 **떠 있는 라벨**이다 — 값이 없으면 입력 칸 안에 있다가 포커스하면 위로 올라가
 * 테두리에 걸친다. 그 방식은 셋을 잃는다.
 *   · 훑을 수 없다. 값이 든 칸과 빈 칸의 라벨 위치가 달라 세로로 라벨을 따라 읽지 못한다.
 *   · 한국어에서 자주 잘린다. 떠 있는 라벨은 테두리 노치 폭 안에 들어가야 한다.
 *   · 필수 표시가 `*` 하나뿐이라, 그것이 무엇을 뜻하는지 화면 어디에도 없다.
 *
 * 라벨을 위에 두고, 필수는 **글자로** 말한다. 스크린리더에도 같은 글자가 읽힌다.
 */
/* 내보내는 이유(W5): 라벨 위치가 제품 안에 다섯 종류로 갈라져 있었다 — kit 은 이 부품을
   쓰는데 kit 밖 화면들이 각자 `Typography component="label"` 을 손으로 그렸고, 필수 표시도
   빨간 글자·MUI `*`·손으로 붙인 `*`·표시 없음 네 가지가 공존했다. 계약을 **부품으로**
   내보내야 그 화면들이 같은 것을 쓸 수 있다. */
export function FieldLabel({ htmlFor, id, children, required, sx }) {
  /* `select` 는 MUI 가 `id` 를 `<div>` 에 건다 — `<label htmlFor>` 은 라벨을 붙일 수 없는
     요소를 가리키게 되어 접근성 트리에서 끊긴다. 그때는 라벨에 `id` 를 주고 입력 쪽에서
     `aria-labelledby` 로 가리킨다(HTML 명세가 정한 그 대안). */
  return (
    <Typography
      component={htmlFor ? "label" : "span"}
      htmlFor={htmlFor}
      id={id}
      sx={{
        display: "flex", alignItems: "center", gap: 0.75, mb: 0.5,
        fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.medium, color: "text.primary",
        ...KO_WORD_BREAK,
        /* 여백은 배치가 정할 수도 있다. 라벨 줄이 **고정 트랙**인 폼(라벨 20 · 필드 36 ·
           도움말 auto)에서는 아래 여백을 격자가 갖는다 — 부품이 든 `mb` 가 그 위에 더해지면
           트랙이 20 을 넘어 옆 필드와 윗선이 어긋난다. 글자 계약은 그대로 두고 여백만 연다. */
        ...sx,
      }}
    >
      {children}
      {/* 표시는 눈으로만. 필수 여부는 입력의 `aria-required` 가 이미 정확히 말한다 —
         라벨에 글자로 또 넣으면 접근성 이름이 "제목 필수"가 되어 두 번 읽히고, 이름으로
         입력을 찾는 코드(시험 포함)가 전부 그 꼬리를 달고 다녀야 한다. */}
      {required ? (
        <Box
          component="span"
          aria-hidden="true"
          sx={{ fontSize: FONT_SIZE.micro, color: "error.strong", fontWeight: FONT_WEIGHT.semibold }}
        >
          {/* 앞의 공백은 장식이 아니다 — 라벨의 글자 내용이 "제목필수" 한 덩어리가 되면
              라벨 글자로 입력을 찾는 코드가 전부 깨진다(접근성 이름과 글자 내용은 다른 것이다). */}
          {" 필수"}
        </Box>
      ) : null}
    </Typography>
  );
}

export function FormField({ field: f, value, onChange, invalid, maxLength, errorMessage }) {
  const id = "ff-" + f.name;
  const required = !!f.required;
  const isJson = f.type === "json";
  const multiline = f.type === "textarea" || isJson;
  /* 붙여넣은 글이 상한에서 잘린 사실 — 그 칸의 도움말 자리에 남는다(되돌릴 수 없는 결과는 사라지는 토스트에
     두지 않는다). 칸을 다시 고치면 걷힌다. */
  const [pasteNotice, setPasteNotice] = React.useState("");
  const handlePasteOverflowWarning = maxLength ? (e) => {
    const pasted = e.clipboardData ? e.clipboardData.getData("text") : "";
    if (!pasted) return;
    const el = e.target;
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const nextLength = el.value.length - (end - start) + pasted.length;
    if (nextLength > maxLength) {
      setPasteNotice(`최대 ${maxLength}자까지만 저장됩니다. 붙여넣은 내용 중 일부가 잘렸습니다.`);
    }
  } : undefined;
  const charCount = (multiline && maxLength) ? `${(value || "").length}/${maxLength}자` : null;
  const staticHelp = charCount ? (f.help ? `${f.help} (${charCount})` : charCount) : (f.help || undefined);
  // PA-RC-0014: invalid면 도움말 대신 실제 오류 문구를 aria-describedby가 가리키는 자리에 둔다 —
  // 빨간 테두리(error)만으로는 스크린리더가 "무엇이 문제인지"를 읽을 수 없었다.
  const helpText = invalid && errorMessage ? errorMessage : (pasteNotice || staticHelp);
  const helpId = helpText ? id + "-helper-text" : undefined;
  /* 칸의 셋째 줄(`Field`)이 그리는 값 — 오류가 있으면 오류가 도움말 자리를 대신한다(D-527). */
  const fieldError = invalid && errorMessage ? errorMessage : null;
  const fieldHelp = fieldError ? null : (pasteNotice || staticHelp || null);

  if (f.type === "checkbox") {
    return (
      <Box className="k-field">
        <FormControlLabel
          control={
            <Checkbox
              id={id}
              checked={!!value}
              onChange={(e) => onChange(e.target.checked)}
              inputProps={{ "aria-describedby": helpId, "aria-required": required || undefined, "aria-invalid": invalid || undefined }}
            />
          }
          label={
            <>
              {f.checkLabel || f.label || "사용"}
              {required ? <Box component="span" sx={{ color: "error.main" }}> *</Box> : null}
            </>
          }
        />
        {helpText ? <Typography id={helpId} variant="caption" color={invalid ? "error" : "text.secondary"} sx={{ display: "block", mt: 0.5 }}>{helpText}</Typography> : null}
      </Box>
    );
  }

  // 선택형에서 현재 값과 맞는 옵션이 없으면 빈 옵션을 앞에 붙인다.
  // (없으면 <select>는 첫 실제 옵션을 보여 주면서 상태는 '' — 화면과 실제 값이 어긋난다.)
  const selNeedEmpty = f.type === "select" &&
    !(f.options || []).some((o) => String(o.value) === (value != null ? String(value) : ""));
  const hasOptions = (f.options || []).length > 0;

  // 도움말 · 오류는 칸의 셋째 줄(`Field`)이 `${id}-helper-text` 자리에 그리고, 입력은 그 자리를 `aria-describedby` 로
  // 가리킨다(아래 `inputProps` · `SelectProps`). MUI 의 `helperText` 는 쓰지 않는다 — 칸 안에 도움말 줄이 하나 더 서고
  // 오류가 도움말을 대신하는 자리가 둘로 갈린다. 연결이 끊기면 도움말이 시각적으로만 남는다(kit.test.jsx 가 잡는다).
  const common = {
    id,
    fullWidth: true,
    size: "small",
    error: !!invalid,
    required,
    // `label` 은 안 넘긴다 — 라벨은 칸(`Field`)의 첫째 줄이 그린다(지시 17). MUI 에 넘기면
    // 떠 있는 라벨이 하나 더 생겨 같은 글자가 두 번 보인다.
    value: value != null ? value : "",
    onChange: (e) => onChange(e.target.value),
    sx: { mb: 0 },
  };

  /* 순수 달력일(`date`) — §15.5 재검수. `datetime-local` 은 손대지 않는다: 그쪽은
     KST 벽시계 변환(`apiToKstLocal`)이 걸린 다른 계약이고, 이 화면들(회차·마감일)은
     원래도 날짜만 다뤘다(네이티브 `input[type=date]` 가 처음부터 시각을 안 받았다). */
  if (f.type === "date") {
    return (
      <Field label={f.label} htmlFor={id} required={required}>
        <DateField
          id={id}
          value={value}
          onChange={onChange}
          error={!!invalid}
          helperText={helpText}
          required={required}
        />
      </Field>
    );
  }

  /* Entity 필드 — 값 집합이 **데이터가 쌓이는 만큼 자라는** 것(사용자·부서·직책·프로젝트·
   * 조직·일정)을 고르는 자리. 닫힌 열거형과 같은 부품으로 그리면 후보가 200명이 되는 날
   * 사용자는 이름을 알면서도 목록을 눈으로 훑는다(R-5 · 지시 0-2.17). 폼과 필터가 **같은
   * 부품**을 쓴다 — 같은 값을 고르는 자리가 표면마다 다른 상호작용을 갖지 않는다(C8). */
  if (f.type === "entity") {
    return (
      <Field label={f.label} labelId={id + "-label"} required={required}>
        <EntityCombobox
          id={id}
          label={undefined}
          ariaLabelledBy={id + "-label"}
          value={value != null ? String(value) : ""}
          onChange={onChange}
          options={f.options || []}
          allLabel={f.emptyLabel || "선택 안 함"}
          helperText={helpText}
          layout="form"
          sx={{ width: "100%", maxWidth: "none" }}
        />
      </Field>
    );
  }

  if (f.type === "select") {
    return (
      <Field label={f.label} labelId={id + "-label"} required={required} help={fieldHelp} error={fieldError} helpId={helpId}>
      <TextField
        {...common}
        select
        /* MUI 는 `label` 이 함께 있을 때만 `labelId` 를 aria-labelledby 로 엮는다 —
           라벨을 위로 올린 뒤로는 직접 걸어 줘야 이름이 접근성 트리에 닿는다.
           `displayEmpty` 가 없으면 값이 `""` 일 때 MUI 가 «아직 아무것도 안 골랐다» 로 보고
           선택 항목을 아예 안 그린다 — 상자가 **완전히 빈 백지**가 된다(사용자 추가 모달의
           부서·직책 select 가 잉크 0px 로 실측됐다). 같은 화면의 **필터** select 는
           `EMPTYABLE_SELECT` 로 이미 이 함정을 피하고 있었는데 폼만 안 쓰고 있었다. */
        SelectProps={{ labelId: id + "-label", displayEmpty: true, "aria-describedby": helpId }}
      >
        {selNeedEmpty ? (
          <MenuItem value="" disabled={required}>
            {hasOptions ? "선택 안 함" : "선택할 항목이 없습니다"}
          </MenuItem>
        ) : null}
        {(f.options || []).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
      </TextField>
      </Field>
    );
  }

  return (
    <Field label={f.label} htmlFor={id} required={required} help={fieldHelp} error={fieldError} helpId={helpId}>
    <TextField
      {...common}
      multiline={multiline}
      minRows={multiline ? (isJson ? 10 : 3) : undefined}
      type={
        f.type === "number" ? "number"
          : f.type === "password" ? "password"
          : f.type === "email" ? "email"
          : f.type === "date" || f.type === "datetime-local" ? f.type
          : "text"
      }
      onPaste={handlePasteOverflowWarning}
      /* `freeTextReason` 은 «이 자유 텍스트는 일부러 그렇다» 는 선언이다(W5). 후보 목록이
         존재하지 않는 값(외부 시스템 식별자, 폼 값에 따라 후보가 갈리는 참조)이 그렇고,
         그 **문장이 그대로** DOM 에 남는다 — 읽는 사람이 바로 이유를 본다.
         억제 마커가 아니다: `plain_dropdown_for_entity` 는 끌 수 없는 검사이고(QA_SUPPRESSIONS
         규칙 4) 여기서 말하는 것은 «끄겠다» 가 아니라 «이 칸은 애초에 선택기가 될 수 없다» 다. */
      data-free-text={f.freeTextReason || undefined}
      inputProps={{
        ...(f.type === "email" ? { inputMode: "email", autoCapitalize: "none" } : null),
        ...(maxLength ? { maxLength } : null),
        ...(helpId ? { "aria-describedby": helpId } : null),
      }}
      /* JSON은 사람이 중첩 구조를 손으로 편집한다 — 가변폭 폰트로는 중괄호·들여쓰기가 안 맞는다. */
      InputProps={isJson ? { sx: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: FONT_SIZE.bodySm } } : undefined}
    />
    </Field>
  );
}

/* 설정 주도 폼 — 항상 중앙 모달. 항목이 많으면(>5) 큰 모달(lg).
 * 제출 로직은 한 줄도 바꾸지 않았다: 숫자 변환, hadValue→null, JSON 객체 검증, 401 처리,
 * details 평탄화, 더티 닫기 확인. 이 15개 이상 화면이 공유하는 유일한 저장 표면이다. */
export function FormModal({ open, title, fields, initial, submitLabel, onSubmit, onClose, size, screenKey, formKind }) {
  const [values, setValues] = React.useState({});
  const [err, setErr] = React.useState("");
  const [errField, setErrField] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  /* 제출이 진행 중인지는 **동기 ref** 가 먼저 안다. `busy` 는 다음 렌더에야 발의 단추를 끄는데,
     Enter 는 그 단추가 아니라 폼 안의 숨은 제출 단추(아래 `sr-only`)를 누르고 그 단추는 꺼지지
     않는다. 그래서 Enter 를 빠르게 두 번 치면 `submit()` 이 두 번 돌아 같은 행이 둘 생기거나 둘째가
     「이미 있습니다」로 실패했다. 이 ref 가 서 있는 동안의 제출은 버린다. */
  const submitting = React.useRef(false);
  const initialRef = React.useRef({});   // 열릴 때의 값 스냅샷 — 더티(변경) 판정 기준.
  const confirm = useConfirm();
  const toast = useToast();
  React.useEffect(() => {
    if (!open) return;
    const v = {};
    (fields || []).forEach((f) => {
      const iv = initial && initial[f.name] != null ? initial[f.name] : (f.value != null ? f.value : (f.type === "checkbox" ? false : ""));
      // datetime-local 은 **벽시계**만 담는다 — 서버가 준 naive UTC 를 그대로 넣으면 목록 열
      // (KST 로 그린다)과 편집 폼이 9시간 다른 값을 말한다(F14). 경계 변환은 lib/format.js.
      if (f.type === "datetime-local") { v[f.name] = apiToKstLocal(iv); return; }
      v[f.name] = f.type === "json" && iv && typeof iv === "object" ? JSON.stringify(iv, null, 2) : iv;
    });
    initialRef.current = v;
    setValues(v); setErr(""); setErrField(null);
  }, [open]);
  // 긴 폼을 채우던 중 오버레이·Esc 오조작 한 번에 입력이 통째로 날아가던 문제.
  // number 필드는 기본값이 숫자(60)지만 입력을 거치면 문자열('60')이 된다 — 정규화 후 비교.
  const normalizeForCompare = React.useCallback((vals) => {
    const out = {};
    (fields || []).forEach((f) => {
      const v = vals ? vals[f.name] : undefined;
      out[f.name] = f.type === "number" ? (v === "" || v == null ? "" : String(v)) : v;
    });
    return out;
  }, [fields]);
  const requestClose = React.useCallback(async () => {
    // 제출 중에는 취소/Esc/오버레이 클릭을 모두 거부한다 — 예전엔 '처리 중…' 표시 중에도
    // 닫기가 통과되며 아무 취소도 없이 모달만 닫혔다.
    if (busy) return;
    if (JSON.stringify(normalizeForCompare(values)) !== JSON.stringify(normalizeForCompare(initialRef.current))) {
      const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?", { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
      if (!ok) return;
    }
    onClose();
  }, [busy, values, confirm, onClose, normalizeForCompare]);
  // 검증 실패 필드를 화면 안으로 스크롤·포커스한다(큰 폼에서 오류가 스크롤 아래 숨는 문제).
  // behavior 를 명시하면 CSS scroll-behavior(theme.js 의 동작 최소화 전역 규칙)가 이 호출에는
  // 닿지 않는다 — 그래서 여기서 직접 판정해서 behavior 를 고른다.
  React.useEffect(() => {
    if (!errField) return;
    const el = document.getElementById("ff-" + errField);
    if (el) { try { el.scrollIntoView({ block: "center", behavior: "smooth" }); el.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
  }, [errField]);
  /* 조건부 필드 (사용자 지적 #15).
   *
   * 예전에는 폼 스키마에 **조건부 장치가 아예 없었다**. 그래서 AI 쿼터 화면은 범위를
   * '전체' 로 골라도 "범위가 '사용자'일 때만 필요합니다" 라고 적힌 사용자 ID 칸을 계속
   * 보여 줬다 — 도움말은 조건을 말하는데 화면은 그 조건을 모르는 상태다.
   *
   * `showIf(values)` 가 false 면 **그리지도, 검증하지도, 보내지도 않는다.** 셋 중 하나만
   * 빠지면 더 나쁜 결함이 된다: 안 그리는데 검증하면 "보이지 않는 칸이 필수" 가 되고,
   * 안 그리는데 보내면 서버가 지워진 값을 받는다.
   *
   * ⚠️ 이 훅은 **`if (!open)` 조기 반환보다 위**에 있어야 한다. 아래에 두면 닫힘→열림에서
   * 훅 개수가 11개→12개로 늘어 리액트가 "Rendered more hooks than during the previous
   * render." 로 트리를 통째로 버린다 — 관리자 화면의 '추가'·'수정'을 누르는 순간 화면이
   * 사라졌다. 조건부 반환 위로 올리면 규칙(훅은 항상 같은 순서)이 지켜진다. */
  /* 후보가 **다른 칸의 값**에 달린 칸도 있다(`options` 를 함수로 준다). 부서 추가의
     「상위 부서」가 그렇다 — 상위 부서는 반드시 같은 조직이어야 해서(app/org/tree.py::
     validate_parent), 조직 칸에서 고른 조직의 부서만 후보다. 후보를 안 좁히면 폼이
     **반드시 422 로 실패하는 선택지**를 권한다(org-03).
     `showIf` 와 같은 자리에서 같은 값(`values`)으로 푼다 — 조건부 필드와 조건부 후보는
     같은 질문("지금 값이 무엇인가")의 두 답이다. */
  const shownFields = React.useMemo(
    () => (fields || [])
      .filter((f) => (typeof f.showIf === "function" ? f.showIf(values) : true))
      .map((f) => (typeof f.options === "function"
        ? { ...f, options: f.options(values), dynamicOptions: true }
        : f)),
    [fields, values],
  );
  /* 크기를 **열릴 때 한 번** 정하기 위한 기억. 위 경고와 같은 이유로 조기 반환 위에 둔다 —
     `useRef` 도 훅이다. 값을 채우는 것은 훅이 아니라 대입이라 아래에서 한다. */
  const sizeAtOpen = React.useRef(null);
  if (!open) {
    sizeAtOpen.current = null;
    return null;
  }
  const set = (name, val) => setValues((s) => ({ ...s, [name]: val }));

  /* 후보가 값에 따라 바뀌는 칸은, **지금 후보에 없는 값을 「고른 것」으로 치지 않는다.**
     조직을 바꾸면 먼저 고른 상위 부서가 후보에서 빠지는데, 화면은 그때 이미 「선택 안 함」을
     보여 준다(위 `selNeedEmpty`). 보내는 값이 그것과 다르면 사용자가 화면에서 안 고른 값이
     그대로 나가고, 서버는 그 조합을 422 로 거절한다 — 화면과 요청이 같은 말을 하게 한다. */
  const chosen = (f) => {
    const val = values[f.name];
    if (!f.dynamicOptions || val == null || val === "") return val;
    return (f.options || []).some((o) => String(o.value) === String(val)) ? val : "";
  };

  const fail = (name, message) => { setErrField(name); setErr(message); };

  async function submit() {
    if (submitting.current) return;   // 같은 제출이 아직 끝나지 않았다(위 `submitting` 주석).
    setErr(""); setErrField(null);
    const body = {};
    for (const f of shownFields) {
      // 수정 화면에서 원래 값이 있던 항목을 비우면 키를 생략하지 않고 null로 보내 실제로 지운다.
      const hadValue = initial && initial[f.name] != null && String(initial[f.name]).trim() !== "";
      let val = chosen(f);
      if (f.type === "number") {
        if (val === "" || val == null) { if (f.required) { fail(f.name, f.label + objectParticle(f.label) + " 입력하세요."); return; } if (hadValue) body[f.name] = null; continue; }
        val = Number(val); if (Number.isNaN(val)) { fail(f.name, f.label + ": 숫자를 입력하세요."); return; }
        body[f.name] = val; continue;
      }
      else if (f.type === "checkbox") { const checkName = f.checkLabel || f.label; if (f.required && !val) { fail(f.name, checkName + objectParticle(checkName) + " 선택해야 합니다."); return; } body[f.name] = !!val; continue; }
      else if (f.type === "json") {
        if (!val || !String(val).trim()) { if (f.required) { fail(f.name, f.label + objectParticle(f.label) + " 입력하세요."); return; } if (hadValue) body[f.name] = null; continue; }
        let parsed;
        try { parsed = JSON.parse(val); } catch (e) { fail(f.name, f.label + ": JSON 형식이 올바르지 않습니다."); return; }
        // 일부 필드(예: 정책 content)는 백엔드가 JSON 객체만 허용한다 — 서버와 같은 문구로 먼저 막는다.
        if (f.jsonObject && (parsed === null || typeof parsed !== "object" || Array.isArray(parsed))) {
          fail(f.name, f.label + topicParticle(f.label) + " JSON 객체여야 합니다."); return;
        }
        body[f.name] = parsed;
        continue;
      }
      else if (f.type === "select" || f.type === "entity") {   // entity 도 «고르는» 값이다 — 문구와 빈 값 처리가 같다
        val = val == null ? "" : String(val);
        if (f.required && !val.trim()) {
          // 옵션 자체가 없으면 '선택하세요'는 헛도는 무한 루프다 — 원인이 다른 문구를 준다.
          if (!(f.options || []).length) { fail(f.name, f.label + ": 선택할 수 있는 항목이 없습니다. 다시 시도하거나 취소하세요."); return; }
          fail(f.name, f.label + objectParticle(f.label) + " 선택하세요."); return;
        }
        body[f.name] = val === "" ? null : val; continue;
      }  // 빈 선택("없음")은 null로 보내 기존 값을 지운다.
      else {
        val = val == null ? "" : String(val);
        if (f.required && !val.trim()) { fail(f.name, f.label + objectParticle(f.label) + " 입력하세요."); return; }
        // 사람이 적은 것은 KST 벽시계다 — 오프셋을 붙여 보내야 서버가 같은 순간으로 저장한다(F14).
        // 붙이지 않으면 서버가 규약대로 naive 를 UTC 로 읽어 9시간 밀린 채 저장된다.
        if (val !== "") body[f.name] = f.type === "datetime-local" ? kstLocalToApi(val) : val;
        else if (hadValue) body[f.name] = null;
      }
    }
    submitting.current = true;
    setBusy(true);
    try { await onSubmit(body); }
    catch (e) {
      // 세션 만료(401)는 여기서 재시도해도 항상 401이라, 일반 폼 오류 문구만 띄우면 사용자는
      // 자신이 방금 입력한 내용이 왜 저장되지 않는지 모른 채 이 모달 안에 막힌다.
      if (e && e.status === 401) {
        expireSession();
        return; // busy=true·submitting 을 남겨 재제출을 막는다 — 곧 페이지가 이동한다.
      }
      submitting.current = false;
      // UX-40: details({loc,msg} 배열, 예: 비밀번호 정책 위반) 합치는 로직은 lib/api.js의
      // api()로 옮겼다 — e.message가 이제 이미 합쳐진 문구다(모든 호출부가 공짜로 받는다).
      // 여기서 다시 합치면 details가 중복으로 붙는다.
      // PA-RC-0014: details[].loc 마지막 조각(필드명)이 이 폼의 필드와 일치하면 그 칸에
      // aria-invalid + 빨간 테두리를 건다 — 지금까지는 상단 알림 문구뿐이라 필드가 많은 폼
      // (사용자 생성 등)에서 어느 칸이 문제인지 눈으로 하나씩 훑어야 했다.
      const details = e && e.body && e.body.error && Array.isArray(e.body.error.details) ? e.body.error.details : null;
      const badField = details && details
        .map((d) => (Array.isArray(d.loc) && d.loc.length ? d.loc[d.loc.length - 1] : null))
        .find((name) => name && shownFields.some((f) => f.name === name));
      if (badField) { fail(badField, e.message || "저장하지 못했습니다. 다시 시도해 주세요."); setBusy(false); return; }
      setErr(e.message || "저장하지 못했습니다. 다시 시도해 주세요."); setBusy(false); return;
    }
    submitting.current = false;
    setBusy(false);
  }

  /* 크기는 **열릴 때 한 번** 정한다 (R-12).
   * 예전에는 매 렌더마다 `shownFields.length` 로 다시 골랐다 — 조건부 필드가 있는 폼(사용자
   * 편집에서 역할을 바꾸면 필드가 늘어난다)에서 사용자가 select 하나를 건드리는 순간 모달이
   * 45rem -> 62rem 로 **열린 채 넓어졌다.** 크기는 이 창이 무엇인지에 대한 사실이지 지금 몇
   * 칸이 보이는가에 대한 사실이 아니다. */
  /* **필드가 많다고 넓어지지 않는다** (W5 · F-W5D-136).
   *
   * 예전 규칙은 «필드 > 5 이면 lg(62rem)» 였다. 그런데 이 폼은 **언제나 한 열**이다 —
   * 필드가 많으면 세로로 길어지지 가로로 넓어지지 않는다. 실측: 필드 6개짜리 폼이 942px
   * 폭을 받아 한 열짜리 입력이 그 안에 놓였다(입력 하나가 화면 절반). 같은 파일이 `lg` 를
   * 「열이 여럿인 것」용이라고 선언해 놓고 그 규칙을 스스로 어기고 있었다.
   *
   * 길이는 세로 스크롤이 감당한다. 진짜로 여러 열인 폼은 호출부가 `size="lg"` 로 **말한다** —
   * 개수가 아니라 구조가 크기를 정한다. */
  if (sizeAtOpen.current == null) sizeAtOpen.current = "md";
  const sz = size || sizeAtOpen.current;
  const footer = <ModalFooter onCancel={requestClose} onSubmit={submit} submitLabel={submitLabel || "저장"} busy={busy} />;
  return (
    <Modal open={open} onClose={requestClose} title={title} size={sz} footer={footer}>
      {/* 필드를 <form>으로 감싸 Enter가 자연스럽게 제출되게 한다(textarea/json은 여러 줄 입력을
          위해 기본 Enter 동작 유지). */}
      <Box
        component="form"
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        /* 칸 사이 간격은 폼이 준다(20, D-527) - 칸이 각자 아래 여백을 들지 않는다. */
        sx={{ display: "flex", flexDirection: "column", rowGap: 2.5, minWidth: 0 }}
      >
        {/* **한 오류에 표현 하나** (PLAN C5 «Feedback 위계»).
            예전에는 필드 하나가 틀렸을 때 전폭 테두리 상자 **와** 그 필드 아래 인라인 문구가
            동시에 떴다 — 같은 문자열이 두 번. C5 는 전폭 상자를 「행동이 있는 것」에만 허용하고,
            어느 칸을 고치면 되는지는 그 칸 옆에서 말하는 것이 가장 짧은 경로다(그리고 이미
            그 칸으로 스크롤·포커스한다). 그래서 **필드를 지목한 오류는 인라인만** 쓴다.
            전폭 상자는 필드를 지목하지 못한 오류(서버 거절·네트워크)에만 남는다 — 그때는
            인라인으로 붙일 자리가 없어서 상자가 유일한 자리다. */}
        {err && !errField ? <Callout tone="danger" className="k-form-err" role="alert">{err}</Callout> : null}
        {shownFields.map((f) => <FormField key={f.name} field={f} value={chosen(f)} invalid={errField === f.name}
          onChange={(val) => set(f.name, val)}
          errorMessage={errField === f.name ? err : undefined}
          maxLength={screenKey ? maxLengthFor(screenKey, formKind, f.name) : null} />)}
        {/* 화면에 보이지 않는 제출 버튼 — 실제 저장 버튼은 Dialog footer(별도 DOM 트리)에 있어
            이 <form> 안에 없다. type="submit"이 하나도 없으면 브라우저에 따라 단일 텍스트
            입력에서 Enter가 폼을 제출하지 않는다. */}
        <button type="submit" className="sr-only" tabIndex={-1} aria-hidden="true" />
      </Box>
    </Modal>
  );
}
/* 하위호환 별칭 — 서랍(drawer)이던 시절의 이름을 남겨 둔 자리다. 전부 중앙 모달로 동작한다.
 *
 * 별칭이 셋이었는데 실제 소비자는 `FormDrawer`(DataScreen)와 `DialogFooter`(이 파일의
 * Confirm) 둘뿐이었다 — `FormDialog` 는 아무도 부르지 않았다. 쓰이지 않는 별칭은 같은 것을
 * 부르는 이름을 하나 더 만들 뿐이라 지운다(지시 23). */
// `Drawer = Modal`은 뺐다(DS-10) — 진짜 옆에서 밀려나오는 드로어(AppShell 사이드바,
// AssistantDrawer)는 애초에 이 별칭을 안 쓰고 `@mui/material/Drawer`를 직접 쓴다. 이 이름은
// 중앙 모달 6곳에서만 쓰이고 있었는데, 이름이 "드로어"라 실제 동작(가운데 다이얼로그)과
// 어긋나 혼동을 줬다 — 호출부를 전부 `Modal`로 고쳐 부른다(동작은 그대로, 이름만 정확해짐).
export const FormDrawer = FormModal;
export const DialogFooter = ModalFooter;

/* 스타일된 확인 대화상자(중앙 모달) — window.confirm 대체. useConfirm()이 async 함수를 준다. */
const ConfirmCtx = React.createContext(() => Promise.resolve(false));
export function ConfirmProvider({ children }) {
  const [state, setState] = React.useState(null);
  const confirm = React.useCallback((message, opts) =>
    new Promise((resolve) => setState({ message, resolve, danger: opts && opts.danger, title: (opts && opts.title) || "확인", confirmLabel: (opts && opts.confirmLabel) || "확인" })), []);
  const done = (val) => { setState((s) => { if (s) s.resolve(val); return null; }); };
  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      <Modal open={!!state} onClose={() => done(false)} title={state ? state.title : ""} size="sm"
        tone={state && state.danger ? "danger" : undefined}
        footer={<DialogFooter onCancel={() => done(false)} onSubmit={() => done(true)}
          /* 되돌릴 수 없는 확인에서는 취소가 기본 포커스다(RULES §8) — Enter 한 번이 파괴가 되지 않는다. */
          cancelAutoFocus={!!(state && state.danger)}
          /* 확인 대화의 마지막 버튼만 채운 error 면을 쓴다 — 여기서는 파괴적 동작이
             이 화면(모달)의 주 행동이고, 사용자는 이미 그것을 하기로 정한 상태다.
             화면 본문의 `danger` 는 외곽선이다(위 BUTTON_VARIANT 주석). */
          submitLabel={state ? state.confirmLabel : "확인"} submitVariant={state && state.danger ? "dangerConfirm" : "primary"} />}>
        <Typography sx={{ whiteSpace: "pre-line" }}>{state ? state.message : ""}</Typography>
      </Modal>
    </ConfirmCtx.Provider>
  );
}
export function useConfirm() { return React.useContext(ConfirmCtx); }

/* 토스트 — window.alert 대체. useToast()(message, kind).
 * 오류는 더 오래 남기고(8s) 직접 닫기 버튼을 준다 — 3.5s에 사라지면 무엇이 실패했는지 놓친다.
 *
 * 낭독은 **바깥 라이브 영역 하나**가 맡는다. 예전에는 그 영역 안의 MUI Alert 이 자기
 * role="alert" 을 들고 있어 같은 문장이 두 번 읽혔다(라이브 영역 한 번, alert 한 번).
 * MUI Alert 은 role 기본값이 'alert' 이라 `role={undefined}` 로는 지워지지 않는다 —
 * 표시용 role("presentation")로 덮어써야 사라진다.
 *
 * 급함의 정도: 정보·성공은 polite(사용자가 읽고 있던 문장을 자르지 않는다), 오류만
 * assertive 다 — 저장 실패처럼 다음 행동이 달라지는 소식은 지금 알려야 한다.
 *
 * Snackbar 를 늘 띄워 두는 이유: 라이브 영역이 **내용과 같은 순간에 생기면** 그 변화를
 * 낭독하지 않는 스크린리더가 있다. 비어 있는 동안에는 클릭도 가로채지 않는다. */
let _toastSeq = 0;
const ToastCtx = React.createContext(() => {});
export function ToastProvider({ children }) {
  const [toasts, setToasts] = React.useState([]);
  const dismiss = React.useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  /* 🔴 사라지는 타이머를 **언마운트에서 걷는다.**
   *
   * 오류 토스트는 8초를 산다. 그 사이에 이 Provider 가 사라지면(라우트 이동·시험 종료)
   * 타이머는 그대로 살아 있다가 없어진 컴포넌트의 `setToasts` 를 부른다. 브라우저에서는
   * React 가 조용히 무시하지만, 그 무시가 공짜인 것은 아니다 — 시험 환경에서는 창이
   * 이미 걷혀서 `ReferenceError: window is not defined` 가 **어느 시험의 것인지도 모르는
   * 채로** 났다(전량 실행이 그것을 잡았다).
   *
   * 브라우저 동작은 안 바뀐다. 살아 있는 동안에는 지금까지와 똑같이 시간이 지나면 사라진다. */
  const timers = React.useRef(new Set());
  React.useEffect(() => () => {
    for (const t of timers.current) clearTimeout(t);
    timers.current.clear();
  }, []);
  const push = React.useCallback((message, kind) => {
    const id = ++_toastSeq;
    const k = kind || "info";
    setToasts((t) => [...t, { id, message, kind: k }]);
    const ttl = k === "error" ? 8000 : 3500;
    const timer = setTimeout(() => {
      timers.current.delete(timer);
      setToasts((t) => t.filter((x) => x.id !== id));
    }, ttl);
    timers.current.add(timer);
  }, []);
  const urgent = toasts.some((t) => t.kind === "error");
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <MuiSnackbar
        open
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        sx={{ maxWidth: "min(92vw, 30rem)", pointerEvents: toasts.length ? "auto" : "none" }}
      >
        {/* 전이(Grow)는 자기 프롭을 자식에게 그대로 넘긴다 — 그 자식이 Stack 이면 Snackbar 가
            넣는 `direction`("up")이 Stack 의 배치 방향으로 오해돼 경고가 난다. 전이가 잡는
            자리는 평범한 상자로 두고 목록은 그 안에 둔다. 라이브 영역도 이 바깥 상자다:
            안쪽 목록이 비어도 영역 자체는 남아 있어야 한다. */}
        <Box sx={{ width: "100%" }} aria-live={urgent ? "assertive" : "polite"} aria-atomic="false">
          <Stack gap={1} sx={{ width: "100%" }}>
            {toasts.map((t) => (
              <MuiAlert
                key={t.id}
                severity={TONE_SEVERITY[t.kind] || (t.kind === "error" ? "error" : t.kind === "success" ? "success" : "info")}
                variant="filled"
                /* 낭독은 바깥 라이브 영역이 한다. 여기 role 을 남기면 같은 문장을 두 번 읽는다.
                   severity 가 주는 색·아이콘은 그대로다(시각 정보는 잃지 않는다). */
                role="presentation"
                onClose={() => dismiss(t.id)}
                /* 토스트는 **잉크 면 + 흰 글자** 하나다(핸드오프 README §10) — 상태색 면이 아니다.
                   상태는 아이콘 모양이 말한다. 다크에서는 잉크 면이 캔버스와 안 갈리므로 함몰면 +
                   strong 테두리다(RULES §13). 모서리는 떠 있는 것의 8. */
                sx={(theme) => ({
                  width: "100%",
                  borderRadius: `${RADIUS.md}px`,
                  ...(theme.palette.mode === "dark"
                    ? { bgcolor: "background.inset", color: "text.primary", border: 1, borderColor: "dividerStrong" }
                    : { bgcolor: "text.primary", color: "common.white" }),
                  "& .MuiAlert-icon, & .MuiAlert-action": { color: "inherit" },
                })}
              >
                {t.message}
              </MuiAlert>
            ))}
          </Stack>
        </Box>
      </MuiSnackbar>
    </ToastCtx.Provider>
  );
}
export function useToast() { return React.useContext(ToastCtx); }

/* PA-RC-0039: crumbRoot의 기본값이 리터럴 "관리자"였다 — 사용자 콘솔 화면이 그 prop을
 * 잊으면 조용히 "관리자"가 새어 나갔다(TeamDocs.jsx·DataScreen.jsx가 실제로 그랬다).
 * kit.jsx는 라우팅을 모르는 채로 남긴다(useLocation을 여기서 부르면 Router 없이 렌더하는
 * 기존 kit.test.jsx 다수가 깨진다) — 대신 AppShell.jsx가 지금 콘솔+navConfig 그룹에서 값을
 * 계산해 Context로 흘려보낸다. Provider가 없으면(격리 렌더·기존 테스트) undefined → 아래
 * PageHeader가 그대로 "관리자"로 떨어져 회귀가 없다. 호출부가 crumbRoot를 명시하면(Trash.jsx
 * 등) 그 값이 always 이긴다.  */
const CrumbRootCtx = React.createContext(undefined);
export function CrumbRootProvider({ value, children }) {
  return <CrumbRootCtx.Provider value={value}>{children}</CrumbRootCtx.Provider>;
}

/* 페이지 헤더 — 빵부스러기→제목 순서와 간격을 한곳에서 정한다.
 * crumbRoot: 빵부스러기 접두어. 명시하면 그 값, 안 하면 위 CrumbRootProvider가 콘솔에 맞게
 *   계산한 값, 그것도 없으면(Provider 밖) "관리자"다. area를 비우면 빵부스러기 자체를 숨길 수 있다.
 *
 * **장식 일러스트 prop 은 없다.** Q4 가 투명 클로비를 뺀 뒤로 `spot` 은 아무것도 안 하는
 * prop 이었는데 화면 열일곱이 계속 값을 넘기고 있었다 — 읽는 사람은 그 화면에 그림이 있다고
 * 믿고, 새 화면은 그 줄을 복사한다. 죽은 prop 은 «지금 없는 기능» 이 아니라 «있다고 잘못
 * 알려 주는 기능» 이다. prop 과 호출부 열일곱을 함께 지웠다(지시 71 «Clovi 금지 구역»:
 * 데이터 표·설정 화면·상세 본문·Page Header 장식). 클로비는 히어로·빈 상태·드로어·상단바
 * 처럼 **의미가 있는 자리**에만 둔다. */
export function PageHeader({ area, title, actions, overflow, crumbRoot, size = "page", description, help, helpTone }) {
  const ctxCrumbRoot = React.useContext(CrumbRootCtx);
  const resolvedCrumbRoot = crumbRoot !== undefined ? crumbRoot : (ctxCrumbRoot !== undefined ? ctxCrumbRoot : "관리자");
  /* size="section" — 다른 화면 안에 곁들여지는 하위 패널(예: OrgConsole 오른쪽의 DataScreen)이
   * 이 컴포넌트를 그대로 쓰면 h4/h1 이 감싸는 페이지의 진짜 제목과 같은 무게라 "페이지가
   * 두 개 겹쳐 있다"처럼 읽힌다(사용자 지적: 조직도 화면에서 조직 관리 패널이 또 하나의
   * 페이지처럼 보임). 글자만 작게(h6/h2) 줄이는 하위 무게 — breadcrumb(area)는 상위
   * 페이지가 이미 보여 주므로 호출부는 보통 area=null 을 같이 넘긴다. */
  const isSection = size === "section";
  /* 🔴 여기 `tab` prop 이 있었다(PA-RC-0017) — 탭 라벨이 h1 이 되고 제목은 빵부스러기로
     올라갔다. 그래서 `/schedules` 의 h1 은 「목록」이었고 `/settings?tab=ai` 의 h1 은 「AI」
     였다. 사용자 탭 화면(승인·휴지통·프로젝트 상세)은 제목을 고정하고 탭을 그 아래 둔다 —
     관리자 그릇도 같은 모양이다(D-452). 호출부가 둘(TabShell·SettingsShell)뿐이라 prop
     자체를 걷었다. */
  const crumb = [resolvedCrumbRoot, area].filter(Boolean).join(" › ");
  const heading = title;
  // PA-RC-0022: 상시 안내 패널(8+ 화면, 실제로는 registry 28개 화면 전부가 DataScreen.jsx를
  // 통해 이 자리를 썼다)을 "제목 옆 도움말 토글"로 옮긴다 — 내용은 그대로, 기본 접힘만 바뀐다.
  // `SectionTitle`(아래, 카드 안 소제목)에도 `help` prop이 있지만 그건 상시 노출되는 평문
  // 한 줄이다 — 이름은 같아도 다른 컴포넌트의 다른 prop이라 여기서 새로 만든다. 화면마다
  // 매번 `useState`를 새로 선언하게 하지 않으려고(호출부 28곳을 전부 고치는 대신) 접힘
  // 상태를 이 컴포넌트가 직접 들고, 호출부는 `help` 내용만 넘긴다.
  const [helpOpen, setHelpOpen] = React.useState(false);
  /* `Math.random()` 이었다 — 렌더마다 id 가 바뀌어 `aria-controls` 가 매번 다른 노드를 가리켰다. */
  const autoId = React.useId();
  const helpId = help ? "page-help-" + autoId : undefined;
  /* 머리는 **한 상자**다(D-528): 경로 → [제목 + 도움말] … [동작] → 한 문장 설명 → 도움말 펼침. 설명과 도움말이 머리 밖 형제였을
     때는 흐름 그릇(`.c-screen`, 간격 16)이 그 사이를 벌렸고, 접힌 도움말(높이 0)에도 간격이 붙었다. 머리 안에서는 설명이 제목에
     바짝 붙고(4), 머리와 다음 덩어리 사이는 그릇이 준다. 흐름 밖(모달 안 등)에서만 아래 여백이 남는다. */
  return (
    <Box
      className="k-page-head"
      sx={{ position: "relative", display: "flex", flexDirection: "column", rowGap: 0.5, minWidth: 0, mb: isSection ? 1.5 : 3 }}
    >
      {crumb ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontWeight: FONT_WEIGHT.semibold }}>
          {crumb}
        </Typography>
      ) : null}
      {/* [제목 + 도움말] … [동작] 이 **제목 줄 가운데선**에 선다. 예전에는 한 줄을 `flex-end` 로 바닥 정렬해 경로와 제목을 한
          덩어리로 보고 동작을 그 덩어리 바닥에 붙였다. 제목 줄(1.75rem × 1.22)과 동작(34)의 높이가 거의 같아 가운데 정렬이 곧
          첫 줄 정렬이다. 주 행동과 파괴적 행동을 같은 줄에서 경쟁시키지 않는다(지시 11 · 12, E8) — 드물거나 되돌리기 어려운
          것은 `overflow` 메뉴로 간다. */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: isSection ? 1.5 : 3, flexWrap: "wrap", minWidth: 0 }}>
        <Box sx={{ position: "relative", zIndex: 1, flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 0.5 }}>
          <Typography variant={isSection ? "h6" : "h4"} component={isSection ? "h2" : "h1"}>{heading}</Typography>
          {help ? (
            <IconButton
              /* 크기는 **이 줄의 이웃**을 따른다 — 같은 줄 오른쪽의 동작은 기본 버튼(34)이다(W5 재정정). */
              onClick={() => setHelpOpen((v) => !v)}
              aria-expanded={helpOpen}
              aria-controls={helpId}
              aria-label={helpOpen ? "도움말 닫기" : "도움말 보기"}
              sx={{ color: "text.secondary" }}
            >
              <HelpOutlineRoundedIcon fontSize={isSection ? "small" : "medium"} />
            </IconButton>
          ) : null}
        </Box>
        {actions || (overflow && overflow.length) ? (
          <Box className="k-page-actions" sx={{ position: "relative", zIndex: 1, display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            {actions}
            {overflow && overflow.length ? <OverflowMenu items={overflow} /> : null}
          </Box>
        ) : null}
      </Box>
      {/* 짧은 화면 설명 — **자리와 간격이 화면마다 같다** (지시 21). 한 문장이라 `70ch` 를 걸지 않는다(CLAUDE.md §10). */}
      {description ? (
        <Typography className="k-page-desc" variant="body2" color="text.secondary" component="p" sx={{ m: 0, ...KO_WORD_BREAK }}>
          {description}
        </Typography>
      ) : null}
      {help ? (
        <Collapse in={helpOpen} id={helpId}>
          <Box sx={{ pt: 1 }}>
            <Callout tone={helpTone}>{help}</Callout>
          </Box>
        </Collapse>
      ) : null}
    </Box>
  );
}

/* 구획(Section) — 체크리스트 ⑥ 이 가리키는 **컨테이너 없는 묶음**의 부품.
 *
 * "무언가를 묶어야 한다 = 흰 네모를 만든다" 는 반사를 막으려면 금지만으로는 부족하다 —
 * 그 자리에 **쓸 것**이 있어야 한다. 판정 체크리스트가 ⑥ 에 도달했을 때 화면이 집는 것이
 * 이것이다: 제목 + 구획 간격, 그리고 목록이면 제목 아래 실선 하나. 판도 테두리도 없다.
 *
 *   <Section title="최근 문서" action={<Link…/>}>…</Section>
 *   <Section title="상태" rule>…</Section>          // 목록형 — 제목 아래 괘선
 *
 * `SectionTitle` 은 판 **안**의 소제목이라 자기 바깥 간격을 모른다. `Section` 은 그
 * 바깥 간격(`SECTION_GAP`)까지 소유한다 — 화면마다 `mb: 4` 같은 숫자를 손으로 적던
 * 자리가 여기 하나로 모인다. */
/* `titleAs` — 제목의 **단계**다(`h2`/`h3`). 기본은 `h3` 이고, 그 자리는 판 안의 소제목이다.
 *
 * 🔴 이 prop 이 없어서 구획 부품이 두 벌이었다. 관리자 화면은 페이지 제목(h1) 바로 아래에
 * 구획이 오므로 `h2` 가 맞는데 이 부품이 `h3` 만 그려서, 그쪽은 `adminKit::DashSection`
 * 이라는 **두 번째 구획 부품**을 따로 들고 있었다 — 같은 성질의 묶음이 콘솔마다 다른
 * 부품으로 그려지면 한쪽에 붙인 것(괘선·도움말)이 다른 쪽에 영영 안 온다. 단계 하나를
 * 받게 해서 부품을 하나로 합친다. */
export function Section({ title, action, help, rule = false, component = "section", titleAs = "h3", flush = false, children, sx }) {
  /* 호출부의 `sx` 가 함수일 수도 있다(테마를 읽는 자리). 객체로만 받아 펼치면 함수는
     **조용히 사라진다** — 이 저장소가 여러 번 밟은 "선언은 있는데 화면에는 없다" 의 한 형태다.
     `Surface` 가 두 형태를 모두 받으므로 여기서 형태를 유지한 채 넘긴다.
     `flush` — 아래 구획 간격을 걷는다. 그릇(흐름 · 격자 · 판)이 간격을 주는 자리다(숫자 여백을 화면이 적지 않는다). */
  const gapSx = { mb: flush ? 0 : SECTION_GAP };
  const merged = typeof sx === "function"
    ? (theme) => ({ ...gapSx, ...sx(theme) })
    : { ...gapSx, ...sx };
  return (
    <Surface tone="none" component={component} sx={merged}>
      {title ? <SectionTitle title={title} action={action} help={help} component={titleAs} sx={rule ? { mb: 1 } : undefined} /> : null}
      {rule ? <Box sx={{ borderTop: 1, borderColor: "divider", mb: 1.5 }} /> : null}
      {children}
    </Surface>
  );
}

/* 카드/패널 안의 소제목(PageHeader보다 한 단계 아래) — 예전엔 Home.jsx `CardHead`,
 * MyStats.jsx `CardHead`, Profile.jsx `SectionTitle`, AssistantPanel.jsx 인라인 코드로
 * 네 벌이 따로 있었다(DS-07). 넷 다 폰트 크기는 이미 17px로 수렴돼 있었지만(재검증으로
 * 확인), 컴포넌트 자체가 갈라져 있어 나중에 하나를 고치면 나머지 셋이 안 따라왔다.
 * title/children 둘 다 받는다(호출부 관성을 다 지원), action(오른쪽 링크·버튼)과
 * help(아래 설명문)는 있으면만 그린다.
 * PA-RC-0001: 이 컴포넌트가 그리는 17px가 바로 RD-1의 sectionTitle 단계다 — variant="h6"
 * + sx fontSize 오버라이드 대신 theme.js의 그 variant를 직접 쓴다(같은 값, letterSpacing도
 * body1/body2와 같은 계열로 맞춰짐 — h6 기본엔 없던 값이라 시각적으로 더 일관돼진다). */
/**
 * 구획 머리 (D-528). [제목 + 건수] … [동작] 이 **제목 줄 가운데선**에 서고, 도움말은 그 아래 전체 폭 한 줄이다.
 *
 * 예전 `SectionTitle` 은 제목과 도움말을 한 상자에 쌓고 동작을 **그 상자의** 가운데에 맞췄다 - 도움말이 있으면 단추가 제목과
 * 도움말 사이 어딘가에 떠 있었다(내 프로필은 `flex-start` 로 덮어 썼다). 동작은 제목 줄에만 선다.
 */
/* 머리 아래 간격은 숫자가 아니라 뜻으로 고른다(정적 검사 `primitive-geometry-override`): normal 12 · tight 8 · none 0(그릇이
   간격을 주는 자리 - 격자 · 흐름). */
const SECTION_HEADER_SPACING = { normal: 1.5, tight: 1, none: 0 };

export function SectionHeader({ title, children, action, help, count, component = "h3", spacing = "normal", sx }) {
  const label = title != null ? title : children;
  return (
    <Box className="k-section-header" sx={{ minWidth: 0, mb: SECTION_HEADER_SPACING[spacing] ?? 1.5, ...sx }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap", minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, flexWrap: "wrap" }}>
          <Typography component={component} variant="sectionTitle">{label}</Typography>
          {count != null ? <CountChip value={count} compact /> : null}
        </Box>
        {action ? <Box className="k-section-header-action" sx={{ display: "flex", alignItems: "center", gap: 1, flexShrink: 0 }}>{action}</Box> : null}
      </Box>
      {/* 설명은 제목보다 두 단 작다(0.8125rem) — 확정 규약의 카드 머리 한 쌍이다. 동작 상자 안에 넣지 않는다. */}
      {help ? (
        <Typography color="text.secondary" sx={{ mt: 0.5, fontSize: FONT_SIZE.caption, lineHeight: LINE_HEIGHT.caption, ...KO_WORD_BREAK }}>
          {help}
        </Typography>
      ) : null}
    </Box>
  );
}

/* 옛 이름 - 판 안의 소제목을 그리던 부품이다. 이제 `SectionHeader` 가 그린다. */
export function SectionTitle(props) {
  return <SectionHeader {...props} />;
}

/** 판 **안쪽**의 정보 묶음 — 판을 새로 만들지 않고 실선과 여백과 소제목으로 가른다.
 *
 * 카드 안에 또 흰 카드를 넣으면 표면이 두 겹이 되고, 두 겹이 되는 순간 사용자는 안쪽
 * 상자를 「다른 것」으로 읽는다. 같은 판 위의 다른 문단일 뿐인데 그렇다. `Surface` 가
 * 깊이 1 이상의 판을 자동으로 눕히기는 하지만, 눕은 판은 여백만 남기고 아무 뜻도 안
 * 나른다 — 처음부터 이 부품을 쓰는 것이 맞다.
 *
 * 위 실선 하나와 소제목 하나가 묶음의 전부다. `first` 를 주면 실선을 안 그린다(첫 묶음은
 * 위에 가를 것이 없다).
 *
 * 소제목은 기본 `h3` 다 — 판 제목이 `h2` 인 화면(홈의 구역들)에서 단계를 안 건너뛴다.
 */
export function SubGroup({ title, help, component = "h3", first = false, spacing = "normal", children, sx }) {
  /* `spacing="tight"` — 위 실선은 그대로 두고 바깥 위 간격만 좁힌다(바로 위가 같은 판의 목록일 때). 숫자 여백을 화면이
     적지 않게 뜻으로 고른다(정적 검사 `primitive-geometry-override`). */
  return (
    <Box
      sx={{
        minWidth: 0,
        ...(first ? null : { mt: spacing === "tight" ? 0.5 : 2.5, pt: 2.5, borderTop: 1, borderColor: "divider" }),
        ...sx,
      }}
    >
      {title ? (
        <Typography
          component={component}
          sx={{
            fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold, color: "text.secondary",
            mb: help ? 0.5 : 1, ...KO_WORD_BREAK,
          }}
        >
          {title}
        </Typography>
      ) : null}
      {help ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25, ...KO_WORD_BREAK }}>{help}</Typography>
      ) : null}
      <StateRegionCtx.Provider value>{children}</StateRegionCtx.Provider>
    </Box>
  );
}

/* 상세의 키/값 줄 — **한 벌**이다 (D-457).
 *
 * 네 벌이 있었다: `DataScreen` 상세 모달(`c-kv` 클래스 + sx 10rem), `Users.jsx` 의 상세
 * (같은 sx 사본), `registry/governance.js` 의 승인 payload(`.c-kv` CSS — 120px 라벨),
 * `data-screen/JsonBlock.jsx::KeyValueRow`(10rem, 라벨에 `break-all`). CSS 와 sx 가 같은
 * 특이도로 다퉈 어느 쪽이 이기는지가 주입 순서에 달려 있었다. 값의 정본은 이 부품이고,
 * 사용자 화면(`/profile`)도 같은 줄을 쓴다.
 *
 *   dense  JSON·UUID 같은 기계 문자열이 라벨/값에 오는 자리 — 글자 단위로 꺾는다. 기본은
 *          한국어라 낱말 단위(`keep-all`)다.
 *
 * 넓은 화면에서는 `DetailGrid` 가 줄을 두세 열로 접는다 — 4K 에서 한 열로 길게 늘어놓으면
 * 오른쪽이 통째로 비고 눈은 위아래로만 움직인다. */
export const DETAIL_GRID_SX = {
  display: "grid", columnGap: 4, rowGap: 0,
  gridTemplateColumns: { xs: "1fr", xxl: "repeat(2, minmax(0,1fr))", uhd: "repeat(3, minmax(0,1fr))" },
};

export function DetailGrid({ children, sx }) {
  return <Box data-detail-grid="" sx={{ ...DETAIL_GRID_SX, ...sx }}>{children}</Box>;
}

export function DetailRow({ label, dense = false, children, sx }) {
  const breakSx = dense ? ANYWHERE_BREAK : KO_WORD_BREAK;
  return (
    <Box
      data-detail-row=""
      sx={{
        display: "grid", gridTemplateColumns: { xs: "1fr", sm: "10rem minmax(0,1fr)" },
        gap: dense ? { xs: 0.25, sm: 1.5 } : 1, py: dense ? 0.75 : 1,
        borderBottom: 1, borderColor: "divider", minWidth: 0,
        "&:last-child": { borderBottom: 0 },
        ...sx,
      }}
    >
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0, ...breakSx }}>{label}</Typography>
      <Box sx={{ minWidth: 0, ...breakSx }}>{children}</Box>
    </Box>
  );
}
