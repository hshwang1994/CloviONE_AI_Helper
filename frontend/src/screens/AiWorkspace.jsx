import React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  FormModal,
  PageHeader,
  Section,
  Skeleton,
  useToast,
  FieldLabel,
} from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, PROSE_MAX_WIDTH } from "../ui/theme.js";
import { PROJECT_NONE, navEntriesFrom } from "./knowledge/constants.js";
import { useAllProjects } from "./project-queries.js";

/* AI 작업공간 — 묻고, 근거를 보고, 그 자리로 간다 (S10).
 *
 * ## 답변보다 근거가 먼저다
 *
 * 이 화면의 기본 상태는 «찾은 문서 목록»이다. 답변은 그 위에 얹힌다. 순서를 반대로 두면
 * 사람이 답변만 읽고 근거를 안 본다 — 그리고 모델이 틀린 날 그 사실을 아무도 모른다.
 *
 * 그래서 «찾기»와 «묻기»가 **다른 단추**다. 찾기는 모델을 안 부르므로 생성이 막혀 있어도
 * 그대로 동작하고, 그 사실이 화면에서 보인다.
 *
 * ## 인용은 눌러서 그 문단까지 간다
 *
 * 주소는 서버가 준다(`citation.route` — `/knowledge/<id>?block=<블록 id>`). 화면이
 * `source_kind` 로 분기해 주소를 조립하지 않는다: 경로가 바뀌는 날 고쳐야 할 자리가
 * 화면 수만큼이 된다.
 *
 * ## 못 쓰는 기능을 숨기지 않는다
 *
 * 모델이 없으면 그 사실과 **운영자가 무엇을 해야 하는지**를 말한다. 단추만 조용히 사라지면
 * 사용자는 기능이 없는 줄 안다. */

const STATUS_KEY = ["ai", "status"];

function useAiStatus() {
  return useQuery({ queryKey: STATUS_KEY, queryFn: () => api("/api/ai/status") });
}

/* 인용 한 건. **본문 미리보기를 접어 둔다** — 여덟 건이 전부 펼쳐져 있으면 답변이 화면
 * 밖으로 밀려나고, 그러면 근거를 먼저 보여 준 뜻이 없어진다. */
function Citation({ index, citation, onOpen }) {
  return (
    <Card>
      <Stack direction="row" spacing={1.5} alignItems="flex-start">
        <Chip
          label={index}
          size="small"
          sx={{ fontWeight: FONT_WEIGHT.semibold, minWidth: "2rem" }}
        />
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
            {citation.document_title}
          </Typography>
          {citation.where ? (
            <Typography
              sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}
            >
              {citation.where}
            </Typography>
          ) : null}
          {/* 찾은 낱말이 하나도 없는데 나온 문서다. 안 알려 주면 사람은 검색이 엉뚱한
              것을 물어 왔다고 생각한다 — 판정은 서버가 한다(fusion.semantic_only). */}
          {citation.semantic_only ? (
            <Typography
              sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}
            >
              낱말은 다르지만 뜻이 가까워 찾았습니다.
            </Typography>
          ) : null}
          <Typography
            component="p"
            sx={{
              mt: 1, fontSize: FONT_SIZE.bodySm, color: "text.secondary",
              maxWidth: PROSE_MAX_WIDTH, ...KO_WORD_BREAK,
            }}
          >
            {citation.excerpt}
          </Typography>
          <Box sx={{ mt: 1 }}>
            <Button size="small" onClick={() => onOpen(citation.route)}>
              문서에서 보기
            </Button>
          </Box>
        </Box>
      </Stack>
    </Card>
  );
}

