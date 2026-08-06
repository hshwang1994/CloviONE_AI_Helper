import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { useAuth } from "./auth.jsx";
import { Button, Modal, ModalFooter } from "../ui/kit.jsx";
import { MASCOT, MISC, SPOT } from "../lib/assets.js";

/* 첫 로그인 둘러보기 (계획서 Phase 6 사용자).
 *
 * ## 지켜야 하는 세 가지
 *
 * 1. **건너뛸 수 있다.** 모든 단계에 '건너뛰기'가 있고, Esc·바깥 클릭으로도 닫힌다.
 *    닫는 것 = 건너뛰는 것이다(닫았는데 다음에 또 뜨면 그건 못 닫은 것이다).
 * 2. **건너뛴 사람에게 다시 뜨지 않는다.** 판정은 **서버**가 한다(GET /api/me/preferences 의
 *    tour.show). localStorage 에 두면 다른 PC·시크릿 창·브라우저 초기화 후 다시 뜬다 —
 *    "껐는데 또 나온다"는 사용자가 화면을 신뢰하지 않게 되는 가장 빠른 길이다.
 * 3. **홈에서만 자동으로 시작한다.** 어느 화면에서든 갑자기 모달이 덮으면 하려던 일이
 *    끊긴다. 첫 진입 화면이 홈(/me)이므로 거기서만 연다. 나중에 다시 보고 싶으면
 *    내 프로필의 '둘러보기 다시 보기'가 있다.
 *
 * 단계마다 '여기로 가기'가 있어서 안내가 끝나면 그 화면에 실제로 도착한다 — 읽고 나서
 * 어디로 가야 하는지 다시 찾아야 하는 안내는 안 읽는 것과 같다.
 */

// 자동 시작 화면. 홈 말고 다른 곳에서 갑자기 덮지 않는다.
export const TOUR_AUTOSTART_PATH = "/me";

export const TOUR_STEPS = [
  {
    key: "welcome",
    title: "클로비가 안내합니다",
    body: "ClovirAssist는 티켓, 문서, 팀 채팅을 한곳에서 보는 사내 업무 도우미입니다. 30초만 둘러보면 어디부터 볼지 알 수 있습니다.",
    art: MISC.onboarding,
  },
  {
    key: "home",
    title: "홈: 오늘 할 일",
    body: "오늘 마감, 지연, 진행 중인 내 티켓과 안 읽은 알림, 채팅이 한 화면에 모입니다. 아침에 여기부터 보세요.",
    art: SPOT.mywork,
    to: "/me",
    goLabel: "홈 보기",
  },
  {
    key: "tickets",
    title: "내 티켓",
    body: "내가 맡은 일의 전체 목록입니다. 상태, 마감을 바로 고칠 수 있고, 미할당 티켓에서 새 일을 가져올 수도 있습니다.",
    art: SPOT.sprint,
    to: "/my-tickets",
    goLabel: "내 티켓 보기",
  },
  {
    key: "chat",
    title: "AI 도우미와 팀 채팅",
    body: "오른쪽 아래 클로비 버튼을 누르면 언제든 AI 도우미가 열립니다. 팀 채팅방은 왼쪽 메뉴의 ‘팀 공간’에 있습니다.",
    art: MASCOT.talking,
    to: "/chat",
    goLabel: "AI 도우미 열기",
  },
  {
    key: "profile",
    title: "내 프로필에서 조용히 하기",
    body: "프로필 사진, 알림 설정, 방해금지를 직접 바꿀 수 있습니다. 방해금지를 켜도 알림은 그대로 쌓이고 배지만 조용해집니다.",
    art: MASCOT.idle,
    to: "/profile",
    goLabel: "내 프로필 열기",
  },
];

