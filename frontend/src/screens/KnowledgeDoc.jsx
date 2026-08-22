import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Section,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";

/* 문서 한 건 — 본문 · 이력 · 차이 · 되돌리기 (S7 Exit).
 *
 * ## 편집기를 늦게 싣는다 (D-198)
 *
 * TipTap 과 ProseMirror 는 무겁다. 문서를 여는 사람만 받으면 되고, 목록만 보는 사람의
 * 첫 로딩에 그 무게를 얹을 이유가 없다. **`React.lazy` 로 들여오는 것이 계약이고**
 * `knowledge-editor-lazy.test.jsx` 가 그것을 코드로 확인한다 — 어느 날 누군가 정적
 * import 로 바꾸면 번들 예산이 조용히 넘어가고, 그때는 원인을 찾기 어렵다.
 *
 * ## 이력 화면이 「변경 없음」으로 차지 않게 한다
 *
 * 서버는 본문이 그대로면 판을 안 쌓고 `created_version: false` 로 답한다. 그 사실을
 * 화면이 구별해서 말한다 — 「저장했습니다」와 「저장했고 이력에 남겼습니다」는 다른 일이다.
 *
 * ## 되돌리기는 잠금 값을 함께 보낸다
 *
 * 되돌리기는 남의 편집을 통째로 덮는 동작이다. 이력을 열어 둔 사이에 누군가 저장했으면
 * 서버가 409 로 막고, 화면은 그 사실을 그대로 전한다 — 조용히 덮으면 사라진 사람은
 * 자기 글이 사라진 것도 모른다. */

const BlockEditor = React.lazy(() =>
  import("../ui/BlockEditor.jsx").then((m) => ({ default: m.BlockEditor })));

const CHANGE_LABEL = {
  added: "추가",
  removed: "삭제",
  changed: "수정",
  moved: "이동",
};

const CHANGE_TONE = {
  added: "ok",
  removed: "danger",
  changed: "info",
  moved: "neutral",
};

function useDocument(id) {
  return useQuery({
    queryKey: ["knowledge", "document", id],
    queryFn: () => api(`/api/knowledge/documents/${id}`),
    enabled: Boolean(id),
  });
}

function useVersions(id) {
  return useQuery({
    queryKey: ["knowledge", "versions", id],
    queryFn: () => api(`/api/knowledge/documents/${id}/versions`),
    enabled: Boolean(id),
  });
}

function VersionDiff({ documentId, base, target }) {
  const diff = useQuery({
    queryKey: ["knowledge", "diff", documentId, base, target],
    queryFn: () =>
      api(`/api/knowledge/documents/${documentId}/diff?base=${base}&target=${target}`),
    enabled: Boolean(documentId && base && target),
  });

  if (diff.isLoading) return <Skeleton kind="section" lines={4} />;
  if (diff.isError) return <ErrorState error={diff.error} onRetry={() => diff.refetch()} />;

  const changes = diff.data?.changes || [];
  if (!changes.length) {
    return (
      <EmptyState
        title="두 판의 본문이 같습니다."
        body="고른 두 판 사이에 바뀐 문단이 없습니다."
      />
    );
  }

  return (
    <Stack spacing={1} component="ul" sx={{ listStyle: "none", p: 0, m: 0 }}>
      {changes.map((change) => (
        <Box
          key={`${change.block_id}-${change.change}`}
          component="li"
          sx={(theme) => ({
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: 1,
            p: 1.5,
          })}
        >
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <Badge value={CHANGE_LABEL[change.change] || change.change}
                   kind={CHANGE_TONE[change.change]} />
          </Stack>
          {change.before && (
            <Typography sx={{ ...KO_WORD_BREAK, textDecoration: "line-through" }}
                        color="text.secondary">
              {change.before}
            </Typography>
          )}
          {change.after && (
            <Typography sx={KO_WORD_BREAK}>{change.after}</Typography>
          )}
        </Box>
      ))}
    </Stack>
  );
}

