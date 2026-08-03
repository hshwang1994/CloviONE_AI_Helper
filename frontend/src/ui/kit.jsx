import React from "react";
import MuiAlert from "@mui/material/Alert";
import MuiButton from "@mui/material/Button";
import MuiCard from "@mui/material/Card";
import MuiChip from "@mui/material/Chip";
import MuiDialog from "@mui/material/Dialog";
import MuiDialogActions from "@mui/material/DialogActions";
import MuiDialogContent from "@mui/material/DialogContent";
import MuiDialogTitle from "@mui/material/DialogTitle";
import MuiSkeleton from "@mui/material/Skeleton";
import MuiSnackbar from "@mui/material/Snackbar";
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
import { ART, SPOT } from "../lib/assets.js";

/* ClovirONE 공통 UI 키트 — 카드/배지/버튼/상태/빈 화면/스켈레톤을 한 규칙으로 그린다.
 *
 * 2026-08 재설계: 안쪽 구현을 MUI로 바꾸되 **export 이름과 prop 시그니처는 그대로 둔다**.
 * 화면 21개가 전부 이 파일에서 컴포넌트를 가져다 쓰기 때문에, 여기만 바꾸면 화면 파일을
 * 한 줄도 건드리지 않고 보이는 표면의 대부분이 새 디자인으로 바뀐다. 기존 vitest도 역할/텍스트로
 * 조회하므로 그대로 통과한다.
 *
 * 예외가 하나 있다: DataTable은 legacy 클래스(k-table)를 유지한다. screens.css가 화면별로
 * 열 너비를 .k-table th:nth-child(n)으로 고정하고(문서 표), 좁은 화면 카드 전환도 그 CSS가
 * 담당하기 때문이다. 표는 DataScreen 재설계(A3)에서 CSS까지 같이 옮긴다.
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

export function Badge({ value, kind }) {
  const raw = String(value == null ? "" : value);
  const k = kind || STATUS_KIND[raw] || "neutral";
  return (
    <MuiChip
      className="k-badge"
      size="small"
      label={statusText(value)}
      color={TONE_COLOR[k] || "default"}
      variant={k === "neutral" ? "outlined" : "filled"}
      sx={{ height: 22, fontSize: "0.75rem", "& .MuiChip-label": { px: 1.25 } }}
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
export function Button({ variant = "default", size, children, ...rest }) {
  const v = BUTTON_VARIANT[variant] || BUTTON_VARIANT.default;
  return (
    <MuiButton type="button" size={size === "sm" ? "small" : "medium"} {...v} {...rest}>
      {children}
    </MuiButton>
  );
}

export function Card({ className, children, sx, ...rest }) {
  return (
    <MuiCard className={className} elevation={0} sx={{ p: 3, ...sx }} {...rest}>
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
      sx={{ alignItems: "flex-start", "& .MuiAlert-message": { minWidth: 0, width: "100%" } }}
    >
      <Box component="span" sx={{ fontWeight: 800, mr: 1.5, whiteSpace: "nowrap" }}>{label}</Box>
      <Box component="span" className="k-callout-body">{children}</Box>
    </MuiAlert>
  );
}

export function StatCard({ value, label, kind, onClick, active }) {
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
        p: 3, textAlign: "left", width: "100%", minWidth: 0, position: "relative",
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
        sx={{ fontSize: "clamp(1.5rem, 1.2rem + .6vw, 2.25rem)", fontWeight: 800, lineHeight: 1.1 }}
        color={color && color !== "default" ? `${color}.main` : "text.primary"}
      >
        {value == null ? "-" : value}
      </Typography>
      <Typography component="div" variant="body2" color="text.secondary" sx={{ display: "flex", gap: 1, alignItems: "center" }}>
        {label}
        {sev ? (
          <Box component="span" sx={{ fontSize: "0.6875rem", fontWeight: 800, color: `${color}.main` }}>{sev}</Box>
        ) : null}
      </Typography>
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
 */
