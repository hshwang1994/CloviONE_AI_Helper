/* 사람 한 명을 화면에서 **구분**해 보여주는 규칙 — 단일 정의.
 *
 * 사용자 지시(2026-08-04): "채팅 및 대화 및 댓글 작성 등을 할 때도 동명이인 등을 고려해
 * 어떤 조직의 어떤 부서인지 나와야 한다."
 *
 * 서버 쪽 짝은 app/core/people.py 다. 응답은 {user_id, display_name, dept, title, org} 를 준다.
 *
 * 왜 조직을 늘 그리지 않는가: 조직이 하나뿐인 설치에서 모든 이름 옆에 같은 조직명을 붙이면
 * 구분에 아무 도움이 안 되면서 줄만 길어진다. 조직이 둘 이상 보일 때만 붙인다 —
 * 그때가 조직이 실제로 사람을 가르는 순간이다.
 *
 * 가운뎃점(·)을 구분자로 쓰지 않는다. 이 제품은 화면 문구에서 그 문자를 쓰지 않기로 했다.
 */

/** 소속 한 줄. 비어 있는 조각은 건너뛴다. 소속이 아예 없으면 빈 문자열. */
export function affiliation(person, { withOrg = false } = {}) {
  if (!person) return "";
  const parts = [];
  if (withOrg && person.org) parts.push(person.org);
  if (person.dept) parts.push(person.dept);
  if (person.title) parts.push(person.title);
  return parts.join(" ");
}

/** 목록에서 고르는 자리용 — "김하나 (개발본부 팀장)". 소속이 없으면 이름만. */
export function personLabel(person, { withOrg = false } = {}) {
  if (!person) return "";
  const name = person.display_name || person.name || "";
  const aff = affiliation(person, { withOrg });
  return aff ? `${name} (${aff})` : name;
}

/** 이 목록에 조직이 둘 이상 섞여 있는가 — 조직을 그릴지 정하는 기준. */
export function needsOrg(people) {
  const seen = new Set();
  for (const p of people || []) {
    if (p && p.org) seen.add(p.org);
    if (seen.size > 1) return true;
  }
  return false;
}

/** 표시 이름이 겹치는 사람이 있는가. 겹치면 소속을 반드시 그려야 한다. */
export function hasDuplicateNames(people) {
  const seen = new Set();
  for (const p of people || []) {
    const name = (p && (p.display_name || p.name)) || "";
    if (!name) continue;
    if (seen.has(name)) return true;
    seen.add(name);
  }
  return false;
}
