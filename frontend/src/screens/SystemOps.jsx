import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge, Button, Callout, Card, ErrorState, FormModal, PageHeader, Skeleton,
  useConfirm, useToast,
} from "../ui/kit.jsx";

/* 운영 콘솔 - 시스템 설정 (§S, 9-6/9-7/9-8).
 *
 * ## 이 화면이 하는 일과 안 하는 일
 *
 * 웹 프로세스는 하드닝돼 있어 `/etc` 를 쓸 수 없다. 실제 변경은 root 로 도는 특권 헬퍼가
 * **정해진 목록의 동작만** 수행한다(app/sysops/actions.py). 이 화면은 그 목록을 그리고,
 * 결과를 그대로 보여 준다.
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

function UnitRow({ unit, state, onControl, disabled }) {
  const good = state === "active";
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 0.75 }}>
      <Typography sx={{ minWidth: 160 }}>{UNIT_LABELS[unit] || unit}</Typography>
      <Badge value={good ? "실행 중" : state || "알 수 없음"} kind={good ? "ok" : "warn"} />
      <Box sx={{ flex: 1 }} />
      <Button size="small" disabled={disabled} onClick={() => onControl(unit, "restart")}>
        재시작
      </Button>
    </Box>
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

  if (state.isLoading) return <Skeleton lines={6} />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.refetch} />;

  const data = state.data || {};
  const info = data.info || {};
  const units = info.units || {};
  const usable = !!data.available;

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
      { title: (UNIT_LABELS[unit] || unit) + " 를 재시작할까요?" },
    );
    if (ok) run.mutate({ action: "service.control", params: { unit, verb } });
  };

  return (
    <Box className="c-screen">
      {embedded ? null : <PageHeader area="운영" title="시스템 설정" />}

      {!usable && (
        <Callout tone="warn">
          {data.detail || "시스템 설정 도우미를 쓸 수 없습니다."} 서버에서
          clovirone-privhelper 서비스를 설치하고 실행하면 이 화면의 기능을 쓸 수 있습니다.
          그 전까지 아래 값은 읽지 못하며, 여기서 바꾼 것은 아무것도 적용되지 않습니다.
        </Callout>
      )}

      {lastResult && lastResult.rolled_back && (
        <Callout tone="warn">
          적용에 실패해 원래 설정으로 되돌렸습니다. {lastResult.detail}
        </Callout>
      )}

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>시스템 정보</Typography>
        {usable ? (
          <Box sx={{ display: "grid", gap: 0.5 }}>
            <Typography>호스트 이름: {info.hostname || "확인하지 못했습니다"}</Typography>
            <Typography>타임존: {info.timezone || "확인하지 못했습니다"}</Typography>
            <Typography>
              시각 동기화: {info.ntp_synchronized === "yes" ? "맞춰져 있습니다"
                : info.ntp_synchronized === "no" ? "맞춰지지 않았습니다"
                : "확인하지 못했습니다"}
            </Typography>
          </Box>
        ) : (
          <Typography color="text.secondary">도우미가 없어 읽지 못했습니다.</Typography>
        )}
      </Card>

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>서비스</Typography>
        {usable && Object.keys(units).length > 0 ? (
          Object.keys(units).map((unit) => (
            <UnitRow key={unit} unit={unit} state={units[unit]}
                     onControl={control} disabled={run.isPending} />
          ))
        ) : (
          <Typography color="text.secondary">
            {usable ? "서비스 상태를 읽지 못했습니다. 새로고침한 뒤 다시 시도해 주세요." : "도우미가 없어 읽지 못했습니다."}
          </Typography>
        )}
      </Card>

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>변경</Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          {(data.actions || [])
            .filter((a) => a.mutating && FORMS[a.name])
            .map((a) => (
              <Button key={a.name} disabled={!usable || run.isPending}
                      onClick={() => setOpenAction(a.name)}>
                {FORMS[a.name].title}
              </Button>
            ))}
        </Box>
        {!usable && (
          <Typography color="text.secondary" sx={{ mt: 1 }}>
            도우미가 없어 지금은 바꿀 수 없습니다.
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
