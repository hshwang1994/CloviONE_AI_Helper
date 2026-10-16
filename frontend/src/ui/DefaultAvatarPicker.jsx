import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { Button, Modal, ModalFooter } from "./kit.jsx";
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

/* 기본 아바타 고르기 — **대화상자다** (REAUDIT_PLAN §17 bundle-2 step 7: "기본 아바타 고르개
 * 대화상자화").
 *
 * 예전에는 후보 격자가 프로필 화면 안에 항상 펼쳐져 있었고, 후보 하나를 누르는 순간
 * **곧바로 저장됐다**(즉시 반영, 취소 없음). 후보를 눌러 보며 비교하는 것이 이 부품의
 * 본래 목적인데, 그 비교 자체가 매번 서버에 쓰는 일이 되어 있었다 — 둘러보다가 마음이
 * 바뀌면 그 전 값으로 한 번 더 눌러야 했다. 이 화면의 다른 선택 대화상자
 * (`AvatarCropDialog.jsx`)와 같은 모양으로 맞춘다: 안에서는 얼마든지 후보를 넘겨 보고,
 * **저장을 눌러야** 반영되고 취소·닫기는 아무것도 바꾸지 않는다.
 *
 * 후보가 여덟 개로 끝나지 않는다. 스타일 다섯에 변형 1,000 이면 조합이 5,000 가지다.
 * 그것을 한 화면에 다 깔 수는 없고, 깔 이유도 없다 — 사람이 고를 때 실제로 하는 일은
 * 「마음에 드는 게 보일 때까지 넘기는 것」이다. 그래서 한 번에 스타일별 한 줄씩 보여 주고,
 * 마음에 안 들면 **다시 만든다**.
 *
 * 다시 만드는 값이 난수가 아니라 **회차 번호**인 것이 이 부품의 요점이다. 같은 회차는
 * 언제 눌러도 같은 후보를 낸다 — 뒤로 갔다 오면 방금 본 얼굴이 사라지는 목록은 고를 수가
 * 없다. 회차는 대화상자를 여는 동안만 세고 저장하지 않는다: 저장되는 것은 사람이 실제로
 * 고른 값 하나뿐이다.
 */

/* 스타일마다 한 줄에 몇 개. 다섯 스타일 × 여섯이면 서른 개가 한 화면에 들어가고,
 * 그 정도면 「마음에 드는 게 없다」를 판단할 수 있다. 한 줄은 flex-wrap 이 아니라
 * 여섯 칸 격자라, 다섯이 앉고 하나가 아래로 떨어지는 모양이 나오지 않는다. */
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

/** 대화상자를 여는 버튼 + 대화상자 — 프로필 화면은 이 하나만 자리로 받는다.
 *  지금 실제로 쓰이는 그림(사진이 없으면 기본 아바타)은 이미 위의 큰 아바타가 보여 주므로
 *  이 버튼 옆에 같은 그림을 또 그리지 않는다. */
export function DefaultAvatarPicker({ seed, value, busy, onPick }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      {/* 크기는 **이웃이 정한다.** 이 단추는 신원 머리의 동작 묶음에서 「사진 바꾸기」·
          「비밀번호 변경」과 한 줄에 서므로 기본 높이(34)다 — 30 이면 셋 중 하나만 낮다. */}
      <Button disabled={busy} onClick={() => setOpen(true)}>
        기본 아바타 고르기
      </Button>
      <DefaultAvatarDialog
        open={open}
        onClose={() => setOpen(false)}
        seed={seed}
        value={value}
        busy={busy}
        onPick={(key) => { onPick(key); setOpen(false); }}
      />
    </>
  );
}

