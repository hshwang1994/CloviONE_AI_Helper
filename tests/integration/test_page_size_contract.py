"""화면이 보내는 `page_size` 를 서버가 실제로 받아 주는가 (재검수 3라운드).

## 무엇이 조용히 깨져 있었나

문서 화면과 프로젝트 고르개가 `/api/projects?page_size=200` 을 불렀다. 서버 상한은 100
(`app/core/pagination.py::MAX_PAGE_SIZE`) 이라 그 질의는 **매번 422** 였고, 거절된 질의의
결과는 빈 배열이다. 그래서:

  * 문서 화면 좌측 내비에 프로젝트가 한 개도 안 나왔고,
  * 고르개는 고른 값의 이름을 못 찾아 UUID 를 그대로 사용자에게 보여 줬다.

아무 오류도 안 떴다. 정적 전량과 vitest 2,855 시험이 전부 초록이었다 — 프런트 시험의
대역이 **주소를 안 보고** 무조건 프로젝트를 돌려줬기 때문이다.

## 이 파일이 지키는 성질

두 가지다. 하나는 서버 쪽 계약(상한이 실제로 100이고 넘기면 422다)이고, 다른 하나는
**프런트가 그 상한을 알고 있는가** 다. 뒤엣것이 이 결함의 뿌리라, 시험은 프런트 소스에
적힌 상수를 읽어 서버 값과 맞춘다. 언어가 갈린 두 값이 갈라지는 순간 여기서 빨간불이 난다.

프런트 소스를 읽는 시험이 낯설 수 있어 적어 둔다: 이 저장소는 프런트 번들을 커밋하고
(`app/static/react/`) 그 소스도 같은 저장소에 있다. 두 층의 계약을 잇는 시험을 어느 한쪽
언어 안에만 두면, 잇는 값이 갈라진 사실을 **어느 쪽도** 못 본다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.core.pagination import MAX_PAGE_SIZE

pytestmark = pytest.mark.integration

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROJECT_QUERIES = REPO_ROOT / "frontend" / "src" / "screens" / "project-queries.js"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

# `PageParams` 를 쓰는 라우터의 목록 질의. 하나라도 상한을 넘기면 그 화면은 빈 목록을 받는다.
PAGE_PARAM_ENDPOINTS = ("/api/projects",)


def test_projects_rejects_over_cap_and_accepts_cap(client, login_as):
    """상한 그대로는 통과하고, 하나만 더 얹으면 422 다 — 계약의 양쪽을 다 본다."""
    login_as("admin")

    ok = client.get(f"/api/projects?page_size={MAX_PAGE_SIZE}")
    assert ok.status_code == 200, ok.text
    assert ok.json()["page_size"] == MAX_PAGE_SIZE

    over = client.get(f"/api/projects?page_size={MAX_PAGE_SIZE + 1}")
    assert over.status_code == 422, (
        "상한을 넘겼는데 통과했다 — 프런트의 상한 상수가 근거를 잃는다"
    )


def test_frontend_knows_the_same_cap():
    """프런트의 `MAX_PAGE_SIZE` 가 서버의 것과 같은 수인가."""
    source = PROJECT_QUERIES.read_text(encoding="utf-8")
    match = re.search(r"export const MAX_PAGE_SIZE\s*=\s*(\d+)\s*;", source)
    assert match, f"{PROJECT_QUERIES.name} 에 MAX_PAGE_SIZE 선언이 없다"
    assert int(match.group(1)) == MAX_PAGE_SIZE, (
        "프런트와 서버의 한 쪽 최대 건수가 갈라졌다 — 갈라지면 그 질의는 조용히 422 가 된다"
    )


def test_no_frontend_call_exceeds_the_cap():
    """`PageParams` 라우터를 부르는 자리에 상한을 넘는 리터럴이 없는가.

    숫자를 손으로 적는 것 자체를 막지는 않는다(적어야 읽히는 자리가 있다). 막는 것은
    **넘는 값**이다. 시험 파일은 뺀다 — 거절되는 값을 일부러 보내는 시험이 있어야 한다.
    """
    offenders = []
    pattern = re.compile(r"page_size=(\d+)")
    for path in FRONTEND_SRC.rglob("*.js*"):
        if any(part in ("node_modules",) for part in path.parts):
            continue
        if path.name.endswith((".test.js", ".test.jsx")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if not any(endpoint in line for endpoint in PAGE_PARAM_ENDPOINTS):
                continue
            for found in pattern.findall(line):
                if int(found) > MAX_PAGE_SIZE:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {line.strip()[:120]}")
    assert not offenders, (
        "서버가 거절할 page_size 를 보내는 자리가 있다(그 화면은 빈 목록을 받는다):\n"
        + "\n".join(offenders)
    )
