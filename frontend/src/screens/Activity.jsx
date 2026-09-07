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
  Badge, Button, Card, EmptyState, ErrorState, ListCard, PageHeader, Skeleton, FlatBadgeSurface,
} from "../ui/kit.jsx";
import { ListFooter } from "../ui/InfiniteScroll.jsx";
import { useInfiniteList } from "../lib/useInfiniteList.js";
import { FONT_WEIGHT, KO_WORD_BREAK, stickyTopSx } from "../ui/theme.js";

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

/* 이 피드의 행은 싸다(한 줄짜리 항목이 날짜로 묶인다) — 20은 굴릴 때마다 왕복이라 너무 작다. */
const PAGE_SIZE = 50;

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
        display: "flex", gap: 2, alignItems: "center", py: 1.25,
        borderBottom: 1, borderColor: "divider", minWidth: 0,
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          display: "grid", placeItems: "center", flexShrink: 0,
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
  const nav = useNavigate();

  const q = useInfiniteList({
    key: ["my-activity", kind],
    size: PAGE_SIZE,
    rowId: (r) => (r && r.id) || undefined,
    fetch: ({ page, page_size: size }) => api(
      `/api/me/activity?page=${page}&page_size=${size}` + (kind ? `&kind=${kind}` : "")
    ),
  });

  const items = q.rows;
  const total = q.total;
  const groups = groupByDay(items);

  return (
    <div className="c-screen">
      <PageHeader area="내 정보" title="내 활동" crumbRoot="" />

      <Card sx={{ p: 2, mb: 2.5 }}>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={kind}
          onChange={(_e, value) => { if (value != null) setKind(value); }}
          aria-label="활동 종류"
        >
          {KINDS.map((k) => (
            /* 🔴 **선택은 면이 아니라 잉크와 레일로 말한다** (D-289 · S22 실측).
               MUI 기본 `Mui-selected` 는 `rgba(0,0,0,.08)` 회색 면이라, 캡처가 이 화면의
               선택 자리를 `#ECEDEE`(S 0.05 · ΔE 3.1)로 읽고 「있는 자리가 회색이다」로
               세었다. 이 제품은 사이드바(3px 레일)도 판독 줄(아래 레일)도 같은 어휘를
               쓴다 — 한 제품이 선택을 두 가지 말로 하지 않는다. */
            <ToggleButton
              key={k.value || "all"}
              value={k.value}
              data-brand-role={kind === k.value ? "selected-state" : undefined}
              sx={(t) => ({
                textTransform: "none", px: 2,
                "&.Mui-selected": {
                  color: t.palette.brand.core,
                  borderColor: t.palette.brand.core,
                  backgroundColor: "transparent",
                  fontWeight: FONT_WEIGHT.semibold,
                  "&:hover": { backgroundColor: "transparent" },
                },
              })}
            >
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
            layout="page"
            art="notify"
            title={kind ? "이 종류의 활동이 없습니다" : "아직 활동 기록이 없습니다"}
            situation={kind
              ? "고른 종류에는 기록이 없습니다. 다른 종류를 보거나 전체로 되돌려 보세요."
              : "로그인, 티켓 수정, 받은 알림 같은 일이 생기면 여기에 시간순으로 쌓입니다."}
            action={kind ? <Button onClick={() => setKind("")}>전체 보기</Button> : null}
          />
        </Card>
      ) : (
        <ListCard>
          {groups.map((g) => (
            <Box key={g.day} sx={{ mb: 2 }}>
              {/* 날짜 머리는 굴려도 남는다 — 어느 날의 일을 보고 있는지가 이 화면의 축이다.
                  두 가지가 필요하다: ① 담는 판이 자기 안을 안 자를 것(`ListCard` — MUI Card 의
                  `overflow:hidden` 은 sticky 의 스크롤 창이 되어 버린다) ② 오프셋이 fixed
                  AppBar 높이만큼일 것(`stickyTopSx`). 둘 중 하나만 있으면 «속성은 sticky 인데
                  안 따라온다» 나 «따라오는데 상단바 뒤로 숨는다» 가 된다. */}
              <Typography
                component="h2"
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", fontWeight: FONT_WEIGHT.bold, py: 1, position: "sticky", ...stickyTopSx(), bgcolor: "background.paper", zIndex: 1 }}
              >
                {g.day}
              </Typography>
              {/* 목록 안이라 배지가 면을 갖지 않는다 (확정 규약 §9). */}
              <FlatBadgeSurface>
                <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0 }}>
                  {g.items.map((item) => (
                    <ActivityRow key={item.id} item={item} onOpen={(route) => nav(route)} />
                  ))}
                </Box>
              </FlatBadgeSurface>
            </Box>
          ))}
          {/* 이 응답은 `total` 을 준다. 안 주는 응답이었다면 「마지막 묶음이 가득 찼는가」로
              더 있음을 판정한다 — 그 폴백은 `useInfiniteList` 의 봉투 어댑터가 든다(DS-22). */}
          <ListFooter
            total={total} loaded={q.loaded}
            hasNext={q.hasNext} isFetchingNext={q.isFetchingNext} onMore={q.fetchNext}
            moreLabel="활동 더 보기"
          />
        </ListCard>
      )}
    </div>
  );
}

export default Activity;
