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
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import HelpOutlineRoundedIcon from "@mui/icons-material/HelpOutlineRounded";
import Collapse from "@mui/material/Collapse";
import { ART, SPOT } from "../lib/assets.js";
import { maxLengthFor } from "../lib/fieldLimits.js";
import { apiToKstLocal, kstLocalToApi } from "../lib/format.js";
import { declaredRowName, rowNameOf } from "./rowName.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS, TABLE_CARD_QUERY } from "./theme.js";
import { CARD_PADDING, STAT_CARD_PADDING, STAT_VALUE_FONT_SIZE } from "./density.js";
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

export function Badge({ value, kind }) {
  const raw = String(value == null ? "" : value);
  const k = kind || STATUS_KIND[raw] || "neutral";
  const extra = EXTRA_TONE_VARS[k];
  return (
    <MuiChip
      className="k-badge"
      size="small"
      label={statusText(value)}
      color={extra ? undefined : TONE_COLOR[k] || "default"}
      variant={k === "neutral" ? "outlined" : "filled"}
      sx={{
        height: 22, fontSize: FONT_SIZE.caption, "& .MuiChip-label": { px: 1.25 },
        ...(extra && { backgroundColor: extra.bg, color: extra.fg }),
      }}
    />
  );
}

/* 버튼 — 기존 variant 어휘(primary/ghost/danger/기본)와 size="sm"을 그대로 받는다. */
const BUTTON_VARIANT = {
  primary: { variant: "contained", color: "primary" },
  danger: { variant: "contained", color: "error" },
  ghost: { variant: "text", color: "inherit" },
  default: { variant: "outlined", color: "inherit" },
};
/* loading: 라벨을 "처리 중…"으로 바꿔치기하지 않는다(예전 DataScreen/ModalFooter 관행) —
 * 텍스트만 바뀌면 스피너도 없고 버튼 폭도 라벨 길이 따라 흔들린다(DS-04). 라벨은 그대로 두고
 * visibility만 숨겨 폭을 고정한 채 스피너를 겹쳐 그린다. */
export function Button({ variant = "default", size, loading = false, disabled, children, sx, ...rest }) {
  const v = BUTTON_VARIANT[variant] || BUTTON_VARIANT.default;
  const isSm = size === "sm";
  return (
    <MuiButton
      type="button"
      size={isSm ? "small" : "medium"}
      disabled={disabled || loading}
      {...v}
      {...rest}
      sx={{ position: "relative", ...sx }}
    >
      <Box component="span" sx={{ visibility: loading ? "hidden" : "visible", display: "inline-flex", alignItems: "center" }}>
        {children}
      </Box>
      {loading ? (
        <CircularProgress
          size={isSm ? 14 : 16}
          color="inherit"
          sx={{ position: "absolute", top: "50%", left: "50%", marginTop: isSm ? "-7px" : "-8px", marginLeft: isSm ? "-7px" : "-8px" }}
        />
      ) : null}
    </MuiButton>
  );
}

/* 안쪽 여백은 기준선 `.card.pad`(20px)다. 예전에는 `p: 3`(=1.5rem, 기본 루트에서 24px)이었다.
 * 한 변에 4px 이지만 **앱의 모든 카드**가 높이도 폭도 8px 씩 커지는 값이라
 * "담은 정보에 비해 카드가 너무 크다"로 보였다. 게다가 이 앱은 4K에서 루트 폰트를 올리므로
 * 24px 이 2560에서 27px, 3840에서 30px 로 더 벌어진다(기준선은 화면 폭과 무관하게 20px 다). */
export function Card({ className, children, sx, ...rest }) {
  return (
    <MuiCard className={className} elevation={0} sx={{ p: CARD_PADDING, ...sx }} {...rest}>
      {children}
    </MuiCard>
  );
}

