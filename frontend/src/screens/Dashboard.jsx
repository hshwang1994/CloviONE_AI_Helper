import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime, actionKo, objKo } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import { canReach } from "../app/navConfig.js";
import { PageHeader, Card, ListCard, DataTable, Badge, Section, Skeleton, ErrorState, Button, Callout, SubGroup, Surface, useToast } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { StatusList, StatusTile, Note } from "../ui/adminKit.jsx";
import {
  serviceLabel, daysSince, BACKUP_STALE_DAYS, fmtNum, fmtProcessingTime, fmtCertDays,
  failedOpenAgeLabel, componentState, integrationState, storageState, countStates,
  SERVICE_STATE_LABEL, SERVICE_STATE_KIND,
} from "./ops/opsHelpers.js";

/* 관리자 대시보드 — 이 화면이 답하는 질문은 **둘**이다.
 *
 *   1. 지금 제품이 정상인가?
 *   2. 지금 관리자가 조치해야 할 것이 있는가?
 *
 * 나머지는 전부 그 둘을 뒷받침하는 자료이고, 그래서 아래에 온다. 순서가 곧 이 화면의
 * 설계다: 판정 → 조치 목록 → 정상 지표 한 줄 → 필수 서비스 → 외부 연동 → 운영 자료 →
 * 최근 주요 변경.
 *
 * ## 🔴 정상 제품을 장애로 그리던 자리 (2026-08-26)
 *
 * 운영 실측에서 이 화면 맨 위에 「중단 · 위험」 네 줄이 상시로 떠 있었다. 그 넷은 전부
 * **S11 이 걷어낸 런타임**을 가리키는 연동 등록 행이었고(n8n 과 러너 셋), 그중 하나는
 * 옛 제품 이름까지 화면에 띄우고 있었다. 워커의 자동 헬스 스윕이 30초마다 없는 주소로
 * 나가 `down` 을 다시 적었으므로 영원히 빨간 줄이었다.
 *
 * 이름을 화면에서 숨기는 것으로는 안 고쳐진다. 데이터가 틀린 것이라 **데이터를 고쳤다**
 * (`alembic/versions/0017_drop_retired_integrations.py`). 이 파일이 고친 것은
 * 그것이 다시 생겨도 화면이 무너지지 않게 하는 **판정 모델**이다:
 *
 *   * **필수 서비스와 외부 연동을 같은 분모에 넣지 않는다.** 예전 「서비스 정상 3 / 7」은
 *     내부 프로세스 셋과 외부 연동 넷을 합친 값이었다. 연동이 몇 개 등록됐는지에 따라
 *     제품의 건강도가 달라 보이는 것은 건강도가 아니다.
 *   * **Red 는 실제 조치가 필요한 장애에만 쓴다.** 「사용 안 함」과 「미점검」은 상태이지
 *     장애가 아니다. 활성 연동이 죽은 것은 주의(warn)다 — 그 기능만 멈추고 제품은 돈다.
 *   * 상태 어휘는 `ops/opsHelpers.js` 한 곳에서 온다. 예전에는 요약이 `v === "up"` 만 세고
 *     배지는 다른 표로 그려서, 같은 줄이 「정상」인데 요약은 「정상 0 / 6」이라고 말했다.
 *
 * ## 어떤 지표든 화면에 정확히 한 번만 나온다
 *
 * 지금 경보 중이면 위 조치 목록에, 아니면 아래 한 줄 스트립에, 둘 다 아니면 해당 상세
 * 화면에만 있다. 이 규칙이 무너지면 운영자는 같은 수를 세 번 읽고도 확신이 안 선다.
 *
 * 이 화면의 **모든 숫자**의 출처표는 docs/DASHBOARD_METRICS.md 에 있다.
 */

/* 링크를 살릴지 죽일지는 **정본 한 표**로 정한다 (지시 21).
 *
 * 예전에는 이 파일이 `NAV_ROLES` 라는 두 번째 표를 들고 있었고 실제로 갈라져 있었다 —
 * 표가 둘이면 한쪽만 고쳐지고, 그때 증상이 「볼 수 있는 화면인데 링크가 죽어 있다」다. */
const canGo = canReach;

/** 대상 표기 — 사람이 읽을 이름이 없을 때만 쓰는 **마지막 수단**이다.
 *
 * object_type이 "user"인 행은 서버가 이미 대상의 display_name을 `object_label`로 함께
 * 내려준다(app/health/service.py) — 그 이름을 그대로 보여준다(아래 RecentChanges).
 * 이름이 없는 나머지 object_type(설정 키·승인 요청 id 등)만 여기로 온다.
 *
 * 예전에는 길이만 보고 여덟 자에서 잘랐다. 그래서 설정 키 `maintenance_mode` 가
 * `maintena…` 가 됐다 — 그 값은 내부 식별자가 아니라 **그 행에서 가장 중요한 정보**다.
 * UUID 와 해시처럼 읽을 수 없는 값만 줄이고, 줄였다는 신호(…)를 남긴다(그냥 잘라내면
 * 전체 값처럼 보여 다른 화면에 잘못 붙여넣게 된다). */
function targetId(id) {
  const s = String(id);
  const opaque = /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(s) || /^[0-9a-f]{16,}$/i.test(s);
  return opaque ? s.slice(0, 8) + "…" : s;
}

/** 동작 칸의 문구. `actionKo` 는 「대상, 동작」으로 옮기는데(감사 로그 화면은 대상 칸이
 * 따로 없어 그 모양이 맞다), 이 표에는 대상 칸이 따로 있어 같은 낱말이 한 줄에 두 번
 * 나온다. 대상과 겹치는 앞머리만 걷어 낸다. */
export function actionOnly(action, objectType) {
  const full = actionKo(action);
  const obj = objKo(objectType);
  const head = obj + ", ";
  return obj && obj !== "-" && full.startsWith(head) ? full.slice(head.length) : full;
}
function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
  return Promise.reject(new Error("copy unsupported"));
}

/** 필수 서비스 이름 → 상태 어휘. `web` 은 이 응답이 왔다는 사실 자체가 증거다. */
export function componentStates(components) {
  return Object.fromEntries(
    Object.entries(components || {}).map(([k, v]) => [k, componentState(v)])
  );
}

/** 외부 연동 이름 → 상태 어휘. 꺼 둔 것과 한 번도 안 잰 것을 중단과 구별한다. */
export function integrationStates(integrations) {
  return Object.fromEntries(
    Object.entries(integrations || {}).map(([k, v]) => [k, integrationState(v)])
  );
}

// 역할별 이동 대상 + 안내 접미사를 한 곳에서 계산한다 — 경보 목록·헤드라인·서비스 타일이
// 전부 같은 값을 써야 "여기선 갈 수 있다는데 저기선 막다른 길"이 안 생긴다.
export function dashboardNav(role) {
  const diagTo = canGo("/diagnostics", role) ? "/diagnostics" : undefined;
  const procTo = diagTo || (canGo("/jobs", role) ? "/jobs" : undefined);
  const jobsTo = canGo("/jobs", role) ? "/jobs" : undefined;
  const diagNote = diagTo ? "" : ", 관리자 문의";
  const jobsNote = jobsTo ? "" : ", 관리자 문의";
  const procNote = procTo ? "" : ", 관리자 문의";
  return { diagTo, procTo, jobsTo, diagNote, jobsNote, procNote };
}

