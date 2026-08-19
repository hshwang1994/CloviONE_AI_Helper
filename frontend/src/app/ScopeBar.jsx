import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { useLocation } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import { isScopeEnforcedRoute } from "./navConfig.js";
import { PATH_SEP } from "../ui/OrgPath.jsx";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "../ui/theme.js";

/* 스코프 바 — **지금 보고 있는 범위를 화면에 적는다** (S4 / A8).
 *
 * 범위를 실제로 걸기 시작하면서 목록이 좁아졌다. 그런데 **왜 좁아졌는지 화면이 말하지
 * 않으면** 사용자는 "왜 이것만 보이지" 를 알 수 없고, 그건 결함으로 신고된다.
 *
 * ## 0060 에서 바뀐 것
 *
 * 1. **소속이 미지정이면 반드시 말한다.** 그 계정은 조직 데이터를 아무것도 못 보는데,
 *    증상이 "권한 없음" 이 아니라 "목록이 비어 있음" 이라 이 안내가 없으면 원인을 찾을
 *    방법이 없다. 예전에는 그 상태가 곧 전역(전부 보임)이라 말할 것이 없었다.
 * 2. **내 소속과 관리 범위를 섞지 않는다.** 관리자가 배정받은 관리 범위와 본인이 속한
 *    부서는 다른 개념이고 다를 수 있다. 상세한 두 줄은 셸의 계정 메뉴가 보여 주고
 *    (`UserMenu.jsx::MyAffiliation`), 여기서는 **지금 이 목록이 왜 좁은가**만 말한다.
 * 3. 조회 범위가 줄기(조상 ∪ 자기 ∪ 후손)라 "내 팀" 이라는 말이 더 이상 정확하지 않다 —
 *    상위 부서의 공통 업무도 함께 보이기 때문이다. 문구를 그에 맞춘다.
 *
 * **전체 범위인 사람에게는 띄우지 않는다.** 모든 화면 위에 "전체 포털" 이 한 줄 붙으면
 * 그건 정보가 아니라 소음이다 — 좁혀진 사람에게만 뜻이 있다.
 */

function pathText(path) {
  return (path || []).map((n) => n.name).filter(Boolean).join(PATH_SEP);
}

/* 관리 범위가 목록을 좁히는 화면. 나머지 범위 화면은 **조회 범위**(내 소속)가 좁힌다.
 *
 * 둘을 갈라 말하는 것이 이 컴포넌트의 존재 이유다. 관리자가 `/users` 에서 보는 좁음과
 * `/projects` 에서 보는 좁음은 서로 다른 축이고(관리 범위 vs 내 소속), 한 문구로 뭉치면
 * 부서 관리자가 자기 소속을 관리 범위로 착각한다. */
const MANAGEMENT_SCOPED_PATHS = [
  "/users", "/offboarding", "/organizations", "/departments", "/org-tree",
];

function isManagementRoute(pathname) {
  return MANAGEMENT_SCOPED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
}

/** 이 사람에게 **이 화면에서** 무엇을 말해야 하는가. `null` 이면 아무것도 안 띄운다. */
export function scopeSummary(me, pathname = "") {
  if (!me) return null;
  const path = me.department_path || [];
  const mgmt = me.management || {};

  // 관리 화면에서는 **관리 범위**가 목록을 좁힌다.
  if (isManagementRoute(pathname)) {
    if (mgmt.kind === "global" || !mgmt.kind) return null;   // 좁혀진 것이 없다 — 소음이다
    if (mgmt.kind === "org") {
      return {
        label: "관리 범위",
        detail: (mgmt.org && mgmt.org.name) || "지정된 조직 없음",
        tone: mgmt.org ? "info" : "warn",
      };
    }
    if (mgmt.kind === "dept") {
      const text = pathText(mgmt.path);
      return {
        label: "관리 범위",
        detail: text || "지정된 부서 없음",
        tone: text ? "info" : "warn",
      };
    }
    return {
      label: "관리 범위 없음",
      detail: "관리할 수 있는 대상이 지정되지 않았습니다.",
      tone: "warn",
    };
  }

  // 소속 미지정 — 가장 먼저, 가장 크게 말해야 하는 상태다. 그 계정은 조직 데이터를
  // 아무것도 못 보는데, 증상이 "목록이 비어 있음" 이라 이 안내가 없으면 원인을 못 찾는다.
  if (!path.length && me.membership_kind === "unassigned" && mgmt.kind !== "global") {
    return {
      label: "소속 미지정",
      detail: "부서 또는 조직 직속이 지정되지 않아 조직 데이터가 보이지 않습니다. 관리자에게 문의하세요.",
      tone: "warn",
    };
  }
  // 조회가 전역이면 좁혀진 것이 없다 — 모든 화면 위의 "전체 포털"은 정보가 아니라 소음이다.
  if (mgmt.kind === "global") return null;

  if (path.length) {
    return { label: "내 소속", detail: pathText(path), tone: "info" };
  }
  if (me.membership_kind === "organization") {
    return { label: "소속", detail: (me.organization && me.organization.name) || "소속 조직", tone: "info" };
  }
  return null;
}

