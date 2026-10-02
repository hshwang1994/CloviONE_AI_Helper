"""로컬 릴레이 준비 점검 (계획 M7, D-551).

「로컬 릴레이를 켰다」와 「받는 쪽까지 간다」는 다른 일이다. 이 점검은 화면의 「바깥으로 보내기 준비」 표를 만든다. 각 줄은 **지금 상태 ·
무엇이 필요한가 · 어디서 고치는가**를 한 문장씩 말하고 상태는 정상(ok) · 주의(warn) · 실패(fail) · 모름(unknown) 넷이다.

공통 — 구성 요소가 설치됐는가 · 동작하는가 · 받는 문이 루프백 2525 하나인가 · 앱이 릴레이에 인증서로 붙어 봉투 시험을 지나는가.
상위 SMTP — 상위 서버에 연결 · 보안 연결 · 로그인 · 봉투 시험.
인터넷으로 직접 전달 — 바깥 IP · 바깥 25번 · 받는 쪽 MX(시스템 해석기 대 공개 답 - 분리 DNS 를 잡는다) · 보내는 도메인 · SPF · DKIM ·
DMARC · 역방향 이름(PTR) · 서버 이름(HELO)의 DNS.

판정 함수는 순수하다(가짜 해석기 · 가짜 헬퍼로 시험한다). 결과는 `sync_status["mail_relay"]` 한 행에 남고, 화면과 초기 설정(M6)이 읽는다.
**메일은 보내지 않는다** - 바깥 25번 시험은 인사(EHLO)까지, 봉투 시험은 RSET 으로 끝난다.
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.text import topic_particle
from app.mail import relay_certs, relay_files as rf
from app.mail.config import DELIVERY_SMARTHOST, MailConfig

COMPONENT = "mail_relay"
OK, WARN, FAIL, UNKNOWN = "ok", "warn", "fail", "unknown"
SPF_LOOKUP_LIMIT = 10
_SPF_DOMAIN = re.compile(r"^(?=.{1,253}\.?$)(?:[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\.?$")
QUAL = {"+": "pass", "-": "fail", "~": "softfail", "?": "neutral"}

LABELS = {
    "relay_installed": "메일 발송 구성 요소",
    "relay_running": "로컬 릴레이 동작",
    "relay_managed": "받는 문",
    "app_to_relay": "앱에서 릴레이로",
    "smarthost_connect": "상위 SMTP 서버",
    "egress_ip": "바깥 IP",
    "outbound_25": "바깥 25번 연결",
    "recipient_mx": "받는 쪽 메일 서버(MX)",
    "sender_domain_public": "보내는 도메인",
    "spf": "SPF",
    "dkim": "DKIM",
    "dmarc": "DMARC",
    "ptr_fcrdns": "역방향 이름(PTR)",
    "helo_dns": "서버 이름(HELO)",
}


def row(key: str, state: str, message: str, *, need: str | None = None, where: str | None = None,
        technical: str | None = None) -> dict:
    return {"key": key, "label": LABELS[key], "state": state, "message": message, "need": need, "where": where,
            "technical": (technical or "")[:300] or None}


# ── 공통 ─────────────────────────────────────────────────────────────────────


def component_rows(status: dict | None, *, dkim: bool) -> list[dict]:
    """헬퍼 `mailrelay.status` 결과 → 설치 · 동작 · 받는 문 세 줄. 헬퍼가 없으면 모름이다."""
    if not status:
        why = "이 서버의 시스템 도우미에 닿지 못해 구성 요소 상태를 알 수 없습니다."
        return [row("relay_installed", UNKNOWN, why), row("relay_running", UNKNOWN, why), row("relay_managed", UNKNOWN, why)]
    component = status.get("component")
    out: list[dict] = []
    if component == "not_installed":
        out.append(row("relay_installed", FAIL, "이 서버에는 로컬 릴레이 구성 요소가 설치되지 않았습니다.",
                       need="구성 요소를 설치하거나 외부 SMTP 사용을 고르세요.",
                       where="서버에서 clovirassist mail-relay install"))
    elif component == "foreign":
        out.append(row("relay_installed", FAIL, "이 서버에는 기존 메일 발송 구성이 있습니다.",
                       need="그 구성을 쓰려면 외부 SMTP 사용에서 그 서버를 지정하세요.", where="메일 설정"))
    else:
        out.append(row("relay_installed", OK, "구성 요소가 설치돼 있습니다."))
    if component == "running":
        out.append(row("relay_running", OK, "로컬 릴레이가 동작하고 있습니다."))
    elif component in ("ready", "stopped"):
        out.append(row("relay_running", FAIL, "메일 발송 구성 요소가 동작하지 않습니다." if component == "stopped"
                       else "로컬 릴레이가 꺼져 있습니다.", need="로컬 릴레이를 켜세요.", where="메일 설정의 로컬 릴레이"))
    else:
        out.append(row("relay_running", UNKNOWN, "구성 요소가 없어 동작을 확인하지 않았습니다."))
    heard = list(status.get("listeners") or [])
    expected = {f"{rf.RELAY_HOST}:{rf.RELAY_PORT}"} | ({f"127.0.0.1:{rf.MILTER_PORT}"} if dkim else set())
    if component != "running":
        state = OK if not heard else WARN
        out.append(row("relay_managed", state, "아무 받는 문도 열려 있지 않습니다." if not heard
                       else "꺼져 있는데 듣는 소켓이 있습니다.", technical=", ".join(heard)))
    elif set(heard) == expected:
        out.append(row("relay_managed", OK, "받는 문은 이 서버 안(127.0.0.1:2525) 하나이고 25번은 닫혀 있습니다.",
                       technical=", ".join(heard)))
    else:
        out.append(row("relay_managed", FAIL, "받는 문이 예상과 다릅니다.", need="로컬 릴레이를 다시 적용하세요.",
                       where="메일 설정의 로컬 릴레이", technical=", ".join(heard)))
    return out


def app_to_relay_row(result: dict | None, error: str | None) -> dict:
    if error:
        return row("app_to_relay", FAIL, "앱이 로컬 릴레이에 메일을 넘기지 못했습니다.", need="로컬 릴레이를 다시 적용하세요.",
                   where="메일 설정의 로컬 릴레이", technical=error)
    if result is None:
        return row("app_to_relay", UNKNOWN, "로컬 릴레이가 동작하지 않아 시험하지 않았습니다.")
    return row("app_to_relay", OK, "앱이 인증서로 로컬 릴레이에 붙어 받는 사람까지 확인했습니다.")


def smarthost_row(result: dict | None, error: str | None) -> dict:
    if error:
        return row("smarthost_connect", FAIL, "상위 SMTP 서버에 연결하거나 로그인하지 못했습니다.",
                   need="서버 주소, 보안 연결, 계정, 비밀번호를 확인하세요.", where="메일 설정의 상위 SMTP 이용", technical=error)
    return row("smarthost_connect", OK, "상위 SMTP 서버에 연결해 로그인과 봉투 시험을 지났습니다.")


# ── 인터넷으로 직접 전달 ─────────────────────────────────────────────────────


def _ip_in(ip: str, network: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(network if "/" in network else f"{network}/32",
                                                                strict=False)
    except ValueError:
        return False


class SpfPermError(Exception):
    pass


def spf_check(lookup, domain: str, ip: str) -> tuple[str, str]:
    """SPF 판정 — `(결과, 설명)`. 결과는 pass · fail · softfail · neutral · none · permerror · temperror.

    다루는 것: ip4 · ip6(건너뜀) · a · mx · include · redirect · all · exists(이름만). 조회는 열 번까지 센다(RFC 7208). include 대상이
    도메인 모양이 아니면 permerror 다(`goodmit.co.kr` 랩 관찰처럼). 매크로(`%{…}`)는 판정하지 않는다(모름 = neutral).
    """
    count = [0]

    def lookup_count() -> None:
        count[0] += 1
        if count[0] > SPF_LOOKUP_LIMIT:
            raise SpfPermError("DNS 조회가 10번을 넘습니다.")

    def evaluate(dom: str, depth: int) -> str:
        if depth > SPF_LOOKUP_LIMIT:
            raise SpfPermError("SPF 가 너무 깊이 이어집니다.")
        got = lookup.txt(dom)
        if not got.ok and got.error not in ("nxdomain", "noanswer"):
            return "temperror"
        records = [v for v in got.values if v.lower().startswith("v=spf1")]
        if not records:
            return "none"
        if len(records) > 1:
            raise SpfPermError(f"{dom} 에 SPF 레코드가 둘 이상 있습니다.")
        redirect = None
        for term in records[0].split()[1:]:
            qualifier = term[0] if term[0] in "+-~?" else "+"
            body = term[1:] if term[0] in "+-~?" else term
            if "%" in body:
                return "neutral"
            lowered = body.lower()
            if lowered.startswith("redirect="):
                redirect = body.split("=", 1)[1]
                continue
            if "=" in lowered.split(":", 1)[0]:
                continue
            name, _, arg = body.partition(":")
            name = name.lower()
            if name.startswith(("a/", "mx/")):
                name, _, cidr = name.partition("/")
                arg = f"{arg}/{cidr}" if arg else f"/{cidr}"
            if name == "all":
                return QUAL[qualifier]
            if name == "ip4":
                if _ip_in(ip, arg):
                    return QUAL[qualifier]
                continue
            if name == "ip6":
                continue
            if name in ("a", "mx"):
                lookup_count()
                target, _, cidr = (arg or "").partition("/")
                target = target or dom
                hosts = [target] if name == "a" else [v.split()[1] for v in lookup.mx(target).values]
                for host in hosts[:10]:
                    for addr in lookup.a(host).values:
                        if _ip_in(ip, f"{addr}/{cidr}" if cidr else addr):
                            return QUAL[qualifier]
                continue
            if name == "include":
                lookup_count()
                if not _SPF_DOMAIN.match(arg or ""):
                    raise SpfPermError(f"include 대상이 도메인이 아닙니다: {arg}")
                sub = evaluate(arg.rstrip("."), depth + 1)
                if sub == "pass":
                    return QUAL[qualifier]
                if sub == "none":
                    raise SpfPermError(f"include 대상 {arg} 에 SPF 레코드가 없습니다.")
                if sub in ("permerror", "temperror"):
                    return sub
                continue
            if name == "exists":
                lookup_count()
                if lookup.a(arg).values:
                    return QUAL[qualifier]
                continue
            if name == "ptr":
                lookup_count()
                continue
            raise SpfPermError(f"모르는 SPF 항목입니다: {term}")
        if redirect:
            lookup_count()
            if not _SPF_DOMAIN.match(redirect):
                raise SpfPermError(f"redirect 대상이 도메인이 아닙니다: {redirect}")
            sub = evaluate(redirect.rstrip("."), depth + 1)
            if sub == "none":
                raise SpfPermError(f"redirect 대상 {redirect} 에 SPF 레코드가 없습니다.")
            return sub
        return "neutral"

    try:
        result = evaluate(domain, 0)
    except SpfPermError as exc:
        return "permerror", str(exc)
    return result, ""


def _broken_spf_terms(record: str) -> list[str]:
    """SPF 레코드에서 대상이 도메인이 아닌 include · redirect 항목 — 그 하나로 레코드 전체가 오류(permerror)다.

    랩의 goodmit.co.kr 은 Google 사이트 확인 값(`google-site-verification=…`)을 include 로 적어 두었다. 그 값은 SPF 가 아니라 따로 선
    TXT 레코드여야 확인에도 쓰인다. 합친 제안이 그 항목을 그대로 옮기면 제안한 레코드도 오류다."""
    broken = []
    for term in record.split()[1:]:
        body = term[1:] if term[:1] in "+-~?" else term
        lowered = body.lower()
        if lowered.startswith("include:"):
            target = body.split(":", 1)[1]
        elif lowered.startswith("redirect="):
            target = body.split("=", 1)[1]
        else:
            continue
        if "%" not in target and not _SPF_DOMAIN.match(target):
            broken.append(term)
    return broken


def spf_row(lookup, domain: str, ip: str | None) -> tuple[dict, str | None]:
    """SPF 한 줄과 지금 레코드(없으면 None). IP 를 모르면 모름이다."""
    current = next((v for v in lookup.txt(domain).values if v.lower().startswith("v=spf1")), None)
    if not ip:
        return row("spf", UNKNOWN, "바깥 IP 를 몰라 SPF 를 판정하지 않았습니다."), current
    result, why = spf_check(lookup, domain, ip)
    if result == "pass":
        return row("spf", OK, f"보내는 도메인의 SPF 가 이 서버 IP({ip})를 허가합니다."), current
    if result == "none":
        return row("spf", WARN, "보내는 도메인에 SPF 레코드가 없습니다.", need="아래 SPF 레코드를 도메인 DNS 에 넣으세요.",
                   where="도메인 DNS(아래 레코드 복사)"), current
    if result == "permerror":
        need = ("도메인이 아닌 항목을 빼세요. 아래 레코드는 그 항목을 뺀 제안입니다." if current and _broken_spf_terms(current)
                else "SPF 레코드를 고치세요.")
        return row("spf", FAIL, "보내는 도메인의 SPF 레코드에 오류가 있습니다.", need=need,
                   where="도메인 DNS(아래 레코드 복사)", technical=why), current
    if result == "temperror":
        return row("spf", UNKNOWN, "SPF 를 조회하지 못했습니다."), current
    return row("spf", FAIL, f"보내는 도메인의 SPF 에 이 서버 IP({ip})가 없습니다.", need="SPF 에 이 서버 IP 를 더하세요.",
               where="도메인 DNS(아래 레코드 복사)", technical=f"result={result}"), current


def dkim_row(lookup, domain: str, selector: str, public: str, enabled: bool) -> dict:
    if not enabled:
        return row("dkim", WARN, "DKIM 서명을 쓰지 않습니다.", need="받는 쪽이 정크로 분류할 수 있어 서명을 켜는 것이 좋습니다.",
                   where="메일 설정의 DKIM 서명")
    if not public:
        return row("dkim", FAIL, "DKIM 키가 아직 없습니다.", need="키를 만드세요.", where="메일 설정의 DKIM 서명")
    name = rf.dkim_record_name(domain, selector)
    got = lookup.txt(name)
    values = [v.replace(" ", "") for v in got.values]
    if not values:
        return row("dkim", FAIL, "DKIM 레코드가 DNS 에 없습니다.", need=f"{name} 에 아래 DKIM 레코드를 넣으세요.",
                   where="도메인 DNS(아래 레코드 복사)")
    if any(f"p={public}" in v for v in values):
        return row("dkim", OK, "DNS 의 DKIM 공개키가 이 서버의 키와 같습니다.")
    return row("dkim", FAIL, "DNS 의 DKIM 공개키가 이 서버의 키와 다릅니다.", need="아래 DKIM 레코드로 바꾸세요.",
               where="도메인 DNS(아래 레코드 복사)")


def dmarc_row(lookup, domain: str) -> tuple[dict, str | None]:
    current = next((v for v in lookup.txt(f"_dmarc.{domain}").values if v.lower().startswith("v=dmarc1")), None)
    if current is None:
        return row("dmarc", WARN, "보내는 도메인에 DMARC 레코드가 없습니다.", need="아래 DMARC 레코드를 넣는 것이 좋습니다.",
                   where="도메인 DNS(아래 레코드 복사)"), None
    policy = re.search(r"\bp=(\w+)", current)
    return row("dmarc", OK, f"DMARC 레코드가 있습니다(정책 {policy.group(1) if policy else '모름'}).", technical=current), current


def ptr_row(lookup, ip: str | None, helo: str) -> dict:
    if not ip:
        return row("ptr_fcrdns", UNKNOWN, "바깥 IP 를 몰라 역방향 이름을 확인하지 않았습니다.")
    names = lookup.ptr(ip).values
    if not names:
        return row("ptr_fcrdns", FAIL, "공인 IP 의 역방향 이름(PTR)이 없습니다.",
                   need=f"{ip} 의 역방향 이름을 {helo or '서버 이름'}(으)로 등록해 달라고 요청하세요.", where="회선이나 클라우드 업체")
    for name in names:
        if ip in lookup.a(name).values:
            if helo and name != helo:
                return row("ptr_fcrdns", WARN, f"역방향 이름({name})이 서버 이름(HELO)과 다릅니다.",
                           need="역방향 이름과 서버 이름을 같게 맞추는 것이 좋습니다.", where="회선이나 클라우드 업체")
            return row("ptr_fcrdns", OK, f"역방향 이름({name})이 이 IP 로 다시 풀립니다.")
    return row("ptr_fcrdns", FAIL, "역방향 이름이 이 IP 로 다시 풀리지 않습니다.", need="역방향 이름의 A 레코드를 이 IP 로 맞추세요.",
               where="도메인 DNS", technical=", ".join(names))


def helo_row(lookup, helo: str, ip: str | None) -> dict:
    addrs = lookup.a(helo).values if helo else []
    if not addrs:
        return row("helo_dns", FAIL, f"서버 이름({helo})이 DNS 에 없습니다.", need="아래 A 레코드를 넣으세요.",
                   where="도메인 DNS(아래 레코드 복사)")
    if ip and ip not in addrs:
        return row("helo_dns", WARN, f"서버 이름({helo})이 다른 IP 로 풀립니다.", need="A 레코드를 이 서버 IP 로 맞추세요.",
                   where="도메인 DNS", technical=", ".join(addrs))
    return row("helo_dns", OK, f"서버 이름({helo})이 DNS 에 있습니다.")


def recipient_mx_row(system, compare, probe_domain: str, overrides: dict[str, str]) -> tuple[dict, str | None, str | None]:
    """받는 쪽 MX — `(줄, 쓸 MX 호스트, 제안할 전달 서버)`. 시스템 해석기가 모르는데 공개 답이 알면 분리 DNS 다."""
    if probe_domain in overrides:
        host = overrides[probe_domain]
        return row("recipient_mx", OK, f"{probe_domain}{topic_particle(probe_domain)} 받는 도메인별 전달 서버({host})로 보냅니다."), host, None
    mine = system.mx(probe_domain).values
    if mine:
        host = mine[0].split()[1]
        return row("recipient_mx", OK, f"{probe_domain} 의 메일 서버를 찾았습니다({host}).", technical="; ".join(mine)), host, None
    public = []
    for resolver in compare:
        public = resolver.mx(probe_domain).values
        if public:
            break
    if public:
        host = public[0].split()[1]
        return row("recipient_mx", FAIL, f"이 서버의 DNS 는 {probe_domain} 의 메일 서버를 모르지만 공개 DNS 는 압니다(분리 DNS).",
                   need=f"받는 도메인별 전달 서버에 {probe_domain} → {host} 를 넣으세요.", where="메일 설정의 받는 도메인별 전달 서버",
                   technical="; ".join(public)), None, host
    return row("recipient_mx", FAIL, f"{probe_domain} 의 메일 서버(MX)를 찾지 못했습니다.",
               need="받는 도메인별 전달 서버를 넣거나 이 서버의 DNS 를 고치세요.", where="메일 설정 또는 서버 DNS"), None, None


def _knows(lookup, domain: str) -> bool:
    return lookup.mx(domain).ok or lookup.txt(domain).ok


def sender_view(system_dns, compare_dns: list, domain: str) -> tuple[object | None, str | None]:
    """보내는 도메인의 레코드를 **받는 쪽처럼** 보는 조회기 — `(조회기, 갈래)`.

    받는 메일 서버는 공개 DNS 로 SPF · DKIM · DMARC · 역방향 이름을 본다. 비교할 공개 DNS 서버가 이 도메인을 알면 그것으로
    판정한다(「public」). 없으면 이 서버의 DNS 다(「system」). 둘 다 모르면 `(None, None)` 이다 — 그때 「레코드가 없습니다」는 사실이
    아닐 수 있다. 랩의 내부 해석기는 goodmit.co.kr 의 공개 SPF · DMARC 를 몰라 「없습니다」라고 했고, 그 말대로 새 SPF 를 넣으면 공개
    DNS 에 SPF 가 둘이 되어 레코드 오류가 된다(P18 랩 E2E)."""
    for resolver in compare_dns:
        if _knows(resolver, domain):
            return resolver, "public"
    if _knows(system_dns, domain):
        return system_dns, "system"
    return None, None


_BLIND = {
    "spf": "이 서버의 DNS 로는 보내는 도메인의 SPF 를 볼 수 없어 판정하지 않았습니다.",
    "dkim": "이 서버의 DNS 로는 보내는 도메인의 DKIM 레코드를 볼 수 없어 판정하지 않았습니다.",
    "dmarc": "이 서버의 DNS 로는 보내는 도메인의 DMARC 를 볼 수 없어 판정하지 않았습니다.",
}


def sender_rows(system_dns, compare_dns: list, *, domain: str, egress_ip: str | None, helo: str,
                dkim_selector: str, dkim_public: str, dkim_enabled: bool) -> tuple[list[dict], str | None, bool]:
    """보내는 도메인 · SPF · DKIM · DMARC · 역방향 이름 · 서버 이름 줄 — `(줄들, 지금 SPF, 보내는 도메인 레코드를 봤는가)`.

    판정은 받는 쪽이 보는 DNS(`sender_view`)로 한다. 보내는 도메인을 어느 조회기도 모르면 SPF · DKIM · DMARC 는 「모름」이고,
    무엇을 넣으면 판정할 수 있는지를 말한다. 역방향 이름과 서버 이름도 공개 DNS 가 답하면 그것으로 본다 — 내부 해석기는 사설
    이름(`*.lab`)을 사설 IP 로 풀어 「다른 IP 로 풀립니다」라고 했지만, 받는 쪽에게 그 이름은 아예 없는 이름이다."""
    view, kind = sender_view(system_dns, compare_dns, domain)
    rows: list[dict] = []
    if kind == "public" and not _knows(system_dns, domain):
        rows.append(row("sender_domain_public", OK,
                        f"보내는 도메인({domain})을 공개 DNS 에서 찾았습니다. 이 서버의 DNS 는 이 도메인을 모릅니다(분리 DNS)."))
    elif kind is not None:
        rows.append(row("sender_domain_public", OK, f"보내는 도메인({domain})을 DNS 에서 찾았습니다."))
    else:
        rows.append(row("sender_domain_public", WARN, f"보내는 도메인({domain})을 이 서버의 DNS 에서 찾지 못했습니다.",
                        need=("받는 쪽이 보는 공개 DNS 에 이 도메인이 있어야 합니다." if compare_dns
                              else "이 서버의 DNS 가 공개 레코드를 모르면 비교할 공개 DNS 서버를 넣으세요."),
                        where="도메인 DNS" if compare_dns else "메일 설정의 비교할 공개 DNS 서버"))
    current_spf = None
    if view is None:
        need = "비교할 공개 DNS 서버를 넣으면 받는 쪽이 보는 레코드로 판정합니다."
        where = "메일 설정의 비교할 공개 DNS 서버"
        rows.append(row("spf", UNKNOWN, _BLIND["spf"], need=need, where=where))
        if dkim_enabled:
            rows.append(row("dkim", UNKNOWN, _BLIND["dkim"], need=need, where=where))
        else:
            rows.append(dkim_row(system_dns, domain, dkim_selector, dkim_public, dkim_enabled))
        rows.append(row("dmarc", UNKNOWN, _BLIND["dmarc"], need=need, where=where))
    else:
        spf, current_spf = spf_row(view, domain, egress_ip)
        rows.append(spf)
        rows.append(dkim_row(view, domain, dkim_selector, dkim_public, dkim_enabled))
        rows.append(dmarc_row(view, domain)[0])
    names = view if kind == "public" else system_dns
    rows.append(ptr_row(names, egress_ip, helo))
    rows.append(helo_row(names, helo, egress_ip))
    return rows, current_spf, view is not None


def outbound_row(probe: dict | None) -> dict:
    if probe is None:
        return row("outbound_25", UNKNOWN, "받는 쪽 메일 서버를 몰라 25번 연결을 시험하지 않았습니다.")
    if probe.get("connected"):
        return row("outbound_25", OK, f"받는 쪽 메일 서버({probe.get('host')})의 25번에 연결할 수 있습니다.",
                   technical=probe.get("ehlo") or probe.get("banner"))
    return row("outbound_25", FAIL, f"받는 쪽 메일 서버({probe.get('host')})의 25번에 연결하지 못했습니다.",
               need="방화벽이나 회선이 바깥 25번을 막고 있는지 확인하세요. 막혀 있으면 상위 SMTP 이용을 고르세요.",
               where="방화벽이나 회선 업체", technical=probe.get("error"))


def records_for(*, domain: str, egress_ip: str | None, current_spf: str | None, dkim_selector: str, dkim_public: str,
                dkim_enabled: bool, from_address: str, helo: str, sender_seen: bool = True) -> list[dict]:
    """복사할 DNS 레코드 — 이름 · 종류 · 값. 기존 SPF 가 있으면 그것과 합친 제안이다.

    보내는 도메인의 레코드를 보지 못했으면(`sender_seen=False`) SPF · DMARC 제안을 내지 않는다 — 기존 레코드를 모르는 채 새 SPF 를
    제안하면 공개 DNS 에 SPF 가 둘이 되어 레코드 오류가 된다."""
    out: list[dict] = []
    if egress_ip and sender_seen:
        note = None
        if current_spf:
            terms = current_spf.split()[1:]
            broken = _broken_spf_terms(current_spf)
            all_terms = [t for t in terms if t.lstrip("+-~?").lower() == "all"]
            rest = [t for t in terms if t not in all_terms and t not in broken and t.lower() != f"ip4:{egress_ip}"]
            value = " ".join(["v=spf1", f"ip4:{egress_ip}", *rest, *(all_terms or ["~all"])])
            if broken:
                note = ("기존 SPF 에서 도메인이 아닌 항목(" + ", ".join(t if len(t) <= 60 else t[:57] + "..." for t in broken)
                        + ")을 뺐습니다. 이 항목이 레코드 오류의 원인입니다.")
        else:
            value = f"v=spf1 ip4:{egress_ip} ~all"
        spf = {"key": "spf", "name": domain, "type": "TXT", "value": value}
        if note:
            spf["note"] = note
        out.append(spf)
    if dkim_enabled and dkim_public and dkim_selector:
        txt = relay_certs.dkim_txt(dkim_public)
        out.append({"key": "dkim", "name": rf.dkim_record_name(domain, dkim_selector), "type": "TXT", "value": txt,
                    "chunks": relay_certs.txt_chunks(txt)})
    if sender_seen:
        out.append({"key": "dmarc", "name": f"_dmarc.{domain}", "type": "TXT", "value": f"v=DMARC1; p=none; rua=mailto:{from_address}"})
    if helo and egress_ip:
        out.append({"key": "helo", "name": helo, "type": "A", "value": egress_ip})
        out.append({"key": "ptr", "name": egress_ip, "type": "PTR", "value": helo,
                    "request": f"공인 IP {egress_ip} 의 역방향 이름(PTR)을 {helo} 로 등록해 주세요."})
    return out


# ── 묶어 돌리기 ──────────────────────────────────────────────────────────────


def run_checks(
    config: MailConfig, *, helper_status: dict | None, app_verify: Callable[[], dict], smarthost_verify: Callable[[], dict],
    system_dns, compare_dns: list, probe_domain: str, mx_probe: Callable[[str, str], dict],
) -> dict:
    """점검 전체. 바깥에 닿는 일은 모두 인자로 받는다(시험이 가짜를 넣는다)."""
    relay = config.relay
    direct = relay.delivery != DELIVERY_SMARTHOST
    checks = component_rows(helper_status, dkim=direct and relay.dkim_enabled)
    running = bool(helper_status) and helper_status.get("component") == "running"
    if running:
        try:
            checks.append(app_to_relay_row(app_verify(), None))
        except Exception as exc:  # noqa: BLE001 - 한 줄이 실패로 남는다
            checks.append(app_to_relay_row(None, f"{type(exc).__name__}: {exc}"))
    else:
        checks.append(app_to_relay_row(None, None))
    records: list[dict] = []
    egress_ip = relay.public_ip or None
    if not direct:
        try:
            checks.append(smarthost_row(smarthost_verify(), None))
        except Exception as exc:  # noqa: BLE001
            checks.append(smarthost_row(None, f"{type(exc).__name__}: {exc}"))
    else:
        domain = config.sender_domain
        overrides = dict(relay.transport_overrides)
        mx_line, mx_host, suggest = recipient_mx_row(system_dns, compare_dns, probe_domain, overrides)
        probe = mx_probe(mx_host, relay.helo_name) if mx_host else None
        if probe and probe.get("egress_ip"):
            egress_ip = probe["egress_ip"]
        checks.append(row("egress_ip", OK if egress_ip else WARN,
                          f"받는 쪽은 이 서버를 {egress_ip} 로 봅니다." if egress_ip else "바깥 IP 를 알지 못했습니다.",
                          need=None if egress_ip else "메일 설정의 공인 IP 칸에 넣으세요.",
                          where=None if egress_ip else "메일 설정"))
        checks.append(outbound_row(probe))
        checks.append(mx_line)
        lines, current_spf, seen = sender_rows(system_dns, compare_dns, domain=domain, egress_ip=egress_ip,
                                               helo=relay.helo_name, dkim_selector=relay.dkim_selector,
                                               dkim_public=relay.dkim_public, dkim_enabled=relay.dkim_enabled)
        checks.extend(lines)
        records = records_for(domain=domain, egress_ip=egress_ip, current_spf=current_spf,
                              dkim_selector=relay.dkim_selector, dkim_public=relay.dkim_public,
                              dkim_enabled=relay.dkim_enabled, from_address=config.from_address, helo=relay.helo_name,
                              sender_seen=seen)
        if suggest:
            records.insert(0, {"key": "override", "name": probe_domain, "type": "전달 서버", "value": suggest})
    worst = FAIL if any(c["state"] == FAIL for c in checks) else (
        WARN if any(c["state"] in (WARN, UNKNOWN) for c in checks) else OK)
    return {"delivery": relay.delivery, "probe_domain": probe_domain if direct else None, "egress_ip": egress_ip,
            "checks": checks, "records": records, "state": worst, "fingerprint": config.relay_fingerprint}


def save(db: Session, result: dict, *, now: datetime) -> None:
    """결과를 `sync_status["mail_relay"]` 한 행에 둔다(웹 · 초기 설정이 읽는다)."""
    from app.observability.models import SYNC_ERROR, SYNC_OK, SyncStatus

    record = db.get(SyncStatus, COMPONENT)
    if record is None:
        record = SyncStatus(component=COMPONENT)
        db.add(record)
    payload = {**result, "checked_at": now.isoformat()}
    record.status = SYNC_OK if result.get("state") == OK else SYNC_ERROR
    record.last_run_at = now
    if result.get("state") == OK:
        record.last_success_at = now
    record.detail_json = json.dumps(payload, ensure_ascii=False)
    db.flush()


def load(db: Session) -> dict | None:
    from app.observability.models import SyncStatus

    record = db.get(SyncStatus, COMPONENT)
    if record is None or not record.detail_json:
        return None
    try:
        value = json.loads(record.detail_json)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None
