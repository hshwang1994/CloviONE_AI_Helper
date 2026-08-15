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
import { FONT_SIZE } from "../ui/theme.js";
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
       검사가 서로를 못 보고 통과해 상한을 넘긴다(각자 "지금 9개니까 괜찮다"고 판단한다).
       인자는 `FileList` 가 아니라 **이미 배열로 뜬 스냅샷**이다 — 이유는 `pick` 참고. */
    mutationFn: async (picked) => {
      for (const f of picked) {
        if (f.size > MAX_BYTES) {
          throw new Error(`${f.name} 은(는) 10MB를 넘습니다.`);
        }
      }
      // ATT-01: 파일별로 실패를 감싼다 — 안 그러면 N번째 업로드가 실패했을 때 이미 서버에
      // 저장된 앞의 N-1개가 있는데도 mutation 전체가 reject돼 onSuccess(→refresh)가 안 돌아
      // 화면 목록이 그대로다. "안 올라갔나 보다"로 같은 파일을 다시 고르면 중복 업로드되고
      // 10칸 상한만 스스로 소모한다(Board.jsx가 같은 사고를 겪고 이미 이 방식으로 고쳤다).
      const failed = [];
      for (const f of picked) {
        try {
          const fd = new FormData();
          fd.append("file", f);
          await api(`/api/tickets/${ticketId}/attachments`, { method: "POST", body: fd });
        } catch (e) {
          failed.push(f.name);
        }
      }
      return { failed };
    },
    onSuccess: ({ failed }) => {
      refresh();
      if (failed.length) {
        toast(`첨부 ${failed.length}개를 올리지 못했습니다: ${failed.join(", ")}`, "error");
      } else {
        toast("파일을 첨부했습니다.", "success");
      }
    },
    onError: (e) => toast((e && e.message) || "첨부하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const remove = useMutation({
    mutationFn: (attachmentId) =>
      api(`/api/tickets/attachments/${attachmentId}`, { method: "DELETE" }),
    onSuccess: () => { toast("첨부를 뗐습니다.", "success"); refresh(); },
    onError: (e) => toast((e && e.message) || "떼지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  /* 파일이 들어오는 문은 여기 하나다 — 버튼으로 고르든 끌어다 놓든 같은 판정을 지난다.
     둘로 갈라 두면 한쪽에만 상한 검사를 빠뜨리게 된다. */
  const pick = (fileList) => {
    /* **동기적으로** 배열로 뜬다. `FileList` 는 살아 있는 목록이고, 바로 아래 onChange 가
       같은 틱에서 `input.value = ""` 로 입력을 비운다 — HTML 표준상 value 에 빈 문자열을
       넣으면 선택 파일 목록을 **그 자리에서** 비운다(새 목록으로 바뀌는 게 아니다).
       업로드는 mutationFn 안에서 마이크로태스크 뒤에 도는 비동기라, 참조를 그대로 넘기면
       그때는 0개다. 그래서 아무것도 안 올라가는데 "파일을 첨부했습니다" 토스트만 떴다 —
       사용자가 "첨부 추가 버튼이 동작하지 않는다"고 말한 것이 이 증상이다.
       드래그는 `dataTransfer.files` 를 아무도 비우지 않아 멀쩡했다: 같은 화면에서 버튼만
       죽고 드래그만 살아 보인 이유가 정확히 이것이다. */
    const picked = Array.from(fileList || []);
    if (picked.length === 0) return;
    if (list.length + picked.length > MAX_ATTACHMENTS) {
      toast(`첨부는 최대 ${MAX_ATTACHMENTS}개까지 올릴 수 있습니다.`, "error");
      return;
    }
    upload.mutate(picked);
  };

  const openPicker = () => { if (inputRef.current) inputRef.current.click(); };

  const askRemove = async (att) => {
    const ok = await confirm(`${att.filename} 을(를) 이 티켓에서 뗍니다. 계속할까요?`,
      { title: "첨부 삭제", confirmLabel: "떼기", danger: true });
    if (ok) remove.mutate(att.id);
  };

  return (
    <Card>
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 1.5, gap: 1, flexWrap: "wrap" }}>
        <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle }}>
          첨부 {list.length > 0 ? `(${list.length})` : ""}
        </Typography>
        {canEdit ? (
          <Button onClick={openPicker} disabled={upload.isPending || full}>
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

      {/* 권한이 없으면 **왜 없는지**를 말한다. 예전에는 버튼과 숨은 입력이 통째로 사라졌는데,
          이유 없이 없어진 버튼은 권한 안내가 아니라 고장으로 읽힌다("추가 버튼이 동작하지
          않는다"는 보고의 절반이 이것이었다). 문구는 서버 판정(app/tickets/service.py
          `ensure_can_edit`)과 같은 선이다 — 한쪽만 고치면 화면이 거짓말을 하게 된다. */}
      {!canEdit ? (
        <Callout tone="info">
          이 티켓의 담당자가 아니라 첨부를 올리거나 뗄 수 없습니다. 담당자이거나 담당자가 아직
          없는 티켓만 수정할 수 있습니다. 파일을 붙이고 떼는 것도 티켓을 고치는 일입니다.
        </Callout>
      ) : null}

      {list.length === 0 && !canEdit ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
          첨부된 파일이 없습니다.
        </Typography>
      ) : null}

      {list.length > 0 ? (
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

        </Box>
      ) : null}

      {/* 끌어다 놓는 판은 **항상** 목록 아래 같은 자리에 있다. 예전에는 첨부가 0건일 때만
          그렸는데, 한 장 붙는 순간 드래그가 아무 데도 안 걸려 "처음엔 되던 게 갑자기 안
          된다"가 됐다(사용자가 "두 개 고른 뒤 드래그하면 올라간다"고 말한 것의 뒷면이다).
          꽉 찼을 때도 치우지 않고 남긴다 — 사라진 판은 이유를 말해 주지 못한다. */}
      {canEdit ? (
        <Box
          data-testid="attachment-dropzone"
          component="button"
          type="button"
          disabled={upload.isPending}
          onClick={() => { if (!upload.isPending) openPicker(); }}
          onDragOver={(e) => { e.preventDefault(); if (!upload.isPending) setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            /* 첫 배치가 아직 순차 업로드 중(upload.isPending)이면 이 두 번째 배치는 받지
               않는다. 안 막으면 두 pick 호출이 서로 다른 뮤테이션 실행이 되어, 각자 아직
               갱신되지 않은 옛 list.length 만 보고 "상한 안 넘는다"고 판단한다 — 위 upload
               뮤테이션 주석이 "동시에 던지면"이라 부르는 바로 그 경쟁이 pick 호출 두 개
               사이에서 재현된다. */
            if (upload.isPending) return;
            pick(e.dataTransfer.files);
          }}
          sx={{
            display: "grid", placeItems: "center", gap: 0.5, py: 3, px: 2, width: "100%",
            mt: list.length > 0 ? 2 : 0, font: "inherit", color: "inherit",
            border: 1, borderStyle: "dashed", borderRadius: 2,
            borderColor: dragging ? "primary.main" : "divider",
            bgcolor: dragging ? "action.hover" : "transparent",
            cursor: full || upload.isPending ? "not-allowed" : "pointer",
            transition: "border-color .16s, background-color .16s",
            "&:focus-visible": { outline: "3px solid", outlineColor: "primary.main", outlineOffset: 2 },
          }}
        >
          {full ? (
            <Typography variant="body2" color="text.secondary">
              첨부가 {MAX_ATTACHMENTS}개로 꽉 찼습니다. 더 올리려면 하나를 먼저 떼세요.
            </Typography>
          ) : upload.isPending ? (
            <Typography variant="body2" color="text.secondary">
              올리는 중입니다. 끝난 뒤 다시 끌어다 놓으세요.
            </Typography>
          ) : (
            <>
              <Typography variant="body2" color="text.secondary">
                화면 캡처나 규격서를 여기에 끌어다 놓으세요. 눌러서 고를 수도 있습니다.
              </Typography>
              <Typography variant="caption" color="text.secondary">
                PNG, JPEG, GIF, WebP, PDF 를 한 개당 10MB까지 올릴 수 있습니다
              </Typography>
            </>
          )}
        </Box>
      ) : null}
    </Card>
  );
}
