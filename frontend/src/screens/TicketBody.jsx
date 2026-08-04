import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { BodyEditor, BodyPreview, BODY_MAX_LINES } from "../ui/BodyEditor.jsx";
import { Button, Callout, useConfirm, useToast } from "../ui/kit.jsx";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { DocBody } from "./TeamDoc.jsx";

/* 티켓 본문 읽기·편집 (계획 Phase 3 §E).
 *
 * 저장은 **정본(우리 DB) 먼저 → 원본(Notion) 그다음** 순서로 이뤄진다(서버). 그래서 이 화면이
 * 반드시 다뤄야 하는 상태가 하나 더 있다: **"저장은 됐는데 원본과 어긋남"**. 서버는 그때도
 * 200을 준다(사용자 글은 안전하므로 오류로 던지면 오히려 그 글이 롤백된다) — 그 대신 응답과
 * 상세 조회에 `body_sync_error`가 실려 온다. 여기서 그걸 조용히 넘기면 사용자는 원본이 갱신된
 * 줄 알고 회의에 들어간다. 그래서 배너 + 재시도 버튼을 띄우고, 그 상태에서는 **원본 블록 대신
 * 우리 정본을 그린다**(원본 블록은 낡았다는 걸 이미 알고 있다).
 *
 * 폭: 본문은 산문이라 78ch에서 멈춘다. 4K에서 남는 폭은 줄 길이가 아니라 옆 레일로 간다. */

const PROSE_SX = {
  maxWidth: PROSE_MAX_WIDTH,
  "& .doc-body": { fontSize: "1rem" },
  "& .doc-h1": { fontSize: "1.25rem" },
  "& .doc-h2": { fontSize: "1.0625rem" },
  "& .doc-h3": { fontSize: "1rem" },
  "& .doc-code, & .doc-unsupported": { fontSize: "0.875rem" },
};

export function lineCount(text) {
  return (text || "").split("\n").length;
}

/* 원본에 우리가 마크다운으로 표현할 수 없는 블록(이미지, 표, 컬럼…)이 있는가.
 * 2026-08 이전에는 저장이 그 블록을 지웠고 이 값은 '경고'용이었다. 지금은 지우지 않으므로
 * '위치가 앞으로 모인다'는 안내용이다 — 사라진다고 말하면 안 된다(사실이 아니다). */
export function hasUnsupportedBlocks(blocks) {
  return (blocks || []).some((b) => b && b.kind === "unsupported");
}

