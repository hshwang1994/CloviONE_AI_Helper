import React, { useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import TextField from "@mui/material/TextField";
import { UserPicker } from "../ui/UserPicker.jsx";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { expireSession } from "../lib/sessionRedirect.js";
import { fmtDateTime } from "../lib/format.js";
import { maxLengthFor } from "../lib/fieldLimits.js";
import {
  ListEmptyState,
  PageHeader, Card, Badge, Button, DataTable, DetailGrid, DetailRow, Modal, Skeleton,
  Section, SectionTitle, EmptyState, ErrorState, Callout, useConfirm, useToast,
  ActionFooter,
  FieldLabel,
} from "../ui/kit.jsx";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { useRowSelection, selectionColumn } from "../ui/bulkSelect.jsx";
import { FilterBar } from "../ui/FilterBar.jsx";
import { SearchBox } from "../ui/filters.jsx";
import { BASELINE_TRACKS, CONTENT_PAIR_CONTAINER, contentPairTracks } from "../ui/density.js";
import { invalidateTicketViews } from "./ticket-views.js";
import { DateCell } from "../ui/cells.jsx";
import { useInfiniteList } from "../lib/useInfiniteList.js";

/* 오프보딩 (PLAN Phase 6 — 관리자 백로그 최우선 항목)
 *
 * 계획서: *"퇴사자 보유 티켓 재배정 — ticket_cache+RBAC가 둘 다 필요한 유일한 항목이자 현재
 * 실제 운영 공백"*. ticket_cache+RBAC 두 조각이 다 들어와 여기서 잇는다.
 *
 * WF1 R4 — 예전엔 제목·내비가 "온보딩, 오프보딩"이었지만 이 화면은 퇴사자 재배정 마법사뿐이다
 * (읽기 전용 계정 준비도 체크리스트—부서/직책/첫 로그인—는 아래 미리보기에
 * 남지만, app/offboarding/service.py::_onboarding_checklist가 명시하듯 "이 계정이 일할
 * 준비가 됐는가"를 뒤집어 오프보딩 점검에도 쓰는 것뿐, 신규 입사자를 만드는 능동적 온보딩
 * 워크플로가 아니다). 실제 신규 계정 생성은 "사용자" 화면의 "사용자 추가"다. 없는 기능을
 * 약속하던 제목을 정정한다.
 *
 * **왜 DataScreen이 아닌가.** 이 화면은 목록이 아니라 마법사다: 사람을 고르고 → 그 사람이 든
 * 티켓을 **미리 보고** → 누구에게 옮길지 정한 뒤 → 실행하고 → 부분 실패를 확인한다. registry.js
 * 계약(엔드포인트 하나 + 열 + 액션)으로는 '미리 보여 주고 확인받는' 단계를 표현할 수 없다.
 * 대신 실행 이력은 같은 화면 아래에 표로 두고, 되돌리기를 그 자리에서 누를 수 있게 한다 —
 * 되돌릴 방법이 화면 안에 없으면 아무도 이 버튼을 못 쓴다.
 */

const STEP_HELP = [
  "1. 대상 고르기: 퇴사(또는 휴직)할 사람을 검색해 고릅니다.",
  "2. 미리 보기: 그 사람이 지금 담당 중인 티켓과 계정 상태를 확인합니다.",
  "3. 실행: 옮길 티켓과 후임을 정하고 실행합니다. 결과는 되돌릴 수 있습니다.",
];

/* `running` 은 **끝까지 가지 못한 실행**이다(C3). 실행은 요청 하나 안에서 끝나므로 목록에
   이 값이 보인다면 계정 처리 중에 무언가 터진 것이다 — 티켓은 이미 옮겨졌을 수 있으니
   "완료" 옆에 조용히 두면 안 된다. 라벨과 색이 둘 다 그 사실을 말해야 한다. */
const RUN_STATUS_KO = {
  running: "미완료", completed: "완료", partial: "부분 실패",
  undone: "되돌림", undo_partial: "되돌리기 부분 실패",
};
const MOVE_STATUS_KO = {
  // `pending` = 소스를 부르기 직전에 남긴 표시. 바뀌었는지 알 수 없는 유일한 상태다.
  pending: "확인 필요", moved: "옮김", skipped: "변경 없음", failed: "실패",
  reverted: "되돌림", revert_failed: "되돌리기 실패",
};
const MOVE_STATUS_KIND = {
  pending: "warn", moved: "ok", skipped: "neutral", failed: "danger",
  reverted: "ok", revert_failed: "danger",
};

export function Offboarding() {
  const [q, setQ] = useState("");
  const [targetId, setTargetId] = useState(null);
  const qc = useQueryClient();
  const toast = useToast();

  // 검색은 사용자 목록 API를 그대로 쓴다(관리 범위가 이미 걸려 있다 — 부서 관리자는 자기
  // 서브트리만 검색된다). 별도 '오프보딩 대상 목록' 엔드포인트를 새로 만들지 않는다.
  const searchQ = useQuery({
    queryKey: ["offboarding-search", q],
    queryFn: () => api("/api/admin/users?page_size=20" + (q ? "&q=" + encodeURIComponent(q) : "")),
    enabled: !targetId,
    retry: false,
  });
  const previewQ = useQuery({
    queryKey: ["offboarding-preview", targetId],
    queryFn: () => api("/api/admin/offboarding/preview/" + targetId),
    enabled: !!targetId,
    retry: false,
  });

  return (
    <div className="c-screen">
      {/* PA-RC-0022: 상시 안내였던 것을 PageHeader의 제목 옆 도움말 토글로 옮긴다 — 문구는
          한 글자도 안 바꿨다, 기본 접힘만 바뀐다. */}
      <PageHeader area="사용자와 권한" title="오프보딩"
        actions={targetId ? <Button onClick={() => setTargetId(null)}>다른 사람 고르기</Button> : null}
        help={<>
          <Box component="p" sx={{ m: 0 }}>
            퇴사나 부서 이동 때 <strong>보유 티켓을 후임에게 옮기고</strong> 계정을 비활성화하거나 보관합니다.
            실행 전에 무엇이 바뀌는지 먼저 보여 주고, 실행한 뒤에도 <strong>되돌릴 수 있습니다</strong>.
          </Box>
          {STEP_HELP.map((line) => (
            <Box component="p" key={line} sx={{ m: 0, mt: 0.75 }}>{line}</Box>
          ))}
        </>} />

      {!targetId ? (
        <TargetPicker q={q} setQ={setQ} query={searchQ} onPick={setTargetId} />
      ) : previewQ.isLoading ? (
        <Card><Skeleton lines={6} /></Card>
      ) : previewQ.isError ? (
        <ErrorState layout="region" error={previewQ.error} onRetry={() => previewQ.refetch()} />
      ) : (
        <OffboardPlan
          preview={previewQ.data}
          onDone={() => {
            qc.invalidateQueries({ queryKey: ["offboarding-runs"] });
            qc.invalidateQueries({ queryKey: ["offboarding-preview", targetId] });
            qc.invalidateQueries({ queryKey: ["users"] });
            // 실행은 보유 티켓의 담당자를 후임(또는 미할당)으로 바꾼다 — 내 티켓·팀 티켓·
            // 스프린트·홈·월간 리포트가 이미 그 티켓을 캐시해 두고 있었다면(오프보딩 전에
            // 열어 본 탭 등) 이 화면만 새로고침되고 나머지는 옛 담당자를 그대로 보여준다.
            // 어떤 키가 티켓을 그리는지는 ticket-views.js 한 곳이 안다.
            invalidateTicketViews(qc, { refetchType: "all" });
          }}
          toast={toast}
        />
      )}

      <RunHistory />
    </div>
  );
}

/* 1단계 — 대상 고르기. */
function TargetPicker({ q, setQ, query, onPick }) {
  const items = (query.data && query.data.items) || [];
  const total = query.data && query.data.total;
  const columns = [
    { key: "display_name", label: "이름", type: "name" },
    // PA-RC-0029/0036: 사람을 고르는 화면인데 이메일이 식별자 대접을 못 받고 있었다.
    { key: "email", label: "이메일", identifier: true },
    { key: "department", label: "부서", type: "enum" },
    { key: "title", label: "직책", type: "enum" },
    { key: "active", label: "상태", type: "status", render: (r) => (
      <Box sx={{ display: "inline-flex", gap: 0.75, flexWrap: "wrap" }}>
        <Badge value={r.active ? "active" : "disabled"} />
        {r.archived_at ? <Badge value="보관됨" kind="neutral" /> : null}
      </Box>
    ) },
  ];
  return (
    <>
      {/* 탐색 줄은 판이 아니다 — 사용자 목록 · 티켓 목록과 같은 필터 바다. 예전에는 검색창 하나가 전폭 흰 판을
          차지했고(글자마다 질의가 나가는 맨 TextField), 아래 목록 판과 표면이 둘이었다. 검색어는 조건이라 칩을 갖고,
          그 조건의 결과 수는 같은 면 안 조건 줄이 말한다(조합 계약 C-1). */}
      <FilterBar
        search={<SearchBox value={q} onSearch={setQ} placeholder="이메일 또는 이름으로 검색" ariaLabel="오프보딩 대상 검색" />}
        conditions={{
          chips: q ? [{ key: "q", label: `검색: ${q}`, onDelete: () => setQ("") }] : [],
          total: query.data ? (total != null ? total : items.length) : null,
          unit: "명",
        }}
      />
      {query.isError ? (
        <ErrorState layout="region" error={query.error} onRetry={() => query.refetch()} />
      ) : (
        /* 목록 판 — 불러오는 중 · 빈 목록 · 행 · 발이 한 판 안이다(조합 계약 C-3). */
        <DataTable
          placement="surface"
          loading={query.isLoading}
          columns={columns} rows={items} rowKey={(r) => r.id} onRow={(r) => onPick(r.id)}
          emptyState={(
            /* 조건이 없는데 조건 탓을 하지 않는다 (C1 · W5). 예전에는 검색어가 비어 있어도
               언제나 「조건에 해당하는 사용자가 없습니다」라고 말했다 — 신규 설치에서 이 문장은
               있지도 않은 조건을 찾아 헤매게 한다. */
            <ListEmptyState
              filtered={!!String(q || "").trim()}
              onClear={() => setQ("")}
              clearLabel="검색어 지우기"
              filteredTitle="검색 조건에 맞는 사용자가 없습니다."
              filteredHelp="검색어를 지우거나 다른 이름으로 검색하세요."
              art="search"
              title="대상 사용자가 없습니다."
              help="퇴사 처리 대상이 될 계정이 아직 없습니다."
            />
          )}
          /* UB-40: 이 화면은 "그 사람을 찾아 실행"이 목적인데, 목록이 사용자 21명(현재는
             더 늘었을 수 있다)부터 page_size=20으로 조용히 잘렸다 — 총건수도 잘림 경고도
             없어 찾는 사람이 20번째 밖에 있으면 검색창을 쓰라는 단서조차 없었다.
             Search.jsx의 ResultGroup과 같은 관용을 재사용한다. 이 문장이 목록 판 발의 문장이다. */
          note={total != null && total > items.length ? `전체 ${total}명 중 ${items.length}명만 표시합니다. 검색어로 범위를 좁히세요.` : undefined}
        />
      )}
    </>
  );
}

/* 2·3단계 — 미리 보기 + 실행. */
function OffboardPlan({ preview, onDone, toast }) {
  const user = preview.user;
  const tickets = preview.tickets || [];
  const selection = useRowSelection();
  const [successor, setSuccessor] = useState("");
  const [deactivate, setDeactivate] = useState(true);
  const [archive, setArchive] = useState(false);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  /* 실행 요청이 실패한 사실 — 실행 단추 곁에 남는다. 다시 실행하면 걷힌다. */
  const [runFailure, setRunFailure] = useState("");
  const confirm = useConfirm();
  const noteMaxLength = maxLengthFor("offboarding", "run", "note");

  // 처음 열 때 모든 티켓을 선택해 둔다 — 전형적인 의도는 '전부 옮긴다'이고, 빼야 할 건만
  // 체크를 푸는 편이 하나씩 켜는 것보다 실수가 적다. 서버는 여전히 보낸 목록만 처리한다.
  const ids = tickets.map((t) => t.id);
  // 이 이펙트는 previewQ.data '객체' 자체가 아니라 그 안의 '티켓 id 집합'에만 반응해야 한다.
  // 예전엔 [preview]에 매여 있어, 티켓 집합은 그대로인데 다른 값(예: 마감일만
  // 바뀜)이 달라진 새 응답이 배경 재조회(재연결 등, staleTime 경과 후)로 와도 매번 재실행돼
  // 사람이 방금 뺀 체크를 조용히 되살렸다 — 그 상태로 실행하면 일부러 제외한 티켓까지
  // 함께 옮겨진다. 실제로 티켓 구성이 달라졌을 때만(다른 사람으로 전환은 이 컴포넌트 자체가
  // 다시 마운트되므로 별도 처리가 필요 없다) 다시 전체 선택한다.
  const idsKey = ids.join(",");
  const prevIdsKeyRef = React.useRef(null);
  React.useEffect(() => {
    if (prevIdsKeyRef.current === idsKey) return;
    prevIdsKeyRef.current = idsKey;
    selection.setAll(ids, true);
  }, [idsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const chosen = ids.filter((id) => selection.selected.has(id));
  const columns = [
    selectionColumn(selection, ids),
    { key: "tid", label: "티켓", type: "code", render: (t) => t.key || "-" },
    { key: "title", label: "제목", type: "title" },
    { key: "status", label: "상태", type: "status", render: (t) => <Badge value={t.status} /> },
    { key: "due", label: "마감", type: "date", render: (t) => t.due || "-" },
    { key: "assignee_names", label: "현재 담당자", type: "name", render: (t) => (t.assignee_names || []).join(", ") || "-" },
  ];

  /* «실행하면 무슨 일이 일어나는가» — 확인 대화와 폼 옆 레일이 **같은 문장**을 쓴다. 레일은
     고르는 동안 미리 보여 주고, 대화는 누르기 직전에 한 번 더 보여 준다. */
  const who = successor
    ? (preview.successor_candidates.find((c) => c.user_id === successor) || {}).display_name
    : null;
  const planLines = [
    `${user.display_name}(${user.email}) 오프보딩을 실행합니다.`,
    chosen.length
      ? `티켓 ${chosen.length}건을 ${who ? who + "에게 옮깁니다" : "미할당으로 되돌립니다"}.`
      : "옮길 티켓은 없습니다.",
    deactivate ? "계정을 비활성화합니다(로그인 불가)." : "",
    archive ? "계정을 보관합니다(목록에서 감춤)." : "",
    "실행 후 아래 ‘실행 이력’에서 되돌릴 수 있습니다.",
  ].filter(Boolean);

  async function run() {
    const message = planLines.join("\n");
    if (!(await confirm(message, { danger: true, title: "오프보딩 실행", confirmLabel: "실행" }))) return;

    setBusy(true); setNoteError(""); setRunFailure("");
    try {
      const res = await api("/api/admin/offboarding/run/" + user.id, {
        method: "POST",
        body: {
          ticket_page_ids: chosen,
          successor_user_id: successor || null,
          deactivate, archive, note: note || null,
        },
      });
      setResult(res);
      onDone();
      const run = res.run;
      // 부분 실패를 성공 토스트로 덮지 않는다 — 실행 결과 판(`RunResult`)의 오류 상자가 그 숫자를 말한다.
      if (!run.ticket_failed) toast("오프보딩을 실행했습니다.", "success");
    } catch (e) {
      if (e && e.status === 401) { expireSession(); return; }
      // PA-RC-0014: 이 화면은 FormModal을 안 쓰는 손수 제작 폼이라 details[].loc 연결을
      // 직접 한다 — 메모(note)가 서버 상한(1000자)을 넘으면 그 칸에도 aria-invalid를 건다.
      const details = e && e.body && e.body.error && Array.isArray(e.body.error.details) ? e.body.error.details : null;
      const noteDetail = details && details.find((d) => Array.isArray(d.loc) && d.loc[d.loc.length - 1] === "note");
      if (noteDetail) setNoteError(e.message || "");
      else setRunFailure(e.message);
    } finally { setBusy(false); }
  }

  if (result) return <RunResult result={result} />;

  return (
    <>
      {/* 대상 요약은 판이 아니라 구획이다 — 제목(사람) 아래 속성 넷이 캔버스 위에 선다. */}
      <Section titleAs="h2" title={`${user.display_name}, ${user.email}`} rule>
        <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", xxl: "repeat(4, minmax(0,1fr))" } }}>
          {(preview.onboarding || []).map((check) => (
            <Box key={check.key} sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
              <Badge value={check.ok ? "완료" : "미완료"} kind={check.ok ? "ok" : "warn"} />
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2">{check.label}</Typography>
                <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>{check.value}</Typography>
              </Box>
            </Box>
          ))}
        </Box>
      </Section>

      {preview.open_run ? (
        <Box sx={{ mb: 2.5 }}>
          <Callout tone="warn">이 사람에 대해 아직 되돌리지 않은 오프보딩 실행이 있습니다({fmtDateTime(preview.open_run.created_at)}). 아래 ‘실행 이력’에서 먼저 확인하세요.</Callout>
        </Box>
      ) : null}
      {preview.tickets_error ? (
        <Box sx={{ mb: 2.5 }}>
          <Callout tone="danger">보유 티켓을 불러오지 못했습니다(원인: {preview.tickets_error}). 이 상태로 실행하면 옮기지 못한 티켓이 그대로 남습니다.</Callout>
        </Box>
      ) : null}

      <Section titleAs="h2" title={`보유 티켓 ${tickets.length}건, 선택 ${chosen.length}건`}>
        {tickets.length ? (
          <DataTable placement="surface" columns={columns} rows={tickets} rowKey={(t) => t.id} />
        ) : (
          <EmptyState size="compact" title="옮길 티켓이 없습니다." help="계정 처리만 진행합니다." />
        )}
      </Section>

      {/* 폼 판 + 보조 레일 — `/new-ticket` 과 같은 모양(D-458). 레일은 «실행하면 무슨 일이
          일어나는가» 를 고르는 동안 보여 준다(확인 대화와 같은 문장). 2열은 본문이 받은 폭이 정한다(`contentPairTracks`). */}
      <Box sx={CONTENT_PAIR_CONTAINER}>
      <Box sx={contentPairTracks(BASELINE_TRACKS.two)}>
      <Card>
        <Box sx={{ display: "grid", gap: 2.5 }}>
          {/* 후임은 사람 고르개 정본이다(핸드오프 계획 B-7) — 검색 · 아바타 · 한 줄 32. 예전에는 후보 전원을
              펼치는 셀렉트라 사람이 많으면 스크롤로 찾아야 했다. 「후임 없음」은 비운 값의 낱말이다. */}
          <UserPicker
            layout="form"
            label="후임(티켓을 받을 사람)"
            candidates={preview.successor_candidates || []}
            value={successor}
            onChange={setSuccessor}
            allLabel="(후임 없음, 미할당으로 되돌림)"
            describe={(c) => [c.email, c.department].filter(Boolean).join(", ")}
            helperText="비워 두면 선택한 티켓이 미할당으로 돌아가고, ‘미할당 티켓’ 화면에서 다시 배정할 수 있습니다."
          />
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor="offboarding-note">메모(선택)</FieldLabel>
            <TextField id="offboarding-note"
              size="small" fullWidth value={note}
              onChange={(e) => { setNote(e.target.value); if (noteError) setNoteError(""); }}
              error={!!noteError}
              helperText={noteError || "오프보딩 사유를 적어 두면 실행 이력에서 바로 볼 수 있습니다."}
              inputProps={noteMaxLength ? { maxLength: noteMaxLength } : undefined}
            />
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mt: 1.5 }}>
          <FormControlLabel control={<Checkbox size="small" checked={deactivate} onChange={(e) => setDeactivate(e.target.checked)} />}
            label={<Typography variant="body2">계정 비활성화(로그인 불가)</Typography>} />
          <FormControlLabel control={<Checkbox size="small" checked={archive} onChange={(e) => setArchive(e.target.checked)} />}
            label={<Typography variant="body2">계정 보관(목록에서 감춤)</Typography>} />
        </Box>
        {runFailure ? <Callout tone="danger" compact>{runFailure}</Callout> : null}
        {/* 실행은 판 발이다(`ActionFooter card` — 함몰면 + 위 실선, 오른쪽 끝 · 조합 계약 C-4). 예전에는 손으로 짠 오른쪽
            정렬 줄이 판 여백 안에 떠 있었다. 되돌릴 수 있는 일이지만 계정을 끄는 일이라 파괴 단추이고 확인을 받는다. */}
        <ActionFooter placement="card">
          <Button variant="danger" disabled={busy} loading={busy} onClick={run}>
            오프보딩 실행
          </Button>
        </ActionFooter>
      </Card>
      <Card component="aside">
        <SectionTitle component="h2" title="실행하면 일어나는 일" />
        <Box component="ol" sx={{ m: 0, pl: 2.5, display: "grid", gap: 0.75 }}>
          {planLines.map((line) => (
            <Typography key={line} component="li" variant="body2" sx={KO_WORD_BREAK}>{line}</Typography>
          ))}
        </Box>
      </Card>
      </Box>
      </Box>
    </>
  );
}

/* 실행 결과 — 부분 실패를 숨기지 않는다. */
function RunResult({ result }) {
  const run = result.run;
  const moves = result.moves || [];
  return (
    <Section titleAs="h2" title="실행 결과">
      {/* 실패한 티켓이 남았다는 것은 주의가 아니라 오류다 - 그 티켓은 아직 그 사람 앞에
          있다. 실패가 없으면 이 줄은 실행 결과 요약일 뿐이므로 조용한 안내다. */}
      {/* 일부가 실패했으면 그 사실이 이 상자의 제목이다 — 예전에는 같은 문장이 사라지는 토스트로 따로 떴다. */}
      <Callout
        tone={run.ticket_failed ? "danger" : "info"}
        title={run.ticket_failed ? `티켓 ${run.ticket_moved}건을 옮기고 ${run.ticket_failed}건은 실패했습니다.` : undefined}
      >
        티켓 {run.ticket_total}건 중 <strong>{run.ticket_moved}건 이동</strong>
        {run.ticket_failed ? <>, <strong>{run.ticket_failed}건 실패</strong></> : null}.
        {run.deactivated ? " 계정을 비활성화했습니다." : ""}
        {run.archived ? " 계정을 보관했습니다." : ""}
        {" "}아래 ‘실행 이력’에서 되돌릴 수 있습니다.
      </Callout>
      {moves.length ? (
        <Box sx={{ mt: 2 }}>
          <DataTable placement="surface" columns={MOVE_COLUMNS} rows={moves} rowKey={(m) => m.id} />
        </Box>
      ) : null}
    </Section>
  );
}

const MOVE_COLUMNS = [
  { key: "tid", label: "티켓", type: "code", render: (m) => m.key || m.ticket_page_id },
  { key: "title", label: "제목", type: "title", render: (m) => m.title || "-" },
  { key: "status", label: "결과", render: (m) => <Badge value={MOVE_STATUS_KO[m.status] || m.status} kind={MOVE_STATUS_KIND[m.status]} /> },
  /* 오류 원문이라 `text` 다 — 타입이 없으면 말줄임이 안 걸려 여러 줄로 접힌다. */
  { key: "error", label: "사유", type: "text", render: (m) => m.error || "-" },
];

const RUN_PAGE_SIZE = 20;

/* 실행 이력 + 되돌리기. 되돌릴 방법이 화면 안에 없으면 아무도 실행 버튼을 못 쓴다.
 *
 * 이 표는 감사 이력이라 지우지 않고 계속 쌓인다(휴지통처럼 보관기간이 지나 스스로 줄지
 * 않는다). 서버가 자른 뒤 더 받을 길을 안 주면 21번째 실행부터는 화면에서 조용히 사라져
 * 아무도 다시 못 찾는다 — 굴리면 이어 받는다(내 활동 피드와 같은 방식). */
function RunHistory() {
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);
  /* 되돌리기 결과 중 남아야 하는 것. 실패는 열린 상세 안(`undoFailure`), 일부만 되돌린 사실은 상세가 닫힌 뒤
     이력 목록 위(`undoPartial`)에 선다. 다음 되돌리기에서 걷힌다. */
  const [undoFailure, setUndoFailure] = useState("");
  const [undoPartial, setUndoPartial] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const query = useInfiniteList({
    key: ["offboarding-runs"],
    size: RUN_PAGE_SIZE,
    rowId: (r) => (r && r.id) || undefined,
    fetch: ({ page, page_size: size }) => api(`/api/admin/offboarding?page=${page}&page_size=${size}`),
  });
  const detailQ = useQuery({
    queryKey: ["offboarding-run", sel && sel.id],
    queryFn: () => api("/api/admin/offboarding/" + sel.id),
    enabled: !!sel,
    retry: false,
  });
  const items = query.rows;
  const total = query.total;

  async function undo(run) {
    const message = [
      `${run.user_name || "대상"}의 오프보딩을 되돌립니다.`,
      run.ticket_moved ? `옮긴 티켓 ${run.ticket_moved}건을 원래 담당자에게 되돌립니다.` : "",
      run.deactivated ? "계정을 다시 활성화합니다." : "",
      run.archived ? "계정 보관을 해제합니다." : "",
    ].filter(Boolean).join("\n");
    if (!(await confirm(message, { title: "오프보딩 되돌리기", confirmLabel: "되돌리기" }))) return;
    setBusy(true);
    setUndoFailure(""); setUndoPartial("");
    try {
      const res = await api("/api/admin/offboarding/" + run.id + "/undo", { method: "POST", body: {} });
      qc.invalidateQueries({ queryKey: ["offboarding-runs"] });
      qc.invalidateQueries({ queryKey: ["offboarding-run", run.id] });
      qc.invalidateQueries({ queryKey: ["users"] });
      // 되돌리기도 티켓 담당자를 다시 바꾼다(후임 → 원래 담당자) — 실행과 같은 이유로
      // 티켓을 그리는 화면 전부를 함께 무효화한다.
      invalidateTicketViews(qc, { refetchType: "all" });
      if (res.revert_failed) setUndoPartial(`${res.revert_failed}건을 되돌리지 못했습니다. 상세에서 사유를 확인하세요.`);
      else toast("되돌렸습니다.", "success");
      setSel(null);
    } catch (e) { setUndoFailure(e.message); }
    finally { setBusy(false); }
  }

  const columns = [
    // SEM-01: 첫 열(실행 시각)이 render라 표식 없이는 이 실행 이력 전부가 "상세 보기"로
    // 동일했다 — 대상 + 실행 시각으로 실제로 구별되는 이름을 만든다.
    { key: "created_at", label: "실행", type: "datetime", nowrap: true, render: (r) => <DateCell value={r.created_at} />, rowName: (r) => (r.user_name || "알 수 없음") + " / " + fmtDateTime(r.created_at) },
    // 서버가 이름을 못 주면(탈퇴 계정 등) raw UUID 대신 '알 수 없음'을 보여준다(E-4 UUID 노출).
    { key: "user_name", label: "대상", type: "name", render: (r) => r.user_name || "알 수 없음" },
    { key: "successor_name", label: "후임", type: "name", render: (r) => r.successor_name || "(없음)" },
    { key: "status", label: "상태", type: "status", render: (r) => (
      <Badge value={RUN_STATUS_KO[r.status] || r.status}
        kind={r.status === "completed" ? "ok" : r.status === "undone" ? "neutral" : "warn"} />
    ) },
    { key: "ticket_moved", label: "티켓", type: "code", render: (r) => `${r.ticket_moved}/${r.ticket_total}` + (r.ticket_failed ? ` (실패 ${r.ticket_failed}건)` : "") },
    { key: "actor_name", label: "실행자", type: "name" },
  ];

  const detail = (detailQ.data && detailQ.data.run) || sel;

  return (
    <Section titleAs="h2" title="실행 이력">
      {query.isError ? (
        <ErrorState layout="region" error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <>
          {/* 되돌리기의 일부 실패는 목록 위 상자가 말한다 — 목록 판 안 표 위에 서면 머리 줄을 판 윗변에서 밀어낸다. */}
          {undoPartial && items.length ? <Callout tone="danger" compact>{undoPartial}</Callout> : null}
          {/* 감사 이력은 지워지지 않고 계속 쌓인다 — 굴리면 이어 받는다(손으로 그린 페이저가
              여기 있었다, 이제 목록 판 발 하나를 다른 화면과 함께 쓴다 · 조합 계약 C-3). */}
          <DataTable
            placement="surface"
            loading={query.isLoading}
            columns={columns} rows={items} rowKey={(r) => r.id} onRow={(r) => { setUndoFailure(""); setSel(r); }} total={total}
            emptyState={(
              <EmptyState layout="region" title="아직 실행한 오프보딩이 없습니다."
                help="위에서 대상을 고르고 실행하면 여기에 기록이 남고, 그 자리에서 되돌릴 수 있습니다." />
            )}
            list={{
              total, loaded: query.loaded,
              hasNext: query.hasNext, isFetchingNext: query.isFetchingNext, onMore: query.fetchNext,
              moreLabel: "실행 이력 더 보기",
            }}
          />
        </>
      )}

      <Modal open={!!sel} onClose={() => setSel(null)} size="lg"
        title={sel ? (sel.user_name || "오프보딩") + " 실행 상세" : ""}
        footer={sel ? (
          /* 발 순서는 보조 → 확정이고 확정이 오른쪽 끝이다(핸드오프 RULES §7 · §8). 예전에는 「되돌리기」(채움)가 앞, 「감사
             로그에서 보기」가 뒤에 서서 확정이 오른쪽 끝이 아니었다. */
          <ActionFooter placement="modal">
              {/* offboarding_run은 감사 로그의 유효한 object_type이고(app/offboarding/router.py)
                  이제 OBJ_ROUTE에도 있다 — 이 화면은 admin/system_admin 전용(navConfig.js
                  SCREEN_ROLES.offboarding)이라 audit 접근 역할의 부분집합이라 별도 role 게이트가
                  필요 없다(MEGA CYCLE G). */}
              <Button href={"#/audit?object_type=offboarding_run&object_id=" + sel.id}>
                감사 로그에서 보기
              </Button>
              {!sel.undone_at ? (
                <Button variant="primary" disabled={busy} loading={busy} onClick={() => undo(sel)}>
                  되돌리기
                </Button>
              ) : null}
            </ActionFooter>
        ) : null}>
        {undoFailure ? <Callout tone="danger" compact>{undoFailure}</Callout> : null}
        {detail ? (
          <>
            <DetailGrid>
              {/* 이름이 없으면(탈퇴 계정 등) raw UUID 대신 '알 수 없음'을 보여준다(E-4 UUID 노출) */}
              <DetailRow label="대상">{detail.user_name || "알 수 없음"}</DetailRow>
              <DetailRow label="후임">{detail.successor_name || "(없음, 미할당으로 되돌림)"}</DetailRow>
              <DetailRow label="실행자">{detail.actor_name || "알 수 없음"}</DetailRow>
              <DetailRow label="상태">{RUN_STATUS_KO[detail.status] || detail.status}</DetailRow>
              <DetailRow label="티켓">{`${detail.ticket_moved}/${detail.ticket_total}건 이동, 실패 ${detail.ticket_failed}건`}</DetailRow>
              <DetailRow label="계정 변경">{[detail.deactivated ? "비활성화" : null, detail.archived ? "보관" : null].filter(Boolean).join(", ") || "없음"}</DetailRow>
              <DetailRow label="메모">{detail.note || "-"}</DetailRow>
              <DetailRow label="되돌린 시각">{detail.undone_at ? fmtDateTime(detail.undone_at) : "-"}</DetailRow>
            </DetailGrid>
            {detail.undo_error ? <Box sx={{ mt: 2 }}><Callout tone="danger">{detail.undo_error}</Callout></Box> : null}
            {(detail.moves || []).length ? (
              <Box sx={{ mt: 2 }}>
                <DataTable columns={MOVE_COLUMNS} rows={detail.moves} rowKey={(m) => m.id} />
              </Box>
            ) : null}
          </>
        ) : null}
      </Modal>
    </Section>
  );
}

export default Offboarding;
