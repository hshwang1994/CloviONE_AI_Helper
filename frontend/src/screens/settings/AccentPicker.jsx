import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Card, SectionTitle } from "../../ui/kit.jsx";
import { ACCENT_PRESETS, CONTROL, FONT_SIZE, FONT_WEIGHT, RADIUS, normalizeAccent, remPx } from "../../ui/theme.js";
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
    <Card>
      {/* 판 제목은 다른 판과 같은 부품(`SectionTitle`)이다 — 예전에는 여기만 h6 에 글자 크기를 손으로 얹었다. */}
      <SectionTitle
        component="h2" title="화면 강조색"
        help={<>버튼과 링크, 선택 표시에 쓰는 색입니다. <strong>이 브라우저에만</strong> 저장되며 다른 사람 화면은 바뀌지 않습니다.</>}
      />
      {/* 칩은 **컨트롤 높이 하나**다(34). 예전에는 40 에 2px 테두리라 이 판만 다른 리듬으로
          서 있었다 — 같은 판에 있는 「시간 저장」이나 「다시 보기」와 키가 달랐다.
          고른 것만 **면**을 갖는다: 테두리 두께로 고름을 말하면 칩들이 서로 1px 씩 어긋나
          한 줄이 물결친다. 면과 체크와 굵기 셋이 함께 말하므로 색만으로 나르지 않는다. */}
      <Box role="group" aria-label="화면 강조색" sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
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
              /* 높이·모서리는 토큰이다 — `minHeight: 44`·`borderRadius: "10px"` 리터럴이 4K 레버를 안 탔다. */
              sx={{
                display: "inline-flex", alignItems: "center", gap: 1, px: 1.5,
                height: remPx(CONTROL.button),
                cursor: "pointer", font: "inherit",
                color: selected ? "text.primary" : "text.secondary",
                bgcolor: selected ? "background.inset" : "background.plate",
                border: 1, borderStyle: "solid", borderColor: selected ? "primary.main" : "divider",
                borderRadius: `${RADIUS.sm}px`,
                "&:hover": { borderColor: "primary.main" },
              }}
            >
              <Box
                aria-hidden="true"
                /* minWidth를 함께 준다 — 폭이 빠지면 원이 테두리만 남은 2px 세로선으로 찌부러진다
                   (색 견본이 사라지면 이 선택기는 글자만 남아 의미의 절반을 잃는다). */
                sx={{ width: "0.875rem", minWidth: "0.875rem", height: "0.875rem", borderRadius: "50%", bgcolor: value, border: 1, borderColor: "divider", flex: "none" }}
              />
              <Box component="span" sx={{ fontSize: FONT_SIZE.caption, fontWeight: selected ? FONT_WEIGHT.semibold : FONT_WEIGHT.regular }}>{name}</Box>
              {/* QAH-07 — dark 모드 대비 미달(최저 2.81) 실측, primary.dark로 교체. */}
              {selected ? <Box component="span" aria-hidden="true" sx={{ fontWeight: FONT_WEIGHT.extrabold, color: "primary.dark" }}>✓</Box> : null}
              {selected ? <span className="sr-only">(현재 색)</span> : null}
            </Box>
          );
        })}
      </Box>
    </Card>
  );
}
