import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import {
  PageHeader, Card, Badge, Button, Callout, Skeleton, ErrorState, EmptyState,
  DotLabel, SectionTitle, useToast,
} from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { GRID_GAP } from "../ui/density.js";

/* 최초 실행 셋업 마법사 (9-3, P3 · 계획 3.5, D-520).
 *
 * ## 이 화면이 하는 일과 하지 않는 일
 *
 * **하는 일**: 서버가 계산한 남은 항목을 **그 순서 그대로** 보여 주고, 막힌 항목이 무엇
 * 때문에 막혔는지 말하고, 각 항목을 실제로 고칠 수 있는 화면으로 보낸다. 선택 항목(메일, AI)은
 * 「사용하지 않음」으로 표시할 수 있다 - 그 한 값만 여기서 바꾼다(`setup_optional_choices`).
 *
 * **하지 않는 일**: 다른 설정은 여기서 바꾸지 않는다. 조직, 부서, 연동, AI 설정에는 이미 각자의
 * 화면이 있고 거기에는 검증과 감사와 되돌리기가 붙어 있다. 마법사가 지름길을 하나 더 내면
 * 그 세 가지가 없는 두 번째 쓰기 경로가 생긴다.
 *
 * ## 필수와 선택
 *
 * 설치가 끝났는지는 **필수 항목**(관리자 계정, 조직과 부서, TLS)만 본다. 메일과 AI 를 쓰지 않는 설치도 정상 설치다 -
 * 선택 항목은 아래 구역에 따로 서고 남아 있어도 「끝났다」를 막지 않는다.
 *
 * ## 폭
 *
 * 예전에는 판 폭을 70rem 으로 묶어(`READ_COLUMN`) 넓은 화면의 오른쪽 3분의 1 이 비었다. 이제 항목 하나가 카드 하나이고
 * 카드들이 격자로 선다 - 긴 줄은 카드 폭 안에서 접히고 화면은 끝까지 쓴다(계획 2.1).
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
const STATE_LABEL = { done: "됨", todo: "안 됨", unknown: "확인 불가", skipped: "사용하지 않음" };
/* 상태는 `Badge` 다(분류라면 `Tag`). 예전에는 여기서 알약을 손으로 그렸는데(테두리 + 색 글자 +
   `RADIUS.full`), 그 알약은 제품의 다른 어떤 상태 표시와도 모양이 달랐다. */
const STATE_KIND = { done: "ok", todo: "warn", unknown: "info", skipped: "neutral" };

/* 한 문장을 네 자리(권한 없음·로딩·오류·본문)가 각자 복사해 들고 있었다. */
const DESCRIPTION = "처음 설치할 때 필요한 설정 중 아직 안 끝난 항목을 순서대로 안내합니다.";

const CHOICES_SETTING = "/api/admin/settings/setup_optional_choices";

/* 항목마다 "그래서 어디로 가면 되는가" - 서버가 링크를 주지 않을 때(옛 서버)만 쓰는 대체 표다.
 *
 * ⚠️ **여기 적는 경로는 실제로 라우팅되는 것이어야 한다.** 죽은 링크는 안내가 아니라
 * 막다른 길이고, 이 화면은 막다른 길을 없애려고 만든 것이다. setup-wizard.test.jsx 가
 * 모든 값이 AdminRoutes.jsx 의 명시 경로이거나 registry.js 의 키인지 확인한다. 서버가 주는 링크(`app/setup/probes.py`)도
 * 같은 경로들이다. */
export const SETUP_LINKS = {
  admin_account: { href: "#/users", label: "사용자 화면 열기" },
  mail: { href: "#/settings?setting=smtp", label: "메일 설정 열기" },
  organization: { href: "#/departments", label: "부서 화면 열기" },
  llm: { href: "#/ai-connection", label: "AI 연결 열기" },
  integrations: { href: "#/diagnostics", label: "진단에서 연동 상태 보기" },
  tls: { href: "#/diagnostics", label: "진단에서 인증서 확인" },
};

/** 항목의 링크 - 서버가 준 것이 먼저다(상태마다 가야 할 곳이 다르다: 메일이 비었으면 설정 줄, 실패하면 메일 발송 화면). */
export function linkOf(item) {
  if (item && item.href && item.link_label) return { href: item.href, label: item.link_label };
  return (item && SETUP_LINKS[item.key]) || null;
}

/* 끝난 항목과 사용하지 않는 항목은 **한 줄 카드**다(D-501 — 끝남 · 정상은 한 줄, 남은 일 · 이상만 펼친다). 이름 · 상태 ·
   지금 상태 한 문장이 한 줄에 선다. 사용하지 않는 항목에는 「사용하기로 바꾸기」가 함께 선다. */
