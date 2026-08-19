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
import MoreHorizRoundedIcon from "@mui/icons-material/MoreHorizRounded";
import HelpOutlineRoundedIcon from "@mui/icons-material/HelpOutlineRounded";
import Collapse from "@mui/material/Collapse";
import { ART, SPOT } from "../lib/assets.js";
import { maxLengthFor } from "../lib/fieldLimits.js";
import { apiToKstLocal, kstLocalToApi } from "../lib/format.js";
import { declaredRowName, rowNameOf } from "./rowName.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, MOTION, NUMERIC, RADIUS, TABLE_CARD_QUERY, TABLE_COMPACT_QUERY } from "./theme.js";
import { CARD_PADDING, SECTION_GAP } from "./density.js";
import { loginUrl, redirectToLogin } from "../lib/sessionRedirect.js";
import { prefersReducedMotion } from "./motion.js";

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
  "시작 전": "시작 전", "진행 중": "진행 중", "완료": "완료", "할 일": "할 일",
  // 조직마다 Notion 보드에서 흔히 쓰는 그 밖의 상태값 — 위 4종만 있으면 실제 워크스페이스가
  // 쓰는 'In Review'/'Blocked' 등이 여전히 원시 영어로 새어 나온다.
  "In Review": "검토 중", "Blocked": "막힘", "Cancelled": "취소됨", "On Hold": "보류",
  "Backlog": "백로그", "검토 중": "검토 중", "막힘": "막힘", "보류": "보류", "백로그": "백로그",
  // 이 워크스페이스 작업 DB의 실제 진행상태 6종(채팅 티켓 카드·배지) — 원시 그대로 통과하지만 명시해 둔다.
  "계획": "계획", "이슈": "이슈", "검증": "검증", "진행": "진행", "취소": "취소",
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
  configured: "ok", "Done": "ok", "완료": "ok",
  "In progress": "info", "진행 중": "info",
  "Not started": "neutral", "시작 전": "neutral", "Todo": "neutral", "할 일": "neutral",
  "In Review": "info", "검토 중": "info", "Blocked": "danger", "막힘": "danger",
  "Cancelled": "neutral", "취소됨": "neutral", "On Hold": "warn", "보류": "warn",
  "Backlog": "neutral", "백로그": "neutral",
  // 작업 DB 실제 진행상태 6종의 톤 — 예전엔 대부분 매핑이 없어 회색 일색이었다. 의미 있는 색으로:
  // 계획=회색(대기) 이슈=빨강(주의) 검증=주황(리뷰) 진행=파랑(활성) 완료=초록 취소=회색(비활성).
  "계획": "neutral", "이슈": "danger", "검증": "warn", "진행": "info", "취소": "neutral",
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

// 키트의 톤 어휘 → MUI 색 이름. 한 곳에서만 번역한다.
const TONE_COLOR = { ok: "success", danger: "error", warn: "warning", info: "info", neutral: "default" };
const TONE_SEVERITY = { danger: "error", warn: "warning", success: "success", info: "info" };
// MUI Chip color 팔레트 밖의 톤(문서 종류·게시판 분류 등) — tokens.css의 --badge-*-bg/fg 변수를
// 그대로 쓴다(다크모드 대응·대비 검증 이미 돼 있는 값). lib/badges.js가 이 네 톤을 배정하는데
// 예전엔 여기 목록이 없어 전부 회색 필 칩으로 뭉개졌다(DS-09).
const EXTRA_TONE_VARS = {
  purple: { bg: "var(--badge-purple-bg)", fg: "var(--badge-purple-fg)" },
  teal: { bg: "var(--badge-teal-bg)", fg: "var(--badge-teal-fg)" },
  indigo: { bg: "var(--badge-indigo-bg)", fg: "var(--badge-indigo-fg)" },
  pink: { bg: "var(--badge-pink-bg)", fg: "var(--badge-pink-fg)" },
};

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
  const strong = emphasis === "strong" || k === "danger";

  /* 표지 모양이 톤마다 다르다 — 흑백으로 인쇄하거나 색을 못 봐도 구분된다. */
  const marker = { ok: "50%", danger: "2px", warn: "2px", info: "50%" }[k] || "1px";

  return (
    <Box
      component="span"
      className="k-badge"
      data-tone={k}
      sx={{
        display: "inline-flex", alignItems: "center", gap: 0.625,
        maxWidth: "100%", minWidth: 0,
        fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.medium, lineHeight: 1.4,
        whiteSpace: "nowrap",
        color: extra ? extra.fg : palette ? `${palette}.strong` : "text.secondary",
        ...(strong && {
          px: 0.75, py: 0.125, borderRadius: `${RADIUS.sm}px`,
          bgcolor: extra ? extra.bg : palette ? `${palette}.bg` : "background.inset",
          fontWeight: FONT_WEIGHT.semibold,
        }),
      }}
    >
      <Box
        aria-hidden="true"
        component="span"
        sx={{
          flexShrink: 0, width: 6, height: 6, borderRadius: marker,
          bgcolor: extra ? extra.fg : palette ? `${palette}.main` : "text.faint",
        }}
      />
      <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>{statusText(value)}</Box>
    </Box>
  );
}

/** 분류 표시 — 상태가 아니다 (지시 11: Status / Category / Tag / Editable Value 를 구분한다).
 *
 * 문서 종류(매뉴얼·참고자료·회의록)·업무 분야(인프라·개발·운영) 같은 것. 좋고 나쁨이 없으므로
 * 상태색을 쓰지 않는다 — 중립 램프 위 옅은 면 하나다. */
