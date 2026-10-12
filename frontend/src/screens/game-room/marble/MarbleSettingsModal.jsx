import React from "react";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Button, Callout, FieldLabel, Modal, ModalFooter } from "../../../ui/kit.jsx";

/* 방장의 경주 설정 — 참가자 · 당첨 인원 · 꼴찌 당첨 · 배속 (D-564). 대기 중에만 연다.
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
  const [problem, setProblem] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const players = (members || []).filter((m) => m.role !== "spectator");

  React.useEffect(() => {
    if (!open) return;
    setText((current.participants || []).map((p) => p.name).join("\n"));
    setWinners(current.winners || 1);
    setPickLast(!!current.pick_last);
    setSpeed(current.speed || 1);
    setProblem(null);
    setBusy(false);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const names = parseNames(text);
  const dirty = text !== (current.participants || []).map((p) => p.name).join("\n")
    || Number(winners) !== (current.winners || 1) || pickLast !== !!current.pick_last || Number(speed) !== (current.speed || 1);
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
      await mutations.marbleParticipants.mutateAsync({ participants });
      await mutations.marbleConfig.mutateAsync({ winners: Number(winners) || 1, pick_last: !!pickLast, speed: Number(speed) || 1 });
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
            placeholder={"한 줄에 한 명씩 적습니다.\n비워 두면 방 구성원이 참가자입니다."}
            inputProps={{ "aria-describedby": "marble-names-help" }}
          />
          <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" sx={{ mt: 1 }}>
            <Typography id="marble-names-help" variant="caption" color="text.secondary">
              {names.length ? `${names.length}명` : "비어 있음"} (2명부터 100명까지, 이름은 24자까지)
            </Typography>
            <Button size="sm" onClick={fillMembers} disabled={!players.length}>방 구성원 이름으로 채우기</Button>
          </Stack>
        </Box>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
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
        {problem ? (
          <Callout tone="danger" compact>
            <Box sx={{ display: "grid", gap: 1 }}>
              <span>{problem.message}</span>
              {suggestionRows.length ? (
                <Box sx={{ display: "grid", gap: 0.5 }}>
                  {suggestionRows.map(([from, to]) => <Typography key={from} variant="body2">{from} → {to}</Typography>)}
                  <Box><Button size="sm" onClick={() => applySuggestions(problem.suggestions)}>제안대로 고치기</Button></Box>
                </Box>
              ) : null}
            </Box>
          </Callout>
        ) : null}
      </Box>
    </Modal>
  );
}