/** 진행 표시 점 — 몇 단계 남았는지 보이지 않으면 사람들은 첫 화면에서 닫는다. */
function Dots({ index, total }) {
  return (
    <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }} aria-hidden="true">
      {Array.from({ length: total }).map((_, i) => (
        <Box
          key={i}
          sx={{
            width: i === index ? "1.25rem" : "0.5rem", height: "0.5rem", borderRadius: "999px",
            bgcolor: i === index ? "primary.main" : "action.disabled",
            transition: "width .2s",
          }}
        />
      ))}
    </Box>
  );
}

export function Tour() {
  const auth = useAuth();
  const loc = useLocation();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [index, setIndex] = React.useState(0);
  // 서버가 '봤다'로 기록하기 전에도 화면에서는 즉시 닫힌다 — 네트워크를 기다리는 동안
  // 모달이 남아 있으면 '닫기가 안 눌린다'로 보인다.
  const [dismissed, setDismissed] = React.useState(false);

  const prefs = useQuery({
    queryKey: ["me-preferences"],
    queryFn: () => api("/api/me/preferences"),
    retry: false,
    enabled: !!(auth.data && auth.data.id),
    staleTime: 5 * 60 * 1000,
  });

  const mark = useMutation({
    mutationFn: (action) => api("/api/me/tour", { method: "POST", body: { action } }),
    onSuccess: (data) => qc.setQueryData(["me-preferences"], data),
    // 실패해도 화면은 이미 닫혔다. 다음 로그인에 한 번 더 뜨는 것이 최악의 결과이고,
    // 여기서 오류 토스트를 띄우면 "둘러보기를 껐더니 오류가 났다"로 읽힌다.
  });

  const show = !!(prefs.data && prefs.data.tour && prefs.data.tour.show);
  const atHome = loc.pathname === TOUR_AUTOSTART_PATH;
  const open = show && atHome && !dismissed;

  // 서버가 다시 'show' 로 바꾸면(내 프로필의 '다시 보기') 처음부터 열린다.
  React.useEffect(() => { if (show) { setDismissed(false); setIndex(0); } }, [show]);

  if (!open) return null;

  const step = TOUR_STEPS[index];
  const last = index === TOUR_STEPS.length - 1;

  function close(action) {
    setDismissed(true);
    mark.mutate(action);
  }

  return (
    <Modal
      open
      /* 바깥 클릭·Esc 로 닫는 것도 '건너뛰기'다 — 닫았는데 다음에 또 뜨면 그건 못 닫은 것이다. */
      onClose={() => close("skip")}
      title={step.title}
      size="sm"
      footer={
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, width: "100%", px: 3, py: 2, flexWrap: "wrap" }}>
          <Dots index={index} total={TOUR_STEPS.length} />
          <Box sx={{ flex: 1 }} />
          <Button variant="ghost" onClick={() => close("skip")}>건너뛰기</Button>
          {index > 0 ? <Button onClick={() => setIndex((i) => i - 1)}>이전</Button> : null}
          {last ? (
            <Button variant="primary" onClick={() => close("complete")}>시작하기</Button>
          ) : (
            <Button variant="primary" onClick={() => setIndex((i) => i + 1)}>다음</Button>
          )}
        </Box>
      }
    >
      <Box sx={{ display: "grid", gap: 2, justifyItems: "center", textAlign: "center" }}>
        {step.art ? (
          <Box
            component="img" src={step.art} alt="" aria-hidden="true" decoding="async"
            sx={{ width: { xs: "9rem", sm: "11rem" }, height: "auto" }}
          />
        ) : null}
        <Typography sx={{ maxWidth: "48ch" }}>{step.body}</Typography>
        {step.to ? (
          <Button
            onClick={() => {
              // 마지막 단계가 아니어도 '여기로 가기'를 누르면 그 화면으로 간다. 그 순간
              // 둘러보기는 끝난 것으로 본다 — 안내를 덮은 채 화면을 바꾸면 방해만 된다.
              close("complete");
              nav(step.to);
            }}
          >
            {step.goLabel || "여기로 가기"}
          </Button>
        ) : null}
      </Box>
    </Modal>
  );
}

export default Tour;