/* 파일 저장소 화면은 설정의 탭 하나이고 시스템 관리자 전용이다(settings/SettingsShell.jsx).
   `canGo("/settings")` 는 더 넓은 집합을 허용하므로 그것만 보고 링크를 걸면 눌러서 들어간
   사람이 그 탭을 못 본다 — 백업 경보가 역할을 직접 보는 것과 같은 이유다. */
const STORAGE_TO = "/settings?tab=storage";
const storageTarget = (role) => (role === "system_admin" ? STORAGE_TO : undefined);

/* 운영자가 지금 확인해야 할 것 — **조치가 필요한 항목만** 담는다.
 *
 * 심각도 두 단계의 뜻이 다르다.
 *   danger  제품의 기능이 지금 멈춰 있거나 곧 멈춘다. 사람이 바로 손대야 한다.
 *   warn    지켜봐야 하지만 제품은 돌고 있다.
 *
 * 「사용 안 함」·「미점검」·「설정 안 됨」은 여기 오지 않는다. 그것은 상태이지 조치가 아니다. */
export function buildAlerts(d, role) {
  const jobs = d.jobs_24h || {};
  const disk = d.disk || {};
  const mem = d.memory || {};
  const comps = d.components || {};
  const { diagTo, procTo, jobsTo, diagNote, jobsNote, procNote } = dashboardNav(role);
  const alerts = [];

  // 유지보수 모드는 이 앱에서 blast-radius가 가장 큰 운영 상태다 — 켜져 있는 동안 일반
  // 사용자의 모든 쓰기가 막힌다(app/settings/gate.py::block_if_maintenance). 맨 앞에 넣는다:
  // 다른 경보들의 원인이 이것일 수 있다(작업이 안 쌓이는 이유 등).
  // `/maintenance` 는 `/settings?tab=policy` 로 접힌 옛 주소다 — 링크는 실제 목적지를 가리킨다.
  if (d.maintenance) alerts.push({ src: "maintenance", label: "유지보수 모드", value: "활성", kind: "danger", to: canGo("/settings", role) ? "/settings?tab=policy" : undefined });
  if (jobs.failed_open) alerts.push({ src: "job:failed", label: "실패 작업" + failedOpenAgeLabel(jobs) + jobsNote, value: fmtNum(jobs.failed_open), kind: "danger", to: jobsTo });
  if (jobs.queued) alerts.push({ src: "job:queued", label: "대기 작업" + jobsNote, value: fmtNum(jobs.queued), kind: "warn", to: jobsTo });
  // success_rate_pct의 분모는 최근 24시간에 '종료된'(성공+실패+취소) 작업만이다 — 접수만
  // 몰린 순간에는 이 값이 영향받지 않는다. headlineStats의 80/95 경계와 맞춘다.
  if (jobs.success_rate_pct != null && jobs.total > 0 && jobs.success_rate_pct < 80)
    alerts.push({ src: "job:rate", label: "성공률 낮음(종료 작업 대비)" + jobsNote, value: jobs.success_rate_pct + "%", kind: "danger", to: jobsTo });
  else if (jobs.success_rate_pct != null && jobs.total > 0 && jobs.success_rate_pct < 95)
    alerts.push({ src: "job:rate", label: "성공률 저하(종료 작업 대비)" + jobsNote, value: jobs.success_rate_pct + "%", kind: "warn", to: jobsTo });

  /* 필수 서비스. 예전에는 `worker` 와 `scheduler` 두 이름을 손으로 적어 두고 있었다 —
     그래서 켠 설치에만 실리는 대화형 워커 레인(`worker_conversational`)이 죽으면 이 목록에
     아무것도 안 떴다. 목록을 손으로 적지 않고 서버가 실어 준 것을 전부 본다. `web` 은
     이 응답이 도착했다는 사실 자체가 증거라 판정 대상이 아니다. */
  Object.keys(comps).forEach((k) => {
    if (k === "web") return;
    const state = componentState(comps[k]);
    if (state === "ok") return;
    alerts.push({
      src: "comp:" + k,
      label: serviceLabel(k) + procNote,
      value: SERVICE_STATE_LABEL[state],
      kind: state === "down" ? "danger" : "warn",
      to: procTo,
    });
  });

  /* 저장소. 용량(디스크)과 다른 결함을 잡는다 — 자리는 넉넉한데 마운트가 빠졌거나 소유권이
     어긋나 **쓰기만** 안 되는 경우다. 그 상태에서 첨부와 업로드가 통째로 멈춘다.
     「설정 안 됨」은 장애가 아니라서 경보가 아니다(storageState 가 그 둘을 가른다). */
  const st = storageState(d.storage);
  if (st.state === "down") {
    alerts.push({ src: "storage", label: "파일 저장소 쓰기 불가", value: "중단", kind: "danger", to: storageTarget(role) });
  }
  // 로컬 업로드 경로는 저장소 공급자와 별개로 본다(OPS-03) — 저쪽이 정상이어도 여기가
  // 막히면 업로드가 실패한다.
  if (d.uploads_writable === false) {
    alerts.push({ src: "uploads", label: "업로드 폴더 쓰기 불가" + diagNote, value: "중단", kind: "danger", to: diagTo });
  }

  /* 외부 연동은 **선택 구성요소**다. 죽으면 그 기능만 멈추고 제품은 돈다 — 주의로 올린다.
     비활성과 미점검은 여기 오지 않는다(`integrationState` 가 그 셋을 가른다). */
  Object.entries(d.integrations || {}).forEach(([name, v]) => {
    if (integrationState(v) !== "down") return;
    /* 가는 곳이 **진단**이다. 「외부 연동」 관리 화면은 걷었다(0017 이 등록 행을 지웠고
       시드 목록이 비어 있어 그 표가 다시 안 채워진다) — 그래도 헬스 스윕은 그대로 돌고,
       그 결과를 읽는 자리는 진단 화면이다. 없는 화면으로 보내는 경보는 막다른 줄이다. */
    alerts.push({ src: "integ:" + name, label: serviceLabel(name) + " 연동", value: "중단", kind: "warn", to: diagTo });
  });

  if (d.cert_days_remaining != null && d.cert_days_remaining <= 30)
    alerts.push({ src: "cert", label: "인증서 만료" + diagNote, value: fmtCertDays(d.cert_days_remaining), kind: d.cert_days_remaining <= 0 ? "danger" : "warn", to: diagTo });
  // '마지막 백업 없음'은 백업을 실제로 '실행할 수 있는' 역할(system_admin)에게만 경보로 띄운다 —
  // 조치할 수 없는 빨간 경보를 상시 띄우면 실제 경보에 둔감해진다.
  if (!d.last_backup_at && role === "system_admin") alerts.push({ src: "backup", label: "마지막 백업", value: "없음", kind: "danger", to: "/backup" });
  // 마지막 성공 백업은 있지만 그 이후로 한참 지났으면(예: 계속 실패 중) 조용한 '정상'으로 보이던
  // 문제 — 자원 타일의 80/90% warn 기준과 같은 취지로, 여기도 나이 기준 경보를 둔다.
  const backupAgeDays = d.last_backup_at ? daysSince(d.last_backup_at) : null;
  if (backupAgeDays != null && backupAgeDays > BACKUP_STALE_DAYS && role === "system_admin")
    alerts.push({ src: "backup-stale", label: "마지막 백업이 오래됨", value: Math.floor(backupAgeDays) + "일 전", kind: backupAgeDays > BACKUP_STALE_DAYS * 2 ? "danger" : "warn", to: "/backup" });
  // 디스크/메모리는 headlineStats의 표시 임계값(80/90)과 달리 경보 발생 임계값이 조금 더
  // 엄격하다(85/90 danger, 80+ warn 전체가 경보) — 자원이 실제로 위험해지는 지점을 우선한다.
  if (disk.used_pct != null && disk.used_pct >= 85)
    alerts.push({ src: "disk", label: "디스크 사용" + diagNote, value: disk.used_pct + "%", kind: "danger", to: diagTo });
  else if (disk.used_pct != null && disk.used_pct >= 80)
    alerts.push({ src: "disk", label: "디스크 사용" + diagNote, value: disk.used_pct + "%", kind: "warn", to: diagTo });
  // 메모리 고갈도 디스크만큼 급하다 — 자원 타일만 빨갛게 칠하고 경보엔 없어 '이상 없음' 오배너가 뜨던 문제.
  if (mem.used_pct != null && mem.used_pct >= 90)
    alerts.push({ src: "mem", label: "메모리 사용" + diagNote, value: mem.used_pct + "%", kind: "danger", to: diagTo });
  else if (mem.used_pct != null && mem.used_pct >= 80)
    alerts.push({ src: "mem", label: "메모리 사용" + diagNote, value: mem.used_pct + "%", kind: "warn", to: diagTo });

  return alerts;
}

