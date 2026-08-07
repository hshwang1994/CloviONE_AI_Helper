import React, { useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import InputBase from "@mui/material/InputBase";
import Paper from "@mui/material/Paper";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import EditRoundedIcon from "@mui/icons-material/EditRounded";
import Inventory2OutlinedIcon from "@mui/icons-material/Inventory2Outlined";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import UnarchiveOutlinedIcon from "@mui/icons-material/UnarchiveOutlined";
import { Badge, Button, EmptyState, ErrorState, Skeleton } from "../../ui/kit.jsx";
import { fmtShort } from "../chat-helpers.js";

// ── 대화 목록 항목 ──────────────────────────────────────────────────────────

/* 대화 목록 항목 — 호버 시 이름 변경(인라인)·보관·삭제. 빈 '새 대화'가 쌓여도 정리 가능.
 * 터치(호버 없음) 기기에서는 hover가 절대 안 일어나 액션에 영영 닿을 수 없으므로 항상 노출한다. */
function ConvItem({ c, active, onOpen, onRename, onDelete, onArchive }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(c.title || "");
  const label = c.title || "새 대화";
  // 이전엔 mutation 결과와 무관하게 setEditing(false)를 먼저 불러 입력을 닫았다 — PATCH가 실패하면
  // (422·네트워크 오류·409 등) 입력창이 조용히 닫히고 사이드바가 옛 제목으로 되돌아가, 사용자가 방금
  // 친 내용이 사라져도 눈에 잘 안 띄는 토스트 하나로만 알렸다. onRename이 돌려주는 프라미스가 성공할
  // 때만 편집 모드를 닫고, 실패하면 입력을 그대로 열어 둬 재시도/복사할 수 있게 한다.
  function commit() {
    const t = val.trim();
    if (!t || t === (c.title || "")) { setEditing(false); return; }
    Promise.resolve(onRename(t)).then(() => setEditing(false)).catch(() => {});
  }
  if (editing) {
    return (
      <Box sx={{ px: 0.5, py: 0.5 }}>
        <InputBase
          fullWidth autoFocus value={val} inputProps={{ maxLength: 200, "aria-label": "이름 변경: " + label }}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.nativeEvent.isComposing || e.keyCode === 229) return; if (e.key === "Enter") { e.preventDefault(); commit(); } if (e.key === "Escape") { setEditing(false); setVal(c.title || ""); } }}
          onBlur={commit}
          sx={{ px: 1, py: 0.5, fontSize: "0.875rem", border: 1, borderColor: "primary.main", borderRadius: 1.5, bgcolor: "background.paper" }}
        />
      </Box>
    );
  }
  const act = (title, ariaLabel, icon, onClick) => (
    <Tooltip title={title}>
      <IconButton size="small" aria-label={ariaLabel} onClick={onClick}
        sx={{ minWidth: "2rem", minHeight: "2rem", color: "text.secondary" }}>{icon}</IconButton>
    </Tooltip>
  );
  return (
    <Box
      sx={{
        display: "flex", alignItems: "center", borderRadius: 2, minWidth: 0,
        opacity: c.archived ? 0.65 : 1,
        bgcolor: active ? (t) => alpha(t.palette.primary.main, 0.12) : "transparent",
        transition: "background .12s ease",
        "&:hover, &:focus-within": { bgcolor: (t) => alpha(t.palette.primary.main, active ? 0.16 : 0.08) },
        "&:hover .chat-conv-actions, &:focus-within .chat-conv-actions": { display: "flex" },
        "&:hover .chat-conv-time, &:focus-within .chat-conv-time": { display: "none" },
        "@media (hover: none)": { "& .chat-conv-actions": { display: "flex" }, "& .chat-conv-time": { display: "none" } },
      }}
    >
      <Box
        component="button" type="button" onClick={onOpen}
        sx={{
          flex: 1, minWidth: 0, textAlign: "left", border: 0, background: "none", cursor: "pointer",
          px: 1.5, py: 1, borderRadius: 2, font: "inherit", fontSize: "0.875rem",
          fontWeight: active ? 700 : 400,
          color: active ? "primary.main" : "text.primary",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}
      >
        {label}
      </Box>
      {/* 보관됨은 호버 아이콘만으로는 쉼 상태에서 구분되지 않는다, 항상 보이는 태그로 표시한다. */}
      {c.archived ? <Badge value="archived" /> : null}
      {c.updated_at ? (
        <Typography className="chat-conv-time" sx={{ flexShrink: 0, ml: "auto", pr: 1, fontSize: "0.6875rem", color: "text.secondary", whiteSpace: "nowrap" }}>
          {fmtShort(c.updated_at)}
        </Typography>
      ) : null}
      {/* 목록에 같은 버튼이 대화 수만큼 있어서, '삭제'만으로는 스크린리더 사용자가 어느 대화의
          삭제 버튼인지 알 수 없다, 대화 제목을 라벨에 포함한다. */}
      <Box className="chat-conv-actions" sx={{ display: "none", flexShrink: 0, pr: 0.5 }}>
        {act("이름 변경", "이름 변경: " + label, <EditRoundedIcon sx={{ fontSize: "1rem" }} />, () => { setVal(c.title || ""); setEditing(true); })}
        {act(c.archived ? "보관 해제" : "보관", (c.archived ? "보관 해제: " : "보관: ") + label,
          c.archived ? <UnarchiveOutlinedIcon sx={{ fontSize: "1rem" }} /> : <Inventory2OutlinedIcon sx={{ fontSize: "1rem" }} />,
          () => onArchive(!c.archived))}
        {act("삭제", "대화 삭제: " + label, <DeleteOutlineRoundedIcon sx={{ fontSize: "1rem" }} />, onDelete)}
      </Box>
    </Box>
  );
}

