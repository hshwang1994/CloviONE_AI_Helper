"""메일 DNS 조회의 문은 하나다 (계획 M7, D-551).

`dnspython`(`dns.*`)을 부르는 제품 파일은 `app/mail/dns.py` 하나다. 해석기 · 시간 제한 · 실패 모양을 고칠 자리가 한 곳이어야 하고,
DNS 조회는 `OutboundClient` 의 허용 목록 밖이라 아무 데서나 부르게 두면 바깥으로 나가는 문이 흩어진다. 반례도 잰다 — 이 검사가
정말 import 를 찾는지(표본 수가 0 이 아닌지)."""

from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
ALLOWED = {pathlib.Path("app/mail/dns.py")}


def _imports_dns(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == "dns" or a.name.startswith("dns.") for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and (
                node.module == "dns" or node.module.startswith("dns.")):
            return True
    return False


def test_only_the_mail_dns_module_imports_dnspython():
    found = []
    checked = 0
    for path in (ROOT / "app").rglob("*.py"):
        checked += 1
        if _imports_dns(path.read_text(encoding="utf-8")):
            found.append(path.relative_to(ROOT))
    assert checked > 100, "app/ 의 파일을 거의 안 읽었다 - 검사가 헛돈다"
    assert set(found) == ALLOWED, f"dnspython 을 부르는 파일이 늘었다: {sorted(map(str, found))}"


def test_the_detector_finds_both_import_forms():
    assert _imports_dns("import dns.resolver\n")
    assert _imports_dns("from dns import resolver\n")
    assert not _imports_dns("from app.mail import dns\n"), "제품의 app.mail.dns 를 부르는 것은 괜찮다"
    assert not _imports_dns("import dnsutils\n")