export function EmptyState({
  icon = null, title = "표시할 항목이 없습니다", help, situation, prerequisite,
  steps, expected, action, relatedLink, art,
}) {
  const stepList = Array.isArray(steps) ? steps.filter((s) => s != null && s !== "") : null;
  const artSrc = art && ART[art] ? ART[art] : null;
  // role="status" + aria-live로 빈 상태 전환을 낭독한다. 제목은 heading으로 올려 탐색 가능하게.
  return (
    <Box className="k-empty" role="status" aria-live="polite" sx={{ display: "grid", justifyItems: "center", textAlign: "center", gap: 1.5, py: 6, px: 3 }}>
      {artSrc ? (
        <Box
          component="img" src={artSrc} alt="" aria-hidden="true" loading="lazy" decoding="async"
          sx={{ display: { xs: "none", sm: "block" }, width: { sm: 160, xxl: 200, uhd: 240 }, height: "auto", opacity: 0.95 }}
        />
      ) : icon ? (
        <Box aria-hidden="true" sx={{ fontSize: 32, color: "text.disabled" }}>{icon}</Box>
      ) : null}
      <Typography role="heading" aria-level={2} sx={{ fontWeight: 750, fontSize: "1.0625rem" }}>{title}</Typography>
      {situation ? <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "60ch" }}>{situation}</Typography> : null}
      {help ? <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "60ch" }}>{help}</Typography> : null}
      {prerequisite ? (
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "60ch" }}>
          <Box component="span" sx={{ fontWeight: 750, mr: 1 }}>필요한 것</Box>{prerequisite}
        </Typography>
      ) : null}
      {stepList && stepList.length ? (
        <Box component="ol" sx={{ textAlign: "left", m: 0, pl: 3, color: "text.secondary", fontSize: "0.875rem", display: "grid", gap: 0.5, maxWidth: "60ch" }}>
          {stepList.map((s, i) => <li key={i}>{s}</li>)}
        </Box>
      ) : null}
      {expected ? (
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "60ch" }}>
          <Box component="span" sx={{ fontWeight: 750, mr: 1 }}>기대 결과</Box>{expected}
        </Typography>
      ) : null}
      {action ? <Box sx={{ mt: 1 }}>{action}</Box> : null}
      {relatedLink && relatedLink.href ? (
        <Link href={relatedLink.href} underline="hover" sx={{ fontSize: "0.875rem" }}>
          {relatedLink.label || "관련 화면으로"}
        </Link>
      ) : null}
    </Box>
  );
}

