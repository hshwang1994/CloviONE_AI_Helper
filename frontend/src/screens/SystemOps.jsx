import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge, Button, Callout, Card, ErrorState, FormModal, OverflowMenu, PageHeader,
  SectionTitle, Skeleton, useConfirm, useToast,
} from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";

/* 운영 콘솔 - OS와 서비스 (§S, 9-6/9-7/9-8 · 지시 33 · 34 · 43).
 *
 * ## 이 화면이 하는 일과 안 하는 일
 *
 * 웹 프로세스는 하드닝돼 있어 `/etc` 를 쓸 수 없다. 실제 변경은 root 로 도는 특권 헬퍼가
 * **정해진 목록의 동작만** 수행한다(app/sysops/actions.py). 이 화면은 그 목록을 그리고,
 * 결과를 그대로 보여 준다.
 *
 * ## 버튼을 누르기 전에 지금 값을 안다 (지시 33)
 *
 * 예전에는 `변경` 이라는 카드 안에 기능명 버튼 여섯이 한 줄로 늘어서 있었다 - `타임존 수정`,
 * `DNS 서버`, `아웃바운드 프록시`… 지금 타임존이 무엇인지는 **다른 카드**에 있었고, DNS 와
 * 프록시는 어디에도 없었다. 그래서 이 화면은 "무엇을 바꿀 수 있는가"만 말하고 "무엇이
 * 설정돼 있는가"는 말하지 않았다.
 *
 * 항목마다 **이름 · 지금 값 · 그것이 무엇인지 · 바꾸는 동작**을 한 줄에 묶는다. 지금 값을
 * 읽을 수 없는 항목(DNS·프록시)은 **모른다고 말한다** - 빈칸으로 두면 "설정 안 됨"으로
 * 읽힌다. 도우미의 `system.info` 가 그 둘을 아직 안 주기 때문이고, 그 사실 자체가 정보다.
 *
 * ## 재시작은 설정 변경과 같은 무게가 아니다 (지시 43)
 *
 * 서비스 다섯이 각자 오른쪽에 `재시작` 버튼을 하나씩 달고 일렬로 서 있었다. 그 줄에서
 * 웹 서버 재시작과 이름 풀이 재시작이 같은 크기, 같은 색, 같은 자리였다. 재시작은
 * **서비스 영향** 등급이라 넘침 메뉴로 내리고, 실행 중이 아닌 서비스에서만 앞으로 꺼낸다
 * (그때는 그것이 그 줄에서 해야 할 일이다).
 *
 * ## 도우미가 없는 것은 오류가 아니라 상태다
 *
 * 개발 머신·컨테이너·도우미를 안 깐 설치가 전부 정상이다. 그때 이 화면은 **빈 화면이나
 * 오류가 아니라** "무엇이 없고 어떻게 하면 되는지" 를 말한다. 그리고 **절대 성공한 척하지
 * 않는다** - 사용자가 타임존을 바꿨다고 믿고 떠나는 것이 가장 나쁜 실패다.
 *
 * ## 되돌아간 시도를 숨기지 않는다
 *
 * 헬퍼는 실패하면 백업으로 원복하고 `rolled_back` 을 준다. 그걸 "실패했습니다" 로만 뭉개면
 * 사용자는 시스템이 반쯤 바뀐 것은 아닌지 알 수 없다. 되돌아갔다는 사실 자체가 정보다.
 */

const UNIT_LABELS = {
  "clovirone-web-assistant.service": "웹 서버",
  "clovirone-web-worker.service": "백그라운드 워커",
  "nginx.service": "웹 프록시(nginx)",
  "systemd-timesyncd.service": "시각 동기화",
  "systemd-resolved.service": "이름 풀이(DNS)",
};

const UNIT_ROLES = {
  "clovirone-web-assistant.service": "이 화면을 포함해 포털 웹 요청을 처리합니다.",
  "clovirone-web-worker.service": "동기화, 메일 발송, 예약 실행을 뒤에서 처리합니다.",
  "nginx.service": "바깥에서 들어오는 요청을 받아 포털로 넘깁니다.",
  "systemd-timesyncd.service": "서버 시각을 표준 시각에 맞춥니다.",
  "systemd-resolved.service": "도메인 이름을 주소로 바꿉니다.",
};

