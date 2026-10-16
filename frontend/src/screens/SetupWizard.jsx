import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime, objectParticle } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import {
  PageHeader, Card, Button, Skeleton, ErrorState, EmptyState, FlowStack, FormSection, useToast,
} from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, LINE_HEIGHT, KO_WORD_BREAK, PROSE_MAX_WIDTH } from "../ui/theme.js";
import { copyText } from "./ops/opsHelpers.js";
import { CHECKLIST_CONTAINER, ChecklistList, ChecklistRow } from "./setup/ChecklistRow.jsx";
import { SetupSummary } from "./setup/SetupSummary.jsx";

/* 초기 설정 체크리스트 (9-3 · D-520 · D-534).
 *
 * ## 이 화면이 하는 일과 하지 않는 일
 *
 * **하는 일**: 서버가 계산한 항목을 **그 순서 그대로** 필수 · 선택 두 구획에 세우고, 맨 위 요약 띠가 지금 상태 한 문장과 다음 할 일을
 * 말한다. 항목마다 상태 아이콘 · 이름 · 상태 한 문장 · 동작이 한 줄에 서고, 펼치면 할 일 · 왜 필요한가 · 막힌 까닭 · 덧붙임 · 복사할
 * 명령 · 최근 확인이 보인다. 지금 할 줄은 저절로 펼쳐진다.
 *
 * **하지 않는 일**: 설정 자체는 여기서 바꾸지 않는다. 조직, 부서, 메일, AI 연결, 연동에는 각자의 화면이 있고 거기에 검증과 감사와
 * 되돌리기가 붙어 있다. 여기서 바꾸는 것은 선택 값 하나뿐이다(메일 · AI 「사용하지 않음」, TLS 「외부 프록시가 맡음」) — 서버가 그 키
 * 하나를 행 잠금 안에서 합치고(`PUT /api/admin/setup/choices/{key}`) 새 체크리스트를 돌려준다. 화면은 그 값으로 바로 다시 그린다.
 *
 * ## 왜 상태로 다시 정렬하지 않는가
 *
 * 끝난 것을 아래로 내리면 안내 순서가 의존 순서가 아니게 되고, 사용자는 뒤 항목이 안 되는 이유가 앞 항목이라는 것을 모른다.
 *
 * ## 왜 닫는 버튼이 없는가
 *
 * 한 번 닫으면 다시 못 보는 마법사는 설정을 미룬 사람에게 아무 도움이 안 된다(과제 요구 3). 끝난 뒤에도 목록은 그대로 남는다.
 */

const DESCRIPTION = "처음 설치할 때 필요한 설정을 순서대로 안내합니다.";
const HELP = "‘확인 필요’는 설정은 끝났지만 실제로 동작하는지 아직 확인하지 않았다는 뜻입니다. "
  + "선택 기능은 쓰지 않으면 ‘사용하지 않음’으로 둘 수 있고, 그것도 끝난 것으로 셉니다.";

/* 항목마다 "그래서 어디로 가면 되는가" - 서버가 링크를 주지 않을 때(옛 서버)만 쓰는 대체 표다.
 *
 * ⚠️ **여기 적는 경로는 실제로 라우팅되는 것이어야 한다.** 죽은 링크는 안내가 아니라 막다른 길이다. setup-wizard.test.jsx 가
 * 모든 값이 AdminRoutes.jsx 의 명시 경로이거나 registry.js 의 키인지 확인한다. 서버가 주는 링크(`app/setup/probes.py`)도 같은 경로들이다. */
export const SETUP_LINKS = {
  admin_account: { href: "#/users", label: "사용자 화면 열기" },
  mail: { href: "#/mail?tab=settings", label: "메일 설정 열기" },
  organization: { href: "#/departments", label: "부서 화면 열기" },
  llm: { href: "#/ai-connection", label: "AI 연결 열기" },
  integrations: { href: "#/diagnostics", label: "진단에서 연동 상태 보기" },
  tls: { href: "#/diagnostics", label: "진단에서 인증서 확인" },
};

/** 항목의 링크 - 서버가 준 것이 먼저다(상태마다 가야 할 곳이 다르다). */
export function linkOf(item) {
  if (item && item.href && item.link_label) return { href: item.href, label: item.link_label };
  return (item && SETUP_LINKS[item.key]) || null;
}

/* 끝난 줄(완료 · 사용하지 않음)과 앞 항목을 기다리는 줄은 줄 위에 단추를 세우지 않는다 — 할 일이 있는 줄만 단추가 선다(D-501).
   끝난 줄의 이동 링크와 선택 되돌리기(「다시 사용」 · 「이 서버의 인증서 사용」)는 펼친 칸에 있다. */
const SETTLED = new Set(["done", "skipped"]);
function hasInlineActions(item) {
  return !SETTLED.has(item.status) && item.status !== "waiting";
}