function DefaultAvatarDialog({ open, onClose, seed, value, busy, onPick }) {
  const [round, setRound] = React.useState(0);
  /* 고른 값은 **열릴 때** 지금 값으로 시작하고, 대화상자 안에서만 바뀐다 — 저장을 눌러야
     `onPick` 이 나간다. 닫았다 다시 열면 저장 안 한 시도는 사라지고 실제 값에서 다시
     시작한다. */
  const [staged, setStaged] = React.useState(value || "");
  React.useEffect(() => {
    if (open) { setStaged(value || ""); setRound(0); }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const chosen = parseAvatarKey(staged) ? String(staged) : null;
  /* 고른 값이 없을 때 무엇이 그려지고 있는지도 보여 준다 — 그것이 지금 이 사람의 얼굴이고,
     고르는 화면에서 그것이 안 보이면 무엇과 비교하는지 알 수 없다. */
  const auto = autoAvatarKey(seed);
  const candidates = React.useMemo(() => candidatesFor(round), [round]);
  const dirty = (staged || "") !== (value || "");

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="기본 아바타 고르기"
      size="fit"
      dirty={dirty}
      footer={
        <ModalFooter
          onCancel={onClose}
          onSubmit={() => onPick(staged || "")}
          submitLabel="저장"
          busy={busy}
          disabled={!dirty}
        />
      }
    >
      {/* 설명 문단은 두지 않는다. 창 폭은 아바타 여섯 칸에 맞추고, 동작은 단추 이름으로
         말한다. 「선택 해제」는 고른 얼굴을 지워 계정마다 정해지는 자동 얼굴로 돌아간다. */}
      <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1, mb: 1.5, flexWrap: "wrap" }}>
        <Button size="sm" disabled={busy} onClick={() => setRound((r) => r + 1)}>
          다른 후보 보기
        </Button>
        {chosen ? (
          <Button
            size="sm"
            disabled={busy}
            onClick={() => setStaged("")}
            title="고른 얼굴을 지우고 이 계정에 자동으로 정해진 얼굴을 씁니다."
          >
            선택 해제
          </Button>
        ) : null}
      </Box>

      <Box
        role="radiogroup"
        aria-label="기본 아바타"
        sx={{ display: "grid", gap: 1.5, width: "max-content", maxWidth: "100%" }}
      >
        {DEFAULT_AVATAR_STYLES.map((style) => (
          <Box key={style} sx={{ display: "grid", gap: 0.75, width: "max-content" }}>
            <Typography
              component="span"
              sx={{
                fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, color: "text.secondary",
              }}
            >
              {DEFAULT_AVATAR_STYLE_LABELS[style]}
            </Typography>
            <Box
              data-avatar-row
              sx={{
                display: "grid",
                gridTemplateColumns: "repeat(6, 2.5rem)",
                gap: 0.75,
                justifyContent: "start",
                py: 0.25,
              }}
            >
            {candidates.filter((c) => c.style === style).map((c, i) => {
              const isChosen = chosen === c.key;
              const isAuto = !chosen && auto === c.key;
              return (
                <Box
                  key={c.key}
                  component="button"
                  type="button"
                  role="radio"
                  aria-checked={isChosen}
                  aria-label={`${DEFAULT_AVATAR_STYLE_LABELS[style]} 아바타 ${i + 1}`}
                  disabled={busy}
                  onClick={() => setStaged(isChosen ? "" : c.key)}
                  sx={{
                    p: 0, border: 0, background: "none", cursor: busy ? "default" : "pointer",
                    borderRadius: "50%", lineHeight: 0, width: "2.5rem", height: "2.5rem",
                    /* 고른 것은 굵은 테, 자동으로 정해진 것은 옅은 테. 둘을 같은 표시로
                       두면 「내가 고른 것」과 「그냥 그렇게 된 것」이 구별되지 않는다. */
                    outline: isChosen ? "2px solid" : isAuto ? "1px dashed" : "2px solid transparent",
                    outlineColor: isChosen ? "primary.main" : isAuto ? "text.secondary" : "transparent",
                    outlineOffset: 1,
                    "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
                  }}
                >
                  <Box sx={{ width: "100%", height: "100%", borderRadius: "50%", overflow: "hidden" }}>
                    <DefaultAvatar seed={seed} avatarKey={c.key} />
                  </Box>
                </Box>
              );
            })}
            </Box>
          </Box>
        ))}
      </Box>
    </Modal>
  );
}