const HELP = "이 서버의 운영체제 설정과 서비스 상태를 봅니다. 실제 변경은 서버에 설치된 시스템 설정 도우미가 정해진 동작만 수행합니다.";

// 이 화면에서 다루는 동작. 헬퍼의 표가 정본이고 여기서는 **그리는 순서와 폼**만 정한다.
// 헬퍼가 모르는 동작은 서버가 404 로 거절하므로, 여기 목록이 낡아도 조용히 통하지 않는다.
const FORMS = {
  "timezone.set": {
    title: "타임존 수정",
    fields: [{ name: "timezone", label: "타임존", required: true,
               help: "예: Asia/Seoul. 서버가 아는 이름만 받습니다." }],
  },
  "ntp.set": {
    title: "시각 동기화(NTP) 서버",
    fields: [
      { name: "enabled", label: "사용", type: "checkbox",
        help: "비활성화하면 지정을 해제하고 배포판 기본값으로 돌아갑니다." },
      { name: "servers", label: "서버 (쉼표로 구분)",
        help: "예: kr.pool.ntp.org, 10.0.0.5", showIf: (v) => !!v.enabled },
    ],
  },
  "hostname.set": {
    title: "호스트 이름 / FQDN",
    fields: [
      { name: "hostname", label: "호스트 이름", required: true, help: "점 없는 짧은 이름입니다." },
      { name: "fqdn", label: "FQDN", help: "비워 두면 짧은 이름만 설정합니다. 첫 부분이 위 이름과 같아야 합니다." },
    ],
  },
  "dns.set": {
    title: "DNS 서버",
    fields: [
      { name: "enabled", label: "사용", type: "checkbox",
        help: "비활성화하면 지정을 해제합니다." },
      { name: "servers", label: "서버 주소 (쉼표로 구분)",
        help: "이름이 아니라 IP 주소만 받습니다. DNS 를 설정하는 중이라 이름을 풀 방법이 없습니다.",
        showIf: (v) => !!v.enabled },
      { name: "search", label: "검색 도메인", showIf: (v) => !!v.enabled },
    ],
  },
  "proxy.set": {
    title: "아웃바운드 프록시",
    fields: [
      { name: "enabled", label: "사용", type: "checkbox" },
      { name: "url", label: "프록시 주소",
        help: "예: http://proxy.example.com:3128. 아이디와 비밀번호는 넣을 수 없습니다.",
        showIf: (v) => !!v.enabled },
      { name: "no_proxy", label: "예외 (쉼표로 구분)", showIf: (v) => !!v.enabled },
    ],
  },
  "cert.install": {
    title: "TLS 인증서 교체",
    size: "lg",
    fields: [
      { name: "certificate", label: "인증서 (PEM)", type: "textarea", required: true },
      { name: "private_key", label: "개인키 (PEM)", type: "textarea", required: true,
        help: "저장한 뒤 다시 보여 주지 않습니다." },
    ],
  },
};

// 쉼표로 나눈 목록을 배열로. 빈 칸은 버린다 - "10.0.0.1, " 처럼 끝에 쉼표가 남는 일이 흔하다.
function splitList(value) {
  return String(value || "").split(",").map((s) => s.trim()).filter(Boolean);
}

export function buildParams(action, values) {
  if (action === "ntp.set" || action === "dns.set") {
    const enabled = !!values.enabled;
    if (!enabled) return { enabled: false };
    const out = { enabled: true, servers: splitList(values.servers) };
    if (action === "dns.set" && values.search) out.search = values.search;
    return out;
  }
  if (action === "proxy.set") {
    if (!values.enabled) return { enabled: false };
    const out = { enabled: true, url: values.url };
    if (values.no_proxy) out.no_proxy = values.no_proxy;
    return out;
  }
  if (action === "hostname.set") {
    const out = { hostname: values.hostname };
    // 빈 문자열을 보내면 서버가 "FQDN 이 비었다" 로 거절한다. 안 보내는 것과 빈 값은 다르다.
    if (values.fqdn) out.fqdn = values.fqdn;
    return out;
  }
  return { ...values };
}