function choiceToast(item, choice) {
  if (choice.value === "unused") return `${item.label} 항목을 ‘사용하지 않음’으로 두었습니다.`;
  if (choice.value === "use") return `${item.label} 항목을 다시 사용합니다.`;
  if (choice.value === "proxy") return "외부 프록시가 TLS를 맡는다고 표시했습니다.";
  if (choice.value === "app") return "이 서버의 인증서로 TLS를 확인합니다.";
  return "선택을 바꿨습니다.";
}

function ItemButtons({ item, onChoice, choosing }) {
  const link = linkOf(item);
  const choices = item.choices || [];
  if (!link && !choices.length) return null;
  return (
    <>
      {link ? <Button size="sm" href={link.href}>{link.label}</Button> : null}
      {choices.map((c) => (
        <Button key={c.key + ":" + c.value} size="sm" disabled={choosing} onClick={() => onChoice(item, c)}>{c.label}</Button>
      ))}
    </>
  );
}

function DetailLine({ label, children }) {
  return (
    <>
      <Typography component="dt" sx={{ fontSize: FONT_SIZE.caption, lineHeight: LINE_HEIGHT.bodySm, fontWeight: FONT_WEIGHT.semibold, color: "text.secondary" }}>
        {label}
      </Typography>
      {/* 까닭 · 덧붙임은 두세 문장의 산문이다 - 넓은 화면에서 한 줄이 끝없이 늘지 않게 산문 폭으로 묶는다. */}
      <Box component="dd" sx={{ m: 0, minWidth: 0, maxWidth: PROSE_MAX_WIDTH, fontSize: FONT_SIZE.bodySm, lineHeight: LINE_HEIGHT.bodySm, ...KO_WORD_BREAK }}>
        {children}
      </Box>
    </>
  );
}

function CommandLine({ command }) {
  const toast = useToast();
  const copy = () => copyText(command).then((ok) => toast(ok ? "명령을 복사했습니다." : "복사하지 못했습니다. 명령을 직접 선택해 복사하세요.", ok ? "success" : "error"));
  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1, minWidth: 0 }}>
      <Box
        component="code"
        sx={{
          flex: "1 1 auto", minWidth: 0, display: "block", px: 1, py: 0.5, borderRadius: 1, bgcolor: "background.inset",
          fontFamily: "monospace", fontSize: FONT_SIZE.caption, lineHeight: LINE_HEIGHT.bodySm, whiteSpace: "pre-wrap", wordBreak: "break-all",
        }}
      >
        {command}
      </Box>
      <Button size="sm" onClick={copy} aria-label="명령 복사">복사</Button>
    </Box>
  );
}

/* 펼친 칸 — 할 일(또는 확인할 것 · 막힌 까닭), 왜 필요한가, 덧붙임, 복사할 명령, 최근 확인. 끝난 줄은 이동 링크와 선택 되돌리기도 여기에. */
function ItemDetails({ item, onChoice, choosing }) {
  const waiting = item.status === "waiting";
  const settledButtons = !hasInlineActions(item) && !waiting;
  return (
    <Box sx={{ display: "grid", rowGap: 1.5, minWidth: 0 }}>
      <Box
        component="dl"
        sx={{
          m: 0, display: "grid", gridTemplateColumns: "minmax(0,1fr)", columnGap: 2, rowGap: 0.75, alignItems: "baseline",
          [`@container ${CHECKLIST_CONTAINER} (min-width: 30rem)`]: { gridTemplateColumns: "6.5rem minmax(0,1fr)" },
        }}
      >
        {waiting ? (
          <DetailLine label="막힌 까닭">
            {`${item.blocked_by_label}${objectParticle(item.blocked_by_label || "")} 먼저 끝내야 이 항목을 진행할 수 있습니다.`}
            {item.requires_why ? " " + item.requires_why : ""}
          </DetailLine>
        ) : item.action && !SETTLED.has(item.status) ? (
          <DetailLine label="할 일">{item.action}</DetailLine>
        ) : item.question && !SETTLED.has(item.status) ? (
          <DetailLine label="확인할 것">{item.question}</DetailLine>
        ) : null}
        {item.why ? <DetailLine label="왜 필요한가">{item.why}</DetailLine> : null}
        {(item.notes || []).length ? (
          <DetailLine label="참고">
            {item.notes.map((note, i) => (
              <Box key={i} component="p" sx={{ m: 0, "& + &": { mt: 0.5 } }}>{note}</Box>
            ))}
          </DetailLine>
        ) : null}
        {item.command ? <DetailLine label="명령"><CommandLine command={item.command} /></DetailLine> : null}
        {item.checked_at ? <DetailLine label="최근 확인">{fmtDateTime(item.checked_at)}</DetailLine> : null}
      </Box>
      {settledButtons ? (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          <ItemButtons item={item} onChoice={onChoice} choosing={choosing} />
        </Box>
      ) : null}
    </Box>
  );
}

