import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { fmtDateTime } from "../../lib/format.js";
import { useAuth } from "../../app/auth.jsx";
import { DashSection, Note } from "../../ui/adminKit.jsx";
import { SettingVersions } from "../settings/SettingVersions.jsx";
import { PageHeader, Card, Badge, Button, Callout, Skeleton, ErrorState, useConfirm, useToast } from "../../ui/kit.jsx";
import { FONT_WEIGHT } from "../../ui/theme.js";
import { isWriteRole, NO_WRITE_REASON } from "./opsHelpers.js";

/* 유지보수 — 유지보수 모드(maintenance_mode 설정)를 켜고 끈다. 켜면 일반 사용자의 내용 쓰기가 차단된다.
   여기 문구는 서버가 실제로 막는 범위와 일치해야 한다 — 예전에는 게이트가 AI 채팅 2곳에만 걸려
   있는데도 "티켓 생성, 변경 등"을 예로 들고 있었다(하필 안 막히던 것). 범위는
   tests/security/test_maintenance_coverage.py 의 GATED_PREFIXES 가 정본이다.
 * 사용자에게 보일 점검 공지(maintenance_message)도 여기서 확인·수정한다. 쓰기는 admin/system_admin.
 *
 * 이 화면은 operator/auditor(읽기 전용 역할)도 들어온다(App.jsx RequireRole). 그 역할에게 쓰기
 * 컨트롤을 **숨기지 않는다** — 보이되 비활성이고, 왜 비활성인지 옆에 글자로 남긴다. 숨기면
 * '이 앱엔 그런 기능이 없다'로 읽혀, 권한을 받으면 할 수 있는 일을 영영 모른 채로 지나간다. */
