"""이관 한 회차가 무엇을 했고 무엇이 남았는가 (S13).

## 「초록」이라는 말을 쓰지 않는다

이 보고서는 통과/실패를 내지 않고 **수와 사유**를 낸다. 통과 판정은 Exit 조건이 하는
일이고(MASTER_PLAN §9.1: 무결성 전항 0 · 길이 초과 0 · 충돌 0), 그 판정은 `validate.py`
가 항목별로 내린다. 여기서 한 번 더 뭉치면 「어느 항이 왜 안 됐나」를 다시 물어야 한다.

## Finding 은 실패가 아니다

「임의로 배정하지 않았다」는 결과도 Finding 이다(U11). 그래서 각 Finding 은 **분류
(`kind`)** 를 들고, Exit 판정은 「분류되지 않은 것이 0인가」를 본다 — 「Finding 이
0인가」가 아니다. 분류된 예외를 0으로 만들려면 데이터를 지어내는 수밖에 없다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

__all__ = [
    "SEVERITY_BLOCKING", "SEVERITY_CLASSIFIED", "SEVERITY_NOTE",
    "Finding", "Check", "StageResult", "MigrationReport",
]

# 이관을 「끝났다」라고 부를 수 없게 만드는 것. Exit 조건이 이 수를 본다.
SEVERITY_BLOCKING = "blocking"
# 사람이 하나씩 결정할 일로 분류해 남긴 것. 0 이 되는 것이 목표가 아니다.
SEVERITY_CLASSIFIED = "classified"
# 사실 기록. 판정에 안 들어간다.
SEVERITY_NOTE = "note"


@dataclass
class Finding:
    """무엇이 어디서 왜."""

    severity: str
    kind: str
    where: str
    detail: str
    ref: str | None = None

    def line(self) -> str:
        tail = f" ({self.ref})" if self.ref else ""
        return f"[{self.severity}/{self.kind}] {self.where}: {self.detail}{tail}"


@dataclass
class Check:
    """검증 한 항. **`expected` 와 `actual` 을 함께 남긴다.**

    「통과」만 남기면 다음 사람이 「몇 건을 봤는가」를 못 읽는다 — 아무것도 안 세고
    통과한 검사와 구별되지 않는다.
    """

    name: str
    ok: bool
    expected: object
    actual: object
    detail: str = ""

    def line(self) -> str:
        mark = "OK  " if self.ok else "FAIL"
        body = f"{mark} {self.name}: 기대 {self.expected!r} / 실제 {self.actual!r}"
        return f"{body} — {self.detail}" if self.detail else body


@dataclass
class StageResult:
    """단계 하나가 옮긴 수."""

    name: str
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    source_rows: int = 0
    seconds: float = 0.0

    def line(self) -> str:
        return (
            f"{self.name}: 소스 {self.source_rows} → 신규 {self.inserted} · "
            f"갱신 {self.updated} · 건너뜀 {self.skipped} ({self.seconds:.1f}s)"
        )


@dataclass
class MigrationReport:
    started_at: str = ""
    finished_at: str = ""
    mode: str = "dry-run"
    source_sqlite: str = ""
    target_database: str = ""
    source_fingerprint: dict = field(default_factory=dict)
    notion: dict = field(default_factory=dict)
    stages: list[StageResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    # ── 쌓기 ─────────────────────────────────────────────────────────────────

    def add(self, stage: StageResult) -> StageResult:
        self.stages.append(stage)
        return stage

    def finding(self, severity: str, kind: str, where: str, detail: str,
                ref: str | None = None) -> None:
        self.findings.append(Finding(severity, kind, where, detail, ref))

    def check(self, name: str, ok: bool, expected, actual, detail: str = "") -> Check:
        row = Check(name=name, ok=ok, expected=expected, actual=actual, detail=detail)
        self.checks.append(row)
        return row

    # ── 읽기 ─────────────────────────────────────────────────────────────────

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_BLOCKING]

    @property
    def classified(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_CLASSIFIED]

    @property
    def failed_checks(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def passed(self) -> bool:
        """Exit 조건. **검사가 하나도 없으면 통과가 아니다** (D-213)."""
        return bool(self.checks) and not self.failed_checks and not self.blocking

    # ── 내보내기 ─────────────────────────────────────────────────────────────

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "source_sqlite": self.source_sqlite,
            "target_database": self.target_database,
            "source_fingerprint": self.source_fingerprint,
            "notion": self.notion,
            "passed": self.passed,
            "counts": self.counts,
            "stages": [asdict(s) for s in self.stages],
            "checks": [asdict(c) for c in self.checks],
            "findings": [asdict(f) for f in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, default=str)

    def to_text(self) -> str:
        lines: list[str] = []
        lines.append(f"# Migration {self.mode}")
        lines.append(f"소스   {self.source_sqlite}")
        lines.append(f"대상   {self.target_database}")
        lines.append(f"기간   {self.started_at} ~ {self.finished_at}")
        if self.source_fingerprint:
            lines.append("지문   " + "  ".join(
                f"{k}={v}" for k, v in sorted(self.source_fingerprint.items())
            ))
        if self.notion:
            lines.append("Notion " + "  ".join(
                f"{k}={v}" for k, v in sorted(self.notion.items())
                if k not in ("databases", "out_of_scope")
            ))
        lines.append("")
        lines.append("## 단계")
        for stage in self.stages:
            lines.append("  " + stage.line())
        lines.append("")
        lines.append("## 검증")
        for check in self.checks:
            lines.append("  " + check.line())
        lines.append("")
        lines.append("## Finding")
        if not self.findings:
            lines.append("  없음")
        for finding in self.findings:
            lines.append("  " + finding.line())
        lines.append("")
        lines.append(
            f"판정: {'PASS' if self.passed else 'FAIL'} — "
            f"검사 {len(self.checks)}건 중 실패 {len(self.failed_checks)} · "
            f"blocking {len(self.blocking)} · 분류된 예외 {len(self.classified)}"
        )
        return "\n".join(lines)