export function Callout({ tone = "info", children }) {
  // 심각도를 색만으로 구분하지 않는다(WCAG 1.4.1). MUI 기본 아이콘 대신 짧은 텍스트 라벨을
  // 쓴다 — 기호는 문화·스크린리더별로 읽히는 방식이 달라 이 앱은 처음부터 글자를 택했다.
  const label = tone === "danger" ? "오류" : tone === "warn" ? "주의" : tone === "success" ? "완료" : "안내";
  return (
    <MuiAlert
      className="k-callout"
      severity={TONE_SEVERITY[tone] || "info"}
      icon={false}
      variant="outlined"
      /* 반지름을 카드와 맞춘다(18px). `MuiAlert` 는 `shape.borderRadius`(14)를 받는데,
         안내 상자는 화면에서 카드 바로 위에 놓이는 자리라 둘의 모서리가 다르면 한 화면에
         반지름이 두 종류가 된다 — 기준 대조에서 **24화면**이 이 한 가지 때문에 어긋났다.
         그림자는 주지 않는다: 안내는 카드가 아니라 카드 앞의 한 줄이고, 띄우면 본문보다
         앞에 나서 버린다(기준도 테두리만 쓴다). */
      sx={{
        alignItems: "flex-start", borderRadius: `${RADIUS.lg}px`,
        // 한국어 줄바꿈(#11) — 이 상자가 **모든 페이지의 도움말**을 그린다. 여기 한 줄이
        // 앱 전체의 안내 문구를 고친다. `Mascot.jsx` 가 같은 증상("도와드/려요")을 진단해
        // 놓고 거기 한 곳에만 걸어 뒀던 것을 토큰으로 올렸다.
        "& .MuiAlert-message": { minWidth: 0, width: "100%", ...KO_WORD_BREAK },
      }}
    >
      <Box component="span" sx={{ fontWeight: FONT_WEIGHT.extrabold, mr: 1.5, whiteSpace: "nowrap" }}>{label}</Box>
      <Box component="span" className="k-callout-body">{children}</Box>
    </MuiAlert>
  );
}

export function StatCard({ value, label, kind, onClick, active, note }) {
  // 심각도는 색만으로 전하지 않는다(WCAG 1.4.1). 짧은 텍스트 태그('주의'/'위험')로 비색상 단서를 준다.
  const sev = kind === "danger" ? "위험" : kind === "warn" ? "주의" : null;
  const color = TONE_COLOR[kind];
  return (
    <Paper
      className="k-stat"
      component={onClick ? "button" : "div"}
      type={onClick ? "button" : undefined}
      onClick={onClick}
      aria-pressed={onClick ? !!active : undefined}
      variant="outlined"
      sx={{
        /* 기준선 `.kpi-card`(17px 18px)다. 예전 `p: 3`(24px)은 카드가 담는 것이 숫자 한 줄과
           라벨 한 줄뿐인데도 위아래 여백만 48px 을 먹었다. 기준선의 `min-height: 132px` 은
           일부러 가져오지 않는다 — 기준선 카드는 그 안에 부연(kpi-note)과 증감 칩까지 그리고
           우리는 안 그린다. 없는 내용을 위해 높이를 비워 두면 사용자가 지적한 그 문제
           ("정보에 비해 카드가 크다")를 검사가 통과시키는 꼴이 된다. */
        p: STAT_CARD_PADDING, textAlign: "left", width: "100%", minWidth: 0, position: "relative",
        display: "grid", gap: 0.5, alignContent: "start",
        font: "inherit", color: "inherit", cursor: onClick ? "pointer" : "default",
        borderColor: active ? "primary.main" : "divider",
        borderWidth: active ? 2 : 1,
        transition: "border-color .15s, transform .15s",
        "&:hover": onClick ? { borderColor: "primary.main", transform: "translateY(-1px)" } : undefined,
      }}
    >
      <Typography
        component="div"
        /* 기준선 `.kpi-value`(30px). 예전 clamp 는 상한이 2.25rem 이라 4K 루트(20px)에서
           45px 까지 커졌다 — 숫자 하나가 카드 높이를 혼자 밀어 올리던 자리다. */
        sx={{ fontSize: STAT_VALUE_FONT_SIZE, fontWeight: FONT_WEIGHT.extrabold, lineHeight: 1.1 }}
        color={color && color !== "default" ? `${color}.main` : "text.primary"}
      >
        {value == null ? "-" : value}
      </Typography>
      <Typography component="div" variant="body2" color="text.secondary" sx={{ display: "flex", gap: 1, alignItems: "center" }}>
        {label}
        {sev ? (
          /* QAH-02(2026-08-11 하네스 실측): label이 길면(예: "이번 주 마감") flex 행이
           * 좁아지고, 한글은 라틴 문자와 달리 음절 사이 어디서나 줄바꿈이 허용돼(word-break
           * 기본 규칙) white-space를 안 주면 "주의" 2글자짜리 배지가 세로 한 글자씩
           * 쌓이며 너비가 12.6px까지 눌렸다(admin_dashboard, 라이트·다크 둘 다). 배지는
           * 애초에 줄바꿈될 이유가 없는 고정 짧은 라벨이라 줄바꿈 자체를 막는다.
           * PA-RC-0001: 11px는 6단계 스케일에 없지만, 위 실측 폭(12.6px)에서 12px로 올리면
           * 그 줄바꿈이 재현될 위험이 있어 실측 없이는 안 바꾼다 — 의도된 예외. */
          <Box component="span" sx={{ fontSize: "0.6875rem", fontWeight: FONT_WEIGHT.extrabold, color: `${color}.strong`, whiteSpace: "nowrap", flexShrink: 0 }}>{sev}</Box>
        ) : null}
      </Typography>
      {/* VIS-09/VIS-27: 숫자를 한정하는 각주(예: "계산이 끝난 20건만")는 구역 아래 멀리
          떨어진 공용 Note가 아니라 그 숫자를 담은 카드 안에 둔다 — 그래야 어느 숫자를
          한정하는지 다시 찾을 필요가 없다(/projects/:id 상세의 기존 패턴과 같은 원칙). */}
      {note ? (
        <Typography component="div" variant="caption" color="text.secondary" sx={{ fontSize: FONT_SIZE.caption, lineHeight: 1.4, ...KO_WORD_BREAK }}>
          {note}
        </Typography>
      ) : null}
      {/* 클릭 가능 여부가 hover(cursor)로만 드러나면 터치 사용자는 눌러보기 전까진 알 방법이 없다. */}
      {onClick ? (
        <ChevronRightRoundedIcon
          aria-hidden="true"
          sx={{ position: "absolute", top: 12, right: 8, fontSize: 20, color: "text.disabled" }}
        />
      ) : null}
    </Paper>
  );
}

