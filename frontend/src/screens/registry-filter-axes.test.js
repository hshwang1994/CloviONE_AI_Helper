/* 서버가 목록을 자르는 화면에 「지금 화면에 받아 둔 것만 보는」 조건이 남아 있는가.
 *
 * ## 왜 이 검사가 있는가
 *
 * 목록이 쪽에서 묶음으로 바뀌면서, 부분만 받아 둔 자료 위에 건 조건은 전부 **조용한 거짓말**이
 * 된다. 오류가 안 나고 화면도 정상으로 보인다:
 *
 *   `clientFilter`   받아 둔 행만 걸러 놓고 전체 필터처럼 보인다
 *   `datalistFrom`   받아 둔 행에서 뽑은 후보를 「이 값들이 전부」처럼 보여 준다
 *   `optionsFrom`    같은 부류. 게다가 그 `items` 는 **지금 걸린 조건의 결과**다
 *
 * 지금까지 이 규칙을 지킨 것은 사람의 주의력이었다(registry 주석들이 「이 화면은 전량을 받으니
 * 괜찮다」고 근거를 적어 뒀다). 주의력은 언젠가 빠진다 — 실제로 감사 로그·프롬프트·정책 셋이
 * 그 상태였고, 사용자가 그것을 보고 신고했다.
 *
 * ## 왜 Python 정적 검사가 아니라 여기인가
 *
 * REGISTRY 는 일곱 파일의 **객체 조립 결과**(스프레드·계산된 키·조건부 병합)다. 정규식으로
 * 훑으면 조용히 놓친다 — `registry-surface-parity.test.js` 가 그 사고를 한 번 겪었다.
 * **JS 진실은 JS 가 증명한다.**
 */

import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";
import { NOTIFICATIONS_SCREEN } from "./registry/notifications.js";
import SORT_KEYS from "../generated/sortKeys.json";

const ALL = { ...REGISTRY, ...NOTIFICATIONS_SCREEN };
const entries = () => Object.entries(ALL);

