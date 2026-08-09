import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { api } from "../lib/api.js";
import { Button, ErrorState, Modal, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { affiliation, hasDuplicateNames, personLabel } from "../lib/people.js";
import { ARCHIVED_SUFFIX } from "../lib/format.js";

/* 채팅방 참여자 — 접속 점(누구나 본다) + 그룹 관리 대화상자(방장만).
 *
 * ChatRoom.jsx 에서 떼어낸 이유: 방 페이지는 헤더 + 대화창이 본체이고, 관리 화면은 가끔
 * 열리는 대화상자다. 한 파일에 두면 대화창을 한 줄 고칠 때마다 관리 폼 전체가 함께 움직인다.
 *
 * **접속 점의 뜻**: 서버가 준 `online` 은 '이 방을 열어 두고 있다'이지 '앱에 로그인해 있다'가
 * 아니다(app/team_chat/service.py). 그래서 라벨도 '접속 중'이 아니라 '이 대화 보는 중'이다 —
 * 점 하나가 실제보다 많은 것을 주장하면 사람들은 답이 없을 때 상대를 오해한다.
 * 색만으로 상태를 전하지 않는다: 점 옆에 글자가 같이 나간다(WCAG 1.4.1).
 *
 * **'자리 비움'이 이제 진짜로 자리 비움이다** (X12). 예전에는 탭만 열어 두면 폴링이 계속
 * 돌아 퇴근한 사람도 밤새 켜져 있었다 — 그래서 이 두 라벨이 사실상 '탭을 닫았는가'만
 * 구분했다. 이제 브라우저가 사람의 입력이 끊긴 것을 보고 폴링에 `idle` 을 붙이고, 서버는
 * 그 폴링을 접속으로 세지 않는다. 판정 규칙과 그 이유는 `frontend/src/lib/idle.js` 에 있다.
 *
 * **권한은 서버가 준 `can_manage` 하나만 본다.** 여기서 '그룹인가? 방장인가? 전체인가?'를
 * 다시 계산하면 서버 규칙과 어긋나는 순간 '보이는데 누르면 403'이 된다.
 */

function Dot({ online }) {
  return (
    <Box
      component="span" aria-hidden="true"
      sx={{
        flexShrink: 0, width: "0.5rem", height: "0.5rem", borderRadius: "50%",
        bgcolor: online ? "success.main" : "action.disabled",
      }}
    />
  );
}

/** 참여자 한 줄(이름 + 접속 상태 + 방장 표시). 관리 동작은 오른쪽 slot 으로 받는다. */
function MemberRow({ member, meId, actions }) {
  return (
    <Box
      sx={{
        display: "flex", alignItems: "center", gap: 1, minWidth: 0,
        px: 1, py: 0.75, borderRadius: 1.5,
        "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
      }}
    >
      <Dot online={member.online} />
      {/* 이름 아래에 소속 한 줄. 방을 만들 때 쓰는 디렉터리는 부서를 보여 주는데 정작
          **만들어진 방의 참여자 목록은 이름만** 보여 줘서, 같은 이름 두 사람을 초대하면
          누가 누구인지 구분할 수 없었다(사용자 지시 2026-08-04). */}
      <Box sx={{ minWidth: 0 }}>
        <Typography sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "0.875rem", lineHeight: 1.35, fontWeight: member.user_id === meId ? 700 : 400 }}>
          {member.name || "알 수 없음"}{member.user_id === meId ? " (나)" : ""}
          {/* 떠난 사람이면 그렇다고 말한다 — 안 하면 답이 안 오는 대화를 며칠 기다린다(N3).
              같은 방의 말풍선(ChatPane.jsx)은 이미 이 표시를 한다 — 참여자 목록만 빠져 있으면
              같은 사람이 화면 위쪽(말풍선)과 이 관리 목록에서 다른 말을 하게 된다. */}
          {member.archived ? (
            <Box component="span" sx={{ fontWeight: 400, opacity: 0.6 }}> {ARCHIVED_SUFFIX}</Box>
          ) : null}
        </Typography>
        {affiliation(member) ? (
          <Typography sx={{ fontSize: "0.6875rem", color: "text.secondary", lineHeight: 1.35, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {affiliation(member)}
          </Typography>
        ) : null}
      </Box>
      {member.role === "owner" ? (
        <Chip size="small" label="방장" sx={{ flexShrink: 0, height: "1.25rem", fontSize: "0.6875rem" }} />
      ) : null}
      <Typography sx={{ flexShrink: 0, ml: "auto", fontSize: "0.75rem", color: "text.secondary" }}>
        {member.online ? "이 대화 보는 중" : "자리 비움"}
      </Typography>
      {actions}
    </Box>
  );
}

/* 방 헤더 아래 한 줄 요약 — 몇 명이 지금 이 대화를 보고 있는지. 전체 채팅은 참여자 개념이 없다.
 *
 * 이름은 최대 STRIP_NAMES 개만 낸다. 정원이 50명이라 전부 늘어놓으면 이 '한 줄'이 세 줄을
 * 차지해 대화창을 밀어낸다 — 숫자(참여자 N명)가 이미 전체를 말하고, 전체 명단은 '관리'
 * 대화상자에 있다. 접속 중인 사람을 먼저 보여 준다(지금 궁금한 것은 그쪽이다).
 */
const STRIP_NAMES = 8;

export function MemberStrip({ members }) {
  const rows = members || [];
  const dupNames = hasDuplicateNames(rows);
  if (!rows.length) return null;
  const online = rows.filter((m) => m.online).length;
  const ordered = [...rows].sort((a, b) => (b.online ? 1 : 0) - (a.online ? 1 : 0));
  const shown = ordered.slice(0, STRIP_NAMES);
  const rest = rows.length - shown.length;
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 1.5, px: 0.5 }}>
      <Typography sx={{ fontSize: "0.8125rem", color: "text.secondary" }}>
        참여자 {rows.length}명, 보는 중 {online}명
      </Typography>
      {/* 한 줄 요약이라 소속을 늘 붙이면 줄이 넘친다. **이름이 겹칠 때만** 붙인다 —
          그때가 이름만으로 못 고르는 유일한 경우다. */}
      {shown.map((m) => (
        <Box key={m.user_id} sx={{ display: "flex", alignItems: "center", gap: 0.5, minWidth: 0 }}>
          <Dot online={m.online} />
          <Typography sx={{ fontSize: "0.8125rem", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {dupNames && affiliation(m) ? personLabel(m) : (m.name || "알 수 없음")}
          </Typography>
        </Box>
      ))}
      {rest > 0 ? (
        <Typography sx={{ fontSize: "0.8125rem", color: "text.secondary" }}>외 {rest}명</Typography>
      ) : null}
    </Box>
  );
}

