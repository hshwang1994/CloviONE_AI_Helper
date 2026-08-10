import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Fade from "@mui/material/Fade";
import InputBase from "@mui/material/InputBase";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";
import { api } from "../lib/api.js";
import { Button, Card, EmptyState, ErrorState, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { FAB_CLEARANCE } from "../ui/theme.js";
import { isSearchable, normalizeQuery, routeOf, searchApi } from "../lib/search.js";
import { useAuth } from "../app/auth.jsx";
import { OPS_ROLES } from "./registry/shared.js";

/* 통합 검색 결과 화면 (계획서 Phase 5).
 *
 * 지키는 계약 세 가지:
 *
 *  1) **빈 상태 두 가지를 구분한다.** '검색어를 아직 안 쳤다'와 '쳤는데 없다'는 다른 화면이다.
 *     후자는 `art="search"` + "검색 결과 없음" 으로, '데이터 없음'(art="tickets" 등)과도
 *     구분한다 — 같은 그림·같은 문장을 쓰면 사용자는 자기 검색어 때문인 줄 모르고 데이터가
 *     사라졌다고 생각한다.
 *
 *  2) **유형별 그룹.** 그룹 제목·순서·라우트는 전부 서버 응답에서 온다. 화면에 유형별 if 를
 *     두지 않으므로, 검색 대상이 늘어도 이 파일은 안 고친다.
 *
 *  3) **짧은 검색어를 숨기지 않는다.** 1~2자는 서버가 LIKE 폴백으로 답하고 `mode:"like"` 로
 *     알려 준다. 그 사실을 화면에도 적는다 — "왜 결과가 이상하지"를 사용자가 스스로 알 수
 *     있어야 한다.
 *
 * px 폰트 크기를 쓰지 않는다(4K 대응이 루트 폰트사이즈 레버 하나로 되어 있다).
 * MUI Grid 는 쓰지 않는다(MUI 7 에서 xs={12} 가 조용히 무시된다) — Box + display:grid 다.
 */

/* 결과 그룹 격자 — 남는 폭은 줄 길이가 아니라 두 번째·세 번째 열로 간다(4K 규칙).
 *
 * `pr`(오른쪽 여백)이 붙어 있는 이유는 순전히 **마스코트 FAB 때문**이다. FAB 은
 * `position:fixed; right:24; bottom:24` 라 문서 흐름 밖에 떠 있고, 셸이 주는 아래 여백은
 * '맨 아래까지 스크롤했을 때'만 도움이 된다. 검색 결과는 목록이 길어서 **어느 스크롤
 * 위치에서든** 오른쪽 열의 결과 줄이 그 모서리에 놓이고, 그 줄은 눌러도 FAB 이 클릭을
 * 가로챈다(QA 하네스의 fab_overlap 이 1366·1920 에서 실제로 잡았다: 5~7% 만 덮여도
 * elementFromPoint 가 FAB 을 돌려준다).
 *
 * 그래서 오른쪽 열이 FAB 의 x 범위에 닿지 않도록 격자 자체를 그만큼 좁힌다. 세로 여백으로는
 * 못 고치는 문제라 가로로 비켜서는 것이 유일한 기하학적 해법이다. 한 열일 때(<lg)는 줄이
 * 화면 폭 전체를 쓰므로 필요 없다. 3840 은 본문 폭 캡 덕에 FAB 이 애초에 본문 밖이지만,
 * 그 폭에서 여백 한 칸은 눈에 띄지 않으므로 분기를 늘리지 않고 그대로 둔다. */
/* `display:grid` 가 아니라 **다단(multi-column)** 인 이유: 그룹 카드는 높이가 제각각이다
 * (문서 20건, 티켓 3건). 격자로 깔면 행 높이가 가장 큰 카드에 맞춰지면서 짧은 카드 아래로
 * 화면 절반짜리 빈 공백이 생기고, 다음 카드는 그 아래로 밀려난다 — 1920 캡처에서 실제로
 * 그랬다. 다단은 카드를 위에서부터 채워 넣으므로 그 구멍이 생기지 않는다.
 * `breakInside: avoid` 로 카드가 열 경계에서 두 동강 나는 것만 막는다. */
const GROUP_GRID = {
  columnCount: { xs: 1, lg: 2, xxl: 3 },
  columnGap: 2.5,
  pr: { xs: 0, lg: FAB_CLEARANCE },
  "& > *": { breakInside: "avoid", mb: 2.5 },
};

function SearchField({ value, onChange, onSubmit }) {
  return (
    <Paper
      component="form"
      role="search"
      elevation={0}
      onSubmit={(e) => { e.preventDefault(); onSubmit(value); }}
      sx={{
        display: "flex", alignItems: "center", gap: 1.5, px: 2.5, py: 1.25, mb: 3,
        border: 1, borderColor: "divider", borderRadius: 3,
      }}
    >
      <SearchRoundedIcon aria-hidden="true" sx={{ color: "text.secondary" }} />
      <InputBase
        fullWidth
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="티켓, 문서, 게시판, 사용자 검색"
        inputProps={{ "aria-label": "통합 검색어" }}
        sx={{ fontSize: "1rem" }}
      />
      {/* flexShrink/nowrap 이 없으면 4K 에서 '검색'이 '검 / 색' 두 줄로 접힌다 —
          루트 폰트사이즈 레버(3000px 에서 20px)로 글자가 커지는데 입력이 fullWidth 라
          버튼만 눌려 찌그러진다. 실제 3840 캡처에서 그랬다. */}
      <Button type="submit" variant="primary" sx={{ flexShrink: 0, whiteSpace: "nowrap" }}>
        검색
      </Button>
    </Paper>
  );
}

function ResultGroup({ group, onOpen }) {
  return (
    <Card>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 1 }}>
        <Typography component="h2" sx={{ fontWeight: 800, fontSize: "1rem" }}>
          {group.label}
        </Typography>
        <Chip size="small" label={group.total} />
      </Box>
      <List dense disablePadding>
        {group.items.map((item) => (
          <ListItemButton
            key={item.kind + ":" + item.id}
            onClick={() => onOpen(item)}
            sx={{ borderRadius: 2, alignItems: "flex-start" }}
          >
            <ListItemText
              primary={item.title}
              secondary={item.subtitle || null}
              primaryTypographyProps={{ sx: { fontWeight: 650 } }}
              secondaryTypographyProps={{ sx: { fontSize: "0.8125rem" } }}
            />
            {item.url ? (
              <OpenInNewRoundedIcon
                aria-hidden="true"
                sx={{ fontSize: "1rem", color: "text.disabled", mt: 0.5, ml: 1 }}
              />
            ) : null}
          </ListItemButton>
        ))}
      </List>
      {group.total > group.items.length ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          {group.total}건 중 {group.items.length}건을 보여 줍니다. 검색어를 더 좁혀 보세요.
        </Typography>
      ) : null}
    </Card>
  );
}

