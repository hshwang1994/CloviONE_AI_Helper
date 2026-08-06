import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { useAuth } from "./auth.jsx";

/* 스코프 바 — **지금 보고 있는 범위를 화면에 적는다** (S4 / A8, 기준 목업의 `관리 범위` 줄).
 *
 * 7단계에서 범위를 실제로 걸기 시작하면서 목록이 좁아졌다. 그런데 **왜 좁아졌는지 화면이
 * 말하지 않으면** 사용자는 "왜 이것만 보이지" 를 알 수 없고, 그건 결함으로 신고된다.
 * 계획서가 이 줄을 요구한 이유가 그것이다:
 *
 * > 화면에 "지금 보는 범위: ClovirONE팀" 을 **항상 표시**하고, 권한이 있으면 그 자리에서 넓힌다.
 * > 범위를 화면에 안 적으면 "왜 이것만 보이지" 가 된다.
 *
 * **범위를 바꾸는 선택기는 아직 두지 않는다.** 그걸 두려면 "이 사람이 넓힐 수 있는 범위
 * 목록" 을 주는 API 가 필요하고(권한 판정이 서버에 있어야 한다), 그건 아직 없다.
 * 없는 컨트롤을 그려 두면 눌러 봐야 아무 일도 안 나는 버튼이 하나 더 생긴다 —
 * 이 저장소가 X5(조직 정지가 아무 일도 안 한다)에서 이미 겪은 모양이다.
 *
 * 전체 범위인 사람에게는 **띄우지 않는다.** 모든 화면 위에 "전체 포털" 이 한 줄 붙으면
 * 그건 정보가 아니라 소음이다. 좁혀진 사람에게만 뜻이 있다.
 */
export const SCOPE_TEXT = {
  dept: "내 팀",
  org: "내 조직",
};

export function scopeSummary(me) {
  if (!me) return null;
  const role = me.role;
  // 일반 사용자는 규칙으로 자기 팀만 본다(`core/scope.py::build_scope`). 부서가 없으면
  // 좁혀지지 않으므로(폴백) 그때는 띄우지 않는다 — 안 좁혀졌는데 좁혔다고 하면 거짓말이다.
  if (role === "user") {
    return me.department ? { label: "내 팀", detail: me.department } : null;
  }
  const scope = me.admin_scope || "global";
  if (scope === "dept") {
    return { label: "관리 범위", detail: me.department || "지정된 부서 없음" };
  }
  if (scope === "org") {
    return { label: "관리 범위", detail: "내 조직" };
  }
  return null;   // global — 소음이라 안 띄운다
}

export function ScopeBar() {
  const auth = useAuth();
  const summary = scopeSummary(auth.data && auth.data.user ? auth.data.user : auth.data);
  if (!summary) return null;
  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{
        display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap",
        px: 2, py: 0.75, mb: 2, borderRadius: "12px",
        bgcolor: (t) => alpha(t.palette.primary.main, 0.07),
        border: 1, borderColor: (t) => alpha(t.palette.primary.main, 0.18),
        fontSize: "0.8125rem",
      }}
    >
      <Typography component="span" sx={{ fontWeight: 750, fontSize: "0.75rem", color: "primary.dark" }}>
        {summary.label}
      </Typography>
      <Typography component="span" sx={{ fontSize: "0.8125rem" }}>{summary.detail}</Typography>
      <Box sx={{ flex: 1 }} />
      <Typography component="span" sx={{ fontSize: "0.75rem", color: "text.secondary" }}>
        이 범위 밖의 항목은 목록에 나오지 않습니다.
      </Typography>
    </Box>
  );
}