function ChecklistSection({ title, description, items, expanded, onToggle, onChoice, choosing }) {
  if (!items.length) return null;
  return (
    <FormSection titleAs="h2" title={title} description={description}>
      <ChecklistList aria-label={title + " 항목"}>
        {items.map((item) => (
          <ChecklistRow
            key={item.key}
            id={"setup-" + item.key}
            data-setup-key={item.key}
            data-testid={"setup-item-" + item.key}
            data-setup-state={item.state}
            name={item.label}
            status={item.status}
            statusLabel={item.status_label}
            description={item.detail}
            current={!!item.current}
            actions={hasInlineActions(item) ? <ItemButtons item={item} onChoice={onChoice} choosing={choosing} /> : null}
            expanded={expanded(item)}
            onToggle={() => onToggle(item)}
          >
            <ItemDetails item={item} onChoice={onChoice} choosing={choosing} />
          </ChecklistRow>
        ))}
      </ChecklistList>
    </FormSection>
  );
}

export function SetupWizard() {
  const auth = useAuth();
  const role = auth && auth.data && auth.data.role;
  // 서버와 같은 게이트(app/setup/router.py: SYSTEM_ADMIN_ONLY). 넓게 두면 눌렀더니 403인
  // 막다른 길이 되고, 요청 자체를 보내면 권한 없는 사람이 실패 요청만 반복한다.
  const allowed = role === "system_admin";
  const qc = useQueryClient();
  const toast = useToast();
  // 사람이 직접 여닫은 줄만 기억한다. 나머지는 「지금 할 줄이면 펼침」 — 선택을 바꿔 다음 줄이 지금 할 차례가 되면 그 줄이 펼쳐진다.
  const [toggled, setToggled] = React.useState({});

  const query = useQuery({
    queryKey: ["setup-checklist"],
    queryFn: () => api("/api/admin/setup/checklist"),
    enabled: allowed,
    retry: false,
  });

  const choose = useMutation({
    mutationFn: ({ choice }) => api(`/api/admin/setup/choices/${encodeURIComponent(choice.key)}`, { method: "PUT", body: { value: choice.value } }),
    onSuccess: (res, vars) => {
      // 서버가 새 체크리스트를 돌려준다 - 다시 묻지 않고 그 값으로 그린다.
      if (res && Array.isArray(res.items)) qc.setQueryData(["setup-checklist"], res);
      else qc.invalidateQueries({ queryKey: ["setup-checklist"] });
      toast(choiceToast(vars.item, vars.choice), "success");
    },
    onError: (e) => toast((e && e.message) || "선택을 바꾸지 못했습니다.", "error"),
  });
  const onChoice = (item, choice) => choose.mutate({ item, choice });
  const expanded = (item) => (item.key in toggled ? toggled[item.key] : !!item.current);
  const onToggle = (item) => setToggled((prev) => ({ ...prev, [item.key]: !expanded(item) }));

  const header = (actions) => (
    <PageHeader area="설정" title="초기 설정" description={DESCRIPTION} help={HELP} actions={actions} />
  );

  if (!allowed) {
    return (
      <Box className="c-screen">
        {header(null)}
        <EmptyState
          layout="page"
          title="권한이 없습니다"
          help="이 화면은 시스템 관리자만 사용할 수 있습니다. 여기 담긴 것은 조직 단위가 아니라 서버 한 대 전체의 상태입니다."
          art="noPermission"
          action={<Button variant="primary" onClick={() => { window.location.hash = "#/dashboard"; }}>대시보드로 이동</Button>}
        />
      </Box>
    );
  }
  if (query.isLoading) {
    return (
      <Box className="c-screen">
        {header(null)}
        <FlowStack>
          <Card><Skeleton lines={2} /></Card>
          <Card><Skeleton lines={6} /></Card>
        </FlowStack>
      </Box>
    );
  }
  if (query.isError) {
    return (
      <Box className="c-screen">
        {header(null)}
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      </Box>
    );
  }

  const data = query.data || {};
  const items = data.items || [];
  const required = items.filter((i) => i.required !== false);
  const optional = items.filter((i) => i.required === false);
  const current = items.find((i) => i.key === (data.current_key || data.next_key)) || null;
  const currentLink = current ? linkOf(current) : null;
  return (
    <Box className="c-screen">
      {header(
        <Button loading={query.isFetching} onClick={() => query.refetch()}>다시 확인</Button>
      )}
      <FlowStack>
        <SetupSummary
          data={data}
          primary={currentLink ? <Button variant="primary" href={currentLink.href}>{currentLink.label}</Button> : null}
        />
        <Card stack data-testid="setup-checklist">
          <ChecklistSection
            title="필수"
            description="모두 끝나야 설치가 끝납니다."
            items={required}
            expanded={expanded}
            onToggle={onToggle}
            onChoice={onChoice}
            choosing={choose.isPending}
          />
          <ChecklistSection
            title="선택"
            description="쓰지 않는 기능은 ‘사용하지 않음’으로 둘 수 있습니다."
            items={optional}
            expanded={expanded}
            onToggle={onToggle}
            onChoice={onChoice}
            choosing={choose.isPending}
          />
        </Card>
      </FlowStack>
    </Box>
  );
}

export default SetupWizard;