export function Search() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const urlQuery = normalizeQuery(params.get("q") || "");
  const [draft, setDraft] = React.useState(urlQuery);

  // 주소창(또는 팔레트에서 넘어온 이동)이 바뀌면 입력도 따라간다. 뒤로가기가 동작해야 한다.
  React.useEffect(() => { setDraft(urlQuery); }, [urlQuery]);

  const enabled = isSearchable(urlQuery);
  const q = useQuery({
    queryKey: ["search", urlQuery],
    queryFn: () => searchApi(urlQuery, { limit: 20 }),
    enabled,
    // 검색은 사용자가 방금 친 것에 대한 답이다. 화면을 떠났다 돌아왔을 때 옛 결과를
    // 잠깐 보여 주지 않도록 짧게 유지한다.
    staleTime: 15_000,
  });

  const submit = React.useCallback((value) => {
    const next = normalizeQuery(value);
    // replace 를 쓰지 않는다 — 검색어를 바꿔 가며 좁히는 흐름에서 뒤로가기가 살아 있어야 한다.
    setParams(next ? { q: next } : {});
  }, [setParams]);

  const open = React.useCallback((item) => {
    const route = routeOf(item);
    if (route) navigate(route);
  }, [navigate]);

  // 재색인(FN-03) — 색인은 읽기 미러라 tickets/team-docs 동기화와 달리 이 목록(GET /api/search)
  // 자체는 role 없이 누구나 쓴다. 그래서 can_reindex 같은 필드를 목록 응답에 실을 자리가 없고
  // (search/reindex_router.py 가 일부러 읽기/쓰기 경로를 분리해 뒀다), 화면에서 role을 직접 본다.
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  const canReindex = role != null && OPS_ROLES.includes(role);
  const confirm = useConfirm();
  const toast = useToast();
  const qc = useQueryClient();
  const reindex = useMutation({
    mutationFn: () => api("/api/search/reindex", { method: "POST", body: {} }),
    onSuccess: (res) => {
      const r = res && res.reindex;
      qc.invalidateQueries({ queryKey: ["search"] });
      if (r && r.status === "error") toast("재색인 실패: " + (r.error || "확인이 필요합니다"), "error");
      else toast("검색 색인을 다시 만들었습니다" + (r ? " (" + r.item_count + "건)" : "") + ".", "success");
    },
    onError: (e) => toast((e && e.message) || "재색인하지 못했습니다.", "error"),
  });
  async function doReindex() {
    const ok = await confirm(
      "검색 색인을 지금 다시 만들까요? 데이터가 많으면 잠시 시간이 걸릴 수 있습니다.",
      { title: "검색 재색인", confirmLabel: "재색인" },
    );
    if (ok) reindex.mutate();
  }

  const result = q.data;
  const groups = (result && result.groups) || [];

  return (
    <Box className="c-screen">
      <PageHeader
        crumbRoot=""
        area="통합 검색"
        title={enabled ? `‘${urlQuery}’ 검색 결과` : "통합 검색"}
        actions={canReindex ? (
          <Button size="sm" onClick={doReindex} disabled={reindex.isPending}>
            {reindex.isPending ? "재색인 중…" : "지금 재색인"}
          </Button>
        ) : null}
      />
      <SearchField value={draft} onChange={setDraft} onSubmit={submit} />

      {!enabled ? (
        /* '아직 안 쳤다' — 결과가 없는 것이 아니라 아직 묻지 않은 상태다.
           여기에 '검색 결과 없음'을 띄우면 사용자는 자기가 뭔가 잘못한 줄 안다. */
        <Card>
          <EmptyState
            title="무엇을 찾을까요?"
            situation="티켓, 문서, 게시판, 사용자를 한 번에 찾습니다."
            help="한 글자만 쳐도 찾습니다. Ctrl+K 로 어느 화면에서든 이 검색을 열 수 있습니다."
            art="search"
          />
        </Card>
      ) : q.isPending ? (
        <Card><Skeleton lines={6} /></Card>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : groups.length === 0 ? (
        /* '쳤는데 없다' — art="search" 로 '데이터 없음'과 구분한다. 복구 행동은 검색어를
           지우는 것이지, 데이터를 만드는 것이 아니다. */
        <Card>
          <EmptyState
            title="검색 결과 없음"
            situation={`‘${urlQuery}’ 와 일치하는 항목을 찾지 못했습니다.`}
            help={
              result && result.mode === "like"
                ? "한두 글자 검색어는 정확히 그 글자가 들어간 항목만 찾습니다. 조금 더 길게 쳐 보세요."
                : "맞춤법을 확인하거나 더 짧은 검색어로 다시 시도해 보세요."
            }
            art="search"
            action={<Button onClick={() => submit("")}>검색어 지우기</Button>}
          />
        </Card>
      ) : (
        <Fade in timeout={200}>
          <Box>
            <Typography
              variant="body2" color="text.secondary" role="status" sx={{ mb: 2 }}
            >
              {`총 ${result.total}건`}
              {result.mode === "like" ? ", 짧은 검색어라 부분 일치로 찾았습니다" : ""}
              {result.truncated ? ", 일부만 표시합니다" : ""}
            </Typography>
            <Box sx={GROUP_GRID}>
              {groups.map((group) => (
                <ResultGroup key={group.kind} group={group} onOpen={open} />
              ))}
            </Box>
          </Box>
        </Fade>
      )}
    </Box>
  );
}

export default Search;