export function ErrorState({ error, onRetry }) {
  const msg = (error && error.message) || "문제가 발생했습니다.";
  const status = error && error.status;
  const code = error && error.body && error.body.error && error.body.error.code;
  const kind = error && error.kind;
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
    <Box className="k-empty" role="alert" sx={{ display: "grid", justifyItems: "center", textAlign: "center", gap: 1.5, py: 6, px: 3 }}>
      <Box
        component="img" src={artSrc} alt="" aria-hidden="true" loading="lazy" decoding="async"
        sx={{ display: { xs: "none", sm: "block" }, width: { sm: 160, xxl: 200, uhd: 240 }, height: "auto" }}
      />
      <Typography role="heading" aria-level={2} sx={{ fontWeight: 750, fontSize: "1.0625rem" }}>{title}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "60ch" }}>{help}</Typography>
      <Box sx={{ mt: 1 }}>
        {isAuth
          ? <MuiButton variant="contained" href="/login">로그인 화면으로</MuiButton>
          // "홈으로"(#/)는 이 SPA 안이라 다시 같은 403을 부른다 — 실제 페이지 이동이 필요하다.
          : isPwChange ? <MuiButton variant="contained" href="/change-password">비밀번호 변경하기</MuiButton>
          // 403/404는 재시도해도 소용없지만 아무 동작도 없으면 막다른 길이다.
          : (isForbidden || isGone) ? <MuiButton variant="contained" href="#/">홈으로</MuiButton>
          : (!noRetry && onRetry ? <Button variant="primary" onClick={onRetry}>다시 시도</Button> : null)}
      </Box>
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
export function DataTable({ columns, rows, rowKey, onRow, empty }) {
  // 방어: 비정상 입력이 와도 렌더 중 throw하지 않고 빈-목록 안내로 폴백한다.
  const baseCols = Array.isArray(columns) ? columns : [];
  const safeRows = Array.isArray(rows) ? rows : [];
  const keyOf = typeof rowKey === "function" ? rowKey : (_, i) => i;
  const cols = onRow ? [...baseCols, { key: "__open", label: "", align: "right", open: true }] : baseCols;
  return (
    <div className="k-table-wrap">
      <table className="k-table">
        <thead>
          {/* 상세 열기 칸은 label이 빈 문자열이라 스크린리더가 헤더 이름 없이 침묵으로 읽었다. */}
          <tr>{cols.map((c) => <th key={c.key} scope="col" className={[c.align ? "is-" + c.align : "", c.className || ""].filter(Boolean).join(" ")}>{c.open ? <span className="sr-only">동작</span> : c.label}</th>)}</tr>
        </thead>
        <tbody>
          {safeRows.length === 0 ? (
            <tr><td className="k-table-empty" colSpan={cols.length}>{empty || "표시할 항목이 없습니다."}</td></tr>
          ) : safeRows.map((row, i) => (
            // 셀 안의 링크/버튼 클릭은 행 클릭(상세 열기)으로 번지지 않게 한다.
            <tr key={keyOf(row, i)} className={onRow ? "is-click" : ""}
              onClick={onRow ? (e) => { if (e.target.closest("a,button")) return; onRow(row); } : undefined}>
              {cols.map((c) => (
                <td key={c.key} data-label={c.label} className={[c.align ? "is-" + c.align : "", c.className || ""].filter(Boolean).join(" ")}>
                  {c.open
                    ? <button type="button" className="k-row-open" aria-label={rowOpenLabel(baseCols, row)}
                        onClick={(e) => { e.stopPropagation(); onRow(row); }}>상세</button>
                    : (c.render ? c.render(row) : (row[c.key] == null || row[c.key] === "" ? "-" : String(row[c.key])))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* 공통 모달 — 모든 생성/수정/확인/상세가 중앙 모달을 쓴다.
 * 예전에는 포커스 트랩·Esc 스택·배경 스크롤 잠금을 직접 구현했다. MUI Dialog가 셋 다
 * 정확히 처리하므로(중첩 모달 포함) 그 코드는 지웠다 — 직접 구현이 남아 있으면 MUI와
 * 이중으로 걸려 Esc 한 번에 두 개가 닫히는 예전 버그가 다시 난다.
 * size: sm|md|lg. 모바일에서는 전체 화면. */
const SIZE_MAP = { sm: "sm", md: "md", lg: "lg" };

export function ModalHeader({ title, onClose, titleId }) {
  return (
    <MuiDialogTitle
      id={titleId}
      sx={{ display: "flex", alignItems: "center", gap: 2, pr: 1.5, fontSize: "1.0625rem", fontWeight: 780 }}
    >
      <Box component="span" sx={{ flex: 1, minWidth: 0 }}>{title}</Box>
      <IconButton onClick={onClose} aria-label="닫기" size="small"><CloseRoundedIcon fontSize="small" /></IconButton>
    </MuiDialogTitle>
  );
}
export function ModalBody({ children }) {
  return <MuiDialogContent dividers sx={{ minWidth: 0 }}>{children}</MuiDialogContent>;
}
/* 표준 하단 작업줄 — 취소(고스트), 기본 작업(오른쪽). 전 화면 동일 위치·크기. */
export function ModalFooter({ onCancel, onSubmit, submitLabel = "저장", cancelLabel = "취소", busy, submitVariant = "primary" }) {
  return (
    <MuiDialogActions className="k-footer-row" sx={{ px: 3, py: 2, gap: 1 }}>
      {onCancel ? <Button variant="ghost" onClick={onCancel} disabled={busy}>{cancelLabel}</Button> : null}
      {onSubmit ? <Button variant={submitVariant} onClick={onSubmit} disabled={busy}>{busy ? "처리 중…" : submitLabel}</Button> : null}
    </MuiDialogActions>
  );
}

export function Modal({ open, onClose, title, size = "md", children, footer }) {
  const titleId = React.useId();
  if (!open) return null;
  return (
    <MuiDialog
      open={!!open}
      onClose={onClose}
      maxWidth={SIZE_MAP[size] || "md"}
      fullWidth
      aria-labelledby={titleId}
      /* 모바일에서는 전체 화면 — 좁은 화면에서 폼이 잘려 스크롤조차 안 되던 문제. */
      sx={{ "& .MuiDialog-paper": { m: { xs: 0, sm: 4 }, width: { xs: "100%", sm: "auto" }, maxHeight: { xs: "100%", sm: "calc(100% - 4rem)" }, height: { xs: "100%", sm: "auto" }, borderRadius: { xs: 0, sm: 2.5 } } }}
    >
      <ModalHeader title={title} onClose={onClose} titleId={titleId} />
      <ModalBody>{children}</ModalBody>
      {footer}
    </MuiDialog>
  );
}

/* 공통 입력 필드 — 라벨/필수(*)/도움말/오류를 한곳에서. 라벨은 htmlFor/id로 입력과 연결해
 * 스크린리더가 이름을 읽게 한다(체크박스는 라벨이 입력을 감싸 이미 연결됨). */
export function FormField({ field: f, value, onChange, invalid }) {
  const id = "ff-" + f.name;
  const helpId = f.help ? id + "-helper-text" : undefined;
  const required = !!f.required;
  const isJson = f.type === "json";
  const multiline = f.type === "textarea" || isJson;

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
    helperText: f.help || undefined,
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
      inputProps={f.type === "email" ? { inputMode: "email", autoCapitalize: "none" } : undefined}
      /* JSON은 사람이 중첩 구조를 손으로 편집한다 — 가변폭 폰트로는 중괄호·들여쓰기가 안 맞는다. */
      InputProps={isJson ? { sx: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "0.8125rem" } } : undefined}
    />
  );
}

/* 설정 주도 폼 — 항상 중앙 모달. 항목이 많으면(>5) 큰 모달(lg).
 * 제출 로직은 한 줄도 바꾸지 않았다: 숫자 변환, hadValue→null, JSON 객체 검증, 401 처리,
 * details 평탄화, 더티 닫기 확인. 이 15개 이상 화면이 공유하는 유일한 저장 표면이다. */
export function FormModal({ open, title, fields, initial, submitLabel, onSubmit, onClose, size }) {
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
  React.useEffect(() => {
    if (!errField) return;
    const el = document.getElementById("ff-" + errField);
    if (el) { try { el.scrollIntoView({ block: "center", behavior: "smooth" }); el.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
  }, [errField]);
  if (!open) return null;
  const set = (name, val) => setValues((s) => ({ ...s, [name]: val }));
  const fail = (name, message) => { setErrField(name); setErr(message); };

  async function submit() {
    setErr(""); setErrField(null);
    const body = {};
    for (const f of (fields || [])) {
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
          if (!(f.options || []).length) { fail(f.name, f.label + ": 선택할 수 있는 항목이 없습니다, 다시 시도하거나 취소하세요."); return; }
          fail(f.name, f.label + "을(를) 선택하세요."); return;
        }
        body[f.name] = val === "" ? null : val; continue;
      }  // 빈 선택("없음")은 null로 보내 기존 값을 지운다.
      else { val = val == null ? "" : String(val); if (f.required && !val.trim()) { fail(f.name, f.label + "을(를) 입력하세요."); return; } if (val !== "") body[f.name] = val; else if (hadValue) body[f.name] = null; }
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
      // 백엔드가 검증 실패 사유를 details로 함께 보낼 때가 있다(예: 비밀번호 정책 위반).
      // details가 {loc,msg} 객체 배열일 수도 있어 그대로 join하면 "[object Object]"가 샌다.
      const details = e.body && e.body.error && Array.isArray(e.body.error.details) ? e.body.error.details : null;
      const detailTexts = (details || []).map((d) => (d && typeof d === "object" ? (d.msg || JSON.stringify(d)) : d));
      const msg = [e.message || "저장하지 못했습니다.", ...detailTexts].filter(Boolean).join(" ");
      setErr(msg); setBusy(false); return;
    }
    setBusy(false);
  }

  const sz = size || ((fields || []).length > 5 ? "lg" : "md");
  const footer = <ModalFooter onCancel={requestClose} onSubmit={submit} submitLabel={submitLabel || "저장"} busy={busy} />;
  return (
    <Modal open={open} onClose={requestClose} title={title} size={sz} footer={footer}>
      {/* 필드를 <form>으로 감싸 Enter가 자연스럽게 제출되게 한다(textarea/json은 여러 줄 입력을
          위해 기본 Enter 동작 유지). */}
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {err ? <MuiAlert severity="error" className="k-form-err" sx={{ mb: 2.5 }} role="alert">{err}</MuiAlert> : null}
        {(fields || []).map((f) => <FormField key={f.name} field={f} value={values[f.name]} invalid={errField === f.name} onChange={(val) => set(f.name, val)} />)}
        {/* 화면에 보이지 않는 제출 버튼 — 실제 저장 버튼은 Dialog footer(별도 DOM 트리)에 있어
            이 <form> 안에 없다. type="submit"이 하나도 없으면 브라우저에 따라 단일 텍스트
            입력에서 Enter가 폼을 제출하지 않는다. */}
        <button type="submit" className="sr-only" tabIndex={-1} aria-hidden="true" />
      </form>
    </Modal>
  );
}
// 하위호환 별칭 — 기존 호출부(FormDrawer/FormDialog/Drawer/DialogFooter)는 그대로 두되 전부 중앙 모달로 동작.
export const FormDrawer = FormModal;
export const FormDialog = FormModal;
export const Drawer = Modal;
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
 * aria: 정보/성공은 polite, 오류는 role="alert"(즉시 낭독). */
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
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <MuiSnackbar
        open={toasts.length > 0}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        sx={{ maxWidth: "min(92vw, 30rem)" }}
      >
        <Stack gap={1} sx={{ width: "100%" }} aria-live="polite" aria-atomic="false">
          {toasts.map((t) => (
            <MuiAlert
              key={t.id}
              severity={TONE_SEVERITY[t.kind] || (t.kind === "error" ? "error" : t.kind === "success" ? "success" : "info")}
              variant="filled"
              role={t.kind === "error" ? "alert" : undefined}
              onClose={() => dismiss(t.id)}
              sx={{ width: "100%" }}
            >
              {t.message}
            </MuiAlert>
          ))}
        </Stack>
      </MuiSnackbar>
    </ToastCtx.Provider>
  );
}
export function useToast() { return React.useContext(ToastCtx); }

/* 페이지 헤더 — 빵부스러기→제목 순서와 간격을 한곳에서 정한다.
 * crumbRoot: 빵부스러기 접두어(기본 '관리자'). 사용자 대면 화면은 다른 뿌리를 넘기거나
 *   area를 비워 빵부스러기 자체를 숨길 수 있다.
 * spot: 섹션 일러스트 키(lib/assets.js의 SPOT). 큰 화면에서만 보인다 — 4K에서 남는 폭을
 *   의미 있는 밀도로 채우는 수단이기도 하다. 자산 8종이 있는데 안 쓰이고 있었다. */
export function PageHeader({ area, title, actions, crumbRoot = "관리자", spot }) {
  const spotSrc = spot && SPOT[spot] ? SPOT[spot] : null;
  return (
    <Box
      className="k-page-head"
      sx={{ display: "flex", alignItems: "flex-end", gap: 3, flexWrap: "wrap", mb: 3 }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        {area ? (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontWeight: 650 }}>
            {crumbRoot ? crumbRoot + " › " : ""}{area}
          </Typography>
        ) : null}
        <Typography variant="h4" component="h1" sx={{ mt: area ? 0.5 : 0 }}>{title}</Typography>
      </Box>
      {spotSrc ? (
        <Box
          component="img" src={spotSrc} alt="" aria-hidden="true" loading="lazy" decoding="async"
          sx={{ display: { xs: "none", lg: "block" }, height: { lg: 96, xxl: 128, uhd: 160 }, width: "auto", order: 2 }}
        />
      ) : null}
      {actions ? <Box className="k-page-actions" sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>{actions}</Box> : null}
    </Box>
  );
}
