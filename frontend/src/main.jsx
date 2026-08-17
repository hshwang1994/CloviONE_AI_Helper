import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
/* root.css가 먼저다 — 루트 폰트사이즈(4K 스케일 레버)를 정한다.
 * 나머지 legacy CSS는 아직 살아 있다: 셸(global.css)은 A2에서, 화면 스타일(screens.css)과
 * 손으로 쓴 폼 마크업(kit.css)은 각 화면 웨이브에서 걷어낸다. MUI의 Emotion 스타일은
 * 런타임에 <head> 끝에 주입되므로 같은 특이도에서는 MUI가 이긴다 — 전환 중 의도한 순서다. */
import "./styles/root.css";
import "./styles/tokens.css";
import "./styles/global.css";
import "./ui/kit.css";
import "./styles/screens.css";
import { App } from "./app/App.jsx";
import { ConfirmProvider, ToastProvider } from "./ui/kit.jsx";
import { ThemeModeProvider } from "./ui/ThemeModeProvider.jsx";
import { shouldRetryQuery } from "./lib/queryRetry.js";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30 * 1000, retry: shouldRetryQuery } },
});

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <App />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
