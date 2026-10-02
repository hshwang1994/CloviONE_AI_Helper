"""메일 DNS 조회의 문 하나 (계획 M7, D-551).

로컬 릴레이의 준비 점검(`app/mail/relay_readiness.py`)이 MX · TXT(SPF · DKIM · DMARC) · A · PTR 을 이 모듈로만 묻는다. `dnspython`
(`dns.*`)을 부르는 파일은 이것 하나다(가둠 시험 `tests/unit/test_mail_dns_containment.py`) - 해석기를 바꾸거나 시간 제한을 고칠 자리가
한 곳이다.

- 기본은 **시스템 해석기**다(이 서버가 실제로 메일을 보낼 때 보는 답). 공개 해석기와 견주는 것은 관리자가 넣은 주소(`compare_resolvers`)일
  때만이다 - 그 목록이 곧 허용 목록이다. DNS 는 HTTP 가 아니라 `OutboundClient` 의 허용 목록 밖이라 따로 둔다.
- 한 질의는 5초로 끊는다. 실패는 예외가 아니라 `Answer.error`(nxdomain · noanswer · timeout · error)다 - 준비 점검의 한 줄이 「모름」이
  될 뿐 점검 전체가 죽지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import dns.exception
import dns.resolver
import dns.reversename

TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class Answer:
    values: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class MailDns:
    """조회기 하나. 시험은 같은 메서드(`mx` · `txt` · `a` · `ptr`)를 가진 가짜를 끼운다."""

    def __init__(self, nameservers: list[str] | None = None, *, timeout: float = TIMEOUT_SECONDS) -> None:
        resolver = dns.resolver.Resolver(configure=not nameservers)
        if nameservers:
            resolver.nameservers = list(nameservers)
        resolver.timeout = timeout
        resolver.lifetime = timeout
        self._resolver = resolver
        self.label = ",".join(nameservers) if nameservers else "system"

    def _query(self, name: str, rtype: str) -> Answer:
        try:
            answer = self._resolver.resolve(name, rtype, raise_on_no_answer=False)
        except dns.resolver.NXDOMAIN:
            return Answer(error="nxdomain")
        except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
            return Answer(error="timeout")
        except (dns.resolver.NoNameservers, dns.resolver.NoAnswer):
            return Answer(error="noanswer")
        except dns.exception.DNSException:
            return Answer(error="error")
        if answer.rrset is None:
            return Answer(error="noanswer")
        values: list[str] = []
        for record in answer:
            if rtype == "TXT":
                values.append("".join(part.decode("utf-8", "replace") for part in record.strings))
            elif rtype == "MX":
                values.append(f"{record.preference} {str(record.exchange).rstrip('.').lower()}")
            else:
                values.append(str(record).rstrip(".").lower())
        return Answer(values=values)

    def mx(self, domain: str) -> Answer:
        """`["10 mx.example.com", …]` — 선호도 순."""
        got = self._query(domain, "MX")
        if got.ok:
            return Answer(values=sorted(got.values, key=lambda v: int(v.split()[0])))
        return got

    def txt(self, name: str) -> Answer:
        return self._query(name, "TXT")

    def a(self, name: str) -> Answer:
        return self._query(name, "A")

    def ptr(self, ip: str) -> Answer:
        try:
            name = dns.reversename.from_address(ip)
        except (dns.exception.SyntaxError, ValueError):
            return Answer(error="error")
        return self._query(str(name), "PTR")
