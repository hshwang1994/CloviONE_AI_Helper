"""ClovirAssist 로컬 릴레이 — 특권 헬퍼 동작 (계획 M7, D-551).

메일 화면(`app/mail/router.py` 의 `/relay/*`)과 워커의 추적 · 준비 점검만 부른다. 접두 `mailrelay.` 는 범용 시스템 API
(`/api/admin/system/*`)로 부를 수 없다(`app/sysops/router.py::PRIVATE_ACTION_PREFIXES`) - 형식이 정해진 메일 API 가 인자를 만든다.

## 하는 일과 하지 않는 일

- `status`(읽기): 꾸러미 · 다른 메일 발송 프로그램 · main.cf 가 제품 것인가 · 서비스 상태 · 듣는 소켓.
- `apply`: 제품이 관리하는 설정을 쓰고(`app/mail/relay_files.py`) `postfix check` 를 지난 뒤 켠다. 켠 뒤 받는 문이 루프백 2525 하나이고
  25번을 아무도 듣지 않는지 다시 본다. **기존 구성(제품 표지가 없는 main.cf)이나 다른 메일 발송 프로그램이 있으면 거절한다** -
  지우지도, 덮지도, 인수하지도 않는다. 인수(`takeover`) 같은 인자는 없다(모르는 키는 거절).
- `disable`: 서비스를 끄고 다음 부팅에도 뜨지 않게 한다. 설정 파일은 남긴다(다시 켤 때 그대로 쓴다).
- `dkim_generate`: RSA-2048 키를 만들어 opendkim 만 읽게 둔다. 이미 있는 선택자의 키는 덮지 않는다. 공개키만 돌려준다.
- `queue` · `log` · `flush`: 큐에 남은 메일, 큐 id 별 바깥 전달 결과(로그 원문이 아니라 요약), 지금 다시 보내기.
- **`apt-get` 은 부르지 않는다.** 꾸러미 설치는 설치기가 한다(넓은 root 능력 · 긴 실행 · 오프라인 불가).

## 비밀

상위 SMTP 비밀번호는 비밀 칸(`smtp.relay_password`)에서 root 로 읽어 `sasl_passwd`(root 0600)에만 쓴다. 앱의 클라이언트 열쇠는 비밀
칸(`smtp.relay_client`, root:clovirassist 0640)에 쓴다. 둘 다 `detail` · `data` · 백업 사본에 싣지 않는다(`touches` 에 넣지 않는다).
"""

from __future__ import annotations

import time
from collections.abc import Mapping

from app.core.secret_slots import SLOT_SMTP_RELAY_CLIENT, SLOT_SMTP_RELAY_PASSWORD
from app.mail import relay_certs, relay_files as rf
from app.mail.relay_log import QUEUE_ID_RE, parse_log, parse_postqueue
from app.sysops.actions import Action, ActionOutcome, register
from app.sysops.actions_secrets import SECRET_FILE_MODE, _secrets_dir
from app.sysops.runner import Runner

SYSTEMCTL = "/usr/bin/systemctl"
DPKG_QUERY = "/usr/bin/dpkg-query"
POSTFIX = "/usr/sbin/postfix"
POSTCONF = "/usr/sbin/postconf"
POSTQUEUE = "/usr/sbin/postqueue"
JOURNALCTL = "/usr/bin/journalctl"

PACKAGE_FORMAT = r"${db:Status-Abbrev}|${Package}|${Version}|${Provides}\n"
MTA_VIRTUAL = "mail-transport-agent"
LOG_LINES = 2000
LOG_MAX_IDS = 50
LOG_MAX_AGE_SECONDS = 14 * 86400

NOT_INSTALLED = "이 서버에는 로컬 릴레이 구성 요소가 설치되지 않았습니다."
FOREIGN = "이 서버에는 기존 메일 발송 구성이 있습니다. ClovirAssist 로컬 릴레이가 자동으로 구성되지 않았습니다."
NOT_RUNNING = "메일 발송 구성 요소가 동작하지 않습니다."


class _RelayRejected(ValueError):
    pass


def _client_path() -> str:
    return f"{_secrets_dir()}/{SLOT_SMTP_RELAY_CLIENT}"


def _relay_password_path() -> str:
    return f"{_secrets_dir()}/{SLOT_SMTP_RELAY_PASSWORD}"


