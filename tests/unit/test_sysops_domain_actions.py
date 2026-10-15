"""대표 서비스 주소 — 헬퍼 액션 `domain.preview` · `domain.apply` · `service.restart_deferred` (계획 M3, D-573).

실제 시스템을 건드리지 않는다(`tests/fakes/sysops.py::FakeRunner`). 엔진(`actions.execute`)을 지나게 해서 백업 · 되돌리기까지 잰다.

못박는 것:
1. 미리 확인은 읽기만 한다 — DNS(이 서버 해석기 기준, 공개 해석기는 따로) · 인증서 SAN · nginx 이름 · 443 · env 를 넷의 확인으로 낸다.
   다른 vhost 가 같은 이름을 쓰면 적용할 수 없다(fail).
2. 적용 정상 경로: 인증서 → vhost → `nginx -t` → reload → env · 매니페스트(엄격한 JSON, 별칭 기록) → 자체 확인 → 뒷단 유닛 재시작
   (꺼져 있던 유닛은 켜지 않는다) → web 지연 재시작(systemd-run).
3. `nginx -t` 가 실패하면 실패이고, 파일이 돌아오고, nginx 를 옛 설정으로 다시 읽힌다.
4. 자체 확인이 실패하면 같은 되돌림이 일어나고 유닛은 재시작하지 않는다.
5. 붙여 넣은 PEM 짝이 안 맞으면 **아무것도 쓰기 전에** 거절하고, 개인키는 결과 어디에도 없다.
6. 「지금 인증서 유지」인데 SAN 에 새 이름이 없으면 실패다.
7. 별칭은 중복을 접고 다섯 개까지다. IP · 경로가 든 주소는 거절한다.
8. 자체 확인(HTTPS)은 진짜 TLS 서버로 잰다 — 맞는 인증서 · 이름은 통과(Known Good), 다른 이름 · 다른 인증서는 실패(Known Bad).
"""

from __future__ import annotations

import json
import socket
import ssl
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core import product
from app.mail.dns import Answer
from app.sysops import actions as engine
from app.sysops import actions_domain as ad
from app.sysops import actions_service as svc
from app.sysops import domain_files as df
from app.sysops import validate as v
from app.sysops.runner import ALLOWED_BINARIES, BinaryNotAllowedError, Completed
from tests.fakes.sysops import FakeRunner

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "deploy" / "nginx" / "clovirassist.conf").read_text(encoding="utf-8")
BIND = "10.0.0.5"
OLD = "old.example.internal"
NEW = "new.example.com"
OLD_CRT, OLD_KEY = df.cert_paths(product.TLS_DIR, OLD)
NEW_CRT, NEW_KEY = df.cert_paths(product.TLS_DIR, NEW)
ENV_TEXT = f"SECRET_KEY=keep-me\nAPP_BASE_URL=https://{OLD}\nTLS_CERT_PATH={OLD_CRT}\nDATA_DIR=/var/lib/clovirassist\n"
# 랩의 매니페스트처럼 `version` 안에 날 CR 이 있다 — 엄격한 JSON 이 아니다.
MANIFEST_TEXT = ('{\n  "product": "ClovirAssist",\n  "version": "0.1.0-dev\r",\n  "dns_name": "' + OLD + '",\n'
                 '  "bind_ip": "' + BIND + '",\n  "upstream_proxies": "10.0.0.96",\n  "stages": [{"stage":0,"verdict":"OK"}]\n}\n')
OLD_PEM = "-----BEGIN CERTIFICATE-----\nOLDCERT\n-----END CERTIFICATE-----\n"
OLD_KEY_PEM = "-----BEGIN PRIVATE KEY-----\nOLDKEYSECRET\n-----END PRIVATE KEY-----\n"
NEW_PEM = "-----BEGIN CERTIFICATE-----\nNEWCERT\n-----END CERTIFICATE-----\n"
NEW_KEY_PEM = "-----BEGIN PRIVATE KEY-----\nNEWKEYSECRET\n-----END PRIVATE KEY-----\n"
LISTEN_443 = ("  sl  local_address rem_address   st\n"
              "   0: 0500000A:01BB 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 1 1 0 100 0 0 10 0\n")
