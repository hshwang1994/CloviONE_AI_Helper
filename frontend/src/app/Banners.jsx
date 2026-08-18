import React from "react";
import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Button from "@mui/material/Button";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import { api } from "../lib/api.js";

/* 화면 위쪽 띠 — **임퍼소네이션 하나만 남는다** (지시 1·55·67).
 *
 * 지시 1 은 상단의 `안내`·`장애` 알림 영역을 없애고 우측 상단 종을 사용자 알림의 단일
 * 진입점으로 쓰라고 한다. 그래서 여기 있던 CRITICAL 한 줄과 헤더의 상태 칩을 걷어내고,
 * 사용자가 알아야 할 시스템 알림은 `NotificationBell` 안의 "시스템 상태" 묶음으로 옮겼다.
 *
 * **임퍼소네이션 배너는 남는다.** 이것은 알림이 아니라 **보안 상태 표시**다 — 지금 남의
 * 눈으로 보고 있다는 사실은 닫을 수 있으면 안 되고, 종 안에 접혀 있어도 안 된다(지시 55).
 *
 * 지시 67 도 함께 지킨다: 없앤 것은 **사용자 화면의 상시 띠**이지 운영 상태 정보 자체가
 * 아니다. 서비스 Health·조치 필요 항목은 관리자 대시보드와 진단 화면이 계속 보여 준다.
 *
 * **PA-RC-0016 이전에는 시스템 상태·공지가 전부 여기서 Alert로 세로로 쌓여, 관리자 화면
 * 5장(331.5px)·사용자 화면 4장(216px)이 전 라우트에서 상시 첫 화면을 잡아먹었다**(실측).
 * 판정 조건(WARNING/CRITICAL 임계, 공지 노출 대상)은 하나도 안 바꿨다 — 같은 정보를
 * 화면 어디에 얼마나 크게 두는가만 바꿨다. 시스템 상태·공지의 실제 데이터 조회·병합·닫기는
 * StatusNotices.jsx의 useStatusNotices()가 맡는다(칩과 이 줄이 같은 목록을 봐야 서로 다른
 * 개수를 말하는 모순이 안 생긴다 — AppShell.jsx가 훅 하나를 두 컴포넌트에 나눠 준다).
 *
 * **폴링에 대해.** 상태는 서버가 알려 준 주기(`poll_seconds`)로만 다시 묻는다 — 프런트에
 * 숫자를 박아 두면 부하를 줄이려 할 때 배포가 두 번 필요하다. 임퍼소네이션 상태는 자기
 * 세션에 대한 것이라 짧게 본다.
 *
 * 실패하면 **조용히 아무것도 그리지 않는다**. 배너를 못 불러온 것 때문에 화면 위에
 * 빨간 오류가 뜨면, 정작 아래 본문은 멀쩡한데 사용자는 앱이 고장 났다고 읽는다.
 */

function useImpersonation() {
  return useQuery({
    queryKey: ["impersonation-state"],
    queryFn: () => api("/api/admin/impersonation/state"),
    refetchInterval: 60000,
    retry: false,
    staleTime: 30000,
  });
}

function ImpersonationBanner({ data }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = React.useState(false);

  const stop = async () => {
    setBusy(true);
    try {
      await api("/api/admin/impersonation/stop", { method: "POST", body: {} });
      // 역할·이름이 통째로 바뀌므로 부분 갱신이 아니라 새로 읽는다. 어중간하게 남은
      // 캐시는 "관리자인데 사용자 메뉴가 보인다" 같은 뒤섞인 화면을 만든다.
      window.location.reload();
    } catch (e) {
      setBusy(false);
      qc.invalidateQueries({ queryKey: ["impersonation-state"] });
      /* 조용히 삼키면 **관리자가 남인 채로 계속 활동**하면서 빠져나온 줄 안다 (E5).
         대리 보기 중에는 그 사람 이름으로 기록이 남으므로, 못 빠져나온 것을 모르는 것이
         가장 위험하다. */
      toast((e && e.message) || "대리 보기를 종료하지 못했습니다. 다시 시도해 주세요.", "error");
    }
  };

  return (
    <Alert
      severity="warning"
      variant="filled"
      role="status"
      sx={{ borderRadius: 0, alignItems: "center" }}
      action={
        <Button color="inherit" size="small" onClick={stop} disabled={busy} sx={{ fontWeight: FONT_WEIGHT.extrabold }}>
          {busy ? "종료 중…" : "대리 보기 종료"}
        </Button>
      }
    >
      <AlertTitle sx={{ fontWeight: FONT_WEIGHT.extrabold, mb: 0 }}>
        {data.target_name || data.target_email}님의 화면을 보는 중입니다 (읽기 전용)
      </AlertTitle>
      <Box component="span" sx={{ fontSize: FONT_SIZE.bodySm }}>
        {data.actor_name}(으)로 로그인한 상태이며, 이 화면에서는 어떤 변경도 저장되지 않습니다.
        {data.blocked_write_count ? ` 지금까지 차단된 변경 시도 ${data.blocked_write_count}건.` : ""}
      </Box>
    </Alert>
  );
}

/** **아무것도 그릴 게 없으면 감싸는 Box 자체를 안 만든다.** `display:"grid"`인 빈 Box는
 * 높이는 0이 돼도 폭은 부모(`#main-content`, flex:1)를 그대로 채운다 — 눈에는 안 보이지만
 * 실측 도구(scrollWidth/union-of-boxes 계열)가 그 폭을 "본문 폭"으로 잘못 잰다(PA-RC-0016
 * 4K 측정에서 실제로 재현: 화면엔 아무 띠도 없는데 본문 폭이 3500px로 나왔다). 조건부
 * 렌더로 아예 없애는 편이 "폭 0으로 만드는" 임시방편보다 정직하다. */
export function Banners() {
  const impersonation = useImpersonation();
  const data = impersonation.data;
  if (!data || !data.impersonating) return null;
  return <ImpersonationBanner data={data} />;
}

export default Banners;