# ── 읽기 ─────────────────────────────────────────────────────────────────────


def packages(runner: Runner) -> dict:
    """설치된 꾸러미. 다른 메일 발송 프로그램은 `mail-transport-agent` 를 제공하는 postfix 밖의 꾸러미다(exim4 · sendmail …)."""
    got = runner.run([DPKG_QUERY, "-W", f"--showformat={PACKAGE_FORMAT}"], timeout=60)
    found: dict[str, str] = {}
    other: list[str] = []
    for line in got.stdout.splitlines():
        parts = line.split("|")
        if len(parts) < 4 or not parts[0].startswith("ii"):
            continue
        name, version, provides = parts[1].strip(), parts[2].strip(), parts[3]
        if name in ("postfix", "opendkim", "libsasl2-modules"):
            found[name] = version
        provided = {p.strip().split(" ")[0] for p in provides.split(",")}
        if MTA_VIRTUAL in provided and name != "postfix":
            other.append(name)
    return {"known": got.ok, "postfix": found.get("postfix"), "opendkim": found.get("opendkim"),
            "sasl_modules": found.get("libsasl2-modules"), "other_mta": sorted(other)}


def _unit_word(runner: Runner, verb: str, unit: str) -> str:
    got = runner.run([SYSTEMCTL, verb, unit])
    word = (got.stdout.strip().splitlines() or [""])[0].strip()
    return word or ("not-found" if verb == "is-enabled" else "unknown")


def services(runner: Runner) -> dict:
    return {
        "postfix": _unit_word(runner, "is-active", rf.POSTFIX_INSTANCE_UNIT),
        "postfix_enabled": _unit_word(runner, "is-enabled", rf.POSTFIX_UNIT),
        "opendkim": _unit_word(runner, "is-active", rf.OPENDKIM_UNIT),
        "opendkim_enabled": _unit_word(runner, "is-enabled", rf.OPENDKIM_UNIT),
    }


def listeners(runner: Runner) -> list[str]:
    found = rf.parse_listeners(runner.read_text("/proc/net/tcp"), runner.read_text("/proc/net/tcp6"))
    ports = {"25", str(rf.RELAY_PORT), str(rf.MILTER_PORT)}
    return [item for item in found if item.rsplit(":", 1)[-1] in ports]


def config_state(runner: Runner) -> str:
    return rf.main_cf_state(runner.read_text(rf.MAIN_CF), runner.read_text(rf.MASTER_CF), runner.read_text(rf.STATE_FILE))


def component_state(pk: dict, config: str, svc: dict) -> str:
    """화면의 구성 요소 상태 — ready(설치됨 · 꺼짐) · running · stopped(켰는데 멈춤) · not_installed · foreign."""
    if not pk.get("postfix"):
        return "foreign" if pk.get("other_mta") else "not_installed"
    if config == "foreign" or pk.get("other_mta"):
        return "foreign"
    if svc.get("postfix") == "active":
        return "running"
    if config == "managed" and (svc.get("postfix_enabled") == "enabled" or svc.get("postfix") == "failed"):
        return "stopped"
    return "ready"


def _normalize_status(params: Mapping) -> dict:
    out: dict = {"dkim": None}
    dkim = params.get("dkim")
    if isinstance(dkim, Mapping):
        domain = str(dkim.get("domain") or "").strip().lower()
        selector = str(dkim.get("selector") or "").strip().lower()
        if rf.DOMAIN_RE.match(domain) and rf.SELECTOR_RE.match(selector):
            out["dkim"] = {"domain": domain, "selector": selector}
    return out


def _dkim_view(runner: Runner, dkim: dict | None) -> dict | None:
    if not dkim:
        return None
    key = runner.read_text(rf.dkim_key_path(dkim["domain"], dkim["selector"]))
    public = None
    if key:
        try:
            public = relay_certs.dkim_public(key)
        except (ValueError, TypeError):
            public = None
    return {**dkim, "key_exists": bool(key), "public": public,
            "record_name": rf.dkim_record_name(dkim["domain"], dkim["selector"])}