function CompactItem({ item, position, onChoice, choosing }) {
  const skipped = item.state === "skipped";
  return (
    <Card
      component="li"
      data-setup-key={item.key}
      data-testid={"setup-item-" + item.key}
      data-setup-state={item.state}
      sx={{ listStyle: "none", display: "grid", gap: 0.5, alignContent: "start" }}
    >
      <Box sx={{ display: "flex", alignItems: "baseline", columnGap: 1, rowGap: 0.25, flexWrap: "wrap" }}>
        <Typography component="span" variant="caption" color="text.secondary">{position}</Typography>
        <Typography component="h2" variant="body1" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
          {item.label}
        </Typography>
        <Badge value={STATE_LABEL[item.state] || item.state} kind={STATE_KIND[item.state]} />
      </Box>
      {item.detail ? (
        <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>{item.detail}</Typography>
      ) : null}
      {skipped && item.optional_choice ? (
        <Box>
          <Button size="sm" disabled={choosing} onClick={() => onChoice(item, "use")}>사용하기로 바꾸기</Button>
        </Box>
      ) : null}
    </Card>
  );
}

/* 남은 항목 하나 — 이름 · 상태 · 지금 상태 · 할 일(또는 확인할 것 · 막힌 까닭) · 그것이 왜 필요한가 · 고치는 화면.
 *
 * **지금 할 차례인 항목은 할 일과 이동 링크를 여기서 말하지 않는다** — 맨 위 「지금 할 차례」 판이 그 둘을 이 화면의
 * 주 동작으로 든다(D-501 — 한 사실은 한 곳). 목록의 그 카드에는 「지금 할 차례」 표지가 서서 위 판과 같은 항목임을 잇는다. */
function SetupItem({ item, isNext, position, onChoice, choosing }) {
  const link = linkOf(item);
  const blocked = item.blocked_by != null;
  const canSkip = item.optional_choice && item.choice !== "unused" && item.configured === false;
  return (
    <Card
      component="li"
      data-setup-key={item.key}
      data-testid={"setup-item-" + item.key}
      data-setup-state={item.state}
      sx={{ listStyle: "none", display: "grid", gap: 0.75, alignContent: "start", opacity: blocked ? 0.75 : 1 }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography component="span" variant="caption" color="text.secondary">{position}</Typography>
        {/* 항목 제목은 h2 그대로다(h1 바로 아래, 판에 따로 제목이 없다). 크기만 본문 단계로 내렸다. */}
        <Typography component="h2" variant="body1" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
          {item.label}
        </Typography>
        <Badge value={STATE_LABEL[item.state] || item.state} kind={STATE_KIND[item.state]} />
        {/* 목록 안에서 면 배지를 세우지 않는다(RULES §2) — 「지금 할 차례」는 점 + 낱말을 600 으로 세운다. */}
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
      {item.checked_at ? (
        <Typography variant="caption" color="text.secondary">마지막 확인 {fmtDateTime(item.checked_at)}</Typography>
      ) : null}
      {(link && !isNext) || canSkip ? (
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
          {link && !isNext ? (
            <Link href={link.href} underline="hover" variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold }}>
              {link.label}
            </Link>
          ) : null}
          {canSkip ? (
            <Button size="sm" disabled={choosing} onClick={() => onChoice(item, "unused")}>사용하지 않음으로 표시</Button>
          ) : null}
        </Box>
      ) : null}
    </Card>
  );
}

/* 사람이 할 일 한 줄 — 「안 됨」은 할 일이고 「확인 불가」는 확인할 것이다. 같은 말로 부르면 사람이 할 일과 물어볼
   일이 뒤섞인다. 목록의 카드와 맨 위 판이 이 한 부품을 쓴다. */
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

/** 진행을 말하는 한 문장 — 「필수 항목 3개 중 2개가 끝났습니다. 직접 할 일이 1개 남았습니다.」
 *
 * 설치가 끝났는지는 필수 항목이 정하므로(D-520) 문장도 필수 항목을 센다. 선택 항목은 남은 수만 덧붙인다. */
export function setupProgressText(data) {
  const items = (data && data.items) || [];
  const required = items.filter((i) => i.required !== false);
  const done = required.filter((i) => i.state === "done").length;
  const todo = required.filter((i) => i.state === "todo").length;
  const unknown = required.filter((i) => i.state === "unknown").length;
  const optional = ((data && data.optional_pending) || []).length;
  const head = done
    ? `필수 항목 ${required.length}개 중 ${done}개가 끝났습니다.`
    : `필수 항목 ${required.length}개 중 아직 끝난 항목이 없습니다.`;
  const rest = [todo ? `직접 할 일이 ${todo}개` : null, unknown ? `확인할 것이 ${unknown}개` : null].filter(Boolean);
  const tail = optional ? ` 선택 항목은 ${optional}개가 남아 있습니다.` : "";
  return (rest.length ? `${head} ${rest.join(", ")} 남았습니다.` : head) + tail;
}

/* **지금 할 차례** 판 — 목록 위에 전폭으로 선다.
 *
 * 다음 항목의 할 일과 그것을 고치는 화면으로 가는 단추가 이 화면의 주 동작이다(D-501 — 채움은 화면당 하나). 목록을 접어도
 * 이 판은 남는다. 필수 항목이 다 끝나면 설치가 끝났다는 문장과 설치 상태(`summary`)가 선다 - 선택 항목이 남았으면 다음
 * 차례로 그것을 안내한다. */