describe("서버가 묶음을 자르는 화면의 조건 축", () => {
  it("조립 사고 감지 — 화면이 실제로 여럿 있다", () => {
    /* 이 단언이 없으면 registry 조립이 깨져 `ALL` 이 비어도 아래 검사들이 전부 초록이다.
       빈 집합을 보면서 통과하는 검사는 없는 것보다 나쁘다.
       바닥값 20 → 17: 조직·부서·조직도 셋이 registry 를 떠나 조직 콘솔(screens/org/)의
       자기 파일로 갔다 — 조립 사고가 아니라 기록된 이사다. */
    expect(entries().length).toBeGreaterThan(17);
  });

  it("clientFilter 는 전량을 받는 화면에만 있다", () => {
    const bad = [];
    for (const [key, cfg] of entries()) {
      if (!cfg.paginated) continue;
      for (const f of cfg.filters || []) {
        if (f.clientFilter) bad.push(`${key}.${f.key}`);
      }
    }
    expect(bad, `묶음을 자르는 화면인데 화면에서 거른다:\n${bad.join("\n")}`).toEqual([]);
  });

  it("후보 목록을 «받아 둔 행» 에서 뽑지 않는다 — 어느 화면에서도", () => {
    /* `paginated` 여부와 무관하게 금지한다. 전량을 받는 화면이라도 그 `items` 는 **지금 걸린
       조건의 결과**라, 목록에 필터를 건 채 폼을 열면 후보가 그만큼 좁아진다(상위 부서가
       실제로 그랬다). 조건과 무관한 후보는 `optionsFromRefList`(별도 질의)로 받는다. */
    const bad = [];
    for (const [key, cfg] of entries()) {
      for (const f of cfg.filters || []) {
        if (f.datalistFrom) bad.push(`${key}.filters.${f.key}: datalistFrom`);
        if (f.optionsFrom) bad.push(`${key}.filters.${f.key}: optionsFrom`);
      }
      for (const group of ["fields", "editFields", "detailFields"]) {
        for (const f of cfg[group] || []) {
          if (f && f.optionsFrom) bad.push(`${key}.${group}.${f.name || f.key}: optionsFrom`);
        }
      }
      for (const a of cfg.actions || []) {
        for (const f of a.fields || []) {
          if (f && f.optionsFrom) bad.push(`${key}.actions.${a.key || a.label}: optionsFrom`);
        }
      }
    }
    expect(bad, `후보를 받아 둔 행에서 뽑는다:\n${bad.join("\n")}`).toEqual([]);
  });

  it("상한만 있고 페이징이 없는 목록은 그 사실을 화면에 알린다", () => {
    /* `clientFilter` 를 그대로 두려면 「받아 둔 것이 곧 전부」여야 한다. 서버가 상한을 두는
       목록(`cap`)은 그 전제가 깨져 있으므로 최소한 잘렸다는 사실을 말해야 한다. */
    const bad = entries()
      .filter(([, c]) => (c.filters || []).some((f) => f.clientFilter))
      .filter(([, c]) => c.cap != null && c.capWarning !== c.cap)
      .map(([k]) => k);
    expect(bad, `상한이 있는데 잘림 경고가 없다: ${bad.join(", ")}`).toEqual([]);
  });

  it("죽은 검색 선언이 없다 — searchFields 는 검색창이 그려질 때만 뜻이 있다", () => {
    /* `showSearch = !inSplitView && (searchable || !paginated)` — 서버 검색이 없는
       paginated 화면은 검색창을 아예 안 그린다. 그 화면에 `searchFields` 가 남아 있으면
       다음 사람이 「검색이 되는 화면」으로 읽는다(UB-24 가 공지에서 실제로 겪은 결함). */
    const bad = entries()
      .filter(([, c]) => c.paginated && !c.searchable && (c.searchFields || c.searchPlaceholder))
      .map(([k]) => k);
    expect(bad, `검색창이 없는데 검색 선언이 있다: ${bad.join(", ")}`).toEqual([]);
  });
});
describe("정렬 화이트리스트는 서버와 한 벌이다", () => {
  /* 🔴 두 벌이 갈라지면 증상이 **조용하다.** 화면은 화살표를 그리고, 사용자는 누르고,
     서버는 모르는 키를 기본 정렬로 떨어뜨린다(그것이 옛 링크를 살리는 옳은 동작이다).
     결과는 「눌렀는데 순서가 그대로」이고 아무 데도 오류가 안 남는다.

     `sortKeys.json` 은 서버의 `SortSpec` 에서 뽑은 미러다
     (`scripts/generate_sort_keys.py` · 신선도는 `check_sort_keys_fresh.py` 가 고정한다). */

  it("serverSort 를 선언한 화면은 서버도 그 목록을 정렬한다", () => {
    const bad = [];
    for (const [key, cfg] of entries()) {
      if (!cfg.serverSort) continue;
      const mirror = SORT_KEYS[key];
      if (!mirror) { bad.push(`${key}: 서버에 정렬 계약이 없다`); continue; }
      for (const k of cfg.serverSort.keys || []) {
        if (!mirror.keys.includes(k)) bad.push(`${key}.${k}: 서버가 안 받는 키다`);
      }
      const def = cfg.serverSort.default;
      if (def && def.key && !mirror.keys.includes(def.key)) {
        bad.push(`${key}: 기본 정렬 ${def.key} 를 서버가 안 받는다`);
      }
    }
    expect(bad, bad.join("\n")).toEqual([]);
  });

  it("화살표를 그리는 열은 그 화면의 화이트리스트 안에 있다", () => {
    /* 화이트리스트 밖 열에 화살표를 그리면 눌러도 서버가 기본 정렬로 떨어뜨린다.
       `DataScreen` 이 런타임에도 같은 판정을 하지만, 선언 자체를 여기서 막아 둔다. */
    const bad = [];
    for (const [key, cfg] of entries()) {
      if (!cfg.serverSort) continue;
      const allowed = new Set(cfg.serverSort.keys || []);
      for (const c of cfg.columns || []) {
        if (c && c.sortable && !allowed.has(c.sortKey || c.key)) {
          bad.push(`${key}.${c.key}`);
        }
      }
    }
    expect(bad, `서버가 안 받는 열에 정렬 화살표를 선언했다:\n${bad.join("\n")}`).toEqual([]);
  });
});