import React from "react";
import { useQuery } from "@tanstack/react-query";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import InputBase from "@mui/material/InputBase";
import LinearProgress from "@mui/material/LinearProgress";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListSubheader from "@mui/material/ListSubheader";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import HistoryRoundedIcon from "@mui/icons-material/HistoryRounded";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import SearchOffRoundedIcon from "@mui/icons-material/SearchOffRounded";
import ErrorOutlineRoundedIcon from "@mui/icons-material/ErrorOutlineRounded";
import KeyboardReturnRoundedIcon from "@mui/icons-material/KeyboardReturnRounded";
import { useLocation, useNavigate } from "react-router-dom";
import { isSearchable, normalizeQuery, routeOf, searchApi, searchResultsPath } from "../lib/search.js";
import { readRecentNav } from "../lib/recentNav.js";
import { navIcon } from "./navIcons.js";
import { DEBOUNCE_MS, FONT_SIZE, FONT_WEIGHT, ICON, KO_WORD_BREAK, RADIUS, remPx } from "../ui/theme.js";

/* 명령 팔레트 (Ctrl+K / Cmd+K) — **메뉴 이동 + 진짜 통합 검색**.
 *
 * v1 에서는 메뉴만 찾았다. 디자인 원본의 상단바 '통합 검색' 입력은 팔레트를 여는 것 말고
 * 아무 일도 하지 않는 죽은 컨트롤이었고, 이 저장소는 '되는 척하는 UI'를 두지 않기 때문에
 * 라벨을 '메뉴 검색'으로 정직하게 낮춰 두었다. 이제 백엔드 인덱스(FTS5, 0030)가 생겼으므로
 * **같은 자리에 진짜를 붙인다** — 라벨도 원래 이름으로 되돌린다.
 *
 * 두 종류의 결과를 한 목록에 섞지 않고 그룹으로 나눈다:
 *   * **바로 가기** — 역할로 걸러진 나브. 권한 없는 화면이 결과에 뜨면 눌렀을 때 403 막다른
 *     길로 간다(사이드바에서 이미 없앤 문제). 로컬이라 항상 즉시 나온다.
 *   * **티켓 / 문서 / 게시판 / 사용자** — 서버가 유형별로 묶어 준다. 그룹 제목과 라우트가
 *     응답에서 오므로 이 파일에는 유형별 if 가 없다. 채팅은 서버가 아예 인덱싱하지 않는다.
 *
 * 서버 왕복은 **디바운스**한다. 팔레트는 글자마다 다시 그리는 화면이라, 디바운스가 없으면
 * 한국어 조합 입력 한 번에 요청이 여러 번 나간다.
 *
 * 빈 질의(SRCH-04)는 지금 콘솔 메뉴 전부를 다시 나열하지 않는다 — 사이드바가 바로 옆에
 * 열려 있는데 같은 목록을 모달로 한 번 더 보여 주는 셈이었다. 대신 실제로 다녀간 경로를
 * `lib/recentNav.js`(localStorage, 서버 없음)에서 읽어 "최근 방문"만 보여준다.
 */

// 값의 정본은 토큰이다(theme.js::DEBOUNCE_MS) — 화면마다 숫자를 박지 않는다(지시 26).
const PALETTE_DEBOUNCE_MS = DEBOUNCE_MS.palette;

/* 결과 유형 → 아이콘 (지시 14: "최근 방문, 메뉴, 티켓, 문서 등 검색 결과 유형을 쉽게 구분").
 *
 * 줄마다 유형을 **글자로** 다시 적으면 구역 제목과 같은 말을 두 번 한다(지시 44). 그래서
 * 유형은 그림으로 말한다. 계열은 사이드바와 같은 하나다(`navIcons.js`, MUI `*Outlined`) —
 * 팔레트에서 본 그림과 다른 화면에서 볼 그림이 다르면 그 둘이 같은 것이라는 걸 못 배운다
 * (지시 79: 아이콘은 한 계열).
 *
 * 이 표는 **엔티티 유형**을 말한다. 같은 목록의 메뉴 줄은 자기 **랜드마크 그룹**의 글리프를
 * 쓴다(아래 `sections`) — 한 열에서 두 질문에 답하지만 답의 단위는 언제나 '유형 하나에
 * 그림 하나' 다. 목적지마다 그림을 따로 주지는 않는다(R-48).
 *
 * 서버가 유형을 늘리면 여기 매핑이 없어도 죽지 않는다 — `null` 이면 줄이 아이콘 없이
 * 그려지고 구역 제목이 유형을 계속 말한다. 화면이 유형별 if 로 갈라지지 않는다는
 * `lib/search.js` 의 설계를 여기서도 깨지 않는다. */
