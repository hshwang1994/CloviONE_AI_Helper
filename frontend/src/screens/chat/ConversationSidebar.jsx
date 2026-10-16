import React, { useState } from "react";
import Box from "@mui/material/Box";
import InputBase from "@mui/material/InputBase";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import { Badge, Button, Callout, ErrorState, ListEmptyState, OverflowMenu, Segmented, Skeleton } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { fmtDateTime, fmtListStamp } from "../../lib/format.js";
import { SearchBox } from "../../ui/filters.jsx";

/* AI 도우미 대화 목록 — 채팅방 목록과 같은 어휘다(RULES §9 · `ChatRooms.jsx::RoomRow`): 고른 행은 함몰면 + 왼쪽 레일 3px +
 * `aria-current`, 올리면 한 단계 면. 행은 높이가 같고(제목 두 줄까지, 넘치면 말줄임 · 전체 제목은 `title`), 시각은 오른쪽 고정
 * 칸이다(마지막 대화 시각 — 목록 순서와 같은 값).
 *
 * 행의 보조 동작(이름 바꾸기 · 보관 · 꺼내기 · 삭제)은 「더 보기」 하나로 모았다. 예전에는 아이콘 셋이 행에 올리면 날짜 자리에
 * 서고 툴팁이 이웃 행을 가렸으며, 단추 옆의 JSX 주석이 화면에 글로 그려져 고른 대화의 제목을 한 글자로 밀었다. 「더 보기」는
 * 올리기 · 초점 · 고름 · 메뉴가 열린 동안 보이고(불투명도 — 키보드로 닿는다), 터치 기기에서는 늘 보인다. */

/** 줄 안 이름 고치기 — 목록 행과 스레드 머리가 같이 쓴다. Enter · 칸을 떠나면 저장, Esc 는 취소, 한글 조합 중 Enter 는 무시한다.
 *  저장이 실패하면 칸을 닫지 않는다(친 글이 사라지지 않게). 끝나면 `onDone` 이 초점을 돌려줄 자리를 정한다.
 *
 *  초점은 다음 그림에서 옮긴다(`autoFocus` 가 아니다). 「더 보기」 메뉴에서 열면 메뉴가 닫히며 초점을 메뉴 단추로 돌려주는데,
 *  칸이 먼저 초점을 받으면 그 순간 흐려져(저장할 것 없음) 칸이 열리자마자 닫혔다. 열면 기존 이름을 모두 골라 둔다. */
export function InlineRename({ value, label, onSave, onDone, sx }) {
  const [val, setVal] = useState(value || "");
  const settled = React.useRef(false);
  const inputRef = React.useRef(null);
  React.useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      if (el.select) el.select();
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  function finish(saved) {
    if (settled.current) return;
    settled.current = true;
    if (onDone) onDone(saved);
  }
  function commit() {
    const t = val.trim();
    if (!t || t === (value || "")) { finish(false); return; }
    Promise.resolve(onSave(t)).then(() => finish(true)).catch(() => { settled.current = false; });
  }
  return (
    <InputBase
      fullWidth inputRef={inputRef} value={val}
      inputProps={{ maxLength: 200, "aria-label": "이름 바꾸기: " + label }}
      onChange={(e) => setVal(e.target.value)}
      onKeyDown={(e) => {
        if (e.nativeEvent.isComposing || e.keyCode === 229) return;
        if (e.key === "Enter") { e.preventDefault(); commit(); }
        if (e.key === "Escape") { e.preventDefault(); finish(false); }
      }}
      onBlur={commit}
      sx={{ px: 1, py: 0.25, fontSize: FONT_SIZE.bodySm, border: 1, borderColor: "primary.main", borderRadius: 1.5,
            bgcolor: "background.paper", ...sx }}
    />
  );
}

/* 행의 높이 — 제목 두 줄(0.875rem × 1.45)과 위아래 여백이다. 한 줄 제목도 같은 높이라 목록의 줄 간격이 고르다. */
const ROW_MIN = "3.5rem";

function rowTime(c) {
  return c.last_message_at || c.updated_at || c.created_at || null;
}

