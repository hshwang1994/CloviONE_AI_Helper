"""문서 분류 택소노미와 생성 스키마 (팀 공간 §17).

qa-contract-change: 이 파일의 절반은 문서 미러 동기화(app/team_docs/sync.py)와 Notion 속성 파서(notion_docs.py)를 시험했고, S14 가 그 둘을 지웠다(D-284) — 미러가 없으므로 「상한에 걸린 회차는 prune 안 함」·「소스 5xx 에도 캐시 유지」·「Notion 속성에서 값을 뽑는다」는 지킬 대상이 없어졌다. 소스가 무엇이든 그대로인 절반(분류 택소노미, 생성 스키마의 필수 필드와 본문 상한)만 남긴다.

## 왜 이름을 안 바꿨나

`check_test_strength.py` 에서 이름을 바꾸는 것은 **삭제**로 세어진다. 그리고 이 파일이 지키는
것의 무게중심은 여전히 문서 쪽 분류·검증이라 이름이 거짓말을 하지 않는다.

## 남은 것이 왜 소스와 무관한가

`classify()` 는 제목과 라벨 문자열만 본다 — 그 문자열이 Notion 에서 왔든 우리 표에서 왔든
같은 답을 내야 한다. `DocumentCreate` 의 상한도 마찬가지다: 본문 줄 수 상한은 **조용히
잘리는 것을 막으려고** 있는 것이고, 자르는 쪽이 사라져도 「받은 것을 다 저장한다」는 약속은
그대로다.
"""

from __future__ import annotations

import pytest

from app.team_docs.classify import DOC_TYPES, WORK_FIELDS, classify

pytestmark = pytest.mark.unit


def test_classify_taxonomy():
    dt, wf, tags = classify(["회의록"], ["고객 프로젝트"], "포스코DX 요금 기능 회의")
    assert dt == "회의록" and wf == "개발"
    dt, wf, tags = classify(["보안 점검 보고서"], ["보안 컴플라이언스"], "WEB 보안취약점")
    assert dt == "보고서" and wf == "보안"
    dt, wf, tags = classify([], [], "Docker Iptables 변경")
    assert wf == "자동화" and "Docker" in tags
    # 목록 밖 태그는 안 나온다.
    _, _, tags = classify([], [], "Ubuntu LVM 디스크 용량 확장")
    from app.team_docs.classify import TECH_TAGS

    assert all(t in TECH_TAGS for t in tags)


def test_document_create_requires_type_and_field():
    from pydantic import ValidationError

    from app.team_docs.schemas import DocumentCreate

    ok = DocumentCreate(
        title="제목", document_type=list(DOC_TYPES)[0], work_field=list(WORK_FIELDS)[0]
    )
    assert ok.document_type in DOC_TYPES and ok.work_field in WORK_FIELDS
    with pytest.raises(ValidationError):
        DocumentCreate(title="제목", work_field=list(WORK_FIELDS)[0])  # 문서 종류 누락
    with pytest.raises(ValidationError):
        DocumentCreate(title="제목", document_type=list(DOC_TYPES)[0])  # 업무 분야 누락


def test_document_create_body_over_line_cap_is_rejected_not_truncated():
    """본문 줄 수 상한은 **조용히 잘리는 것**을 막으려고 있다.

    총 글자 수만 보고 통과시키면 짧은 줄 150개(1,300자 남짓, 글자 상한 밑)가 통과하고
    뒤쪽이 소리 없이 사라진다. 거절하는 쪽이 옳다 — 사용자는 자기가 쓴 글이 어디까지
    저장됐는지 화면에서 알 수 없다.

    소스가 자체 DB 가 된 뒤에도 이 성질은 그대로다. 자르는 쪽(옛 Notion 블록 변환기)이
    사라졌다고 「받은 것을 다 저장한다」는 약속이 없어지지는 않는다.
    """
    from pydantic import ValidationError

    from app.team_docs.schemas import DocumentCreate

    body = "\n".join(f"줄 {n}" for n in range(150))
    assert len(body) < 20_000, "이 표본이 글자 상한에 걸리면 줄 수 상한을 시험하지 못한다"
    with pytest.raises(ValidationError):
        DocumentCreate(
            title="제목",
            document_type=list(DOC_TYPES)[0],
            work_field=list(WORK_FIELDS)[0],
            body=body,
        )