SYSTEMCTL = "/usr/bin/systemctl"
NGINX = "/usr/sbin/nginx"
OPENSSL = "/usr/bin/openssl"


def x509_text(names: list[str], *, issuer: str | None = None) -> str:
    subject = f"CN = {names[0]}"
    sans = ", ".join([f"DNS:{n}" for n in names] + [f"IP Address:{BIND}"])
    return (f"subject={subject}\nissuer={issuer or subject}\nnotAfter=Oct 15 00:00:00 2027 GMT\n"
            f"X509v3 Subject Alternative Name: \n    {sans}\n")


def nginx_dump(our_names: list[str], *, other: str = "") -> str:
    names = " ".join(our_names)
    out = (f"# configuration file /etc/nginx/nginx.conf:\nhttp {{ }}\n\n"
           f"# configuration file {df.SITE_ENABLED}:\nserver {{\n    server_name {names};\n}}\n"
           f"server {{\n    server_name {names};\n}}\n")
    if other:
        out += f"\n# configuration file /etc/nginx/sites-enabled/other:\nserver {{\n    server_name {other};\n}}\n"
    return out


class DomainRunner(FakeRunner):
    """FakeRunner + 같은 명령의 답을 차례로 주는 줄 + `openssl req` 가 파일을 만드는 흉내."""

    def __init__(self, files=None) -> None:
        super().__init__(files)
        self.queue: dict[tuple[str, ...], list[Completed]] = {}

    def reply_seq(self, argv: list[str], results: list[tuple[int, str, str]]) -> None:
        self.queue[tuple(argv)] = [Completed(tuple(argv), code, out, err) for code, out, err in results]

    def run(self, argv, *, timeout=20):
        key = tuple(argv)
        if argv and argv[0] not in ALLOWED_BINARIES:
            raise BinaryNotAllowedError(argv[0])
        if self.queue.get(key):
            self.calls.append(key)
            return self.queue[key].pop(0)
        if len(argv) > 2 and argv[0] == OPENSSL and argv[1] == "req":
            self.calls.append(key)
            self.files[argv[argv.index("-out") + 1]] = NEW_PEM
            self.files[argv[argv.index("-keyout") + 1]] = NEW_KEY_PEM
            return Completed(key, 0, "", "")
        return super().run(argv, timeout=timeout)

    def count(self, argv: list[str]) -> int:
        return sum(1 for c in self.calls if c == tuple(argv))


class FakeDns:
    def __init__(self, table: dict[str, list[str]]) -> None:
        self.table = table

    def a(self, name: str) -> Answer:
        return Answer(values=self.table[name]) if name in self.table else Answer(error="nxdomain")