/** 대화 한 줄. 제목 링크(`#/chat/<id>`)는 새 탭 열기도 된다 — 보통 누르면 주소만 바꾼다(`onSelect`). */
export function ConversationRow({ c, active, onSelect, onRename, onArchive, onDelete }) {
  const [editing, setEditing] = useState(false);
  const linkRef = React.useRef(null);
  const label = c.title || "새 대화";
  const ts = rowTime(c);
  const items = [
    { key: "rename", label: "이름 바꾸기", onClick: () => setEditing(true) },
    { key: "archive", label: c.archived ? "보관함에서 꺼내기" : "보관하기", onClick: () => onArchive(!c.archived) },
    { key: "delete", label: "삭제", tone: "danger", onClick: onDelete },
  ];
  return (
    <Box
      component="li"
      data-conversation-row={c.id}
      data-active={active ? "" : undefined}
      data-brand-role={active ? "selected-state" : undefined}
      sx={{
        position: "relative", display: "flex", alignItems: "center", minHeight: ROW_MIN, minWidth: 0,
        borderLeft: 3, borderLeftStyle: "solid", borderLeftColor: active ? "primary.main" : "transparent",
        bgcolor: active ? "background.inset" : "transparent",
        transition: "background-color .12s ease",
        "&:hover": { bgcolor: active ? "background.inset" : "action.hover" },
        "& .conv-menu": { opacity: active ? 1 : 0, transition: "opacity .12s ease" },
        "&:hover .conv-menu, &:focus-within .conv-menu, &:has([aria-expanded='true']) .conv-menu": { opacity: 1 },
        "@media (hover: none)": { "& .conv-menu": { opacity: 1 } },
      }}
    >
      {editing ? (
        <Box sx={{ flex: 1, minWidth: 0, px: 1, py: 0.75 }}>
          <InlineRename
            value={c.title || ""} label={label} onSave={onRename}
            onDone={() => { setEditing(false); requestAnimationFrame(() => linkRef.current && linkRef.current.focus()); }}
          />
        </Box>
      ) : (
        <Box
          component="a" ref={linkRef} href={"#/chat/" + c.id}
          aria-current={active ? "page" : undefined}
          onClick={(e) => {
            // 새 탭 · 새 창으로 여는 손짓은 브라우저에 맡긴다.
            if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
            e.preventDefault();
            onSelect(c.id);
          }}
          sx={{
            flex: 1, minWidth: 0, alignSelf: "stretch", display: "grid", gridTemplateColumns: "minmax(0,1fr) auto",
            columnGap: 1, alignItems: "center", pl: 1.25, pr: 0.5, py: 0.75,
            color: "text.primary", textDecoration: "none", outline: "none",
            "&:focus-visible": { outline: (t) => `2px solid ${t.palette.focusRing}`, outlineOffset: "-2px" },
          }}
        >
          <Box
            component="span" title={label}
            sx={{
              fontSize: FONT_SIZE.bodySm, lineHeight: 1.45, fontWeight: active ? FONT_WEIGHT.semibold : FONT_WEIGHT.regular,
              display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", ...KO_WORD_BREAK,
            }}
          >
            {label}
          </Box>
          <Box component="span" sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 0.25 }}>
            {ts ? (
              <Box component="time" dateTime={ts} title={fmtDateTime(ts)}
                sx={{ fontSize: FONT_SIZE.micro, color: "text.secondary", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                {fmtListStamp(ts)}
              </Box>
            ) : null}
            {c.archived ? <Badge value="archived" /> : null}
          </Box>
        </Box>
      )}
      <Box className="conv-menu" sx={{ flexShrink: 0, pr: 0.75, display: editing ? "none" : "flex" }}>
        <OverflowMenu size="sm" ariaLabel={"대화 동작: " + label} items={items} />
      </Box>
    </Box>
  );
}

