import React from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Typography from "@mui/material/Typography";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import { useAuth } from "./auth.jsx";
import { api } from "../lib/api.js";
import { Badge, ErrorState, Modal, Skeleton } from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { ROLE_KO } from "./navConfig.js";
import { applyTheme, readTheme, storeTheme, clearBootTheme } from "./theme-store.js";

/* 사용자 메뉴 — 이름/아바타를 누르면 테마 전환·내 프로필·비밀번호 변경·로그아웃.
 * 로그아웃이 없던 것이 큰 공백이었다(공용 PC 보안).
 *
 * 예전에는 팝오버 포커스 트랩·바깥 클릭 닫기·트리거 복귀를 직접 구현했다. MUI Menu가 셋 다
 * 정확히 처리하므로 그 코드는 지웠다 — 직접 구현이 남아 있으면 MUI와 이중으로 걸려
 * '프로필을 열면 두 컴포넌트가 포커스를 뺏고 뺏기는' 예전 경쟁 상태가 다시 난다. */

function ProfileModal({ open, onClose }) {
  const auth = useAuth();
  const [data, setData] = React.useState(null);
  const [err, setErr] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  // 이 모달은 react-query가 아니라 수동 fetch라 기성 재조회 함수가 없다. 네트워크 순단·일시적
  // 5xx로 실패했을 때 onRetry가 없으면 버튼 하나 없는 막다른 화면이 된다.
  const [reloadTick, setReloadTick] = React.useState(0);
  React.useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setLoading(true); setErr(null); setData(null);
    api("/api/profile")
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setErr(e); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, reloadTick]);

  const row = (label, value) => (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "10rem 1fr" }, gap: 1, py: 1.25, borderBottom: 1, borderColor: "divider" }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Box sx={{ minWidth: 0 }}>{value}</Box>
    </Box>
  );

  return (
    <Modal open={open} onClose={onClose} title="내 프로필" size="sm">
      {loading ? <Skeleton /> : err ? <ErrorState error={err} onRetry={() => setReloadTick((n) => n + 1)} /> : data ? (
        <Box>
          {row("역할", (() => { const r = data.role || (auth.data && auth.data.role); return r ? (ROLE_KO[r] || r) : "-"; })())}
          {row("부서", data.department || "-")}
          {row("직책", data.title || "-")}
          {row("마지막 로그인", data.last_login_at ? fmtDateTime(data.last_login_at) : "-")}
          {row("현재 활성 세션", data.active_session_count != null ? data.active_session_count + "개" : "-")}
          {/* 세션 수가 예상보다 많으면 계정 침해 신호일 수 있다. 본인 계정용 세션 해제
              자기서비스는 아직 없으니(백로그) 최소한 무엇을 해야 하는지는 알려주고,
              그 링크를 여기 바로 심는다 — 안내만 있고 통제로 이어지지 않으면 있으나 마나다. */}
          {data.active_session_count != null && data.active_session_count > 1 ? (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              숫자가 예상보다 많다면 <Box component="a" href="/change-password" sx={{ color: "primary.main" }}>비밀번호를 변경</Box>하거나 관리자에게 문의하세요.
            </Typography>
          ) : null}
          {row("Notion 연결 상태", data.notion_mapping_status ? <Badge value={data.notion_mapping_status} /> : "-")}
        </Box>
      ) : null}
    </Modal>
  );
}

export function UserMenu({ name, userId }) {
  const [anchor, setAnchor] = React.useState(null);
  const [theme, setTheme] = React.useState(() => readTheme());
  const [busy, setBusy] = React.useState(false);
  const [profileOpen, setProfileOpen] = React.useState(false);
  const open = Boolean(anchor);

  React.useEffect(() => {
    if (!userId) return;
    // 이 계정 전용으로 저장된 테마가 있으면(공용 PC에서 이전 사용자와 선택이 다를 수 있다)
    // 부팅 시 적용된 계정 구분 없는 테마 대신 그 값을 따른다.
    const saved = readTheme(userId, { onlyAccount: true });
    if (saved && saved !== theme) { setTheme(saved); applyTheme(saved); }
    if (saved) storeTheme(saved, userId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    storeTheme(next, userId);
    applyTheme(next);
  }

  async function logout() {
    setBusy(true);
    // 계정 구분 없는 테마 키는 로그아웃 때 지운다 — 공용/키오스크 PC에서 다음 사용자가
    // 로그인 화면부터 이전 사용자의 테마를 물려받지 않게. 계정별 키는 남겨 본인 재로그인 시 복원.
    clearBootTheme();
    try { await api("/logout", { method: "POST", body: {} }); } catch (e) { /* 세션이 이미 없어도 로그인으로 */ }
    window.location.href = "/login";
  }

  const label = name || "관리자";
  return (
    <>
      <Button
        onClick={(e) => setAnchor(e.currentTarget)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label + " 메뉴"}
        color="inherit"
        sx={{ minWidth: 0, gap: 1, px: 1, textTransform: "none" }}
      >
        {/* 좁은 화면에서는 이름을 숨긴다. 버튼 자체에 aria-label이 있어 접근 가능한 이름은 유지된다
            — 예전엔 이름이 유일한 텍스트 자식이라 모바일에서 이름이 통째로 사라졌다. */}
        <Box component="span" sx={{ display: { xs: "none", md: "inline" }, fontWeight: 700 }} aria-hidden="true">{label}</Box>
        <Avatar sx={{ width: 30, height: 30, fontSize: "0.8125rem", bgcolor: "rgba(255,255,255,.22)" }} aria-hidden="true">
          {label[0]}
        </Avatar>
      </Button>
      <Menu
        anchorEl={anchor}
        open={open}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { minWidth: 200 } } }}
      >
        <MenuItem onClick={() => { toggleTheme(); }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            {theme === "dark" ? <LightModeOutlinedIcon fontSize="small" /> : <DarkModeOutlinedIcon fontSize="small" />}
            {theme === "dark" ? "라이트 모드" : "다크 모드"}
          </Box>
        </MenuItem>
        <MenuItem onClick={() => { setAnchor(null); setProfileOpen(true); }}>내 프로필</MenuItem>
        <MenuItem component="a" href="/change-password">비밀번호 변경</MenuItem>
        <Divider />
        <MenuItem disabled={busy} onClick={logout} sx={{ color: "error.main" }}>
          {busy ? "로그아웃 중…" : "로그아웃"}
        </MenuItem>
      </Menu>
      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
    </>
  );
}