const KIND_ICON = {
  ticket: "ticket",
  document: "docs",
  board: "board",
  user: "profile",
};

function normalize(s) {
  return String(s || "").toLowerCase().replace(/\s+/g, "");
}

/* 입력이 멎은 뒤에만 값을 흘려보낸다. 서버 검색 전용이고, 메뉴 검색은 로컬이라 즉시 반응한다. */
export function useDebounced(value, delay = PALETTE_DEBOUNCE_MS) {
  const [settled, setSettled] = React.useState(value);
  React.useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

export function CommandPalette({ open, onClose, groups }) {
  const [q, setQ] = React.useState("");
  const navigate = useNavigate();
  const loc = useLocation();
  const inputRef = React.useRef(null);
  const debounced = useDebounced(q);

  React.useEffect(() => { if (open) setQ(""); }, [open]);

  // 메뉴(로컬) — 즉시.
  const navResults = React.useMemo(() => {
    const needle = normalize(q);
    if (!needle) {
      // SRCH-04 — 빈 질의에서 지금 콘솔의 메뉴 전부를 다시 나열하지 않는다(사이드바가
      // 바로 옆에 열려 있는데 같은 목록을 모달로 한 번 더 보여 주는 셈이었다). 실제로
      // 다녀간 경로만, 지금 이 역할에서도 여전히 유효한 것만, 지금 보고 있는 화면은
      // 빼고 보여준다 — 역할이 바뀌어 더는 못 보는 메뉴나 detail 경로(예: /tickets/:id)는
      // groups에 없으니 자연히 걸러진다.
      // 항목과 함께 **그 항목이 사는 그룹의 글리프**를 기억해 둔다 — 최근 방문 목록은 여러
      // 그룹에서 모이므로, 그러지 않으면 줄마다 소속을 잃고 전부 같은 그림이 된다.
      const byPath = new Map();
      for (const g of groups || []) {
        for (const it of g.items) byPath.set(it.to, { ...it, groupIcon: g.icon });
      }
      const items = readRecentNav()
        .filter((path) => path !== loc.pathname)
        .map((path) => byPath.get(path))
        .filter(Boolean);
      return items.length ? [{ group: "최근 방문", items, recent: true }] : [];
    }
    return (groups || [])
      .map((g) => ({
        group: g.group,
        // 랜드마크 글리프를 함께 나른다 — 아래 `sections` 가 결과 줄 앞에 그것을 놓는다.
        icon: g.icon,
        items: g.items.filter((it) => normalize(it.label).includes(needle) || normalize(g.group).includes(needle)),
      }))
      .filter((g) => g.items.length);
  }, [groups, q, loc.pathname]);

  // 콘텐츠(서버) — 디바운스 후. 팔레트가 닫혀 있으면 요청하지 않는다.
  const searchable = isSearchable(debounced);
  const search = useQuery({
    queryKey: ["search", "palette", normalizeQuery(debounced)],
    queryFn: () => searchApi(debounced, { limit: 5 }),
    enabled: !!open && searchable,
    staleTime: 15_000,
  });

  const sections = React.useMemo(() => {
    // 라벨 앞에 "메뉴 ·"를 붙인다 — 사용자 지적: 검색어를 쳤을 때 '운영' 등 사이드바
    // 그룹 이름이 그대로 목록에 나열돼, 이게 검색 결과인지 메뉴 이동인지 구분이 안 됐다
    // ("운영 밑에 있는것들이 페이지 이전인건가??"). 아래 서버 검색 그룹(티켓/문서/게시판 등)과
    // 같은 ListSubheader 모양을 쓰므로, 이름 자체로 종류를 밝힌다. "최근 방문"(빈 질의,
    // SRCH-04)은 애초에 메뉴 그룹이 아니라 접두어를 안 붙인다 — 서버 결과와 헷갈릴 여지가
    // 없다(빈 질의에서는 서버 검색 자체가 안 돈다).
    const out = navResults.map((g) => ({
      key: g.recent ? "recent" : "nav:" + g.group,
      label: g.recent ? g.group : "메뉴 › " + g.group,
      /* 메뉴 결과의 글리프는 **그 목적지가 사는 랜드마크**(사이드바 그룹)의 것이다.
         항목마다 자기 글리프를 달던 시절에는 `ticket` 이 네 곳, `report` 가 네 곳에서
         반복돼 훑을 때 서로 다른 목적지가 한 덩어리로 보였다(R-48 이 금지한 상태) —
         W3 이 사이드바에서 그 반복을 걷어내면서 여기 표도 같이 정리됐다.
         최근 방문은 그룹이 아니라 이력이라 시계 글리프를 쓴다. */
      items: g.items.map((it) => ({
        key: "nav:" + it.to, label: it.label, hint: it.to, to: it.to,
        /* 최근 방문 줄도 **자기 랜드마크**의 글리프를 쓴다. 시계로 덮으면 네 줄이 전부 같은
           그림이 되어 서로 구분이 안 된다 — 이 파일이 예전부터 적어 두었던 경고이고, 그
           상태를 한 번 만들었다가 독립 재검증이 잡았다. 소속을 모를 때만 시계로 떨어진다. */
        Icon: it.groupIcon || g.icon || (g.recent ? HistoryRoundedIcon : null),
      })),
    }));
    const serverGroups = (search.data && search.data.groups) || [];
    for (const group of serverGroups) {
      const Icon = navIcon(KIND_ICON[group.kind]);
      out.push({
        key: "kind:" + group.kind,
        label: group.label,
        items: (group.items || []).map((item) => ({
          key: item.kind + ":" + item.id,
          label: item.title,
          hint: item.subtitle || "",
          to: routeOf(item),
          Icon,
        })),
      });
    }
    return out.filter((section) => section.items.length);
  }, [navResults, search.data]);

  // '모든 결과 보기'는 목록의 마지막 항목이다 — 키보드로도 닿아야 한다.
  const seeAll = React.useMemo(
    () => (searchable && search.data && search.data.total > 0
      ? { key: "see-all", label: `‘${normalizeQuery(debounced)}’ 검색 결과 모두 보기`,
          hint: `총 ${search.data.total}건`, to: searchResultsPath(debounced),
          Icon: ArrowForwardRoundedIcon }
      : null),
    [searchable, search.data, debounced],
  );

  const flat = React.useMemo(
    () => [...sections.flatMap((s) => s.items), ...(seeAll ? [seeAll] : [])],
    [sections, seeAll],
  );
  const [cursor, setCursor] = React.useState(0);
  React.useEffect(() => { setCursor(0); }, [q, open]);
  // 서버 결과가 뒤늦게 도착해 목록이 짧아지면 커서가 목록 밖에 남는다(Enter 가 아무 일도
  // 안 하거나 엉뚱한 곳으로 간다). 항상 범위 안으로 되돌린다.
  React.useEffect(() => {
    setCursor((c) => (flat.length ? Math.min(c, flat.length - 1) : 0));
  }, [flat.length]);

  const go = React.useCallback((to) => {
    if (!to) return;
    onClose();
    navigate(to);
  }, [navigate, onClose]);

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(c + 1, flat.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
    else if (e.key === "Enter") {
      e.preventDefault();
      // 결과가 아직 없어도 Enter 는 검색 결과 화면으로 보낸다 — 친 것이 사라지지 않게.
      // 판정은 **디바운스된 값이 아니라 지금 입력값**으로 한다. 디바운스가 아직 안 끝났다는
      // 이유로 Enter 가 아무 일도 안 하면, 빨리 치는 사용자에게는 그냥 고장으로 보인다.
      if (flat[cursor]) go(flat[cursor].to);
      else if (isSearchable(q)) go(searchResultsPath(q));
    }
  };

  // 디바운스가 아직 안 따라잡은 동안에도 '찾는 중'이다. 이걸 빼면 글자를 칠 때마다
  // '검색 결과 없음'이 한 번씩 번쩍인다 — 결과가 있는데도 없다고 말하는 순간이 생긴다.
  const pending = isSearchable(q) && normalizeQuery(q) !== normalizeQuery(debounced);
  const busy = !!open && (pending || (searchable && search.isFetching));
  // 검색이 **실패했는가**. 이게 없으면 서버 오류가 "검색 결과 없음" 으로 둔갑한다 (E9).
  const failed = searchable && search.isError && !search.isFetching;

  return (
    /* 통합 검색 (지시 14).
     *
     * 예전에는 흰 팝업(600px) 안의 평범한 목록이었다. 4K 에서 화면 폭의 1/6 을 차지하는
     * 상자에 결과가 두 줄씩 쌓였고, 지금 고른 줄은 MUI 기본 옅은 배경뿐이라 키보드로
     * 훑으면 어디 있는지 놓치기 쉬웠다. 그리고 결과 유형(메뉴/티켓/문서)은 구역 제목에만
     * 있어서, 목록을 반쯤 내려가면 지금 보는 것이 무엇인지 알 수 없었다.
     *
     * 바뀐 것: 폭을 실제 화면에 맞게 넓히고, 고른 줄에 **앞머리 레일 + 안쪽 바탕**을 주고
     * (계기판의 현재 선택 표현과 같은 어휘), 줄마다 유형 표지를 달고, 아래에 키 안내를
     * 상시로 둔다. 목록은 여전히 한 줄에 하나 - 두 줄짜리 카드로 만들면 한 화면에 들어오는
     * 결과가 절반이 된다. */
    <Dialog
      open={!!open}
      onClose={onClose}
      maxWidth={false}
      fullWidth
      aria-label="통합 검색"
      sx={{
        "& .MuiDialog-paper": {
          alignSelf: "flex-start", mt: { xs: 4, sm: 10 },
          width: "min(46rem, calc(100% - 2rem))", maxWidth: "none",
          borderRadius: `${RADIUS.lg}px`,
        },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2.5, py: 1.75, borderBottom: 1, borderColor: "divider" }}>
        <SearchRoundedIcon aria-hidden="true" sx={{ color: "text.secondary" }} />
        <InputBase
          inputRef={inputRef}
          autoFocus
          fullWidth
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="검색 (티켓, 문서, 게시판, 메뉴)"
          inputProps={{ "aria-label": "통합 검색" }}
          sx={{ fontSize: FONT_SIZE.title }}
        />
      </Box>
      {/* 높이가 0인 자리를 늘 잡아 두면 결과 목록이 위아래로 튀지 않는다. */}
      <Box sx={{ height: "0.25rem" }}>
        {busy ? <LinearProgress aria-label="검색 중" sx={{ height: "0.25rem" }} /> : null}
      </Box>
      {/* 검색이 **실패했는데 메뉴/최근 방문이 하나라도 맞으면** 아래 목록이 그려지고, 빈 상태
          얼굴은 애초에 렌더되지 않는다 — 그러면 서버 오류가 화면에서 통째로 사라진다.
          E9 가 막으려던 실패("없다고 말하지 않는다")의 나머지 절반이 이 경계였다. 목록이
          있든 없든 실패는 실패라고 한 줄로 말한다. */}
      {failed && flat.length > 0 ? (
        <Box
          role="alert"
          sx={{
            display: "flex", alignItems: "center", gap: 1,
            px: 2.5, py: 1, borderBottom: 1, borderColor: "divider",
            bgcolor: (t) => t.palette.error.bg, color: "error.strong",
            fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK,
          }}
        >
          <ErrorOutlineRoundedIcon aria-hidden="true" sx={{ fontSize: FONT_SIZE.title }} />
          <Box component="span">
            티켓, 문서, 게시판 검색을 불러오지 못했습니다. 아래는 메뉴 결과만 있습니다.
          </Box>
        </Box>
      ) : null}
      <DialogContent sx={{ p: 0, maxHeight: "62vh" }}>
        {flat.length === 0 ? (
          /* 결과가 없는 세 상태를 **서로 다른 얼굴**로 그린다 (지시 14: "검색 중 Loading,
             결과 없음, Error State 도 포함"). 예전에는 셋 다 가운데 한 줄짜리 회색 문장이라,
             오류인지 아직 안 왔는지 정말 없는지가 문장을 읽어야만 구분됐다 — 팔레트는
             0.3초 안에 훑는 화면이라 그 구분이 글자에만 있으면 없는 것과 같다.
             빈 자리를 키우지 않는다: 아이콘 하나 + 제목 + 도움말 한 줄로 세로 리듬만 준다
             (지시 15 «Empty State 는 완성된 구획이지 큰 여백이 아니다»). */
          <PaletteMessage state={!q ? "prompt" : busy ? "busy" : failed ? "error" : "empty"} />
        ) : (
          <List dense disablePadding sx={{ py: 0.5 }}>
            {sections.map((section) => (
              <li key={section.key}>
                <ul style={{ padding: 0, margin: 0, listStyle: "none" }}>
                  {/* 붙박이 제목. 예전에는 구역을 벗어나 스크롤하면 지금 보는 것이 무엇인지
                      알 수 없었다. 줄마다 유형을 다시 적으면 같은 말을 두 번 하는 것이라
                      (지시 44) 제목이 따라오게 한다. */}
                  <ListSubheader
                    sx={{
                      bgcolor: "background.paper", color: "text.secondary", lineHeight: 2.2,
                      px: 2.5, fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold, letterSpacing: ".06em",
                      borderBottom: 1, borderColor: "divider",
                    }}
                  >
                    {section.label}
                  </ListSubheader>
                  {section.items.map((it) => (
                    <PaletteRow
                      key={it.key} item={it}
                      selected={flat.indexOf(it) === cursor}
                      onHover={() => setCursor(flat.indexOf(it))}
                      onPick={() => go(it.to)}
                    />
                  ))}
                </ul>
              </li>
            ))}
            {seeAll ? (
              <PaletteRow
                item={seeAll}
                selected={flat.indexOf(seeAll) === cursor}
                onHover={() => setCursor(flat.indexOf(seeAll))}
                onPick={() => go(seeAll.to)}
              />
            ) : null}
          </List>
        )}
      </DialogContent>
      {/* 키 안내는 상시로 둔다 - 팔레트를 키보드로 쓰는 사람에게 그것이 이 창의 사용법이다. */}
      <Box
        sx={{
          display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap",
          px: 2.5, py: 1, borderTop: 1, borderColor: "divider",
          fontSize: FONT_SIZE.caption, color: "text.secondary",
        }}
      >
        <Box component="span">↑ ↓ 이동</Box>
        <Box component="span">Enter 열기</Box>
        <Box component="span">Esc 닫기</Box>
      </Box>
    </Dialog>
  );
}

/* 결과가 없는 세 상태의 얼굴. 셋은 **다른 그림·다른 제목·다른 다음 행동**을 갖는다. */
const MESSAGE_FACE = {
  prompt: {
    Icon: SearchRoundedIcon,
    title: "무엇을 찾으시나요?",
    hint: "메뉴 이름, 티켓 제목, 문서 제목, 게시글 제목으로 찾을 수 있습니다.",
  },
  busy: { Icon: SearchRoundedIcon, title: "찾는 중…", hint: "" },
  /* 서버 오류를 "없다" 고 말하지 않는다 (E9). 예전에는 500 이든 네트워크 끊김이든
     전부 "검색 결과 없음" 이었다 — 사용자는 찾는 것이 정말 없다고 믿고 포기한다.
     그건 화면이 거짓말하는 것이고, 이 저장소가 곳곳에서 잡아낸 그 부류다. */
  error: {
    Icon: ErrorOutlineRoundedIcon,
    title: "검색하지 못했습니다",
    hint: "일시적인 문제일 수 있습니다. 잠시 후 다시 시도해 주세요.",
    tone: "error.main",
  },
  empty: { Icon: SearchOffRoundedIcon, title: "검색 결과 없음", hint: "다른 낱말이나 더 짧은 낱말로 찾아 보세요." },
};

function PaletteMessage({ state }) {
  const face = MESSAGE_FACE[state] || MESSAGE_FACE.empty;
  const { Icon } = face;
  return (
    <Box
      role={state === "error" ? "alert" : undefined}
      sx={{ px: 3, py: 4, display: "grid", justifyItems: "center", gap: 0.75, textAlign: "center" }}
    >
      <Icon aria-hidden="true" sx={{ fontSize: FONT_SIZE.pageTitle, color: face.tone || "text.faint" }} />
      {/* 제목에 검색어를 되풀이하지 않는다 — 바로 두 줄 위 입력창에 그대로 보인다
          (지시 44: 같은 말을 두 번 하지 않는다). */}
      <Typography sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.semibold, color: face.tone || "text.primary" }}>
        {face.title}
      </Typography>
      {face.hint ? (
        <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.bodySm, maxWidth: "34rem", ...KO_WORD_BREAK }}>
          {face.hint}
        </Typography>
      ) : null}
    </Box>
  );
}

