"""로컬 릴레이 준비 점검 (계획 M7, D-551).

「로컬 릴레이를 켰다」와 「받는 쪽까지 간다」는 다른 일이다. 이 점검은 화면의 「바깥으로 보내기 준비」 표를 만든다. 각 줄은 **지금 상태 ·
무엇이 필요한가 · 어디서 고치는가**를 한 문장씩 말하고 상태는 정상(ok) · 주의(warn) · 실패(fail) · 모름(unknown) 넷이다.

공통 — 구성 요소가 설치됐는가 · 동작하는가 · 받는 문이 루프백 2525 하나인가 · 앱이 릴레이에 인증서로 붙어 봉투 시험을 지나는가.
상위 SMTP — 상위 서버에 연결 · 보안 연결 · 로그인 · 봉투 시험.
인터넷으로 직접 전달 — 바깥 IP · 바깥 25번 · 받는 쪽 MX(시스템 해석기 대 공개 답 - 분리 DNS 를 잡는다) · 보내는 도메인 · SPF · DKIM ·
DMARC · 역방향 이름(PTR) · 서버 이름(HELO)의 DNS.

판정 함수는 순수하다(가짜 해석기 · 가짜 헬퍼로 시험한다). 결과는 `sync_status["mail_relay"]` 한 행에 남고, 화면과 초기 설정(M6)이 읽는다.

제안은 빠진 것만이다(D-572): SPF · DKIM 은 그 점검이 통과하지 못했을 때만, DMARC 는 **없을 때만** 레코드를 낸다(있는데 하나 더 넣으면 둘 다
무효다 - 랩 공개 DNS 에 `p=none` 이 이미 있었다). 서버 이름(HELO)과 역방향 이름은 **메일이 나가는 IP** 를 가리키는 이름이어야 한다 - 웹 주소가
다른 IP 로 풀리면(랩: 웹 .210 · 메일 .201) 메일 전용 이름을 제안한다(`helo_suggestion`). 받는 쪽이 Microsoft 365 면 그 관리자에게 보낼
「발신자 표시 요청」도 낸다. 스팸 필터 예외 · IP 허용 목록은 요청하지 않는다 - 인증이 통과하면 필요 없다.
**메일은 보내지 않는다** - 바깥 25번 시험은 인사(EHLO)까지, 봉투 시험은 RSET 으로 끝난다.
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Callable
from datetime import datetime
from typing import NamedTuple

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
    "egress_vs_web": "웹 주소와 발신 IP",
    "sender_alignment": "보내는 주소 정렬",
}

OWNER_DNS = "도메인 DNS 담당자"
OWNER_NETWORK = "회선 또는 클라우드 업체"
OWNER_MAILBOX = "받는 쪽 메일 관리자"
M365_MX_SUFFIX = "mail.protection.outlook.com"
NO_ALLOWLIST = "스팸 필터 예외나 IP 허용 목록은 요청하지 않습니다. 인증(SPF와 DKIM)이 통과하면 필요 없습니다."
DMARC_KEEP = "DMARC 레코드는 이미 있으므로 새로 넣지 않습니다. 하나 더 넣으면 둘 다 무효가 됩니다."
DMARC_NONE_ADVICE = "지금 DMARC 정책은 none 입니다. SPF와 DKIM이 통과한 뒤 quarantine 으로 올리는 것을 권합니다."


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


def dmarc_policy(current: str | None) -> str | None:
    """DMARC 레코드의 정책(`p=`) - none · quarantine · reject. 없거나 못 읽으면 None."""
    found = re.search(r"\bp=(\w+)", current or "")
    return found.group(1).lower() if found else None


def dmarc_advice(current: str | None) -> str | None:
    """있는 DMARC 가 `p=none` 이면 레코드 없이 권고 한 문장(D-572). 새 레코드를 제안하지 않는다(둘이 되면 무효)."""
    return DMARC_NONE_ADVICE if current and dmarc_policy(current) == "none" else None


def dmarc_row(lookup, domain: str) -> tuple[dict, str | None]:
    current = next((v for v in lookup.txt(f"_dmarc.{domain}").values if v.lower().startswith("v=dmarc1")), None)
    if current is None:
        return row("dmarc", WARN, "보내는 도메인에 DMARC 레코드가 없습니다.", need="아래 DMARC 레코드를 넣는 것이 좋습니다.",
                   where="도메인 DNS(아래 레코드 복사)"), None
    return row("dmarc", OK, f"DMARC 레코드가 있습니다(정책 {dmarc_policy(current) or '모름'}).", need=dmarc_advice(current),
               technical=current), current


def _under(name: str | None, domain: str | None) -> bool:
    name = (name or "").strip().lower().rstrip(".")
    domain = (domain or "").strip().lower().rstrip(".")
    return bool(name and domain) and (name == domain or name.endswith("." + domain))


def helo_suggestion(domain: str, helo: str | None, egress_ip: str | None, web_host: str | None = None,
                    web_ip: str | None = None, *, helo_addrs=None) -> dict:
    """서버 이름(HELO)과 역방향 이름(PTR)이 쓸 이름(D-572) - `{name, keep, reason, note}`. 순수 함수다(해석은 부르는 쪽이 한다).

    - 지금 HELO 가 보내는 도메인 아래이고 발신 IP 로 풀리면 그대로 둔다(`keep`, reason `ok`).
    - 보내는 도메인 아래인데 아직 DNS 에 없으면(다른 IP 로 풀리지도 않으면) 그 이름에 A 레코드만 더하면 된다(`keep`, reason `missing`).
    - 아니면(사설 이름 · 웹 주소의 IP 로 풀림 · 다른 IP) 새 이름을 제안한다. 웹 주소가 보내는 도메인 아래이고 메일과 같은 IP 로 나가면 웹
      주소 그 자체, 다른 IP 로 나가면 `<웹 주소 첫 이름>-mail.<도메인>`(메일 전용 이름 - NAT 를 바꾸는 대안을 함께 말한다), 웹 주소가 도메인
      밖이면 `mail-clovirassist.<도메인>` 이다.
    """
    domain = (domain or "").strip().lower().rstrip(".")
    helo = (helo or "").strip().lower().rstrip(".")
    web_host = (web_host or "").strip().lower().rstrip(".")
    addrs = [a for a in (helo_addrs or []) if a]
    if _under(helo, domain) and egress_ip and egress_ip in addrs:
        return {"name": helo, "keep": True, "reason": "ok", "note": None}
    if _under(helo, domain) and not addrs and helo != web_host:
        return {"name": helo, "keep": True, "reason": "missing", "note": None}
    if not helo:
        reason, lead = "empty", ""
    elif not _under(helo, domain):
        reason, lead = "private", f"지금 서버 이름({helo})은 {domain} 아래 이름이 아니어서 받는 쪽이 확인하지 못합니다. "
    elif web_ip and web_ip in addrs:
        reason, lead = "web_ip", f"지금 서버 이름({helo})은 웹 주소의 IP({web_ip})로 풀립니다. "
    else:
        reason, lead = "other_ip", f"지금 서버 이름({helo})은 발신 IP 가 아닌 다른 IP 로 풀립니다. "
    if _under(web_host, domain) and web_ip and egress_ip and web_ip == egress_ip:
        name = web_host
        note = lead + f"웹 주소({web_host})가 메일과 같은 IP({egress_ip})로 나가므로 서버 이름을 웹 주소로 바꾸면 됩니다."
    elif _under(web_host, domain):
        name = f"{web_host.split('.')[0]}-mail.{domain}"
        if web_ip and egress_ip and web_ip != egress_ip:
            note = lead + (f"웹 주소({web_host})의 IP 는 {web_ip} 이고 메일은 {egress_ip} 에서 나가므로 메일 전용 이름이 필요합니다. "
                           "메일이 웹 주소와 같은 IP 로 나가도록 NAT 를 바꾸면 메일 전용 이름 대신 웹 주소를 쓸 수 있습니다.")
        else:
            note = lead + "서버 이름은 메일이 나가는 IP 로 풀리는 이름이어야 해서 메일 전용 이름을 제안합니다."
    else:
        name = f"mail-clovirassist.{domain}" if domain else ""
        note = lead + "서버 이름은 메일이 나가는 IP 로 풀리는 보내는 도메인 아래 이름이어야 해서 메일 전용 이름을 제안합니다."
    return {"name": name, "keep": name == helo, "reason": reason, "note": note.strip() or None}


def ptr_row(lookup, ip: str | None, helo: str, *, target: str | None = None) -> dict:
    """역방향 이름 한 줄. ``target`` 은 등록을 요청할 이름이다(제안한 서버 이름 - 없으면 지금 HELO)."""
    if not ip:
        return row("ptr_fcrdns", UNKNOWN, "바깥 IP 를 몰라 역방향 이름을 확인하지 않았습니다.")
    want = target or helo
    names = lookup.ptr(ip).values
    if not names:
        return row("ptr_fcrdns", FAIL, "공인 IP 의 역방향 이름(PTR)이 없습니다.",
                   need=f"{ip} 의 역방향 이름을 서버 이름({want or '보내는 도메인 아래 이름'})으로 등록해 달라고 요청하세요.",
                   where="회선이나 클라우드 업체")
    for name in names:
        if ip in lookup.a(name).values:
            if helo and name != helo:
                return row("ptr_fcrdns", WARN, f"역방향 이름({name})이 서버 이름(HELO)과 다릅니다.",
                           need="역방향 이름과 서버 이름을 같게 맞추는 것이 좋습니다.", where="회선이나 클라우드 업체")
            return row("ptr_fcrdns", OK, f"역방향 이름({name})이 이 IP 로 다시 풀립니다.")
    return row("ptr_fcrdns", FAIL, "역방향 이름이 이 IP 로 다시 풀리지 않습니다.", need="역방향 이름의 A 레코드를 이 IP 로 맞추세요.",
               where="도메인 DNS", technical=", ".join(names))


def _helo_need(suggestion: dict | None, fallback: str) -> tuple[str, str]:
    """서버 이름 줄의 `need` 와 `where` - 제안한 이름이 있으면 그 이름으로 말한다."""
    if not suggestion or suggestion.get("keep") or not suggestion.get("name"):
        return fallback, "도메인 DNS(아래 레코드 복사)"
    name = suggestion["name"]
    if suggestion.get("ready"):
        return f"새 이름({name})이 이미 발신 IP 로 풀립니다. 메일 설정의 서버 이름(HELO)을 그 이름으로 바꾸세요.", "메일 설정"
    return (f"메일 전용 이름({name})을 발신 IP 로 등록하고, 등록이 끝나면 메일 설정의 서버 이름(HELO)을 그 이름으로 바꾸세요.",
            "도메인 DNS(아래 레코드 복사)")


def helo_row(lookup, helo: str, ip: str | None, *, web_ip: str | None = None, suggestion: dict | None = None) -> dict:
    addrs = lookup.a(helo).values if helo else []
    if not addrs:
        need, where = _helo_need(suggestion, "아래 A 레코드를 넣으세요.")
        return row("helo_dns", FAIL, f"서버 이름({helo})이 DNS 에 없습니다.", need=need, where=where)
    if ip and ip not in addrs:
        if web_ip and web_ip in addrs:
            message = f"서버 이름({helo})이 발신 IP({ip})가 아닌 웹 주소의 IP({web_ip})로 풀립니다."
        else:
            message = f"서버 이름({helo})이 발신 IP({ip})가 아닌 다른 IP 로 풀립니다."
        need, where = _helo_need(suggestion, "A 레코드를 발신 IP 로 맞추세요.")
        return row("helo_dns", WARN, message, need=need, where=where, technical=", ".join(addrs))
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


class SenderFacts(NamedTuple):
    """보내는 도메인을 받는 쪽처럼 본 결과(D-572). `records_for` · `requests_for` 의 재료다."""

    rows: list[dict]
    current_spf: str | None
    current_dmarc: str | None
    seen: bool
    helo_addrs: list[str]
    web_ip: str | None
    suggestion: dict


def _first_ipv4(values) -> str | None:
    for value in values or []:
        try:
            if ipaddress.ip_address(value).version == 4:
                return value
        except ValueError:
            continue
    return None


def sender_rows(system_dns, compare_dns: list, *, domain: str, egress_ip: str | None, helo: str,
                dkim_selector: str, dkim_public: str, dkim_enabled: bool, web_host: str | None = None) -> SenderFacts:
    """보내는 도메인 · SPF · DKIM · DMARC · 역방향 이름 · 서버 이름 줄과 그 재료(`SenderFacts`).

    판정은 받는 쪽이 보는 DNS(`sender_view`)로 한다. 보내는 도메인을 어느 조회기도 모르면 SPF · DKIM · DMARC 는 「모름」이고,
    무엇을 넣으면 판정할 수 있는지를 말한다. 역방향 이름과 서버 이름도 공개 DNS 가 답하면 그것으로 본다 — 내부 해석기는 사설
    이름(`*.lab`)을 사설 IP 로 풀어 「다른 IP 로 풀립니다」라고 했지만, 받는 쪽에게 그 이름은 아예 없는 이름이다. 웹 주소(``web_host``)도
    같은 조회기로 풀어 발신 IP 와 견준다(D-572 - 랩은 분리 DNS 라 내부 답은 사설 IP 다).
    """
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
    current_dmarc = None
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
        dmarc, current_dmarc = dmarc_row(view, domain)
        rows.append(dmarc)
    names = view if kind == "public" else system_dns
    helo_addrs = list(names.a(helo).values) if helo else []
    web_ip = _first_ipv4(names.a(web_host).values) if web_host else None
    suggestion = helo_suggestion(domain, helo, egress_ip, web_host, web_ip, helo_addrs=helo_addrs)
    if suggestion["name"] and not suggestion["keep"] and egress_ip:
        # 제안한 이름이 이미 발신 IP 로 풀리면(담당자가 A 를 넣었고 설정만 남음) A 레코드 대신 설정을 바꾸라고 말한다.
        suggestion["ready"] = egress_ip in names.a(suggestion["name"]).values
    rows.append(ptr_row(names, egress_ip, helo, target=suggestion["name"] or None))
    rows.append(helo_row(names, helo, egress_ip, web_ip=web_ip, suggestion=suggestion))
    return SenderFacts(rows, current_spf, current_dmarc, view is not None, helo_addrs, web_ip, suggestion)


def egress_vs_web_row(web_host: str, web_ip: str, egress_ip: str) -> dict:
    """정보 줄(D-572) - 웹 주소와 메일이 같은 IP 로 나가는가. 다르면 서버 이름 · 역방향 이름은 메일 IP 쪽 이름이어야 한다."""
    if web_ip == egress_ip:
        return row("egress_vs_web", OK, f"웹 주소({web_host})와 메일이 같은 IP({egress_ip})로 나갑니다.")
    return row("egress_vs_web", OK, f"웹 주소({web_host})의 IP 는 {web_ip} 이고 메일은 {egress_ip} 에서 나갑니다. "
                                    "서버 이름(HELO)과 역방향 이름은 메일이 나가는 IP 를 가리켜야 합니다.",
               technical=f"web={web_ip} egress={egress_ip}")


def alignment_row(config: MailConfig) -> dict:
    """보내는 주소(From) · 봉투 주소(MAIL FROM) · DKIM 서명(d=)의 도메인이 같은가(D-572) - DMARC 는 이 정렬을 본다."""
    domain = config.sender_domain
    envelope = config.from_address.rsplit("@", 1)[-1].lower() if "@" in config.from_address else ""
    signing = domain if config.relay.dkim_enabled and config.relay.dkim_selector else None
    if domain and envelope == domain and signing == domain:
        return row("sender_alignment", OK, f"보내는 주소, 봉투 주소, DKIM 서명이 모두 같은 도메인({domain})이라 정렬됐습니다.")
    if domain and envelope == domain:
        return row("sender_alignment", OK, f"보내는 주소와 봉투 주소가 같은 도메인({domain})이라 정렬됐습니다. "
                                           "DKIM 서명은 꺼져 있어 정렬에 들지 않습니다.")
    return row("sender_alignment", FAIL, "보내는 주소와 봉투 주소의 도메인이 다릅니다.", need="보내는 사람 주소를 확인하세요.",
               where="메일 설정")


def outbound_row(probe: dict | None) -> dict:
    if probe is None:
        return row("outbound_25", UNKNOWN, "받는 쪽 메일 서버를 몰라 25번 연결을 시험하지 않았습니다.")
    if probe.get("connected"):
        return row("outbound_25", OK, f"받는 쪽 메일 서버({probe.get('host')})의 25번에 연결할 수 있습니다.",
                   technical=probe.get("ehlo") or probe.get("banner"))
    return row("outbound_25", FAIL, f"받는 쪽 메일 서버({probe.get('host')})의 25번에 연결하지 못했습니다.",
               need="방화벽이나 회선이 바깥 25번을 막고 있는지 확인하세요. 막혀 있으면 상위 SMTP 이용을 고르세요.",
               where="방화벽이나 회선 업체", technical=probe.get("error"))


def _needs(states: dict | None, key: str) -> bool:
    """그 점검이 통과하지 못했는가. 점검 상태를 모르면(옛 부름 · 시험) 제안한다."""
    return states is None or states.get(key) != OK


def records_for(*, domain: str, egress_ip: str | None, current_spf: str | None, dkim_selector: str, dkim_public: str,
                dkim_enabled: bool, from_address: str, helo: str, sender_seen: bool = True, current_dmarc: str | None = None,
                states: dict | None = None, web_host: str | None = None, web_ip: str | None = None, helo_addrs=None,
                suggestion: dict | None = None) -> list[dict]:
    """복사할 DNS 레코드 — 이름 · 종류 · 값. **빠진 것만** 낸다(D-572).

    - SPF 는 그 점검이 통과하지 못했을 때만이고 기존 SPF 가 있으면 그것과 합친 제안이다. DKIM 도 같다.
    - DMARC 는 **없을 때만** 낸다(``current_dmarc is None``). 있는데 하나 더 넣으면 둘 다 무효다. 있고 `p=none` 이면 레코드 없이 권고
      문장(`dmarc_advice`)이 점검 줄과 요청문에 선다 - 여기 목록에는 싣지 않는다(목록의 항목마다 「복사」가 붙는다).
    - 서버 이름(A)과 역방향 이름(PTR)은 메일이 나가는 IP 를 가리키는 이름(`helo_suggestion`)으로 낸다 - 사설 이름이나 웹 주소의 IP 로
      풀리는 이름을 PTR 값으로 내지 않는다. 제안한 이름이 이미 발신 IP 로 풀리면 A 레코드는 없다(설정만 바꾸면 된다).
    - 보내는 도메인의 레코드를 보지 못했으면(`sender_seen=False`) SPF · DMARC 제안을 내지 않는다 — 기존 레코드를 모르는 채 새 SPF 를
      제안하면 공개 DNS 에 SPF 가 둘이 되어 레코드 오류가 된다.
    """
    out: list[dict] = []
    if egress_ip and sender_seen and _needs(states, "spf"):
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
    if dkim_enabled and dkim_public and dkim_selector and _needs(states, "dkim"):
        txt = relay_certs.dkim_txt(dkim_public)
        out.append({"key": "dkim", "name": rf.dkim_record_name(domain, dkim_selector), "type": "TXT", "value": txt,
                    "chunks": relay_certs.txt_chunks(txt)})
    if sender_seen and current_dmarc is None:
        out.append({"key": "dmarc", "name": f"_dmarc.{domain}", "type": "TXT", "value": f"v=DMARC1; p=none; rua=mailto:{from_address}"})
    sug = suggestion or helo_suggestion(domain, helo, egress_ip, web_host, web_ip, helo_addrs=helo_addrs)
    if egress_ip and sug.get("name"):
        # 지금 HELO 가 통과하면(발신 IP 로 풀림) 역방향 이름은 그 HELO 로 맞춘다 - 설정을 바꾸지 않는 이름이다.
        helo_ok = states is not None and states.get("helo_dns") == OK
        target = helo if helo_ok and helo else sug["name"]
        if _needs(states, "helo_dns") and not sug.get("ready"):
            a_record = {"key": "helo", "name": sug["name"], "type": "A", "value": egress_ip}
            if sug.get("note"):
                a_record["note"] = sug["note"]
            out.append(a_record)
        if _needs(states, "ptr_fcrdns"):
            out.append({"key": "ptr", "name": egress_ip, "type": "PTR", "value": target,
                        "request": f"공인 IP {egress_ip} 의 역방향 이름(PTR)을 {target} 로 등록해 주세요."})
    return out


_DNS_RECORD_KEYS = ("spf", "dkim", "dmarc", "helo")


def requests_for(records: list[dict], *, domain: str, egress_ip: str | None, helo: str, recipient_mx_host: str | None = None,
                 product_host: str | None = None, web_ip: str | None = None, from_address: str | None = None,
                 recipient_domain: str | None = None, display_name: str = "ClovirAssist", advice=()) -> list[dict]:
    """「담당자에게 보낼 요청문」(D-560 · D-572) — 서버가 할 수 없는 일을 담당자별로 「무엇을 · 왜 · 어떤 값으로」 한 문단과 레코드로.

    메일 서버 설정을 모르는 관리자가 그대로 복사해 보낼 수 있는 글이다. 도메인 DNS 담당자에게는 **제안한 레코드만**(SPF · DKIM · DMARC ·
    서버 이름 A)과 참고 문장(``advice`` - 있는 DMARC 를 두라는 말 · `p=none` 권고), 회선 또는 클라우드 업체에게는 PTR(제안한 메일 전용
    이름, 웹 주소와 IP 가 다르면 NAT 대안 한 문단)이다. 받는 쪽 메일 서버를 알고 그 도메인이 보내는 도메인과 같으면(사내 수신) 받는 쪽 메일
    관리자에게 「발신자 표시 요청」 - 레코드 확인 · 선택 사서함 사진 · 통과 확인 - 을 낸다. 허용 목록이나 필터 예외는 요청하지 않는다.
    """
    out: list[dict] = []
    dns = [r for r in records if r.get("key") in _DNS_RECORD_KEYS]
    ip_text = egress_ip or "이 서버의 공인 IP"
    if dns:
        lines = [
            f"{domain} 도메인의 DNS 에 아래 레코드를 넣어 주세요.",
            f"ClovirAssist 서버({ip_text})가 {domain} 주소로 보내는 메일을 받는 쪽 메일 서버가 정상으로 판정하는 데 필요합니다.",
            "",
        ]
        for r in dns:
            lines.append(f"[{r['type']}] {r['name']}")
            lines.append(f"값: {r['value']}")
            if r.get("note"):
                lines.append(f"참고: {r['note']}")
            lines.append("")
        for sentence in advice or ():
            lines.append(f"참고: {sentence}")
        if advice:
            lines.append("")
        lines.append("등록이 끝나면 알려 주세요. ClovirAssist 의 메일 설정에서 점검을 다시 하면 결과가 보입니다.")
        out.append({
            "owner": OWNER_DNS, "title": "DNS 레코드 등록 요청",
            "why": "받는 쪽 메일 서버는 SPF, DKIM, 서버 이름으로 이 서버가 보낸 메일인지 확인합니다. 레코드가 없으면 정크로 가거나 거부됩니다.",
            "records": dns, "text": "\n".join(lines).rstrip() + "\n",
        })
    ptr = next((r for r in records if r.get("key") == "ptr"), None)
    if ptr is not None and egress_ip:
        target = ptr["value"]
        lines = [
            f"공인 IP {egress_ip} 의 역방향 이름(PTR 레코드)을 {target} 로 등록해 주세요.",
            "이 IP 로 메일을 보내는 서버(ClovirAssist)가 있는데, 역방향 이름이 없으면 받는 쪽 메일 서버(Gmail 등)가 연결 단계에서 거부합니다.",
            "",
            f"[PTR] {egress_ip}",
            f"값: {target}",
        ]
        if web_ip and product_host and web_ip != egress_ip:
            lines += ["", f"다른 방법도 있습니다. 메일이 웹 주소와 같은 IP({web_ip})로 나가도록 NAT 를 바꾸면, 이 요청 대신 {web_ip} 의 "
                          f"역방향 이름을 {product_host} 로 등록하면 됩니다."]
        out.append({
            "owner": OWNER_NETWORK, "title": "PTR 등록 요청",
            "why": "역방향 이름은 IP 를 준 쪽(회선 또는 클라우드 업체)만 등록할 수 있습니다. 도메인 DNS 에서는 할 수 없습니다.",
            "records": [ptr], "text": "\n".join(lines) + "\n",
        })
    mx = (recipient_mx_host or "").strip().lower().rstrip(".")
    same_tenant = not recipient_domain or recipient_domain.strip().lower() == (domain or "").lower()
    if mx and domain and same_tenant:
        out.append(_mailbox_request(domain=domain, mx=mx, ip_text=ip_text, product_host=product_host,
                                    sender=from_address or f"noreply@{domain}", display_name=display_name))
    return out


def _mailbox_request(*, domain: str, mx: str, ip_text: str, product_host: str | None, sender: str, display_name: str) -> dict:
    """받는 쪽 메일 관리자에게 보내는 「발신자 표시 요청」(D-572). Microsoft 365 면 그 이름과 메시지 추적 · compauth 로 말한다."""
    m365 = mx.endswith(M365_MX_SUFFIX)
    admin = f"{domain} 의 Microsoft 365 관리자님" if m365 else f"{domain} 메일 관리자님"
    where = f", 웹 주소 {product_host}" if product_host else ""
    check = ("3. 레코드가 통과한 뒤 ClovirAssist 가 보낸 시험 메일의 Message-ID 로 메시지 추적을 열어 인증 결과가 compauth=pass 인지 확인해 "
             "주세요." if m365 else
             "3. 레코드가 통과한 뒤 ClovirAssist 가 보낸 시험 메일의 머리(Authentication-Results)에서 spf=pass, dkim=pass 인지 확인해 주세요.")
    lines = [
        f"{admin}께 요청드립니다.",
        f"ClovirAssist 서버({ip_text}{where})가 {sender} 주소로 보내는 알림 메일이 사내 받은 편지함에 정상 메일로 들어오도록 확인해 주세요.",
        "",
        "1. 도메인 DNS 담당자에게 요청한 레코드(SPF, DKIM, 서버 이름)가 등록됐는지 확인해 주세요.",
        f"2. (선택) {sender} 주소로 공유 사서함이나 메일 연락처를 만들어 표시 이름을 「{display_name}」로, 사진을 ClovirAssist 표식으로 "
        "넣어 주세요. Outlook 이 보낸 사람 사진으로 그 그림을 보여 줍니다.",
        check,
        "",
        NO_ALLOWLIST,
    ]
    return {
        "owner": OWNER_MAILBOX, "title": "발신자 표시 요청", "provider": "Microsoft 365" if m365 else None,
        "why": ("Outlook 은 보낸 사람 인증(SPF, DKIM)이 통과해야 발신자를 확인된 것으로 표시하고 사서함이나 연락처의 사진을 보여 줍니다. "
                "인증이 실패하면 「보낸 사람의 ID를 확인할 수 없습니다」와 물음표 아이콘이 붙습니다."),
        "records": [], "text": "\n".join(lines) + "\n",
    }


# ── 묶어 돌리기 ──────────────────────────────────────────────────────────────


def run_checks(
    config: MailConfig, *, helper_status: dict | None, app_verify: Callable[[], dict], smarthost_verify: Callable[[], dict],
    system_dns, compare_dns: list, probe_domain: str, mx_probe: Callable[[str, str], dict], web_host: str | None = None,
) -> dict:
    """점검 전체. 바깥에 닿는 일은 모두 인자로 받는다(시험이 가짜를 넣는다). ``web_host`` 는 이 설치의 웹 주소 이름이다(D-572 -
    받는 쪽이 보는 DNS 로 풀어 발신 IP 와 견주고, 서버 이름 제안에 쓴다)."""
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
    requests: list[dict] = []
    advice: list[str] = []
    egress_ip = relay.public_ip or None
    facts = None
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
        facts = sender_rows(system_dns, compare_dns, domain=domain, egress_ip=egress_ip, helo=relay.helo_name,
                            dkim_selector=relay.dkim_selector, dkim_public=relay.dkim_public, dkim_enabled=relay.dkim_enabled,
                            web_host=web_host)
        checks.extend(facts.rows)
        if web_host and facts.web_ip and egress_ip:
            checks.append(egress_vs_web_row(web_host, facts.web_ip, egress_ip))
        checks.append(alignment_row(config))
        states = {c["key"]: c["state"] for c in checks}
        records = records_for(domain=domain, egress_ip=egress_ip, current_spf=facts.current_spf,
                              dkim_selector=relay.dkim_selector, dkim_public=relay.dkim_public,
                              dkim_enabled=relay.dkim_enabled, from_address=config.from_address, helo=relay.helo_name,
                              sender_seen=facts.seen, current_dmarc=facts.current_dmarc, states=states, web_host=web_host,
                              web_ip=facts.web_ip, suggestion=facts.suggestion)
        if facts.current_dmarc:
            advice.append(DMARC_KEEP)
            if dmarc_advice(facts.current_dmarc):
                advice.append(dmarc_advice(facts.current_dmarc))
        requests = requests_for(records, domain=domain, egress_ip=egress_ip, helo=relay.helo_name,
                                recipient_mx_host=mx_host or suggest, product_host=web_host, web_ip=facts.web_ip,
                                from_address=config.from_address, recipient_domain=probe_domain,
                                display_name=config.from_name or "ClovirAssist", advice=advice)
        if suggest:
            records.insert(0, {"key": "override", "name": probe_domain, "type": "전달 서버", "value": suggest})
    worst = FAIL if any(c["state"] == FAIL for c in checks) else (
        WARN if any(c["state"] in (WARN, UNKNOWN) for c in checks) else OK)
    return {"delivery": relay.delivery, "probe_domain": probe_domain if direct else None, "egress_ip": egress_ip,
            "web_host": web_host if direct else None, "web_ip": facts.web_ip if facts else None,
            "helo_suggestion": facts.suggestion if facts else None, "advice": advice,
            "checks": checks, "records": records, "requests": requests, "state": worst,
            "fingerprint": config.relay_fingerprint}


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
