import React from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Badge, Card, EmptyState } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { safeExternal } from "../lib/safeUrl.js";
import { ProgressBasis } from "./ProjectMetrics.jsx";
import { WBS_UNPLACED_KO, percentText } from "./project-format.js";
import { Note } from "../ui/adminKit.jsx";

/* WBS 트리 — 노션 작업 계층(`parent_page_id`)을 그대로 그린다.
 *
 * 계층을 화면에서 다시 만들지 않는다. 서버가 이미 트리와 노드별 진행률을 같은 함수로
 * 만들어 보낸다(app/projects/wbs.py). 여기서 다시 세면 트리의 숫자와 머리글의 숫자가
 * 갈라지고, 그때 사용자는 어느 쪽도 안 믿는다.
 *
 * ## 못 그린 작업을 반드시 말한다
 *
 * 상위 작업이 순환이거나 계층이 너무 깊으면 서버가 `unplaced` 로 따로 담아 보낸다.
 * 조용히 빼면 사용자는 자기 일이 사라진 줄 알고, 고칠 사람은 고칠 곳을 못 찾는다.
 */

/* 들여쓰기 한 칸. 깊이가 깊어져도 카드 밖으로 안 나가게 상한을 둔다 - 노션 계층이 열 단계인
 * 프로젝트에서 왼쪽 여백만 20rem 이 되면 제목이 한 글자씩 세로로 흐른다. */
const INDENT_REM = 1.25;
const MAX_INDENT_STEPS = 8;

function NodeProgress({ progress }) {
  const p = progress || {};
  const text = percentText(p.percent);
  const basis = p.basis || {};
  return (
    <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
      {text
        ? text + " (" + (basis.counted_tasks || 0) + "건 중 " + (basis.done_tasks || 0) + "건 완료)"
        : "셀 작업이 없습니다"}
    </Typography>
  );
}

function WbsRow({ node }) {
  const url = safeExternal(node.url);
  const steps = Math.min(node.depth || 0, MAX_INDENT_STEPS);
  return (
    <Box component="li" sx={{ listStyle: "none" }}>
      <Box
        sx={{
          display: "flex", gap: 1.5, alignItems: "baseline", flexWrap: "wrap",
          /* steps * INDENT_REM 을 숫자로 넘기면 sx 의 pl 이 theme.spacing()을 타면서
           * (frontend/src/ui/theme.js: spacing = factor => `${0.5 * factor}rem`) 값이 반토막
           * 난다 — 문자열로 넘겨 그 배율을 건너뛴다. */
          py: 1, pl: `${steps * INDENT_REM}rem`, borderBottom: 1, borderColor: "divider", minWidth: 0,
        }}
      >
        {node.ticket_number != null ? (
          <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
            {"GIT-" + node.ticket_number}
          </Typography>
        ) : null}
        <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body, minWidth: 0, ...KO_WORD_BREAK }}>
          {node.title || "제목 없음"}
        </Typography>
        {node.status ? <Badge value={node.status} /> : null}
        {node.est_wd != null ? (
          <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
            {"예상 " + node.est_wd + " WD"}
          </Typography>
        ) : null}
        <Box sx={{ flex: 1 }} />
        <NodeProgress progress={node.progress} />
        {url ? (
          <Link href={url} target="_blank" rel="noopener noreferrer" underline="hover" sx={{ fontSize: FONT_SIZE.bodySm }}>
            원본
          </Link>
        ) : null}
      </Box>
      {(node.children || []).length ? (
        <Box component="ul" sx={{ m: 0, p: 0 }}>
          {node.children.map((child) => <WbsRow key={child.key} node={child} />)}
        </Box>
      ) : null}
    </Box>
  );
}

export function ProjectWbs({ data, ticketsLinked }) {
  const d = data || {};
  const roots = Array.isArray(d.roots) ? d.roots : [];
  const unplaced = Array.isArray(d.unplaced) ? d.unplaced : [];

  if (!roots.length && !unplaced.length) {
    return (
      <Card>
        <EmptyState
          art="tickets"
          title="작업 계층을 그릴 자료가 없습니다"
          help={ticketsLinked
            ? "이 프로젝트에 연결된 노션 작업이 아직 없습니다."
            : "이 프로젝트는 노션 페이지와 연결되어 있지 않아 작업을 가져올 수 없습니다."}
        />
      </Card>
    );
  }

  return (
    <Stack gap={2.5}>
      <Card>
        <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1 }}>트리 전체 진행률</Typography>
        {/* 머리글 숫자는 개요 탭과 **같은 함수, 같은 표본**이다(서버가 그렇게 만든다).
            그 사실이 화면에서도 보이도록 같은 근거 표를 그린다. */}
        {/* PA-RC-0001: 24px — game-room/GameStage.jsx·charts/Donut.jsx와 같은 값+굵기(의도된
            예외, 세부 사유는 GameStage.jsx 참고 — 전용 토큰 신설은 검토 후 보류함, D-78). */}
        <Typography sx={{ fontSize: "1.5rem", fontWeight: FONT_WEIGHT.extrabold }}>
          {percentText(d.progress && d.progress.percent) || "작업이 아직 없습니다"}
        </Typography>
        <ProgressBasis basis={d.progress && d.progress.basis} />
      </Card>

      {roots.length ? (
        <Card>
          <Box component="ul" sx={{ m: 0, p: 0 }}>
            {roots.map((node) => <WbsRow key={node.key} node={node} />)}
          </Box>
        </Card>
      ) : null}

      {unplaced.length ? (
        <Card>
          <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1 }}>
            {"트리에 넣지 못한 작업 " + unplaced.length + "건"}
          </Typography>
          <Note sx={{ mt: 0 }}>
            아래 작업은 트리에 넣지 못했지만 위의 진행률에는 들어 있습니다. 빼면 상위 작업 설정 하나에 진행률이 통째로 흔들립니다.
          </Note>
          <Box component="ul" sx={{ m: 0, mt: 1.5, p: 0, display: "grid", gap: 1 }}>
            {unplaced.map((u) => (
              <Box component="li" key={u.key} sx={{ listStyle: "none", display: "grid", gap: 0.25 }}>
                <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}>
                  {u.title || "제목 없음"}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
                  {WBS_UNPLACED_KO[u.reason] || "트리에 넣지 못했습니다. 노션에서 작업 구조를 확인해 주세요."}
                </Typography>
              </Box>
            ))}
          </Box>
        </Card>
      ) : null}
    </Stack>
  );
}