@pytest.fixture()
def lab(monkeypatch):
    """옛 이름 하나로 설치된 서버 — env · 매니페스트(CR 포함) · 템플릿 · vhost · 인증서."""
    runner = DomainRunner({
        product.ENV_FILE: ENV_TEXT,
        df.MANIFEST_FILE: MANIFEST_TEXT,
        df.TEMPLATE_FILE: TEMPLATE,
        df.SITE_AVAILABLE: df.render_vhost(TEMPLATE, BIND, OLD, []),
        df.SITE_ENABLED: "(symlink)",
        OLD_CRT: OLD_PEM,
        OLD_KEY: OLD_KEY_PEM,
        "/proc/net/tcp": LISTEN_443,
    })
    read = [OPENSSL, "x509", "-noout", "-subject", "-issuer", "-enddate", "-ext", "subjectAltName", "-in"]
    runner.reply(read + [OLD_CRT], out=x509_text([OLD]))
    runner.reply(read + [NEW_CRT], out=x509_text([NEW, OLD]))
    runner.reply([NGINX, "-T"], out=nginx_dump([OLD]))
    runner.reply([NGINX, "-t"])
    runner.reply([SYSTEMCTL, "reload", "nginx.service"])
    for unit in ad.BACKEND_UNITS:
        state = "inactive" if unit == product.WORKER_CONVERSATIONAL_UNIT else "active"
        runner.reply([SYSTEMCTL, "is-active", unit], out=state + "\n", code=0 if state == "active" else 3)
        runner.reply([SYSTEMCTL, "restart", unit])
    runner.reply(ad.restart_argv(product.WEB_UNIT, ad.WEB_RESTART_DELAY))
    probes: list[tuple[str, str, str]] = []

    def probe(bind_ip, host, path, cadata, timeout=8.0, port=443):
        probes.append((bind_ip, host, path))
        assert cadata == NEW_PEM or cadata == OLD_PEM, "자체 확인의 신뢰 기준이 새 인증서 글이 아니다"
        return (200, '<form id="login-form">' if path == "/login" else "ok", None)

    monkeypatch.setattr(ad, "HTTPS_PROBE", probe)
    monkeypatch.setattr(ad, "SLEEP", lambda _s: None)
    monkeypatch.setattr(ad, "DNS_FACTORY", lambda ns=None: FakeDns(
        {NEW: ["203.0.113.10"], OLD: ["203.0.113.99"]} if ns else {NEW: [BIND], OLD: [BIND]}))
    runner.probes = probes
    return runner


def run(runner, name, params):
    return engine.execute(runner, name, params, backup_root="/var/backups/clovirassist/sysops",
                          now=datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc))


APPLY = {"host": NEW, "aliases": [OLD], "cert": {"strategy": "self_signed"}, "restart_web": True}


# ── 미리 확인 ─────────────────────────────────────────────────────────────────


def test_preview_reports_four_checks_and_keeps_the_public_answer_apart(lab):
    result = run(lab, "domain.preview", {"host": NEW, "aliases": [OLD], "resolvers": ["8.8.8.8"]})
    assert result.ok, result.detail
    checks = {c["key"]: c for c in result.data["checks"]}
    assert list(checks) == ["dns", "https", "web", "app"]
    assert checks["dns"]["state"] == "ok", checks["dns"]
    assert BIND in checks["dns"]["message"]
    assert checks["https"]["state"] == "warn" and NEW in checks["https"]["message"], "지금 인증서에 새 이름이 없다는 말이 없다"
    assert checks["web"]["state"] == "warn", "웹 서버 설정에 새 이름이 아직 없다"
    assert checks["app"]["state"] == "warn" and f"https://{NEW}" in checks["app"]["message"]
    assert result.data["can_apply"] is True
    # 공개 해석기의 답은 따로 실리고, 이 서버 기준 판정(ok)에 섞이지 않는다.
    assert result.data["dns"]["compare"] == [{"name": NEW, "answers": ["203.0.113.10"], "error": None, "resolver": "8.8.8.8"}]
    impact = " ".join(result.data["impact"])
    assert "다시 로그인" in impact and f"옛 주소 {OLD}는 함께 쓰는 주소로 남아" in impact
    assert result.data["current"]["canonical"] == OLD and result.data["current"]["bind_ip"] == BIND
    assert result.data["current"]["cert"]["sans"] == [OLD]
    assert result.changed is False and result.backup_dir is None, "미리 확인이 무언가를 바꿨다"
    assert not any(c[:2] == (SYSTEMCTL, "reload") for c in lab.calls)


def test_preview_without_a_host_describes_the_current_address(lab):
    result = run(lab, "domain.preview", {})
    assert result.ok
    assert result.data["target"] == {"host": OLD, "aliases": [], "names": [OLD], "changes": False}
    assert {c["key"]: c["state"] for c in result.data["checks"]} == {"dns": "ok", "https": "ok", "web": "ok", "app": "ok"}
    assert result.data["impact"] == []