export function TicketBody({ ticketId, blocks, blocksError, bodyMarkdown, bodyIsLocal, bodySyncError, originalUrl, onSaved }) {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(bodyMarkdown || "");

  // 본문을 읽지 못했으면(blocks 실패) bodyMarkdown 은 null 이다. 그 상태로 편집기를 열면
  // 빈 칸이 뜨고, 저장이 곧 본문 삭제가 된다. 그래서 편집 자체를 막는다.
  const canEdit = bodyMarkdown != null;
  const tooManyLines = lineCount(draft) > BODY_MAX_LINES;
  const lossy = hasUnsupportedBlocks(blocks);

  const save = useMutation({
    mutationFn: (body) => api("/api/tickets/" + ticketId + "/body", {
      method: "PUT", body: { body_markdown: body },
    }),
    onSuccess: (res) => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["tickets"], refetchType: "all" });
      if (res && res.synced === false) {
        // 절반의 성공을 성공으로 보고하지 않는다.
        toast("본문은 저장했지만 원본(Notion) 반영에 실패했습니다. 아래에서 다시 시도할 수 있습니다.", "error");
      } else {
        toast("본문을 저장했습니다.", "success");
      }
      if (onSaved) onSaved();
    },
    onError: (e) => toast((e && e.message) || "본문을 저장하지 못했습니다.", "error"),
  });

  const startEditing = () => { setDraft(bodyMarkdown || ""); setEditing(true); };
  const cancel = async () => {
    if (draft !== (bodyMarkdown || "")) {
      const ok = await confirm("편집한 내용을 버립니다. 계속할까요?", { title: "편집 취소", confirmLabel: "버리기", danger: true });
      if (!ok) return;
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <Box sx={{ maxWidth: PROSE_MAX_WIDTH }}>
        <Stack direction="row" gap={1} sx={{ alignItems: "center", mb: 1.5, flexWrap: "wrap" }}>
          <Typography component="h2" variant="h6" sx={{ fontSize: "1rem", flex: 1 }}>본문 편집</Typography>
          <Button size="sm" onClick={cancel} disabled={save.isPending}>취소</Button>
          <Button size="sm" variant="primary" disabled={save.isPending || tooManyLines}
            onClick={() => save.mutate(draft)}>
            {save.isPending ? "저장 중…" : "저장"}
          </Button>
        </Stack>
        {/* 아직 우리 정본이 없는 본문(=원본에서 읽어온 근사치)을 여기서 저장하면 평문만 남는다.
            정본이 생긴 뒤에는 저장이 무손실이라 경고하지 않는다 — 늘 경고하면 아무도 안 읽는다. */}
        {/* 2026-08: 저장이 더 이상 이미지·표를 지우지 않는다(app/tickets/notion_write.py의
            replace_page_body). 그래서 "사라집니다"라는 옛 경고를 실제 동작에 맞춰 고쳤다 —
            틀린 경고는 안 읽히는 데서 끝나지 않고, 되는 일을 안 된다고 믿게 만든다. */}
        {!bodyIsLocal ? (
          <Box sx={{ mb: 1.5 }}>
            <Callout tone="warn">
              이 본문은 원본(Notion)에서 읽어온 것입니다. 여기서 저장하면 굵게, 링크 같은 인라인
              서식은 사라지고 글자만 남습니다. 서식을 지키려면 ‘원본 열기’에서 편집하세요.
            </Callout>
          </Box>
        ) : null}
        {lossy ? (
          <Box sx={{ mb: 1.5 }}>
            <Callout tone="info">
              원본에 이 편집기가 다루지 않는 블록(이미지, 표 등)이 있습니다. 저장해도
              그 블록은 지워지지 않습니다. 다만 원본에서의 위치는 글 앞쪽으로 모입니다.
            </Callout>
          </Box>
        ) : null}
        {tooManyLines ? (
          <Box sx={{ mb: 1.5 }}>
            <Callout tone="danger">
              본문은 최대 {BODY_MAX_LINES}줄까지 저장할 수 있습니다(현재 {lineCount(draft)}줄).
              줄 수를 줄여야 저장할 수 있습니다.
            </Callout>
          </Box>
        ) : null}
        <BodyEditor id={"ticket-body-" + ticketId} value={draft} onChange={setDraft} rows={14}
          placeholder="본문을 입력하세요. 제목, 글머리, 번호, 구분선을 쓸 수 있습니다." />
      </Box>
    );
  }

  return (
    <Box>
      <Stack direction="row" gap={1} sx={{ alignItems: "center", mb: 1.5, flexWrap: "wrap" }}>
        <Typography component="h2" variant="h6" sx={{ fontSize: "1rem", flex: 1 }}>본문</Typography>
        <Button size="sm" onClick={startEditing} disabled={!canEdit}>본문 편집</Button>
      </Stack>
      {!canEdit ? (
        <Box sx={{ mb: 1.5, maxWidth: PROSE_MAX_WIDTH }}>
          <Callout tone="warn">
            본문을 불러오지 못해 편집할 수 없습니다. 지금 저장하면 원본 본문을 지우게 되므로
            편집을 막았습니다. 새로고침하거나 ‘원본 열기’에서 편집하세요.
          </Callout>
        </Box>
      ) : null}
      {bodySyncError ? (
        <Box sx={{ mb: 1.5, maxWidth: PROSE_MAX_WIDTH }}>
          <Callout tone="warn">
            <Box sx={{ display: "grid", gap: 1 }}>
              <span>
                본문은 저장되었지만 원본(Notion)에 반영하지 못했습니다: {bodySyncError}.
                아래 내용이 우리 쪽 정본이며, 원본에는 아직 이전 내용이 남아 있습니다.
              </span>
              <Box>
                {/* 정본이 없으면 재시도가 곧 '빈 본문 밀어넣기'가 된다. 여기서는 논리상
                    일어날 수 없지만(sync 오류는 정본 저장 뒤에만 생긴다) 막아 둔다. */}
                <Button size="sm" disabled={save.isPending || bodyMarkdown == null}
                  onClick={() => save.mutate(bodyMarkdown)}>
                  {save.isPending ? "동기화 중…" : "원본에 다시 반영"}
                </Button>
              </Box>
            </Box>
          </Callout>
        </Box>
      ) : null}
      {bodySyncError ? (
        /* 원본 블록은 낡았다는 걸 이미 안다 — 우리 정본을 그린다. */
        <BodyPreview text={bodyMarkdown} />
      ) : (
        <Box sx={PROSE_SX}>
          <DocBody blocks={blocks} blocksError={blocksError} originalUrl={originalUrl} />
        </Box>
      )}
    </Box>
  );
}