function Answer({ result }) {
  if (!result) return null;
  if (!result.answer) {
    /* 🔴 생성이 막혀 있어도 근거는 그대로 나간다. 그 사실을 여기서 말한다 — 안 그러면
       사용자는 검색까지 고장 난 줄 안다. */
    return (
      <Callout tone="info">
        {result.notice} 찾은 문서는 아래에 그대로 있습니다.
      </Callout>
    );
  }
  return (
    <Card>
      <Typography
        component="p"
        sx={{ whiteSpace: "pre-wrap", maxWidth: PROSE_MAX_WIDTH, ...KO_WORD_BREAK }}
      >
        {result.answer}
      </Typography>
      <Typography
        sx={{ mt: 1.5, fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}
      >
        아래 문서에서 찾은 내용으로 답했습니다. 번호를 눌러 원문을 확인해 주세요.
      </Typography>
    </Card>
  );
}

export function AiWorkspace() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const status = useAiStatus();
  /* 초안이 앉을 자리는 **프로젝트**다 — 새 문서 대화상자와 같은 축·같은 후보다.
     🔴 예전에는 「공간」 목록이었고 `space_id` 가 **필수**였다. 그래서 이 경로만
     프로젝트 없이는 초안을 못 만들었고, 아직 공간이 없는 프로젝트는 후보에도 없었다. */
  const projectsList = useAllProjects();
  const draftTargets = React.useMemo(
    () => navEntriesFrom(projectsList.rows),
    [projectsList.rows],
  );
  const [draft, setDraft] = React.useState(params.get("q") || "");
  const [result, setResult] = React.useState(null);
  const [drafting, setDrafting] = React.useState(false);

  const capabilities = status.data?.capabilities;
  const canAsk = Boolean(capabilities?.generate?.available);
  // 한도가 있을 때만 오늘 쓴 양을 보인다(계획 3.10) - 채팅 화면과 같은 값(`/api/me/ai-quota`)을 읽는다.
  const quota = useQuery({ queryKey: ["ai-quota-self"], queryFn: () => api("/api/me/ai-quota"), retry: false });
  const quotaDay = quota.data && Array.isArray(quota.data.periods)
    ? quota.data.periods.find((p) => p.period === "day") : null;
  const semanticOff = capabilities && !capabilities.embed.available;

  const search = useMutation({
    mutationFn: (q) => api(`/api/ai/search?q=${encodeURIComponent(q)}`),
    onSuccess: (data) => setResult(data),
  });
  const ask = useMutation({
    mutationFn: (question) => api("/api/ai/ask", { method: "POST", body: { question } }),
    onSuccess: (data) => setResult(data),
  });
  const makeDocument = useMutation({
    mutationFn: (body) => api("/api/ai/documents", { method: "POST", body }),
    onSuccess: (data) => {
      /* 쓰기 승인 정책이 걸려 있으면 문서 대신 승인 요청이 생긴다(D-519). 초안은 만들어졌으니 모달을 닫고, 진행은
         내 승인 화면의 「내가 올린 요청」에서 본다. */
      if (data.approval) {
        setDrafting(false);
        toast("초안을 만들어 승인을 요청했습니다. 승인되면 문서가 만들어집니다.");
        return;
      }
      /* 초안을 못 쓴 응답이면 모달을 닫지 않는다 — 그 이유는 폼 위 오류로 선다(아래 `onSubmit` 이
         던진다). 예전에는 모달을 닫고 사라지는 토스트로만 말했다. */
      if (!data.document) return;
      setDrafting(false);
      toast("초안 문서를 추가했습니다.");
      navigate(data.document.route);
    },
  });

  const busy = search.isPending || ask.isPending;
  const failure = search.error || ask.error;

  function run(kind) {
    const q = draft.trim();
    if (!q) return;
    setParams(q ? { q } : {}, { replace: true });
    setResult(null);
    (kind === "ask" ? ask : search).mutate(q);
  }

  if (status.isLoading) return <Skeleton kind="page" lines={4} />;
  if (status.error) return <ErrorState error={status.error} onRetry={status.refetch} />;

  return (
    <Box className="c-screen">
      <PageHeader
        area="AI"
        title="AI 작업공간"

        help="사내 문서에서 근거를 찾아 답하고, 그 근거가 어느 문서 어디인지 함께 보여 줍니다."
      />

      {semanticOff ? (
        <Callout tone="warn" detail={capabilities.embed.detail}>
          {capabilities.embed.notice} 지금은 낱말이 일치하는 문서만 찾습니다.
        </Callout>
      ) : null}

      <Card>
        <Stack
          component="form"
          direction={{ xs: "column", sm: "row" }}
          spacing={1.5}
          alignItems={{ sm: "flex-end" }}
          onSubmit={(event) => {
            event.preventDefault();
            run(canAsk ? "ask" : "search");
          }}
        >
          {/* 라벨은 칸 위에 선다(`FieldLabel`) — 칸 안으로 내려앉으면 값이 들어간 뒤 무엇을 묻는 칸이었는지 사라진다. */}
          <Box sx={{ minWidth: 0, flex: 1, width: "100%" }}>
            <FieldLabel htmlFor="ai-workspace-question">무엇을 찾고 있습니까?</FieldLabel>
            <TextField
              id="ai-workspace-question"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              fullWidth
              multiline
              maxRows={4}
            />
          </Box>
          <Stack direction="row" spacing={1}>
            <Button type="button" onClick={() => run("search")} disabled={busy || !draft.trim()}>
              문서 찾기
            </Button>
            {/* 못 쓰는 단추를 숨기지 않는다 — 왜 못 쓰는지는 위 안내가 말한다. */}
            <Button
              variant="primary"
              type="button"
              onClick={() => run("ask")}
              disabled={busy || !draft.trim() || !canAsk}
              loading={ask.isPending}
            >
              물어보기
            </Button>
          </Stack>
        </Stack>
        {!canAsk ? (
          <Typography
            sx={{ mt: 1.5, fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}
          >
            {capabilities.generate.notice} 문서 찾기는 그대로 쓸 수 있습니다.
          </Typography>
        ) : null}
        {canAsk && quotaDay && quotaDay.limit != null ? (
          <Typography sx={{ mt: 1, textAlign: "right", fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
            오늘 AI 사용량 {quotaDay.used}/{quotaDay.limit}
          </Typography>
        ) : null}
      </Card>

      {failure ? <ErrorState layout="region" error={failure} /> : null}
      {busy ? <Skeleton kind="section" lines={3} /> : null}

      {result ? (
        <Stack spacing={2}>
          <Answer result={result} />
          <Section
            title="근거 문서"
            action={
              result.citations.length && canAsk ? (
                <Button onClick={() => setDrafting(true)}>이 근거로 초안 쓰기</Button>
              ) : null
            }
          >
            {result.citations.length ? (
              <Stack spacing={1.5}>
                {result.citations.map((citation, index) => (
                  <Citation
                    key={citation.chunk_id}
                    index={index + 1}
                    citation={citation}
                    onOpen={(route) => navigate(route)}
                  />
                ))}
              </Stack>
            ) : (
              <EmptyState
                title="찾은 문서가 없습니다"
                help="다른 낱말로 다시 찾아보거나, 문서가 아직 색인되지 않았는지 확인해 주세요."
                art="search"
              />
            )}
          </Section>
        </Stack>
      ) : (
        <EmptyState
          layout="page"
          title="궁금한 것을 물어보세요"
          help="사내 문서에서 근거를 찾아 답합니다. 답에 쓰인 문서는 아래에 함께 나옵니다."
          art="search"
        />
      )}

      <FormModal
        open={drafting}
        title="문서 초안 쓰기"
        submitLabel="초안 쓰기"
        fields={[
          { name: "title", label: "문서 제목", type: "text", required: true, maxLength: 500 },
          {
            // 「공간」 낱말을 일반 사용자 화면에 쓰지 않는다(§11.2). 값도 이제 프로젝트다 —
            // 서버가 그 프로젝트의 공간을 찾거나 만들고, 미지정이면 조직 공통 공간을 쓴다.
            name: "project_id",
            label: "프로젝트",
            type: "select",
            options: draftTargets.map((e) => ({ value: e.value, label: e.label })),
          },
        ]}
        initial={{ title: draft.slice(0, 60), project_id: PROJECT_NONE }}
        onClose={() => setDrafting(false)}
        onSubmit={async (values) => {
          const data = await makeDocument.mutateAsync({
            title: values.title,
            /* 「프로젝트 미지정」은 아무것도 안 보낸다 — 서버의 기본 자리가 그것이다. */
            ...(values.project_id && values.project_id !== PROJECT_NONE
              ? { project_id: values.project_id }
              : {}),
            instruction: draft.trim(),
          });
          if (!data.document && !data.approval) throw new Error(data.notice || "초안을 쓰지 못했습니다.");
        }}
      />
    </Box>
  );
}

export default AiWorkspace;
