import React from "react";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import InputBase from "@mui/material/InputBase";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import ListSubheader from "@mui/material/ListSubheader";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import { useNavigate } from "react-router-dom";

/* 명령 팔레트 (Ctrl+K / Cmd+K).
 *
 * v1은 **메뉴 이동만** 한다. 디자인 원본에는 상단바에 "통합 검색" 입력이 있었지만 실제로는
 * 팔레트를 여는 것 말고 아무 일도 하지 않는 죽은 컨트롤이었다. 이 저장소는 '되는 척하는 UI'를
 * 두지 않는다 — 그래서 라벨을 "메뉴 검색"으로 정직하게 두고, 티켓·문서·게시판·사람을 가로지르는
 * 진짜 통합 검색(SQLite FTS5)은 백엔드가 준비된 뒤(Phase 5) 같은 자리에 붙인다.
 *
 * 후보 목록은 **역할로 걸러진 나브**에서 온다. 권한 없는 화면이 검색 결과에 뜨면 눌렀을 때
 * 403 막다른 길로 가는데, 그건 사이드바에서 이미 없앤 문제다.
 */

function normalize(s) {
  return String(s || "").toLowerCase().replace(/\s+/g, "");
}

export function CommandPalette({ open, onClose, groups }) {
  const [q, setQ] = React.useState("");
  const navigate = useNavigate();
  const inputRef = React.useRef(null);

  React.useEffect(() => { if (open) setQ(""); }, [open]);

  const results = React.useMemo(() => {
    const needle = normalize(q);
    return (groups || [])
      .map((g) => ({
        group: g.group,
        items: g.items.filter((it) => !needle || normalize(it.label).includes(needle) || normalize(g.group).includes(needle)),
      }))
      .filter((g) => g.items.length);
  }, [groups, q]);

  const flat = React.useMemo(() => results.flatMap((g) => g.items), [results]);
  const [cursor, setCursor] = React.useState(0);
  React.useEffect(() => { setCursor(0); }, [q, open]);

  const go = React.useCallback((to) => { onClose(); navigate(to); }, [navigate, onClose]);

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(c + 1, flat.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
    else if (e.key === "Enter" && flat[cursor]) { e.preventDefault(); go(flat[cursor].to); }
  };

  return (
    <Dialog
      open={!!open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      aria-label="메뉴 검색"
      sx={{ "& .MuiDialog-paper": { alignSelf: "flex-start", mt: { xs: 4, sm: 12 }, borderRadius: 3 } }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, px: 3, py: 2, borderBottom: 1, borderColor: "divider" }}>
        <SearchRoundedIcon aria-hidden="true" sx={{ color: "text.secondary" }} />
        <InputBase
          inputRef={inputRef}
          autoFocus
          fullWidth
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="메뉴 검색 (예: 티켓, 감사 로그)"
          inputProps={{ "aria-label": "메뉴 검색" }}
          sx={{ fontSize: "1rem" }}
        />
        <Box component="kbd" sx={{ fontSize: "0.6875rem", color: "text.secondary", border: 1, borderColor: "divider", borderRadius: 1, px: 1, py: 0.25 }}>
          Esc
        </Box>
      </Box>
      <DialogContent sx={{ p: 0, maxHeight: "60vh" }}>
        {flat.length === 0 ? (
          <Typography sx={{ p: 4, textAlign: "center" }} color="text.secondary">
            일치하는 메뉴가 없습니다.
          </Typography>
        ) : (
          <List dense disablePadding>
            {results.map((g) => (
              <li key={g.group}>
                <ul style={{ padding: 0, margin: 0, listStyle: "none" }}>
                  <ListSubheader disableSticky sx={{ bgcolor: "transparent", fontSize: "0.6875rem", fontWeight: 800, letterSpacing: ".04em" }}>
                    {g.group}
                  </ListSubheader>
                  {g.items.map((it) => {
                    const idx = flat.indexOf(it);
                    return (
                      <ListItemButton
                        key={it.to}
                        selected={idx === cursor}
                        onMouseEnter={() => setCursor(idx)}
                        onClick={() => go(it.to)}
                      >
                        <ListItemText primary={it.label} secondary={it.to} />
                      </ListItemButton>
                    );
                  })}
                </ul>
              </li>
            ))}
          </List>
        )}
      </DialogContent>
    </Dialog>
  );
}

/* Ctrl+K / Cmd+K 전역 단축키. 입력 중에도 열리게 두되(팔레트가 검색이라 자연스럽다)
 * 브라우저 기본 동작은 막는다. */
export function useCommandPaletteHotkey(setOpen) {
  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);
}
