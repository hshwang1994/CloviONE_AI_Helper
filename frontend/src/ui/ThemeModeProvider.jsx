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
 */

const ACCENT_KEY = "clovirone_accent";
const ThemeModeCtx = React.createContext({
  mode: "light",
  accent: ACCENT_PRESETS[0],
  setAccent: () => {},
});

function readDomMode() {
  if (typeof document === "undefined") return "light";
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function readStoredAccent() {
  try {
    return normalizeAccent(window.localStorage.getItem(ACCENT_KEY));
  } catch (e) {
    return normalizeAccent(null);
  }
}

export function ThemeModeProvider({ children }) {
  const [mode, setMode] = React.useState(readDomMode);
  const [accent, setAccentState] = React.useState(readStoredAccent);

  React.useEffect(() => {
    const root = document.documentElement;
    const sync = () => setMode(readDomMode());
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  const setAccent = React.useCallback((value) => {
    const next = normalizeAccent(value);
    setAccentState(next);
    try {
      window.localStorage.setItem(ACCENT_KEY, next);
    } catch (e) {
      /* 시크릿 모드/저장소 차단 — 색은 이번 세션에만 적용되고 앱은 계속 동작한다 */
    }
  }, []);

  const theme = React.useMemo(() => createClovirTheme(mode, accent), [mode, accent]);
  const ctx = React.useMemo(() => ({ mode, accent, setAccent }), [mode, accent, setAccent]);

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
