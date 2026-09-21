import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { fmtDateTime } from "../../lib/format.js";
import { useGuardedMutation } from "../../lib/useGuardedMutation.js";
import { useAuth } from "../../app/auth.jsx";
import { SettingRow } from "../../ui/adminKit.jsx";
import { SettingVersions } from "../settings/SettingVersions.jsx";
import { ActionFooter, Section, Card, Badge, Button, Callout, Modal, Skeleton, ErrorState, useConfirm, useToast } from "../../ui/kit.jsx";
import { KO_WORD_BREAK } from "../../ui/theme.js";
import { isWriteRole, NO_WRITE_REASON } from "./opsHelpers.js";
import { failureText } from "../../lib/failure.js";

/* 유지보수 — 유지보수 모드(maintenance_mode 설정)를 켜고 끈다. 켜면 일반 사용자의 내용 쓰기가 차단된다.
   여기 문구는 서버가 실제로 막는 범위와 일치해야 한다 — 예전에는 게이트가 AI 채팅 2곳에만 걸려
   있는데도 "티켓 생성, 변경 등"을 예로 들고 있었다(하필 안 막히던 것). 범위는
   tests/security/test_maintenance_coverage.py 의 GATED_PREFIXES 가 정본이다.
 * 사용자에게 보일 점검 공지(maintenance_message)도 여기서 확인 · 수정한다. 쓰기는 admin/system_admin.
 *
 * 이 화면은 operator/auditor(읽기 전용 역할)도 들어온다(App.jsx RequireRole). 그 역할에게 쓰기
 * 컨트롤을 **숨기지 않는다** — 보이되 비활성이고, 왜 비활성인지 옆에 글자로 남긴다. 숨기면
 * '이 앱엔 그런 기능이 없다'로 읽혀, 권한을 받으면 할 수 있는 일을 영영 모른 채로 지나간다.
 *
 * PA-RC-0017: `embedded`(SettingsShell.jsx의 '시스템 정책' 탭, 설정 표 바로 아래)일 땐 이
 * 화면 몫의 큰 PageHeader(h1) 대신 한 단계 아래 구획 제목(h2)을 그린다 — 탭 하나 안에
 * '설정' 표와 '유지보수' 판이 나란히 있는데 둘 다 h1이면 탭 안에 페이지가 두 개 겹친
 * 것처럼 읽힌다(PageHeader.jsx의 size="section" 과 같은 근거). 새로고침 단추 · 갱신 시각은
 * 그대로 필요해 구획 제목의 동작 자리에 둔다.
 *
 * ## 판 하나에 설정 줄 둘이다 (D-501)
 *
 * 모드와 공지는 각자 한 줄짜리 값이다. 예전에는 둘이 1.2 : 0.8 짝 판 둘이었고(D-457), 왼쪽 판은 「현재 상태」 한 줄 아래가
 * 비어 있었으며 오른쪽 판은 네 줄 높이 입력창이 늘 열려 있었다. 3줄 미만의 내용은 판이 아니라 줄이다 — 설정 한 줄
 * (`adminKit::SettingRow`)의 어휘 그대로 **이름 · 지금 값 · 그것이 무엇인지 · 바꾸는 동작**을 한 줄에 둔다. 공지는 지금
 * 문구를 그대로 보이고, 고치는 일은 「수정」이 여는 창에서 한다(미리 검증과 저장이 그 창의 발에 선다 — 설정 표의
 * `SettingEditor` 와 같은 발이다).
 *
 * 쓰기 셋(모드 전환 · 공지 저장 · 미리 검증)은 같은 요청이 끝나기 전에 두 번 나가지 않는다(`useGuardedMutation`).
 * 확인 대화를 연 사이 한 번 더 누르거나 저장을 연달아 눌러도 요청은 하나다. */
