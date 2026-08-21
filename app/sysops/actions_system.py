"""시간·이름·이름풀이·프록시 액션 (§S).

## 드롭인만 쓰고 원본 설정 파일은 건드리지 않는다

`/etc/systemd/resolved.conf` 같은 배포판 원본을 직접 고치면 OS 업그레이드 때 충돌 표시가
뜨고, 사람이 손으로 고친 부분과 우리가 고친 부분을 구별할 수 없게 된다. `*.conf.d/` 아래
**우리 이름의 파일 하나**만 쓰면 되돌리기가 "그 파일을 지우는 것" 으로 끝난다.

## "비우면 해제" 를 만들지 않는다

이 저장소에는 폼 도움말이 "비우면 연결 해제" 라고 적어 놓고 실제로는 무시되는 결함(F5)이
있었다. 빈 값에 뜻을 싣지 않고 **`enabled` 를 따로 받는다.** 끄는 것은 끄겠다고 말해야 한다.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.core import product
from app.sysops import validate as v
from app.sysops.actions import Action, ActionOutcome, register
from app.sysops.runner import Runner

TIMEDATECTL = "/usr/bin/timedatectl"
HOSTNAMECTL = "/usr/bin/hostnamectl"
SYSTEMCTL = "/usr/bin/systemctl"

TIMESYNCD_DROPIN = product.TIMESYNCD_DROPIN
RESOLVED_DROPIN = product.RESOLVED_DROPIN
# 프록시 드롭인을 받는 유닛. 외부로 나가는 프로세스가 전부 들어와야 한다 —
# 스케줄러도 워크플로를 부르므로 웹·배치 워커와 같은 프록시를 봐야 한다.
PROXY_DROPIN_UNITS = (
    product.WEB_UNIT,
    product.WORKER_UNIT,
    product.SCHEDULER_UNIT,
)
HOSTS_FILE = "/etc/hosts"
HOSTS_MARKER = product.HOSTS_MARKER


def _show(runner: Runner, argv: list[str]) -> str:
    got = runner.run(argv)
    return got.stdout.strip() if got.ok else ""


# ---------------------------------------------------------------- 타임존


def _normalize_timezone(params: Mapping) -> dict:
    return {"timezone": v.timezone(params.get("timezone"))}


def _perform_timezone(runner: Runner, params: dict) -> ActionOutcome:
    """`timedatectl` 이 관리하는 상태라 **파일 백업으로는 되돌릴 수 없다.**

    그래서 적용 전에 현재 값을 읽어 두고, 검증이 어긋나면 그 값으로 되돌린다.
    (엔진의 파일 롤백은 `touches` 가 비어 있어 아무 일도 하지 않는다.)
    """
    want = params["timezone"]
    before = _show(runner, [TIMEDATECTL, "show", "-p", "Timezone", "--value"])
    if before == want:
        return ActionOutcome(ok=True, detail=f"이미 {want} 입니다.", data={"timezone": want})

    applied = runner.run([TIMEDATECTL, "set-timezone", want])
    if not applied.ok:
        return ActionOutcome(ok=False, detail=f"타임존을 바꾸지 못했습니다: {applied.stderr.strip()}")

    after = _show(runner, [TIMEDATECTL, "show", "-p", "Timezone", "--value"])
    if after != want:
        if before:
            runner.run([TIMEDATECTL, "set-timezone", before])
        return ActionOutcome(
            ok=False,
            detail=f"타임존이 적용되지 않았습니다(요청 {want}, 실제 {after or '알 수 없음'}).",
        )
    return ActionOutcome(
        ok=True, detail=f"타임존을 {want} 로 바꿨습니다.", changed=True,
        data={"timezone": after, "previous": before},
    )


register(Action(
    name="timezone.set",
    summary="서버 타임존 변경",
    mutating=True,
    normalize=_normalize_timezone,
    perform=_perform_timezone,
))


# ---------------------------------------------------------------- NTP


def _normalize_ntp(params: Mapping) -> dict:
    enabled = bool(params.get("enabled", True))
    if not enabled:
        return {"enabled": False, "servers": []}
    return {"enabled": True, "servers": v.ntp_servers(params.get("servers"))}


def _restart_unit(runner: Runner, unit: str) -> tuple[bool, str]:
    restarted = runner.run([SYSTEMCTL, "restart", unit], timeout=30)
    if not restarted.ok:
        return False, restarted.stderr.strip() or f"{unit} 재시작에 실패했습니다."
    active = runner.run([SYSTEMCTL, "is-active", unit])
    if active.stdout.strip() != "active":
        return False, f"{unit} 가 다시 살아나지 않았습니다({active.stdout.strip() or '상태 없음'})."
    return True, ""


def _revert_and_restart(runner: Runner, path: str, previous: str | None, unit: str) -> None:
    """새 설정으로 재시작이 실패했을 때 **그 자리에서** 이전 설정으로 되돌리고 다시 시작한다.

    `execute()`(app/sysops/actions.py) 의 백업 롤백은 실패한 뒤 파일만 복사해 돌려놓을 뿐,
    그 파일을 쓰는 서비스를 다시 시작하지는 않는다 — 그래서 "rolled_back: true" 라고 답해도
    실제로는 깨진 새 설정을 문 채 죽어 있는 systemd-resolved/timesyncd 가 남을 수 있다. 여기서
    실패를 감지한 즉시 파일을 되돌리고 재시작까지 시도해 두면, 나중에 엔진이 같은 내용을 다시
    덮어써도(무해한 중복) 서비스는 이미 이전 상태로 살아 있다. 이 복구 자체가 실패해도(예:
    이전 설정도 이미 깨져 있었다) 최선을 다한 것이고, 원래 오류 메시지는 그대로 보고한다.
    """
    if previous is None:
        runner.remove(path)
    else:
        runner.write_text(path, previous)
    _restart_unit(runner, unit)


def _perform_ntp(runner: Runner, params: dict) -> ActionOutcome:
    if not params["enabled"]:
        if not runner.exists(TIMESYNCD_DROPIN):
            return ActionOutcome(ok=True, detail="NTP 서버 지정이 원래 없습니다.")
        previous = runner.read_text(TIMESYNCD_DROPIN)
        runner.remove(TIMESYNCD_DROPIN)
        ok, why = _restart_unit(runner, "systemd-timesyncd")
        if not ok:
            _revert_and_restart(runner, TIMESYNCD_DROPIN, previous, "systemd-timesyncd")
            return ActionOutcome(ok=False, detail=why)
        return ActionOutcome(ok=True, detail="NTP 서버 지정을 해제했습니다.", changed=True)

    servers = params["servers"]
    text = "[Time]\nNTP=" + " ".join(servers) + "\n"
    previous = runner.read_text(TIMESYNCD_DROPIN)
    if previous == text:
        return ActionOutcome(ok=True, detail="이미 같은 NTP 서버입니다.", data={"servers": servers})

    runner.write_text(TIMESYNCD_DROPIN, text)
    ok, why = _restart_unit(runner, "systemd-timesyncd")
    if not ok:
        _revert_and_restart(runner, TIMESYNCD_DROPIN, previous, "systemd-timesyncd")
        return ActionOutcome(ok=False, detail=why)
    # 읽어서 확인한다. 쓰기가 성공했다는 것과 파일에 그 내용이 있다는 것은 다른 사건이다.
    if runner.read_text(TIMESYNCD_DROPIN) != text:
        return ActionOutcome(ok=False, detail="NTP 설정이 파일에 남지 않았습니다.")
    return ActionOutcome(
        ok=True, detail="NTP 서버를 바꿨습니다.", changed=True, data={"servers": servers},
    )


register(Action(
    name="ntp.set",
    summary="시각 동기화(NTP) 서버 지정",
    mutating=True,
    normalize=_normalize_ntp,
    perform=_perform_ntp,
    touches=lambda _p: (TIMESYNCD_DROPIN,),
))


# ---------------------------------------------------------------- 호스트 이름


def _normalize_hostname(params: Mapping) -> dict:
    out: dict = {"hostname": v.hostname(params.get("hostname"))}
    raw_fqdn = params.get("fqdn")
    out["fqdn"] = v.fqdn(raw_fqdn) if raw_fqdn else None
    if out["fqdn"] and out["fqdn"].split(".")[0] != out["hostname"]:
        raise v.InvalidSysopsValueError(
            f"FQDN 의 첫 부분이 호스트 이름과 다릅니다: {out['fqdn']} vs {out['hostname']}"
        )
    return out


def _hosts_with_entry(current: str | None, *, host: str, fqdn: str | None) -> str:
    """`/etc/hosts` 의 우리 줄만 갈아 끼운다.

    `127.0.1.1` 줄이 이름과 어긋나면 sudo 가 매 호출마다 이름을 풀려다 지연되고, 메일·인증서
    도구가 FQDN 을 못 찾는다. 그래서 이름을 바꿀 때 이 줄도 같이 바꾼다.
    다른 줄은 손대지 않는다 — 사람이 넣어 둔 항목을 지우면 그 서버에서만 되던 것이 조용히 깨진다.
    """
    names = f"{fqdn} {host}" if fqdn else host
    line = f"127.0.1.1\t{names}\t{HOSTS_MARKER}"
    lines = [ln for ln in (current or "").splitlines() if HOSTS_MARKER not in ln]
    lines.append(line)
    return "\n".join(lines) + "\n"


def _perform_hostname(runner: Runner, params: dict) -> ActionOutcome:
    host = params["hostname"]
    fqdn = params["fqdn"]
    want_static = fqdn or host

    applied = runner.run([HOSTNAMECTL, "set-hostname", want_static])
    if not applied.ok:
        return ActionOutcome(ok=False, detail=f"호스트 이름을 바꾸지 못했습니다: {applied.stderr.strip()}")

    after = _show(runner, [HOSTNAMECTL, "status", "--static"]) or _show(
        runner, [HOSTNAMECTL, "show", "-p", "StaticHostname", "--value"]
    )
    if after != want_static:
        return ActionOutcome(
            ok=False,
            detail=f"호스트 이름이 적용되지 않았습니다(요청 {want_static}, 실제 {after or '알 수 없음'}).",
        )

    runner.write_text(HOSTS_FILE, _hosts_with_entry(runner.read_text(HOSTS_FILE), host=host, fqdn=fqdn))
    return ActionOutcome(
        ok=True, detail=f"호스트 이름을 {want_static} 로 바꿨습니다.", changed=True,
        data={"hostname": host, "fqdn": fqdn},
    )


register(Action(
    name="hostname.set",
    summary="호스트 이름 / FQDN 변경",
    mutating=True,
    normalize=_normalize_hostname,
    perform=_perform_hostname,
    touches=lambda _p: (HOSTS_FILE,),
))


# ---------------------------------------------------------------- DNS


def _normalize_dns(params: Mapping) -> dict:
    enabled = bool(params.get("enabled", True))
    if not enabled:
        return {"enabled": False, "servers": [], "search": None}
    out: dict = {"enabled": True, "servers": v.dns_servers(params.get("servers"))}
    raw = params.get("search")
    out["search"] = v.fqdn(raw) if raw else None
    return out


def _perform_dns(runner: Runner, params: dict) -> ActionOutcome:
    if not params["enabled"]:
        if not runner.exists(RESOLVED_DROPIN):
            return ActionOutcome(ok=True, detail="DNS 지정이 원래 없습니다.")
        previous = runner.read_text(RESOLVED_DROPIN)
        runner.remove(RESOLVED_DROPIN)
        ok, why = _restart_unit(runner, "systemd-resolved")
        if not ok:
            _revert_and_restart(runner, RESOLVED_DROPIN, previous, "systemd-resolved")
            return ActionOutcome(ok=False, detail=why)
        return ActionOutcome(ok=True, detail="DNS 지정을 해제했습니다.", changed=True)

    servers = params["servers"]
    text = "[Resolve]\nDNS=" + " ".join(servers) + "\n"
    if params["search"]:
        text += f"Domains={params['search']}\n"
    previous = runner.read_text(RESOLVED_DROPIN)
    if previous == text:
        return ActionOutcome(ok=True, detail="이미 같은 DNS 설정입니다.", data={"servers": servers})

    runner.write_text(RESOLVED_DROPIN, text)
    ok, why = _restart_unit(runner, "systemd-resolved")
    if not ok:
        _revert_and_restart(runner, RESOLVED_DROPIN, previous, "systemd-resolved")
        return ActionOutcome(ok=False, detail=why)
    if runner.read_text(RESOLVED_DROPIN) != text:
        return ActionOutcome(ok=False, detail="DNS 설정이 파일에 남지 않았습니다.")
    return ActionOutcome(
        ok=True, detail="DNS 서버를 바꿨습니다.", changed=True,
        data={"servers": servers, "search": params["search"]},
    )


register(Action(
    name="dns.set",
    summary="DNS 서버 지정",
    mutating=True,
    normalize=_normalize_dns,
    perform=_perform_dns,
    touches=lambda _p: (RESOLVED_DROPIN,),
))


# ---------------------------------------------------------------- 프록시


def _proxy_dropin(unit: str) -> str:
    return f"/etc/systemd/system/{unit}.d/{product.PROXY_DROPIN_NAME}"


def _normalize_proxy(params: Mapping) -> dict:
    enabled = bool(params.get("enabled", True))
    if not enabled:
        return {"enabled": False, "url": None, "no_proxy": None}
    out: dict = {"enabled": True, "url": v.proxy_url(params.get("url"))}
    raw = params.get("no_proxy")
    out["no_proxy"] = v.no_proxy(raw) if raw else None
    return out


def _perform_proxy(runner: Runner, params: dict) -> ActionOutcome:
    """프록시는 **우리 서비스의 환경 변수**로만 건다.

    `/etc/environment` 를 고치면 서버 전체(사람의 셸 포함)에 영향을 주고, 되돌릴 때 우리가 넣은
    줄과 사람이 넣은 줄을 구별하기 어렵다. 우리 유닛의 드롭인이면 영향 범위가 우리 것뿐이다.

    ⚠️ **적용은 재시작해야 실제로 반영된다.** 여기서 재시작하지 않는 이유: 웹을 재시작하면
    지금 이 요청을 보낸 연결이 끊겨 사용자는 "실패했다" 고 읽는다. 재시작은 별도 액션이고,
    화면이 "재시작해야 반영됩니다" 라고 말한다.
    """
    if not params["enabled"]:
        removed = False
        for unit in PROXY_DROPIN_UNITS:
            path = _proxy_dropin(unit)
            if runner.exists(path):
                runner.remove(path)
                removed = True
        runner.run([SYSTEMCTL, "daemon-reload"])
        if not removed:
            return ActionOutcome(ok=True, detail="프록시 설정이 원래 없습니다.")
        return ActionOutcome(
            ok=True, detail="프록시 설정을 해제했습니다. 반영하려면 서비스를 재시작하세요.",
            changed=True,
        )

    lines = ["[Service]", f'Environment="HTTPS_PROXY={params["url"]}"',
             f'Environment="HTTP_PROXY={params["url"]}"']
    if params["no_proxy"]:
        lines.append(f'Environment="NO_PROXY={params["no_proxy"]}"')
    text = "\n".join(lines) + "\n"

    same = all(runner.read_text(_proxy_dropin(u)) == text for u in PROXY_DROPIN_UNITS)
    if same:
        return ActionOutcome(ok=True, detail="이미 같은 프록시 설정입니다.", data={"url": params["url"]})

    for unit in PROXY_DROPIN_UNITS:
        runner.write_text(_proxy_dropin(unit), text)
    reloaded = runner.run([SYSTEMCTL, "daemon-reload"], timeout=30)
    if not reloaded.ok:
        return ActionOutcome(ok=False, detail=f"systemd 를 다시 읽지 못했습니다: {reloaded.stderr.strip()}")
    for unit in PROXY_DROPIN_UNITS:
        if runner.read_text(_proxy_dropin(unit)) != text:
            return ActionOutcome(ok=False, detail=f"{unit} 프록시 설정이 파일에 남지 않았습니다.")
    return ActionOutcome(
        ok=True,
        detail="프록시를 설정했습니다. 반영하려면 서비스를 재시작하세요.",
        changed=True,
        data={"url": params["url"], "no_proxy": params["no_proxy"], "restart_required": True},
    )


register(Action(
    name="proxy.set",
    summary="아웃바운드 프록시 지정",
    mutating=True,
    normalize=_normalize_proxy,
    perform=_perform_proxy,
    touches=lambda _p: tuple(_proxy_dropin(u) for u in PROXY_DROPIN_UNITS),
))