def _perform_status(runner: Runner, params: dict) -> ActionOutcome:
    pk = packages(runner)
    config = config_state(runner)
    svc = services(runner)
    state = component_state(pk, config, svc)
    data = {
        "component": state,
        "packages": {"postfix": pk["postfix"], "opendkim": pk["opendkim"], "sasl_modules": pk["sasl_modules"]},
        "other_mta": pk["other_mta"],
        "config": config,
        "applied_relay_fingerprint": rf.applied_relay_fingerprint(runner.read_text(rf.STATE_FILE)),
        "services": svc,
        "listeners": listeners(runner),
        "client_ready": runner.exists(_client_path()) and runner.exists(rf.SERVER_CERT),
        "dkim": _dkim_view(runner, params.get("dkim")),
    }
    if state == "running":
        got = runner.run([POSTQUEUE, "-j"], timeout=30)
        data["queue_count"] = len(parse_postqueue(got.stdout)) if got.ok else None
    return ActionOutcome(ok=True, detail="로컬 릴레이 상태를 읽었습니다.", data=data)


# ── 켜기 ─────────────────────────────────────────────────────────────────────


def _guarded(normalize):
    def inner(params: Mapping) -> dict:
        try:
            return normalize(params)
        except (_RelayRejected, rf.RelayParamsError) as exc:
            return {"_rejected": str(exc)}
    return inner


def _perform_guarded(perform):
    def inner(runner: Runner, params: dict) -> ActionOutcome:
        if "_rejected" in params:
            return ActionOutcome(ok=False, detail=params["_rejected"])
        return perform(runner, params)
    return inner


def _apply_touches(params: dict) -> tuple[str, ...]:
    # 개인키와 비밀번호가 든 파일(server.key · sasl_passwd · 클라이언트 열쇠)은 백업 사본을 남기지 않는다.
    return (rf.MAIN_CF, rf.MASTER_CF, rf.CLIENT_CERTS, rf.TRANSPORT_MAP, rf.STATE_FILE, rf.SERVER_CERT, rf.OPENDKIM_CONF)