const INPUT_SX = {
  width: "100%", px: 1.5, py: 1.125, font: "inherit", fontSize: "0.875rem",
  border: 1, borderColor: "divider", borderRadius: 2,
  bgcolor: "background.default", color: "text.primary",
  "&:focus": { outline: "none", borderColor: "primary.main" },
};
const PICKER_SX = {
  display: "flex", flexDirection: "column", gap: 0.25, maxHeight: "14rem", overflowY: "auto",
  border: 1, borderColor: "divider", borderRadius: 2, p: 0.5,
};

export function ManageRoomModal({ open, onClose, roomId, title, members, meId }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [name, setName] = React.useState(title || "");
  const [picked, setPicked] = React.useState({});
  /* 열릴 때만 초기화한다(step 9 #6) — `title`을 의존성에 넣으면, 이미 열려 있는 채로
   * 이름을 저장했을 때(rename.onSuccess → refresh() → room 쿼리 재조회 → title prop 갱신)
   * 이 효과가 다시 돌아 방금 골라 둔 초대 대상(picked)까지 조용히 날아간다. 초대 성공
   * 경로는 이미 `setPicked({})`를 명시적으로 부르므로(위 invite.onSuccess), 여기서 title
   * 변화에 반응할 이유가 없다 - 모달이 열리는 순간의 값으로 한 번만 채우면 된다(그 시점에는
   * title 이 이미 최신값이다 - "관리" 버튼 자체가 room 데이터 로딩 후에만 보인다). */
  React.useEffect(() => { if (open) { setName(title || ""); setPicked({}); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["team-chat-msgs", roomId] });
    qc.invalidateQueries({ queryKey: ["team-chat-rooms"] });
  };
  const fail = (e, fallback) => toast((e && e.message) || fallback, "error");

  const dir = useQuery({
    queryKey: ["team-chat-directory"],
    queryFn: () => api("/api/team-chat/directory"),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const rename = useMutation({
    mutationFn: () => api(`/api/team-chat/rooms/${roomId}/rename`, { method: "POST", body: { title: name.trim() } }),
    onSuccess: () => { refresh(); toast("방 이름을 바꿨습니다.", "success"); },
    onError: (e) => fail(e, "이름을 바꾸지 못했습니다."),
  });
  const invite = useMutation({
    mutationFn: (ids) => api(`/api/team-chat/rooms/${roomId}/members/add`, { method: "POST", body: { user_ids: ids } }),
    onSuccess: (r) => {
      refresh();
      setPicked({});
      // 서버는 '실제로 새로 들어온 수'를 돌려준다 — 이미 있던 사람은 조용히 건너뛴다.
      toast(r && r.added ? `${r.added}명을 초대했습니다.` : "이미 모두 참여 중입니다.", "success");
    },
    onError: (e) => fail(e, "초대하지 못했습니다."),
  });
  const remove = useMutation({
    mutationFn: (userId) => api(`/api/team-chat/rooms/${roomId}/members/remove`, { method: "POST", body: { user_id: userId } }),
    onSuccess: () => { refresh(); toast("참여자를 내보냈습니다.", "success"); },
    onError: (e) => fail(e, "내보내지 못했습니다."),
  });
  const handOver = useMutation({
    mutationFn: (userId) => api(`/api/team-chat/rooms/${roomId}/owner`, { method: "POST", body: { user_id: userId } }),
    onSuccess: () => { refresh(); onClose(); toast("방장을 넘겼습니다. 이제 이 방을 관리할 수 없습니다.", "info"); },
    onError: (e) => fail(e, "방장을 넘기지 못했습니다."),
  });

  const rows = members || [];
  const memberIds = new Set(rows.map((m) => m.user_id));
  const candidates = ((dir.data && dir.data.users) || []).filter((u) => !memberIds.has(u.user_id));
  const chosen = Object.keys(picked).filter((k) => picked[k]);
  const busy = rename.isPending || invite.isPending || remove.isPending || handOver.isPending;

  const askRemove = async (m) => {
    const ok = await confirm(`${m.name || "이 참여자"}님을 내보냅니다. 이 방의 대화를 더는 볼 수 없게 됩니다.`,
      { title: "참여자 내보내기", confirmLabel: "내보내기", danger: true });
    if (ok) remove.mutate(m.user_id);
  };
  const askHandOver = async (m) => {
    const ok = await confirm(
      `${m.name || "이 참여자"}님에게 방장을 넘깁니다. 넘기면 나는 일반 참여자가 되고 이 방을 관리할 수 없습니다.`,
      { title: "방장 넘기기", confirmLabel: "넘기기", danger: true });
    if (ok) handOver.mutate(m.user_id);
  };

  return (
    <Modal open={open} onClose={onClose} title="채팅방 관리" size="md" footer={<Button onClick={onClose}>닫기</Button>}>
      <Box component="section" sx={{ mb: 3 }}>
        <Typography component="label" htmlFor="tc-rename" sx={{ display: "block", mb: 0.75, fontSize: "0.8125rem", fontWeight: 700 }}>
          방 이름
        </Typography>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
          {/* maxLength는 서버(app/team_chat/schemas.py::MAX_TITLE)와 같은 값이어야 한다 — 여기가
              더 짧으면 서버는 받아 줄 이름을 화면이 미리 못 치게 막는 것이 된다. */}
          <Box component="input" id="tc-rename" maxLength={200} value={name}
            onChange={(e) => setName(e.target.value)} sx={{ ...INPUT_SX, flex: 1, minWidth: "12rem" }} />
          <Button variant="primary" disabled={busy || !name.trim() || name.trim() === title}
            onClick={() => rename.mutate()}>저장</Button>
        </Box>
      </Box>

      <Box component="section" sx={{ mb: 3 }}>
        <Typography component="h3" sx={{ mb: 0.75, fontSize: "0.8125rem", fontWeight: 700 }}>
          참여자 {rows.length}명
        </Typography>
        <Box sx={PICKER_SX}>
          {rows.map((m) => (
            <MemberRow
              key={m.user_id} member={m} meId={meId}
              actions={m.user_id === meId ? null : (
                <Box sx={{ display: "flex", gap: 0.5, flexShrink: 0 }}>
                  <Button size="sm" disabled={busy} onClick={() => askHandOver(m)}>방장 넘기기</Button>
                  <Button size="sm" variant="danger" disabled={busy} onClick={() => askRemove(m)}>내보내기</Button>
                </Box>
              )}
            />
          ))}
        </Box>
        {/* 방장이 스스로 빠지는 길은 '방장 넘기기'와 '나가기' 둘뿐이다 — 스스로 내보내기는
            서버가 409로 막는다(주인 없는 방이 생기기 때문). 그래서 내 줄에는 버튼이 없다. */}
        <Typography sx={{ mt: 0.75, fontSize: "0.75rem", color: "text.secondary" }}>
          방장은 스스로 내보낼 수 없습니다. 빠지려면 방장을 넘기거나 방을 나가세요(마지막 한 명이 나가면 방이 사라집니다).
        </Typography>
      </Box>

      <Box component="section">
        <Typography component="h3" sx={{ mb: 0.75, fontSize: "0.8125rem", fontWeight: 700 }}>초대하기</Typography>
        {dir.isPending ? <Skeleton lines={3} />
          : dir.isError ? <ErrorState error={dir.error} onRetry={() => dir.refetch()} />
          : candidates.length === 0 ? (
            <Typography sx={{ color: "text.secondary", fontSize: "0.8125rem", py: 1.5 }}>초대할 다른 사용자가 없습니다.</Typography>
          ) : (
            <>
              <Box sx={PICKER_SX}>
                {candidates.map((u) => (
                  <Box key={u.user_id} component="label"
                    sx={{
                      display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.75, borderRadius: 1.5,
                      cursor: "pointer", fontSize: "0.875rem",
                      "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
                      "&:focus-within": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
                    }}>
                    <Box component="input" type="checkbox" checked={!!picked[u.user_id]}
                      onChange={(e) => setPicked((p) => ({ ...p, [u.user_id]: e.target.checked }))} sx={{ m: 0 }} />
                    <span>{personLabel(u)}</span>
                  </Box>
                ))}
              </Box>
              <Box sx={{ mt: 1 }}>
                <Button variant="primary" disabled={busy || chosen.length === 0} onClick={() => invite.mutate(chosen)}>
                  {chosen.length > 0 ? `${chosen.length}명 초대` : "초대"}
                </Button>
              </Box>
            </>
          )}
      </Box>
    </Modal>
  );
}