export function Skeleton({ lines = 3 }) {
  // 스켈레톤은 장식(aria-hidden)이라 스크린리더엔 침묵이다 — 별도 live 노드로 로딩을 낭독한다.
  return (
    <>
      <span className="sr-only" aria-live="polite">불러오는 중…</span>
      <Box aria-hidden="true" sx={{ display: "grid", gap: 1.5, py: 1 }}>
        {Array.from({ length: lines }).map((_, i) => (
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
  steps, expected, action, relatedLink, art, size,
}) {
  const compact = size === "compact";
  const stepList = Array.isArray(steps) ? steps.filter((s) => s != null && s !== "") : null;
  const artSrc = !compact && art && ART[art] ? ART[art] : null;
  // KO_WORD_BREAK: Callout·Mascot는 이미 쓰는데(사용자 지적 #11) 정작 이 컴포넌트가 31개 파일
  // 전체의 빈 상태 안내문을 그리면서 빠져 있었다 — 좁은 화면에서 한글이 단어 중간에서 잘렸다.
  const bodySx = { maxWidth: "60ch", fontSize: compact ? FONT_SIZE.bodySm : undefined, ...KO_WORD_BREAK };
  // role="status" + aria-live로 빈 상태 전환을 낭독한다. 제목은 heading으로 올려 탐색 가능하게.
  return (
    // VIS-50/VIS-52: 4K 스크린샷 실측 확인(dist/ui-qa/converge-pa15-4k) — 삽화·여백이
    // 1920 그대로라 3840 캔버스에서 왼쪽 위에 작게 몰려 있었다. uhd 삽화 폭을 sm/xxl의
    // 확대 비율(약 160/600→200/2200, 뷰포트 대비 8~9%)에 맞춰 240→320으로 올리고(그
    // 비율에서 벗어나 있던 값이었다), 세로 여백도 uhd에서만 키운다. 다만 전체 높이를
    // 채우는 실제 세로 가운데 정렬은 이 컴포넌트가 31개 파일에 공유돼 있어(모달·좁은
    // 카드 등 고정 높이가 아닌 맥락도 많다) 여기서 하지 않는다 — 그건 각 소비처의 레이아웃
    // 문제라 이 컴포넌트 하나로 안전하게 처리할 수 없다.
    <Box className="k-empty" role="status" aria-live="polite" sx={{ display: "grid", justifyItems: "center", textAlign: "center", gap: compact ? 0.75 : 1.5, py: compact ? 2 : { xs: 6, uhd: 14 }, px: compact ? 1.5 : 3 }}>
      {artSrc ? (
        <Box
          component="img" src={artSrc} alt="" aria-hidden="true" loading="lazy" decoding="async"
          sx={{ display: { xs: "none", sm: "block" }, width: { sm: 160, xxl: 200, uhd: 320 }, height: "auto", opacity: 0.95 }}
        />
      ) : icon ? (
        <Box aria-hidden="true" sx={{ fontSize: compact ? 20 : 32, color: "text.disabled" }}>{icon}</Box>
      ) : null}
      <Typography role="heading" aria-level={2} sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: compact ? FONT_SIZE.body : FONT_SIZE.sectionTitle, ...KO_WORD_BREAK }}>{title}</Typography>
      {situation ? <Typography variant="body2" color="text.secondary" sx={bodySx}>{situation}</Typography> : null}
      {help ? <Typography variant="body2" color="text.secondary" sx={bodySx}>{help}</Typography> : null}
      {prerequisite ? (
        <Typography variant="body2" color="text.secondary" sx={bodySx}>
          <Box component="span" sx={{ fontWeight: FONT_WEIGHT.bold, mr: 1 }}>필요한 것</Box>{prerequisite}
        </Typography>
      ) : null}
      {stepList && stepList.length ? (
        <Box component="ol" sx={{ textAlign: "left", m: 0, pl: 3, color: "text.secondary", fontSize: compact ? FONT_SIZE.bodySm : FONT_SIZE.body, display: "grid", gap: 0.5, maxWidth: "60ch", ...KO_WORD_BREAK }}>
          {stepList.map((s, i) => <li key={i}>{s}</li>)}
        </Box>
      ) : null}
      {expected ? (
        <Typography variant="body2" color="text.secondary" sx={bodySx}>
          <Box component="span" sx={{ fontWeight: FONT_WEIGHT.bold, mr: 1 }}>기대 결과</Box>{expected}
        </Typography>
      ) : null}
      {action ? <Box sx={{ mt: compact ? 0.5 : 1 }}>{action}</Box> : null}
      {relatedLink && relatedLink.href ? (
        <Link href={relatedLink.href} underline="hover" sx={{ fontSize: compact ? FONT_SIZE.bodySm : FONT_SIZE.body }}>
          {relatedLink.label || "관련 화면으로"}
        </Link>
      ) : null}
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
          ? <MuiButton variant="contained" size={compact ? "small" : "medium"} href="/login">로그인 화면으로</MuiButton>
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
 * 접근성: 행은 표 의미(row)를 유지하고, 상세 열기는 마지막 칸의 실제 <button>이 담당한다. */
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

/* 셀 렌더러에 넘기는 두 번째 인자(ctx)는 **그 행에 대한 표의 지식**이다. 지금은 rowName
 * 하나뿐이다: 선택 체크박스처럼 셀 안에 있으면서 '자기 행이 무엇인지' 알아야 하는 컨트롤이
 * 쓴다. 화면이 열 정의마다 라벨을 손으로 적지 않게 하려면 표가 알려 주는 수밖에 없다
 * (열은 자기 옆 열들을 모른다). 기존 render 들은 인자를 하나만 받으므로 그대로 동작한다. */
function cellValue(c, row, ctx) {
  if (c.render) return c.render(row, ctx);
  const v = row[c.key];
  return v == null || v === "" ? "-" : String(v);
}

export function DataTable({ columns, rows, rowKey, onRow, empty, fixed, ellipsis, stickyHeader }) {
  // 방어: 비정상 입력이 와도 렌더 중 throw하지 않고 빈-목록 안내로 폴백한다.
  // 공용 표라 한 화면의 실수나 API shape 변화가 전역 크래시로 번지지 않게 한다.
  const baseCols = Array.isArray(columns) ? columns : [];
  const safeRows = Array.isArray(rows) ? rows : [];
  const keyOf = typeof rowKey === "function" ? rowKey : (_, i) => i;
  const cols = onRow ? [...baseCols, { key: "__open", label: "", align: "right", open: true, width: "6rem" }] : baseCols;
  const narrow = useMediaQuery(TABLE_CARD_QUERY);

  /* 이 저장소에서 **가장 많이 반복되는 버튼**이다 — 관리자 28화면 × 표의 모든 행.
     `MuiButton variant="outlined"` 를 그냥 쓰면 MUI 기본 색(primary)이 붙어 **혼자만
     파랗다**. kit 의 `default` 는 `color: "inherit"`(중립)이고 같은 화면의 다른 버튼은
     전부 그쪽이다. 한 화면에 수십 개가 깔리므로 이 하나가 화면 전체의 색 인상을 정한다
     (K-B1). kit `Button` 을 쓰면 어휘가 한 곳에서만 정해진다. */
  const openButton = (row) => (
    <Button
      size="sm"
      aria-label={rowOpenLabel(baseCols, row)}
      onClick={(e) => { e.stopPropagation(); onRow(row); }}
    >
      상세
    </Button>
  );

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
              {cols.map((c) => c.open ? (
                <Box key={c.key} sx={{ pt: 1 }}>{openButton(row)}</Box>
              ) : (
                <Box key={c.key} sx={{ display: "grid", gridTemplateColumns: "7rem minmax(0,1fr)", gap: 1, alignItems: "start" }}>
                  <Typography variant="caption" color="text.secondary">{c.label}</Typography>
                  <Box sx={{ minWidth: 0, fontSize: FONT_SIZE.body, overflowWrap: "anywhere" }}>{cellValue(c, row, ctx)}</Box>
                </Box>
              ))}
            </Paper>
          );
        })}
      </Stack>
    );
  }

  return (
    <TableContainer>
      <Table size="small" stickyHeader={stickyHeader} sx={{ tableLayout: fixed ? "fixed" : "auto" }}>
        <TableHead>
          <TableRow>
            {cols.map((c) => (
              <TableCell
                key={c.key}
                scope="col"
                align={c.align || "left"}
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
                  width: c.width, minWidth: c.minWidth ?? (c.open ? undefined : DEFAULT_COL_MIN_WIDTH), whiteSpace: "nowrap",
                  ...(stickyHeader ? { bgcolor: "background.paper" } : null),
                }}
              >
                {/* 상세 열기 칸은 라벨이 비어 있어 스크린리더가 이름 없이 침묵으로 읽었다. */}
                {c.open ? <span className="sr-only">동작</span> : c.label}
              </TableCell>
            ))}
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
                {cols.map((c) => {
                  /* HOST-01/HOST-02/VIS-73 — 열 폭이 순수하게 내용에서 파생되던 게 두 방향 모두에서
                     문제였다: ① 값 하나가 길면 그 셀이 51px×2,353px까지 벌어지고 같은 행의 다른
                     셀도 그 높이로 끌려간다(HOST-01, truncateCol이 있는 자리에만 부분 적용돼 있었다)
                     ② 열이 많으면 `overflowWrap:anywhere`가 각 열을 '한 글자' 폭까지 짜부라뜨린다
                     (VIS-73). `c.render`가 있는 열(배지·버튼·직접 JSX)은 이미 자기 폭을 스스로
                     관리하므로 건드리지 않는다 — 값을 있는 그대로 보여주는 순수 텍스트 열만 기본을
                     말줄임으로 바꾼다(`truncateCol`이 문자 수 기준으로 이미 하던 것과 같은 방향,
                     이제 그걸 안 쓴 나머지 열에도 `DataTable` 자신이 최소한의 보호를 준다).
                     `title`로 전체 값은 그대로 hover에 남는다 — truncateCol과 같은 힌트 패턴. */
                  const truncate = !c.open && (ellipsis || !c.render);
                  const raw = !c.open && !c.render ? cellValue(c, row, ctx) : null;
                  return (
                    <TableCell
                      key={c.key}
                      align={c.align || "left"}
                      title={truncate && raw && raw !== "-" ? raw : undefined}
                      sx={truncate
                        ? { whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 0,
                           minWidth: c.minWidth ?? DEFAULT_COL_MIN_WIDTH }
                        : { overflowWrap: c.nowrap ? "normal" : "anywhere",
                           whiteSpace: c.nowrap ? "nowrap" : undefined,
                           minWidth: c.minWidth ?? (c.open ? undefined : DEFAULT_COL_MIN_WIDTH) }}
                    >
                      {c.open ? openButton(row) : raw != null ? raw : cellValue(c, row, ctx)}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
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
      <ModalHeader title={title} onClose={requestClose} titleId={titleId} />
      <ModalBody>{children}</ModalBody>
      {footer ? <ModalActions>{footer}</ModalActions> : null}
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
export function FormField({ field: f, value, onChange, invalid, maxLength }) {
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
  const helpText = charCount ? (f.help ? `${f.help} (${charCount})` : charCount) : (f.help || undefined);
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
              inputProps={{ "aria-describedby": helpId, "aria-required": required || undefined }}
            />
          }
          label={
            <>
              {f.checkLabel || f.label || "사용"}
              {required ? <Box component="span" sx={{ color: "error.main" }}> *</Box> : null}
            </>
          }
        />
        {f.help ? <Typography id={helpId} variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>{f.help}</Typography> : null}
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
    label: f.label,
    helperText: helpText,
    value: value != null ? value : "",
    onChange: (e) => onChange(e.target.value),
    sx: { mb: 2.5 },
  };

  if (f.type === "select") {
    return (
      <TextField {...common} select className="k-field">
        {selNeedEmpty ? (
          <MenuItem value="" disabled={required}>
            {hasOptions ? "선택 안 함" : "선택할 항목이 없습니다"}
          </MenuItem>
        ) : null}
        {(f.options || []).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
      </TextField>
    );
  }

  return (
    <TextField
      {...common}
      className="k-field"
      multiline={multiline}
      minRows={multiline ? (isJson ? 10 : 3) : undefined}
      type={
        f.type === "number" ? "number"
          : f.type === "password" ? "password"
          : f.type === "email" ? "email"
          : f.type === "date" || f.type === "datetime-local" ? f.type
          : "text"
      }
      InputLabelProps={f.type === "date" || f.type === "datetime-local" ? { shrink: true } : undefined}
      onPaste={handlePasteOverflowWarning}
      inputProps={{
        ...(f.type === "email" ? { inputMode: "email", autoCapitalize: "none" } : null),
        ...(maxLength ? { maxLength } : null),
      }}
      /* JSON은 사람이 중첩 구조를 손으로 편집한다 — 가변폭 폰트로는 중괄호·들여쓰기가 안 맞는다. */
      InputProps={isJson ? { sx: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: FONT_SIZE.bodySm } } : undefined}
    />
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
   * render." 로 트리를 통째로 버린다 — 관리자 화면의 '+ 추가'·'수정'을 누르는 순간 화면이
   * 사라졌다. 조건부 반환 위로 올리면 규칙(훅은 항상 같은 순서)이 지켜진다. */
  const shownFields = React.useMemo(
    () => (fields || []).filter((f) => (typeof f.showIf === "function" ? f.showIf(values) : true)),
    [fields, values],
  );
  if (!open) return null;
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
        window.setTimeout(() => { window.location.href = "/login"; }, 1200);
        return; // busy=true로 남겨 재제출을 막는다 — 곧 페이지가 이동한다.
      }
      // UX-40: details({loc,msg} 배열, 예: 비밀번호 정책 위반) 합치는 로직은 lib/api.js의
      // api()로 옮겼다 — e.message가 이제 이미 합쳐진 문구다(모든 호출부가 공짜로 받는다).
      // 여기서 다시 합치면 details가 중복으로 붙는다.
      setErr(e.message || "저장하지 못했습니다. 다시 시도해 주세요."); setBusy(false); return;
    }
    setBusy(false);
  }

  const sz = size || (shownFields.length > 5 ? "lg" : "md");
  const footer = <ModalFooter onCancel={requestClose} onSubmit={submit} submitLabel={submitLabel || "저장"} busy={busy} />;
  return (
    <Modal open={open} onClose={requestClose} title={title} size={sz} footer={footer}>
      {/* 필드를 <form>으로 감싸 Enter가 자연스럽게 제출되게 한다(textarea/json은 여러 줄 입력을
          위해 기본 Enter 동작 유지). */}
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {err ? <MuiAlert severity="error" className="k-form-err" sx={{ mb: 2.5 }} role="alert">{err}</MuiAlert> : null}
        {shownFields.map((f) => <FormField key={f.name} field={f} value={values[f.name]} invalid={errField === f.name}
          onChange={(val) => set(f.name, val)}
          maxLength={screenKey ? maxLengthFor(screenKey, formKind, f.name) : null} />)}
        {/* 화면에 보이지 않는 제출 버튼 — 실제 저장 버튼은 Dialog footer(별도 DOM 트리)에 있어
            이 <form> 안에 없다. type="submit"이 하나도 없으면 브라우저에 따라 단일 텍스트
            입력에서 Enter가 폼을 제출하지 않는다. */}
        <button type="submit" className="sr-only" tabIndex={-1} aria-hidden="true" />
      </form>
    </Modal>
  );
}
// 하위호환 별칭 — 기존 호출부(FormDrawer/FormDialog/DialogFooter)는 그대로 두되 전부 중앙 모달로 동작.
// `Drawer = Modal`은 뺐다(DS-10) — 진짜 옆에서 밀려나오는 드로어(AppShell 사이드바,
// AssistantDrawer)는 애초에 이 별칭을 안 쓰고 `@mui/material/Drawer`를 직접 쓴다. 이 이름은
// 중앙 모달 6곳에서만 쓰이고 있었는데, 이름이 "드로어"라 실제 동작(가운데 다이얼로그)과
// 어긋나 혼동을 줬다 — 호출부를 전부 `Modal`로 고쳐 부른다(동작은 그대로, 이름만 정확해짐).
export const FormDrawer = FormModal;
export const FormDialog = FormModal;
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
          submitLabel={state ? state.confirmLabel : "확인"} submitVariant={state && state.danger ? "danger" : "primary"} />}>
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