/** 결과 한 줄. 되돌아간 시도를 성공처럼도 단순 실패처럼도 보이지 않게 한다. */
export function outcomeText(result) {
  if (!result) return "";
  if (!result.available) return result.detail || "시스템 설정 도우미를 쓸 수 없습니다.";
  if (result.ok) return result.detail || "적용했습니다.";
  if (result.rolled_back) {
    return (result.detail || "적용하지 못했습니다.") + " 원래 설정으로 되돌렸습니다.";
  }
  return result.detail || "적용하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

/** 지금 값을 못 읽는 항목은 **모른다고** 말한다. 빈칸은 "설정 안 됨"으로 읽힌다. */
const UNKNOWN = "서버에서만 확인할 수 있습니다";

export function certificateText(cert) {
  if (!cert || !cert.known) return "확인하지 못했습니다";
  const days = cert.days_remaining;
  const life = days == null ? "만료일을 읽지 못했습니다"
    : days < 0 ? "이미 만료되었습니다"
    : days === 0 ? "오늘 만료됩니다"
    : `만료까지 ${days}일 남았습니다`;
  return cert.self_signed ? life + ", 자체 서명 인증서입니다" : life;
}

/** 설정 한 줄 — 이름 · 지금 값 · 무엇인지 · 바꾸는 동작 (지시 32 · 33 · 45). */
function SettingRow({ label, value, description, tone, action, last }) {
  return (
    <Box
      /* 줄 하나가 한 항목이라는 사실을 시험이 붙잡을 자리. 라벨에서 부모를 몇 번 거슬러
         올라가는 식으로 찾으면 안쪽 배치를 조금만 바꿔도 시험이 깨진다. */
      className="k-settingrow"
      sx={{
        display: "flex", alignItems: "flex-start", gap: 2, flexWrap: "wrap",
        py: 1.75, borderBottom: last ? 0 : 1, borderColor: "divider",
      }}
    >
      <Box sx={{ flex: "1 1 22rem", minWidth: 0, display: "grid", gap: 0.25 }}>
        <Typography component="div" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
          {label}
        </Typography>
        <Typography
          component="div"
          color={tone === "muted" ? "text.faint" : "text.primary"}
          sx={{ fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}
        >
          {value}
        </Typography>
        {description ? (
          <Typography component="div" color="text.secondary" sx={{ fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }}>
            {description}
          </Typography>
        ) : null}
      </Box>
      {action ? <Box sx={{ flexShrink: 0, pt: 0.25 }}>{action}</Box> : null}
    </Box>
  );
}

/** 서비스 한 줄 — 이름 · 지금 상태 · 무엇을 하는 서비스인지 · 가능한 동작. */
function ServiceRow({ unit, state, onControl, disabled, last }) {
  const good = state === "active";
  return (
    <SettingRow
      last={last}
      label={UNIT_LABELS[unit] || unit}
      value={<Badge value={good ? "실행 중" : state || "알 수 없음"} kind={good ? "ok" : "warn"} />}
      description={UNIT_ROLES[unit]}
      action={good ? (
        /* 재시작은 서비스 영향 등급이다(지시 43) - 실행 중인 서비스에서는 앞줄에 두지 않는다.
           멈춰 있는 서비스에서는 그것이 이 줄에서 할 일이라 버튼으로 꺼낸다. */
        <OverflowMenu
          ariaLabel={(UNIT_LABELS[unit] || unit) + " 더 보기"}
          items={[{ key: "restart", label: "재시작", tone: "danger", disabled, onClick: () => onControl(unit, "restart") }]}
        />
      ) : (
        <Button size="sm" disabled={disabled} onClick={() => onControl(unit, "restart")}>재시작</Button>
      )}
    />
  );
}

// PA-RC-0017: embedded(SettingsShell.jsx의 'OS와 서비스 동작' 탭)일 땐 자체 PageHeader를
// 그리지 않는다 — 이 화면은 탭 하나를 통째로 차지해 SettingsShell의 바깥 PageHeader(tab=
// "OS와 서비스 동작")가 이미 제목을 보여준다, 안에서 또 그리면 h1이 두 개가 된다.
export function SystemOps({ embedded = false } = {}) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [openAction, setOpenAction] = React.useState(null);
  const [lastResult, setLastResult] = React.useState(null);

  const state = useQuery({
    queryKey: ["system-ops"],
    queryFn: () => api("/api/admin/system"),
  });

  const run = useMutation({
    mutationFn: ({ action, params }) =>
      api("/api/admin/system/" + action, { method: "POST", body: { params } }),
    onSuccess: (result) => {
      setLastResult(result);
      // 성공이든 실패든 상태를 다시 읽는다. 실패해도 그 사이 무언가 바뀌었을 수 있고,
      // 화면이 옛 값을 들고 있으면 사용자가 그것을 현재 상태로 읽는다.
      qc.invalidateQueries({ queryKey: ["system-ops"] });
      // useToast()는 {success, error} 메서드를 가진 객체가 아니라 (message, kind) 두 인자를
      // 받는 함수 하나다(kit.jsx ToastCtx.Provider value={push}) — 이 앱의 다른 모든 화면과
      // 같은 호출 모양을 쓴다. toast[...](...)/toast.error(...)로 부르면 존재하지 않는
      // 메서드를 호출하는 셈이라 TypeError로 죽어, 이 화면의 모든 쓰기 작업(재시작, 타임존
      // 변경 등)이 결과를 토스트로 전혀 알리지 못했다.
      toast(outcomeText(result), result && result.ok ? "success" : "error");
    },
    onError: (err) => toast((err && err.message) || "요청을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.", "error"),
  });

  /* 헤더까지 포함해 **화면 전체**가 아직 없다 - 회색 줄만 그리면 도착하는 순간 제목·본문이
     한꺼번에 튀어 들어온다. 들어올 배치를 미리 잡아 준다(지시 20). */
  if (state.isLoading) return <Skeleton kind="page" lines={4} />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.refetch} />;

  const data = state.data || {};
  const info = data.info || {};
  const units = info.units || {};
  const usable = !!data.available;
  const known = (value) => (usable && value ? value : usable ? "확인하지 못했습니다" : UNKNOWN);

  const submit = async (action, values) => {
    const params = buildParams(action, values);
    if (action === "cert.install") {
      // useConfirm()은 (message, opts) 시그니처다(kit.jsx ConfirmProvider) — opts는
      // {title, danger, confirmLabel}만 읽고 message는 문자열이어야 <Typography>가 그대로
      // 그린다. 여기서 예전처럼 {title, body} 객체 하나만 넘기면 opts가 undefined가 되어
      // title이 항상 기본값 "확인"으로 뭉개지고, message 자리에 들어간 객체를 그대로
      // <Typography>{state.message}</Typography>에 그리려다 "Objects are not valid as a
      // React child"로 렌더 자체가 죽는다 — 인증서 교체처럼 되돌릴 수 없는 작업의 확인
      // 대화상자가 열리지 않는 셈이다.
      const ok = await confirm(
        "검사에 실패하면 원래 인증서로 되돌립니다. 성공하면 nginx 를 다시 읽습니다.",
        { title: "인증서를 교체할까요?" },
      );
      if (!ok) return;
    }
    await run.mutateAsync({ action, params });
    setOpenAction(null);
  };

  const control = async (unit, verb) => {
    // 위 submit()의 cert.install과 같은 이유 — 문자열 message + opts 두 인자로 호출한다.
    const ok = await confirm(
      "재시작하는 동안 그 기능이 잠시 멈춥니다.",
      { title: (UNIT_LABELS[unit] || unit) + "를 재시작할까요?" },
    );
    if (ok) run.mutate({ action: "service.control", params: { unit, verb } });
  };

  // 헬퍼가 아는 동작만 그린다. 이름 하나에 줄 하나 — `변경` 카드에 버튼을 몰아 두지 않는다.
  const can = (name) => (data.actions || []).some((a) => a.name === name);
  const changeButton = (name, label) => (
    can(name) && FORMS[name] ? (
      <Button size="sm" disabled={!usable || run.isPending} onClick={() => setOpenAction(name)}>
        {label || "수정"}
      </Button>
    ) : null
  );

  const rows = [
    {
      key: "hostname", label: "호스트 이름",
      value: known(info.hostname),
      tone: usable && info.hostname ? undefined : "muted",
      description: "이 서버가 자신을 부르는 이름입니다. 인증서와 메일 발신 주소가 이 이름을 씁니다.",
      action: changeButton("hostname.set"),
    },
    {
      key: "timezone", label: "타임존",
      value: known(info.timezone),
      tone: usable && info.timezone ? undefined : "muted",
      description: "예약 실행과 로그 시각의 기준입니다. 포털 화면의 시각 표시와는 별개입니다.",
      action: changeButton("timezone.set"),
    },
    {
      key: "ntp", label: "시각 동기화",
      value: !usable ? UNKNOWN
        : info.ntp_synchronized === "yes" ? "표준 시각에 맞춰져 있습니다"
        : info.ntp_synchronized === "no" ? "맞춰지지 않았습니다"
        : "확인하지 못했습니다",
      tone: usable && info.ntp_synchronized === "yes" ? undefined : "muted",
      description: "서버 시각이 어긋나면 예약 실행 시각과 인증서 검증이 함께 어긋납니다.",
      action: changeButton("ntp.set", "서버 지정"),
    },
    {
      key: "dns", label: "DNS 서버",
      value: UNKNOWN,
      tone: "muted",
      description: "도메인 이름을 주소로 바꿀 때 물어보는 서버입니다. 지금 지정된 값은 도우미가 아직 알려 주지 않습니다.",
      action: changeButton("dns.set"),
    },
    {
      key: "proxy", label: "아웃바운드 프록시",
      value: UNKNOWN,
      tone: "muted",
      description: "포털이 바깥(Notion 등)으로 나갈 때 거치는 서버입니다. 지금 지정된 값은 도우미가 아직 알려 주지 않습니다.",
      action: changeButton("proxy.set"),
    },
    {
      key: "cert", label: "TLS 인증서",
      value: certificateText(data.certificate),
      tone: data.certificate && data.certificate.known ? undefined : "muted",
      description: "브라우저가 이 서버를 믿게 하는 인증서입니다. 교체는 검사에 실패하면 자동으로 되돌립니다.",
      action: changeButton("cert.install", "교체"),
    },
  ];

  const unitNames = Object.keys(units);

  return (
    <Box className="c-screen">
      {embedded ? null : <PageHeader area="운영" title="OS와 서비스" help={HELP} />}

      {!usable && (
        /* 도우미가 없는 것은 오류가 아니라 이 서버의 상태다 - 사람이 할 일이 있으므로 조용한
           안내(info)가 아니라 주의로 말하되, 오류(danger)로는 말하지 않는다(D-155). */
        <Callout tone="warn">
          {data.detail || "시스템 설정 도우미를 쓸 수 없습니다."} 서버에 시스템 설정 도우미를
          설치하고 실행하면 이 화면의 값을 읽고 바꿀 수 있습니다. 그 전까지 아래 값은 읽지
          못하며, 여기서 바꾼 것은 아무것도 적용되지 않습니다.
        </Callout>
      )}

      {lastResult && lastResult.rolled_back && (
        <Callout tone="danger">
          적용에 실패해 원래 설정으로 되돌렸습니다. {lastResult.detail}
        </Callout>
      )}

      <Card sx={{ mt: 2, px: 2, py: 0.5 }}>
        <SectionTitle title="시스템 설정" component="h2" sx={{ pt: 1.5 }} />
        {rows.map((r, i) => (
          <SettingRow
            key={r.key} label={r.label} value={r.value} description={r.description}
            tone={r.tone} action={r.action} last={i === rows.length - 1}
          />
        ))}
      </Card>

      <Card sx={{ mt: 2, px: 2, py: 0.5 }}>
        <SectionTitle title="서비스" component="h2" sx={{ pt: 1.5 }} />
        {usable && unitNames.length > 0 ? (
          unitNames.map((unit, i) => (
            <ServiceRow key={unit} unit={unit} state={units[unit]} onControl={control}
                        disabled={run.isPending} last={i === unitNames.length - 1} />
          ))
        ) : (
          <Typography color="text.secondary" sx={{ py: 2 }}>
            {usable ? "서비스 상태를 읽지 못했습니다. 새로고침한 뒤 다시 시도해 주세요." : "도우미가 없어 읽지 못했습니다."}
          </Typography>
        )}
      </Card>

      {openAction && (
        <FormModal
          open
          title={FORMS[openAction].title}
          size={FORMS[openAction].size}
          fields={FORMS[openAction].fields}
          submitLabel="적용"
          onSubmit={(values) => submit(openAction, values)}
          onClose={() => setOpenAction(null)}
        />
      )}
    </Box>
  );
}

export default SystemOps;