def _opendkim_is_ours_or_default(text: str | None) -> bool:
    """opendkim.conf 가 제품 것이거나 꾸러미 기본(로컬 소켓, 서명 키 없음)인가. 다른 용도로 쓰던 OpenDKIM 은 건드리지 않는다.

    주석은 보지 않는다 - Ubuntu 꾸러미의 기본 파일은 `#KeyFile …` 같은 예시 줄을 주석으로 들고 있다(실제 systemd 컨테이너에서 확인).
    """
    if text is None or text.startswith(rf.MARKER):
        return True
    directives: dict[str, list[str]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        directives.setdefault(parts[0], []).append(parts[1].strip() if len(parts) > 1 else "")
    socket = directives.get("Socket", [])
    signing = {"KeyFile", "KeyTable", "SigningTable", "Domain", "Selector"} & set(directives)
    return socket in ([], ["local:/run/opendkim/opendkim.sock"]) and not signing


def _stop(runner: Runner) -> None:
    runner.run([SYSTEMCTL, "disable", "--now", rf.POSTFIX_UNIT])
    runner.run([SYSTEMCTL, "stop", rf.POSTFIX_INSTANCE_UNIT])
    runner.run([SYSTEMCTL, "disable", "--now", rf.OPENDKIM_UNIT])


def _ensure_certs(runner: Runner) -> str:
    """서버 인증서 · 앱 클라이언트 열쇠가 없거나 곧 만료되면 새로 만든다. 클라이언트 지문을 돌려준다."""
    server_crt = runner.read_text(rf.SERVER_CERT)
    if not (relay_certs.cert_usable(server_crt) and runner.exists(rf.SERVER_KEY)):
        crt, key = relay_certs.make_server_cert()
        runner.write_text(rf.SERVER_KEY, key, mode=0o600)
        runner.write_text(rf.SERVER_CERT, crt, mode=0o644)
    client = runner.read_text(_client_path())
    if not relay_certs.cert_usable(client):
        client = relay_certs.make_client_bundle()
        runner.write_text(_client_path(), client, mode=SECRET_FILE_MODE)
    return relay_certs.fingerprint(client)


def _perform_apply(runner: Runner, params: dict) -> ActionOutcome:
    pk = packages(runner)
    if not pk["postfix"]:
        return ActionOutcome(ok=False, detail=FOREIGN if pk["other_mta"] else NOT_INSTALLED)
    if pk["other_mta"] or config_state(runner) == "foreign":
        return ActionOutcome(ok=False, detail=FOREIGN)
    proto = runner.read_text(rf.MASTER_CF_PROTO)
    if not proto:
        return ActionOutcome(ok=False, detail="메일 발송 구성 요소의 기본 설정 파일을 찾지 못했습니다.")
    dkim = params.get("dkim")
    if dkim:
        if not pk["opendkim"]:
            return ActionOutcome(ok=False, detail="이 서버에는 서명 구성 요소가 설치되지 않았습니다.")
        if not _opendkim_is_ours_or_default(runner.read_text(rf.OPENDKIM_CONF)):
            return ActionOutcome(ok=False, detail="서명 구성 요소에 기존 설정이 있어 DKIM 서명을 활성화하지 않았습니다.")
        if not runner.exists(rf.dkim_key_path(dkim["domain"], dkim["selector"])):
            return ActionOutcome(ok=False, detail="DKIM 키가 없습니다. 먼저 키를 추가하세요.")
    smarthost = params.get("smarthost") or {}
    password = None
    if smarthost.get("username"):
        password = (runner.read_text(_relay_password_path()) or "").strip()
        if not password:
            return ActionOutcome(ok=False, detail="상위 SMTP 계정의 비밀번호가 저장되지 않았습니다. 메일 설정에서 상위 SMTP 비밀번호를 저장하세요.")

    was_running = services(runner)["postfix"] == "active"
    fingerprint = _ensure_certs(runner)
    main_cf = rf.render_main_cf(params)
    master_cf = rf.render_master_cf(proto)
    runner.write_text(rf.MAIN_CF, main_cf, mode=0o644)
    runner.write_text(rf.MASTER_CF, master_cf, mode=0o644)
    runner.write_text(rf.CLIENT_CERTS, rf.render_client_certs([fingerprint]), mode=0o644)
    if password:
        runner.write_text(rf.SASL_PASSWD, rf.render_sasl_passwd(smarthost, password), mode=0o600)
    else:
        runner.remove(rf.SASL_PASSWD)
    if params.get("transport_overrides"):
        runner.write_text(rf.TRANSPORT_MAP, rf.render_transport(params["transport_overrides"]), mode=0o644)
    else:
        runner.remove(rf.TRANSPORT_MAP)
    if dkim:
        runner.write_text(rf.OPENDKIM_CONF, rf.render_opendkim_conf(dkim), mode=0o644)
    runner.write_text(rf.STATE_FILE, rf.render_state(main_cf, master_cf, relay_fingerprint=rf.relay_fingerprint(params)),
                      mode=0o644)

    check = runner.run([POSTFIX, "check"], timeout=60)
    if not check.ok or "fatal" in (check.stderr or "").lower():
        return ActionOutcome(ok=False, detail="메일 발송 구성 요소가 새 설정을 받아들이지 않았습니다. 설정을 되돌렸습니다.",
                             data={"technical": (check.stderr or check.stdout or "").strip()[-500:]})

    steps: list[list[str]] = []
    if dkim:
        steps += [[SYSTEMCTL, "enable", rf.OPENDKIM_UNIT], [SYSTEMCTL, "restart", rf.OPENDKIM_UNIT]]
    elif pk["opendkim"]:
        steps.append([SYSTEMCTL, "disable", "--now", rf.OPENDKIM_UNIT])
    steps += [[SYSTEMCTL, "enable", rf.POSTFIX_UNIT], [SYSTEMCTL, "restart", rf.POSTFIX_UNIT]]
    for argv in steps:
        got = runner.run(argv, timeout=60)
        if not got.ok and argv[1] != "disable":
            _stop(runner)
            return ActionOutcome(ok=False, detail=NOT_RUNNING + " 로컬 릴레이를 비활성화했습니다.",
                                 data={"technical": f"{' '.join(argv[1:])}: {(got.stderr or '').strip()[-300:]}"})
    svc = services(runner)
    heard = listeners(runner)
    problems = []
    if svc["postfix"] != "active":
        problems.append(f"{rf.POSTFIX_INSTANCE_UNIT} {svc['postfix']}")
    if f"{rf.RELAY_HOST}:{rf.RELAY_PORT}" not in heard:
        problems.append("2525 not listening on 127.0.0.1")
    if rf.listening_on(heard, 25):
        problems.append("port 25 is listening")
    outside = [item for item in rf.listening_on(heard, rf.RELAY_PORT) + rf.listening_on(heard, rf.MILTER_PORT)
               if not item.startswith("127.0.0.1:")]
    if outside:
        problems.append("listening outside loopback: " + ", ".join(outside))
    if dkim and (svc["opendkim"] != "active" or f"127.0.0.1:{rf.MILTER_PORT}" not in heard):
        problems.append(f"{rf.OPENDKIM_UNIT} {svc['opendkim']}")
    if problems:
        _stop(runner)
        return ActionOutcome(ok=False, detail=NOT_RUNNING + " 로컬 릴레이를 비활성화했습니다.",
                             data={"technical": "; ".join(problems)})
    return ActionOutcome(
        ok=True, changed=True,
        detail="로컬 릴레이를 다시 적용했습니다." if was_running else "로컬 릴레이를 활성화했습니다.",
        data={"component": "running", "listeners": heard, "client_fingerprint": fingerprint,
              "relay_fingerprint": rf.relay_fingerprint(params)},
    )


def _perform_disable(runner: Runner, params: dict) -> ActionOutcome:
    _stop(runner)
    svc = services(runner)
    heard = listeners(runner)
    # 우리 받는 문(2525)과 서명 구성 요소(8891)만 본다. 25번은 우리가 듣는 적이 없는 포트다 - 다른 프로그램이 들어도 이 동작의 일이
    # 아니다(실제 systemd 컨테이너에서 시험용 받는 쪽이 25번을 들어 끄기가 실패로 보였다).
    still = [item for item in heard if item.rsplit(":", 1)[-1] in (str(rf.RELAY_PORT), str(rf.MILTER_PORT))]
    if svc["postfix"] == "active" or still:
        return ActionOutcome(ok=False, detail="로컬 릴레이를 비활성화하지 못했습니다.",
                             data={"technical": f"postfix={svc['postfix']} listeners={','.join(still)}"})
    return ActionOutcome(ok=True, changed=True, detail="로컬 릴레이를 비활성화했습니다. 설정은 남겨 두었습니다.",
                         data={"component": "ready" if config_state(runner) != "foreign" else "foreign"})


# ── DKIM 키 ──────────────────────────────────────────────────────────────────


def _normalize_dkim(params: Mapping) -> dict:
    unknown = sorted(k for k in params if k not in ("domain", "selector"))
    if unknown:
        raise _RelayRejected("알 수 없는 항목이 있습니다.")
    domain = str(params.get("domain") or "").strip().lower()
    selector = str(params.get("selector") or "").strip().lower()
    if not rf.DOMAIN_RE.match(domain):
        raise _RelayRejected("보내는 주소의 도메인이 올바르지 않습니다.")
    if not rf.SELECTOR_RE.match(selector):
        raise _RelayRejected("DKIM 선택자는 영문 소문자와 숫자, 하이픈으로 씁니다.")
    return {"domain": domain, "selector": selector}


def _perform_dkim(runner: Runner, params: dict) -> ActionOutcome:
    pk = packages(runner)
    if not pk["opendkim"]:
        return ActionOutcome(ok=False, detail="이 서버에는 서명 구성 요소가 설치되지 않았습니다.")
    domain, selector = params["domain"], params["selector"]
    path = rf.dkim_key_path(domain, selector)
    existing = runner.read_text(path)
    changed = False
    if existing:
        key = existing
    else:
        key = relay_certs.make_dkim_key()
        runner.write_text(path, key, mode=0o600)
        changed = True
    # opendkim 만 읽는다(RequireSafeKeys). 디렉터리도 그 사용자 것이고 다른 사람이 못 들어온다.
    runner.chown("/etc/opendkim", "root", "root", mode=0o755)
    runner.chown(rf.OPENDKIM_KEYS, "opendkim", "opendkim", mode=0o700)
    runner.chown(f"{rf.OPENDKIM_KEYS}/{domain}", "opendkim", "opendkim", mode=0o700)
    runner.chown(path, "opendkim", "opendkim", mode=0o600)
    public = relay_certs.dkim_public(key)
    return ActionOutcome(
        ok=True, changed=changed,
        detail="DKIM 키를 추가했습니다." if changed else "이 선택자의 DKIM 키가 이미 있어 그대로 씁니다.",
        data={"domain": domain, "selector": selector, "record_name": rf.dkim_record_name(domain, selector),
              "public": public},
    )


# ── 큐 · 로그 · 다시 보내기 ──────────────────────────────────────────────────


def _perform_queue(runner: Runner, params: dict) -> ActionOutcome:
    got = runner.run([POSTQUEUE, "-j"], timeout=30)
    if not got.ok:
        return ActionOutcome(ok=False, detail=NOT_RUNNING, data={"technical": (got.stderr or "").strip()[-300:]})
    items = parse_postqueue(got.stdout)
    return ActionOutcome(ok=True, detail=f"큐에 {len(items)}통이 있습니다.", data={"items": items, "count": len(items)})


def _normalize_log(params: Mapping) -> dict:
    ids = params.get("queue_ids")
    if not isinstance(ids, list) or not ids or len(ids) > LOG_MAX_IDS:
        raise _RelayRejected(f"큐 id 는 1개에서 {LOG_MAX_IDS}개까지 줍니다.")
    if not all(isinstance(q, str) and QUEUE_ID_RE.match(q) for q in ids):
        raise _RelayRejected("큐 id 모양이 올바르지 않습니다.")
    since = params.get("since")
    now = int(time.time())
    if not isinstance(since, int) or isinstance(since, bool) or not (now - LOG_MAX_AGE_SECONDS <= since <= now + 60):
        raise _RelayRejected("로그를 읽을 시작 시각이 올바르지 않습니다.")
    return {"queue_ids": sorted(set(ids)), "since": since}


def _perform_log(runner: Runner, params: dict) -> ActionOutcome:
    got = runner.run([JOURNALCTL, "-u", rf.POSTFIX_INSTANCE_UNIT, "--since", f"@{params['since']}", "-o", "cat",
                      "--no-pager", "-n", str(LOG_LINES)], timeout=60)
    if not got.ok:
        return ActionOutcome(ok=False, detail="메일 발송 기록을 읽지 못했습니다.",
                             data={"technical": (got.stderr or "").strip()[-300:]})
    return ActionOutcome(ok=True, detail="바깥 전달 결과를 읽었습니다.",
                         data={"results": parse_log(got.stdout, params["queue_ids"])})


def _perform_flush(runner: Runner, params: dict) -> ActionOutcome:
    got = runner.run([POSTQUEUE, "-f"], timeout=30)
    if not got.ok:
        return ActionOutcome(ok=False, detail=NOT_RUNNING, data={"technical": (got.stderr or "").strip()[-300:]})
    return ActionOutcome(ok=True, changed=True, detail="큐에 남은 메일을 지금 다시 보내도록 했습니다.")


def _no_params(params: Mapping) -> dict:
    if params:
        raise _RelayRejected("이 동작은 인자를 받지 않습니다.")
    return {}


register(Action(
    name="mailrelay.status", summary="로컬 릴레이 상태를 읽습니다", mutating=False,
    normalize=_normalize_status, perform=_perform_status,
))
register(Action(
    name="mailrelay.apply", summary="로컬 릴레이 설정을 쓰고 켭니다", mutating=True,
    normalize=_guarded(rf.normalize_params), perform=_perform_guarded(_perform_apply), touches=_apply_touches,
))
register(Action(
    name="mailrelay.disable", summary="로컬 릴레이를 끕니다", mutating=True,
    normalize=_guarded(_no_params), perform=_perform_guarded(_perform_disable),
))
register(Action(
    name="mailrelay.dkim_generate", summary="DKIM 키를 만듭니다", mutating=True,
    normalize=_guarded(_normalize_dkim), perform=_perform_guarded(_perform_dkim),
))
register(Action(
    name="mailrelay.queue", summary="로컬 릴레이 큐를 읽습니다", mutating=False,
    normalize=_guarded(_no_params), perform=_perform_guarded(_perform_queue),
))
register(Action(
    name="mailrelay.log", summary="큐 id 별 바깥 전달 결과를 읽습니다", mutating=False,
    normalize=_guarded(_normalize_log), perform=_perform_guarded(_perform_log),
))
register(Action(
    name="mailrelay.flush", summary="큐에 남은 메일을 지금 다시 보냅니다", mutating=True,
    normalize=_guarded(_no_params), perform=_perform_guarded(_perform_flush),
))

