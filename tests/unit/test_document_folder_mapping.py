"""이관해 온 문서를 폴더에 넣는 **규칙**을 시험이 지킨다 (마이그레이션 `0022`).

## 왜 규칙을 따로 시험하는가

마이그레이션은 한 번 돌고 끝난다. 규칙이 틀린 채로 돌면 문서 111건이 잘못된 자리에
앉고, 그 사실은 아무 오류도 안 낸다 — 사람이 「내 문서가 왜 여기 있지」를 만날 때까지
아무도 모른다. 되감을 수는 있지만(폴더를 지우면 문서가 공간 뿌리로 올라온다) 그때는
이미 사람들이 그 트리를 보고 있다.

그래서 판정을 순수 함수 하나로 꺼내 두고 여기서 본다. 여기서 보는 것 넷:

  1. **종류가 있으면 종류가 이긴다.** 옛 시스템의 「문서 종류」가 가장 확실한 근거다.
  2. **근거가 없으면 미분류다.** 빈 문서를 제목의 낱말 하나로 분류하지 않는다.
  3. **규칙의 순서가 뜻을 정한다** — 「서버정보 및 요구사항 협의서」는 운영이 아니라 계획이다.
  4. 규칙이 가리키는 폴더가 **실제로 만들어지는 폴더 목록 안에** 있다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load():
    path = PROJECT_ROOT / "alembic" / "versions" / "0022_document_folders.py"
    spec = importlib.util.spec_from_file_location("mig_0022_document_folders", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_document_type_decides_when_it_has_one():
    m = _load()
    assert m._folder_for("회의록", "아무 제목", 100) == m.MEETING
    assert m._folder_for("보안 점검 보고서", "아무 제목", 100) == m.SECURITY
    assert m._folder_for("Knowledge base", "아무 제목", 100) == m.KNOWLEDGE
    # 본문이 비어도 종류는 그대로 근거다 — 빈 회의록도 회의록이다.
    assert m._folder_for("회의록", "", 0) == m.MEETING


def test_every_known_type_lands_in_a_folder_that_gets_created():
    """🔴 규칙이 없는 폴더 이름을 가리키면 마이그레이션이 `KeyError` 로 죽는다.

    죽는 자리가 배포 중이라, 그때는 스키마가 반쯤 올라간 상태다.
    """
    m = _load()
    names = {name for name, _ in m.FOLDERS}
    for doc_type, folder in m.BY_DOC_TYPE.items():
        assert folder in names, f"{doc_type} 이 없는 폴더({folder})를 가리킨다"
    for needle, folder in m.BY_TITLE:
        assert folder in names, f"제목 규칙 {needle} 이 없는 폴더({folder})를 가리킨다"
    assert m.UNSORTED in names


def test_a_document_with_no_evidence_goes_to_the_unsorted_folder():
    """지시가 적은 그대로다 — 근거가 없으면 억지로 분류하지 않는다."""
    m = _load()
    assert m._folder_for("기타", "새문서", 0) == m.UNSORTED
    assert m._folder_for("기타", "(제목 없음)", 0) == m.UNSORTED
    assert m._folder_for(None, "cytoscape.js", 0) == m.UNSORTED
    # 종류를 모르고 제목에도 낱말이 없으면, 본문이 있어도 미분류다.
    assert m._folder_for("기타", "ERP", 500) == m.UNSORTED


def test_the_title_rules_run_in_order():
    """🔴 「인천공항공사 서버정보 및 요구사항 협의서」는 **계획**이다.

    「서버」가 먼저 잡으면 운영 폴더로 가는데, 그 문서는 서버 정보가 아니라 협의 문서다.
    규칙 순서가 곧 판정이라 여기서 못박는다.
    """
    m = _load()
    assert m._folder_for("기타", "인천공항공사 서버정보 및 요구사항 협의서", 438) == m.PLAN
    assert m._folder_for("기타", "인천공항공사 서버정보", 158) == m.OPS
    # 「스마일게이트 포탈 교육 및 OS 자동화 회의록」은 교육이 아니라 회의록이다.
    assert m._folder_for("기타", "[12/19] 스마일게이트 포탈 교육 및 OS 자동화 회의록", 1546) == m.MEETING


def test_the_real_shape_of_the_migrated_corpus_is_covered():
    """운영 DB 실측(2026-08-27)의 종류 15가지가 전부 규칙을 지난다.

    「기타」·「기타 문서」·없음 셋만 제목 규칙으로 내려가고, 나머지 열둘은 종류가 답한다.
    새 종류가 생기면 이 목록이 먼저 어긋난다 — 그때 규칙을 더할지 미분류로 둘지 정한다.
    """
    m = _load()
    measured = {
        "회의록": 24, "작업 계획서": 21, "기타": 17, "Knowledge base": 15,
        "고객사 별 배포 가이드": 9, "기타 문서": 5, "보안 점검 보고서": 5, "교육": 3,
        "포탈 개발 컨벤션": 3, "아키텍처 설계서": 2, "개발자 레퍼런스 문서": 2,
        "요구 사항 정의서": 1, "테스트 결과서": 1, "사용자 매뉴얼": 1, "Linux": 1,
    }
    assert sum(measured.values()) == 110, "실측 합이 110(종류가 있는 문서)이 아니다"
    unknown = [t for t in measured if t not in m.BY_DOC_TYPE]
    assert unknown == ["기타", "기타 문서"], f"규칙이 없는 종류가 늘었다: {unknown}"


def test_the_unsorted_folder_is_not_where_most_documents_end_up():
    """미분류가 커지면 분류를 안 한 것과 같다.

    실측 23건(종류가 「기타」류인 것) 중 제목이 근거를 주는 17건은 제 폴더로 가고, 남는
    것은 여섯이다 — 빈 문서 다섯과 제목만 있는 하나.
    """
    m = _load()
    corpus = [
        ("기타", "새문서", 0),
        ("기타", "인천공항공사 서버정보", 158),
        ("기타", "인천공항공사 서버정보 및 요구사항 협의서", 438),
        ("기타", "외부시스템 개념 정의서", 21),
        ("기타", "조민 인수인계 체크리스트", 0),
        ("기타", "(제목 없음)", 0),
        ("기타", "(제목 없음)", 0),
        ("기타", "[12/19] 스마일게이트 포탈 교육 및 OS 자동화 회의록", 1546),
        ("기타", "하이닉스 5월 19일 기준 엔티티 정의", 1052),
        ("기타", "branch-comparison-report", 10324),
        ("기타", "CLI AI", 800),
        ("기타", "cytoscape.js", 0),
        ("기타", "Docker로 로컬 Oracle DB 설치하기", 482),
        ("기타", "암센터 EOS 작업", 788),
        ("기타", "ERP 서버", 33),
        ("기타", "ovf 배포 시 에러사항", 2692),
        ("기타", "timedatacetl  Asia/Seoul 설정", 708),
        ("기타 문서", "신입 직원 교육 커리큘럼", 14),
        ("기타 문서", "CI/CD 고도화 check list", 1621),
        ("기타 문서", "ClovirONE 고객사 JAR 결합 및 WAR 실행 작업 정리", 4778),
        ("기타 문서", "실무자를 위한 TCP/IP 네트워크 기본 과정 교육 자료 공유", 7328),
        ("기타 문서", "사내 포탈 VM", 888),
        (None, "Postman 대체 Bruno 소프트웨어 추천", 0),
    ]
    placed = [m._folder_for(*row) for row in corpus]
    assert len(corpus) == 23
    assert placed.count(m.UNSORTED) == 6, f"미분류가 여섯이 아니다: {placed.count(m.UNSORTED)}"
    assert placed.count(m.MEETING) == 1
    assert placed.count(m.TRAINING) == 2
    assert placed.count(m.OPS) == 7
