import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import { api } from "../lib/api.js";
import { Button, Callout, Card, useConfirm, useToast } from "../ui/kit.jsx";
import { ImageLightbox, useLightbox } from "../ui/ImageLightbox.jsx";

/* 티켓 첨부 — 지시서 §4 "티켓에 연결된 이미지가 있다면 현재 화면과 티켓 상세에서 바로 확인할 수
 * 있게 하고, 클릭했을 때 내용을 확인할 수 있도록 구성하라." + 제품화 지시("사용자가 노션에
 * 접근하지 않아도 본인 업무를 모두 관리").
 *
 * 두 갈래를 한 자리에 모은다:
 *   1. **본문 안의 이미지**(Notion 블록) — TicketBody 가 그린다. 여기서 손대지 않는다.
 *   2. **포털에서 붙인 파일** — 이 컴포넌트. 우리 DB·우리 디스크에 있고 우리 라우트로 서빙된다.
 *
 * 왜 나누는가: 1 은 원본(Notion)의 것이라 우리가 지울 수 없고, 2 는 우리 것이라 지울 수 있다.
 * 한 줄에 섞어 놓고 어떤 것은 X 가 없으면 사용자는 그 이유를 알 방법이 없다.
 *
 * 이미지는 인증이 걸린 같은 출처 라우트라 <img src> 로 쿠키가 함께 간다(objectURL 불필요).
 */

// 서버(app/tickets/attachments.py)와 같은 값. 한쪽만 바꾸면 "올렸는데 거부당함"이 된다.
const MAX_ATTACHMENTS = 10;
const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/png,image/jpeg,image/gif,image/webp,application/pdf";

function humanSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return Math.round(n / 1024) + " KB";
  return (n / (1024 * 1024)).toFixed(1) + " MB";
}

