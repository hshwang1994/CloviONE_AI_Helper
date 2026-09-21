import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { useAuth } from "../app/auth.jsx";
import {
  PageHeader, Card, Badge, Button, Callout, Skeleton, ErrorState, EmptyState,
  DotLabel, SectionTitle,
} from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { GRID_GAP } from "../ui/density.js";

/* 최초 실행 셋업 마법사 (9-3, P3).
 *
 * ## 이 화면이 하는 일과 하지 않는 일
 *
 * **하는 일**: 서버가 계산한 남은 항목을 **그 순서 그대로** 보여 주고, 막힌 항목이 무엇
 * 때문에 막혔는지 말하고, 각 항목을 실제로 고칠 수 있는 화면으로 보낸다.
 *
 * **하지 않는 일**: 여기서 설정을 바꾸지 않는다. 조직, 부서, 연동, AI 설정에는 이미 각자의
 * 화면이 있고 거기에는 검증과 감사와 되돌리기가 붙어 있다. 마법사가 지름길을 하나 더 내면
 * 그 세 가지가 없는 두 번째 쓰기 경로가 생긴다.
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
/* 상태는 `Badge` 다(분류라면 `Tag`). 예전에는 여기서 알약을 손으로 그렸는데(테두리 + 색 글자 +
   `RADIUS.full`), 그 알약은 제품의 다른 어떤 상태 표시와도 모양이 달랐다 — 같은 뜻(됨·안 됨)이
   사용자 화면의 표지+글자와 다르게 보이면 관리자 화면이 다른 제품으로 읽힌다. */
const STATE_KIND = { done: "ok", todo: "warn", unknown: "info" };

/* 한 문장을 네 자리(권한 없음·로딩·오류·본문)가 각자 복사해 들고 있었다. */
const DESCRIPTION = "처음 설치할 때 필요한 설정 중 아직 안 끝난 항목을 순서대로 안내합니다.";

/* 항목마다 "그래서 어디로 가면 되는가".
 *
 * ⚠️ **여기 적는 경로는 실제로 라우팅되는 것이어야 한다.** 죽은 링크는 안내가 아니라
 * 막다른 길이고, 이 화면은 막다른 길을 없애려고 만든 것이다. setup-wizard.test.jsx 가
 * 모든 값이 AdminRoutes.jsx 의 명시 경로이거나 registry.js 의 키인지 확인한다.
 *
 * 「Notion 토큰과 데이터베이스」 항목이 여기 있었고 `#/notion-console` 로 보냈다. 티켓과
 * 문서와 리포트가 그 토큰으로 노션을 읽던 때에는 설치할 때 반드시 채워야 하는 값이었다.
 * 지금은 셋 다 이 서버의 데이터베이스에서 나오므로 채울 값도, 보낼 화면도 없다 —
 * 서버의 안내 목록(app/setup/steps.py)에서도 그 단계가 빠졌다.
 * 그 뒤에 남아 있던 「사용자 매핑」 항목도 같은 이유로 함께 걷었다(S20) — 그 항목이
 * 보내던 `#/notion-mapping` 화면이 없어졌고, 담당자 축은 이제 옛 짝이 없으면 자기
 * user id 로 선다(D-285)이라 설치할 때 연결할 것이 없다.
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
  /* 메일은 설정 표의 그 한 줄을 연다(`SettingsMain.jsx` 의 `?setting=` 딥링크) — 스무 항목짜리 표 앞에 세워 두고
     어느 줄인지 찾게 하지 않는다. 메일 발송 화면의 「메일 설정 열기」와 같은 곳 · 같은 이름이다. */
  mail: { href: "#/settings?setting=smtp", label: "메일 설정 열기" },
  organization: { href: "#/departments", label: "부서 화면 열기" },
  llm: { href: "#/settings?tab=ai", label: "AI 설정 열기" },
  // 「외부 연동」 관리 화면은 걷었다 — 0017 이 등록 행을 지웠고 시드 목록이 비어 있어
  // 그 표가 다시 안 채워진다. 연동 상태를 읽는 자리는 진단이다.
  integrations: { href: "#/diagnostics", label: "진단에서 연동 상태 보기" },
  tls: { href: "#/diagnostics", label: "진단에서 인증서 확인" },
};

/* 끝난 항목은 **한 줄**이다(D-501 — 끝남 · 0건 · 정상은 한 줄, 남은 일 · 이상만 펼친다). 이름 · 「됨」 · 지금 상태
   한 문장이 한 줄에 선다. 예전에는 끝난 항목도 남은 항목처럼 설명 · 까닭 · 이동 링크를 다 펼쳐, 여섯 항목 중 셋이
   끝난 설치에서 목록의 절반이 읽을 필요가 없는 글이었다. 자리(순서)와 항목은 그대로다 — 순서는 의존 순서라서
   끝난 것을 빼거나 아래로 내리지 않는다(위 머리말 「왜 상태로 다시 정렬하지 않는가」). */
