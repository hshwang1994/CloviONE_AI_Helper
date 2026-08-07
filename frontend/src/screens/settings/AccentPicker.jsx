import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Card } from "../../ui/kit.jsx";
import { ACCENT_PRESETS, normalizeAccent } from "../../ui/theme.js";
import { useThemeMode } from "../../ui/ThemeModeProvider.jsx";
import { ACCENT_NAMES } from "./settingsRegistry.js";

/* 화면 강조색 — 다크/라이트 모드와 같은 성격의 '이 브라우저에만' 저장되는 개인 취향이다
 * (ui/ThemeModeProvider.jsx가 localStorage에 넣는다). 서버 설정으로 만들면 한 사람의 취향이
 * 전원에게 적용되므로 위의 설정 표(시스템 값)와는 일부러 분리해 둔다.
 *
 * 선택 표시를 색만으로 하지 않는다(WCAG 1.4.1) — 이름 굵게 + 체크 글리프 + 테두리 강조를 함께 준다. */
export function AccentPicker() {
  const { accent, setAccent } = useThemeMode();
  const current = normalizeAccent(accent);
  return (
    <Card sx={{ mb: 2.5 }}>
      <Typography component="h2" variant="h6" sx={{ fontSize: "1.0625rem" }}>화면 강조색</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2, maxWidth: "70ch" }}>
        버튼, 링크, 선택 표시에 쓰는 색입니다. 밝게/어둡게 설정과 마찬가지로 <strong>지금 쓰는 브라우저에만</strong> 저장되는 개인 설정이라,
        다른 사람이 보는 화면은 바뀌지 않습니다(위 표의 시스템 설정과 다릅니다).
      </Typography>
      <Box role="group" aria-label="화면 강조색" sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
        {ACCENT_PRESETS.map((hex) => {
          const value = normalizeAccent(hex);
          const selected = value === current;
          const name = ACCENT_NAMES[value] || value;
          return (
            <Box
              key={value}
              component="button"
              type="button"
              aria-pressed={selected}
              onClick={() => setAccent(value)}
              sx={{
                display: "flex", alignItems: "center", gap: 1, px: 2, py: 1, minHeight: 44,
                cursor: "pointer", font: "inherit", color: "inherit", bgcolor: "transparent",
                border: 2, borderStyle: "solid", borderColor: selected ? "primary.main" : "divider",
                borderRadius: "10px",
                "&:hover": { borderColor: "primary.main" },
              }}
            >
              <Box
                aria-hidden="true"
                /* minWidth를 함께 준다 — 폭이 빠지면 원이 테두리만 남은 2px 세로선으로 찌부러진다
                   (색 견본이 사라지면 이 선택기는 글자만 남아 의미의 절반을 잃는다). */
                sx={{ width: "1.25rem", minWidth: "1.25rem", height: "1.25rem", borderRadius: "50%", bgcolor: value, border: 1, borderColor: "divider", flex: "none" }}
              />
              <Box component="span" sx={{ fontSize: "0.875rem", fontWeight: selected ? 780 : 550 }}>{name}</Box>
              {selected ? <Box component="span" aria-hidden="true" sx={{ fontWeight: 800, color: "primary.main" }}>✓</Box> : null}
              {selected ? <span className="sr-only">(현재 색)</span> : null}
            </Box>
          );
        })}
      </Box>
    </Card>
  );
}