/* 결과 한 줄. 고른 줄은 앞머리 레일 + 안쪽 바탕 + **Enter 표지**로 말한다 - 옅은 배경만으로는
 * 키보드로 빠르게 훑을 때 놓친다(지시 14). 유형은 왼쪽 아이콘과 붙박이 구역 제목이 말한다 —
 * 줄마다 유형을 글자로 다시 적으면 같은 말을 두 번 한다(지시 44). */
function PaletteRow({ item, selected, onHover, onPick }) {
  const Icon = item.Icon;
  return (
    <ListItemButton
      selected={selected}
      onMouseEnter={onHover}
      onClick={onPick}
      sx={{
        px: 2.5, py: 0.875, gap: 1.5, alignItems: "center",
        /* 레일은 **style 까지 적어야 그려진다.** 예전에는 `borderInlineStart: 2` 만 두었는데,
           MUI 의 border 스타일 함수는 그것을 `border-inline-start: 2px` 로만 펴고 `-style` 을
           넣지 않는다 — CSS 기본값이 `none` 이라 폭 2px 짜리 **보이지 않는** 레일이 됐다.
           독립 검수자가 배포본 픽셀에서 "선택 신호가 4% 워시 하나뿐" 이라고 잡은 자리다.
           지시 14 가 요구한 선택 표현은 신호 둘(앞머리 레일 + 안쪽 바탕)이므로 하나가
           안 그려지면 요구가 미이행이다. */
        borderInlineStartStyle: "solid",
        borderInlineStartWidth: "2px",
        borderInlineStartColor: "transparent",
        "&.Mui-selected, &.Mui-selected:hover": {
          bgcolor: "background.inset",
          /* 색을 **콜백으로** 푼다. `borderInlineStartColor` 는 MUI 의 border 설정 목록에
             없어서 값이 그대로 CSS 로 나간다 — `"primary.main"` 이라고 적으면 팔레트가
             해석되지 않고 `border-inline-start-color: primary.main` 이라는 무효 선언이
             된다(배포본 실측: 선택 줄 왼쪽 x=592 가 여전히 오목면 색). 같은 함정의 두 번째
             층이다: 첫 층은 style 이 없어서, 두 번째 층은 색이 안 풀려서 안 그려진다. */
          borderInlineStartColor: (t) => t.palette.primary.main,
        },
      }}
    >
      {/* 아이콘 칸은 결과가 있든 없든 같은 폭이다 — 매핑 없는 새 유형이 와도 글자 시작선이
          흔들리지 않는다(사이드바가 42px 시작선을 지키는 것과 같은 이유). */}
      <Box
        aria-hidden="true"
        sx={{
          flexShrink: 0, width: "1.25rem", display: "grid", placeItems: "center",
          color: selected ? "primary.main" : "text.faint",
        }}
      >
        {Icon ? <Icon aria-hidden="true" sx={{ fontSize: remPx(ICON.nav) }} /> : null}
      </Box>
      <Box sx={{ minWidth: 0, flex: 1, display: "flex", alignItems: "baseline", gap: 1.5 }}>
        <Typography
          component="span"
          sx={{
            /* 굵기는 선택으로 바뀌지 않는다 — 한글에서 weight 전환은 글자 폭을 실제로
               바꿔 줄이 움직인다. 선택 신호는 이미 셋이다(레일 · 오목면 · Enter 표지).
               nav 라벨 굵기는 제품 전체에서 medium 고정이다(PLAN «Navigation 상태»). */
            fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.medium,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}
        >
          {item.label}
        </Typography>
        {item.hint ? (
          <Typography
            component="span"
            color="text.secondary"
            sx={{ fontSize: FONT_SIZE.caption, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}
          >
            {item.hint}
          </Typography>
        ) : null}
      </Box>
      {/* 고른 줄에서만 나온다. 아래 붙박이 키 안내가 규칙을 말한다면 이것은 **지금 Enter 가
          무엇을 여는지**를 그 줄 위에서 말한다 — 자리를 늘 잡아 두면 목록이 흔들리므로
          visibility 가 아니라 조건부 렌더로 두되 폭은 고정한다. */}
      <Box aria-hidden="true" sx={{ flexShrink: 0, width: "1.125rem", display: "grid", placeItems: "center", color: "text.faint" }}>
        {selected ? <KeyboardReturnRoundedIcon sx={{ fontSize: FONT_SIZE.title }} /> : null}
      </Box>
    </ListItemButton>
  );
}

/* Ctrl+K / Cmd+K 전역 단축키. 입력 중에도 열리게 두되(팔레트가 검색이라 자연스럽다)
 * 브라우저 기본 동작은 막는다. */
export function useCommandPaletteHotkey(setOpen) {
  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);
}