/** 「지금 제품이 정상인가」 한 문장. 조치 목록과 **같은 재료**로 만든다 — 두 줄이 서로 다른
 * 말을 하면 어느 쪽도 안 믿게 된다. */
export function systemVerdict(alerts) {
  const list = Array.isArray(alerts) ? alerts : [];
  const danger = list.filter((a) => a.kind === "danger").length;
  const warn = list.length - danger;
  if (danger) {
    return {
      // 배지 낱말은 아래 조치 목록의 심각도 태그(SEV_TEXT)와 같은 어휘여야 한다 — 예전엔
      // 여기만 "문제"였고 목록 각 줄은 "위험"이라 같은 화면에 같은 뜻의 경고가 다른 말로
      // 두 번 떴다(재감사 C16, "경고 관용구를 둘 쓴다"). 문장 속의 "문제"는 자연스러운
      // 서술이라 그대로 둔다 — 배지처럼 위험/주의/정상 셋 중 하나로 끊어 읽는 낱말만 맞춘다.
      tone: "danger", label: "위험",
      text: warn
        ? `지금 조치가 필요한 문제가 ${danger}건 있고, 지켜볼 것이 ${warn}건 있습니다.`
        : `지금 조치가 필요한 문제가 ${danger}건 있습니다.`,
    };
  }
  if (warn) {
    return { tone: "warn", label: "주의", text: `제품은 돌고 있습니다. 지켜볼 것이 ${warn}건 있습니다.` };
  }
  return { tone: "ok", label: "정상", text: "지금 조치가 필요한 문제가 없습니다." };
}

/* 머리 지표 넷 — **정상일 때 아래 한 줄 스트립에 접히는 값들**.
 *
 * 「서비스 정상 N / M」의 분모는 **필수 서비스뿐**이다. 예전에는 외부 연동까지 합쳐 세서,
 * 연동을 몇 개 등록했는지에 따라 제품의 건강도가 달라 보였다. 연동 수는 아래 「외부 연동」
 * 구역이 자기 분모로 따로 말한다.
 *
 * 이 넷 중 지금 경보 중인 것은 buildAlerts()가 이미 위 조치 목록에 올렸다 — DashboardBody 가
 * 그 경보 소스와 겹치는 항목을 스트립에서 걸러낸다(같은 값이 화면에 두 번 나오지 않는다).
 */
export function headlineStats({ components, jobs, disk, jobsNote, diagTo, diagNote }) {
  const counts = countStates(Object.values(componentStates(components)));
  const rate = jobs.success_rate_pct;
  const usedPct = (disk || {}).used_pct;

  return [
    {
      key: "services",
      value: counts.total ? `${counts.ok} / ${counts.total}` : "-",
      label: "필수 서비스 정상",
      kind: counts.down > 0 ? "danger" : counts.warn > 0 ? "warn" : counts.total ? "ok" : undefined,
      to: null,
    },
    {
      key: "rate",
      value: rate != null ? rate + "%" : "-",
      label: "24시간 성공률" + jobsNote,
      kind: rate == null ? undefined : rate >= 95 ? "ok" : rate >= 80 ? "warn" : "danger",
      to: "/jobs",
    },
    {
      key: "failed",
      value: fmtNum(jobs.failed_open != null ? jobs.failed_open : 0),
      label: "미해결 실패 작업" + failedOpenAgeLabel(jobs) + jobsNote,
      kind: (jobs.failed_open || 0) > 0 ? "warn" : undefined,
      to: "/jobs",
    },
    {
      key: "disk",
      value: usedPct != null ? usedPct + "%" : "-",
      label: "디스크 사용" + diagNote,
      kind: usedPct == null ? undefined : usedPct >= 90 ? "danger" : usedPct >= 80 ? "warn" : undefined,
      to: diagTo,
    },
  ];
}

/* 위 네 지표 중 지금 경보 중이면(buildAlerts 의 src) 스트립에서 빼는 대응표.
 *
 * 🔴 `services` 에는 **"대응하는 경보가 없다"고 적혀 있었지만 사실이 아니었다.** buildAlerts
 * 는 `web` 을 뺀 모든 필수 서비스에 `comp:<이름>` 경보를 만든다. 그래서 워커와 스케줄러가
 * 응답 없음일 때, 그 사실이 **한 화면에 세 번** 나왔다(실측 2026-09-01): 조치 목록의 두 줄,
 * 아래 「필수 서비스」 구역의 배지, 그리고 이 스트립의 「필수 서비스 정상 1 / 3」.
 *
 * 이 스트립은 「**지금 정상인** 지표」 줄이다. 「정상 1 / 3」은 정상 지표가 아니라 고장
 * 요약이고, 그 요약을 굳이 여기 둘 이유는 없다 — 조치 목록이 어느 서비스인지까지 말하고
 * 아래 구역이 배지로 다시 말한다. 하나가 아니라 **여럿 중 하나라도** 경보 중이면 뺀다. */
const HEALTHY_SRC_FOR_KEY = { rate: "job:rate", failed: "job:failed", disk: "disk" };
const isHealthySrcActive = (key, alertSrcs) => (
  key === "services"
    ? [...alertSrcs].some((s) => s.startsWith("comp:"))
    : !!HEALTHY_SRC_FOR_KEY[key] && alertSrcs.has(HEALTHY_SRC_FOR_KEY[key])
);

// 경보 행의 기본 조치 버튼 — 라벨은 "어디로 가는가"로 정한다(경보 종류가 아니라). 워커·
// 스케줄러·디스크·메모리·인증서는 전부 diagTo/procTo로 모이므로 종류별로 따로 정의하면
// 어차피 같은 문구가 다섯 번 반복된다.
const ACTION_LABEL = {
  // 유지보수 정책은 설정 화면의 '정책' 탭에 있다(옛 `/maintenance` 주소는 거기로 접힌다).
  "/settings?tab=policy": "유지보수 설정 열기",
  [STORAGE_TO]: "파일 저장소 열기",
  "/jobs": "작업 큐 열기",
  "/diagnostics": "진단 열기",
  "/backup": "백업 관리로 이동",
};
const SEV_COLOR = { danger: "error.main", warn: "warning.strong" };
const SEV_TEXT = { danger: "위험", warn: "주의" };