/** 대화 목록 판 — 머리(새 대화 · 검색 · 보기)는 고정이고 목록만 굴러간다(스크롤 칸은 목록 하나). */
export function ConversationSidebar({
  convs, convItems, convFilter, setConvFilter, showArchived, setShowArchived,
  cid, onSelect, onNew, renameConv, archiveConv, deleteConv, confirm, toast,
  hasMoreConvs, loadMoreConvs, failure, emptyTotal = 0, onArchiveEmpty, headingId,
}) {
  async function archiveEmpty() {
    if (!(await confirm(
      `메시지가 하나도 없는 대화 ${emptyTotal}개를 보관합니다. 메시지가 있는 대화는 건드리지 않고, 보관한 대화는 보관함에서 다시 꺼낼 수 있습니다.`,
      { title: "빈 대화 보관", confirmLabel: `${emptyTotal}개 보관` },
    ))) return;
    onArchiveEmpty();
  }
  return (
    <Box sx={{ display: "flex", flexDirection: "column", minHeight: 0, height: "100%", minWidth: 0 }}>
      <Box sx={{ display: "grid", gap: 1.25, p: 1.5, borderBottom: 1, borderColor: "rule", flexShrink: 0 }}>
        <Box component="h2" id={headingId} className="sr-only">대화 목록</Box>
        {/* 「새 대화」는 보조다(조합 계약 C-4) — 이 화면의 채움은 입력의 「전송」 하나다. */}
        <Button onClick={onNew}>
          <AddRoundedIcon aria-hidden="true" sx={{ fontSize: "1.125rem", mr: 0.5 }} />새 대화
        </Button>
        {/* 🔴 검색 중에는 결과가 0건이어도 상자를 남긴다(S21) — 조건을 좁힌 사람이 넓히는 길은 그 조건을 적은 자리여야 한다.
            대화도 검색어도 없으면 찾을 것이 없어 상자를 그리지 않는다. 제목과 내용을 함께 찾는다(서버). */}
        {(convItems.length > 0 || convFilter.trim()) ? (
          <SearchBox layout="fill" immediate value={convFilter} onSearch={setConvFilter} placeholder="대화 검색" ariaLabel="대화 목록 검색" />
        ) : null}
        <Segmented
          value={showArchived ? "archived" : "active"} onChange={(v) => setShowArchived(v === "archived")}
          ariaLabel="대화 보기" options={[{ value: "active", label: "대화" }, { value: "archived", label: "보관함" }]}
          sx={{ width: "100%", "& [role='tab']": { flex: 1 } }}
        />
        {failure ? <Callout tone="danger" compact>{failure}</Callout> : null}
      </Box>
      {/* 굴러가는 칸은 목록 하나다. 이름표는 감싼 카드(넓은 틀) · 서랍(좁은 틀)이 「대화 목록」 머리글로 이미 단다 — 여기에 같은
          이름의 랜드마크를 하나 더 세우지 않는다(채팅방 목록과 같은 구조). */}
      <Box data-conversation-list="" sx={{ flex: 1, minHeight: 0, overflowY: "auto", scrollbarGutter: "stable" }}>
        {convs.isLoading ? <Box sx={{ p: 1.5 }}><Skeleton lines={4} /></Box>
          : convs.isError ? <Box sx={{ p: 1.5 }}><ErrorState layout="region" error={convs.error} onRetry={() => convs.refetch()} /></Box>
          : !convItems.length ? (
            <Box sx={{ p: 1.5 }}>
              <ListEmptyState
                size="compact"
                filtered={!!convFilter.trim()}
                onClear={() => setConvFilter("")}
                clearLabel="검색어 지우기"
                filteredTitle="검색 조건에 맞는 대화가 없습니다."
                filteredHelp={`'${convFilter.trim()}' 대신 다른 검색어로 검색하세요.`}
                title={showArchived ? "보관한 대화가 없습니다." : "대화가 없습니다."}
                help={showArchived ? "대화를 보관하면 여기에 모입니다." : "위의 '새 대화'를 눌러 시작하세요."}
              />
            </Box>
          ) : (
            <>
              <Box component="ul" role="list" sx={{ listStyle: "none", m: 0, p: 0 }}>
                {convItems.map((c) => (
                  <ConversationRow
                    key={c.id} c={c} active={c.id === cid}
                    onSelect={onSelect}
                    onRename={(title) => renameConv.mutateAsync({ id: c.id, title })}
                    onArchive={(archived) => archiveConv.mutateAsync({ id: c.id, archived }).then(() => {
                      if (toast) toast(archived ? "대화를 보관했습니다. 보관함에서 다시 꺼낼 수 있습니다." : "대화를 보관함에서 꺼냈습니다.", "success");
                    }, () => {})}
                    onDelete={async () => {
                      if (await confirm(`「${c.title || "새 대화"}」 대화를 삭제합니다. 되돌릴 수 없습니다.`,
                        { danger: true, title: "대화 삭제", confirmLabel: "삭제" })) deleteConv.mutate(c.id);
                    }}
                  />
                ))}
              </Box>
              {hasMoreConvs ? (
                <Box sx={{ display: "flex", justifyContent: "center", py: 1 }}>
                  <Button size="sm" variant="ghost" loading={convs.isFetching} onClick={loadMoreConvs}>대화 더 보기</Button>
                </Box>
              ) : null}
            </>
          )}
      </Box>
      {!showArchived && emptyTotal > 0 ? (
        <Box sx={{ px: 1.5, py: 1, borderTop: 1, borderColor: "rule", flexShrink: 0 }}>
          <Button size="sm" variant="ghost" onClick={archiveEmpty}>빈 대화 {emptyTotal}개 보관</Button>
        </Box>
      ) : null}
    </Box>
  );
}
