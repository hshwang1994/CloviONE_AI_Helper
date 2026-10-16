import React from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import FullscreenRoundedIcon from "@mui/icons-material/FullscreenRounded";
import FullscreenExitRoundedIcon from "@mui/icons-material/FullscreenExitRounded";
import { Badge, Button, FlatBadgeSurface, HeadRow, OverflowMenu, useToast } from "../../ui/kit.jsx";
import { CONTROL, FONT_SIZE, ICON, NUMERIC, remPx } from "../../ui/theme.js";
import { GAME_LABELS } from "../Games.jsx";
import { Countdown } from "./StageShared.jsx";
import { marbleMetaParts } from "./roomStatus.js";
import { STAGE_KEYS, STAGE_LABELS } from "./marble/engine/stages/labels.js";
import { useGameRoomLayout } from "./GameRoomLayout.jsx";

/* 방 툴바 (게임 공통 G2 · D-575) — 상태 정본 하나 · 동작 줄 하나.
 *
 * 왼쪽은 사실(종류 · 상태 · 참여 · 관전 · 구슬 설정 · 완주 · 당첨 · 남은 시간 · 제출), 오른쪽은 동작이다. 예전에는 상태가 두 줄(껍데기의
 * 「대기 중」 배지와 구슬 판의 「대기 중 · 1명 참가 …」 띠)에 서고, 설정 · 정보 · 전체 화면은 순위 레일 위, 경주 시작 · 방 파하기는
 * 판 아래, 나가기는 페이지 머리에 따로 섰다. 이제 상태 낱말은 페이지에 한 번이고(`data-room-status`), 동작은 한 줄이다.
 *
 * 한 줄의 컨트롤은 모두 34px 이다(`control_row` — 작은 단추 30 을 섞지 않는다). 동작 순서: [설정] · [준비] · 주 동작 · [결과 보기] ·
 * [전체 화면] · [나가기] · 넘침(방 파하기). 전체 화면에서는 설정 · 나가기 · 넘침을 숨긴다(그 메뉴 · 확인 창은 문서의 포털이라 전체 화면이
 * 가린다). 흐름 · 모바일은 상태 줄 하나 + 동작 줄 하나이고, `sm` 아래에서는 나가기도 넘침으로 들어간다. */

function Meta({ children }) {
  return (
    <Typography component="span" variant="body2" color="text.secondary" sx={{ ...NUMERIC, whiteSpace: "nowrap" }}>
      {children}
    </Typography>
  );
}

/* 맵 선택 (D-593) — 방장만, 대기 중에만 쓴다. 「다시 하기」 뒤도 대기다. 경주 중 · 끝난 방에서는 단추를 지우지 않고 막아 두며 까닭을
 * 툴팁과 설명(`aria-describedby`)으로 보인다. 예전에는 맵을 바꾸려면 「설정」 창을 열어야 했고, 구성원을 참가자로 쓰는 방은 그 창의 저장이
 * 막혀 맵을 바꿀 수 없었다. 고른 맵은 서버가 경주 상태에 박는다 — 툴바의 맵 이름과 실제로 그리는 판이 같은 값을 읽는다. */
function MarbleMapPicker({ current, enabled, reason, mutation }) {
  const toast = useToast();
  const reasonId = React.useId();
  const pick = async (key) => {
    if (key === current) return;
    try {
      await mutation.mutateAsync({ map: key });
    } catch (e) {
      toast((e && e.message) || "맵을 바꾸지 못했습니다. 다시 시도해 주세요.", "error");
    }
  };
  const menu = (
    <OverflowMenu
      label="맵 선택"
      items={STAGE_KEYS.map((key) => ({ key, label: STAGE_LABELS[key], checked: key === current, onClick: () => pick(key) }))}
      buttonProps={{
        disabled: !enabled || mutation.isPending,
        "aria-describedby": enabled ? undefined : reasonId,
        "data-marble-map-picker": enabled ? "on" : "off",
      }}
    />
  );
  if (enabled) return menu;
  return (
    <Tooltip title={reason}>
      {/* 막힌 단추는 초점을 못 받는다 — 감싸개가 초점을 받아 키보드로도 까닭이 열린다. */}
      <Box component="span" tabIndex={0} sx={{ display: "inline-flex", borderRadius: 1 }}>
        {menu}
        <Box component="span" id={reasonId} className="sr-only">{reason}</Box>
      </Box>
    </Tooltip>
  );
}