// ── 대화 목록 사이드바 ──────────────────────────────────────────────────────

/* 좁은 폭에서는 오버레이 서랍(Esc·백드롭·포커스 이동·inert), xl 이상에서는 열로 상주한다.
 * inert는 '서랍인데 닫혀 있을 때'에만 건다 — 상주 상태에 걸면 목록 전체가 키보드/스크린리더에서
 * 사라진다.
 *
 * K-H3(중첩 스크롤): 이 aside 자체에는 overflow를 걸지 않는다 — 대화 목록만 스크롤한다(사이드바
 * 전체가 아니라). '새 대화' 버튼과 보관 토글, 검색창은 항상 위에 고정되고, 목록만 아래쪽 flex:1
 * 칸 안에서 스크롤된다. 예전엔 이 aside에도 overflowY:auto가 걸려 있어, 목록을 끝까지 보려면
 * 바깥(사이드바)과 안(목록) 두 스크롤바를 번갈아 만져야 했다. */
export function ConversationSidebar({
  asideRef, listIsDrawer, sideOpen, closeSideDrawer, setSideOpen,
  convs, convItems, convFilter, setConvFilter, showArchived, setShowArchived,
  cid, setCid, setComposingNew, clearDraft, textareaRef,
  renameConv, archiveConv, deleteConv, confirm,
}) {
  const q = convFilter.trim().toLowerCase();
  const filtered = q ? convItems.filter((c) => (c.title || "새 대화").toLowerCase().includes(q)) : convItems;

  return (
    <>
      <Box
        component="aside" id="chat-conv-drawer" ref={asideRef}
        {...(listIsDrawer && !sideOpen ? { inert: "", "aria-hidden": "true" } : {})}
        sx={{
          position: { xs: "absolute", xl: "static" },
          top: 0, left: 0, bottom: 0, zIndex: 20,
          width: { xs: "18.75rem", xl: "auto" }, maxWidth: { xs: "85%", xl: "none" },
          borderRight: 1, borderColor: "divider", bgcolor: "background.paper",
          display: "flex", flexDirection: "column", gap: 1.5, p: 1.5, minHeight: 0, minWidth: 0,
          transform: { xs: sideOpen ? "none" : "translateX(-100%)", xl: "none" },
          transition: "transform .2s ease",
          boxShadow: { xs: sideOpen ? 8 : 0, xl: 0 },
        }}
      >
        <Button variant="primary" onClick={() => { clearDraft(); setComposingNew(true); setCid(null); setSideOpen(false); textareaRef.current && textareaRef.current.focus(); }}>
          <AddRoundedIcon aria-hidden="true" sx={{ fontSize: "1.125rem", mr: 0.5 }} />새 대화
        </Button>
        <Box component="label" sx={{ display: "flex", alignItems: "center", gap: 1, fontSize: "0.8125rem", color: "text.secondary", cursor: "pointer" }}>
          <Box component="input" type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} sx={{ m: 0 }} />
          보관된 대화 보기
        </Box>
        {/* 대화가 쌓일수록 스크롤만으로 찾기 어렵다 — 이미 불러온 전체 목록을 제목 부분일치로
            클라이언트에서만 좁힌다(백엔드 변경 불필요). */}
        {convItems.length > 0 ? (
          <Paper variant="outlined" sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.25, borderRadius: 2 }}>
            <SearchRoundedIcon aria-hidden="true" sx={{ fontSize: "1.125rem", color: "text.secondary" }} />
            <InputBase
              type="search" fullWidth placeholder="대화 제목 검색" value={convFilter}
              onChange={(e) => setConvFilter(e.target.value)}
              inputProps={{ "aria-label": "대화 목록 검색" }}
              sx={{ fontSize: "0.875rem" }}
            />
          </Paper>
        ) : null}
        {/* 대화 목록만 스크롤한다(사이드바 전체가 아니라) — '새 대화' 버튼과 보관 토글은 항상 위에
            고정되고, 목록이 사이드바 높이를 넘칠 때만 이 안에서 스크롤된다. */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25, flex: 1, minHeight: 0, overflowY: "auto", pr: 0.5, scrollbarGutter: "stable" }}>
          {convs.isLoading ? <Skeleton lines={4} />
            : convs.isError ? <ErrorState error={convs.error} onRetry={() => convs.refetch()} />
            : !convItems.length
              /* 빈 상태는 kit `EmptyState` 로. 회색 한 줄은 로딩 중인지·보관 필터 때문인지·
                 정말 없는 건지 구분해 주지 않는다(E계열 지적, `GroupedTickets` 와 같은 수정).
                 `.k-empty` + `role="status"` 가 따라오는 것도 이득이다 — 낭독되고, 기준 대조
                 도구가 "데이터가 없어 카드가 0" 인 화면을 디자인 불일치로 세지 않게 된다. */
              ? (showArchived
                  ? <EmptyState title="보관된 대화가 없습니다"
                      help="대화를 보관하면 여기에 모입니다. 위 체크를 풀면 진행 중인 대화가 보입니다." />
                  : <EmptyState title="아직 대화가 없습니다"
                      help="위의 '새 대화'를 눌러 시작하세요. 지금 보고 있는 화면을 기준으로 물어볼 수 있습니다." />)
              : (filtered.length ? filtered.map((c) => (
                  <ConvItem key={c.id} c={c} active={c.id === cid}
                    onOpen={() => { if (c.id !== cid) clearDraft(); setCid(c.id); setComposingNew(false); setSideOpen(false); textareaRef.current && textareaRef.current.focus(); }}
                    onRename={(title) => renameConv.mutateAsync({ id: c.id, title })}
                    onArchive={(archived) => archiveConv.mutate({ id: c.id, archived })}
                    onDelete={async () => { if (await confirm("이 대화를 삭제할까요? 되돌릴 수 없습니다.", { danger: true, confirmLabel: "대화 삭제" })) deleteConv.mutate(c.id); }} />
                )) : <Typography sx={{ fontSize: "0.8125rem", color: "text.secondary", px: 1 }}>검색 결과가 없습니다.</Typography>)}
        </Box>
      </Box>
      {sideOpen && listIsDrawer ? (
        <Box onClick={closeSideDrawer} aria-hidden="true"
          sx={{ position: "absolute", inset: 0, zIndex: 15, bgcolor: (t) => alpha(t.palette.common.black, 0.4) }} />
      ) : null}
    </>
  );
}