/* 조치 대기 행 하나 — 카드가 아니라 표에 가까운 한 줄이다. 「무엇이(라벨) · 영향(값+심각도)
 * · 기본 조치」를 한 시선에서 읽는다. 심각도는 색만으로 전하지 않는다(WCAG 1.4.1) — 짧은
 * 텍스트 태그를 함께 쓴다(판독 칸과 같은 규칙).
 *
 * 가장 급한 한 건만 `primary`(채운 버튼)이고 나머지는 `default`(외곽선)다 — 화면/오버레이당
 * `contained` 정확히 1개. 호출부가 이미 danger를 앞으로 정렬해 두므로 "첫 행"이 곧 "가장
 * 급한 행"이다. */
function ActionRow({ a, isPrimary, onClick }) {
  const sevText = SEV_TEXT[a.kind];
  return (
    <Box
      component="li"
      sx={{
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap",
        py: 1.5, borderBottom: 1, borderColor: "divider", "&:last-of-type": { borderBottom: 0 },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, minWidth: 0, flexWrap: "wrap" }}>
        <Typography sx={{ fontWeight: FONT_WEIGHT.bold, minWidth: 0, ...KO_WORD_BREAK }}>{a.label}</Typography>
        <Typography
          component="span"
          sx={{
            fontWeight: FONT_WEIGHT.semibold, fontVariantNumeric: "tabular-nums",
            /* 한 줄 상자 하나로 둔다. inline-flex 면 값과 심각도 낱말이 각자 line box 를
               만들어, 눈으로는 한 줄이어도 측정은 3줄로 읽힌다. */
            color: SEV_COLOR[a.kind] || "text.primary", display: "inline",
            // 짧고 고정된 값이 줄바꿈될 이유가 없는데 white-space 없이 두면 390px에서 라벨이
            // 행을 다 채운 뒤 이 값만 남은 좁은 폭에 한글 음절 단위로 세로 붕괴한다.
            whiteSpace: "nowrap", flexShrink: 0,
          }}
        >
          {a.value}
          {sevText ? <Box component="span" sx={{ fontSize: FONT_SIZE.caption, ml: 0.5 }}>{sevText}</Box> : null}
        </Typography>
      </Box>
      <Button variant={isPrimary ? "primary" : "default"} size="sm" disabled={!a.to} onClick={onClick}>
        {a.to ? (ACTION_LABEL[a.to] || "이동") : "이동 불가"}
      </Button>
    </Box>
  );
}

/* 조치 대기 목록. danger를 항상 앞으로 정렬한다(불변성: sort 전에 배열을 복사) — 좁은
 * 화면에서 스크롤 없이 처음 1~2개만 보이면 danger가 코드 순서상 warn보다 뒤에 있을 때 가장
 * 급한 항목을 놓칠 수 있다.
 *
 * **안쪽 스크롤을 만들지 않는다.** 이 목록은 「지금 손대야 하는 것 전부」라 잘리면 안 된다.
 * 길어질 수 있다는 이유로 상자에 가두면, 상자 밖으로 밀린 위험이 없는 것처럼 보인다. */
function ActionQueue({ alerts, goto }) {
  if (!alerts.length) return null;
  const sorted = [...alerts].sort((a, b) => (a.kind === "danger" ? 0 : 1) - (b.kind === "danger" ? 0 : 1));
  return (
    <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, mt: 1 }}>
      {sorted.map((a, i) => (
        // 안정 key(출처 태그 a.src) — label만 쓰면 컴포넌트 경보('워커')와 같은 이름을 쓰는
        // 연동 경보가 같은 key로 충돌할 수 있다.
        <ActionRow key={a.src} a={a} isPrimary={i === 0} onClick={a.to ? goto(a.to) : undefined} />
      ))}
    </Box>
  );
}

/* 상태 한 줄 — 이 화면의 첫 질문에 대한 답과, 지금 정상인 지표들.
 *
 * 둘을 **한 줄에 둔다.** 판정만 담은 상자는 4K 에서 2,206px 짜리 면에 문장 하나가 놓인
 * 모양이 되고(실측 잉크 11%), 그것은 상자를 만든 이유를 스스로 부정한다. 오른쪽에 지금
 * 정상인 값들이 오면 그 폭이 실제로 쓰이고, 「정상인가」와 「무엇이 정상인가」가 한
 * 시선에서 읽힌다.
 *
 * 배지가 모양과 색을 함께 나르고 문장이 같은 사실을 글자로 말한다 — 색만으로 전하지 않는다. */
function StatusBand({ verdict, strip }) {
  const line = { ok: "success.main", warn: "warning.main", danger: "error.main" }[verdict.tone];
  return (
    <Box
      sx={(t) => ({
        display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: 2, flexWrap: "wrap",
        px: 2, py: 1.5, borderRadius: 1,
        border: 1, borderColor: line, bgcolor: t.palette.action.hover,
      })}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, minWidth: 0 }}>
        {/* 배지는 줄어들지 않는다. `Badge` 안쪽 글자는 말줄임을 갖고 있어서, 좁은 폭에서
            이 자리가 눌리면 「문제」가 「문.」이 된다(390 실측). 두 글자짜리 판정이 잘리면
            그 판정은 아무 말도 안 한 것과 같다. */}
        <Box sx={{ flexShrink: 0 }}>
          <Badge value={verdict.label} kind={verdict.tone === "danger" ? "danger" : verdict.tone === "warn" ? "warn" : "ok"} emphasis="strong" />
        </Box>
        <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, minWidth: 0, ...KO_WORD_BREAK }}>{verdict.text}</Typography>
      </Box>
      <HealthyStrip items={strip} />
    </Box>
  );
}

/* 정상 지표 한 줄 — 지금 경보 중이 아닌 값만 여기 온다(경보 중이면 위 목록에 이미 있다).
 * 값 하나하나는 headlineStats()가 이미 계산한 것을 그대로 빌린다. 0인 값도 무채색 텍스트로
 * 그대로 보여준다 — 카드가 아니라 이 작은 글자 자체가 이미 "크게 그리지 않는다"다. */
function HealthyStrip({ items }) {
  if (!items.length) return null;
  return (
    <Typography
      component="div" variant="body2" color="text.secondary"
      sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "1em", fontVariantNumeric: "tabular-nums" }}
    >
      {items.map((it, i) => (
        // 항목 구분은 글자(가운뎃점 등)가 아니라 테두리로 한다 — 화면 문구에 가운뎃점을
        // 쓰지 않는다(scripts/check_user_text.py).
        <Box key={it.key} component="span"
          sx={i > 0 ? { pl: "1em", borderLeft: 1, borderColor: "divider" } : undefined}>
          {it.onClick ? (
            <Link component="button" type="button" underline="hover" color="text.primary"
              onClick={it.onClick} sx={{ font: "inherit", verticalAlign: "baseline" }}>
              {it.label} {it.value}
            </Link>
          ) : (
            <Box component="span">{it.label} {it.value}</Box>
          )}
        </Box>
      ))}
    </Typography>
  );
}

/* 사실 한 줄 — 이름과 값. 운영 자료 세 묶음이 같은 모양으로 읽히게 한다.
 * 값이 몇 개뿐인 자료에 큰 판독 칸을 쓰지 않는다(그러면 그 자료가 화면을 지배한다). */
