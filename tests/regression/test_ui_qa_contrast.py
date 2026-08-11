"""CTR-05: 대비(WCAG) 검사가 하네스의 21개 자동 검사에 없었다 — 위반 넷(CTR-01/02/03/04)이
전 페이지 통과로 영원히 남는 근본원인이었다. `scripts/ui_qa/contrast.py`는 완성된 독립
스크립트였지만 `run.py`의 캡처 루프가 부르지 않았다.

여기서 확인하는 것: (1) `evaluate_contrast`/`contrast_verdict` 분리가 실제 페이지 없이도
동작한다(순수 함수) (2) `contrast`가 `assertions.CLASSES`에 등록돼 `--fail-on contrast`·
요약표·실패표가 이 축을 안다.
"""

from __future__ import annotations

from scripts.ui_qa import assertions
from scripts.ui_qa.contrast import contrast_verdict, evaluate_contrast


class _FakePage:
    """`page.evaluate(PROBE)` 한 호출만 흉내 낸다 — 실제 브라우저 없이 변환 로직만 본다."""

    def __init__(self, result: dict) -> None:
        self._result = result

    def evaluate(self, _script):
        return self._result


def test_evaluate_contrast_returns_the_probe_result_verbatim():
    fake = {"items": [{"text": "x", "ratio": 2.1}], "skipped": 3}
    page = _FakePage(fake)
    assert evaluate_contrast(page) == fake


def test_contrast_verdict_fails_when_violations_present():
    probe_result = {
        "items": [
            {"tag": "a", "cls": "link", "text": "자세히 보기", "ratio": 3.76, "need": 4.5},
        ],
        "skipped": 2,
    }
    verdict = contrast_verdict(probe_result)
    assert verdict["status"] == "fail"
    assert verdict["count"] == 1
    assert "3.76" in verdict["samples"][0]
    # 위반이 있어도 판정불가 건수는 항상 note에 남는다 — 위반=0이 "다 확인했다"는 뜻이
    # 아니라는 것을 숨기지 않는다(CTR-05의 핵심 요구사항).
    assert "2건" in verdict["note"]


def test_contrast_verdict_passes_when_no_violations_but_still_reports_skipped():
    verdict = contrast_verdict({"items": [], "skipped": 5})
    assert verdict["status"] == "pass"
    assert verdict["count"] == 0
    assert "5건" in verdict["note"], "위반 0건이 '판정불가 5건'을 가리면 위양성처럼 보인다"


def test_contrast_verdict_caps_samples_at_max_samples():
    many = [{"tag": "p", "cls": "", "text": f"item{i}", "ratio": 1.0, "need": 4.5} for i in range(10)]
    verdict = contrast_verdict({"items": many, "skipped": 0}, max_samples=5)
    assert verdict["count"] == 10  # count는 전체를 세되
    assert len(verdict["samples"]) == 5  # 표시 샘플만 자른다


# CTR-05: 이 축이 --fail-on/요약표/실패표가 아는 CLASSES 목록에 실제로 등록돼 있는지.
# 등록만 빠져도 검사는 돌지만 리포트에 안 나온다(assertions.py 자체 주석이 이미 이 함정을
# 다른 modal_* 클래스에서 경고한다).
def test_contrast_is_registered_in_assertions_classes():
    assert "contrast" in assertions.CLASSES


def test_summarize_aggregates_the_contrast_class():
    per_page = [
        {"assertions": {"contrast": {"status": "fail", "count": 1}}},
        {"assertions": {"contrast": {"status": "pass", "count": 0}}},
    ]
    totals = assertions.summarize(per_page)
    assert totals["contrast"] == {"pass": 1, "fail": 1, "skip": 0}