export function Tag({ label, tone }) {
  const extra = EXTRA_TONE_VARS[tone];
  return (
    <Box
      component="span"
      className="k-tag"
      data-tone={tone || "neutral"}
      sx={{
        display: "inline-flex", alignItems: "center", maxWidth: "100%", minWidth: 0,
        px: 0.75, py: 0.125, borderRadius: `${RADIUS.sm}px`,
        fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.medium, lineHeight: 1.5,
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        bgcolor: extra ? extra.bg : "background.inset",
        color: extra ? extra.fg : "text.secondary",
      }}
    >
      {label}
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
/* loading: 라벨을 "처리 중…"으로 바꿔치기하지 않는다(예전 DataScreen/ModalFooter 관행) —
 * 텍스트만 바뀌면 스피너도 없고 버튼 폭도 라벨 길이 따라 흔들린다(DS-04). 라벨은 그대로 두고
 * visibility만 숨겨 폭을 고정한 채 스피너를 겹쳐 그린다. */
// forwardRef: MUI 컴포넌트(Tooltip 등)가 자식 DOM 노드에 직접 ref를 걸어야 하는 경우가 있다
// (Tooltip은 호버 위치를 앵커에서 계산한다) — 일반 함수 컴포넌트면 그 ref가 조용히 버려진다.
export const Button = React.forwardRef(function Button({ variant = "default", size, loading = false, disabled, children, sx, ...rest }, ref) {
  const v = BUTTON_VARIANT[variant] || BUTTON_VARIANT.default;
  const isSm = size === "sm";
  return (
    <MuiButton
      ref={ref}
      type="button"
      size={isSm ? "small" : "medium"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...v}
      {...rest}
      sx={(theme) => ({
        position: "relative",
        /* 보조 버튼의 **테두리가 주 행동보다 강했다** (R-11 실측).
           MUI v7 의 `outlined` + `color="inherit"` 은 테두리를 `currentColor` 로 그린다
           (`@mui/material/Button/Button.js`) — 이 앱에서 그것은 `text.primary`(#161A2C) 이고
           판 위 대비 **17.1:1** 이다. 같은 화면의 채운 primary 가 5.96:1 이니 보조가 주보다
           2.9배 강했다. 배포본 픽셀로 확인한 상태다(`user_unassigned.png` y=505, x=1787 이
           단일 #161A2C). 소비처 109곳(전체 버튼의 44%)이 이 variant 다 — 호출부를 하나도
           안 건드리고 여기 한 줄로 닫는다.
           테두리는 **비텍스트 경계**라 WCAG 1.4.11 의 3:1 이 기준이다. `text.faint` 는 W4 가
           AA-large 전용으로 좁힌 잉크이고 네 면에서 3.67~4.95:1 이다 — 경계로 충분하고
           주 행동을 이기지 않는다. */
        ...(variant === "default" ? {
          borderColor: theme.palette.text.faint,
          "&:hover": { borderColor: theme.palette.text.secondary },
        } : null),
        /* 파괴적 동작도 **같은 하한을 받는다.** 위 한 줄을 `default` 에만 걸었더니
           `danger` 는 MUI 기본값 `alpha(error.main, 0.5)` 에 남았고, 그것이 판 위에서
           light 2.48:1 · dark 2.84:1 이 됐다 — 3:1 미만인 데다 바로 옆 중립 보조
           버튼(4.18:1)보다 약하다. **제품에서 가장 위험한 동작이 가장 흐린 경계를 갖는
           역전**이다(독립 검수 실측). 불투명 `error.main` 은 판 위 6.54:1(dark 7.72:1)이라
           경계로 충분하고, 채운 면은 여전히 주 행동만 갖는다 — 강도 순서는 그대로다.
           hover 색은 따로 주지 않는다. 이 팔레트의 `error` 는 `{main,bg,line,strong}` 만
           선언하고 `dark` 는 MUI 가 채워 주는데, 그 값을 실제로 재 보면 **다크에서 대비를
           깎는다**: light `rgb(125,26,21)` 은 흰 판 위에서 더 강해지지만 dark
           `rgb(178,96,89)` 은 판 위 7.72 → **3.95:1** 로 내려간다. hover 는 신호가 세지는
           자리이므로 방향이 반대다. `outlined` 의 기본 hover 배경으로 충분하다. */
        ...(variant === "danger" ? { borderColor: theme.palette.error.main } : null),
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
      <Box component="span" sx={{ display: "inline-flex", alignItems: "center", minWidth: 0 }}>
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
 * items: `{ key, label, onClick, tone, disabled, hint }[]` — `null`/`false` 는 걸러 낸다
 * (호출부가 권한 분기를 그대로 인라인으로 쓸 수 있게).
 */
export function OverflowMenu({ items, ariaLabel = "더 보기" }) {
  const list = (items || []).filter(Boolean);
  const [anchorEl, setAnchorEl] = React.useState(null);
  if (!list.length) return null;

  const close = () => setAnchorEl(null);
  return (
    <>
      <IconButton
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={anchorEl ? true : undefined}
        onClick={(e) => setAnchorEl(e.currentTarget)}
        size="small"
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
        slotProps={{ paper: { sx: { minWidth: "12rem" } } }}
      >
        {list.map((it, i) => {
          const danger = it.tone === "danger";
          /* 파괴적 항목은 앞의 항목들과 실선으로 가른다 — 마우스가 미끄러져 바로 위 항목을
             누르려다 삭제를 누르는 일을 막는 물리적 간격이다. */
          const firstDanger = danger && !(list[i - 1] && list[i - 1].tone === "danger");
          return (
            <MenuItem
              key={it.key || it.label || i}
              disabled={it.disabled}
              onClick={() => { close(); if (it.onClick) it.onClick(); }}
              sx={{
                fontSize: FONT_SIZE.bodySm,
                color: danger ? "error.strong" : "text.primary",
                borderTop: firstDanger && i > 0 ? 1 : 0,
                borderColor: "divider",
                mt: firstDanger && i > 0 ? 0.5 : 0,
                pt: firstDanger && i > 0 ? 1 : undefined,
              }}
            >
              {it.label}
            </MenuItem>
          );
        })}
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
export const SURFACE_EDGE_WIDTH = 3;

export const SURFACE_TONES = {
  none: {},
  plate: { fill: "background.plate", border: true, radius: RADIUS.md, holds: true },
  inset: { fill: "background.inset", radius: RADIUS.sm },
  sunken: { fill: "background.sunken", radius: RADIUS.sm },
  brandTint: { fill: "background.brandTint", radius: RADIUS.md, edge: "brand.core" },
  overlay: { fill: "background.plate", border: true, radius: RADIUS.lg, shadow: "overlay", floats: true },
  modal: { fill: "background.plate", border: true, radius: RADIUS.lg, shadow: "modal", floats: true },
};

/* 팔레트 경로("brand.core")를 실제 색으로. `borderInlineStartColor` 는 MUI 의 border 설정
   목록에 없어 팔레트 경로를 해석해 주지 않는다 — 그래서 여기서 직접 푼다. */
function paletteAt(theme, path) {
  return String(path).split(".").reduce((o, k) => (o == null ? o : o[k]), theme.palette);
}

/* 지금 이 자리가 판 안인가. 0 = 캔버스 위. */
const SurfaceDepthCtx = React.createContext(0);

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
        {children}
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
  return <SurfaceDepthCtx.Provider value={0}>{children}</SurfaceDepthCtx.Provider>;
}

/* 판 — `Surface tone="plate"` 에 판 안쪽 여백을 더한 것. 소비처 170여 곳이 이 이름을 쓴다.
 *
 * 안쪽 여백은 `density.js::CARD_PADDING`(24px)이다. W4 가 20 에서 올렸다 — 19px 구획
 * 제목이 20px 여백 안에서 테두리에 붙어 읽혔다.
 *
 * **판 안에서는 여백도 함께 사라진다.** 판정이 `none` 으로 내려갔는데 24px 여백만 남으면
 * 부모 판의 24px 와 겹쳐 48px 들여쓰기가 된다 — 없앤 테두리가 공백으로 되살아나는 셈이다. */
export function Card({ className, children, sx, ...rest }) {
  const nested = useSurfaceDepth() > 0;
  const base = nested ? null : { p: CARD_PADDING };
  const merged = typeof sx === "function"
    ? (theme) => ({ ...base, ...sx(theme) })
    : { ...base, ...sx };
  return (
    <Surface tone="plate" className={className} sx={merged} {...rest}>
      {children}
    </Surface>
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
export function TechDetail({ label = "기술 정보", children, sx }) {
  if (children == null || children === "" || children === false) return null;
  return (
    <Box
      component="details"
      className="k-techdetail"
      sx={{
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

export function Callout({ tone = "info", variant = "block", detail, detailLabel = "기술 정보", children }) {
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
   * 심각도를 색만으로 구분하지 않는다(WCAG 1.4.1) — 짧은 **텍스트 라벨**을 항상 붙인다.
   * 기호는 문화·스크린리더별로 읽히는 방식이 달라 이 앱은 처음부터 글자를 택했다.
   *
   * `detail` 은 긴 기술 설명을 접어 둔다(지시 35: "긴 기술 설명을 하나의 Alert 안에 모두
   * 넣지 않는다"). 표현은 `TechDetail` 이 맡는다 - 표·카드도 같은 접기를 쓴다.
   */
  const kind = tone === "ok" ? "success" : tone;
  const label = kind === "danger" ? "오류" : kind === "warn" ? "주의" : kind === "success" ? "완료" : "안내";
  const paletteKey = kind === "danger" ? "error" : kind === "warn" ? "warning" : kind === "success" ? "success" : "info";
  const quiet = kind === "info";

  const body = (
    <>
      <Box
        component="span"
        sx={{
          fontWeight: FONT_WEIGHT.semibold, mr: 1.25, whiteSpace: "nowrap",
          color: `${paletteKey}.strong`, fontSize: FONT_SIZE.bodySm,
        }}
      >
        {label}
      </Box>
      <Box component="span" className="k-callout-body">{children}</Box>
    </>
  );

  if (variant === "inline") {
    // 문장 흐름 안에 놓이는 한 줄. 상자도 바탕도 없다.
    return (
      <Typography className="k-callout" data-tone={kind} component="p" sx={{ fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }}>
        {body}
      </Typography>
    );
  }

  return (
    <Box
      className="k-callout"
      data-tone={kind}
      role={kind === "danger" ? "alert" : "note"}
      /* 앞머리 실선이 이 부품의 **유일한 형태 신호**다. 그런데 `borderInlineStart: 2` 로는
         한 픽셀도 그려지지 않았다 — MUI 의 border 스타일 함수가 논리 속성을 펴 주지 않아
         `border-inline-start: 2px` 가 나가고 `border-style` 초기값이 `none` 이기 때문이다.
         배포본 실측으로 확인한 결함이다(F-W2R-01). style·width·color 를 따로 적는다. */
      sx={(t) => ({
        display: "grid", gap: 0.5,
        px: 1.5, py: 1, borderRadius: `${RADIUS.sm}px`,
        borderInlineStartStyle: "solid",
        borderInlineStartWidth: "2px",
        borderInlineStartColor: t.palette[paletteKey].main,
        bgcolor: quiet ? "transparent" : `${paletteKey}.bg`,
        fontSize: FONT_SIZE.body,
        ...KO_WORD_BREAK,
      })}
    >
      <Box sx={{ minWidth: 0 }}>{body}</Box>
      <TechDetail label={detailLabel}>{detail}</TechDetail>
    </Box>
  );
}


/* 판독 한 줄에 쓰이는 두 상수. `rem` 숫자만 뽑아 계산에 쓴다 — 값의 정본은 theme.js 다. */
const REM_OF = (v) => Number.parseFloat(String(v));
const READOUT_LEAD = 1.15;   // 판독값 줄의 줄간격
const READOUT_RAIL = 2;      // 지금 목록을 거르고 있는 칸을 말하는 레일 두께

/** 지표 묶음 — **판이 아니라 판독 줄** (지시 2 · 77, PLAN «Surface 위계»).
 *
 * 예전에는 지표 하나당 카드 하나였다. 그 벽은 이미 없앴는데, 그 자리를 **판 하나**가
 * 대신 차지하고 있었다. PLAN 의 하드 금지 목록에 그것이 이름으로 적혀 있다 —
 * "판독 한 줄에 plate 금지(`MetricStrip` 의 `<Card>` 제거)". 독립 검수도 같은 자리를
 * 짚었다(F-W1R-16): `user_me.png` 에서 canvas -> plate -> inset 세 톤이 한 줄에 겹쳤다.
 *
 * W4 가 바꾼 것 넷.
 *
 * **① 판을 벗겼다.** 이제 캔버스 위에 판독값이 나란히 놓이고 실선이 그것들을 가른다.
 * 테두리가 없어졌으므로 줄은 **왼쪽으로 packing** 한다 — 예전 주석이 "칸을 상한으로 묶으면
 * 판의 오른쪽 절반이 테두리 안에서 빈다" 고 적어 둔 그 실측은 판이 있을 때만 성립한다.
 * 판이 없으면 남는 폭은 그냥 캔버스이고, 숫자 셋을 화면 폭에 억지로 늘리는 편이 나쁘다.
 *
 * **② 라벨 기준선을 공유한다.** 값 40px 과 19px 이 한 줄에 섞이면 각 칸이 자기 높이대로
 * 라벨을 내려 라벨 기준선이 24px 어긋났다(F-W1R-27 픽셀 실측). 이제 값 줄이 **줄 전체에서
 * 같은 최소 높이**를 갖고 값들이 그 아래쪽에 앉는다 — 라벨은 어느 칸에서나 같은 y 에서
 * 시작한다.
 *
 * **③ 판독 슬롯은 판단을 요구하는 값에만 준다.** `primary` 가 40px 을 차지하던 값이
 * 실제로는 «0 오늘 마감»·«0 처리 요청» 이었다 — 위계가 있는데 방향이 반대인 것은 위계가
 * 없는 것보다 나쁘다. 값이 없거나(`null`/`-`) **0 이면 판독 슬롯을 주지 않는다.** 0 은
 * 대개 "할 일이 없다" 이고 그건 화면을 지배할 판단이 아니다. 어떤 지표가 `primary` 여야
 * 하는가는 화면이 정하는 일이라 여기서 다 닫히지 않는다 — 남은 절반은 화면 Wave 로 넘긴다.
 *
 * **④ 전 항목이 비면 그 자리에 원인을 그린다** (PLAN «C1»). `-` 만 늘어선 판독 줄은
 * "없는 데이터를 위한 컨테이너" 다. 다만 PLAN 의 문장은 둘이 한 쌍이다 — "렌더하지 않고
 * **원인을 렌더한다**". 원인 없이 줄만 지우면 화면은 구획 정체성까지 잃는다(실측: 홈에서
 * Notion 매핑이 없을 때 «오늘 마감» 이라는 이름 자체가 사라진다 — "없다" 도 "모른다" 도
 * 아닌 침묵이 된다). 그래서 `emptyCause` 를 받는다: 주면 줄 대신 그것을 그리고, 안 주면
 * 줄을 그대로 두되 `data-metrics-empty="true"` 를 남겨 **몇 곳이 아직 원인을 안 넘기는지
 * 셀 수 있게** 한다. 배선은 원인 표현(`EmptyState`/Blocked)을 소유하는 Wave 의 몫이다.
 *
 * `delta` 는 변화량, `note` 는 그 숫자를 한정하는 각주다(구역 아래 공용 각주로 빼면 어느
 * 숫자를 한정하는지 다시 찾아야 한다 — VIS-09/VIS-27).
 * 심각도는 색만으로 전하지 않는다(WCAG 1.4.1) — `kind` 가 danger/warn 이면 짧은 텍스트
 * 태그를 함께 붙인다.
 */
export function MetricStrip({ items, ariaLabel, emptyCause, sx }) {
  const list = (items || []).filter(Boolean);
  const isEmptyValue = (v) => v == null || v === "" || v === "-";
  if (!list.length) return null;
  const allEmpty = list.every((it) => isEmptyValue(it.value));
  if (allEmpty && emptyCause) return emptyCause;

  /* 판독 슬롯은 묶음당 하나다. 값이 비었거나 0 이면 그 자격을 잃는다. */
  const earnsReadout = (it) =>
    !!it.primary && !isEmptyValue(it.value) && String(it.value).trim() !== "0";
  const readoutKey = list.findIndex(earnsReadout);
  const hasReadout = readoutKey >= 0;
  /* 값 줄의 공유 높이 — 이 줄에서 가장 큰 글자가 만드는 높이. 라벨이 같은 y 에서 시작한다. */
  const valueLead = REM_OF(hasReadout ? FONT_SIZE.readout : FONT_SIZE.title) * READOUT_LEAD;

  return (
    <Box
      className="k-metrics"
      role="group"
      aria-label={ariaLabel}
      /* 아직 원인을 안 넘기는 자리. 지우지 않고 **세는** 이유는 위 ④ 에 적었다. */
      data-metrics-empty={allEmpty ? "true" : undefined}
      sx={(t) => ({
        display: "flex", flexWrap: "wrap", alignItems: "stretch",
        /* 실선이 항목을 가른다. 각 항목이 앞머리 선을 갖고 첫 항목만 그것을 지운다 —
           줄바꿈이 일어나도 선이 어긋나지 않는다. 논리 속성은 MUI 가 펴 주지 않으므로
           style·width·color 를 따로 적는다(F-W2R-01). */
        "& > *:not(:first-of-type)": {
          borderInlineStartStyle: "solid",
          borderInlineStartWidth: "1px",
          borderInlineStartColor: t.palette.divider,
        },
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
    >
      {list.map((it, i) => {
        const sev = it.kind === "danger" ? "위험" : it.kind === "warn" ? "주의" : null;
        const tone = TONE_COLOR[it.kind];
        const clickable = !!it.onClick;
        const readout = i === readoutKey;
        return (
          <Box
            key={it.key || it.label || i}
            /* `k-readout` = "숫자 하나와 그 라벨·각주를 담은 칸". 칸은 자기 판을 갖지 않고
               줄 하나를 여럿이 나눠 쓴다. */
            className="k-readout"
            component={clickable ? "button" : "div"}
            type={clickable ? "button" : undefined}
            onClick={it.onClick}
            aria-pressed={clickable ? !!it.active : undefined}
            sx={(t) => ({
              /* 왼쪽으로 packing 한다. 늘어나지 않고 자기 내용 폭을 갖는다. */
              flex: "0 0 auto", minWidth: readout ? "9rem" : "6.5rem", maxWidth: "100%",
              textAlign: "left", font: "inherit", color: "inherit",
              border: 0, borderRadius: 0, bgcolor: "transparent",
              px: 2, py: 1.5, display: "grid", gap: 0.25, alignContent: "start",
              cursor: clickable ? "pointer" : "default",
              transition: `border-color ${MOTION.instant} ${MOTION.ease}`,
              "&:hover": clickable
                ? { borderBlockEndColor: it.active ? t.palette.brand.core : t.palette.text.faint }
                : undefined,
              /* **판을 벗기면 선택 신호가 뒤집힌다.** `background.inset` 은 판(#FFFFFF) 위에서는
                 어두운 함몰면이지만 캔버스(#EEF0F7) 위에서는 오히려 **더 밝고 대비가
                 1.055:1** 이다 — 눈에 보이지 않는 데다 의미가 반대다. 그래서 지금 어느 칸이
                 아래 목록을 거르고 있는지를 **면이 아니라 레일**이 말한다. 사이드바가 활성
                 위치를 3px 레일로 말하는 것과 같은 어휘다(W3, D-184) — 한 제품이 선택을
                 두 가지 말로 하지 않는다. 색은 Brand 잉크라 사용자 Accent 를 따르지 않는다.
                 비활성 칸도 같은 두께의 투명 레일을 가져 선택할 때 줄 높이가 튀지 않는다.
                 처음에는 이 주석을 적어 두고도 `bgcolor` 와 hover 면을 **지우지 않아**,
                 light 에서 1.055:1 짜리 보이지 않는 면이 유일한 hover 신호로 남아 있었다
                 (독립 검수 실측 — 주석은 레일이라 말하고 코드는 면을 칠하고 있었다).
                 hover 도 레일로 말한다: 가리키면 `text.faint`(경계 하한 3:1 을 넘는
                 잉크), 활성이면 Brand 로 유지된다. */
              borderBlockEndStyle: "solid",
              borderBlockEndWidth: `${READOUT_RAIL}px`,
              borderBlockEndColor: it.active ? t.palette.brand.core : "transparent",
            })}
          >
            {/* 값 줄의 높이를 줄 전체가 공유한다 — 그래서 라벨이 같은 y 에서 시작한다.
                `data-readout` 는 시험이 **자식 순서 대신** 이름으로 값/라벨을 짚게 한다 —
                순서로 짚으면 안쪽 배치를 조금만 바꿔도 시험이 깨지는 게 아니라 **조용히 빈
                문자열을 비교한다**(독립 실측이 `projects.test.jsx` 에서 그 위험을 지목했다). */}
            <Box data-readout="value" sx={{ minHeight: `${valueLead}rem`, display: "flex", alignItems: "flex-end", minWidth: 0 }}>
              <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, minWidth: 0 }}>
                <Typography
                  component="div"
                  sx={{
                    fontSize: readout ? FONT_SIZE.readout : FONT_SIZE.title,
                    fontWeight: FONT_WEIGHT.semibold, lineHeight: READOUT_LEAD, ...NUMERIC,
                  }}
                  color={tone && tone !== "default" ? `${tone}.strong` : "text.primary"}
                >
                  {it.value == null ? "-" : it.value}
                </Typography>
                {it.delta ? (
                  <Typography
                    component="span"
                    sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", whiteSpace: "nowrap", ...NUMERIC }}
                  >
                    {it.delta}
                  </Typography>
                ) : null}
              </Box>
            </Box>
            <Box data-readout="label" sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0 }}>
              <Typography component="div" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}>
                {it.label}
              </Typography>
              {sev ? (
                <Box
                  component="span"
                  sx={{ fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold, color: `${tone}.strong`, whiteSpace: "nowrap", flexShrink: 0 }}
                >
                  {sev}
                </Box>
              ) : null}
            </Box>
            {/* 각주는 세 번째 잉크 단계가 아니다 — 크기와 자리로 종속을 말한다.
                `text.faint` 는 본문 크기 글자에서 `text.secondary` 와 눈으로 구분되지
                않는다(대비 1.10:1, F-W1R-03). 같은 잉크에 caption 크기를 쓴다. */}
            {it.note ? (
              <Typography component="div" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", lineHeight: 1.4, ...KO_WORD_BREAK }}>
                {it.note}
              </Typography>
            ) : null}
          </Box>
        );
      })}
    </Box>
  );
}

/* 속성 줄 — 상세 화면 맨 위의 전폭 메타 (지시 7).
 *
 * `MetricStrip` 과 판 모양은 같지만 **읽는 순서가 반대**다: 지표는 숫자를 먼저 보고 그게
 * 무엇인지 확인하지만, 속성은 "마감이 언제지"처럼 **찾는 이름이 먼저** 있다. 그래서 라벨이
 * 위, 값이 아래다. 값도 지표처럼 크게 내지 않는다 — 여기서 큰 글자는 본문 몫이다.
 * 하나에 두 역할을 겸하게 하지 않고 따로 둔다(지시 57).
 *
 * 왜 위인가: 예전에는 속성이 오른쪽 레일 맨 위에 있었고 첨부는 본문 아래였다. 그래서
 * 본문을 읽다가 마감을 확인하려면 시선이 화면 오른쪽 끝까지 갔다가 돌아와야 했고, 첨부는
 * 본문이 길면 화면 밖으로 밀렸다. 속성은 훑는 정보라 한 줄로 위에 눕히는 편이 짧고,
 * 그 자리를 비워 준 레일은 본문과 나란히 읽는 것(첨부·댓글)이 갖는다.
 *
 * items: `{ key, label, value }[]` — `null`/`false` 는 걸러 낸다.
 */
export function MetaBar({ items, ariaLabel, sx }) {
  const list = (items || []).filter(Boolean);
  if (!list.length) return null;
  return (
    /* 판독 줄과 같은 판정을 받는다 — **속성 한 줄에 plate 금지.** 이 줄은 자기 생명주기도
       독립 스크롤도 없고 떠 있지도 않다. 체크리스트 ⑥ 이라 컨테이너가 없다.
       칸 사이 실선은 세 속성으로 적어야 실제로 그려진다(F-W2R-01).
       칸 폭의 의미 기반 재배분(프로젝트 2fr · 상태/마감 max-content)은 상세 Metadata 위계를
       소유하는 Wave 의 몫이다 — 여기서는 면과 실선만 고친다. */
    <Box
      className="k-metabar"
      role="group"
      aria-label={ariaLabel}
      sx={(t) => ({
        display: "flex", flexWrap: "wrap",
        "& > *:not(:first-of-type)": {
          borderInlineStartStyle: "solid",
          borderInlineStartWidth: "1px",
          borderInlineStartColor: t.palette.divider,
        },
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
    >
      {list.map((it, i) => (
        <Box
          key={it.key || it.label || i}
          className="k-metacell"
          sx={{ flex: "1 1 9rem", maxWidth: "20rem", minWidth: 0, px: 2, py: 1.25, display: "grid", gap: 0.25, alignContent: "start" }}
        >
          <Typography component="div" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
            {it.label}
          </Typography>
          <Box sx={{ fontSize: FONT_SIZE.body, color: "text.primary", minWidth: 0, ...KO_WORD_BREAK }}>
            {it.value == null || it.value === "" ? "-" : it.value}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

/* 로딩 자리표시자 — **들어올 것의 모양**을 한다 (지시 20).
 *
 * 예전에는 어느 화면에서나 회색 줄 N개였다. 표가 들어올 자리에도, 지표 줄이 들어올 자리에도
 * 같은 줄무늬가 그려지니 화면이 무엇을 준비 중인지 알 수 없었고, 실제 내용이 도착하는 순간
 * 배치가 통째로 튀었다(자리표시자가 자리를 안 잡아 준다는 뜻이다).
 *
 * 모양은 셋이다. 넷째(버튼)는 `Button` 의 `loading` 이 이미 맡는다 - 버튼 자리에 회색 알약을
 * 그리면 그 버튼이 사라진 것처럼 보인다.
 *
 *   `section` (기본) 구역 안 본문. 예전 동작 그대로 - `lines` 로 줄 수를 준다.
 *   `page`          화면 전체. 제목 줄 + 판독값 줄 + 본문 판. 셸이 이미 그린 자리를 흉내 낸다.
 *   `table`         표. 머리행 + 행들. `cols` 만큼 칸을 나눠 열 리듬까지 맞춘다.
 *
 * 스켈레톤 자체는 장식(aria-hidden)이라 스크린리더엔 침묵이다 - 별도 live 노드로 낭독한다.
 */
export function Skeleton({ kind = "section", lines = 3, rows = 5, cols = 4 }) {
  const live = <span className="sr-only" aria-live="polite">불러오는 중…</span>;

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
export function EmptyState({
  icon = null, title = "표시할 항목이 없습니다", help, situation, prerequisite,
  steps, expected, action, relatedLink, art, size, layout = "region",
}) {
  /* `layout` — **이 빈 상태가 무엇을 대신하는가** (PLAN «C1»).
   *
   *   page    화면 전체가 비었다. 남은 높이 안에서 세로 가운데에 선다 — 판·차트·Pager 를
   *           언마운트한 뒤 남는 큰 공백에 내용이 위쪽에 붙어 매달리지 않게 한다.
   *   region  구획 하나가 비었다(기본). 지금까지의 동작 그대로다.
   *   inline  팝오버·모달 하위목록처럼 폭도 높이도 좁은 자리. `size="compact"` 와 같은 뜻이다.
   *
   * 크기(`size`)와 자리(`layout`)를 따로 두는 이유: 좁은 팝오버 안의 빈 상태와 4K 전면의
   * 빈 상태는 **글자 크기**가 아니라 **놓이는 방식**이 다르다. 한 prop 에 둘을 겹치면
   * "작게" 와 "가운데" 를 따로 고를 수 없다. */
  const compact = size === "compact" || layout === "inline";
  const stepList = Array.isArray(steps) ? steps.filter((s) => s != null && s !== "") : null;
  const artSrc = !compact && art && ART[art] ? ART[art] : null;
  const detail = [prerequisite, stepList && stepList.length ? stepList : null, expected].some(Boolean);
  const bodySx = { maxWidth: "56ch", fontSize: compact ? FONT_SIZE.bodySm : FONT_SIZE.body, ...KO_WORD_BREAK };

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
      sx={{
        display: "flex", alignItems: "flex-start", gap: compact ? 1.5 : 2.5,
        py: compact ? 2 : 3.5, px: compact ? 1.5 : 2,
        /* page — 남은 높이를 실제로 차지하고 그 안에서 가운데에 선다. `minHeight` 는
           본문 열의 남은 높이를 겨냥한 값이다(셸이 상단바 높이를 이미 뺐다). */
        ...(layout === "page"
          ? { minHeight: "min(28rem, 55vh)", alignItems: "center", justifyContent: "flex-start" }
          : null),
      }}
      data-empty-layout={layout}
    >
      {artSrc ? (
        <Box
          component="img" src={artSrc} alt="" aria-hidden="true" loading="lazy" decoding="async"
          sx={{
            display: { xs: "none", sm: "block" }, flexShrink: 0,
            width: { sm: 72, xxl: 88, uhd: 112 }, height: "auto",
          }}
        />
      ) : icon ? (
        <Box aria-hidden="true" sx={{ flexShrink: 0, fontSize: compact ? FONT_SIZE.pageTitle : FONT_SIZE.readout, color: "text.faint", lineHeight: 1 }}>{icon}</Box>
      ) : null}

      <Box sx={{ display: "grid", gap: compact ? 0.5 : 0.75, minWidth: 0 }}>
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
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", mt: 0.25 }}>
            {action}
            {relatedLink && relatedLink.href ? (
              <Link href={relatedLink.href} underline="hover" sx={{ fontSize: compact ? FONT_SIZE.bodySm : FONT_SIZE.body }}>
                {relatedLink.label || "관련 화면으로"}
              </Link>
            ) : null}
          </Box>
        ) : null}

        {/* 준비물·절차·기대 결과는 보조다. 실선 하나로 아래에 붙인다(상자를 만들지 않는다). */}
        {detail ? (
          <Box sx={{ mt: 0.5, pt: 1, borderTop: 1, borderColor: "divider", display: "grid", gap: 0.5 }}>
            {prerequisite ? (
              <Typography color="text.secondary" sx={{ ...bodySx, fontSize: FONT_SIZE.bodySm }}>
                <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, mr: 1 }}>필요한 것</Box>{prerequisite}
              </Typography>
            ) : null}
            {stepList && stepList.length ? (
              <Box
                component="ol"
                sx={{ m: 0, pl: 2.5, color: "text.secondary", fontSize: FONT_SIZE.bodySm, display: "grid", gap: 0.25, maxWidth: "56ch", ...KO_WORD_BREAK }}
              >
                {stepList.map((s, i) => <li key={i}>{s}</li>)}
              </Box>
            ) : null}
            {expected ? (
              <Typography color="text.secondary" sx={{ ...bodySx, fontSize: FONT_SIZE.bodySm }}>
                <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, mr: 1 }}>기대 결과</Box>{expected}
              </Typography>
            ) : null}
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}

/* size="compact" — EmptyState와 같은 이유(DS-15): 팝오버·모달 하위목록처럼 폭이 좁은 맥락에서
 * 일러스트를 빼고 여백·글자를 줄인다. 예전엔 이 크기 차이를 소비 측 CSS(global.css 등)가
 * `.noti-pop-error .k-empty { padding:... }` 식으로 소유권 밖에서 되짚어 맞췄다 — 컴포넌트가
 * 직접 size를 받으면 그 특이도 전쟁 CSS가 필요 없어진다. */
export function ErrorState({ error, onRetry, size }) {
  const compact = size === "compact";
  const msg = (error && error.message) || "문제가 발생했습니다.";
  const status = error && error.status;
  const code = error && error.body && error.body.error && error.body.error.code;
  const kind = error && error.kind;
  const requestId = (error && error.requestId) || null;
  const isAuth = status === 401;
  const isForbidden = status === 403;
  const isGone = status === 404;
  const isOffline = kind === "network";
  // password_change_required는 403이지만 '권한 부족'이 아니라 '본인이 비번을 안 바꿔서' 막힌
  // 것이다 — 일반 권한부족 문구로 뭉개면 정반대로 오해하게 만든다.
  const isPwChange = isForbidden && code === "password_change_required";
  // 401/403/404는 재시도해도 같은 실패가 반복된다 — '다시 시도'는 일시적 오류에만 준다.
  const noRetry = isAuth || isForbidden || isGone;
  const title = isAuth ? "로그인이 필요합니다"
    : isPwChange ? "비밀번호 변경이 필요합니다"
    : isForbidden ? "권한이 없습니다"
    : isGone ? "찾을 수 없습니다"
    : isOffline ? "서버에 연결하지 못했습니다"
    : "불러오지 못했습니다";
  const help = isPwChange ? msg
    : isForbidden ? "이 항목에 접근할 권한이 없습니다. 관리자에게 문의하세요."
    : isGone ? "요청한 항목을 찾을 수 없습니다. 이미 삭제되었거나 이동했을 수 있습니다."
    : msg;
  // 상태마다 다른 그림을 준다 — 자산 12종이 있는데 한 곳도 연결돼 있지 않았다.
  const art = isAuth ? "sessionExpired"
    : isForbidden ? "noPermission"
    : isGone ? "notFound"
    : isOffline ? "offline"
    : "serverError";
  const artSrc = ART[art];
  // role="alert"로 오류 전환을 즉시 낭독한다. 제목은 heading으로.
  return (
    // VIS-50/VIS-52와 같은 이유(EmptyState 주석 참고) — ErrorState도 같은 삽화 자산과
    // 여백 규칙을 공유하므로 같은 값으로 맞춘다.
    <Box className="k-empty" role="alert" sx={{ display: "grid", justifyItems: "center", textAlign: "center", gap: compact ? 0.75 : 1.5, py: compact ? 2 : { xs: 6, uhd: 14 }, px: compact ? 1.5 : 3 }}>
      {!compact ? (
        <Box
          component="img" src={artSrc} alt="" aria-hidden="true" loading="lazy" decoding="async"
          sx={{ display: { xs: "none", sm: "block" }, width: { sm: 160, xxl: 200, uhd: 320 }, height: "auto" }}
        />
      ) : null}
      <Typography role="heading" aria-level={2} sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: compact ? FONT_SIZE.body : FONT_SIZE.sectionTitle }}>{title}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "60ch", fontSize: compact ? FONT_SIZE.bodySm : undefined }}>{help}</Typography>
      <Box sx={{ mt: compact ? 0.5 : 1 }}>
        {isAuth
          /* 되돌아올 곳을 실어 보낸다 — 재로그인 뒤 보던 화면으로 돌아온다(지시 19). */
          ? <MuiButton variant="contained" size={compact ? "small" : "medium"} href={loginUrl()}>로그인 화면으로</MuiButton>
          // "홈으로"(#/)는 이 SPA 안이라 다시 같은 403을 부른다 — 실제 페이지 이동이 필요하다.
          : isPwChange ? <MuiButton variant="contained" size={compact ? "small" : "medium"} href="/change-password">비밀번호 변경하기</MuiButton>
          // 403/404는 재시도해도 소용없지만 아무 동작도 없으면 막다른 길이다.
          : (isForbidden || isGone) ? <MuiButton variant="contained" size={compact ? "small" : "medium"} href="#/">홈으로</MuiButton>
          : (!noRetry && onRetry ? <Button variant="primary" onClick={onRetry}>다시 시도</Button> : null)}
      </Box>
      {/* 문의 번호 (Z8). 서버는 요청마다 id 를 만들어 오류 봉투와 `X-Request-ID` 에 실어
          보내고 감사 로그도 그 값을 저장하는데, 화면이 한 번도 보여 주지 않아 **사용자가
          불러 줄 수가 없었다.** 새벽 3시에 "화면이 안 나와요" 를 받으면 경로와 상태 코드밖에
          단서가 없었다. 로그인·권한 문제처럼 원인이 뻔한 것에는 붙이지 않는다 — 번호를
          아무 데나 붙이면 아무도 안 읽는다. compact에선 이미 좁은 공간이라 더 뺀다. */}
      {requestId && !isAuth && !isForbidden && !isGone && !compact ? (
        <Typography
          variant="body2" color="text.disabled"
          sx={{ fontSize: FONT_SIZE.caption, userSelect: "all", mt: 0.5 }}
        >
          문의 번호 {requestId}
        </Typography>
      ) : null}
    </Box>
  );
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
/* 본문 셀은 열 폭을 안 정해 주면(`c.minWidth` 없음) `overflowWrap:"anywhere"`가 좁은
 * 컨테이너에서 열 폭을 '한 글자'까지 줄여, 설명 같은 긴 텍스트가 세로로 한 자씩 흐른다
 * (관리자 registry 표 28개 전부가 이 상태였다, DS-06). SettingsMain.jsx가 이미 겪어 실측
 * 확인한 버그와 같은 것이다 — 개별 화면마다 minWidth를 채우는 대신 표 자신이 바닥값을 둔다. */
const DEFAULT_COL_MIN_WIDTH = "4.5rem";

/* PA-RC-0029/0037: 행을 식별하는 열(이메일·항목명 등)은 폭이 부족해질 때 가장 먼저
 * 보호돼야 하는 열이다 — `c.identifier:true`만 붙이면 화면마다 정확한 px를 직접 재지
 * 않아도 이 바닥값이 붙는다(필요폭이 다르면 `c.minWidth`로 그대로 덮어쓸 수 있다,
 * SettingsMain.jsx의 `항목명`처럼). 나머지 열은 `DEFAULT_COL_MIN_WIDTH`를 그대로 쓴다 —
 * 우선순위를 지정하지 않은 화면은 렌더 결과가 바뀌지 않는다(REGRESSION 없음). */
const IDENTIFIER_COL_MIN_WIDTH = "12.5rem";
function colMinWidth(c) {
  return c.minWidth ?? (c.identifier ? IDENTIFIER_COL_MIN_WIDTH : DEFAULT_COL_MIN_WIDTH);
}

/* 셀 렌더러에 넘기는 두 번째 인자(ctx)는 **그 행에 대한 표의 지식**이다. 지금은 rowName
 * 하나뿐이다: 선택 체크박스처럼 셀 안에 있으면서 '자기 행이 무엇인지' 알아야 하는 컨트롤이
 * 쓴다. 화면이 열 정의마다 라벨을 손으로 적지 않게 하려면 표가 알려 주는 수밖에 없다
 * (열은 자기 옆 열들을 모른다). 기존 render 들은 인자를 하나만 받으므로 그대로 동작한다. */
function cellValue(c, row, ctx) {
  if (c.render) return c.render(row, ctx);
  const v = row[c.key];
  return v == null || v === "" ? "-" : String(v);
}

/* 정렬은 **지금 화면에 있는 행 전부**를 대상으로만 제공한다 (지시 10).
 *
 * 서버가 페이지를 자르는 목록에서 보이는 20건만 정렬해 놓고 화살표를 그리면, 사용자는
 * "가장 오래된 것"을 봤다고 믿는다. 실제로는 그 페이지 안에서 가장 오래된 것이다. 이 저장소는
 * 같은 함정을 `clientFilter` 에서 이미 겪었고 그때는 "이 필터는 지금 보고 있는 페이지에만
 * 적용됩니다"라는 경고로 막았다 — 정렬은 그 경고로도 못 막는다(필터는 결과가 줄어드는 것이
 * 눈에 보이지만 정렬은 틀린 순서가 맞아 보인다). 그래서 호출부가 `onSort` 를 줄지 말지로
 * 정한다: 전체를 들고 있는 화면만 준다.
 *
 * `sort` = `{ key, dir }`(dir: "asc" | "desc"), `onSort(key)` 는 호출부가 방향을 뒤집는다.
 */
export function DataTable({ columns, rows, rowKey, onRow, empty, fixed, ellipsis, stickyHeader, loading, sort, onSort }) {
  // 방어: 비정상 입력이 와도 렌더 중 throw하지 않고 빈-목록 안내로 폴백한다.
  // 공용 표라 한 화면의 실수나 API shape 변화가 전역 크래시로 번지지 않게 한다.
  const baseCols = Array.isArray(columns) ? columns : [];
  const cols = baseCols;
  const safeRows = Array.isArray(rows) ? rows : [];
  const keyOf = typeof rowKey === "function" ? rowKey : (_, i) => i;
  const narrow = useMediaQuery(TABLE_CARD_QUERY);
  // RESP-01: 900~1200 구간(사이드바 아직 안 접힘)에서 열이 많은 표만 겪는 문제라 카드 뷰는
  // 안 건드린다 — 폭 제약이 없는 카드에서 열을 빼면 정보만 준다.
  const compact = useMediaQuery(TABLE_COMPACT_QUERY);
  const wideCols = compact ? baseCols.filter((c) => !c.hideNarrow) : baseCols;
  // PA-RC-0037 acceptance (4): 열이 접힌 경우 그 사실을 화면에 알린다 — 예전엔 hideNarrow
  // 열이 900~1200 구간에서 아무 표시 없이 사라졌다(Users.jsx가 이미 그렇게 2열 쓰고 있었다).
  // 값 자체는 행을 열면(onRow) 상세에서 그대로 보인다 — 여기서는 "더 있다"는 사실만 알린다.
  const hiddenCols = compact ? baseCols.filter((c) => c.hideNarrow) : [];

  /* 로딩 모양을 표가 스스로 안다 (지시 20). 호출부가 각자 `<Skeleton lines={6} />` 을 두면
     열 수도 행 높이도 표와 다르고, 무엇보다 **빈 목록과 아직 안 온 목록이 같아 보인다** -
     "없다"와 "아직 모른다"는 다른 사실이다. */
  if (loading) return <Skeleton kind="table" cols={wideCols.length || baseCols.length} />;

  if (safeRows.length === 0) {
    return (
      <Typography color="text.secondary" sx={{ py: 5, textAlign: "center" }}>
        {empty || "표시할 항목이 없습니다."}
      </Typography>
    );
  }

  /* 좁은 화면에서는 표를 카드 목록으로 바꾼다. 가로 스크롤되는 표는 손가락으로 훑기 어렵고,
   * 열 이름이 화면 밖으로 나가면 어떤 값인지 알 수 없다. 카드에서는 라벨을 값 옆에 붙인다. */
  if (narrow) {
    return (
      <Stack gap={1.5}>
        {safeRows.map((row, i) => {
          const ctx = { rowName: rowNameOf(baseCols, row) };
          return (
            <Paper
              key={keyOf(row, i)}
              variant="outlined"
              onClick={onRow ? (e) => { if (e.target.closest("a,button")) return; onRow(row); } : undefined}
              onKeyDown={onRow ? (e) => { if (e.target.closest("a,button")) return; if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRow(row); } } : undefined}
              tabIndex={onRow ? 0 : undefined}
              aria-label={onRow ? rowOpenLabel(baseCols, row) : undefined}
              sx={{ p: 2, display: "grid", gap: 0.75, cursor: onRow ? "pointer" : "default" }}
            >
              {cols.map((c) => (
                <Box key={c.key} sx={{ display: "grid", gridTemplateColumns: "7rem minmax(0,1fr)", gap: 1, alignItems: "start" }}>
                  <Typography variant="caption" color="text.secondary">{c.label}</Typography>
                  {/* `overflowWrap:anywhere` 만 걸면 한글이 음절 단위로 끊긴다 - 영문에서는
                      안 생기는 일이라 눈에 잘 안 띈다. 단어는 지키고 긴 토큰만 끊는다. */}
                  <Box sx={{ minWidth: 0, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}>{cellValue(c, row, ctx)}</Box>
                </Box>
              ))}
            </Paper>
          );
        })}
      </Stack>
    );
  }

  return (
    <>
      {hiddenCols.length ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", px: 2, pt: 1.5 }}>
          화면 폭이 좁아 {hiddenCols.map((c) => c.label).join(", ")} 열을 숨겼습니다. 행을 열면 전체 정보를 볼 수 있습니다.
        </Typography>
      ) : null}
      <TableContainer>
      {/* 표 리듬 (지시 10) — 세로 괘선이 없고, 행 사이는 실선 하나로만 나눈다. 마지막 행의
          아래 선은 지운다(판의 테두리와 겹쳐 두 줄로 보인다). 행 추적은 괘선이 아니라
          **hover 면**과 머리행의 굵은 선이 만든다 — 엑셀 표가 아니라 계기판 판독부다. */}
      <Table
        size="small"
        stickyHeader={stickyHeader}
        sx={{
          tableLayout: fixed ? "fixed" : "auto",
          "& td, & th": { borderInline: 0 },
          "& tbody tr:last-of-type td": { borderBottom: 0 },
          "& tbody tr": { transition: `background-color ${MOTION.instant} ${MOTION.ease}` },
          "& tbody tr.MuiTableRow-hover:hover": { bgcolor: "background.inset" },
        }}
      >
        <TableHead>
          <TableRow>
            {wideCols.map((c) => {
              const sortable = !!(c.sortable && onSort);
              const active = sortable && sort && sort.key === c.key;
              const dir = active ? sort.dir : null;
              return (
              <TableCell
                key={c.key}
                scope="col"
                align={c.align || "left"}
                /* 스크린리더가 "정렬 안 됨 / 오름차순 / 내림차순"을 읽는다. 화살표만 그리면
                   그 정보는 눈으로만 전달된다(WCAG 1.4.1 과 같은 이유). */
                aria-sort={sortable ? (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none") : undefined}
                /* minWidth: 이 열이 절대 그 아래로 줄지 않는 폭. 없으면 좁은 컨테이너에서
                   `overflowWrap: anywhere` 때문에 열의 최소 폭이 '한 글자'가 되어, 제목이
                   세로로 무너진다(24px 폭에 11줄 — QA의 vertical_text_collapse 검사가 잡는
                   상태). 폭이 모자라면 TableContainer가 스스로 가로 스크롤하므로 페이지에
                   가로 스크롤이 생기지는 않는다.
                   본문 셀엔 이미 이 바닥값이 있었는데(DS-06) 머리글 셀엔 없었다 — 폭 906~1366px
                   구간에서 열이 많은 표(`/users` 9열 등)가 실측으로 무너진 게(VIS-73/RESP-01/
                   RESP-02) 바로 이 비대칭이었다. 같은 바닥값을 여기도 준다.
                   VIS-58: stickyHeader일 때 MUI가 자동으로 position:sticky를 붙이지만
                   불투명 배경은 안 준다 — 스크롤되는 본문 셀이 헤더 뒤로 비쳐 보인다.
                   이 표는 항상 Card(background.paper) 안에 있으므로 그 색을 명시한다. */
                sx={{
                  width: c.width, minWidth: colMinWidth(c), whiteSpace: "nowrap",
                  ...(stickyHeader ? { bgcolor: "background.paper" } : null),
                }}
              >
                {sortable ? (
                  <Box
                    component="button"
                    type="button"
                    onClick={() => onSort(c.key)}
                    sx={{
                      font: "inherit", color: "inherit", border: 0, background: "none", p: 0,
                      display: "inline-flex", alignItems: "center", gap: 0.5, cursor: "pointer",
                      /* 머리글 칸은 `whiteSpace: nowrap` 인데, 그 안에 flex 상자를 넣으면 글자
                         항목이 상자 폭에 맞춰 줄어들 수 있다 — 4K 실측에서 "마지막 확인"이
                         81.5px 안에서 세 줄(줄당 2.3자)로 무너졌다(QA 의 vertical_text_collapse).
                         상자 자신에게도 같은 규칙을 준다. */
                      whiteSpace: "nowrap",
                      "&:hover": { color: "text.primary" },
                      "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
                    }}
                  >
                    {c.label}
                    {/* 방향 표시는 지금 정렬된 열에만 그린다 — 모든 열에 회색 화살표를 달면
                        머리행이 화살표 줄이 되고 정작 어느 열이 정렬 중인지 안 보인다. */}
                    <Box component="span" aria-hidden="true" sx={{ fontSize: FONT_SIZE.caption, opacity: active ? 1 : 0.35 }}>
                      {dir === "desc" ? "\u2193" : dir === "asc" ? "\u2191" : "\u2195"}
                    </Box>
                  </Box>
                ) : c.label}
              </TableCell>
              );
            })}
          </TableRow>
        </TableHead>
        <TableBody>
          {safeRows.map((row, i) => {
            // 행마다 한 번만 구한다 — 셀마다 다시 구하면 열 수만큼 같은 계산을 반복한다.
            const ctx = { rowName: rowNameOf(baseCols, row) };
            return (
              /* 셀 안의 링크/버튼 클릭이 행 클릭(상세 열기)으로 번지지 않게 막는다 —
                 문서 '발행 링크'를 누르면 새 탭이 열리면서 상세까지 같이 열리던 이중 동작.
                 같은 이유로 키보드 Enter/Space도 셀 안의 실제 버튼·링크에서 눌렀으면
                 행 전체의 onRow를 다시 부르지 않는다(그 버튼 자신의 키보드 활성화가
                 이미 처리한다). PA-RC-0023: role="button"은 일부러 안 준다 — 이 행 안에
                 재시도/취소 같은 진짜 버튼이 함께 있는 표가 있어(registry 행 액션),
                 role=button 위에 포커스 가능한 자손을 두는 것은 WAI-ARIA 금지다
                 (StatusTile의 같은 이유 참고, adminKit.jsx). tabIndex + aria-label +
                 Enter 처리만으로 키보드 도달을 준다. */
              <TableRow
                key={keyOf(row, i)}
                hover={!!onRow}
                onClick={onRow ? (e) => { if (e.target.closest("a,button")) return; onRow(row); } : undefined}
                onKeyDown={onRow ? (e) => { if (e.target.closest("a,button")) return; if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRow(row); } } : undefined}
                tabIndex={onRow ? 0 : undefined}
                aria-label={onRow ? rowOpenLabel(baseCols, row) : undefined}
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
                  const truncate = ellipsis || !c.render;
                  const raw = !c.render ? cellValue(c, row, ctx) : null;
                  return (
                    <TableCell
                      key={c.key}
                      align={c.align || "left"}
                      title={truncate && raw && raw !== "-" ? raw : undefined}
                      sx={truncate
                        ? { whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 0,
                           minWidth: colMinWidth(c) }
                        : { ...(c.nowrap ? { overflowWrap: "normal", whiteSpace: "nowrap" } : KO_WORD_BREAK),
                           minWidth: colMinWidth(c) }}
                    >
                      {raw != null ? raw : cellValue(c, row, ctx)}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      </TableContainer>
    </>
  );
}

/* 공통 모달 — 모든 생성/수정/확인/상세가 중앙 모달을 쓴다.
 * 예전에는 포커스 트랩·Esc 스택·배경 스크롤 잠금을 직접 구현했다. MUI Dialog가 셋 다
 * 정확히 처리하므로(중첩 모달 포함) 그 코드는 지웠다 — 직접 구현이 남아 있으면 MUI와
 * 이중으로 걸려 Esc 한 번에 두 개가 닫히는 예전 버그가 다시 난다.
 * size: sm|md|lg. 모바일에서는 전체 화면. */
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
 */
const MODAL_MAX_WIDTH = { sm: "30rem", md: "45rem", lg: "62rem" };

export function ModalHeader({ title, onClose, titleId }) {
  return (
    <MuiDialogTitle
      id={titleId}
      sx={{ display: "flex", alignItems: "center", gap: 2, pr: 1.5, fontSize: FONT_SIZE.sectionTitle, fontWeight: FONT_WEIGHT.extrabold }}
    >
      <Box component="span" sx={{ flex: 1, minWidth: 0 }}>{title}</Box>
      <IconButton onClick={onClose} aria-label="닫기" size="small"><CloseRoundedIcon fontSize="small" /></IconButton>
    </MuiDialogTitle>
  );
}
export function ModalBody({ children }) {
  return <MuiDialogContent dividers sx={{ minWidth: 0 }}>{children}</MuiDialogContent>;
}
/* 모달 모서리 반지름 — 사용자 지적 P4("전체적으로 눌렀을 때 라운드가 너무 크다").
 *
 * 예전 값은 `borderRadius: 2.5` 였는데, MUI 는 이 숫자에 `shape.borderRadius`(14)를 곱하므로
 * 실제로는 **35px** 이었다. 기준 목업의 카드는 `--radius-lg: 18px` 이고 모달도 같은 계열이다.
 * 하네스에 클릭을 붙여 실제로 연 모달 47개가 **예외 없이 35px** 이었다.
 *
 * 절댓값으로 적는 이유: 배수로 두면 `shape.borderRadius` 를 나중에 건드리는 순간 다시
 * 틀어진다. 이 값은 "카드와 같은 반지름" 이라는 뜻이지 "shape 의 2.5배" 가 아니다.
 * PA-RC-0001: RADIUS.lg가 바로 그 "카드와 같은 반지름"이므로 그 값을 그대로 쓴다(여전히
 * 절댓값 — RADIUS.lg 자체가 shape.borderRadius에서 유도되지 않는다). */
const MODAL_RADIUS = `${RADIUS.lg}px`;

/* 표준 하단 작업줄 — 취소(고스트), 기본 작업(오른쪽). 전 화면 동일 위치·크기. */
export function ModalFooter({ onCancel, onSubmit, submitLabel = "저장", cancelLabel = "취소", busy, submitVariant = "primary" }) {
  return (
    <MuiDialogActions className="k-footer-row" sx={{ px: 3, py: 2, gap: 1 }}>
      {onCancel ? <Button variant="ghost" onClick={onCancel} disabled={busy}>{cancelLabel}</Button> : null}
      {onSubmit ? <Button variant={submitVariant} onClick={onSubmit} disabled={busy} loading={busy}>{submitLabel}</Button> : null}
    </MuiDialogActions>
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
  const wrapped =
    React.isValidElement(children) &&
    (children.type === ModalFooter || children.type === MuiDialogActions);
  if (wrapped) return children;
  return (
    <MuiDialogActions className="k-footer-row" sx={{ px: 3, py: 2, gap: 1 }}>
      {children}
    </MuiDialogActions>
  );
}

/* `dirty` 를 주면 **닫기 전에 확인**한다 (E11).
 *
 * `FormModal` 은 값 스냅샷으로 더티를 스스로 판정하지만, 이 저수준 `Modal` 은 내용을 모른다.
 * 그래서 부르는 쪽이 알려 준다. 안 주면 예전과 똑같이 그냥 닫힌다 - 기존 호출부를 깨지 않는다.
 *
 * 이게 없어서 실제로 아팠던 자리: 퀴즈 방 만들기(최대 20문항)를 다 쓰고 Esc 나 바깥을 한 번
 * 누르면 **전부 사라졌다.** 되돌릴 방법도 없다. 확인 문구는 FormModal 과 같은 것을 쓴다 -
 * 같은 상황에 다른 말이 나오면 사용자는 다른 일이 일어난다고 읽는다. */
export function Modal({ open, onClose, title, size = "md", children, footer, dirty = false }) {
  const titleId = React.useId();
  const confirm = useConfirm();
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
      fullWidth
      aria-labelledby={titleId}
      /* 모바일에서는 전체 화면 — 좁은 화면에서 폼이 잘려 스크롤조차 안 되던 문제.
       *
       * `width` 를 지정하지 않는다(M7). 예전에는 `sm` 이상에서 `width:"auto"` 였는데, 그것이
       * 바로 위 `fullWidth` 를 **무력화**했다 — 폭이 내용 길이로 정해져 같은 성격의 모달이
       * 화면마다 다른 크기가 됐다(실측: 한 화면에서 폭 7~8가지, `+ 직책 추가` 286px vs
       * `+ 공지 추가` 1200px 로 4배 차이). 이제 `maxWidth`(sm/md/lg) 세 등급만 남는다 —
       * 크기를 고르는 일이 `size` prop 한 곳으로 모인다.
       *
       * xs 는 그대로 전체 화면이다(좁은 화면에서 등급 폭을 쓰면 좌우가 잘린다). */
      sx={{ "& .MuiDialog-paper": {
        m: { xs: 0, sm: 4 },
        width: { xs: "100%" },
        maxWidth: { xs: "100%", sm: MODAL_MAX_WIDTH[size] || MODAL_MAX_WIDTH.md },
        maxHeight: { xs: "100%", sm: "calc(100% - 4rem)" },
        height: { xs: "100%", sm: "auto" },
        borderRadius: { xs: 0, sm: MODAL_RADIUS },
      } }}
    >
      <SurfaceReset>
        <ModalHeader title={title} onClose={requestClose} titleId={titleId} />
        <ModalBody>{children}</ModalBody>
        {footer ? <ModalActions>{footer}</ModalActions> : null}
      </SurfaceReset>
    </MuiDialog>
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
function FieldLabel({ htmlFor, id, children, required }) {
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
  const toast = useToast();
  const handlePasteOverflowWarning = maxLength ? (e) => {
    const pasted = e.clipboardData ? e.clipboardData.getData("text") : "";
    if (!pasted) return;
    const el = e.target;
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const nextLength = el.value.length - (end - start) + pasted.length;
    if (nextLength > maxLength) {
      toast(`최대 ${maxLength}자까지만 저장됩니다. 붙여넣은 내용 중 일부가 잘렸습니다.`, "warn");
    }
  } : undefined;
  const charCount = (multiline && maxLength) ? `${(value || "").length}/${maxLength}자` : null;
  const staticHelp = charCount ? (f.help ? `${f.help} (${charCount})` : charCount) : (f.help || undefined);
  // PA-RC-0014: invalid면 도움말 대신 실제 오류 문구를 aria-describedby가 가리키는 자리에 둔다 —
  // 빨간 테두리(error)만으로는 스크린리더가 "무엇이 문제인지"를 읽을 수 없었다.
  const helpText = invalid && errorMessage ? errorMessage : staticHelp;
  const helpId = helpText ? id + "-helper-text" : undefined;

  if (f.type === "checkbox") {
    return (
      <Box className="k-field" sx={{ mb: 2.5 }}>
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

  // helperText의 id는 MUI가 `${id}-helper-text`로 만들고 입력의 aria-describedby에 직접
  // 걸어 준다. 여기서 id를 덮어쓰면 그 연결이 끊겨, 도움말이 시각적으로만 남고 스크린리더가
  // 읽지 않는다(예전 키트가 손으로 걸어 두던 동작이라 조용히 사라질 뻔했다 — kit.test.jsx가 잡음).
  const common = {
    id,
    fullWidth: true,
    size: "small",
    error: !!invalid,
    required,
    // `label` 은 안 넘긴다 — 라벨은 위의 `FieldLabel` 이 그린다(지시 17). MUI 에 넘기면
    // 떠 있는 라벨이 하나 더 생겨 같은 글자가 두 번 보인다.
    helperText: helpText,
    value: value != null ? value : "",
    onChange: (e) => onChange(e.target.value),
    sx: { mb: 0 },
  };

  if (f.type === "select") {
    return (
      <Box className="k-field" sx={{ mb: 2.5 }}>
      <FieldLabel id={id + "-label"} required={required}>{f.label}</FieldLabel>
      <TextField
        {...common}
        select
        /* MUI 는 `label` 이 함께 있을 때만 `labelId` 를 aria-labelledby 로 엮는다 —
           라벨을 위로 올린 뒤로는 직접 걸어 줘야 이름이 접근성 트리에 닿는다. */
        SelectProps={{ labelId: id + "-label" }}
      >
        {selNeedEmpty ? (
          <MenuItem value="" disabled={required}>
            {hasOptions ? "선택 안 함" : "선택할 항목이 없습니다"}
          </MenuItem>
        ) : null}
        {(f.options || []).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
      </TextField>
      </Box>
    );
  }

  return (
    <Box className="k-field" sx={{ mb: 2.5 }}>
    <FieldLabel htmlFor={id} required={required}>{f.label}</FieldLabel>
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
      inputProps={{
        ...(f.type === "email" ? { inputMode: "email", autoCapitalize: "none" } : null),
        ...(maxLength ? { maxLength } : null),
      }}
      /* JSON은 사람이 중첩 구조를 손으로 편집한다 — 가변폭 폰트로는 중괄호·들여쓰기가 안 맞는다. */
      InputProps={isJson ? { sx: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: FONT_SIZE.bodySm } } : undefined}
    />
    </Box>
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
    if (el) { try { el.scrollIntoView({ block: "center", behavior: prefersReducedMotion() ? "auto" : "smooth" }); el.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
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
  const shownFields = React.useMemo(
    () => (fields || []).filter((f) => (typeof f.showIf === "function" ? f.showIf(values) : true)),
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

  const fail = (name, message) => { setErrField(name); setErr(message); };

  async function submit() {
    setErr(""); setErrField(null);
    const body = {};
    for (const f of shownFields) {
      // 수정 화면에서 원래 값이 있던 항목을 비우면 키를 생략하지 않고 null로 보내 실제로 지운다.
      const hadValue = initial && initial[f.name] != null && String(initial[f.name]).trim() !== "";
      let val = values[f.name];
      if (f.type === "number") {
        if (val === "" || val == null) { if (f.required) { fail(f.name, f.label + "을(를) 입력하세요."); return; } if (hadValue) body[f.name] = null; continue; }
        val = Number(val); if (Number.isNaN(val)) { fail(f.name, f.label + ": 숫자를 입력하세요."); return; }
        body[f.name] = val; continue;
      }
      else if (f.type === "checkbox") { if (f.required && !val) { fail(f.name, (f.checkLabel || f.label) + "을(를) 선택해야 합니다."); return; } body[f.name] = !!val; continue; }
      else if (f.type === "json") {
        if (!val || !String(val).trim()) { if (f.required) { fail(f.name, f.label + "을(를) 입력하세요."); return; } if (hadValue) body[f.name] = null; continue; }
        let parsed;
        try { parsed = JSON.parse(val); } catch (e) { fail(f.name, f.label + ": JSON 형식이 올바르지 않습니다."); return; }
        // 일부 필드(예: 정책 content)는 백엔드가 JSON 객체만 허용한다 — 서버와 같은 문구로 먼저 막는다.
        if (f.jsonObject && (parsed === null || typeof parsed !== "object" || Array.isArray(parsed))) {
          fail(f.name, f.label + "은(는) JSON 객체여야 합니다."); return;
        }
        body[f.name] = parsed;
        continue;
      }
      else if (f.type === "select") {
        val = val == null ? "" : String(val);
        if (f.required && !val.trim()) {
          // 옵션 자체가 없으면 '선택하세요'는 헛도는 무한 루프다 — 원인이 다른 문구를 준다.
          if (!(f.options || []).length) { fail(f.name, f.label + ": 선택할 수 있는 항목이 없습니다. 다시 시도하거나 취소하세요."); return; }
          fail(f.name, f.label + "을(를) 선택하세요."); return;
        }
        body[f.name] = val === "" ? null : val; continue;
      }  // 빈 선택("없음")은 null로 보내 기존 값을 지운다.
      else {
        val = val == null ? "" : String(val);
        if (f.required && !val.trim()) { fail(f.name, f.label + "을(를) 입력하세요."); return; }
        // 사람이 적은 것은 KST 벽시계다 — 오프셋을 붙여 보내야 서버가 같은 순간으로 저장한다(F14).
        // 붙이지 않으면 서버가 규약대로 naive 를 UTC 로 읽어 9시간 밀린 채 저장된다.
        if (val !== "") body[f.name] = f.type === "datetime-local" ? kstLocalToApi(val) : val;
        else if (hadValue) body[f.name] = null;
      }
    }
    setBusy(true);
    try { await onSubmit(body); }
    catch (e) {
      // 세션 만료(401)는 여기서 재시도해도 항상 401이라, 일반 폼 오류 문구만 띄우면 사용자는
      // 자신이 방금 입력한 내용이 왜 저장되지 않는지 모른 채 이 모달 안에 막힌다.
      if (e && e.status === 401) {
        toast("로그인이 필요합니다. 로그인 화면으로 이동합니다.", "error");
        redirectToLogin({ delayMs: 1200 });
        return; // busy=true로 남겨 재제출을 막는다 — 곧 페이지가 이동한다.
      }
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
    setBusy(false);
  }

  /* 크기는 **열릴 때 한 번** 정한다 (R-12).
   * 예전에는 매 렌더마다 `shownFields.length` 로 다시 골랐다 — 조건부 필드가 있는 폼(사용자
   * 편집에서 역할을 바꾸면 필드가 늘어난다)에서 사용자가 select 하나를 건드리는 순간 모달이
   * 45rem -> 62rem 로 **열린 채 넓어졌다.** 크기는 이 창이 무엇인지에 대한 사실이지 지금 몇
   * 칸이 보이는가에 대한 사실이 아니다. */
  if (sizeAtOpen.current == null) sizeAtOpen.current = shownFields.length > 5 ? "lg" : "md";
  const sz = size || sizeAtOpen.current;
  const footer = <ModalFooter onCancel={requestClose} onSubmit={submit} submitLabel={submitLabel || "저장"} busy={busy} />;
  return (
    <Modal open={open} onClose={requestClose} title={title} size={sz} footer={footer}>
      {/* 필드를 <form>으로 감싸 Enter가 자연스럽게 제출되게 한다(textarea/json은 여러 줄 입력을
          위해 기본 Enter 동작 유지). */}
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {err ? <MuiAlert severity="error" className="k-form-err" sx={{ mb: 2.5 }} role="alert">{err}</MuiAlert> : null}
        {shownFields.map((f) => <FormField key={f.name} field={f} value={values[f.name]} invalid={errField === f.name}
          onChange={(val) => set(f.name, val)}
          errorMessage={errField === f.name ? err : undefined}
          maxLength={screenKey ? maxLengthFor(screenKey, formKind, f.name) : null} />)}
        {/* 화면에 보이지 않는 제출 버튼 — 실제 저장 버튼은 Dialog footer(별도 DOM 트리)에 있어
            이 <form> 안에 없다. type="submit"이 하나도 없으면 브라우저에 따라 단일 텍스트
            입력에서 Enter가 폼을 제출하지 않는다. */}
        <button type="submit" className="sr-only" tabIndex={-1} aria-hidden="true" />
      </form>
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
        footer={<DialogFooter onCancel={() => done(false)} onSubmit={() => done(true)}
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
  const push = React.useCallback((message, kind) => {
    const id = ++_toastSeq;
    const k = kind || "info";
    setToasts((t) => [...t, { id, message, kind: k }]);
    const ttl = k === "error" ? 8000 : 3500;
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ttl);
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
                sx={{ width: "100%" }}
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
 * spot: 섹션 일러스트 키(lib/assets.js의 SPOT).
 *
 * 일러스트는 **격자 항목이 아니라 배경 장식**이다(사용자 지시 §5: "페이지마다 클로비
 * 이미지를 크게 배치하지 말고, 페이지 오른쪽 상단 배경 영역에 투명도를 적용해 자연스럽게").
 * 예전에는 flex 항목이라 두 가지가 났다:
 *   1) 이미지에만 order:2 가 있고 actions 에는 없어서 **액션이 먼저** 왔다. 액션이 줄바꿈되면
 *      96~160px 그림이 제 줄로 밀려 본문 전체를 아래로 밀었다.
 *   2) 높이가 raw px 라 4K 루트 폰트 레버를 안 따라가 큰 화면에서 혼자 작았다.
 * 이제 흐름 밖(absolute)에 두고 투명도를 낮춘다 — 레이아웃을 밀지도, 클릭을 막지도 않는다.
 * 높이는 rem 이라 다른 글자·여백과 같이 커진다. */
export function PageHeader({ area, title, tab, actions, overflow, crumbRoot, spot, size = "page", help, helpTone }) {
  const ctxCrumbRoot = React.useContext(CrumbRootCtx);
  const resolvedCrumbRoot = crumbRoot !== undefined ? crumbRoot : (ctxCrumbRoot !== undefined ? ctxCrumbRoot : "관리자");
  void spot;  // Q4 로 장식 일러스트를 뺐다. 호출부 호환을 위해 prop 만 남긴다.
  /* size="section" — 다른 화면 안에 곁들여지는 하위 패널(예: OrgConsole 오른쪽의 DataScreen)이
   * 이 컴포넌트를 그대로 쓰면 h4/h1 이 감싸는 페이지의 진짜 제목과 같은 무게라 "페이지가
   * 두 개 겹쳐 있다"처럼 읽힌다(사용자 지적: 조직도 화면에서 조직 관리 패널이 또 하나의
   * 페이지처럼 보임). 글자만 작게(h6/h2) 줄이는 하위 무게 — breadcrumb(area)는 상위
   * 페이지가 이미 보여 주므로 호출부는 보통 area=null 을 같이 넘긴다. */
  const isSection = size === "section";
  // PA-RC-0017: tab 이 있으면 3단(영역 › 화면 › 탭) — title 이 캡션 줄로 올라가고 tab 이 큰
  // 제목이 된다. 안 주는 61개 기존 호출부는 그대로 2단(관리자 › 영역 / 제목)이라 하위 호환된다.
  const crumb = [resolvedCrumbRoot, area, tab ? title : null].filter(Boolean).join(" › ");
  const heading = tab || title;
  // PA-RC-0022: 상시 안내 패널(8+ 화면, 실제로는 registry 28개 화면 전부가 DataScreen.jsx를
  // 통해 이 자리를 썼다)을 "제목 옆 도움말 토글"로 옮긴다 — 내용은 그대로, 기본 접힘만 바뀐다.
  // `SectionTitle`(아래, 카드 안 소제목)에도 `help` prop이 있지만 그건 상시 노출되는 평문
  // 한 줄이다 — 이름은 같아도 다른 컴포넌트의 다른 prop이라 여기서 새로 만든다. 화면마다
  // 매번 `useState`를 새로 선언하게 하지 않으려고(호출부 28곳을 전부 고치는 대신) 접힘
  // 상태를 이 컴포넌트가 직접 들고, 호출부는 `help` 내용만 넘긴다.
  const [helpOpen, setHelpOpen] = React.useState(false);
  const helpId = help ? "page-help-" + Math.random().toString(36).slice(2, 8) : undefined;
  return (
    <>
      <Box
        className="k-page-head"
        sx={{ position: "relative", display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: isSection ? 1.5 : 3, flexWrap: "wrap", mb: help && helpOpen ? 1 : (isSection ? 1.5 : 3) }}
      >
        {/* 투명 장식 클로비(opacity .1)를 뺐다 — 사용자 지적 Q4.
            61개 화면 중 15곳에만 있어서, 화면을 옮길 때마다 흐린 그림이 나타났다 사라졌다 했다.
            "있다 없다" 가 반복되면 통일감이 없어 보인다. `spot` prop 은 호출부 13곳이 아직
            넘기고 있어 시그니처만 남긴다(그 값은 이제 무시된다).
            클로비는 히어로·빈 상태·드로어·FAB 처럼 **의미가 있는 자리**에만 둔다. */}
        <Box sx={{ position: "relative", zIndex: 1, flex: 1, minWidth: 0 }}>
          {crumb ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontWeight: FONT_WEIGHT.semibold }}>
              {crumb}
            </Typography>
          ) : null}
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: crumb ? 0.5 : 0 }}>
            <Typography variant={isSection ? "h6" : "h4"} component={isSection ? "h2" : "h1"}>{heading}</Typography>
            {help ? (
              <IconButton
                size="small"
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
        </Box>
        {/* 동작 줄 — **주 행동과 파괴적 행동을 같은 줄에서 경쟁시키지 않는다** (지시 11 · 12,
            E8). `actions` 는 이 화면에서 할 일이고, `overflow` 는 드물거나 되돌리기 어려운
            것들이다. 예전에는 페이지 머리에 «목록 · 수정 · 원본 열기 · 삭제» 넷이 나란히
            놓였고 그중 삭제가 채운 빨강이라 가장 자주 하는 일(수정)과 시선을 다퉜다.
            `DataScreen` 은 이미 행 단위로 같은 판단(`isRiskyHeader`)을 하는데 페이지
            레벨에는 그 자리가 없었다 — 이제 있다. */}
        {/* 이 줄에 `alignItems` 를 주지 않는다 — 헤더 행 자체가 `flex-end` 로 바닥을
            맞추므로 기본 stretch 가 맞다.
            (원인 귀속 정정) 이 주석은 한때 조직 화면 넷의 `control_baseline_mismatch`
            신규 fail 24셀을 «잠깐 넣었던 alignItems:center» 탓으로 적어 두었는데, **틀렸다.**
            그 fail 을 낸 배포본(`kit.TfNSaiDa.js`)에는 `alignItems` 가 없다 — stretch 상태에서
            나는 실패다. 독립 검수가 배포 PNG 를 직접 찍어 원인을 짚었다: 「?」 글리프와
            「조직 추가」 버튼의 중심 y 가 **둘 다 242.5 로 정확히 같다**(어긋남 0px). 이
            assertion 은 거대 flex 컨테이너의 각 행에서 `querySelector` 로 **첫 후손 컨트롤**을
            뽑아 짝지어서, 깊이가 다른 두 컨트롤(빈 문자열 표본 포함)을 비교하고 있다 —
            시각 결함이 아니라 프로브 기하 노이즈다. 이 줄은 이 실패의 원인이 아니고,
            해당 24셀은 라우트 Surface 넷에 OPEN Finding 으로 이미 걸려 있다(W8·W12).
            assertion 자체는 PLAN 이 W5 에서 `--fail-on` 으로 승격하는 대상이다. */}
        {actions || (overflow && overflow.length) ? (
          <Box className="k-page-actions" sx={{ position: "relative", zIndex: 1, display: "flex", gap: 1, flexWrap: "wrap" }}>
            {actions}
            {overflow && overflow.length ? <OverflowMenu items={overflow} /> : null}
          </Box>
        ) : null}
      </Box>
      {help ? (
        <Collapse in={helpOpen} id={helpId}>
          <Box sx={{ mb: isSection ? 1.5 : 3 }}>
            <Callout tone={helpTone}>{help}</Callout>
          </Box>
        </Collapse>
      ) : null}
    </>
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
export function Section({ title, action, help, rule = false, component = "section", children, sx }) {
  /* 호출부의 `sx` 가 함수일 수도 있다(테마를 읽는 자리). 객체로만 받아 펼치면 함수는
     **조용히 사라진다** — 이 저장소가 여러 번 밟은 "선언은 있는데 화면에는 없다" 의 한 형태다.
     `Surface` 가 두 형태를 모두 받으므로 여기서 형태를 유지한 채 넘긴다. */
  const merged = typeof sx === "function"
    ? (theme) => ({ mb: SECTION_GAP, ...sx(theme) })
    : { mb: SECTION_GAP, ...sx };
  return (
    <Surface tone="none" component={component} sx={merged}>
      {title ? <SectionTitle title={title} action={action} help={help} sx={rule ? { mb: 1 } : undefined} /> : null}
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
export function SectionTitle({ title, children, action, help, component = "h3", sx }) {
  const label = title != null ? title : children;
  return (
    <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap", mb: 1.5, ...sx }}>
      <Box sx={{ minWidth: 0 }}>
        <Typography component={component} variant="sectionTitle">{label}</Typography>
        {help ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: "70ch" }}>
            {help}
          </Typography>
        ) : null}
      </Box>
      {action}
    </Box>
  );
}
