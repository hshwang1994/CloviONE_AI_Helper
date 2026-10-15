import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { failureText } from "../lib/failure.js";
import {
  Badge, Button, Callout, Card, EmptyState, ErrorState, FormModal, OverflowMenu,
  Skeleton, useConfirm, useToast,
} from "../ui/kit.jsx";
import { SettingList, SettingRow } from "../ui/adminKit.jsx";
import { pairTracks } from "../ui/density.js";
import { ServiceAddressCard } from "./system/ServiceAddressCard.jsx";

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
 * 항목마다 **이름 · 지금 값 · 그것이 무엇인지 · 바꾸는 동작**을 한 줄에 묶는다. DNS · 프록시는
 * 도우미의 `system.info` 가 이 콘솔이 쓴 드롭인을 읽어 준다(`source`: console · unset · unreadable) —
 * 「지정하지 않음」과 「읽지 못함」은 다른 사실이라 따로 말한다. 빈칸으로 두면 "설정 안 됨"으로 읽힌다.
 *
 * ## 서비스 주소는 맨 위 한 판이다 (D-574)
 *
 * 대표 주소 · 지금 접속한 주소 · 별칭 · 인증서 · 확인 넷이 `system/ServiceAddressCard.jsx` 한 판에 선다.
 * 호스트 이름은 그것과 다른 값이다(이 서버가 자신을 부르는 이름) — 설명이 둘을 섞지 않는다.
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

/* 유닛 이름은 서버가 정한다(app/core/product.py). 여기 있는 것은 **그 이름에 붙는 우리말
   이름과 설명**뿐이고, 목록 자체는 서버 응답이 준다 — 여기 없는 유닛이 와도 화면은 원래
   이름을 그대로 보여 준다.

   이 표가 낡으면 조용히 틀린다: 응답의 유닛 이름과 안 맞으면 사용자는 «웹 서버» 대신
   `clovirassist-web.service` 를 보고, 장애 중에 그 화면을 읽는 사람에게는 그 차이가 크다.
   S4 가 slug 를 옮길 때 이 표만 옛 이름으로 남아 있었다. */
const UNIT_LABELS = {
  "clovirassist-web.service": "웹 서버",
  "clovirassist-worker.service": "백그라운드 작업",
  "clovirassist-worker-conversational.service": "대화형 작업",
  "clovirassist-scheduler.service": "예약 실행",
  "clovirassist-index.service": "검색 색인",
  "clovirassist-privhelper.service": "시스템 설정 도우미",
  "nginx.service": "웹 프록시(nginx)",
  "systemd-timesyncd.service": "시각 동기화",
  "systemd-resolved.service": "이름 풀이(DNS)",
};

const UNIT_ROLES = {
  "clovirassist-web.service": "이 화면을 포함해 포털 웹 요청을 처리합니다.",
  "clovirassist-worker.service": "메일 발송과 일괄 작업을 뒤에서 처리합니다.",
  "clovirassist-worker-conversational.service": "AI 도우미의 대화 요청을 처리합니다.",
  "clovirassist-scheduler.service": "예약된 작업을 정해진 시각에 시작합니다.",
  "clovirassist-index.service": "문서를 읽어 검색 색인을 갱신합니다.",
  "clovirassist-privhelper.service": "이 화면이 요청한 시스템 설정 변경만 대신 수행합니다.",
  "nginx.service": "바깥에서 들어오는 요청을 받아 포털로 넘깁니다.",
  "systemd-timesyncd.service": "서버 시각을 표준 시각에 맞춥니다.",
  "systemd-resolved.service": "도메인 이름을 주소로 바꿉니다.",
};

/* 도우미가 없을 때 서비스 한 줄의 설명 — 그 자리가 무엇을 다루는지만 말한다. 읽지 못한다는 사실은 안내 상자가 말한다. */
const SERVICES_ROLE = "웹 서버와 백그라운드 작업처럼 포털을 이루는 서비스가 실행 중인지 보고 재시작합니다.";
/* 도우미가 없을 때 서비스 주소 한 줄 — 무엇을 다루는 자리인지만 말한다(D-574). */
const ADDRESS_ROLE = "알림 메일과 링크가 쓰는 대표 주소와 함께 쓰는 주소를 보고 바꿉니다.";

