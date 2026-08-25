/* 딥링크 쿼리를 소비할 때 **이 화면 자신의 조건까지 지우지 않는다** (S18 · W8).
 *
 * `onQuery` 를 가진 화면은 해시 쿼리를 한 번 쓰고 지운다 — `?job_id=…` 같은 «의도» 가 재렌더
 * 때 다시 열리면 안 되기 때문이다. 그런데 그 청소가 **쿼리 전체**를 지우고 있었다. 그래서
 * `#/jobs?status=succeeded` 로 들어오면 주소에서 조건이 사라졌고, 두 가지가 함께 깨졌다:
 *
 *   * 조건이 걸린 링크를 공유하면 상대는 **다른 화면**을 본다.
 *   * 뒤로가기가 조건을 잃는다 — 앞 기록이 `#/jobs` 로 바뀌어 있으니 돌아갈 곳이 없다.
 *
 * S18 이 `admin_jobs` 의 「뒤로가기」 축을 실브라우저로 재다가 잡았다(FF-1414).
 *
 * 여기서 고정하는 것은 **청소가 남길 키 집합**이다. 그 집합이 `DataScreen` 의 그 한 줄이
 * 계산하는 값이고, 화면 렌더를 흉내 내는 것보다 이쪽이 흔들리지 않는다 — 렌더로 재면 화면이
 * 곧바로 자기 뷰를 주소에 되쓰기 때문에 **고쳐도 안 고쳐도 같은 결과**가 나온다(실제로 그랬다).
 */
import { describe, it, expect } from "vitest";

import { SHELL_QUERY_KEYS, keepQueryKeys, ownedQueryKeys } from "./datascreen-view.js";

/* `/jobs` 와 같은 모양 — 자기 조건 둘과, 다른 화면이 보내는 의도 키. */
const CONFIG = {
  key: "probe-jobs",
  filters: [
    { key: "status", type: "select", label: "상태" },
    { key: "job_type", type: "select", label: "유형" },
  ],
};

/** `DataScreen` 의 딥링크 청소가 남기는 키 집합 — 그 한 줄과 같은 계산이다. */
function kept(query) {
  return keepQueryKeys(query, SHELL_QUERY_KEYS.concat(ownedQueryKeys(CONFIG)));
}

describe("딥링크 쿼리 청소", () => {
  it("이 화면이 소유한 조건(q·page·필터)은 남는다", () => {
    expect(kept("status=succeeded")).toBe("status=succeeded");
    expect(kept("job_type=mail_send&page=2")).toBe("job_type=mail_send&page=2");
    expect(kept("q=%EC%8B%A4%ED%8C%A8")).toBe("q=%EC%8B%A4%ED%8C%A8");
  });

  it("그릇(탭 셸)이 소유한 키도 남는다", () => {
    expect(kept("tab=policy&status=failed")).toBe("tab=policy&status=failed");
  });

  it("반례 — 다른 화면이 보낸 의도 키는 지운다", () => {
    expect(kept("job_id=abc-1")).toBe("");
    expect(kept("schedule_run_id=r-9")).toBe("");
  });

  it("의도와 조건이 함께 오면 **의도만** 지운다", () => {
    expect(kept("job_id=abc-1&status=failed")).toBe("status=failed");
  });

  it("반례 — 셸 키만 남기던 예전 계산은 이 화면의 조건을 잃는다", () => {
    // 고치기 전의 계산. 이 줄이 통과하는 한, 위 시험들이 무엇을 지키는지 분명하다.
    expect(keepQueryKeys("status=succeeded", SHELL_QUERY_KEYS)).toBe("");
  });
});