export function RoomToolbar({ c, fs, onOpenSettings }) {
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down("sm"), { noSsr: true });
  const { mode } = useGameRoomLayout();
  const { room, status, summary, actions, reveal, isMarble, marble, submissionActive, remaining, submittedCount, activePlayers, mutations } = c;
  const fullscreen = !!(fs && fs.active);
  /* 채움 모드는 한 줄(사실 | 동작), 흐름 · 모바일은 두 줄(사실 / 동작)이다. 좁은 폭에서 한 줄이 상태마다 접혔다 펴지면(동작 단추 수가
     단계마다 다르다) 판이 위아래로 흔들린다 — 두 줄로 세우면 툴바 높이가 단계와 무관하다(G8 「판 사각 불변」). */
  const stacked = mode !== "fill";
  const game = c.isTournament ? "가위바위보 토너먼트" : (GAME_LABELS[room.game_type] || room.game_type);

  const facts = (
    <FlatBadgeSurface>
      <Box data-room-facts="" sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", columnGap: 1.5, rowGap: 0.5, minHeight: remPx(CONTROL.control), minWidth: 0 }}>
        <Badge value={game} kind="neutral" />
        <Box component="span" data-room-status={status.key} sx={{ display: "inline-flex" }}>
          <Badge value={status.label} kind={status.kind} emphasis="strong" />
        </Box>
        {status.spectating ? <Badge value="관전 중" kind="neutral" emphasis="strong" /> : null}
        <Meta>참여 {summary.players}/{summary.max}</Meta>
        {summary.spectators ? <Meta>관전 {summary.spectators}</Meta> : null}
        {isMarble ? <Meta>{STAGE_LABELS[marble.stageKey] || STAGE_LABELS.wheel}</Meta> : null}
        {isMarble ? marbleMetaParts(summary).map((part) => <Meta key={part}>{part}</Meta>) : null}
        {isMarble && !marble.waiting && room.status === "playing" ? <Meta>완주 {summary.finishedCount}/{summary.marbles}</Meta> : null}
        {c.isDraw && room.status === "finished" && c.drawWinners.length ? <Meta>당첨 {c.drawWinners.length}명</Meta> : null}
        {room.status === "playing" ? <Countdown remaining={remaining} /> : null}
        {submissionActive ? <Meta>제출 {submittedCount}/{activePlayers.length}</Meta> : null}
      </Box>
    </FlatBadgeSurface>
  );

  const fsButton = (
    <Button
      onClick={() => fs && fs.toggle()}
      aria-pressed={fullscreen}
      startIcon={fullscreen ? <FullscreenExitRoundedIcon sx={{ fontSize: remPx(ICON.action) }} /> : <FullscreenRoundedIcon sx={{ fontSize: remPx(ICON.action) }} />}
    >
      {fullscreen ? "전체 화면 종료" : "전체 화면"}
    </Button>
  );
  const leaveInMenu = narrow && !fullscreen;
  const menu = !fullscreen ? [
    leaveInMenu ? { key: "leave", label: "나가기", onClick: () => mutations.leave.mutate(), disabled: mutations.leave.isPending } : null,
    actions.disband ? { key: "disband", label: "게임방 종료", tone: "danger", onClick: c.disbandWithConfirm, disabled: mutations.disband.isPending } : null,
  ].filter(Boolean) : [];

  /* 맵 선택은 방장에게만 선다(서버도 방장만 받는다 — 403). 대기 중이 아니면 막고 까닭을 말한다. 전체 화면에서는 메뉴가 문서의 포털이라
     가려지므로 설정과 함께 숨긴다. */
  const mapPick = isMarble && c.isHost && !fullscreen ? {
    enabled: !!marble.waiting,
    reason: room.status === "playing" ? "경주 중에는 맵을 바꿀 수 없습니다. 경주가 끝난 뒤 '다시 하기'를 누르면 바꿀 수 있습니다."
      : "'다시 하기'를 누른 뒤 변경할 수 있습니다.",
  } : null;

  const buttons = (
    <>
      {mapPick ? (
        <MarbleMapPicker current={marble.stageKey || "wheel"} enabled={mapPick.enabled} reason={mapPick.reason} mutation={mutations.marbleConfig} />
      ) : null}
      {actions.settings && !fullscreen ? <Button onClick={onOpenSettings}>설정</Button> : null}
      {actions.ready ? (
        <Button variant={actions.ready.on ? "default" : "primary"} onClick={actions.ready.onClick} disabled={actions.ready.pending}>{actions.ready.label}</Button>
      ) : null}
      {actions.primary ? (
        <Button variant="primary" onClick={actions.primary.onClick} disabled={actions.primary.pending} data-room-primary={actions.primary.key}>{actions.primary.label}</Button>
      ) : null}
      {actions.showResult ? <Button onClick={reveal.openDialog}>결과 보기</Button> : null}
      {fsButton}
      {!fullscreen && !leaveInMenu ? <Button onClick={() => mutations.leave.mutate()} disabled={mutations.leave.isPending}>나가기</Button> : null}
      {menu.length ? <OverflowMenu items={menu} ariaLabel="방 동작 더 보기" /> : null}
    </>
  );

  if (stacked) {
    return (
      <Box component="section" aria-label="방 상태와 동작" data-room-toolbar={mode === "mobile" ? "mobile" : "stacked"} sx={{ display: "grid", gap: 1, minWidth: 0 }}>
        {facts}
        <Box data-room-actions="" sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "center" }}>{buttons}</Box>
      </Box>
    );
  }
  return (
    <HeadRow
      component="section"
      aria-label="방 상태와 동작"
      data-room-toolbar={fullscreen ? "fullscreen" : "full"}
      lineHeightPx={CONTROL.control}
      action={buttons}
      sx={{ fontSize: FONT_SIZE.bodySm }}
    >
      {facts}
    </HeadRow>
  );
}
