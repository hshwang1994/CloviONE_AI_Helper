"""제품 정체성 한 곳 — slug 에서 나오는 경로·유닛 이름·시스템 계정 (R13).

## 왜 모듈 하나인가

slug 는 한 단어인데 그 한 단어가 **열두 곳에 문자열로 박혀** 있었다: 특권 헬퍼 소켓 경로,
관리 콘솔이 제어할 수 있는 유닛 목록, 프록시 드롭인 파일 이름, `/etc/hosts` 표시자,
LLM 콘솔이 안내하는 서비스 계정 이름, 백업 안내문. 이름을 바꾸는 날 그중 하나를 빠뜨리면
**아무 오류도 안 난다** — 웹은 없는 소켓에 붙으려다 «도우미가 없습니다» 를 보여 주고,
콘솔의 서비스 제어는 없는 유닛 이름을 systemd 에 넘겨 조용히 실패한다. 이 저장소가 이미
여러 번 겪은 패턴이라(D-22) 정본을 하나로 둔다.

## 여기 있는 것과 없는 것

**있는 것**: 설치 레이아웃이 정하는 이름들. `deploy/install.sh` 가 만드는 경로와
`deploy/systemd/*.service` 가 쓰는 유닛 이름이 이 상수들과 **글자까지 같아야** 한다.
`tests/unit/test_product_identity.py` 가 그 일치를 지킨다.

**없는 것**: 설치처마다 다른 값(호스트명·IP·DB 주소·비밀). 그것은 `web.env` 와
`Settings` 의 일이고 여기 두면 다시 소스에 설치처가 박힌다.

## 왜 환경변수로 덮게 하지 않는가

한 설치는 한 slug 만 쓴다. 옛 slug 설치는 옛 코드를 돌고, 새 slug 설치는 이 코드를 돈다 —
같은 프로세스가 둘을 오갈 일이 없다. 덮어쓸 수 있게 만들면 «어느 값이 실제로 쓰였나» 를
런타임에 확인해야 하는 문제가 새로 생기는데, 그 대가로 얻는 것이 없다. 옛 설치에서 새
설치로 넘어가는 일은 프로세스가 아니라 **설치 스크립트**가 한다
(`deploy/install.sh` 의 legacy 이전 경로).
"""

from __future__ import annotations

# 제품 slug. 사용자 노출 이름은 `ClovirAssist`, 기술 slug 는 이것이다 (CLAUDE.md §0).
SLUG = "clovirassist"

# 시스템 계정. 예전 slug 는 경로(`clovirone-web-assistant`)와 계정(`clovirone-web`)이
# 서로 달라서, 어느 쪽을 적어야 하는지 매번 확인해야 했다. 같게 둔다.
SERVICE_USER = SLUG
SERVICE_GROUP = SLUG

# ── 설치 레이아웃 ──────────────────────────────────────────────────────────────
APP_DIR = f"/opt/{SLUG}"
ETC_DIR = f"/etc/{SLUG}"
VAR_DIR = f"/var/lib/{SLUG}"
BACKUP_DIR = f"/var/backups/{SLUG}"
LOG_DIR = f"/var/log/{SLUG}"
RUN_DIR = f"/run/{SLUG}"
TLS_DIR = f"{ETC_DIR}/tls"
SECRETS_DIR = f"{ETC_DIR}/secrets"
ENV_FILE = f"{ETC_DIR}/{SLUG}.env"

# nginx 가 쓰는 이름. vhost 파일명과 로그 파일 접두사가 같은 slug 를 따른다.
NGINX_SITE = SLUG
# `TLS_CERT_PATH` 가 없는 설치(개발·시험, 또는 앞단 프록시가 TLS 를 끊는 구성)에서만
# 쓰이는 자리. 운영 설치는 installer 가 `TLS_CERT_PATH` 를 항상 채운다.
SSL_FALLBACK_DIR = f"/etc/ssl/{SLUG}"

# ── systemd 유닛 ──────────────────────────────────────────────────────────────
# INSTALLATION.md §5 Stage 13 의 이름이 정본이다. `index` 는 아직 없다 — 색인 레인은
# S9 이 만들고(P-18), 그 Session 이 유닛·health probe·uninstall·복구까지 함께 넣는다
# (INSTALLATION.md §6.1 Installer 계약).
WEB_UNIT = f"{SLUG}-web.service"
WORKER_UNIT = f"{SLUG}-worker.service"
WORKER_CONVERSATIONAL_UNIT = f"{SLUG}-worker-conversational.service"
SCHEDULER_UNIT = f"{SLUG}-scheduler.service"
PRIVHELPER_UNIT = f"{SLUG}-privhelper.service"

#: 설치 스크립트가 설치·활성화하는 유닛 전부. 순서가 곧 기동 순서다.
ALL_UNITS: tuple[str, ...] = (
    PRIVHELPER_UNIT,
    WORKER_UNIT,
    WORKER_CONVERSATIONAL_UNIT,
    SCHEDULER_UNIT,
    WEB_UNIT,
)

#: 재부팅 뒤 **떠 있어야** 하는 유닛. 대화형 레인은 설정 플래그가 꺼져 있으면 정상적으로
#: exit(0) 해 `inactive (dead)` 가 되므로 여기 없다 (D-118).
ALWAYS_ACTIVE_UNITS: tuple[str, ...] = (
    PRIVHELPER_UNIT,
    WORKER_UNIT,
    SCHEDULER_UNIT,
    WEB_UNIT,
)

# ── 관리 콘솔이 건드리는 자리 ─────────────────────────────────────────────────
PRIVHELPER_SOCKET = f"{RUN_DIR}/privhelper.sock"
PRIVHELPER_BACKUP_ROOT = f"{BACKUP_DIR}/sysops"
PRIVHELPER_AUDIT_LOG = f"{LOG_DIR}/privhelper.jsonl"

TIMESYNCD_DROPIN = f"/etc/systemd/timesyncd.conf.d/99-{SLUG}.conf"
RESOLVED_DROPIN = f"/etc/systemd/resolved.conf.d/99-{SLUG}.conf"
PROXY_DROPIN_NAME = f"99-{SLUG}-proxy.conf"
HOSTS_MARKER = f"# {SLUG}"

# ── 옛 정체성 — 이전 경로에서만 쓴다 ──────────────────────────────────────────
# `deploy/install.sh` 의 legacy 이전이 이 이름들을 찾아 새 자리로 옮긴다. 런타임 코드가
# 이 값을 읽는 곳은 없어야 한다 — 있으면 옛 정체성이 제품에 남는다 (CLAUDE.md §0).
LEGACY_SLUG = "clovirone-web-assistant"
LEGACY_SERVICE_USER = "clovirone-web"