export function KnowledgeDoc() {
  const { id } = useParams();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();

  const doc = useDocument(id);
  const versions = useVersions(id);

  const [tab, setTab] = React.useState(0);
  const [title, setTitle] = React.useState("");
  const [body, setBody] = React.useState(null);
  const [compareTo, setCompareTo] = React.useState(null);

  /* 서버가 준 값을 편집 상태의 출발점으로 삼는다. 문서 id 가 바뀔 때만 다시 잡는다 —
   * 매 응답마다 덮으면 사용자가 타이핑하는 중에 화면이 되감긴다. */
  React.useEffect(() => {
    if (!doc.data) return;
    setTitle(doc.data.title);
    setBody(doc.data.current?.body || null);
    setCompareTo(null);
  }, [doc.data?.id]);

  const save = useMutation({
    mutationFn: (payload) =>
      api(`/api/knowledge/documents/${id}`, { method: "PUT", body: payload }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["knowledge", "document", id] });
      qc.invalidateQueries({ queryKey: ["knowledge", "versions", id] });
      toast.show(
        result.created_version
          ? "저장했고 새 판을 이력에 남겼습니다."
          : "저장했습니다. 본문이 그대로라 새 판은 만들지 않았습니다.",
      );
    },
    onError: (e) => toast.show(e.message, "error"),
  });

  const restore = useMutation({
    mutationFn: (versionNo) =>
      api(`/api/knowledge/documents/${id}/versions/${versionNo}/restore`, {
        method: "POST",
        body: { base_version: doc.data?.version },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["knowledge", "document", id] });
      qc.invalidateQueries({ queryKey: ["knowledge", "versions", id] });
      toast.show("옛 판의 본문으로 새 판을 만들었습니다. 이력은 그대로 남아 있습니다.");
    },
    onError: (e) => toast.show(e.message, "error"),
  });

  if (doc.isLoading) return <Skeleton kind="page" lines={5} />;
  if (doc.isError) return <ErrorState error={doc.error} onRetry={() => doc.refetch()} />;

  const current = doc.data.current || {};
  const history = versions.data?.items || [];

  return (
    <>
      <PageHeader
        area="지식 공간"
        title={doc.data.title}
        actions={
          <Button
            variant="primary"
            loading={save.isPending}
            onClick={() => save.mutate({ title, body, base_version: doc.data.version })}
          >
            저장
          </Button>
        }
      />

      <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="본문" />
        <Tab label={`이력 ${history.length}건`} />
      </Tabs>

      {tab === 0 && (
        <Card>
          <Stack spacing={2}>
            <TextField
              label="문서 제목"
              InputLabelProps={{ shrink: true }}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              inputProps={{ maxLength: 500 }}
              fullWidth
            />
            <React.Suspense fallback={<Skeleton kind="section" lines={6} />}>
              <BlockEditor value={body} onChange={setBody} />
            </React.Suspense>
          </Stack>
        </Card>
      )}

      {tab === 1 && (
        <Stack spacing={2}>
          <Card>
            <Section title="판 이력">
              {versions.isLoading && <Skeleton kind="list" rows={4} />}
              {versions.isError && (
                <ErrorState error={versions.error} onRetry={() => versions.refetch()} />
              )}
              {!versions.isLoading && history.length === 0 && (
                <EmptyState
                  title="아직 판이 없습니다."
                  body="본문을 저장하면 판이 하나씩 쌓입니다."
                />
              )}
              <Stack spacing={1} component="ul" sx={{ listStyle: "none", p: 0, m: 0 }}>
                {history.map((version) => {
                  const isCurrent = version.version_no === versions.data?.current_version_no;
                  return (
                    <Box
                      key={version.id}
                      component="li"
                      sx={(theme) => ({
                        border: `1px solid ${theme.palette.divider}`,
                        borderRadius: 1,
                        p: 1.5,
                      })}
                    >
                      <Stack
                        direction={{ xs: "column", sm: "row" }}
                        spacing={1}
                        alignItems={{ sm: "center" }}
                      >
                        <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, minWidth: "4rem" }}>
                          {version.version_no}판
                        </Typography>
                        {isCurrent && <Badge value="지금 보는 판" kind="info" />}
                        {version.source === "RESTORE" && <Badge value="되돌림" kind="neutral" />}
                        {version.ai_used && <Badge value="AI 사용" kind="neutral" />}
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{ ...KO_WORD_BREAK, flex: 1, minWidth: 0 }}
                        >
                          {version.change_reason || "사유를 적지 않았습니다."}
                        </Typography>
                        <Stack direction="row" spacing={1}>
                          <Button
                            size="small"
                            disabled={isCurrent}
                            onClick={() => setCompareTo(version.version_no)}
                          >
                            지금 판과 비교
                          </Button>
                          <Button
                            size="small"
                            disabled={isCurrent}
                            loading={restore.isPending}
                            onClick={async () => {
                              const ok = await confirm(
                                "지금 본문을 지우지 않습니다. 옛 판의 내용으로 새 판을"
                                + " 하나 더 쌓고, 이력은 그대로 남습니다.",
                                {
                                  title: `${version.version_no}판으로 되돌릴까요?`,
                                  confirmLabel: "되돌리기",
                                },
                              );
                              if (ok) restore.mutate(version.version_no);
                            }}
                          >
                            되돌리기
                          </Button>
                        </Stack>
                      </Stack>
                    </Box>
                  );
                })}
              </Stack>
            </Section>
          </Card>

          {compareTo != null && versions.data?.current_version_no != null && (
            <Card>
              <Section
                title={`${compareTo}판과 ${versions.data.current_version_no}판의 차이`}
                action={<Button size="small" onClick={() => setCompareTo(null)}>닫기</Button>}
              >
                <VersionDiff
                  documentId={id}
                  base={compareTo}
                  target={versions.data.current_version_no}
                />
              </Section>
            </Card>
          )}
        </Stack>
      )}

      {current.version_no != null && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          지금 보고 있는 것은 {current.version_no}판입니다.
        </Typography>
      )}
    </>
  );
}

export default KnowledgeDoc;
