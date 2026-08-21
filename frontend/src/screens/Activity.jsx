import React from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import EastRoundedIcon from "@mui/icons-material/EastRounded";
import InboxRoundedIcon from "@mui/icons-material/InboxRounded";
import { api } from "../lib/api.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import {
  Badge, Button, Card, EmptyState, ErrorState, PageHeader, Skeleton,
} from "../ui/kit.jsx";
import { Pager } from "../ui/Pager.jsx";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";

/* 내 활동 피드 — 내가 한 일 / 나에게 일어난 일 (계획서 Phase 6 사용자).
 *
 * 두 원천을 서버가 합쳐서 준다(GET /api/me/activity): 감사 로그의 **내가 행위자인 행**과
 * 내 알림. 새 표를 만들지 않은 이유는 app/profiles/activity.py 모듈 docstring 에 있다 —
 * 같은 사건을 두 곳에 적기 시작하면 한쪽만 적는 코드 경로가 생기는 날 피드가 조용히
 * 진실을 잃는다.
 *
 * **모르는 활동도 원문 그대로 보여 준다.** '알 수 없는 활동'으로 뭉개면 내가 한 일인데
 * 무엇인지 알 수 없게 된다 — 이 화면에서 할 수 있는 가장 나쁜 일이다(서버가 같은 원칙으로
 * 문장을 만든다).
 */

const PAGE_SIZE = 20;

const KINDS = [
  { value: "", label: "전체" },
  { value: "did", label: "내가 한 일" },
  { value: "happened", label: "나에게 일어난 일" },
];

/* 하루 단위로 묶는다 — 30건이 시각만 다르게 줄줄이 늘어서면 '언제쯤'이 안 읽힌다. */
function groupByDay(items) {
  const groups = [];
  let current = null;
  items.forEach((item) => {
    const day = (item.at || "").slice(0, 10);
    if (!current || current.day !== day) {
      current = { day, items: [] };
      groups.push(current);
    }
    current.items.push(item);
  });
  return groups;
}

function ActivityRow({ item, onOpen }) {
  const isDid = item.kind === "did";
  const failed = item.result && item.result !== "success";
  return (
    <Box
      component="li"
      sx={{
        display: "flex", gap: 2, alignItems: "flex-start", py: 1.25,
        borderBottom: 1, borderColor: "divider", minWidth: 0,
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          mt: 0.25, display: "grid", placeItems: "center", flexShrink: 0,
          width: "2rem", height: "2rem", borderRadius: "50%",
          bgcolor: isDid ? "primary.main" : "action.selected",
          color: isDid ? "primary.contrastText" : "text.secondary",
        }}
      >
        {isDid ? <EastRoundedIcon fontSize="small" /> : <InboxRoundedIcon fontSize="small" />}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, minWidth: 0, ...KO_WORD_BREAK }}>
            {item.title}
          </Typography>
          {failed ? <Badge value="실패" kind="danger" /> : null}
          {item.kind === "happened" && !item.read_at ? <Badge value="안 읽음" kind="warn" /> : null}
        </Box>
        {item.body ? (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
            {item.body}
          </Typography>
        ) : null}
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
          <time dateTime={item.at} title={fmtDateTime(item.at)}>{fmtRelative(item.at)}</time>
          {", "}{isDid ? "내가 한 일" : "나에게 일어난 일"}
        </Typography>
      </Box>
      {item.route ? (
        <Button size="sm" onClick={() => onOpen(item.route)}>열기</Button>
      ) : null}
    </Box>
  );
}

export function Activity() {
  const [kind, setKind] = React.useState("");
  const [page, setPage] = React.useState(1);
  const nav = useNavigate();

  const q = useQuery({
    queryKey: ["my-activity", kind, page],
    queryFn: () => api(
      `/api/me/activity?page=${page}&page_size=${PAGE_SIZE}` + (kind ? `&kind=${kind}` : "")
    ),
    retry: false,
    // 페이지를 넘길 때 목록이 통째로 Skeleton 으로 사라졌다 나타나지 않게 한다.
    placeholderData: keepPreviousData,
  });

  const items = (q.data && q.data.items) || [];
  const total = q.data && q.data.total;
  const groups = groupByDay(items);

  return (
    <div className="c-screen">
      <PageHeader area="내 정보" title="내 활동" crumbRoot="" spot="teamspace" />

      <Card sx={{ p: 2, mb: 2.5 }}>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={kind}
          onChange={(_e, value) => { if (value != null) { setKind(value); setPage(1); } }}
          aria-label="활동 종류"
        >
          {KINDS.map((k) => (
            <ToggleButton key={k.value || "all"} value={k.value} sx={{ textTransform: "none", px: 2 }}>
              {k.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Card>

      {q.isLoading ? (
        <Card><Skeleton lines={8} /></Card>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            art="notify"
            title={kind ? "이 종류의 활동이 없습니다" : "아직 활동 기록이 없습니다"}
            situation={kind
              ? "고른 종류에는 기록이 없습니다. 다른 종류를 보거나 전체로 되돌려 보세요."
              : "로그인, 티켓 수정, 받은 알림 같은 일이 생기면 여기에 시간순으로 쌓입니다."}
            action={kind ? <Button onClick={() => { setKind(""); setPage(1); }}>전체 보기</Button> : null}
          />
        </Card>
      ) : (
        <Card>
          {groups.map((g) => (
            <Box key={g.day} sx={{ mb: 2 }}>
              <Typography
                component="h2"
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", fontWeight: FONT_WEIGHT.bold, py: 1, position: "sticky", top: 0, bgcolor: "background.paper", zIndex: 1 }}
              >
                {g.day}
              </Typography>
              <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0 }}>
                {g.items.map((item) => (
                  <ActivityRow key={item.id} item={item} onOpen={(route) => nav(route)} />
                ))}
              </Box>
            </Box>
          ))}
          <Pager
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            hasNext={items.length >= PAGE_SIZE}
            onPage={(p) => setPage(Math.max(1, p))}
          />
        </Card>
      )}
    </div>
  );
}

export default Activity;