function DoneItem({ item }) {
  return (
    <Box
      data-setup-key={item.key}
      data-testid={"setup-item-" + item.key}
      data-setup-state="done"
      component="li"
      sx={{
        listStyle: "none", display: "flex", alignItems: "baseline", columnGap: 1, rowGap: 0.25, flexWrap: "wrap",
        py: 1.25, borderTop: 1, borderColor: "divider",
      }}
    >
      <Typography component="h2" variant="body1" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
        {item.label}
      </Typography>
      <Badge value={STATE_LABEL[item.state] || item.state} kind={STATE_KIND[item.state]} />
      {item.detail ? (
        <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>{item.detail}</Typography>
      ) : null}
    </Box>
  );
}

/* 남은 항목 하나 — 이름 · 상태 · 지금 상태 · 할 일(또는 확인할 것 · 막힌 까닭) · 그것이 왜 필요한가 · 고치는 화면.
 *
 * **지금 할 차례인 항목은 할 일과 이동 링크를 여기서 말하지 않는다** — 옆 레일의 「지금 할 차례」 판이 그 둘을 이 화면의
 * 주 동작으로 든다(D-501 — 한 사실은 한 곳). 목록의 그 줄에는 「지금 할 차례」 표지가 서서 레일과 같은 항목임을 잇는다. */
function SetupItem({ item, isNext }) {
  const link = SETUP_LINKS[item.key];
  const blocked = item.blocked_by != null;
  return (
    <Box
      data-setup-key={item.key}
      data-testid={"setup-item-" + item.key}
      component="li"
      sx={{
        listStyle: "none", display: "grid", gap: 0.5, py: 2,
        borderTop: 1, borderColor: "divider",
        opacity: blocked ? 0.75 : 1,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        {/* 항목 제목은 h2 그대로다(h1 바로 아래, 판에 따로 제목이 없다). 크기만 본문 단계로
            내렸다 — 여섯 항목이 각각 구획 제목 크기로 서면 한 화면에 제목이 일곱이다. */}
        <Typography component="h2" variant="body1" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
          {item.label}
        </Typography>
        <Badge value={STATE_LABEL[item.state] || item.state} kind={STATE_KIND[item.state]} />
        {/* 목록 행 안에서 면 배지를 세우지 않는다(RULES §2) — 「지금 할 차례」는 점 + 낱말을 600 으로 세운다. */}
        {isNext ? <DotLabel label="지금 할 차례" tone="info" strong sx={{ fontSize: FONT_SIZE.bodySm }} /> : null}
      </Box>
      <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{item.detail}</Typography>
      {blocked ? (
        <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
          {item.blocked_by_label}를 먼저 끝내야 이 항목을 진행할 수 있습니다.
          {item.requires_why ? " " + item.requires_why : ""}
        </Typography>
      ) : isNext ? null : <NextStep item={item} />}
      <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>{item.why}</Typography>
      {link && !isNext ? (
        <Box>
          <Link href={link.href} underline="hover" variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold }}>
            {link.label}
          </Link>
        </Box>
      ) : null}
    </Box>
  );
}

/* 사람이 할 일 한 줄 — 「안 됨」은 할 일이고 「확인 불가」는 확인할 것이다. 같은 말로 부르면 사람이 할 일과 물어볼
   일이 뒤섞인다. 목록의 줄과 레일이 이 한 부품을 쓴다. */
function NextStep({ item }) {
  const [label, text] = item.action ? ["할 일", item.action] : item.question ? ["확인할 것", item.question] : [null, null];
  if (!label) return null;
  return (
    <Typography variant="body2" sx={KO_WORD_BREAK}>
      <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, mr: 1 }}>{label}</Box>
      {text}
    </Typography>
  );
}

/** 진행을 말하는 한 문장 — 「6개 중 3개가 끝났습니다. 직접 할 일이 2개, 확인할 것이 1개 남았습니다.」
 *
 * 예전에는 같은 수가 두 번 섰다: 「남은 항목 3개입니다. 사람이 해야 할 일 2개, 확인이 필요한 것 1개.」라는 조각 문장과,
 * 그 수를 다시 그린 상태 요약 카드(「3 남은 항목 · 할 일 2 · 확인 필요 1」)였다. 수는 이 한 문장이 말한다. */
export function setupProgressText(data) {
  const items = (data && data.items) || [];
  const done = items.filter((i) => i.state === "done").length;
  const todo = ((data && data.todo) || []).length;
  const unknown = ((data && data.unknown) || []).length;
  const head = done ? `${items.length}개 중 ${done}개가 끝났습니다.` : `${items.length}개 중 아직 끝난 항목이 없습니다.`;
  const rest = [todo ? `직접 할 일이 ${todo}개` : null, unknown ? `확인할 것이 ${unknown}개` : null].filter(Boolean);
  return rest.length ? `${head} ${rest.join(", ")} 남았습니다.` : head;
}