export function TicketAttachments({ ticketId, attachments, canEdit, onChanged }) {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const lb = useLightbox();
  const inputRef = React.useRef(null);
  const [dragging, setDragging] = React.useState(false);

  const list = Array.isArray(attachments) ? attachments : [];
  const images = list.filter((a) => a.is_image);
  const files = list.filter((a) => !a.is_image);
  const slides = images.map((a) => ({ src: a.url, title: a.filename }));
  const full = list.length >= MAX_ATTACHMENTS;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["ticket", ticketId] });
    if (onChanged) onChanged();
  };

  const upload = useMutation({
    /* 여러 장을 한 번에 고를 수 있게 하되 **순차로** 올린다. 동시에 던지면 서버의 개수 상한
       검사가 서로를 못 보고 통과해 상한을 넘긴다(각자 "지금 9개니까 괜찮다"고 판단한다). */
    mutationFn: async (fileList) => {
      const picked = Array.from(fileList || []);
      for (const f of picked) {
        if (f.size > MAX_BYTES) {
          throw new Error(`${f.name} 은(는) 10MB를 넘습니다.`);
        }
      }
      let last = null;
      for (const f of picked) {
        const fd = new FormData();
        fd.append("file", f);
        last = await api(`/api/tickets/${ticketId}/attachments`, { method: "POST", body: fd });
      }
      return last;
    },
    onSuccess: () => { toast("파일을 첨부했습니다.", "success"); refresh(); },
    onError: (e) => toast((e && e.message) || "첨부하지 못했습니다.", "error"),
  });

  const remove = useMutation({
    mutationFn: (attachmentId) =>
      api(`/api/tickets/attachments/${attachmentId}`, { method: "DELETE" }),
    onSuccess: () => { toast("첨부를 뗐습니다.", "success"); refresh(); },
    onError: (e) => toast((e && e.message) || "떼지 못했습니다.", "error"),
  });

  const pick = (fileList) => {
    if (!fileList || fileList.length === 0) return;
    if (list.length + fileList.length > MAX_ATTACHMENTS) {
      toast(`첨부는 최대 ${MAX_ATTACHMENTS}개까지 올릴 수 있습니다.`, "error");
      return;
    }
    upload.mutate(fileList);
  };

  const askRemove = async (att) => {
    const ok = await confirm(`${att.filename} 을(를) 이 티켓에서 뗍니다. 계속할까요?`,
      { title: "첨부 제거", confirmLabel: "떼기", danger: true });
    if (ok) remove.mutate(att.id);
  };

  return (
    <Card>
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 1.5, gap: 1, flexWrap: "wrap" }}>
        <Typography component="h2" variant="h6" sx={{ fontSize: "1rem" }}>
          첨부 {list.length > 0 ? `(${list.length})` : ""}
        </Typography>
        {canEdit ? (
          <Button
            onClick={() => inputRef.current && inputRef.current.click()}
            disabled={upload.isPending || full}
          >
            {upload.isPending ? "올리는 중" : "파일 추가"}
          </Button>
        ) : null}
      </Stack>

      {canEdit ? (
        <Box
          component="input"
          type="file"
          ref={inputRef}
          accept={ACCEPT}
          multiple
          onChange={(e) => { pick(e.target.files); e.target.value = ""; }}
          sx={{ display: "none" }}
        />
      ) : null}

      {list.length === 0 ? (
        canEdit ? (
          /* 빈 상태를 그대로 두면 "여기에 무엇을 할 수 있는지"가 안 보인다. 끌어다 놓는 판을
             둬서 버튼을 못 찾은 사람도 파일을 놓을 수 있게 한다. */
          <Box
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files); }}
            sx={{
              display: "grid", placeItems: "center", gap: 0.5, py: 3, px: 2,
              border: 1, borderStyle: "dashed", borderRadius: 2,
              borderColor: dragging ? "primary.main" : "divider",
              bgcolor: dragging ? "action.hover" : "transparent",
              transition: "border-color .16s, background-color .16s",
            }}
          >
            <Typography variant="body2" color="text.secondary">
              화면 캡처나 규격서를 여기에 끌어다 놓으세요.
            </Typography>
            <Typography variant="caption" color="text.secondary">
              PNG, JPEG, GIF, WebP, PDF 를 한 개당 10MB까지 올릴 수 있습니다
            </Typography>
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary">첨부된 파일이 없습니다.</Typography>
        )
      ) : (
        <Box sx={{ display: "grid", gap: 2 }}>
          {images.length > 0 ? (
            <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: "repeat(auto-fill, minmax(9rem, 1fr))" }}>
              {images.map((a, i) => (
                <Box key={a.id} sx={{ position: "relative", minWidth: 0 }}>
                  <Box
                    component="button"
                    type="button"
                    onClick={() => lb.open(slides, i)}
                    aria-label={a.filename + " 크게 보기"}
                    sx={{
                      p: 0, border: 0, background: "none", cursor: "zoom-in",
                      display: "block", width: "100%", minWidth: 0,
                      "&:focus-visible": { outline: "3px solid", outlineColor: "primary.main", outlineOffset: 2 },
                    }}
                  >
                    {/* contain 이다 — 사용자가 올린 이미지를 잘라 보여주지 않는다(§5). */}
                    <Box
                      component="img"
                      src={a.url}
                      alt={a.filename}
                      loading="lazy"
                      decoding="async"
                      sx={{
                        width: "100%", aspectRatio: "4 / 3", objectFit: "contain",
                        borderRadius: 2, border: 1, borderColor: "divider",
                        bgcolor: "action.hover", display: "block",
                      }}
                    />
                  </Box>
                  {canEdit ? (
                    <Tooltip title="이 첨부 떼기">
                      <IconButton
                        size="small"
                        onClick={() => askRemove(a)}
                        disabled={remove.isPending}
                        aria-label={a.filename + " 떼기"}
                        sx={{
                          position: "absolute", top: 4, right: 4,
                          bgcolor: "background.paper", boxShadow: 1,
                          "&:hover": { bgcolor: "background.paper" },
                        }}
                      >
                        <CloseRoundedIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  ) : null}
                  <Typography variant="caption" color="text.secondary"
                    sx={{ display: "block", mt: 0.5, overflowWrap: "anywhere" }}>
                    {a.filename}
                  </Typography>
                </Box>
              ))}
              <ImageLightbox {...lb.props} />
            </Box>
          ) : null}

          {files.length > 0 ? (
            <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.75 }}>
              {files.map((a) => (
                <Stack key={a.id} component="li" direction="row"
                  sx={{ alignItems: "center", gap: 1, minWidth: 0 }}>
                  <Link href={a.url} target="_blank" rel="noreferrer noopener" underline="hover"
                    sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
                    {a.filename}
                  </Link>
                  <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                    {humanSize(a.size_bytes)}
                  </Typography>
                  {canEdit ? (
                    <IconButton size="small" onClick={() => askRemove(a)} disabled={remove.isPending}
                      aria-label={a.filename + " 떼기"} sx={{ ml: "auto" }}>
                      <CloseRoundedIcon fontSize="small" />
                    </IconButton>
                  ) : null}
                </Stack>
              ))}
            </Box>
          ) : null}

          {canEdit && full ? (
            <Callout tone="warn">
              첨부가 {MAX_ATTACHMENTS}개로 꽉 찼습니다. 더 올리려면 하나를 먼저 떼세요.
            </Callout>
          ) : null}
        </Box>
      )}
    </Card>
  );
}
