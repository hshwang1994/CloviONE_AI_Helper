import React from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { useAuth } from "../app/auth.jsx";
import { Badge, Button, Callout, Card, ErrorState, Skeleton, useToast } from "../ui/kit.jsx";
import { BodyPreview } from "../ui/BodyEditor.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { MILESTONE_STATUS_KO, PROJECT_WRITE_ROLES } from "./project-format.js";

/* 주간 리포트 탭.
 *
 * ## 주 이동을 화면이 계산하지 않는다
 *
 * 응답의 `window` 에 `prev_week` / `next_week` 가 들어 있다. 화면이 직접 월요일을 구하면
 * 주 경계 계산이 두 벌이 되고, 스프린트 회의 화면과 이 화면이 서로 다른 주를 '이번 주'라고
 * 부르는 순간 사용자는 둘 중 하나를 거짓말로 받아들인다(app/projects/weekly.py::Week).
 * 서버가 만든 값을 그대로 되돌려 보내기만 한다.
 *
 * ## 저장은 POST 만 한다
 *
 * 이 탭을 여는 것(GET)은 저장하지 않는다. GET 이 저장하면 새로고침할 때마다 `generated_at`
 * 이 움직여 "언제 만든 리포트인가"라는 질문 자체가 사라진다. 그래서 저장본이 없으면 없다고
 * 말하고, 저장은 버튼이 시킨다.
 */

const SECTIONS = [
  ["done", "이번 주 완료"],
  ["in_progress", "진행 중"],
  ["delayed", "지연"],
  ["issues", "이슈"],
  ["next_week", "다음 주 계획"],
];

const MILESTONE_BUCKETS = [
  ["changed", "이번 주에 바뀐 마일스톤"],
  ["due_this_week", "이번 주가 기한인 마일스톤"],
  ["overdue", "기한을 넘긴 마일스톤"],
];

/** 창의 **포함되는** 마지막 날. 계약은 배타적 끝이지만 사람에게는 포함으로 보여야 한다. */
export function inclusiveLastDay(endExclusive) {
  if (!endExclusive) return "";
  const d = new Date(endExclusive + "T00:00:00");
  if (Number.isNaN(d.getTime())) return endExclusive;
  d.setDate(d.getDate() - 1);
  const pad = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
}

function Bucket({ title, bucket, onOpen }) {
  const b = bucket || { count: 0, items: [] };
  const items = Array.isArray(b.items) ? b.items : [];
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography component="h3" sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold }}>
        {title + " " + (b.count || 0) + "건"}
      </Typography>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>없습니다.</Typography>
      ) : (
        <Box component="ul" sx={{ m: 0, mt: 1, p: 0, display: "grid", gap: 0.75 }}>
          {items.map((it) => (
            <Box component="li" key={it.id} sx={{ listStyle: "none", display: "flex", gap: 1, alignItems: "baseline", flexWrap: "wrap" }}>
              <Button
                variant="ghost" size="sm"
                onClick={() => onOpen(it)}
                sx={{ p: 0, minWidth: 0, textAlign: "left", ...KO_WORD_BREAK }}
              >
                {it.title || "제목 없음"}
              </Button>
              {it.status ? <Badge value={it.status} /> : null}
              <Typography variant="body2" color="text.secondary">
                {it.due ? "마감 " + it.due : "마감 없음"}
              </Typography>
            </Box>
          ))}
          {b.count > items.length ? (
            <Typography variant="body2" color="text.secondary">
              {"그 밖에 " + (b.count - items.length) + "건이 더 있습니다."}
            </Typography>
          ) : null}
        </Box>
      )}
    </Box>
  );
}