/* **지금 할 차례** 판 — 목록 위에 전폭으로 선다(사용자 지시, 2026-09-21. 그 전에는 목록 옆 레일이었다).
 *
 * 다음 항목의 할 일과 그것을 고치는 화면으로 가는 단추가 이 화면의 주 동작이다(D-501 — 채움은 화면당 하나). 목록을 접어도
 * 이 판은 남는다 — 한 번 닫으면 다시 못 보는 마법사는 설정을 미룬 사람에게 도움이 안 된다. 다 끝나면 할 차례가 없으므로
 * 끝났다는 문장 하나만 선다.
 *
 * 전폭이 되면서 **글과 단추가 한 줄**이다 — 할 일 문장이 왼쪽에서 폭을 쓰고 단추가 오른쪽 끝에 선다(메일 발송의 안내 상자와
 * 같은 어휘). 레일이던 때처럼 단추를 문장 아래 두면 1920 에서 오른쪽 1,200px 가 빈다(실측). 좁아지면 줄이 접혀 단추가
 * 문장 아래로 내려간다. 읽는 순서(항목 → 할 일 → 단추)는 어느 폭에서나 같다. */
function NowRail({ data }) {
  const items = data.items || [];
  const next = data.complete ? null : items.find((i) => i.key === data.next_key) || null;
  const link = next ? SETUP_LINKS[next.key] : null;
  return (
    <Box data-testid="setup-summary" sx={{ display: "grid", gap: 1.5, justifyItems: "stretch" }}>
      {data.complete ? (
        <Callout tone="success">
          초기 설정 항목이 모두 끝났습니다. 목록은 그대로 두어 언제든 다시 확인할 수 있습니다.
        </Callout>
      ) : (
        <>
          {next ? (
            <>
              <SectionTitle component="h2" title="지금 할 차례" sx={{ mb: 0 }} />
              <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 2 }}>
                <Box data-setup-now={next.key} sx={{ display: "grid", gap: 0.5, flex: "1 1 20rem", minWidth: 0 }}>
                  <Typography variant="body1" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>{next.label}</Typography>
                  <NextStep item={next} />
                </Box>
                {link ? (
                  <Box sx={{ flex: "0 0 auto" }}>
                    <Button variant="primary" href={link.href}>{link.label}</Button>
                  </Box>
                ) : null}
              </Box>
            </>
          ) : null}
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{setupProgressText(data)}</Typography>
        </>
      )}
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
        <PageHeader area="설정" title="초기 설정" description={DESCRIPTION} />
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
        <PageHeader area="설정" title="초기 설정" description={DESCRIPTION} />
        <Card><Skeleton lines={7} /></Card>
      </Box>
    );
  }
  if (query.isError) {
    return (
      <Box className="c-screen">
        <PageHeader area="설정" title="초기 설정" description={DESCRIPTION} />
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      </Box>
    );
  }

  const data = query.data || {};
  const items = data.items || [];
  return (
    <Box className="c-screen">
      <PageHeader
        area="설정"
        title="초기 설정"
        description={DESCRIPTION}
        help="확인할 것은 이 서버가 스스로 판단할 수 없어 사람에게 묻는 항목입니다."
        actions={
          <Button onClick={() => setOpen((v) => !v)}>
            {open ? "목록 접기" : "목록 펼치기"}
          </Button>
        }
      />
      {/* 두 판은 **위아래로 이어진다** — 「지금 할 차례」가 위, 목록이 아래다(사용자 지시, 2026-09-21).
          여기 주 판 + 곁열 2열 격자가 있었는데, 지금 할 일과 전체 목록은 나란히 견주는 값이 아니라
          차례로 읽는 것이다. 화면 폭에 따라 배치가 갈리지 않고 어느 폭에서나 같은 순서로 읽힌다
          (D-501 — 머리 → 지금 할 일 → 목록). 판은 제 내용만큼만 선다. */}
      <Box sx={{ display: "grid", gap: GRID_GAP, gridTemplateColumns: "minmax(0, 1fr)", alignItems: "start" }}>
        <Card component="aside" aria-label="초기 설정 진행">
          <NowRail data={data} />
        </Card>
        {open ? (
          <Card>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1, ...KO_WORD_BREAK }}>
              아래 순서는 의존 순서입니다. 앞 항목이 끝나야 뒤 항목이 실제로 동작합니다.
            </Typography>
            <Box component="ul" sx={{ m: 0, p: 0 }}>
              {items.map((item) => (
                item.state === "done"
                  ? <DoneItem key={item.key} item={item} />
                  : <SetupItem key={item.key} item={item} isNext={item.key === data.next_key} />
              ))}
            </Box>
          </Card>
        ) : null}
      </Box>
    </Box>
  );
}

export default SetupWizard;