export function Maintenance() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const auth = useAuth();
  const canWrite = isWriteRole(auth.data && auth.data.role);
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/admin/settings"), retry: false });
  // 이 값(refetchOnWindowFocus:false·staleTime 30s)이 언제 것인지 안 보이면, 탭을 오래 열어 둔
  // 관리자가 30초 넘게 낡은 on/off 상태를 '지금'으로 오해할 수 있다 — Dashboard.jsx처럼 마지막
  // 갱신 시각을 옆에 남긴다.
  const updated = q.dataUpdatedAt ? fmtDateTime(new Date(q.dataUpdatedAt).toISOString()) : null;
  // GET /api/admin/settings 응답은 {settings:{maintenance_mode:{value,...}}}로 한 겹 감싸져 있다.
  const settings = (q.data && q.data.settings) || {};
  const mm = settings.maintenance_mode || null;
  const on = mm ? (mm.value === true || mm.value === "true") : false;
  const serverMsg = settings.maintenance_message ? (settings.maintenance_message.value || "") : "";
  const [showVersions, setShowVersions] = React.useState(false);
  const [showModeVersions, setShowModeVersions] = React.useState(false); // 유지보수 모드 on/off 변경 기록
  // 초안은 서버 값으로 '지연 초기화'한다 — ['settings'] 캐시가 이미 따뜻할 때(설정 화면 방문 후·재방문)
  // ""로 초기화하면 seeding 이펙트 가드가 통과되지 않아 편집기가 빈 채로 뜨던 버그가 있었다.
  const [msg, setMsg] = React.useState(() => serverMsg);
  // 서버 값이 바뀔 때 로컬 초안을 덮어쓰되, 사용자가 편집 중(더티)이면 그대로 둔다 —
  // 다른 관리자가 공지를 바꾼 뒤 창 포커스로 refetch되면 작성 중이던 초안이 조용히 날아가던 문제.
  //
  // 갱신 함수 안에서 ref를 '읽으면' 안 된다. setMsg(fn)의 fn은 호출 시점이 아니라 **다음 렌더에서**
  // 실행되는데, 그때는 바로 아랫줄의 prevServerRef.current = serverMsg가 이미 끝난 뒤라
  // (prev === prevServerRef.current) 비교가 항상 거짓이 된다. 그래서 이 화면은 서버 공지를 한 번도
  // 초안에 싣지 못했다: 편집기는 늘 빈 채로 뜨고, 빈 초안 vs 서버 값 차이 때문에 '되돌리기'만
  // 항상 떠 있었으며, 관리자는 현재 공지 문구를 이 화면에서 볼 수 없었다(2026-08 QA 캡처로 확인).
  // 비교 기준값을 지역 const로 먼저 붙잡아 실행 시점과 무관하게 만든다.
  const prevServerRef = React.useRef(serverMsg);
  React.useEffect(() => {
    const prevServer = prevServerRef.current;
    prevServerRef.current = serverMsg;
    setMsg((prev) => (prev === prevServer ? serverMsg : prev));
  }, [serverMsg]);

  const toggle = useMutation({
    mutationFn: (val) => api("/api/admin/settings/maintenance_mode", { method: "PUT", body: { value: val } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      // SettingVersions.doRollback·SettingsMain.jsx의 onSaved와 동일한 이유: 이 값 자체가
      // '변경 기록(켜고 끈 이력)' 드로어(아래 showModeVersions)로 노출되는데, 그 드로어는
      // 별도 캐시(["settings","maintenance_mode","versions"])를 쓴다. 여기서 함께 무효화하지
      // 않으면 방금 켜고/끈 기록이 기본 staleTime(30초) 안에 열어도 빠져 있다.
      qc.invalidateQueries({ queryKey: ["settings", "maintenance_mode", "versions"] });
      toast("유지보수 모드를 전환했습니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });
  const saveMsg = useMutation({
    mutationFn: (val) => api("/api/admin/settings/maintenance_message", { method: "PUT", body: { value: val } }),
    // 저장 시작 시 이전 '미리 검증' 결과를 지운다 — 안 그러면 검증 통과 뒤 저장하면 이미 저장된
    // 값 옆에 낡은 '검증 통과' 배너가 계속 남고, 검증 없이 바로 저장해 실패하면 방금 실패와
    // 무관한 옛 검증 결과가 뒤섞여 어느 쪽이 지금 상태인지 알 수 없다.
    onMutate: () => { setMsgChecked(""); setMsgCheckErr(""); },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      // 위 toggle과 같은 이유 — '버전 기록'(showVersions)도 별도 캐시
      // (["settings","maintenance_message","versions"])라 여기서 함께 무효화한다.
      qc.invalidateQueries({ queryKey: ["settings", "maintenance_message", "versions"] });
      toast("점검 공지를 저장했습니다.", "success");
    },
    // 실패는 사라지는 토스트만이 아니라 미리 검증 실패와 같은 자리에도 남긴다 —
    // 필드 바로 옆에 지속되는 이유를 남겨 토스트를 놓쳐도 원인을 알 수 있게 한다.
    onError: (e) => { setMsgCheckErr(e.message); toast(e.message, "error"); },
  });
  // Settings.jsx의 다른 설정들은 '미리 검증'(dry-run)을 제공하는데 이 두 키(같은 PUT 엔드포인트)만
  // 여기 전용 화면이라 그 수단이 없었다 — 같은 백엔드 능력을 여기서도 노출한다.
  const dryRunMsg = useMutation({
    mutationFn: (val) => api("/api/admin/settings/maintenance_message/dry-run", { method: "POST", body: { value: val } }), });
  const [msgChecked, setMsgChecked] = React.useState("");
  const [msgCheckErr, setMsgCheckErr] = React.useState("");
  async function onCheckMsg() {
    setMsgChecked(""); setMsgCheckErr("");
    try { await dryRunMsg.mutateAsync(msg); setMsgChecked("검증 통과, 저장할 수 있습니다."); }
    catch (e) { setMsgCheckErr(e.message); }
  }
  function changeMsg(next) { setMsg(next); setMsgChecked(""); setMsgCheckErr(""); }
  async function onToggle() {
    // confirm 문구가 실제로 적용될 전환과 어긋나면 안 된다, 예전엔 클릭 시점의(낡을 수 있는) on으로
    // 먼저 문구("켤까요?"/"끌까요?")를 만들고, 사용자가 확인을 누른 뒤에야 서버 최신값을 다시 조회해
    // 뒤집었다. 그 사이(대화상자가 열려 있던 몇 초) 다른 관리자가 이미 상태를 바꿨다면, 대화상자는
    // "켤까요?"라고 말해 놓고 실제로는 끄는(반대) 동작이 조용히 실행될 수 있었다, 대화상자를 열기
    // '전에' 먼저 최신 상태를 확인해, 그 값 하나로 문구와 실제 전환을 항상 일치시킨다.
    const fresh = await q.refetch();
    // refetch()는 실패해도 throw하지 않고 { isError: true, data: undefined }로 조용히 해결된다 -
    // 이 확인을 건너뛰면(예전 코드) 네트워크 blip 때 fresh.data가 undefined가 돼 freshOn이 클로저의
    // 낡은 on으로 폴백하면서도 사용자에게는 "최신 상태 확인"이 성공한 것처럼 그대로 진행됐다.
    if (fresh.isError) { toast("현재 상태를 확인하지 못해 전환을 취소했습니다. 다시 시도하세요.", "error"); return; }
    const freshMm = fresh.data && fresh.data.settings && fresh.data.settings.maintenance_mode;
    const freshOn = freshMm ? (freshMm.value === true || freshMm.value === "true") : on;
    const ok = await confirm(freshOn ? "유지보수 모드를 비활성화할까요?" : "유지보수 모드를 활성화할까요? 일반 사용자의 쓰기가 차단됩니다. 운영자 이상은 계속 쓸 수 있습니다.",
      // 확정 버튼이 무엇을 하는지 말한다 (E7). 예전에는 이것도 "확인" 한 단어였다 —
      // **전 사용자의 쓰기를 막는 일**인데 빨간색 말고는 단서가 없었다.
      { danger: !freshOn, confirmLabel: freshOn ? "유지보수 모드 비활성화" : "유지보수 모드 활성화" });
    if (!ok) return;
    toggle.mutate(!freshOn);
  }
  const dirty = msg !== serverMsg;
  // 비활성 버튼의 '왜'를 스크린리더에도 연결한다 — 눈으로는 옆 문장이 보이지만, 연결이 없으면
  // 보조기기는 '비활성 버튼'까지만 읽고 이유는 영영 읽지 않는다.
  const lockedDescribedBy = canWrite ? undefined : "maint-locked-reason";

  return (
    <Box className="c-screen">
      {/* 유지보수 모드는 다른 admin이 지금 이 순간 켜고/끌 수 있는 상태다, Diagnostics처럼 자동
          폴링을 걸진 않되(쓰기가 잦은 화면은 아니다), 최소한 수동 새로고침은 준다. QueryClient가
          refetchOnWindowFocus:false, staleTime 30s라 아무 조작도 없이 놔두면 30초 넘게 낡은 값이
          '지금 상태'처럼 보일 수 있었다(main.jsx). */}
      <PageHeader area="운영" title="유지보수"
        actions={<>
          {updated ? (
            <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center", fontVariantNumeric: "tabular-nums" }}>
              {updated} 기준
            </Typography>
          ) : null}
          <Button size="sm" onClick={() => q.refetch()} disabled={q.isFetching}>{q.isFetching ? "새로고침 중…" : "새로고침"}</Button>
        </>} />
      {/* TanStack Query v5에서 isLoading은 '최초' 로딩만 true다, 캐시된 데이터가 이미 있는 상태에서
          (예: 이 화면의 '새로고침' 버튼을 눌렀다가) 재조회가 실패하면 isLoading은 false, isError만
          true가 된다. 그걸 그대로 ErrorState로 바꿔치기하면 방금까지 보이던 켜짐/꺼짐 토글과 공지
          textarea가 통째로 사라진다, 캐시된 데이터가 하나도 없을 때만 전체화면 ErrorState를 쓴다. */}
      {(q.isLoading || (q.isError && !q.data)) ? (
        q.isLoading ? <Card><Skeleton lines={2} /></Card> : <ErrorState error={q.error} onRetry={() => q.refetch()} />
      )
        : (
          <Box>
            {/* 새로고침이 실패했지만 이전 값이 남아 있는 경우, 화면을 지우지 않고 낡았다는 사실만 알린다. */}
            {q.isError ? (
              <Box sx={{ mb: 3 }} role="status">
                <Callout tone="warn">
                  최신 상태를 불러오지 못했습니다. 아래 값은 이전에 불러온 자료입니다.{" "}
                  <Link component="button" type="button" variant="body2" underline="hover" onClick={() => q.refetch()}>다시 시도</Link>
                </Callout>
              </Box>
            ) : null}
            {/* 유지보수 모드가 켜져 있으면 사용자 쓰기가 차단되는 위험 상태다, 페이지 상단에 눈에 띄는 배너로 분명히 한다
                (현재 상태 배지만으론 이 화면에 돌아온 관리자가 한눈에 알기 어려웠다). */}
            {on ? <Box sx={{ mb: 3 }} role="status"><Callout tone="warn">현재 유지보수 모드가 활성화되어 있습니다. 일반 사용자의 쓰기(티켓, 게시판, 문서, 팀 채팅, 놀이, AI 대화, 휴지통)가 차단되고 있습니다. 읽기와 운영자 이상의 쓰기는 그대로 됩니다. 점검이 끝나면 아래에서 비활성화해 주세요.</Callout></Box> : null}
            <Card sx={{ p: 3, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 3, flexWrap: "wrap", mb: 4 }}>
              <Box sx={{ minWidth: 0, flex: "1 1 20rem" }}>
                <Typography component="div" sx={{ display: "flex", alignItems: "center", gap: 1, fontWeight: FONT_WEIGHT.bold, mb: 1 }}>
                  현재 상태 <Badge value={on ? "maintenance" : "up"} />
                </Typography>
                <Note sx={{ mt: 0 }}>유지보수 모드를 활성화하면 일반 사용자의 쓰기(티켓, 게시판, 문서, 팀 채팅, 놀이, AI 대화, 휴지통)가 일시 차단됩니다. 읽기는 막지 않고, 운영자 이상은 계속 쓸 수 있습니다. 점검이 끝나면 다시 비활성화하세요.</Note>
                {/* 쓰기 권한이 없어 비활성인 이유 — 이 한 줄이 아래 두 버튼(모드 전환·공지 저장 계열)의
                    aria-describedby 대상이다. 버튼을 숨기는 대신 이유를 보여 준다. */}
                {!canWrite ? (
                  <Typography id="maint-locked-reason" variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                    유지보수 모드 전환은 {NO_WRITE_REASON}
                  </Typography>
                ) : null}
                {/* 점검 공지에는 '버전 기록'이 있는데 정작 더 위험한(앱 전체 쓰기를 막는) 유지보수 모드
                    토글 자체는 누가 언제 켜고 껐는지 볼 곳이 없었다, 백엔드가 config_versions에 이미
                    기록하므로 같은 SettingVersions UI를 maintenance_mode에도 붙인다. */}
                <Box sx={{ mt: 1 }}>
                  <Button variant="ghost" size="sm" onClick={() => setShowModeVersions(true)}>변경 기록(켜고 끈 이력)</Button>
                </Box>
              </Box>
              <Button variant={on ? "primary" : "danger"} disabled={!canWrite || toggle.isPending} onClick={onToggle}
                aria-describedby={lockedDescribedBy}>
                {toggle.isPending ? "전환 중…" : on ? "유지보수 모드 비활성화" : "유지보수 모드 활성화"}
              </Button>
            </Card>

            <DashSection title="점검 공지 (사용자에게 표시되는 안내)">
              <Card>
                <Note sx={{ mt: 0 }} id="maint-msg-desc">유지보수 모드가 활성화되어 있을 때 사용자가 보게 되는 안내 문구입니다.</Note>
                {/* 위쪽 유지보수 모드 토글 카드에만 '관리자, 시스템 관리자만' 안내가 붙어 있어, 이 섹션만
                    보는(특히 스크린리더) 사용자는 입력이 왜 잠겨 있는지 알 방법이 없었다, 여기도 남긴다. */}
                {!canWrite ? (
                  <Typography id="maint-msg-locked" variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                    점검 공지 수정은 {NO_WRITE_REASON}
                  </Typography>
                ) : null}
                {/* 공지는 사용자에게 보이는 산문이라 JSON 편집기용 monospace를 쓰지 않는다.
                    설명·유효성 힌트를 aria-describedby로 입력에 프로그래매틱하게 연결한다(이전엔 시각적으로만
                    인접해 있고 연결은 안 돼 있었다 — 이 필드가 켜지면 앱 전체 쓰기를 막는 공지라
                    스크린리더 사용자에게 특히 중요하다).
                    /maintenance는 operator, auditor(읽기 전용 역할)도 볼 수 있게 열려 있다(App.jsx
                    RequireRole), disabled는 그 방문자에게서 선택, 복사는 물론 탭/스크린리더 접근까지
                    막는다(네이티브 disabled 필드는 포커스 순서에서 빠진다). readOnly는 편집만 막고
                    선택, 복사, 포커스 이동은 그대로 허용한다. */}
                <TextField
                  multiline minRows={4} fullWidth value={msg}
                  error={canWrite && !msg.trim()}
                  onChange={(e) => { if (canWrite) changeMsg(e.target.value); }}
                  InputProps={{ readOnly: !canWrite }}
                  inputProps={{
                    "aria-label": "점검 공지",
                    "aria-describedby": "maint-msg-desc"
                      + (canWrite && !msg.trim() ? " maint-msg-help" : "")
                      + (!canWrite ? " maint-msg-locked" : ""),
                  }}
                />
                {canWrite && !msg.trim() ? (
                  <Typography id="maint-msg-help" variant="caption" color="error.main" sx={{ display: "block", mt: 0.5 }}>
                    공지 내용을 입력하세요. 빈 공지는 저장할 수 없습니다.
                  </Typography>
                ) : null}
                {msgChecked ? <Box sx={{ mt: 2 }} role="status"><Callout tone="success">{msgChecked}</Callout></Box> : null}
                {msgCheckErr ? (
                  <Typography role="alert" variant="body2" color="error.main" sx={{ mt: 2 }}>{msgCheckErr}</Typography>
                ) : null}
                {/* 폼 작업줄 — 앱 공통 우측 정렬. 쓰기 권한이 없어도 버튼을 지우지 않는다:
                    비활성 + 위의 이유 문구(aria-describedby)로 '있지만 지금은 못 누른다'를 그대로 보여 준다.
                    (예전엔 '미리 검증'만 canWrite일 때 렌더돼, 읽기 전용 역할에겐 그 기능의 존재 자체가 사라졌다.) */}
                <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1, flexWrap: "wrap", mt: 2 }}>
                  <Button disabled={!canWrite || dryRunMsg.isPending} onClick={onCheckMsg} aria-describedby={lockedDescribedBy}>
                    {dryRunMsg.isPending ? "검증 중…" : "미리 검증"}
                  </Button>
                  <Button variant="primary" disabled={!canWrite || !dirty || !msg.trim() || saveMsg.isPending} onClick={() => saveMsg.mutate(msg)}
                    aria-describedby={lockedDescribedBy}>
                    {saveMsg.isPending ? "저장 중…" : "공지 저장"}
                  </Button>
                  {dirty ? <Button disabled={saveMsg.isPending} onClick={() => changeMsg(serverMsg)}>되돌리기</Button> : null}
                  {/* 다른 설정과 달리 점검 공지는 설정 표에서 제외돼 버전 기록, 롤백이 닿지 않았다, 여기서 같은 UI를 재사용해 제공한다. */}
                  <Button variant="ghost" onClick={() => setShowVersions(true)}>버전 기록</Button>
                </Box>
              </Card>
            </DashSection>
          </Box>
        )}
      {showVersions ? (
        <SettingVersions settingKey="maintenance_message" label="점검 공지" canWrite={canWrite}
          onClose={() => setShowVersions(false)} onRolledBack={() => setShowVersions(false)} />
      ) : null}
      {showModeVersions ? (
        <SettingVersions settingKey="maintenance_mode" label="유지보수 모드" canWrite={canWrite}
          onClose={() => setShowModeVersions(false)} onRolledBack={() => setShowModeVersions(false)} />
      ) : null}
    </Box>
  );
}
