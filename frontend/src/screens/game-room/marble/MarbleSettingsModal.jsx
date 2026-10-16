import React from "react";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Button, Callout, FieldLabel, Modal, ModalFooter } from "../../../ui/kit.jsx";
import { KO_WORD_BREAK } from "../../../ui/theme.js";
import { STAGE_KEYS, STAGE_LABELS } from "./engine/stages/labels.js";

/* 방장의 경주 설정 — 참가자 · 경주 판 · 당첨 인원 · 꼴찌 당첨 · 배속 (D-564 · D-578). 대기 중에만 연다.
 *
 * 참가자는 한 줄에 한 명이다(붙여 넣기로 여럿). 비워 두면 시작할 때 방 구성원이 참가자다. 이름이 겹치면 서버가 422 와
 * 「(2)」 제안을 돌려주고, 여기서는 그 제안을 한 번에 적용할 수 있다. 검증의 정본은 서버(`app/games/marble.py`)다 — 여기
 * 숫자는 보내기 전에 헛걸음을 줄이는 같은 값이다. */

export const MARBLE_LIMITS = { minParticipants: 2, maxParticipants: 100, nameMax: 24, maxWinners: 10, speeds: [1, 2, 4] };

export function parseNames(text) {
  return String(text || "").split(/\r?\n/).map((s) => s.replace(/\s+/g, " ").trim()).filter(Boolean);
}

function localProblem(names) {
  if (names.length && names.length < MARBLE_LIMITS.minParticipants) return `참가자는 ${MARBLE_LIMITS.minParticipants}명 이상이어야 합니다.`;
  if (names.length > MARBLE_LIMITS.maxParticipants) return `참가자는 ${MARBLE_LIMITS.maxParticipants}명까지 넣을 수 있습니다.`;
  const long = names.find((n) => Array.from(n).length > MARBLE_LIMITS.nameMax);
  if (long) return `참가자 이름은 ${MARBLE_LIMITS.nameMax}자까지 넣을 수 있습니다.`;
  return null;
}

/* 422 의 `details.suggestions` — `lib/api.js` 는 봉투 전체를 `error.body` 에 남긴다(배열 details 만 문장에 합친다). */
function suggestionsOf(error) {
  const d = error && ((error.body && error.body.error && error.body.error.details) || error.details);
  if (d && !Array.isArray(d) && d.suggestions && typeof d.suggestions === "object") return d.suggestions;
  return null;
}

