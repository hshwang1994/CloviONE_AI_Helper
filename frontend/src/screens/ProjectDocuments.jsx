import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Button, Card, DataTable, EmptyState, ErrorState, Modal, ModalFooter, Skeleton, useToast,
} from "../ui/kit.jsx";
import { TagPicker } from "../ui/TagPicker.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { fmtDateTimeCompact } from "../lib/format.js";

/* 프로젝트에 걸린 문서 — 프로젝트 상세의 「문서」 탭 (§14.3).
 *
 * 새 API 를 만들지 않는다. `GET /api/knowledge/documents?project_id=` 를 그대로 쓴다 —
 * 권한 계약(그 프로젝트를 볼 수 있는 사람 = 그 문서를 볼 수 있는 사람)을 한 벌로 유지한다
 * (§11.4). 문서 목록 화면(`Knowledge.jsx`)의 표 구성과 다른 이유는, 여기서는 "어느
 * 프로젝트인가"가 이미 정해져 있어 프로젝트 열이 정보가 아니라 잉크 무게이기 때문이다.
 */
/* 한 번에 받는 문서 수. 서버 상한은 이보다 크지만(`service.PAGE_MAX`), 이 탭은 쪽을
 * 넘기지 않으므로 **받은 만큼이 곧 보이는 전부**다. 그래서 그 사실을 숨기지 않는다 —
 * 아래에서 `total` 과 견줘 「몇 건 중 몇 건」을 말한다. */
const DOC_PAGE_SIZE = 100;

function useProjectDocuments(projectId) {
  return useQuery({
    queryKey: ["knowledge", "documents", "by-project", projectId],
    queryFn: () => api(`/api/knowledge/documents?project_id=${projectId}&limit=${DOC_PAGE_SIZE}`),
    enabled: Boolean(projectId),
  });
}

/* 돌아올 자리에 **탭까지** 싣는다 — 프로젝트 경로만 넘기면 문서에서 나온 사람이 개요
 * 탭으로 떨어져, 방금 보던 문서 목록을 다시 찾아 눌러야 했다(`ProjectTickets.jsx` 참고). */
function backToDocsTab(projectId) {
  return "/projects/" + encodeURIComponent(projectId) + "?tab=documents";
}

function NewProjectDocumentModal({ open, onClose, onSubmit, busy, projectId }) {
  const [title, setTitle] = React.useState("");
  const [tags, setTags] = React.useState([]);
  React.useEffect(() => { if (open) { setTitle(""); setTags([]); } }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="이 프로젝트에 문서 추가"
      dirty={Boolean(title.trim())}
      footer={(
        <ModalFooter
          onCancel={onClose}
          onSubmit={() => onSubmit({ project_id: projectId, title: title.trim(), tag_names: tags })}
          disabled={!title.trim()}
          submitLabel="추가"
          busy={busy}
        />
      )}
    >
      <Stack spacing={2}>
        <TextField
          label="문서 제목"
          required
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          inputProps={{ maxLength: 500 }}
          InputLabelProps={{ shrink: true }}
          fullWidth
        />
        <TagPicker value={tags} onChange={setTags} />
      </Stack>
    </Modal>
  );
}

export function ProjectDocuments({ projectId }) {
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const documents = useProjectDocuments(projectId);
  const [newDoc, setNewDoc] = React.useState(false);

  const createDocument = useMutation({
    mutationFn: (body) => api("/api/knowledge/documents", { method: "POST", body }),
    onSuccess: (doc) => {
      qc.invalidateQueries({ queryKey: ["knowledge", "documents", "by-project", projectId] });
      setNewDoc(false);
      navigate(`/knowledge/${doc.id}`, { state: { from: backToDocsTab(projectId) } });
    },
    onError: (e) => toast(e.message, "error"),
  });

  const openDoc = (doc) => navigate(`/knowledge/${doc.id}`, { state: { from: backToDocsTab(projectId) } });

  const columns = React.useMemo(() => [
    {
      key: "title", label: "제목", type: "title", minWidth: "16rem", rowName: (d) => d.title,
      render: (doc) => (
        <Box sx={{ display: "grid", gap: 0.25, minWidth: 0 }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
            {doc.title}
          </Typography>
          {(doc.tags || []).length > 0 ? (
            <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", rowGap: 0.5, mt: 0.25 }}>
              {(doc.tags || []).map((t) => <Chip key={t.id} size="small" label={t.name} />)}
            </Stack>
          ) : null}
        </Box>
      ),
    },
    {
      key: "author", label: "작성자", type: "name", minWidth: "8rem",
      render: (doc) => (
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
          <UserAvatar person={doc.author} size="sm" />
          <Typography variant="body2" sx={KO_WORD_BREAK}>{doc.author?.display_name || "-"}</Typography>
        </Stack>
      ),
    },
    {
      key: "updated_at", label: "최종 수정", type: "datetime", minWidth: "9rem",
      render: (doc) => fmtDateTimeCompact(doc.updated_at),
    },
  ], []);

  if (documents.isLoading) return <Card><Skeleton lines={4} /></Card>;
  if (documents.isError) {
    return <ErrorState error={documents.error} onRetry={() => documents.refetch()} />;
  }

  const rows = documents.data?.items || [];
  /* 응답은 `total` 을 함께 준다(app/knowledge/router.py::list_documents — 그 docstring 이
     「N번째 뒤에 문서가 더 있다는 사실이 사용자에게 보여야 한다」고 못 박아 둔 값이다).
     한때 이 탭은 그 값을 읽지도 그리지도 않았고 쪽을 넘길 수단도 없었다 — 상한을 넘긴
     프로젝트의 문서는 화면에서 조용히 사라졌고, 오류도 빈 자리도 안 남았다. */
  const total = typeof documents.data?.total === "number" ? documents.data.total : rows.length;
  const hidden = Math.max(0, total - rows.length);

  return (
    <Stack spacing={2}>
      <Stack direction="row" gap={2} sx={{ flexWrap: "wrap", alignItems: "center" }}>
        <Typography variant="body2" color="text.secondary" aria-live="polite" sx={{ flex: 1 }}>
          {hidden
            ? "총 " + total + "건 가운데 " + rows.length + "건을 보여 줍니다. 나머지는 문서 화면에서 찾을 수 있습니다."
            : "총 " + total + "건"}
        </Typography>
        <Button variant="primary" onClick={() => setNewDoc(true)}>새 문서</Button>
      </Stack>
      {rows.length === 0 ? (
        <EmptyState
          title="이 프로젝트에 문서가 아직 없습니다."
          help="회의록이나 설계 문서를 여기에 모아 두면 프로젝트 안에서 바로 찾을 수 있습니다."
          action={<Button variant="primary" onClick={() => setNewDoc(true)}>이 프로젝트 문서 추가</Button>}
        />
      ) : (
        <Card>
          <DataTable columns={columns} rows={rows} rowKey={(d) => d.id} onRow={openDoc} />
        </Card>
      )}
      <NewProjectDocumentModal
        open={newDoc}
        projectId={projectId}
        busy={createDocument.isPending}
        onClose={() => setNewDoc(false)}
        onSubmit={(body) => createDocument.mutate(body)}
      />
    </Stack>
  );
}

export default ProjectDocuments;