/* 이 탭의 `?` 도움말 — 그릇(`settings/SettingsShell.jsx`)이 제목 옆에 그린다(D-453).
   예전에는 어디에도 안 쓰이는 상수였다. */
export const HELP = "이 서버의 운영체제 설정과 서비스 상태를 봅니다. 실제 변경은 서버에 설치된 시스템 설정 도우미가 정해진 동작만 수행합니다.";

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

/** DNS · 프록시 줄의 값 — 이 콘솔이 쓴 드롭인을 읽은 결과(`system.info` 의 `dns` · `proxy`). 지정하지 않은 것과 읽지 못한 것을
 *  가른다. 도우미가 없으면 줄은 값 없이 선다(위 안내 상자가 한 번 말한다, D-501). */
export function dnsRow(dns) {
  if (!dns || dns.source === "unreadable") return { value: "확인하지 못했습니다", muted: true, note: null };
  if (dns.configured && (dns.servers || []).length) {
    return { value: dns.servers.join(", "), muted: false, note: dns.search ? `검색 도메인은 ${dns.search}입니다.` : null };
  }
  return { value: "지정하지 않음", muted: true, note: "이 화면에서 지정하지 않아 서버의 기본 설정을 씁니다." };
}

export function proxyRow(proxy) {
  if (!proxy || proxy.source === "unreadable") return { value: "확인하지 못했습니다", muted: true, note: null };
  if (proxy.configured && proxy.url) {
    return { value: proxy.url, muted: false, note: proxy.no_proxy ? `예외는 ${proxy.no_proxy}입니다.` : null };
  }
  return { value: "지정하지 않음", muted: true, note: "이 화면에서 지정하지 않아 바깥으로 곧바로 나갑니다." };
}

export function certificateText(cert) {
  if (!cert || !cert.known) return "확인하지 못했습니다";
  const days = cert.days_remaining;
  const life = days == null ? "만료일을 읽지 못했습니다"
    : days < 0 ? "이미 만료되었습니다"
    : days === 0 ? "오늘 만료됩니다"
    : `만료까지 ${days}일 남았습니다`;
  return cert.self_signed ? life + ", 자체 서명 인증서입니다" : life;
}

/* systemd 상태 낱말의 우리말 — 「inactive」 같은 원문이 값 자리에 그대로 섰다(캡처 m4-svc-2). 모르는 낱말은 원문 그대로 둔다. */
export const UNIT_STATE_WORD = {
  active: "실행 중", inactive: "멈춤", failed: "실패", activating: "시작하는 중", deactivating: "멈추는 중",
  reloading: "다시 읽는 중", unknown: "알 수 없음",
};

