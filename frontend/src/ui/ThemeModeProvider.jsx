import React from "react";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { ACCENT_PRESETS, createClovirTheme, normalizeAccent } from "./theme.js";

/* MUI 테마를 앱에 붙이는 지점.
 *
 * 다크/라이트의 원본 상태는 여전히 app/App.jsx가 갖고 있다(localStorage + <html data-theme>).
 * 여기서 상태를 새로 만들면 출처가 둘이 되어 반드시 어긋나므로, 대신 <html>의 data-theme
 * 속성을 MutationObserver로 **따라간다**. 화면 코드를 한 줄도 건드리지 않고 MUI를 얹기 위한
 * 다리이며, 셸을 MUI로 재작성할 때(A2) 상태를 이쪽으로 옮기고 옵저버를 걷어낸다.
 *
 * 액센트 색은 사용자별 취향이라 테마와 같은 방식(localStorage)으로 둔다. 서버 설정으로
 * 만들면 한 사람의 취향이 전원에게 적용된다.
 *
 * 계정별 키(app/theme-store.js의 accountKey와 같은 모양)를 쓴다 — 그 파일이 이미 겪은 문제를
 * 여기서도 그대로 반복하지 않기 위해서다: 키가 기기 하나에 하나뿐이면 공용/키오스크 PC에서
 * 다음 로그인 사용자가 이전 사람이 고른 색을 그대로 물려받는다. 이 컴포넌트는
 * app/App.jsx보다 먼저(위에서) 마운트되어 **부팅 시점엔 userId를 알 방법이 없다**
 * (useAuth()는 그 안쪽 AuthProvider 안에서만 쓸 수 있다) - 그래서 userId를 prop으로
 * 받는 대신, 계정을 아는 첫 지점(app/UserMenu.jsx, 테마 복원과 같은 자리)이
 * `useThemeMode().identifyAccentUser(userId)`를 불러 **안에서** 알려 준다. 로그아웃 시
 * 계정 무관 키를 지우는 것은 app/UserMenu.jsx의 clearBootTheme() 호출부가 함께 한다
 * (clearBootAccent, 이 파일 하단에서 내보낸다). */

const ACCENT_KEY = "clovirassist_accent";
const ThemeModeCtx = React.createContext({
  mode: "light",
  accent: ACCENT_PRESETS[0],
  setAccent: () => {},
  identifyAccentUser: () => {},
});

function readDomMode() {
  if (typeof document === "undefined") return "light";
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function accentAccountKey(userId) {
  return userId ? ACCENT_KEY + ":" + userId : ACCENT_KEY;
}

/* 부팅 시점(userId 모름)엔 계정 무관 키만 본다 - 계정별 값은 로그인 확인 뒤
 * identifyAccentUser()가 따로 적용한다(아래). */
function readStoredAccent() {
  try {
    return normalizeAccent(window.localStorage.getItem(ACCENT_KEY));
  } catch (e) {
    return normalizeAccent(null);
  }
}

/* app/theme-store.js의 clearBootTheme과 같은 계약 — 로그아웃 때 계정 무관 키만 지운다.
 * 계정별 키는 남겨 본인 재로그인 시 복원한다. */
export function clearBootAccent() {
  try { window.localStorage.removeItem(ACCENT_KEY); } catch (e) { /* ignore */ }
}

export function ThemeModeProvider({ children }) {
  const [mode, setMode] = React.useState(readDomMode);
  const [accent, setAccentState] = React.useState(readStoredAccent);
  // 부팅 시점엔 아무도 모른다(null = 계정 무관). identifyAccentUser()가 로그인 확인 뒤
  // 채운다. setAccent도 이 상태를 봐야 "지금 로그인한 계정"의 키에 저장한다 — prop으로는
  // 이 값이 절대 안 들어온다(이 컴포넌트는 AuthProvider 바깥에 있다).
  const [accentUserId, setAccentUserId] = React.useState(null);

  React.useEffect(() => {
    const root = document.documentElement;
    const sync = () => setMode(readDomMode());
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  /* 계정을 아는 첫 지점(UserMenu.jsx)이 부른다 - 그 계정의 저장된 색이 있으면 적용하고,
   * 이후 setAccent 호출도 이 계정의 키로 가게 기억해 둔다. */
  const identifyAccentUser = React.useCallback((userId) => {
    setAccentUserId(userId || null);
    if (!userId) return;
    try {
      const perAccount = window.localStorage.getItem(accentAccountKey(userId));
      if (!perAccount) return;
      const next = normalizeAccent(perAccount);
      setAccentState(next);
      window.localStorage.setItem(ACCENT_KEY, next);
    } catch (e) {
      /* 시크릿 모드/저장소 차단 */
    }
  }, []);

  const setAccent = React.useCallback((value) => {
    const next = normalizeAccent(value);
    setAccentState(next);
    try {
      window.localStorage.setItem(accentAccountKey(accentUserId), next);
      // 부팅(계정 무관) 키에도 미러링 — theme-store.js의 storeTheme과 같은 이유다. 로그아웃
      // 때 clearBootAccent가 이 키를 지우므로 다음 로그인 사용자에게 넘어가지 않는다.
      window.localStorage.setItem(ACCENT_KEY, next);
    } catch (e) {
      /* 시크릿 모드/저장소 차단 — 색은 이번 세션에만 적용되고 앱은 계속 동작한다 */
    }
  }, [accentUserId]);

  const theme = React.useMemo(() => createClovirTheme(mode, accent), [mode, accent]);
  const ctx = React.useMemo(
    () => ({ mode, accent, setAccent, identifyAccentUser }),
    [mode, accent, setAccent, identifyAccentUser],
  );

  return (
    <ThemeModeCtx.Provider value={ctx}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ThemeModeCtx.Provider>
  );
}

export function useThemeMode() {
  return React.useContext(ThemeModeCtx);
}
