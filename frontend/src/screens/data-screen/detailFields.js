// 상세 드로어 필드 병합 — columns와 detailFields를 그냥 이어붙이면 같은 key가 두 화면(예: 러너의
// base_url/config_version)에 모두 정의된 경우 드로어에 같은 값이 두 번 보인다. key가 겹치면
// 먼저 오는(columns) 항목만 남기고 detailFields의 중복 항목은 버린다(레지스트리 작성자가 실수로
// 같은 필드를 두 번 넣어도 드로어가 조용히 두 배로 늘어나지 않게).
export function mergeDetailFields(config, columns) {
  const seen = new Set();
  const merged = [];
  [...(columns || config.columns || []), ...(config.detailFields || [])].forEach((c) => {
    if (c.key != null) {
      if (seen.has(c.key)) return;
      seen.add(c.key);
    }
    merged.push(c);
  });
  return merged;
}

export function detailTitle(row, columns) {
  const first = (columns || [])[0];
  // 열의 render(예: 날짜 KST 포맷)를 존중한다 — 원시 ISO 타임스탬프가 제목으로 새어 나오지 않게.
  // 단 render가 문자열/숫자가 아닌(배지 등 JSX) 값을 주면 원시 값으로 되돌린다(제목은 문자열이어야 함).
  if (first && first.render) {
    const rendered = first.render(row);
    if (typeof rendered === "string" || typeof rendered === "number") return String(rendered);
  }
  // columnsFrom 화면은 응답이 오기 전 한 프레임 동안 열이 비어 있을 수 있다 — 그때 first가
  // undefined면 여기서 크래시가 난다(드로어가 열려 있는 상태에서만 드러나는 결함).
  if (!first) return String(row.id || "상세");
  return String(row[first.key] != null ? row[first.key] : (row.id || "상세"));
}
