import React from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Typography from "@mui/material/Typography";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useToast } from "../ui/kit.jsx";
import { applyTheme, readTheme, storeTheme, clearBootTheme } from "./theme-store.js";
import { clearBootAccent, useThemeMode } from "../ui/ThemeModeProvider.jsx";

/* 사용자 메뉴 — 이름/아바타를 누르면 내 프로필·비밀번호 변경·로그아웃.
 * 로그아웃이 없던 것이 큰 공백이었다(공용 PC 보안).
 *
 * **다크/라이트 전환은 여기 없다.** 상단바 아이콘 버튼(AppShell 의 `ThemeToggle`)이 정본이다.
 * 예전에는 두 곳에 다 있었는데, 두 벌이 같은 상태를 **따로** 들고 있었다: 상단바는
 * `<html data-theme>` 를 읽고(ThemeModeProvider), 이 메뉴는 자기 React 상태를 들었다.
 * 그래서 상단바로 바꾸면 이 메뉴의 라벨이 낡은 채 남아, 메뉴를 열면 방금 켠 모드를 다시
 * 켜라고 적혀 있었다. "좁은 화면에서는 상단바 아이콘이 접히니 두 경로가 다 필요하다" 는
 * 예전 근거도 사실이 아니었다 — 그 버튼에는 폭에 따른 숨김이 걸려 있지 않다.
 *
 * 예전에는 팝오버 포커스 트랩·바깥 클릭 닫기·트리거 복귀를 직접 구현했다. MUI Menu가 셋 다
 * 정확히 처리하므로 그 코드는 지웠다 — 직접 구현이 남아 있으면 MUI와 이중으로 걸려
 * '프로필을 열면 두 컴포넌트가 포커스를 뺏고 뺏기는' 예전 경쟁 상태가 다시 난다.
 *
 * '내 프로필'은 예전에 이 파일 안의 작은 읽기 전용 모달이었다. 그 모달은 "활성 세션 3개"라고
 * 알려 주면서 정작 끊을 방법이 없었다 — 안내만 있고 통제로 이어지지 않는 화면이었다.
 * 이제 실제 화면(screens/Profile.jsx)이 그 일을 하므로 여기서는 **이동만** 한다. 같은 정보를
 * 두 곳에서 그리면 언젠가 한쪽만 고쳐져 서로 다른 말을 한다. */

export function UserMenu({ name, userId, avatarUrl }) {
  const [anchor, setAnchor] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const open = Boolean(anchor);
  const nav = useNavigate();
  const toast = useToast();
  const { identifyAccentUser } = useThemeMode();

  React.useEffect(() => {
    if (!userId) return;
    /* 이 계정 전용으로 저장된 테마가 있으면(공용 PC에서 이전 사용자와 선택이 다를 수 있다)
       부팅 시 적용된 계정 구분 없는 테마 대신 그 값을 따른다.
       이 복원은 계정을 아는 첫 지점이 여기라서 남는다 — 그리는 컨트롤은 없다.
       비교 대상이 React 상태가 아니라 `<html data-theme>` 인 이유: 그것이 정본이고,
       여기서 사본을 들면 다시 두 벌이 된다(위 주석의 그 결함). */
    const saved = readTheme(userId, { onlyAccount: true });
    if (saved) {
      if (saved !== document.documentElement.getAttribute("data-theme")) applyTheme(saved);
      storeTheme(saved, userId);
    }
    // 강조색도 같은 이유로 같은 자리에서 복원한다 - ThemeModeProvider는 AuthProvider
    // 바깥에 마운트돼 있어 userId를 prop으로 받을 수 없다(ui/ThemeModeProvider.jsx 참고).
    // 이후 setAccent 호출(강조색 선택 UI)도 이 호출로 알려 준 계정의 키에 저장된다.
    identifyAccentUser(userId);
  }, [userId, identifyAccentUser]);

  async function logout() {
    setBusy(true);
    // 계정 구분 없는 테마 키는 로그아웃 때 지운다 — 공용/키오스크 PC에서 다음 사용자가
    // 로그인 화면부터 이전 사용자의 테마를 물려받지 않게. 계정별 키는 남겨 본인 재로그인 시 복원.
    clearBootTheme();
    // 강조색도 같은 이유로 계정 구분 없는 키만 지운다(ui/ThemeModeProvider.jsx 참고).
    clearBootAccent();
    try {
      await api("/logout", { method: "POST", body: {} });
    } catch (e) {
      // 401(세션이 이미 없음)만 "그래도 로그인으로" 를 정당화한다 - 그때는 쿠키가 이미
      // 죽었으니 이동해도 안전하다. 5xx·망 순단처럼 세션이 **아직 살아 있을 수 있는**
      // 실패까지 무조건 이동시키면, 쿠키가 살아 있는 채로 `GET /login` 이 303 으로 `/` 로
      // 되돌려 "로그아웃 중…" 을 보고 기다렸다가 대시보드로 돌아오는데 아무 설명도 없다
      // (Banners.jsx 의 대리 보기 종료 실패와 같은 판단 - 조용히 삼키면 사용자가 로그아웃된
      // 줄 알고 자리를 뜬다).
      if (e && e.status === 401) {
        window.location.href = "/login";
        return;
      }
      setBusy(false);
      toast((e && e.message) || "로그아웃하지 못했습니다. 다시 시도해 주세요.", "error");
      return;
    }
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
        {/* 프로필 사진이 있으면 그것을, 없으면 이니셜을. src 가 없거나 로드에 실패하면
            MUI Avatar 가 자식(이니셜)으로 자동 폴백하므로 깨진 이미지가 뜨지 않는다. */}
        <Avatar
          src={avatarUrl || undefined}
          sx={{ width: 30, height: 30, fontSize: "0.8125rem", bgcolor: "rgba(255,255,255,.22)" }}
          aria-hidden="true"
        >
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
        <MenuItem onClick={() => { setAnchor(null); nav("/profile"); }}>내 프로필</MenuItem>
        <MenuItem onClick={() => { setAnchor(null); nav("/my-stats"); }}>내 업무량</MenuItem>
        <MenuItem onClick={() => { setAnchor(null); nav("/activity"); }}>내 활동</MenuItem>
        <MenuItem component="a" href="/change-password">비밀번호 변경</MenuItem>
        <Divider />
        <MenuItem disabled={busy} onClick={logout} sx={{ color: "error.main" }}>
          {busy ? "로그아웃 중…" : "로그아웃"}
        </MenuItem>
      </Menu>
    </>
  );
}