def test_a_name_another_vhost_already_serves_blocks_the_apply(lab):
    lab.reply([NGINX, "-T"], out=nginx_dump([OLD], other=f"intranet.example.com {NEW}"))
    result = run(lab, "domain.preview", {"host": NEW})
    web = next(c for c in result.data["checks"] if c["key"] == "web")
    assert web["state"] == "fail" and "/etc/nginx/sites-enabled/other" in web["message"]
    assert result.data["can_apply"] is False


def test_an_old_template_without_the_alias_slot_blocks_the_apply(lab):
    lab.files[df.TEMPLATE_FILE] = TEMPLATE.replace("server_name __SERVER_NAMES__;", "server_name __DNS_NAME__;")
    result = run(lab, "domain.preview", {"host": NEW})
    assert next(c for c in result.data["checks"] if c["key"] == "web")["state"] == "fail"
    applied = run(lab, "domain.apply", APPLY)
    assert applied.ok is False and "옛 버전" in applied.detail
    assert lab.files[product.ENV_FILE] == ENV_TEXT


def test_dns_that_points_elsewhere_or_nowhere_is_a_warning_not_a_failure(lab, monkeypatch):
    monkeypatch.setattr(ad, "DNS_FACTORY", lambda ns=None: FakeDns({NEW: ["203.0.113.10"]}))
    result = run(lab, "domain.preview", {"host": NEW, "aliases": [OLD]})
    dns = next(c for c in result.data["checks"] if c["key"] == "dns")
    assert dns["state"] == "warn"
    assert "다른 주소(203.0.113.10)" in dns["message"] and "앞단 프록시" in dns["message"]
    assert OLD in dns["message"], "풀리지 않는 별칭을 말하지 않았다"
    assert result.data["can_apply"] is True


# ── 적용: 정상 경로 ───────────────────────────────────────────────────────────


def test_apply_writes_cert_vhost_env_manifest_then_checks_and_restarts(lab):
    result = run(lab, "domain.apply", APPLY)
    assert result.ok, (result.detail, result.data)
    assert result.changed and not result.rolled_back
    assert [s["name"] for s in result.data["steps"]] == ["validate", "cert", "web", "config", "check", "services", "web_restart"]

    env = lab.files[product.ENV_FILE]
    assert df.env_get(env, "APP_BASE_URL") == f"https://{NEW}"
    assert df.env_get(env, "TLS_CERT_PATH") == NEW_CRT
    assert df.env_get(env, "SECRET_KEY") == "keep-me", "다른 env 줄이 사라졌다"
    assert lab.owners[product.ENV_FILE] == ("root", product.SERVICE_GROUP) and lab.modes[product.ENV_FILE] == 0o640

    manifest = json.loads(lab.files[df.MANIFEST_FILE])  # 엄격한 JSON 이어야 한다
    assert manifest["dns_name"] == NEW and manifest["alias_names"] == OLD
    assert manifest["version"] == "0.1.0-dev" and manifest["upstream_proxies"] == "10.0.0.96"

    vhost = lab.files[df.SITE_AVAILABLE]
    assert vhost.count(f"server_name {NEW} {OLD};") == 2
    assert f"ssl_certificate     {NEW_CRT};" in vhost

    assert lab.files[NEW_CRT] == NEW_PEM and lab.modes[NEW_KEY] == 0o600
    req = next(c for c in lab.calls if c[:2] == (OPENSSL, "req"))
    assert req[req.index("-addext") + 1] == f"subjectAltName=DNS:{NEW},DNS:{OLD},IP:{BIND}"

    order = [c for c in lab.calls if c in {(NGINX, "-t"), (SYSTEMCTL, "reload", "nginx.service")}]
    assert order == [(NGINX, "-t"), (SYSTEMCTL, "reload", "nginx.service")]
    assert (BIND, NEW, "/healthz") in lab.probes and (BIND, NEW, "/login") in lab.probes and (BIND, OLD, "/healthz") in lab.probes

    restarted = [c[2] for c in lab.calls if c[:2] == (SYSTEMCTL, "restart")]
    assert restarted == [product.WORKER_UNIT, product.SCHEDULER_UNIT, product.INDEX_UNIT], "꺼져 있던 대화형 레인을 켰다"
    assert lab.count(ad.restart_argv(product.WEB_UNIT, 3)) == 1
    assert result.data["web_restart"]["scheduled"] is True
    assert result.data["url"] == f"https://{NEW}"
    # 자체 확인이 유닛 재시작보다 먼저다(머리말: 되돌릴 때 새 env 로 뜬 유닛이 없어야 한다).
    first_restart = next(i for i, c in enumerate(lab.calls) if c[:2] == (SYSTEMCTL, "restart"))
    assert first_restart > lab.calls.index((SYSTEMCTL, "reload", "nginx.service"))