/* 페이지 헤더 — 빵부스러기→제목 순서와 간격을 한곳에서 정한다.
 * crumbRoot: 빵부스러기 접두어(기본 '관리자'). 사용자 대면 화면은 다른 뿌리를 넘기거나
 *   area를 비워 빵부스러기 자체를 숨길 수 있다.
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
export function PageHeader({ area, title, tab, actions, crumbRoot = "관리자", spot, size = "page", help, helpTone }) {
  void spot;  // Q4 로 장식 일러스트를 뺐다. 호출부 호환을 위해 prop 만 남긴다.
  /* size="section" — 다른 화면 안에 곁들여지는 하위 패널(예: OrgConsole 오른쪽의 DataScreen)이
   * 이 컴포넌트를 그대로 쓰면 h4/h1 이 감싸는 페이지의 진짜 제목과 같은 무게라 "페이지가
   * 두 개 겹쳐 있다"처럼 읽힌다(사용자 지적: 조직도 화면에서 조직 관리 패널이 또 하나의
   * 페이지처럼 보임). 글자만 작게(h6/h2) 줄이는 하위 무게 — breadcrumb(area)는 상위
   * 페이지가 이미 보여 주므로 호출부는 보통 area=null 을 같이 넘긴다. */
  const isSection = size === "section";
  // PA-RC-0017: tab 이 있으면 3단(영역 › 화면 › 탭) — title 이 캡션 줄로 올라가고 tab 이 큰
  // 제목이 된다. 안 주는 61개 기존 호출부는 그대로 2단(관리자 › 영역 / 제목)이라 하위 호환된다.
  const crumb = [crumbRoot, area, tab ? title : null].filter(Boolean).join(" › ");
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
        {actions ? <Box className="k-page-actions" sx={{ position: "relative", zIndex: 1, display: "flex", gap: 1, flexWrap: "wrap" }}>{actions}</Box> : null}
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
