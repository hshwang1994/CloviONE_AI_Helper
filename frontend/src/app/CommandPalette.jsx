import React from "react";
import { useQuery } from "@tanstack/react-query";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import InputBase from "@mui/material/InputBase";
import LinearProgress from "@mui/material/LinearProgress";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import ListSubheader from "@mui/material/ListSubheader";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import { useNavigate } from "react-router-dom";
import { isSearchable, normalizeQuery, routeOf, searchApi, searchResultsPath } from "../lib/search.js";

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
  const inputRef = React.useRef(null);
  const debounced = useDebounced(q);

  React.useEffect(() => { if (open) setQ(""); }, [open]);

  // 메뉴(로컬) — 즉시.
  const navResults = React.useMemo(() => {
    const needle = normalize(q);
    return (groups || [])
      .map((g) => ({
        group: g.group,
        items: g.items.filter((it) => !needle || normalize(it.label).includes(needle) || normalize(g.group).includes(needle)),
      }))
      .filter((g) => g.items.length);
  }, [groups, q]);

  // 콘텐츠(서버) — 디바운스 후. 팔레트가 닫혀 있으면 요청하지 않는다.
  const searchable = isSearchable(debounced);
  const search = useQuery({
    queryKey: ["search", "palette", normalizeQuery(debounced)],
    queryFn: () => searchApi(debounced, { limit: 5 }),
    enabled: !!open && searchable,
    staleTime: 15_000,
  });

  const sections = React.useMemo(() => {
    const out = navResults.map((g) => ({
      key: "nav:" + g.group,
      label: g.group,
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
    <Dialog
      open={!!open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      aria-label="통합 검색"
      sx={{ "& .MuiDialog-paper": { alignSelf: "flex-start", mt: { xs: 4, sm: 12 }, borderRadius: 3 } }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, px: 3, py: 2, borderBottom: 1, borderColor: "divider" }}>
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
          sx={{ fontSize: "1rem" }}
        />
        <Box component="kbd" sx={{ fontSize: "0.6875rem", color: "text.secondary", border: 1, borderColor: "divider", borderRadius: 1, px: 1, py: 0.25 }}>
          Esc
        </Box>
      </Box>
      {/* 높이가 0인 자리를 늘 잡아 두면 결과 목록이 위아래로 튀지 않는다. */}
      <Box sx={{ height: "0.25rem" }}>
        {busy ? <LinearProgress aria-label="검색 중" sx={{ height: "0.25rem" }} /> : null}
      </Box>
      <DialogContent sx={{ p: 0, maxHeight: "60vh" }}>
        {flat.length === 0 ? (
          <Typography sx={{ p: 4, textAlign: "center" }} color="text.secondary">
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
          <List dense disablePadding>
            {sections.map((section) => (
              <li key={section.key}>
                <ul style={{ padding: 0, margin: 0, listStyle: "none" }}>
                  <ListSubheader disableSticky sx={{ bgcolor: "transparent", fontSize: "0.6875rem", fontWeight: 800, letterSpacing: ".04em" }}>
                    {section.label}
                  </ListSubheader>
                  {section.items.map((it) => {
                    const idx = flat.indexOf(it);
                    return (
                      <ListItemButton
                        key={it.key}
                        selected={idx === cursor}
                        onMouseEnter={() => setCursor(idx)}
                        onClick={() => go(it.to)}
                      >
                        <ListItemText primary={it.label} secondary={it.hint || null} />
                      </ListItemButton>
                    );
                  })}
                </ul>
              </li>
            ))}
            {seeAll ? (
              <ListItemButton
                key={seeAll.key}
                selected={flat.indexOf(seeAll) === cursor}
                onMouseEnter={() => setCursor(flat.indexOf(seeAll))}
                onClick={() => go(seeAll.to)}
              >
                <ListItemText primary={seeAll.label} secondary={seeAll.hint} />
              </ListItemButton>
            ) : null}
          </List>
        )}
      </DialogContent>
    </Dialog>
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