def test_the_web_restart_is_deferred_through_a_transient_timer():
    argv = ad.restart_argv(product.WEB_UNIT, 3)
    assert argv[0] == "/usr/bin/systemd-run" and "/usr/bin/systemd-run" in ALLOWED_BINARIES
    assert "--on-active=3" in argv and "--unit=clovirassist-web-restart" in argv
    assert "--timer-property=RemainAfterElapse=no" in argv, "울린 타이머가 남으면 같은 이름으로 다시 예약할 수 없다"
    assert argv[-3:] == ["/usr/bin/systemctl", "restart", product.WEB_UNIT]


def test_a_unit_that_fails_to_restart_is_a_warning_not_a_rollback(lab):
    lab.reply([SYSTEMCTL, "restart", product.SCHEDULER_UNIT], code=1, err="Job failed")
    result = run(lab, "domain.apply", APPLY)
    assert result.ok and not result.rolled_back
    services = next(s for s in result.data["steps"] if s["name"] == "services")
    assert services["ok"] is False
    assert any("예약 실행" in w for w in result.data["warnings"])
    assert df.env_get(lab.files[product.ENV_FILE], "APP_BASE_URL") == f"https://{NEW}"


def test_nothing_to_change_is_a_no_op_without_restarts(lab):
    first = run(lab, "domain.apply", {"host": OLD, "aliases": [], "cert": {"strategy": "keep"}, "restart_web": True})
    assert first.ok and first.changed is False, first.data
    assert not any(c[:2] in {(SYSTEMCTL, "restart"), (SYSTEMCTL, "reload")} for c in lab.calls)


# ── 적용: 실패와 되돌리기 ──────────────────────────────────────────────────────


def _unchanged(lab) -> None:
    assert lab.files[product.ENV_FILE] == ENV_TEXT
    assert lab.files[df.MANIFEST_FILE] == MANIFEST_TEXT
    assert lab.files[df.SITE_AVAILABLE] == df.render_vhost(TEMPLATE, BIND, OLD, [])
    assert NEW_CRT not in lab.files and NEW_KEY not in lab.files, "없던 새 인증서가 남았다"
    assert lab.files[OLD_CRT] == OLD_PEM and lab.files[OLD_KEY] == OLD_KEY_PEM


def test_a_failing_nginx_t_restores_the_files_and_reloads_the_old_config(lab):
    lab.reply_seq([NGINX, "-t"], [(1, "", "nginx: [emerg] unknown directive"), (0, "", "")])
    result = run(lab, "domain.apply", APPLY)
    assert result.ok is False and result.rolled_back is True
    _unchanged(lab)
    assert lab.count([NGINX, "-t"]) == 2, "되돌린 뒤 nginx -t 를 다시 하지 않았다"
    assert lab.count([SYSTEMCTL, "reload", "nginx.service"]) == 1, "되돌린 설정을 nginx 가 다시 읽지 않았다"
    rollback = next(s for s in result.data["steps"] if s["name"] == "rollback")
    assert rollback["ok"] is True
    assert not any(c[:2] == (SYSTEMCTL, "restart") for c in lab.calls)


