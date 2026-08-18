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
import { useLocation, useNavigate } from "react-router-dom";
import { isSearchable, normalizeQuery, routeOf, searchApi, searchResultsPath } from "../lib/search.js";
import { readRecentNav } from "../lib/recentNav.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "../ui/theme.js";

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

const DEBOUNCE_MS = 220;

function normalize(s) {
  return String(s || "").toLowerCase().replace(/\s+/g, "");
}

/* 입력이 멎은 뒤에만 값을 흘려보낸다. 서버 검색 전용이고, 메뉴 검색은 로컬이라 즉시 반응한다. */
export function useDebounced(value, delay = DEBOUNCE_MS) {
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
      const byPath = new Map();
      for (const g of groups || []) {
        for (const it of g.items) byPath.set(it.to, it);
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
      items: g.items.map((it) => ({ key: "nav:" + it.to, label: it.label, hint: it.to, to: it.to })),
    }));
    const serverGroups = (search.data && search.data.groups) || [];
    for (const group of serverGroups) {
      out.push({
        key: "kind:" + group.kind,
        label: group.label,
        items: (group.items || []).map((item) => ({
          key: item.kind + ":" + item.id,
          label: item.title,
          hint: item.subtitle || "",
          to: routeOf(item),
        })),
      });
    }
    return out.filter((section) => section.items.length);
  }, [navResults, search.data]);

  // '모든 결과 보기'는 목록의 마지막 항목이다 — 키보드로도 닿아야 한다.
  const seeAll = React.useMemo(
    () => (searchable && search.data && search.data.total > 0
      ? { key: "see-all", label: `‘${normalizeQuery(debounced)}’ 검색 결과 모두 보기`,
          hint: `총 ${search.data.total}건`, to: searchResultsPath(debounced) }
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
      <DialogContent sx={{ p: 0, maxHeight: "62vh" }}>
        {flat.length === 0 ? (
          <Typography sx={{ px: 3, py: 5, textAlign: "center", ...KO_WORD_BREAK }} color="text.secondary">
            {!q
              ? "메뉴 이름이나 티켓, 문서, 게시글 제목을 입력하세요."
              : busy
                ? "찾는 중…"
                /* 서버 오류를 "없다" 고 말하지 않는다 (E9). 예전에는 500 이든 네트워크 끊김이든
                   전부 "검색 결과 없음" 이었다 — 사용자는 찾는 것이 정말 없다고 믿고 포기한다.
                   그건 화면이 거짓말하는 것이고, 이 저장소가 곳곳에서 잡아낸 그 부류다. */
                : failed
                  ? "검색하지 못했습니다. 잠시 후 다시 시도해 주세요."
                  : "검색 결과 없음"}
          </Typography>
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
                      bgcolor: "background.paper", color: "text.faint", lineHeight: 2.2,
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
          fontSize: FONT_SIZE.caption, color: "text.faint",
        }}
      >
        <Box component="span">↑ ↓ 이동</Box>
        <Box component="span">Enter 열기</Box>
        <Box component="span">Esc 닫기</Box>
      </Box>
    </Dialog>
  );
}

/* 결과 한 줄. 고른 줄은 앞머리 레일 + 안쪽 바탕으로 말한다 - 옅은 배경만으로는 키보드로
 * 빠르게 훑을 때 놓친다(지시 14). 유형은 붙박이 구역 제목이 말한다. */
function PaletteRow({ item, selected, onHover, onPick }) {
  return (
    <ListItemButton
      selected={selected}
      onMouseEnter={onHover}
      onClick={onPick}
      sx={{
        px: 2.5, py: 0.875, gap: 1.5, alignItems: "baseline",
        borderInlineStart: 2, borderColor: "transparent",
        "&.Mui-selected, &.Mui-selected:hover": {
          bgcolor: "background.inset", borderColor: "primary.main",
        },
      }}
    >
      <Box sx={{ minWidth: 0, flex: 1, display: "flex", alignItems: "baseline", gap: 1.5 }}>
        <Typography
          component="span"
          sx={{
            fontSize: FONT_SIZE.body, fontWeight: selected ? FONT_WEIGHT.semibold : FONT_WEIGHT.regular,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}
        >
          {item.label}
        </Typography>
        {item.hint ? (
          <Typography
            component="span"
            color="text.faint"
            sx={{ fontSize: FONT_SIZE.caption, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}
          >
            {item.hint}
          </Typography>
        ) : null}
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
