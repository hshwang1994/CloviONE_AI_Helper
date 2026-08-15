import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { useAuth } from "../app/auth.jsx";
import { PageHeader, Card, Button, Callout, Skeleton, ErrorState, EmptyState } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "../ui/theme.js";

/* 최초 실행 셋업 마법사 (9-3, P3).
 *
 * ## 이 화면이 하는 일과 하지 않는 일
 *
 * **하는 일**: 서버가 계산한 남은 항목을 **그 순서 그대로** 보여 주고, 막힌 항목이 무엇
 * 때문에 막혔는지 말하고, 각 항목을 실제로 고칠 수 있는 화면으로 보낸다.
 *
 * **하지 않는 일**: 여기서 설정을 바꾸지 않는다. 조직, 부서, 연동, 러너, Notion 연결에는
 * 이미 각자의 화면이 있고 거기에는 검증과 감사와 되돌리기가 붙어 있다. 마법사가 지름길을
 * 하나 더 내면 그 세 가지가 없는 두 번째 쓰기 경로가 생긴다.
 *
 * ## 왜 상태로 다시 정렬하지 않는가
 *
 * 끝난 것을 아래로 내리고 싶은 유혹이 있다. 그러면 안내 순서가 의존 순서가 아니게 되고,
 * 사용자는 3번이 안 되는 이유가 1번이라는 것을 영원히 모른다. 순서는 서버가 정한다.
 *
 * ## 왜 닫는 버튼이 없는가
 *
 * 접을 수는 있지만 **남은 항목 수는 접어도 남는다**. 한 번 닫으면 다시 못 보는 마법사는
 * 설정을 미룬 사람에게 아무 도움이 안 된다(과제 요구 3).
 */

// 상태를 색으로만 말하지 않는다(WCAG 1.4.1, 이 앱의 Badge, Callout 과 같은 규칙).
const STATE_LABEL = { done: "됨", todo: "안 됨", unknown: "확인 불가" };
const STATE_TONE = { done: "success", todo: "warn", unknown: "info" };
const TONE_COLOR = { success: "success.main", warn: "warning.main", info: "info.main" };

/* 항목마다 "그래서 어디로 가면 되는가".
 *
 * ⚠️ **여기 적는 경로는 실제로 라우팅되는 것이어야 한다.** 죽은 링크는 안내가 아니라
 * 막다른 길이고, 이 화면은 막다른 길을 없애려고 만든 것이다. setup-wizard.test.jsx 가
 * 모든 값이 AdminRoutes.jsx 의 명시 경로이거나 registry.js 의 키인지 확인한다.
 *
 * Notion 데이터베이스 id 와 토큰은 **이제 화면에서 바꾼다**(9-4, #/notion-console).
 * 예전에는 서버 파일을 고치고 재시작해야 해서 '고치는 화면' 대신 진단으로 보냈고, 이 주석이
 * 그 사실을 적어 두고 있었다. 화면이 생겼으니 고치는 자리로 곧장 보낸다.
 * SYS-06: `llm` 항목은 예전엔 여기가 `#/llm-console`(AI 관리)을 가리켰다 — "러너는 별개라
 * 그쪽으로 보내면 엉뚱하다"는 근거였다. 그런데 `probe_llm`(app/setup/probes.py)이 실제로
 * 재는 것은 `app.runners.models.Runner` 행이고, 그 프로브 자신의 안내 문구도 전부 "관리
 * 콘솔의 러너 화면에서 …"라고 말한다(등록·활성화·헬스체크 전부) — 안내는 러너 화면을
 * 가리키는데 링크만 AI 관리로 갔다. `/llm-console`은 이 항목이 재는 것(Runner 레지스트리)
 * 과 무관한 별개 백엔드(app/llm/service.py, CLI 기반)를 설정하는 화면이라 눌러도 이 항목이
 * 빨간 이유(러너 미등록/비활성/헬스 실패)를 고칠 수 없었다(RN-10/RN-11 조사에서 확인된 그
 * 분리와 같은 뿌리). */
export const SETUP_LINKS = {
  admin_account: { href: "#/users", label: "사용자 화면 열기" },
  mail: { href: "#/settings", label: "설정 화면 열기" },
  organization: { href: "#/departments", label: "부서 화면 열기" },
  notion: { href: "#/notion-console", label: "Notion 관리 화면 열기" },
  user_mapping: { href: "#/notion-mapping", label: "Notion 연결 화면 열기" },
  llm: { href: "#/runners", label: "러너 화면 열기" },
  integrations: { href: "#/integrations", label: "외부 연동 화면 열기" },
  tls: { href: "#/diagnostics", label: "진단에서 인증서 확인" },
};

function StateTag({ state }) {
  const label = STATE_LABEL[state] || state;
  return (
    <Box
      component="span"
      sx={{
        px: 1, py: 0.25, borderRadius: RADIUS.full, fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.extrabold,
        border: "1px solid", borderColor: TONE_COLOR[STATE_TONE[state]] || "divider",
        color: TONE_COLOR[STATE_TONE[state]] || "text.secondary", whiteSpace: "nowrap",
      }}
    >
      {label}
    </Box>
  );
}