/** 서비스 한 줄 — 이름 · 지금 상태 · 무엇을 하는 서비스인지 · 가능한 동작. */
function ServiceRow({ unit, state, onControl, disabled, last }) {
  const good = state === "active";
  return (
    <SettingRow
      last={last}
      label={UNIT_LABELS[unit] || unit}
      value={<Badge value={UNIT_STATE_WORD[state] || state || "알 수 없음"} kind={good ? "ok" : "warn"} />}
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
// 그리지 않는다 — 이 화면은 탭 하나를 통째로 차지해 SettingsShell의 바깥 PageHeader(제목
// 「설정」, 그 아래 탭 줄)가 이미 제목을 보여준다, 안에서 또 그리면 h1이 두 개가 된다.
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
      // 적용했을 때만 토스트다. 못 적용한 결과는 본문 위 메시지 박스가 말한다(`opsNotice`).
      if (result && result.ok) toast(outcomeText(result), "success");
    },
  });
  /* 요청 실패 또는 「적용하지 못했다」는 결과 — 되돌린 경우는 아래 「원래 설정으로 되돌렸습니다」 상자가
     이미 말하므로 겹쳐 세우지 않는다. 다음 요청에서 걷힌다. */
  const opsNotice = failureText([run, "요청을 보내지 못했습니다. 잠시 후 다시 시도해 주세요."])
    || (run.isSuccess && lastResult && lastResult.available !== false && !lastResult.ok && !lastResult.rolled_back
      ? outcomeText(lastResult) : null);

  /* 헤더까지 포함해 **화면 전체**가 아직 없다 - 회색 줄만 그리면 도착하는 순간 제목·본문이
     한꺼번에 튀어 들어온다. 들어올 배치를 미리 잡아 준다(지시 20). */
  if (state.isLoading) return <Skeleton kind="page" lines={4} />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.refetch} />;

  const data = state.data || {};
  const info = data.info || {};
  const units = info.units || {};
  const usable = !!data.available;
  /* 도우미가 없으면 도우미가 읽어 주는 값은 줄에 서지 않는다(`null`) — 여섯 줄이 모두 「서버에서만 확인할 수 있습니다」를
     되풀이했다(D-501). 그 사실은 위 안내 상자가 한 번 말한다. 도우미가 있는데 값이 비었으면 「확인하지 못했습니다」다. */
  const known = (value) => (!usable ? null : value || "확인하지 못했습니다");

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
  // 도우미가 없으면 단추를 그리지 않는다 — 여섯 줄 모두 누를 수 없는 단추를 들고 있었고, 누를 수 없는 이유는 위 안내 상자
  // 한 곳이 말한다(D-501 — 한 사실은 한 곳). 도우미가 있는데 요청이 도는 중이면 꺼 둔다.
  const can = (name) => (data.actions || []).some((a) => a.name === name);
  const changeButton = (name, label) => (
    usable && can(name) && FORMS[name] ? (
      <Button size="sm" disabled={run.isPending} onClick={() => setOpenAction(name)}>
        {label || "수정"}
      </Button>
    ) : null
  );

  const dns = dnsRow(info.dns);
  const proxy = proxyRow(info.proxy);
  const rows = [
    {
      key: "hostname", label: "호스트 이름",
      value: known(info.hostname),
      tone: usable && info.hostname ? undefined : "muted",
      description: "이 서버가 자신을 부르는 이름입니다. 접속 주소, 인증서, 메일 서버 이름(HELO)과는 별개이며, 접속 주소는 위 「서비스 주소」에서, 메일 서버 이름은 메일 설정에서 정합니다.",
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
      value: !usable ? null
        : info.ntp_synchronized === "yes" ? "표준 시각에 맞춰져 있습니다"
        : info.ntp_synchronized === "no" ? "맞춰지지 않았습니다"
        : "확인하지 못했습니다",
      tone: usable && info.ntp_synchronized === "yes" ? undefined : "muted",
      description: "서버 시각이 어긋나면 예약 실행 시각과 인증서 검증이 함께 어긋납니다.",
      action: changeButton("ntp.set", "서버 지정"),
    },
    {
      /* 도우미가 이 콘솔이 쓴 드롭인을 읽어 준다(`dnsRow`). 도우미가 없으면 위 안내 상자가 말한다. */
      key: "dns", label: "DNS 서버",
      value: usable ? dns.value : null,
      tone: usable && !dns.muted ? undefined : "muted",
      description: ["도메인 이름을 주소로 바꿀 때 물어보는 서버입니다.", usable ? dns.note : null].filter(Boolean).join(" "),
      action: changeButton("dns.set"),
    },
    {
      key: "proxy", label: "아웃바운드 프록시",
      value: usable ? proxy.value : null,
      tone: usable && !proxy.muted ? undefined : "muted",
      description: ["포털이 바깥으로 나갈 때 거치는 서버입니다.", usable ? proxy.note : null].filter(Boolean).join(" "),
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

  /* 🔴 여기 `embedded ? null : <PageHeader area="운영" …>` 가 있었다. **도달할 수 없는
     갈래**다 — 이 화면의 옛 주소 `/system` 은 `/settings?tab=os` 로 보내는 리다이렉트가
     됐고(`app/AdminRoutes.jsx`), 그 뒤로 이 컴포넌트는 언제나 설정 껍데기 안에서
     `embedded` 로만 그려진다. 게다가 그 머리는 `area="운영"` 이라고 적고 있었는데 지금
     이 화면이 사는 사이드바 묶음은 **설정**이다 — 도달만 했으면 빵 부스러기가 틀린 자리를
     가리켰을 것이다. 껍데기가 이미 머리를 그린다(`settings/SettingsShell.jsx`).
     `.c-screen` 도 껍데기가 감싼다 — 여기서 또 감싸면 바깥 여백이 두 번 붙는다. */
  return (
    <>

      {!usable && (
        /* 도우미가 없는 것은 오류가 아니라 이 서버의 상태다 - 사람이 할 일이 있으므로 조용한
           안내(info)가 아니라 주의로 말하되, 오류(danger)로는 말하지 않는다(D-155).
           그 사실은 **여기 한 번**이다(D-501). 예전에는 아래 여섯 줄이 저마다 「서버에서만 확인할 수 있습니다」와 꺼진
           단추를 들고 있었고, 서비스 판도 「도우미가 없어 읽지 못했습니다」를 한 번 더 말했다. */
        <Callout tone="warn">
          {data.detail || "시스템 설정 도우미를 쓸 수 없습니다."} 서버에 시스템 설정 도우미를
          설치하고 실행하면 아래 설정과 서비스 상태를 이 화면에서 읽고 바꿀 수 있습니다.
        </Callout>
      )}

      {opsNotice ? <Callout tone="danger">{opsNotice}</Callout> : null}

      {lastResult && lastResult.rolled_back && (
        <Callout tone="danger">
          적용에 실패해 원래 설정으로 되돌렸습니다. {lastResult.detail}
        </Callout>
      )}

      {/* 🔴 두 묶음이 전폭 괘선 목록이었다 — 라벨과 「수정」 단추가 1500px 떨어져 한 줄로 읽히지
          않았다. 설정성 화면은 `/profile` 처럼 **판 2열 격자**다(D-457): 설정 묶음이 왼쪽 판,
          서비스 묶음이 오른쪽 판. 왼쪽이 설명이 길어 폭을 더 받는다(가중치 선언, D-333).
          도우미가 없으면 판 하나다(D-501). 줄마다 값과 단추가 빠져 이름과 설명만 남고, 서비스는 읽을 것이 없어 오른쪽 판이
          왼쪽 판 높이만큼 빈 채로 섰다 — 서비스도 같은 판의 한 줄(무엇을 다루는 자리인가)로 선다. */}
      {usable ? <ServiceAddressCard system={data} /> : null}

      {usable ? (
        <Box sx={pairTracks("minmax(0, 1.15fr) minmax(0, 0.85fr)")}>
          <Card>
            <SettingList title="시스템 설정" sx={{ mt: 0 }}>
              {rows.map((r, i) => (
                <SettingRow
                  key={r.key} label={r.label} value={r.value} description={r.description}
                  tone={r.tone} action={r.action} last={i === rows.length - 1}
                />
              ))}
            </SettingList>
          </Card>
          <Card>
            <SettingList title="서비스" sx={{ mt: 0 }}>
              {unitNames.length > 0 ? (
                unitNames.map((unit, i) => (
                  <ServiceRow key={unit} unit={unit} state={units[unit]} onControl={control}
                              disabled={run.isPending} last={i === unitNames.length - 1} />
                ))
              ) : (
                <EmptyState size="compact" title="서비스 상태를 읽지 못했습니다" help="새로고침한 뒤 다시 시도해 주세요." />
              )}
            </SettingList>
          </Card>
        </Box>
      ) : (
        <Card>
          <SettingList title="시스템 설정" sx={{ mt: 0 }}>
            {/* 서비스 주소는 맨 위다 — 도우미가 있을 때 판이 맨 위에 서고, 호스트 이름 설명이 「위 「서비스 주소」」를 가리킨다. */}
            <SettingRow label="서비스 주소" description={ADDRESS_ROLE} />
            {rows.map((r) => (
              <SettingRow
                key={r.key} label={r.label} value={r.value} description={r.description}
                tone={r.tone} action={r.action}
              />
            ))}
            <SettingRow last label="서비스" description={SERVICES_ROLE} />
          </SettingList>
        </Card>
      )}

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
    </>
  );
}

export default SystemOps;