function NowRail({ data }) {
  const items = data.items || [];
  const next = items.find((i) => i.key === data.next_key) || null;
  const link = next ? linkOf(next) : null;
  return (
    <Box data-testid="setup-summary" sx={{ display: "grid", gap: 1.5, justifyItems: "stretch" }}>
      {data.complete ? (
        <Callout tone="success">
          필수 설정이 모두 끝났습니다. {data.summary || "정상 설치입니다."}
        </Callout>
      ) : null}
      {next ? (
        <>
          <SectionTitle spacing="none"
            component="h2"
            title="지금 할 차례"

            action={link ? <Button variant="primary" href={link.href}>{link.label}</Button> : null}
          />
          <Box data-setup-now={next.key} sx={{ display: "grid", gap: 0.5 }}>
            <Typography variant="body1" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>{next.label}</Typography>
            <NextStep item={next} />
          </Box>
        </>
      ) : null}
      <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{setupProgressText(data)}</Typography>
    </Box>
  );
}

/* 항목 카드의 격자. 카드 하나의 바닥 폭(22rem)을 넘는 만큼 열이 는다 - 넓은 화면은 두세 열, 좁은 화면은 한 열이다. */
const ITEM_GRID = {
  m: 0, p: 0, display: "grid", gap: GRID_GAP, alignItems: "start",
  gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 22rem), 1fr))",
};

function ItemSection({ title, items, all, data, onChoice, choosing }) {
  if (!items.length) return null;
  return (
    <Box component="section" aria-label={title} sx={{ display: "grid", gap: 1.5 }}>
      <SectionTitle spacing="none" component="h2" title={title}  />
      <Box component="ul" sx={ITEM_GRID}>
        {items.map((item) => {
          const position = `${all.indexOf(item) + 1}/${all.length}`;
          return item.state === "done" || item.state === "skipped"
            ? <CompactItem key={item.key} item={item} position={position} onChoice={onChoice} choosing={choosing} />
            : <SetupItem key={item.key} item={item} position={position} isNext={item.key === data.next_key}
              onChoice={onChoice} choosing={choosing} />;
        })}
      </Box>
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
  const qc = useQueryClient();
  const toast = useToast();

  const query = useQuery({
    queryKey: ["setup-checklist"],
    queryFn: () => api("/api/admin/setup/checklist"),
    enabled: allowed,
    retry: false,
  });

  /* 「사용하지 않음」은 선택 항목의 선택 한 값을 바꾼다(`setup_optional_choices`, system_admin 전용). 다른 항목의 선택은
     그대로 싣는다 - 한 항목만 보내면 나머지가 기본값으로 돌아간다. */
  const choose = useMutation({
    mutationFn: ({ item, value }) => {
      const current = Object.fromEntries(((query.data && query.data.items) || [])
        .filter((i) => i.optional_choice).map((i) => [i.optional_choice, i.choice || "use"]));
      return api(CHOICES_SETTING, { method: "PUT", body: { value: { ...current, [item.optional_choice]: value } } });
    },
    onSuccess: (_res, vars) => {
      toast(vars.value === "unused" ? vars.item.label + " 항목을 사용하지 않음으로 표시했습니다." : vars.item.label + " 항목을 다시 사용합니다.");
      qc.invalidateQueries({ queryKey: ["setup-checklist"] });
    },
    onError: (e) => toast((e && e.message) || "선택을 바꾸지 못했습니다.", "error"),
  });
  const onChoice = (item, value) => choose.mutate({ item, value });

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
  const required = items.filter((i) => i.required !== false);
  const optional = items.filter((i) => i.required === false);
  return (
    <Box className="c-screen">
      <PageHeader
        area="설정"
        title="초기 설정"
        description={DESCRIPTION}
        help="확인할 것은 이 서버가 스스로 판단할 수 없어 사람에게 묻는 항목입니다. 선택 항목은 쓰지 않는다면 사용하지 않음으로 표시할 수 있습니다."
        actions={
          <Button onClick={() => setOpen((v) => !v)}>
            {open ? "목록 접기" : "목록 펼치기"}
          </Button>
        }
      />
      {/* 「지금 할 차례」가 위, 항목이 아래다(D-501 — 머리 → 지금 할 일 → 목록). 폭은 묶지 않는다(계획 2.1). */}
      <Box sx={{ display: "grid", gap: GRID_GAP, gridTemplateColumns: "minmax(0, 1fr)", alignItems: "start" }}>
        <Card component="aside" aria-label="초기 설정 진행">
          <NowRail data={data} />
        </Card>
        {open ? (
          <>
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              항목은 의존 순서대로 섭니다. 앞 항목이 끝나야 뒤 항목이 실제로 동작합니다.
            </Typography>
            <ItemSection title="필수 항목" items={required} all={items} data={data} onChoice={onChoice} choosing={choose.isPending} />
            <ItemSection title="선택 항목" items={optional} all={items} data={data} onChoice={onChoice} choosing={choose.isPending} />
          </>
        ) : null}
      </Box>
    </Box>
  );
}

export default SetupWizard;