export function Maintenance({ embedded = false } = {}) {
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
  /* 공지 수정 창이 열려 있는가. 초안(`msg`)은 창을 열 때 서버 값에서 시작한다(`openEditor`). */
  const [editing, setEditing] = React.useState(false);
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

  const toggle = useGuardedMutation({
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
  });
  /* 전환 전에 최신 상태를 못 읽어 취소한 사실 — 전환 실패와 같은 자리(모드 줄 아래)에 남는다. 다시 누르면 걷힌다. */
  const [modeCheckFailure, setModeCheckFailure] = React.useState("");
  const [msgChecked, setMsgChecked] = React.useState("");
  const [msgCheckErr, setMsgCheckErr] = React.useState("");
  const saveMsg = useGuardedMutation({
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
      setEditing(false);
      toast("점검 공지를 저장했습니다.", "success");
    },
    // 실패는 미리 검증 실패와 같은 자리(창 안 입력 아래)에 남긴다 — 창을 닫지 않는 이유다(토스트는 걷었다:
    // 같은 문장이 두 곳에 서면 어느 쪽이 지금 상태인지 헷갈린다).
    onError: (e) => { setMsgCheckErr(e.message); },
  });
  // Settings.jsx의 다른 설정들은 '미리 검증'(dry-run)을 제공하는데 이 두 키(같은 PUT 엔드포인트)만
  // 여기 전용 화면이라 그 수단이 없었다 — 같은 백엔드 능력을 여기서도 노출한다.
  const dryRunMsg = useGuardedMutation({
    mutationFn: (val) => api("/api/admin/settings/maintenance_message/dry-run", { method: "POST", body: { value: val } }), });
  async function onCheckMsg() {
    setMsgChecked(""); setMsgCheckErr("");
    try { await dryRunMsg.mutateAsync(msg); setMsgChecked("검증을 통과했습니다. 저장할 수 있습니다."); }
    catch (e) { setMsgCheckErr(e.message); }
  }
  function changeMsg(next) { setMsg(next); setMsgChecked(""); setMsgCheckErr(""); }
  /* 창은 언제나 **지금 서버 값**에서 시작한다 — 지난번에 닫으며 버린 초안이 다시 살아나지 않게 한다. */
  function openEditor() {
    setMsg(serverMsg);
    setMsgChecked(""); setMsgCheckErr("");
    setEditing(true);
  }
  /* 창 닫기(취소 · Esc · 바깥 누르기)는 설정 표의 편집 창(`SettingEditor::requestClose`)과 같은 규칙이다 — 저장 요청이
     도는 동안은 닫지 않고(되돌릴 수단이 없는 요청이 닫힌 창 뒤에서 끝난다), 고친 초안이 있으면 한 번 묻는다. */
  async function requestCloseEditor() {
    if (saveMsg.isPending) return;
    if (msg !== serverMsg) {
      const ok = await confirm("수정한 내용이 저장되지 않았습니다. 닫을까요?", { danger: true, confirmLabel: "닫기" });
      if (!ok) return;
    }
    setEditing(false);
  }
  async function onToggle() {
    // confirm 문구가 실제로 적용될 전환과 어긋나면 안 된다, 예전엔 클릭 시점의(낡을 수 있는) on으로
    // 먼저 문구("켤까요?"/"끌까요?")를 만들고, 사용자가 확인을 누른 뒤에야 서버 최신값을 다시 조회해
    // 뒤집었다. 그 사이(대화상자가 열려 있던 몇 초) 다른 관리자가 이미 상태를 바꿨다면, 대화상자는
    // "켤까요?"라고 말해 놓고 실제로는 끄는(반대) 동작이 조용히 실행될 수 있었다, 대화상자를 열기
    // '전에' 먼저 최신 상태를 확인해, 그 값 하나로 문구와 실제 전환을 항상 일치시킨다.
    setModeCheckFailure("");
    const fresh = await q.refetch();
    // refetch()는 실패해도 throw하지 않고 { isError: true, data: undefined }로 조용히 해결된다 -
    // 이 확인을 건너뛰면(예전 코드) 네트워크 blip 때 fresh.data가 undefined가 돼 freshOn이 클로저의
    // 낡은 on으로 폴백하면서도 사용자에게는 "최신 상태 확인"이 성공한 것처럼 그대로 진행됐다.
    if (fresh.isError) { setModeCheckFailure("현재 상태를 확인하지 못해 전환을 취소했습니다. 다시 시도하세요."); return; }
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
  const modeFailure = modeCheckFailure || failureText([toggle, null]);
  // 비활성 버튼의 '왜'를 스크린리더에도 연결한다 — 눈으로는 판 아래 문장이 보이지만, 연결이 없으면
  // 보조기기는 '비활성 버튼'까지만 읽고 이유는 영영 읽지 않는다. 판이 하나라 이유 문장도 하나다.
  const lockedDescribedBy = canWrite ? undefined : "maint-locked-reason";

  /* 옛 주소 `/maintenance` 는 `/settings?tab=policy` 로 보내는 리다이렉트다 — 이 화면은 언제나
     껍데기 안이라 페이지 머리(h1)도 `.c-screen` 도 스스로 그리지 않는다(둘 다 껍데기가 그린다.
     예전에는 `.c-screen` 을 한 번 더 감싸 바깥 여백이 두 번 붙었다). */
  // `SectionTitle` 은 제목과 동작을 양끝으로 벌리는 flex 다 — 캡션과 단추가 각각 자식이면
  // 캡션이 줄 한가운데로 떠서 어느 쪽에도 안 붙는다(실측). 하나로 묶어 오른쪽에 세운다.
  const refreshActions = (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
      {updated ? (
        <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center", fontVariantNumeric: "tabular-nums" }}>
          {updated} 기준
        </Typography>
      ) : null}
      <Button size="sm" onClick={() => q.refetch()} disabled={q.isFetching} loading={q.isFetching}>새로고침</Button>
    </Box>
  );
  /* 설정 줄의 동작 칸 — 이력을 여는 보조가 앞, 그 줄의 일이 뒤(오른쪽 끝)다. */
  const rowActions = (children) => (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", justifyContent: "flex-end" }}>{children}</Box>
  );
  /* 공지 수정 창의 발 — 설정 표의 편집 창(`SettingEditor`)과 같은 발이다. 값을 확정하지 않는 미리 검증은 왼쪽 칸이고,
     오른쪽은 「취소 → 공지 저장」이다(RULES §8 · 조합 계약 C-4). 되돌리기는 두지 않는다 — 창을 닫으면 초안이 버려지고,
     다시 열면 지금 서버 값에서 시작한다. */
  const editorFooter = (
    <ActionFooter
      placement="modal"
      extra={(
        <Button disabled={dryRunMsg.isPending} loading={dryRunMsg.isPending} onClick={onCheckMsg}>미리 검증</Button>
      )}
    >
      <Button onClick={requestCloseEditor} disabled={saveMsg.isPending}>취소</Button>
      <Button variant="primary" disabled={!dirty || !msg.trim() || saveMsg.isPending} loading={saveMsg.isPending} onClick={() => saveMsg.mutate(msg)}>
        공지 저장
      </Button>
    </ActionFooter>
  );
  return (
    <Section titleAs="h2" title="유지보수" action={refreshActions}>
      {/* TanStack Query v5에서 isLoading은 '최초' 로딩만 true다, 캐시된 데이터가 이미 있는 상태에서
          (예: 이 화면의 '새로고침' 버튼을 눌렀다가) 재조회가 실패하면 isLoading은 false, isError만
          true가 된다. 그걸 그대로 ErrorState로 바꿔치기하면 방금까지 보이던 켜짐/꺼짐 토글과 공지
          문구가 통째로 사라진다, 캐시된 데이터가 하나도 없을 때만 전체화면 ErrorState를 쓴다. */}
      {(q.isLoading || (q.isError && !q.data)) ? (
        q.isLoading ? <Card><Skeleton lines={2} /></Card> : <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          {/* 새로고침이 실패했지만 이전 값이 남아 있는 경우, 화면을 지우지 않고 낡았다는 사실만 알린다. */}
          {q.isError ? (
            <Box sx={{ mb: 3 }}>
              {/* 다시 부르는 동작은 본문 속 글자 링크가 아니라 상자의 동작 칸에 선다(메시지 박스 구조). */}
              <Callout tone="warn" action={<Button size="sm" onClick={() => q.refetch()}>다시 시도</Button>}>
                최신 상태를 불러오지 못했습니다. 아래 값은 이전에 불러온 자료입니다.
              </Callout>
            </Box>
          ) : null}
          {/* 유지보수 모드가 켜져 있으면 사용자 쓰기가 차단되는 위험 상태다, 페이지 상단에 눈에 띄는 배너로 분명히 한다
              (현재 상태 배지만으론 이 화면에 돌아온 관리자가 한눈에 알기 어려웠다). */}
          {on ? <Box sx={{ mb: 3 }} role="status"><Callout tone="warn">현재 유지보수 모드가 활성화되어 있습니다. 일반 사용자의 쓰기(티켓, 게시판, 문서, 팀 채팅, 놀이, AI 대화, 휴지통)가 차단되고 있습니다. 읽기와 운영자 이상의 쓰기는 그대로 됩니다. 점검이 끝나면 아래에서 비활성화해 주세요.</Callout></Box> : null}
          <Card>
            <SettingRow
              label="유지보수 모드"
              value={<Badge value={on ? "maintenance" : "up"} />}
              description="활성화하면 일반 사용자의 쓰기(티켓, 게시판, 문서, 팀 채팅, 놀이, AI 대화, 휴지통)가 차단됩니다. 읽기와 운영자 이상의 쓰기는 그대로 됩니다."
              action={rowActions(
                <>
                  {/* 점검 공지에는 '버전 기록'이 있는데 정작 더 위험한(앱 전체 쓰기를 막는) 유지보수 모드
                      토글 자체는 누가 언제 켜고 껐는지 볼 곳이 없었다, 백엔드가 config_versions에 이미
                      기록하므로 같은 SettingVersions UI를 maintenance_mode에도 붙인다. */}
                  <Button onClick={() => setShowModeVersions(true)}>변경 기록</Button>
                  <Button variant={on ? "primary" : "danger"} disabled={!canWrite || toggle.isPending} loading={toggle.isPending} onClick={onToggle}
                    aria-describedby={lockedDescribedBy}>
                    {on ? "유지보수 모드 비활성화" : "유지보수 모드 활성화"}
                  </Button>
                </>,
              )}
            >
              {modeFailure ? <Callout tone="danger" compact sx={{ mt: 1 }}>{modeFailure}</Callout> : null}
            </SettingRow>
            <SettingRow
              last
              label="점검 공지"
              /* 공지는 사용자에게 보이는 산문이다 — 지금 문구를 그대로 보인다(줄바꿈 포함). 비어 있으면 비었다고 말한다. */
              value={serverMsg
                ? <Box component="span" sx={{ whiteSpace: "pre-line", ...KO_WORD_BREAK }}>{serverMsg}</Box>
                : "아직 적은 공지가 없습니다."}
              tone={serverMsg ? undefined : "muted"}
              description="유지보수 모드가 활성화되어 있을 때 사용자가 보게 되는 안내 문구입니다."
              action={rowActions(
                <>
                  {/* 다른 설정과 달리 점검 공지는 설정 표에서 제외돼 버전 기록, 롤백이 닿지 않았다, 여기서 같은 UI를 재사용해 제공한다. */}
                  <Button onClick={() => setShowVersions(true)}>버전 기록</Button>
                  {/* 쓰기 권한이 없어도 버튼을 지우지 않는다: 비활성 + 아래 이유 문구(aria-describedby)로 '있지만 지금은 못
                      누른다'를 그대로 보여 준다. 이름은 「점검 공지 수정」이다 — 같은 탭의 설정 표 행마다 「수정」이 선다. */}
                  <Button onClick={openEditor} disabled={!canWrite} aria-label="점검 공지 수정" aria-describedby={lockedDescribedBy}>수정</Button>
                </>,
              )}
            />
            {/* 쓰기 권한이 없어 비활성인 이유 — 판 하나에 한 줄이고, 두 줄의 쓰기 단추가 모두 이 줄을 가리킨다. */}
            {!canWrite ? (
              <Typography id="maint-locked-reason" variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                유지보수 모드와 점검 공지는 {NO_WRITE_REASON}
              </Typography>
            ) : null}
          </Card>
        </>
      )}
      {editing && canWrite ? (
        <Modal open onClose={requestCloseEditor} title="점검 공지 수정" footer={editorFooter}>
          <Typography variant="body2" color="text.secondary" id="maint-msg-desc" sx={{ mb: 1.5, ...KO_WORD_BREAK }}>
            유지보수 모드가 활성화되어 있을 때 사용자가 보게 되는 안내 문구입니다.
          </Typography>
          {/* 공지는 사용자에게 보이는 산문이라 JSON 편집기용 monospace를 쓰지 않는다.
              설명 · 유효성 힌트를 aria-describedby로 입력에 프로그래매틱하게 연결한다(이전엔 시각적으로만
              인접해 있고 연결은 안 돼 있었다 — 이 필드가 켜지면 앱 전체 쓰기를 막는 공지라
              스크린리더 사용자에게 특히 중요하다). */}
          <TextField
            multiline minRows={4} fullWidth value={msg} autoFocus
            error={!msg.trim()}
            onChange={(e) => changeMsg(e.target.value)}
            disabled={saveMsg.isPending}
            inputProps={{
              "aria-label": "점검 공지",
              "aria-describedby": "maint-msg-desc" + (!msg.trim() ? " maint-msg-help" : ""),
            }}
          />
          {!msg.trim() ? (
            <Box id="maint-msg-help" sx={{ mt: 0.5 }}>
              <Callout tone="danger" compact>공지 내용을 입력하세요. 빈 공지는 저장할 수 없습니다.</Callout>
            </Box>
          ) : null}
          {msgChecked ? <Box sx={{ mt: 2 }} role="status"><Callout tone="success">{msgChecked}</Callout></Box> : null}
          {msgCheckErr ? (
            <Callout tone="danger" compact sx={{ mt: 2 }}>{msgCheckErr}</Callout>
          ) : null}
        </Modal>
      ) : null}
      {showVersions ? (
        <SettingVersions settingKey="maintenance_message" label="점검 공지" canWrite={canWrite}
          onClose={() => setShowVersions(false)} onRolledBack={() => setShowVersions(false)} />
      ) : null}
      {showModeVersions ? (
        <SettingVersions settingKey="maintenance_mode" label="유지보수 모드" canWrite={canWrite}
          onClose={() => setShowModeVersions(false)} onRolledBack={() => setShowModeVersions(false)} />
      ) : null}
    </Section>
  );
}
