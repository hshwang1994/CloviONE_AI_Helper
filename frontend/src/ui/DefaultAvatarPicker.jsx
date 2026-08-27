import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { Button } from "./kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "./theme.js";
import {
  AVATAR_VARIANT_MAX,
  DEFAULT_AVATAR_STYLES,
  DEFAULT_AVATAR_STYLE_LABELS,
  DefaultAvatar,
  autoAvatarKey,
  formatAvatarKey,
  parseAvatarKey,
} from "./DefaultAvatar.jsx";

/* 기본 아바타 고르기 — **후보가 여덟 개로 끝나지 않는다.**
 *
 * 스타일 다섯에 변형 1,000 이면 조합이 5,000 가지다. 그것을 한 화면에 다 깔 수는 없고,
 * 깔 이유도 없다 — 사람이 고를 때 실제로 하는 일은 「마음에 드는 게 보일 때까지 넘기는
 * 것」이다. 그래서 한 번에 스타일별 한 줄씩 보여 주고, 마음에 안 들면 **다시 만든다**.
 *
 * 다시 만드는 값이 난수가 아니라 **회차 번호**인 것이 이 부품의 요점이다. 같은 회차는
 * 언제 눌러도 같은 후보를 낸다 — 뒤로 갔다 오면 방금 본 얼굴이 사라지는 목록은 고를 수가
 * 없다. 회차는 화면 안에서만 세고 저장하지 않는다: 저장되는 것은 사람이 실제로 고른
 * 값 하나뿐이다.
 */

/* 스타일마다 한 줄에 몇 개. 다섯 스타일 × 여섯이면 서른 개가 한 화면에 들어가고,
 * 그 정도면 「마음에 드는 게 없다」를 판단할 수 있다. */
const PER_STYLE = 6;

function candidatesFor(round) {
  const out = [];
  for (const style of DEFAULT_AVATAR_STYLES) {
    for (let i = 0; i < PER_STYLE; i++) {
      // 회차와 자리로 변형을 만든다 — 같은 회차는 언제나 같은 후보를 낸다.
      const variant = (round * PER_STYLE + i) % (AVATAR_VARIANT_MAX + 1);
      out.push({ style, key: formatAvatarKey(style, variant) });
    }
  }
  return out;
}

export function DefaultAvatarPicker({ seed, value, busy, onPick }) {
  const [round, setRound] = React.useState(0);
  const chosen = parseAvatarKey(value) ? String(value) : null;
  /* 고른 값이 없을 때 무엇이 그려지고 있는지도 보여 준다 — 그것이 지금 이 사람의 얼굴이고,
     고르는 화면에서 그것이 안 보이면 무엇과 비교하는지 알 수 없다. */
  const auto = autoAvatarKey(seed);
  const candidates = React.useMemo(() => candidatesFor(round), [round]);

  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap", mb: 1 }}>
        <Typography variant="body2" color="text.secondary" sx={{ flex: 1, minWidth: "16rem" }}>
          사진이 없을 때 쓸 기본 아바타를 고를 수 있습니다. 고르지 않으면 계정마다 자동으로 하나가 정해집니다.
        </Typography>
        <Button size="sm" disabled={busy} onClick={() => setRound((r) => r + 1)}>
          다른 후보 보기
        </Button>
        {chosen ? (
          <Button size="sm" disabled={busy} onClick={() => onPick("")}>
            자동으로 되돌리기
          </Button>
        ) : null}
      </Box>

      <Box role="radiogroup" aria-label="기본 아바타" sx={{ display: "grid", gap: 1.25 }}>
        {DEFAULT_AVATAR_STYLES.map((style) => (
          <Box key={style} sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Typography
              component="span"
              sx={{
                width: "7rem", flexShrink: 0,
                fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, color: "text.secondary",
              }}
            >
              {DEFAULT_AVATAR_STYLE_LABELS[style]}
            </Typography>
            {candidates.filter((c) => c.style === style).map((c) => {
              const isChosen = chosen === c.key;
              const isAuto = !chosen && auto === c.key;
              return (
                <Box
                  key={c.key}
                  component="button"
                  type="button"
                  role="radio"
                  aria-checked={isChosen}
                  aria-label={`${DEFAULT_AVATAR_STYLE_LABELS[style]} 아바타 고르기`}
                  disabled={busy}
                  onClick={() => onPick(isChosen ? "" : c.key)}
                  sx={{
                    p: 0.375, border: 0, background: "none", cursor: busy ? "default" : "pointer",
                    borderRadius: "50%", lineHeight: 0,
                    /* 고른 것은 굵은 테, 자동으로 정해진 것은 옅은 테. 둘을 같은 표시로
                       두면 「내가 고른 것」과 「그냥 그렇게 된 것」이 구별되지 않는다. */
                    outline: isChosen ? "2px solid" : isAuto ? "1px dashed" : "2px solid transparent",
                    outlineColor: isChosen ? "primary.main" : isAuto ? "text.secondary" : "transparent",
                    outlineOffset: 1,
                    "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
                  }}
                >
                  <Box sx={{ width: "2.5rem", height: "2.5rem", borderRadius: "50%", overflow: "hidden" }}>
                    <DefaultAvatar seed={seed} avatarKey={c.key} />
                  </Box>
                </Box>
              );
            })}
          </Box>
        ))}
      </Box>
    </Box>
  );
}