function Fact({ label, value, tone }) {
  return (
    /* 이름과 값 사이를 넓은 화면에서 무한히 벌리지 않는다. 4K 에서 한 칸이 700px 이면
       「처리 요청」과 「0」이 그만큼 떨어져 한 줄로 안 읽힌다 — 값이 무슨 값인지 다시
       찾아야 한다. 상한을 20rem 으로 좁혔다(예전 26rem 은 2560 에서 여전히 396px 였다). */
    <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1.5, py: 0.5, minWidth: 0, maxWidth: "20rem" }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>{label}</Typography>
      <Typography
        component="div"
        variant="body2"
        color={tone ? `${tone}.strong` : "text.primary"}
        sx={{ fontWeight: FONT_WEIGHT.semibold, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 0.75 }}
      >
        {value}
      </Typography>
    </Box>
  );
}

/* 운영 자료 한 칸의 이동 링크.
 *
 * **버튼이 아니라 링크다.** 이 화면에서 버튼은 위 조치 목록의 몫이다 — 「지금 손대야 하는
 * 것」과 「가서 보면 되는 것」이 같은 모양이면 급한 것이 안 보인다. 「최근 주요 변경」의
 * 「전체 보기」와 같은 어휘를 쓴다.
 *
 * 갈 수 없는 역할에게는 아무것도 안 그린다 — 눌러도 아무 일도 안 나는 링크는 막다른 길이고,
 * 그 사실은 위 조치 목록의 「관리자 문의」 접미사가 이미 말한다. */
function OpsLink({ label, onClick }) {
  if (!onClick) return null;
  return (
    <Box sx={{ mt: 1.5 }}>
      <Link component="button" type="button" variant="body2" underline="hover" onClick={onClick}>
        {label} →
      </Link>
    </Box>
  );
}

/* 운영 자료 세 칸의 격자.
 *
 * ## 🔴 세로 실선만으로는 «다른 자료» 가 안 보였다 (2026-08-26 실측)
 *
 * 예전에는 한 흰 판 안에서 셋을 세로 실선으로만 갈랐다. 배경도 같고 여백도 같아서 화면에는
 * 저장소·백업·작업이 **한 표의 세 단**처럼 평평하게 놓였다 — 서로 다른 성격의 운영 정보라는
 * 사실이 어디에도 없었다.
 *
 * 판을 셋으로 쪼개지 않는다(흰 판 안에 흰 판을 넣는 것이다). 대신 묶음마다 **아주 옅은
 * 함몰면**을 준다(`Surface tone="inset"`). 테두리도 그림자도 없다 — 면 하나와 여백이면
 * 「여기부터 다른 이야기」가 읽힌다.
 *
 * ## 폭은 정보량으로 나눈다
 *
 * 정확히 3분의 1씩 주지 않는다. 백업의 「마지막 성공」은 날짜와 시각이 함께 들어가 이 화면
 * 에서 가장 긴 값이고, 작업 지표는 짧은 수 셋뿐이다. 같은 폭을 주면 한쪽은 꺾이고 한쪽은
 * 빈다.
 *
 * ⚠️ 중단점 미디어쿼리를 **키로 직접 적지 않는다.** `gridTemplateColumns: { xs, md }` 도
 * 같은 `@media (min-width:900px)` 키로 펴지기 때문에, 같은 객체에 `[t.breakpoints.up("md")]`
 * 를 또 두면 뒤에 적은 쪽이 앞의 것을 통째로 덮는다 — 실제로 이 격자가 4K 에서 한 열로
 * 그려지던 원인이 그것이었다. 값마다 반응형 객체를 쓴다. */
const OPS_GRID = {
  display: "grid", gap: 2, alignItems: "stretch",
  gridTemplateColumns: {
    xs: "minmax(0,1fr)",
    md: "repeat(2, minmax(0,1fr))",
    lg: "minmax(0,1.05fr) minmax(0,1.15fr) minmax(0,0.8fr)",
  },
};

/* 화면 아래 두 구역 — 운영 자료와 최근 주요 변경.
 *
 * 🔴 4K 에서 «내용이 한쪽에만 몰린» 면이 생겼다(2026-08-26 실측: 833×221 판에 잉크 18%,
 * 내용이 폭의 43% — `oversized_empty_surface` 가 잡았다). 값이 서넛뿐인 자료에 2,200px
 * 를 셋으로 나눠 주면 판마다 800px 씩 가는데, 그 안에 들어갈 것이 없다.
 *
 * 이 앱의 4K 규칙은 **남는 폭을 두 번째 열로 보내는 것**이다(density.js) — 위쪽
 * 「필수 서비스 / 외부 연동」이 이미 같은 방식이다. 2200 이상에서 이 둘을 나란히 두면
 * 운영 자료의 판이 350px 대가 되어 이름과 값이 한 줄로 읽히고, 아래 빈 캔버스도 줄어든다.
 * 1920 에서는 나누지 않는다 — 그 폭에서 반으로 자르면 「마지막 성공」의 날짜와 시각이
 * 꺾인다. */
const BOTTOM_GRID = {
  display: "grid", alignItems: "start", columnGap: 4,
  gridTemplateColumns: { xs: "minmax(0,1fr)", xxl: "repeat(2, minmax(0,1fr))" },
};

/* 운영 자료 한 묶음 — 옅은 함몰면 위에 「제목 → 상태 → 핵심 값 → 설명 → 이동」.
 *
 * 세 묶음이 **같은 순서**를 쓴다. 예전에는 백업만 상태가 둘째 줄에 있어서, 세 칸을 훑을 때
 * 눈이 매번 다른 높이에서 상태를 찾아야 했다. */
function OpsGroup({ title, children }) {
  return (
    <Surface tone="inset" sx={{ p: 2.5, minWidth: 0, display: "flex", flexDirection: "column" }}>
      <SubGroup first title={title} sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {children}
      </SubGroup>
    </Surface>
  );
}