def test_a_failing_self_check_rolls_back_and_restarts_nothing(lab, monkeypatch):
    monkeypatch.setattr(ad, "HTTPS_PROBE", lambda *a, **k: (502, "", None))
    result = run(lab, "domain.apply", APPLY)
    assert result.ok is False and result.rolled_back is True
    assert "확인을 통과하지 못했습니다" in result.detail
    _unchanged(lab)
    assert lab.count([SYSTEMCTL, "reload", "nginx.service"]) == 2, "적용 한 번 + 되돌림 한 번이어야 한다"
    assert not any(c[:2] == (SYSTEMCTL, "restart") for c in lab.calls)
    assert lab.count(ad.restart_argv(product.WEB_UNIT, 3)) == 0


def test_a_mismatched_pem_pair_is_rejected_before_anything_is_written(lab):
    stage_crt, stage_key = f"{product.TLS_DIR}/.staged.crt", f"{product.TLS_DIR}/.staged.key"
    lab.reply([OPENSSL, "x509", "-noout", "-in", stage_crt])
    lab.reply([OPENSSL, "pkey", "-noout", "-in", stage_key])
    lab.reply([OPENSSL, "x509", "-noout", "-pubkey", "-in", stage_crt], out="PUB-A")
    lab.reply([OPENSSL, "pkey", "-pubout", "-in", stage_key], out="PUB-B")
    secret = "-----BEGIN PRIVATE KEY-----\nPASTEDKEYSENTINEL\n-----END PRIVATE KEY-----"
    params = {**APPLY, "cert": {"strategy": "provided", "certificate": NEW_PEM, "private_key": secret}}
    result = run(lab, "domain.apply", params)
    assert result.ok is False and "한 쌍이 아닙니다" in result.detail
    _unchanged(lab)
    assert stage_crt not in lab.files and stage_key not in lab.files, "임시 자리에 개인키가 남았다"
    assert not any(c == (NGINX, "-t") for c in lab.calls)
    blob = json.dumps({"detail": result.detail, "data": result.data}, ensure_ascii=False)
    assert "PASTEDKEYSENTINEL" not in blob, "개인키가 결과에 실렸다"


def test_a_provided_certificate_without_the_new_name_is_refused(lab):
    stage_crt, stage_key = f"{product.TLS_DIR}/.staged.crt", f"{product.TLS_DIR}/.staged.key"
    lab.reply([OPENSSL, "x509", "-noout", "-in", stage_crt])
    lab.reply([OPENSSL, "pkey", "-noout", "-in", stage_key])
    lab.reply([OPENSSL, "x509", "-noout", "-pubkey", "-in", stage_crt], out="PUB")
    lab.reply([OPENSSL, "pkey", "-pubout", "-in", stage_key], out="PUB")
    lab.reply([OPENSSL, "x509", "-noout", "-subject", "-issuer", "-enddate", "-ext", "subjectAltName", "-in", stage_crt],
              out=x509_text([NEW]))
    params = {**APPLY, "cert": {"strategy": "provided", "certificate": NEW_PEM, "private_key": NEW_KEY_PEM}}
    result = run(lab, "domain.apply", params)
    assert result.ok is False and OLD in result.detail, "별칭이 없는 인증서를 받았다"
    _unchanged(lab)


def test_keeping_a_certificate_that_lacks_the_new_name_fails(lab):
    result = run(lab, "domain.apply", {**APPLY, "cert": {"strategy": "keep"}})
    assert result.ok is False and f"{NEW}가 없습니다" in result.detail
    _unchanged(lab)