/** 이 화면에서 "범위 밖은 안 보인다" 를 **어떻게** 말할 것인가.
 *
 * 두 축은 좁히는 방향이 다르다:
 *
 *   조회 범위: 줄기 = 조상 ∪ 자기 ∪ 후손 (상위 부서의 공통 업무도 보인다)
 *   관리 범위: 자기 ∪ 후손 **만** (위로 올라가면 위임이 아니라 승격이다)
 *
 * 한 문장으로 뭉치면 한쪽이 거짓말이 된다 — 관리 화면에서 "상위 부서와 하위 부서 밖"
 * 이라고 쓰면 부서 관리자가 상위 부서 사람도 관리할 수 있다고 읽는데, 목록에는 안 나온다.
 */
export function caveatFor(pathname) {
  return isManagementRoute(pathname)
    ? "이 부서와 하위 부서 밖의 항목은 목록에 나오지 않습니다."
    : "상위 부서와 하위 부서 밖의 항목은 목록에 나오지 않습니다.";
}


export function ScopeBar() {
  const auth = useAuth();
  const location = useLocation();
  const summary = scopeSummary(
    auth.data && auth.data.user ? auth.data.user : auth.data,
    location.pathname,
  );
  if (!summary) return null;
  // 범위가 실제로 걸리는 화면에서만 "이 범위 밖은 안 보인다"고 단언한다 — 게시판·놀이·
  // 알림처럼 조직 전체가 보는 화면에서까지 그 문장을 띄우면 그 화면을 여는 순간 거짓말이
  // 된다(navConfig.js::SCOPE_ENFORCED_PATHS 참조).
  const enforced = isScopeEnforcedRoute(location.pathname);
  const warn = summary.tone === "warn";
  /* 두 축은 **좁히는 방향이 다르다** — 한 문장으로 뭉치면 한쪽이 거짓말이 된다.
   *
   *   조회 범위: 줄기 = 조상 ∪ 자기 ∪ 후손 (상위 부서의 공통 업무도 보인다)
   *   관리 범위: 자기 ∪ 후손 **만** (위로 올라가면 위임이 아니라 승격이다)
   *
   * 관리 화면에서 "상위 부서와 하위 부서 밖" 이라고 쓰면 부서 관리자가 상위 부서 사람도
   * 관리할 수 있다고 읽는다. 실제로는 목록에 나오지 않으므로 화면이 거짓말을 한 셈이 된다. */
  const caveat = caveatFor(location.pathname);
  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{
        display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap",
        // 반지름은 토큰에서 온다 — 12px 리터럴은 RADIUS 세 단(6/8/14) 어디에도 없는
        // 네 번째 값이었다(지시 26: 화면마다 숫자를 박지 않는다).
        px: 2, py: 0.75, mb: 2, borderRadius: `${RADIUS.md}px`,
        bgcolor: (t) => alpha(warn ? t.palette.warning.main : t.palette.primary.main, 0.07),
        border: 1,
        borderColor: (t) => alpha(warn ? t.palette.warning.main : t.palette.primary.main, 0.18),
        fontSize: FONT_SIZE.bodySm,
      }}
    >
      <Typography
        component="span"
        sx={{
          fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.caption,
          color: warn ? "warning.dark" : "primary.dark",
        }}
      >
        {summary.label}
      </Typography>
      <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, minWidth: 0 }}>
        {summary.detail}
      </Typography>
      <Box sx={{ flex: 1 }} />
      {enforced && !warn ? (
        <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
          {caveat}
        </Typography>
      ) : null}
    </Box>
  );
}