export function Dashboard() {
  const nav = useNavigate();
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  // 운영 현황은 실시간성이 핵심이라 30초마다 자동 갱신(하트비트 stale 90초 창에 맞춤).
  // 폴링은 한 번 재시도해 순간 네트워크 끊김에 실시간 보드가 통째로 사라지지 않게 한다.
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api("/api/admin/dashboard"), retry: 1, refetchInterval: 30 * 1000 });
  const updated = q.dataUpdatedAt ? fmtDateTime(new Date(q.dataUpdatedAt).toISOString()) : null;
  // 백그라운드 폴링은 매번 isFetching을 켜 버튼을 깜빡이게 하므로, 수동 새로고침만 버튼 상태로 반영한다.
  const [manualRefreshing, setManualRefreshing] = React.useState(false);
  // 수동 새로고침만 스크린리더에 완료를 알린다(30초 자동 폴링은 알리지 않는다 — 타임스탬프를
  // aria-live에서 뺀 것과 같은 이유로 소음이 된다).
  const [refreshAnnounce, setRefreshAnnounce] = React.useState("");
  React.useEffect(() => {
    if (q.isFetching) return;
    if (manualRefreshing) {
      setManualRefreshing(false);
      /* 🔴 **실패한 새로고침을 성공이라고 알리지 않는다.** 예전에는 결과를 안 보고 언제나
         「대시보드를 갱신했습니다」였고, 뒤에 붙는 시각은 **직전에 성공한** 조회의
         `dataUpdatedAt` 이었다. 그래서 새로고침이 실패하면 눈으로 보는 사람은 머리말에서
         「새로고침 실패」를 읽는데 스크린리더 사용자만 「갱신했습니다 (오후 3:45 기준)」를
         들었다 — 한 화면이 두 사람에게 반대로 말했다. */
      setRefreshAnnounce(q.isError
        ? "대시보드를 갱신하지 못했습니다. 표시된 값이 최신이 아닐 수 있습니다."
        : "대시보드를 갱신했습니다" + (q.dataUpdatedAt ? " (" + fmtDateTime(new Date(q.dataUpdatedAt).toISOString()) + " 기준)" : "") + ".");
    }
  }, [q.isFetching]); // eslint-disable-line react-hooks/exhaustive-deps
  const onManualRefresh = () => { setManualRefreshing(true); q.refetch(); };
  // 마지막으로 성공한 데이터가 있으면 폴링 실패로 화면을 비우지 않고 계속 보여준다.
  const staleAfterError = q.isError && !!q.data;

  return (
    <Box className="c-screen">
      <PageHeader area="운영" title="대시보드"
        // C17 재감사 — 사용자 화면(ui/kit.jsx PageHeader description)은 다 갖고 있는 한 줄
        // 설명이 관리자 화면에는 없었다. 이 화면 머리말이 이미 답이라고 적어 둔 두 질문을
        // 그대로 옮긴다("이 화면이 답하는 질문은 둘이다" 위 주석 참고).
        description="제품이 지금 정상인지, 조치해야 할 문제가 있는지 봅니다."
        actions={<>
          {/* 30초마다 갱신되는 비-조치성 타임스탬프에 aria-live를 달면 스크린리더 사용자에게
              "오후 3:45 기준", "오후 3:46 기준" ...이 탭을 열어 둔 내내 끊임없이 낭독된다. */}
          {updated ? (
            <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center", fontVariantNumeric: "tabular-nums" }}>
              {updated} 기준{staleAfterError ? ", 새로고침 실패" : ""}
            </Typography>
          ) : null}
          <Button variant="ghost" size="sm" disabled={manualRefreshing} onClick={onManualRefresh}>{manualRefreshing ? "새로고침 중…" : "새로고침"}</Button>
          {/* 수동 새로고침 완료만 조용히 알린다. */}
          <span className="sr-only" role="status" aria-live="polite">{refreshAnnounce}</span>
        </>} />
      {!q.data ? (
        // 데이터가 아직/전혀 없을 때: 오류면 ErrorState, 아니면 로딩 스켈레톤.
        // 판정 줄 + 조치 목록 + 그 아래 구역들의 대략적인 모양을 미리 잡아 세로 공간이
        // 크게 튀지 않게 한다.
        q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
          <Box>
            <Card sx={{ mb: 3 }}><Skeleton lines={3} /></Card>
            <Card sx={{ mb: 3, py: 1.5 }}><Skeleton lines={2} /></Card>
            <Card><Skeleton lines={4} /></Card>
          </Box>
        )
      ) : (
        <DashboardBody d={q.data} nav={nav} role={role} stale={staleAfterError} />
      )}
      {/* 개인 업무(`WorkSection`)는 **여기 없다** (0060 §3).
          관리자 콘솔은 Control Plane 이다 — 운영·관리 정보만 둔다. */}
    </Box>
  );
}

