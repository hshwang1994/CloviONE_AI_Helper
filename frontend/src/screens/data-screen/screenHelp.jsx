import React from "react";
import { GuidanceBlock } from "../../ui/kit.jsx";

/* 목록 화면의 `?` 도움말 — **단독 화면과 탭 그릇이 같은 함수를 부른다** (D-453 · D-456).
 *
 * 예전에는 도움말 문장이 두 자리에서 따로 만들어졌다: 단독 화면은 `PageHeader help`,
 * 탭 그릇 안에서는 DataScreen 이 오른쪽 정렬 줄에 `Callout` 로. 그리고 준비물·절차·기대
 * 결과는 빈 상태(`EmptyState`)에만 있었다. 이 함수 하나가 셋을 합친다 — 문장 + (그 화면의
 * CTA 를 볼 수 있는 역할이면) 절차 안내. 그릇은 DataScreen 의 안을 몰라도 되고, 문장이 역할
 * 함수(`config.help(role)`)여도 여기서 푼다.
 */

/** 절차 안내를 볼 수 있는가 — 안내가 가리키는 단추(추가·주 동작)를 이 역할이 **지금** 보는가.
 *
 * `config.forceOnboarding` 은 안내가 웹 단추가 아니라 서버 절차를 말하는 화면(복구 리허설)이
 * 게이트를 우회하는 선언이다.
 *
 * 주 머리 동작에 `when(ctx)` 가 걸려 있으면 그 조건까지 본다 (P-88). 예전에는 `roles` 만
 * 봤다 — 「모두 읽음」처럼 읽을 것이 없으면 사라지는 주 동작을 두고, 도움말은 그 단추가
 * 있다고 말하고 머리에는 단추가 없는 화면이 만들어질 수 있었다. `ctx` 는 DataScreen 이
 * 목록 응답에서 뽑아 준다(`headerActionCtx`). 탭 그릇처럼 목록을 모르는 자리에서 부르면
 * `ctx` 가 없는데, 그때 `when` 이 걸린 동작은 **없는 것으로** 본다 — 조건을 모른 채 안내를
 * 내보내는 것보다 안내 하나가 빠지는 쪽이 덜 틀린다. */
export function canOnboardFor(config, role, ctx) {
  const ok = (roles) => !roles || (role != null && roles.includes(role));
  const nowVisible = (a) => !a.when || (ctx != null && !!a.when(ctx));
  if (config.forceOnboarding) return true;
  if (config.create && ok(config.create.roles)) return true;
  return (config.headerActions || []).some((a) => a.primary && ok(a.roles) && nowVisible(a));
}

/** `PageHeader help` 에 넣을 노드. 문장도 안내도 없으면 `null`(그러면 `?` 자체가 안 그려진다). */
export function buildScreenHelp(config, role, ctx) {
  const text = typeof config.help === "function" ? config.help(role) : (config.help || null);
  const guide = canOnboardFor(config, role, ctx)
    ? <GuidanceBlock prerequisite={config.emptyPrerequisite} steps={config.emptySteps} expected={config.emptyExpected} rule={!!text} />
    : null;
  const hasGuide = !!(config.emptyPrerequisite || (Array.isArray(config.emptySteps) && config.emptySteps.length) || config.emptyExpected);
  if (!text && !(guide && hasGuide)) return null;
  return (
    <>
      {text}
      {hasGuide ? guide : null}
    </>
  );
}