function SetupItem({ item, isNext }) {
  const link = SETUP_LINKS[item.key];
  const blocked = item.blocked_by != null;
  return (
    <Box
      data-setup-key={item.key}
      data-testid={"setup-item-" + item.key}
      component="li"
      sx={{
        listStyle: "none", display: "grid", gap: 0.75, py: 2,
        borderTop: "1px solid", borderColor: "divider",
        opacity: blocked ? 0.75 : 1,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography component="h3" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle }}>
          {item.label}
        </Typography>
        <StateTag state={item.state} />
        {isNext ? (
          <Box
            component="span"
            sx={{
              px: 1, py: 0.25, borderRadius: RADIUS.full, fontSize: FONT_SIZE.caption,
              fontWeight: FONT_WEIGHT.extrabold, bgcolor: "primary.main", color: "primary.contrastText",
            }}
          >
            지금 할 차례
          </Box>
        ) : null}
      </Box>
      <Typography variant="body2" color="text.secondary">{item.detail}</Typography>
      {blocked ? (
        <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold }}>
          {item.blocked_by_label}를 먼저 끝내야 이 항목을 진행할 수 있습니다.
          {item.requires_why ? " " + item.requires_why : ""}
        </Typography>
      ) : item.action ? (
        <Typography variant="body2">
          <Box component="span" sx={{ fontWeight: FONT_WEIGHT.extrabold, mr: 1 }}>할 일</Box>
          {item.action}
        </Typography>
      ) : item.question ? (
        <Typography variant="body2">
          <Box component="span" sx={{ fontWeight: FONT_WEIGHT.extrabold, mr: 1 }}>확인할 것</Box>
          {item.question}
        </Typography>
      ) : null}
      <Typography variant="caption" color="text.secondary">{item.why}</Typography>
      {link ? (
        <Box>
          <Link href={link.href} underline="hover" sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold }}>
            {link.label}
          </Link>
        </Box>
      ) : null}
    </Box>
  );
}

function Summary({ data }) {
  const remaining = (data.remaining || []).length;
  const todo = (data.todo || []).length;
  const unknown = (data.unknown || []).length;
  if (data.complete) {
    return (
      <Box data-testid="setup-summary">
        <Callout tone="success">
          초기 설정 항목이 모두 끝났습니다. 아래 목록은 그대로 두어 언제든 다시 확인할 수 있습니다.
        </Callout>
      </Box>
    );
  }
  return (
    <Box data-testid="setup-summary">
      <Callout tone="warn">
        {`남은 항목 ${remaining}개입니다. 사람이 해야 할 일 ${todo}개, 확인이 필요한 것 ${unknown}개.`}
        {" 확인이 필요한 것은 이 서버에서는 판단할 수 없어 사람에게 묻는 항목입니다."}
      </Callout>
    </Box>
  );
}

export function SetupWizard() {
  const auth = useAuth();
  const role = auth && auth.data && auth.data.role;
  // 서버와 같은 게이트(app/setup/router.py: SYSTEM_ADMIN_ONLY). 넓게 두면 눌렀더니 403인
  // 막다른 길이 되고, 요청 자체를 보내면 권한 없는 사람이 실패 요청만 반복한다.
  const allowed = role === "system_admin";
  const [open, setOpen] = React.useState(true);

  const query = useQuery({
    queryKey: ["setup-checklist"],
    queryFn: () => api("/api/admin/setup/checklist"),
    enabled: allowed,
    retry: false,
  });

  if (!allowed) {
    return (
      <Box className="c-screen">
        <PageHeader area="시스템" title="초기 설정" />
        <EmptyState
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
        <PageHeader area="시스템" title="초기 설정" />
        <Card><Skeleton lines={7} /></Card>
      </Box>
    );
  }
  if (query.isError) {
    return (
      <Box className="c-screen">
        <PageHeader area="시스템" title="초기 설정" />
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      </Box>
    );
  }

  const data = query.data || {};
  const items = data.items || [];
  return (
    <Box className="c-screen">
      <PageHeader
        area="시스템"
        title="초기 설정"
        actions={
          <Button onClick={() => setOpen((v) => !v)}>
            {open ? "목록 접기" : "목록 펼치기"}
          </Button>
        }
      />
      <Summary data={data} />
      {open ? (
        <Card sx={{ mt: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            아래 순서는 의존 순서입니다. 앞 항목이 끝나야 뒤 항목이 실제로 동작합니다.
          </Typography>
          <Box component="ul" sx={{ m: 0, p: 0 }}>
            {items.map((item) => (
              <SetupItem key={item.key} item={item} isNext={item.key === data.next_key} />
            ))}
          </Box>
        </Card>
      ) : null}
    </Box>
  );
}

export default SetupWizard;