function DashboardBody({ d, nav, role, stale }) {
  const toast = useToast();
  // 대상 ID는 title(hover) 툴팁으로만 전체 값을 보여줬다 — 터치 기기·스크린리더는 title이 안 뜬다.
  // 짧은 표기를 눌러 전체 ID를 클립보드로 복사할 수 있게 한다. 복사가 실패하면(비보안 컨텍스트 등)
  // 그 행의 전체 ID를 수동 선택-복사 스팬으로 펼쳐 보여준다.
  const [revealedId, setRevealedId] = React.useState(null);
  function copyObjectId(id) {
    copyToClipboard(id).then(
      () => { setRevealedId(null); toast("ID를 복사했습니다.", "success"); },
      () => { setRevealedId(id); toast("복사를 지원하지 않는 환경입니다. 아래에 전체 ID를 펼쳤습니다.", "info"); }
    );
  }
  const jobs = d.jobs_24h || {};
  const disk = d.disk || {};
  // 링크는 볼 수 있는 역할에게만 건다(없으면 클릭 불가로 남겨 정보는 유지).
  const goto = (path) => (canGo(path, role) ? () => nav(path) : undefined);
  const { diagTo, jobsTo, diagNote, jobsNote } = dashboardNav(role);
  const alerts = buildAlerts(d, role);
  const alertSrcs = new Set(alerts.map((a) => a.src));
  const verdict = systemVerdict(alerts);

  const comps = d.components || {};
  const compStates = componentStates(comps);
  const integStates = integrationStates(d.integrations);
  const compCounts = countStates(Object.values(compStates));
  const integCounts = countStates(Object.values(integStates));

  /* 정상 지표 스트립: headlineStats 의 넷 중 지금 경보 중이 아닌 것만 남긴다 + 대기 작업.
   *
   * 🔴 **값이 없는 항목은 여기 오지 않는다.** 실측(2026-09-01)에서 이 줄이 「필수 서비스
   * 정상 1 / 3 · 24시간 성공률 - · 디스크 사용 45.8%」였다. 가운데 「-」는 24시간 안에 끝난
   * 작업이 하나도 없어서 성공률을 **낼 수 없다**는 뜻인데, 그 사실은 아래 「최근 24시간
   * 작업」 칸이 이미 한 문장으로 말한다. 「지금 정상인 지표」 줄에 모르는 값을 세워 두면
   * 옆의 진짜 값까지 같은 무게로 읽힌다 — `MetricStrip` 이 같은 이유로 「-」를 빈 값으로
   * 친다(ui/kit.jsx::isEmptyValue). */
  const headline = headlineStats({ components: comps, jobs, disk, jobsNote, diagTo, diagNote });
  const hasValue = (v) => v != null && v !== "" && v !== "-";
  const stripItems = headline
    .filter((t) => hasValue(t.value) && !isHealthySrcActive(t.key, alertSrcs))
    .map((t) => ({ key: t.key, label: t.label, value: t.value, onClick: t.to && canGo(t.to, role) ? goto(t.to) : undefined }));
  /* 대기 작업은 「미해결 실패」 다음, 「디스크」 앞이다. 자리를 **인덱스 3** 으로 적어
     두면 위 필터가 앞 항목을 하나라도 뺀 순간 그 뜻이 사라진다 — 실제로 실패 작업이 경보
     중이면 대기가 디스크 뒤로 밀려 있었다. 자리를 **이웃으로** 정한다. */
  if (jobs.queued != null && !alertSrcs.has("job:queued")) {
    const at = stripItems.findIndex((it) => it.key === "disk");
    stripItems.splice(at < 0 ? stripItems.length : at, 0,
      { key: "queued", label: "대기 작업" + jobsNote, value: fmtNum(jobs.queued), onClick: jobsTo ? goto(jobsTo) : undefined });
  }

  // 서비스 타일의 이동 대상. 워커/스케줄러는 상단 경보와 동일하게 진단을 못 보는 역할이면
  // 작업 큐로 대체한다 — 같은 사실이 경보에선 클릭 가능한데 타일에선 죽어 보이면 안 된다.
  const { procTo } = dashboardNav(role);
  function compNav(k) {
    if (k === "web") return undefined;
    return procTo ? goto(procTo) : undefined;
  }
  // 문제(중단)와 응답 없음을 먼저 보여준다 — 연동이 많은 배포에서 '중단' 타일이 정상 타일들
  // 아래로 밀려 스크롤해야 찾던 문제. 같은 등급 안에서는 원래 삽입 순서가 안정 정렬로 유지된다.
  const rank = (s) => (s === "down" ? 0 : s === "warn" ? 1 : s === "unset" ? 2 : s === "off" ? 4 : 3);
  const compKeys = Object.keys(compStates).sort((a, b) => rank(compStates[a]) - rank(compStates[b]));
  const integKeys = Object.keys(integStates).sort((a, b) => rank(integStates[a]) - rank(integStates[b]));

  // 「처리한 작업이 한 건도 없다」 — 0 을 세 줄 늘어놓는 대신 한 문장으로 말하는 조건.
  // `total` 이 없거나(구형 응답) 0 이면 나머지 둘도 볼 것이 없다.
  const jobsQuiet = !(jobs.total > 0);
  const storage = storageState(d.storage);
  const fileCount = d.storage && typeof d.storage.file_count === "number" ? d.storage.file_count : null;
  const backupAgeDays = d.last_backup_at ? daysSince(d.last_backup_at) : null;

  return (
    <Box>
      {/* 백그라운드 폴링이 실패해 캐시된 값이 남았을 때, 헤더의 작은 접미 문구만으론 운영자가
          낡은 수치를 계속 최신처럼 읽기 쉽다 — 눈에 띄는 경고 배너로 올린다. */}
      {stale ? <Box sx={{ mb: 3 }} role="status" aria-live="polite"><Callout tone="warn">실시간 갱신이 실패했습니다. 표시된 값이 최신이 아닐 수 있습니다. 새로고침해 주세요.</Callout></Box> : null}

      {/* aria-live 래퍼 자체는 항상 마운트된 채로 두고 안의 자식만 바꾼다 — 래퍼가 통째로
          언마운트되면 전환 자체를 스크린리더가 놓친다. */}
      <Box aria-live="polite">
        <Section titleAs="h2" title="지금 상태">
          <StatusBand verdict={verdict} strip={stripItems} />
          <ActionQueue alerts={alerts} goto={goto} />
        </Section>
      </Box>

      {/* 같은 성격의 목록 둘을 넓은 화면에서 나란히 둔다. 남는 폭을 **줄 길이**로 쓰면
          이름과 배지가 2,100px 떨어져 한 줄로 안 읽힌다 — 이 앱의 4K 규칙은 남는 폭을
          두 번째 열로 보내는 것이다(density.js). 둘 다 짧은 목록이라 한 줄 안에서 키가
          맞지 않아도 그 차이가 화면을 밀지 않는다.

          균등 2열은 **양쪽 다 목록일 때만** 켠다(재검수 §19 — 실브라우저에서 실측).
          외부 연동을 하나도 안 쓰는 설치(정상 상태, 위 주석)에서는 오른쪽이 문장 한
          줄뿐이라 균등 분할이 그 옆을 92% 빈 칸으로 남기고 왼쪽 목록만 두 줄로
          접어 눌렀다 — 트랙 폭이 내용 요구를 안 보고 있었다(D-343). 연동이 실제로
          있을 때는 양쪽 다 목록이라 원래 의도(나란히 두어 줄 길이를 줄인다)가
          그대로 맞는다. */}
      <Box sx={{ display: "grid", alignItems: "start", columnGap: 4, gridTemplateColumns: { xs: "minmax(0,1fr)", xl: integKeys.length ? "repeat(2, minmax(0,1fr))" : "minmax(0,1fr)" } }}>
      <Section titleAs="h2"
        title="필수 서비스"
        action={<Typography variant="body2" color="text.secondary">정상 {compCounts.ok} / {compCounts.total}</Typography>}
      >
        {/* build_dashboard()는 components를 항상 채워 돌려준다 — 이 가드는 실제로는 결코
            false가 될 수 없는 사전 방어다. 그래도 빈 목록을 아무 설명 없이 그리면 "비어
            보이는 것"과 "고장난 것"을 구분할 수 없으므로 문구를 둔다. */}
        {compKeys.length ? (
          <StatusList ariaLabel="필수 서비스">
            {compKeys.map((k) => (
              <StatusTile key={k} name={serviceLabel(k)} onClick={compNav(k)} ariaLabel={serviceLabel(k) + " 상세 열기"}>
                <Badge value={SERVICE_STATE_LABEL[compStates[k]]} kind={SERVICE_STATE_KIND[compStates[k]]} />
              </StatusTile>
            ))}
          </StatusList>
        ) : <Note sx={{ mt: 0 }}>서비스 정보 없음</Note>}
      </Section>

      <Section titleAs="h2"
        title="외부 연동"
        action={integKeys.length
          ? <Typography variant="body2" color="text.secondary">정상 {integCounts.ok} / {integCounts.total}</Typography>
          : null}
      >
        {/* 🔴 **하나도 없는 것은 장애가 아니다.** 이 설치가 바깥으로 나가는 호출을 안 쓴다는
            정상 상태이고, 그렇게 말한다. 예전에는 이 구역이 아예 사라져서 「연동 기능이
            없는 제품」처럼 보였고, 반대로 걷어낸 런타임의 죽은 등록 행이 남아 있을 때는
            전부 빨간 「중단」이었다. */}
        {integKeys.length ? (
          <StatusList ariaLabel="외부 연동">
            {integKeys.map((k) => (
              <StatusTile key={k} name={serviceLabel(k)} onClick={goto("/diagnostics")} ariaLabel={serviceLabel(k) + " 연동 상태를 진단에서 보기"}>
                <Badge value={SERVICE_STATE_LABEL[integStates[k]]} kind={SERVICE_STATE_KIND[integStates[k]]} />
              </StatusTile>
            ))}
          </StatusList>
        ) : (
          <Note sx={{ mt: 0 }}>추가된 외부 연동이 없습니다. 이 설치는 바깥으로 나가는 호출을 쓰지 않습니다.</Note>
        )}
      </Section>
      </Box>

      <Box sx={BOTTOM_GRID}>
      {/* 운영 자료 셋 — 값이 몇 개뿐이라 각자 한 구역을 차지하지 않는다. 한 구역 안에서
          옅은 함몰면 셋으로 나눈다(위 `OpsGroup` 주석). */}
      <Section titleAs="h2" title="운영">
        <Box sx={OPS_GRID}>
          <OpsGroup title="파일 저장소">
            <Fact
              label="상태"
              value={<Badge value={SERVICE_STATE_LABEL[storage.state]} kind={SERVICE_STATE_KIND[storage.state]} />}
            />
            <Fact label="보관 파일" value={fileCount == null ? "-" : fmtNum(fileCount) + "개"} />
            <Note sx={{ mt: 1 }}>{storage.detail}</Note>
            {d.storage && d.storage.warning ? <Note sx={{ mt: 0.75 }}>{d.storage.warning}</Note> : null}
            {role === "system_admin" ? <OpsLink label="저장소 설정" onClick={goto(STORAGE_TO)} /> : null}
          </OpsGroup>

          <OpsGroup title="백업">
            {/* 상태가 첫 줄이다 — 세 묶음이 같은 순서로 읽히게 한다. */}
            <Fact
              label="상태"
              value={d.last_backup_status ? <Badge value={d.last_backup_status} /> : "기록 없음"}
            />
            <Fact
              label="마지막 성공"
              value={d.last_backup_at ? fmtDateTime(d.last_backup_at) : "없음"}
              tone={!d.last_backup_at ? "warning" : undefined}
            />
            {/* 오래된 백업 배지는 system_admin에게는 이미 위 조치 목록에 같은 사실이 행으로
                떠 있다 — 그 역할이 아니면 여기가 그 사실을 보여주는 유일한 자리다. */}
            {backupAgeDays != null ? (
              <Fact
                label="경과"
                value={Math.floor(backupAgeDays) + "일 전"}
                tone={backupAgeDays > BACKUP_STALE_DAYS ? (backupAgeDays > BACKUP_STALE_DAYS * 2 ? "error" : "warning") : undefined}
              />
            ) : null}
            <OpsLink label="백업 관리" onClick={goto("/backup")} />
          </OpsGroup>

          <OpsGroup title="최근 24시간 작업">
            {/* 성공률은 이 24시간 지표군의 하나이지만 위 스트립·조치 목록과 겹치는 값이라
                여기서는 뺐다 — 나머지 셋은 스트립·경보 어디에도 없는 유일한 자리다.
                이 값들에는 시계열이 없다(백엔드가 24시간 집계 스칼라만 내려준다) — 없는
                추세선을 그리면 한 점을 선으로 잇는 거짓말이 된다.

                🔴 **한 건도 없으면 0 을 셋 늘어놓지 않는다.** 실측(2026-08-26)에서 이 칸이
                「처리 요청 0 · 성공 0 · 평균 처리 -」 세 줄이었다. 세 줄을 다 읽고 나서야
                「아무 일도 없었다」를 알게 되는데, 그것은 한 문장이면 되는 사실이다. */}
            {jobsQuiet ? (
              <Note sx={{ mt: 0 }}>최근 24시간 동안 처리한 작업이 없습니다.</Note>
            ) : (
              <>
                <Fact label="처리 요청" value={fmtNum(jobs.total)} />
                <Fact label="성공" value={fmtNum(jobs.succeeded != null ? jobs.succeeded : 0)} />
                <Fact label="평균 처리" value={fmtProcessingTime(jobs.avg_processing_seconds)} />
              </>
            )}
            <OpsLink label="작업 큐" onClick={jobsTo ? goto(jobsTo) : undefined} />
          </OpsGroup>
        </Box>
      </Section>

      <RecentChanges
        rows={d.recent_critical_audit || []}
        role={role}
        nav={nav}
        revealedId={revealedId}
        onCopyId={copyObjectId}
      />
      </Box>
    </Box>
  );
}