export function MarbleSettingsModal({ open, onClose, config, members, mutations, onSaved }) {
  const current = config || {};
  const [text, setText] = React.useState("");
  const [winners, setWinners] = React.useState(1);
  const [pickLast, setPickLast] = React.useState(false);
  const [speed, setSpeed] = React.useState(1);
  const [map, setMap] = React.useState("wheel");
  const [problem, setProblem] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const players = (members || []).filter((m) => m.role !== "spectator");

  React.useEffect(() => {
    if (!open) return;
    setText((current.participants || []).map((p) => p.name).join("\n"));
    setWinners(current.winners || 1);
    setPickLast(!!current.pick_last);
    setSpeed(current.speed || 1);
    setMap(current.map || "wheel");
    setProblem(null);
    setBusy(false);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const names = parseNames(text);
  /* 참가자와 나머지 설정은 따로 저장한다 — 바뀐 쪽만 보낸다. 예전에는 늘 참가자를 먼저 보냈고, 방 구성원을 참가자로 쓰는 방(빈 목록)은
     그 요청이 막혀 맵조차 저장되지 않았다(r23 D-593). */
  const participantsDirty = text !== (current.participants || []).map((p) => p.name).join("\n");
  const configDirty = Number(winners) !== (current.winners || 1) || pickLast !== !!current.pick_last || Number(speed) !== (current.speed || 1)
    || map !== (current.map || "wheel");
  const dirty = participantsDirty || configDirty;
  const fillMembers = () => setText(players.map((m) => m.name).join("\n"));
  const applySuggestions = (map) => {
    setText(names.map((n) => (map[n] ? map[n] : n)).join("\n"));
    setProblem(null);
  };

  const save = async () => {
    const local = localProblem(names);
    if (local) { setProblem({ message: local }); return; }
    setBusy(true);
    setProblem(null);
    try {
      const byName = new Map(players.map((m) => [m.name, m.user_id]));
      const known = new Map((current.participants || []).map((p) => [p.name, p]));
      const participants = names.map((name) => {
        const prev = known.get(name);
        if (prev) return { key: prev.key, name, user_id: prev.user_id || undefined };
        const uid = byName.get(name);
        return uid ? { name, user_id: uid } : { name };
      });
      if (participantsDirty) await mutations.marbleParticipants.mutateAsync({ participants });
      if (configDirty) await mutations.marbleConfig.mutateAsync({ winners: Number(winners) || 1, pick_last: !!pickLast, speed: Number(speed) || 1, map });
      onSaved && onSaved();
      onClose();
    } catch (e) {
      setProblem({ message: (e && e.message) || "설정을 저장하지 못했습니다. 다시 시도해 주세요.", suggestions: suggestionsOf(e) });
    } finally {
      setBusy(false);
    }
  };

  const suggestionRows = problem && problem.suggestions ? Object.entries(problem.suggestions) : [];

  return (
    <Modal open={open} onClose={onClose} title="경주 설정" size="md" dirty={dirty}
      footer={<ModalFooter onCancel={onClose} onSubmit={save} submitLabel="저장" busy={busy} />}>
      <Box sx={{ display: "grid", gap: 2.5 }}>
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor="marble-names">참가자</FieldLabel>
          <TextField
            id="marble-names" size="small" fullWidth multiline minRows={4} maxRows={12}
            value={text} onChange={(e) => setText(e.target.value)}
            placeholder={"한 줄에 한 명씩 적습니다. 비워 두면 방 구성원이 참가자입니다."}
            inputProps={{ "aria-describedby": "marble-names-help" }}
          />
          <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" sx={{ mt: 1 }}>
            <Typography id="marble-names-help" variant="caption" color="text.secondary">
              {names.length ? `${names.length}명` : "비어 있음"} (2명부터 100명까지, 이름은 24자까지)
            </Typography>
            <Button size="sm" onClick={fillMembers} disabled={!players.length}>방 구성원 이름으로 채우기</Button>
          </Stack>
        </Box>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr 1fr" } }}>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel id="marble-map-label">맵 선택</FieldLabel>
            <TextField SelectProps={{ labelId: "marble-map-label" }} id="marble-map" select size="small" fullWidth
              value={map} onChange={(e) => setMap(e.target.value)}>
              {STAGE_KEYS.map((k) => <MenuItem key={k} value={k}>{STAGE_LABELS[k]}</MenuItem>)}
            </TextField>
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor="marble-winners">당첨 인원</FieldLabel>
            <TextField id="marble-winners" type="number" size="small" fullWidth
              inputProps={{ min: 1, max: MARBLE_LIMITS.maxWinners }} value={winners} onChange={(e) => setWinners(e.target.value)} />
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel id="marble-speed-label">배속</FieldLabel>
            <TextField SelectProps={{ labelId: "marble-speed-label" }} id="marble-speed" select size="small" fullWidth
              value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
              {MARBLE_LIMITS.speeds.map((s) => <MenuItem key={s} value={s}>{s}배속</MenuItem>)}
            </TextField>
          </Box>
        </Box>
        <FormControlLabel
          control={<Checkbox checked={pickLast} onChange={(e) => setPickLast(e.target.checked)} />}
          label="꼴찌로 들어온 구슬이 당첨"
        />
        {/* 결과의 뜻 한 줄(D-564) — 예전 「정보」 대화 상자에 있던 문장이다. 출처 고지는 사용자 메뉴의 「오픈소스 고지」로 갔다(D-579). */}
        <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>
          모든 화면이 같은 시작값으로 경주를 계산하고 서버가 결과를 대조합니다. 「확인됨」은 화면끼리 결과가 같았다는 뜻이고, 조작이 없었다는 증명은 아닙니다.
        </Typography>
        {problem ? (
          <Callout tone="danger" compact>
            <Box sx={{ display: "grid", gap: 1 }}>
              <span>{problem.message}</span>
              {suggestionRows.length ? (
                <Box sx={{ display: "grid", gap: 0.5 }}>
                  {suggestionRows.map(([from, to]) => <Typography key={from} variant="body2">{from} → {to}</Typography>)}
                  <Box><Button size="sm" onClick={() => applySuggestions(problem.suggestions)}>제안대로 수정</Button></Box>
                </Box>
              ) : null}
            </Box>
          </Callout>
        ) : null}
      </Box>
    </Modal>
  );
}