function MilestoneBucket({ title, bucket }) {
  const b = bucket || { count: 0, items: [] };
  const items = Array.isArray(b.items) ? b.items : [];
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography component="h3" sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold }}>
        {title + " " + (b.count || 0) + "건"}
      </Typography>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>없습니다.</Typography>
      ) : (
        <Box component="ul" sx={{ m: 0, mt: 1, p: 0, display: "grid", gap: 0.5 }}>
          {items.map((m) => (
            <Box component="li" key={m.id} sx={{ listStyle: "none", display: "flex", gap: 1, alignItems: "baseline", flexWrap: "wrap" }}>
              <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, ...KO_WORD_BREAK }}>{m.name}</Typography>
              <Typography variant="body2" color="text.secondary">
                {(m.due_on ? "기한 " + m.due_on : "기한 없음")
                  + ", " + (MILESTONE_STATUS_KO[m.status] || m.status)}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

export function ProjectWeekly({ projectId, week, onWeek, query }) {
  const nav = useNavigate();
  const auth = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const role = (auth.data && auth.data.role) || "";
  // 역할 목록은 project-format.js 한 곳이다. 화면마다 적으면 한쪽만 고쳐진다.
  const canWrite = PROJECT_WRITE_ROLES.includes(role);

  const save = useMutation({
    mutationFn: () => api(
      "/api/projects/" + encodeURIComponent(projectId) + "/weekly-report"
      + (week ? "?week=" + encodeURIComponent(week) : ""),
      { method: "POST" },
    ),
    onSuccess: () => {
      toast("주간 리포트를 저장했습니다.", "success");
      qc.invalidateQueries({ queryKey: ["projects", "one", projectId], refetchType: "all" });
    },
    onError: (e) => toast((e && e.message) || "주간 리포트를 저장하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  /* AI 요약 생성(§L). 여기서 결과를 기다리지 않는다 — CLI 왕복이 수십 초 걸릴 수 있어
   * 서버가 잡 큐로 넘긴다(app/jobs/handlers/project_weekly_summary.py). 그래서 이 버튼은
   * "요청했다"만 알리고, 실제로 됐는지는 사용자가 잠시 뒤 새로고침해서 `saved.source`
   * 로 확인한다 — 되는 척 진행 바를 그리지 않는다(정직한 상태만 보여준다는 이 화면의
   * 다른 문구들과 같은 규칙). */
  const generateLlm = useMutation({
    mutationFn: () => api(
      "/api/projects/" + encodeURIComponent(projectId) + "/weekly-report/llm-summary"
      + (week ? "?week=" + encodeURIComponent(week) : ""),
      { method: "POST" },
    ),
    onSuccess: () => toast("AI 요약 생성을 요청했습니다. 잠시 후 새로고침해서 확인하세요.", "success"),
    onError: (e) => toast((e && e.message) || "AI 요약 생성을 요청하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  if (query.isPending) return <Card><Skeleton lines={8} /></Card>;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  const data = query.data || {};
  const win = data.window || {};
  const basis = data.basis || {};
  const milestones = data.milestones || {};
  const openTicket = (it) => nav("/tickets/" + it.id, { state: { from: "/projects" } });

  return (
    <Stack gap={2.5}>
      <Card>
        <Stack direction="row" gap={1} sx={{ flexWrap: "wrap", alignItems: "center" }}>
          <Button size="sm" onClick={() => onWeek(win.prev_week || "")}>이전 주</Button>
          <Button size="sm" disabled={!week} onClick={() => onWeek("")}>이번 주</Button>
          <Button size="sm" onClick={() => onWeek(win.next_week || "")}>다음 주</Button>
          <Typography variant="body2" color="text.secondary" aria-live="polite" sx={{ ml: 1 }}>
            {win.start
              ? win.start + " ~ " + inclusiveLastDay(win.end_exclusive) + " (마감일 기준, Asia/Seoul)"
              : "기간을 알 수 없습니다."}
          </Typography>
        </Stack>
        {basis.tickets_linked === false ? (
          <Box sx={{ mt: 1.5 }}>
            <Callout tone="info">
              이 프로젝트에 걸린 작업이 없어 작업 기준 집계를 낼 수 없습니다. 아래 숫자는 전부 0건입니다.
            </Callout>
          </Box>
        ) : null}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5, ...KO_WORD_BREAK }}>
          {"작업 " + (basis.sample_tickets || 0) + "건, 마일스톤 "
            + (basis.sample_milestones || 0) + "건을 보고 만들었습니다."}
        </Typography>
      </Card>

      <Card>
        <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1.5 }}>이번 주 작업</Typography>
        <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" } }}>
          {SECTIONS.map(([key, title]) => (
            <Bucket key={key} title={title} bucket={data[key]} onOpen={openTicket} />
          ))}
        </Box>
      </Card>

      <Card>
        <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1.5 }}>마일스톤</Typography>
        <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" } }}>
          {MILESTONE_BUCKETS.map(([key, title]) => (
            <MilestoneBucket key={key} title={title} bucket={milestones[key]} />
          ))}
        </Box>
      </Card>

      <Card>
        <Stack direction="row" gap={1} sx={{ flexWrap: "wrap", alignItems: "center", mb: 1.5 }}>
          <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, flex: 1 }}>요약</Typography>
          {canWrite ? (
            <Button variant="primary" size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
              이 주 리포트 저장
            </Button>
          ) : null}
          {/* AI 요약이 꺼져 있으면(llm_notice가 있으면) 눌러도 규칙 요약만 다시 나오므로
              버튼을 안 보여준다 — 있는 기능처럼 보이고 안 되면 고장으로 읽힌다. */}
          {canWrite && !data.llm_notice ? (
            <Button size="sm" disabled={generateLlm.isPending} onClick={() => generateLlm.mutate()}>
              {generateLlm.isPending ? "요청하는 중…" : "AI 요약 생성"}
            </Button>
          ) : null}
        </Stack>
        {/* 규칙이 쓴 문장인지 모델이 쓴 문장인지 구별을 남긴다. 안 남기면 몇 주 뒤에 둘 다
            못 믿게 된다(app/projects/models.py::REPORT_SOURCES).
            GET 은 언제나 규칙 문장만 계산한다(§L, 웹에서 LLM 을 안 부른다) — 그래서 AI 가
            쓴 문장은 top-level summary_md 가 아니라 저장본(saved)에서만 온다. 저장본이
            AI 요약이면 그걸 보여주고, 아니면 지금 계산한 규칙 요약을 보여준다. */}
        {(() => {
          const savedIsLlm = data.saved && data.saved.source === "llm";
          const text = savedIsLlm ? data.saved.summary_md : (data.summary_md || "");
          return (
            <>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5, ...KO_WORD_BREAK }}>
                {savedIsLlm ? "AI 가 쓴 요약입니다(저장본)." : "규칙으로 만든 요약입니다."}
                {/* 🔴 **왜** 규칙 요약인지까지 말한다. 서버가 `llm_notice` 로 계산해 보내는데
                    화면이 안 그리면, 사용자는 AI 요약이 꺼져 있는지 고장 났는지 구분할 수 없다.
                    (실제로 서버에만 넣고 화면을 안 고친 채 "배선했다"고 적어 뒀던 자리다.) */}
                {!savedIsLlm && data.llm_notice ? " " + data.llm_notice : ""}
              </Typography>
              <BodyPreview text={text} wide />
            </>
          );
        })()}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5, ...KO_WORD_BREAK }}>
          {data.saved && data.saved.generated_at
            ? "저장본이 있습니다. 만든 시각 " + data.saved.generated_at
            : "이 주의 저장본이 아직 없습니다. 위 문장은 지금 계산한 것이고 저장되지 않았습니다."}
        </Typography>
      </Card>
    </Stack>
  );
}