def test_keeping_a_certificate_that_has_every_name_copies_it_to_the_new_name(lab):
    read = [OPENSSL, "x509", "-noout", "-subject", "-issuer", "-enddate", "-ext", "subjectAltName", "-in"]
    lab.reply(read + [OLD_CRT], out=x509_text([OLD, NEW]))
    result = run(lab, "domain.apply", {**APPLY, "cert": {"strategy": "keep"}})
    assert result.ok, result.detail
    assert lab.files[NEW_CRT] == OLD_PEM and lab.files[NEW_KEY] == OLD_KEY_PEM
    assert not any(c[:2] == (OPENSSL, "req") for c in lab.calls)


# ── 입력 검증 ─────────────────────────────────────────────────────────────────


def test_aliases_are_deduplicated_and_capped_at_five():
    out = ad.normalize_apply({"host": "New.Example.com.", "aliases": [OLD, OLD.upper(), "new.example.com"],
                              "cert": {"strategy": "self_signed"}})
    assert out["host"] == NEW and out["aliases"] == [OLD]
    with pytest.raises(v.InvalidSysopsValueError, match="최대 5개"):
        ad.normalize_apply({"host": NEW, "aliases": [f"a{i}.example.com" for i in range(6)], "cert": {"strategy": "keep"}})


@pytest.mark.parametrize("host", ["10.0.0.5", "localhost", "https://x.example.com", "x.example.com/path", "x.example.com:8443", ""])
def test_hosts_that_are_not_plain_names_are_refused(host):
    with pytest.raises(v.InvalidSysopsValueError):
        ad.normalize_apply({"host": host, "cert": {"strategy": "keep"}})


@pytest.mark.parametrize("cert", [None, {}, {"strategy": "letsencrypt"}, {"strategy": "provided", "certificate": "x"}])
def test_the_certificate_choice_must_be_one_of_three(cert):
    with pytest.raises(v.InvalidSysopsValueError):
        ad.normalize_apply({"host": NEW, "cert": cert})


def test_restart_web_must_be_a_real_boolean():
    with pytest.raises(v.InvalidSysopsValueError):
        ad.normalize_apply({"host": NEW, "cert": {"strategy": "keep"}, "restart_web": "yes"})


def test_preview_resolvers_are_addresses_and_at_most_three():
    assert ad.normalize_preview({"resolvers": "8.8.8.8, 1.1.1.1"})["resolvers"] == ["8.8.8.8", "1.1.1.1"]
    with pytest.raises(v.InvalidSysopsValueError):
        ad.normalize_preview({"resolvers": ["dns.google"]})
    with pytest.raises(v.InvalidSysopsValueError):
        ad.normalize_preview({"resolvers": ["1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4"]})


def test_the_engine_backs_up_exactly_the_files_apply_writes():
    touched = engine.get_action("domain.apply").touches(ad.normalize_apply({"host": NEW, "cert": {"strategy": "keep"}}))
    assert touched == (product.ENV_FILE, df.MANIFEST_FILE, df.SITE_AVAILABLE, NEW_CRT, NEW_KEY)


# ── 지연 재시작 · 유닛 목록 ──────────────────────────────────────────────────


def test_restart_deferred_schedules_one_transient_timer():
    runner = DomainRunner()
    runner.reply(ad.restart_argv(product.WEB_UNIT, 5))
    result = run(runner, "service.restart_deferred", {"unit": product.WEB_UNIT, "delay_seconds": 5})
    assert result.ok and result.changed
    assert runner.calls == [tuple(ad.restart_argv(product.WEB_UNIT, 5))]
    assert result.data["transient_unit"] == "clovirassist-web-restart"
    assert "5초 뒤에" in result.detail


@pytest.mark.parametrize("params", [
    {"unit": "sshd.service", "delay_seconds": 3},
    {"unit": product.WEB_UNIT, "delay_seconds": 1},
    {"unit": product.WEB_UNIT, "delay_seconds": 31},
    {"unit": product.WEB_UNIT, "delay_seconds": True},
])
def test_restart_deferred_takes_only_managed_units_and_a_short_delay(params):
    with pytest.raises(v.InvalidSysopsValueError):
        ad.normalize_restart_deferred(params)


