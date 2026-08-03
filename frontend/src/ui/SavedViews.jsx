import React from "react";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import BookmarkBorderRoundedIcon from "@mui/icons-material/BookmarkBorderRounded";
import BookmarkRoundedIcon from "@mui/icons-material/BookmarkRounded";
import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import LinkRoundedIcon from "@mui/icons-material/LinkRounded";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { Button, Modal, ModalFooter, useToast } from "./kit.jsx";

/* 저장된 뷰 — 자주 쓰는 필터 조합에 이름을 붙여 두고 다시 부른다.
 *
 * 저장하는 것은 **화면 주소의 쿼리 문자열** 하나다(screens/datascreen-view.js). 그래서
 * 뷰를 부르는 일이 곧 '그 주소로 가는 일'이고, 링크 공유가 공짜로 따라온다 — 서버는 그
 * 문자열을 해석하지 않으므로 화면의 필터 정의가 바뀌어도 저장된 뷰를 손볼 필요가 없다.
 *
 * props
 *   screenKey  화면 키(registry.js 의 config.key). 뷰는 화면별로 분리된다.
 *   query      지금 화면의 쿼리 문자열(저장 버튼이 이 값을 보낸다).
 *   describe   쿼리 → 사람이 읽는 요약(목록 부제). 없으면 부제를 생략한다.
 *   onApply    뷰를 골랐을 때 그 쿼리 문자열로 화면을 되돌리는 콜백.
 */
export function SavedViews({ screenKey, query, describe, onApply }) {
  const [anchor, setAnchor] = React.useState(null);
  const [saving, setSaving] = React.useState(false);
  const [name, setName] = React.useState("");
  const [conflict, setConflict] = React.useState(false);
  const qc = useQueryClient();
  const toast = useToast();

  const list = useQuery({
    queryKey: ["saved-views", screenKey],
    queryFn: () => api("/api/me/views?screen_key=" + encodeURIComponent(screenKey)),
    // 뷰는 이 사용자가 직접 만들 때만 바뀐다 — 화면마다 다시 받아올 이유가 없다.
    staleTime: 60_000,
    retry: false,
  });
  const views = (list.data && list.data.items) || [];

  const save = useMutation({
    mutationFn: (body) => api("/api/me/views", { method: "POST", body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["saved-views", screenKey] });
      setSaving(false); setName(""); setConflict(false);
      toast("뷰를 저장했습니다.", "success");
    },
    onError: (e) => {
      // 409 는 실패가 아니라 질문이다 — "같은 이름이 있는데 덮어쓸까요?"
      if (e && e.status === 409) { setConflict(true); return; }
      toast(e.message, "error");
    },
  });

  const remove = useMutation({
    mutationFn: (id) => api("/api/me/views/" + id, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["saved-views", screenKey] });
      toast("뷰를 지웠습니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });

  function copyLink() {
    const url = window.location.href;
    // 사내 LAN 은 https 이므로 clipboard API 가 있다. 없거나 거부되면 주소를 그대로 알려
    // 준다 — "복사했습니다"라고만 하고 실제로는 아무 일도 안 일어나는 것이 최악이다.
    const done = () => toast("이 화면의 링크를 복사했습니다.", "success");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done, () => toast(url, "info"));
    } else {
      toast(url, "info");
    }
  }

  return (
    <>
      <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
        <Button
          variant="ghost"
          onClick={(e) => setAnchor(e.currentTarget)}
          aria-haspopup="menu"
          aria-expanded={Boolean(anchor)}
        >
          <BookmarkBorderRoundedIcon fontSize="small" aria-hidden="true" />
          <Box component="span" sx={{ ml: 0.75 }}>
            저장된 뷰{views.length ? ` (${views.length})` : ""}
          </Box>
        </Button>
        <Tooltip title="이 화면의 링크 복사">
          <IconButton size="small" onClick={copyLink} aria-label="이 화면의 링크 복사">
            <LinkRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      <Menu
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
        slotProps={{ paper: { sx: { minWidth: "18rem", maxWidth: "28rem" } } }}
      >
        {views.length === 0 ? (
          <Box sx={{ px: 2, py: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              저장된 뷰가 없습니다. 지금 걸어 둔 필터를 이름 붙여 저장해 보세요.
            </Typography>
          </Box>
        ) : null}
        {views.map((v) => (
          <MenuItem
            key={v.id}
            onClick={() => { setAnchor(null); onApply(v.query); }}
            sx={{ alignItems: "flex-start", gap: 1 }}
          >
            <BookmarkRoundedIcon fontSize="small" color="primary" aria-hidden="true" sx={{ mt: 0.25 }} />
            <ListItemText
              primary={v.name}
              secondary={describe ? describe(v.query) || "조건 없음(전체)" : null}
              secondaryTypographyProps={{ sx: { whiteSpace: "normal" } }}
            />
            <IconButton
              size="small"
              aria-label={`${v.name} 삭제`}
              onClick={(e) => { e.stopPropagation(); remove.mutate(v.id); }}
            >
              <DeleteOutlineRoundedIcon fontSize="small" />
            </IconButton>
          </MenuItem>
        ))}
        <Divider />
        <MenuItem onClick={() => { setAnchor(null); setConflict(false); setSaving(true); }}>
          지금 필터를 뷰로 저장…
        </MenuItem>
      </Menu>

      <Modal
        open={saving}
        onClose={() => setSaving(false)}
        title="현재 필터를 뷰로 저장"
        size="sm"
        footer={
          <ModalFooter
            onCancel={() => setSaving(false)}
            onSubmit={() => save.mutate({
              screen_key: screenKey, name, query, overwrite: conflict,
            })}
            submitLabel={conflict ? "덮어쓰기" : "저장"}
            busy={save.isPending}
          />
        }
      >
        <TextField
          autoFocus
          fullWidth
          label="뷰 이름"
          value={name}
          onChange={(e) => { setName(e.target.value); setConflict(false); }}
          inputProps={{ maxLength: 80 }}
          helperText={describe ? (describe(query) || "조건 없음(전체 목록)") : " "}
        />
        {conflict ? (
          <Typography variant="body2" color="warning.main" sx={{ mt: 1.5 }}>
            같은 이름의 뷰가 이미 있습니다. ‘덮어쓰기’를 누르면 그 뷰의 조건이 지금 조건으로 바뀝니다.
          </Typography>
        ) : null}
      </Modal>
    </>
  );
}

export default SavedViews;