/* 최근 주요 변경 — **언제 · 무엇을 · 어디에 · 누가**. 네 칸의 순서가 곧 읽는 순서다.
 *
 * 예전에는 한 칸이 「대상 종류, 8자로 자른 내부 ID」였고 실행자는 동작 뒤 괄호 안에 숨어
 * 있었다. 그래서 훑을 때 눈에 먼저 들어오는 것이 `c1929cb4…` 같은 내부 식별자였다. ID 는
 * 대상 이름 **뒤에** 작은 보조 표기로 두고, 실행자는 자기 칸을 갖는다.
 *
 * 서버가 다섯 줄까지만 준다(app/health/service.py 의 limit 5) — 안쪽 스크롤을 만들지 않고
 * 전체 보기 링크로 넘긴다. */
function RecentChanges({ rows, role, nav, revealedId, onCopyId }) {
  const canAudit = canGo("/audit", role);
  if (!rows.length) {
    return (
      <Section titleAs="h2" title="최근 주요 변경">
        {/* 비어 보이는 두 경우(실제로 없음 / 권한이 없어 서버가 아예 안 내려줌)를 구분한다 —
            안 그러면 감사 로그 열람 권한이 없는 역할은 '아무 변경도 없었다'로 오해한다. */}
        <Note sx={{ mt: 0 }}>
          {canAudit ? "최근 주요 변경 이력이 없습니다." : "감사 로그 열람 권한이 없어 숨겨졌습니다."}
        </Note>
      </Section>
    );
  }
  return (
    <Section titleAs="h2"
      title="최근 주요 변경"
      action={canAudit
        ? <Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav("/audit")}>전체 보기 →</Link>
        : null}
    >
      {/* 공용 표다 — 예전에는 머리글 줄과 격자 행을 손으로 그린 표였고, 그래서 열 폭·정렬·
          자릿수 규칙이 다른 표와 따로 살았다. 열 정의만 남기고 그리기는 `DataTable` 이 한다.
          행 key 는 안정 키다 — 30초 폴링마다 새 항목이 앞에 붙으므로 index 는 행을 위치로
          재사용해 어긋난다. 대상 ID 의 복사·펼침(`c-id-selectable`)은 대상 칸 안에 그대로다. */}
      <ListCard>
        <DataTable
          rows={rows}
          rowKey={(a) => a.created_at + "|" + (a.object_id || "") + "|" + a.action}
          columns={[
            { key: "created_at", label: "시각", type: "datetime", render: (a) => fmtDateTime(a.created_at) },
            {
              key: "action", label: "동작", type: "text", rowName: (a) => actionOnly(a.action, a.object_type),
              render: (a) => <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold }}>{actionOnly(a.action, a.object_type)}</Box>,
            },
            { key: "object", label: "대상", type: "name", render: (a) => (
              <Box sx={{ minWidth: 0, display: "flex", alignItems: "baseline", gap: 0.75, flexWrap: "wrap" }}>
                <Typography variant="body2" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>{objKo(a.object_type)}</Typography>
                {/* 이름이 있으면(현재는 object_type "user") 그 이름을 보여준다 — 예전엔 이
                    자리가 항상 UUID 앞머리였다(재감사 C16). 이름이 없는 대상만 줄인 ID로
                    물러난다: …을 붙여 '전체 값'처럼 보이지 않게 하고, 눌러서 복사할 수
                    있게 한다(title 툴팁은 터치·스크린리더에서 안 보인다). 어느 쪽이든
                    object_id 자체는 title/aria-label과 클립보드 복사에 그대로 남는다 —
                    지원 문의 등에서 정확한 값을 찾아야 하는 경우가 있다. */}
                {a.object_id ? (
                  <Link
                    component="button" type="button" underline="hover"
                    color={a.object_label ? "text.primary" : "text.secondary"}
                    title={a.object_label ? `${a.object_label} (${a.object_id})` : a.object_id}
                    aria-label={objKo(a.object_type) + " " + (a.object_label || "전체") + " ID 복사: " + a.object_id}
                    onClick={() => onCopyId(a.object_id)}
                    sx={{ fontSize: FONT_SIZE.caption, textAlign: "left", fontVariantNumeric: "tabular-nums" }}
                  >
                    {a.object_label || targetId(a.object_id)}
                  </Link>
                ) : null}
                {revealedId && revealedId === a.object_id ? (
                  <Typography className="c-id-selectable" variant="caption" color="text.secondary" tabIndex={0}
                    sx={{ flexBasis: "100%", wordBreak: "break-all", userSelect: "all" }}>
                    {a.object_id}
                  </Typography>
                ) : null}
              </Box>
            ) },
            { key: "actor", label: "실행자", type: "name", render: (a) => a.actor || "시스템" },
          ]}
        />
      </ListCard>
    </Section>
  );
}