def test_the_managed_units_include_the_conversational_and_index_lanes():
    assert product.WORKER_CONVERSATIONAL_UNIT in svc.MANAGED_UNITS
    assert product.INDEX_UNIT in svc.MANAGED_UNITS
    assert set(ad.BACKEND_UNITS) <= set(svc.MANAGED_UNITS)


def test_system_info_reports_the_domain_from_env_and_a_tolerantly_read_manifest(lab):
    lab.files[df.MANIFEST_FILE] = MANIFEST_TEXT.replace('"upstream_proxies"', '"alias_names": "' + OLD.upper() + '",\n  "upstream_proxies"')
    for argv in (["/usr/bin/hostnamectl", "status", "--static"], ["/usr/bin/df", "-h", "/"]):
        lab.reply(argv, out="x")
    result = run(lab, "system.info", {})
    domain = result.data["domain"]
    assert domain["canonical"] == OLD and domain["dns_name"] == OLD and domain["aliases"] == [OLD]
    assert domain["bind_ip"] == BIND and domain["cert_path"] == OLD_CRT
    assert domain["upstream_proxies"] == ["10.0.0.96"]
    assert not any(k.startswith("_") for k in domain), "env 원문이 응답에 실렸다"


# ── 자체 확인 프로브 자신을 진짜 TLS 로 잰다 ─────────────────────────────────


def _make_cert(tmp_path: Path, names: list[str]) -> tuple[str, str, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    crt_path, key_path = tmp_path / f"{names[0]}.crt", tmp_path / f"{names[0]}.key"
    crt_path.write_text(pem, encoding="utf-8")
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return pem, str(crt_path), str(key_path)


@pytest.fixture()
def tls_server(tmp_path):
    pem, crt, key = _make_cert(tmp_path, [NEW, OLD])
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(crt, key)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    seen: list[str] = []
    stop = threading.Event()

    def serve():
        listener.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except (TimeoutError, OSError):
                continue
            try:
                with ctx.wrap_socket(conn, server_side=True) as tls:
                    request = tls.recv(4096).decode("latin-1")
                    seen.append(request)
                    path = request.split(" ", 2)[1]
                    body = '<form id="login-form">' if path == "/login" else "ok"
                    tls.sendall(f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}".encode())
            except (ssl.SSLError, OSError):
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield {"pem": pem, "port": listener.getsockname()[1], "seen": seen, "tmp": tmp_path}
    stop.set()
    thread.join(2)
    listener.close()


def test_the_https_probe_passes_with_the_new_certificate_and_name(tls_server):
    status, body, error = ad._https_get("127.0.0.1", NEW, "/login", tls_server["pem"], timeout=5, port=tls_server["port"])
    assert (status, error) == (200, None) and ad.LOGIN_MARKER in body
    assert f"Host: {NEW}\r\n" in tls_server["seen"][-1], "Host 머리가 대표 이름이 아니다"
    status, _body, error = ad._https_get("127.0.0.1", OLD, "/healthz", tls_server["pem"], timeout=5, port=tls_server["port"])
    assert status == 200, error


def test_the_https_probe_fails_for_a_name_the_certificate_lacks(tls_server):
    status, _body, error = ad._https_get("127.0.0.1", "other.example.com", "/healthz", tls_server["pem"], timeout=5,
                                         port=tls_server["port"])
    assert status is None and error and error.startswith("tls:"), error


def test_the_https_probe_fails_when_the_server_serves_a_different_certificate(tls_server):
    other_pem, _crt, _key = _make_cert(tls_server["tmp"], ["unrelated.example.com", NEW])
    status, _body, error = ad._https_get("127.0.0.1", NEW, "/healthz", other_pem, timeout=5, port=tls_server["port"])
    assert status is None and error and error.startswith("tls:"), "다른 인증서를 믿고도 통과했다"
