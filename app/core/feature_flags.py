"""기능 플래그 — **소유자가 한 명뿐인** 단일 레지스트리 (spec §14.4, PLAN Phase 4).

## 고친 것 1: 설정 split-brain

`maintenance_mode` 와 `document_automation_enabled` 는 **두 곳에 동시에 정의돼 있었다**:
`config/feature-flags.json`(파일)과 `app/settings/registry.py`(DB, 관리 콘솔에서 편집).
실제로 값을 읽는 코드는 DB 쪽(`settings_cache`)만 본다. 즉 운영자가 서버에 들어가
`feature-flags.json` 의 `maintenance_mode` 를 true 로 바꾸고 서비스를 재시작해도 **아무 일도
일어나지 않는다.** 오류도 경고도 없다 — 점검 모드를 켰다고 믿은 채로 사용자 요청이 그대로
들어온다. 이런 종류는 사고가 난 뒤에야 알게 된다.

해결: 플래그마다 **소유자**를 명시하고, 소유자가 아닌 곳에서는 아예 값을 돌려주지 않는다.
  * `OWNER_FILE` — 이 JSON 파일이 정본. 배포 단위 토글(모듈 on/off)처럼 재시작급이고
    관리 콘솔에 노출할 필요가 없는 것들.
  * `OWNER_DB` — `app/settings/registry.py` + `app_settings` 테이블이 정본. 운영 중에
    관리자가 켜고 끄는 것들. `load_feature_flags()` 는 이 키들을 **돌려주지 않는다.**

파일에 DB 소유 키가 남아 있어도 무시한다(옛 배포와의 호환). 대신 두 곳에 같은 키가
살아 있지 않은지는 `tests/unit/test_feature_flag_registry.py` 가 못박는다.

## 고친 것 2: 요청마다 파일을 읽고 파싱하던 것

`load_feature_flags` 는 **요청마다** JSON 파일을 열어 읽고 파싱했다. 그런데 이 함수는 팀 채팅·
게시판·문서·놀이 라우터의 **의존성**으로 걸려 있다 — 즉 가장 뜨거운 폴링 경로가 매번 디스크
I/O 를 한다. 이제 `(경로, mtime_ns, size)` 로 파싱 결과를 캐시한다.

**stat 은 그대로 매번 한다.** 캐시를 프로세스 수명 동안 고정하지 않는 이유는
`app/core/assets.py` 가 정확히 그 실수로 한 번 데었기 때문이다(지문을 캐시했더니 파일을
바꿔도 옛 주소가 계속 나가 캐시 버스팅이 통째로 무효였고, 사용자에겐 "바뀐 게 없다"로
보였다). 여기서 같은 실수를 하면 "플래그를 껐는데 안 꺼진다"가 된다. stat 한 번은
read+json.loads 에 비하면 무료에 가깝다.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

OWNER_FILE = "file"
OWNER_DB = "db"


@dataclass(frozen=True)
class FlagSpec:
    """플래그 하나의 정의. `owner` 가 이 파일의 존재 이유다."""

    name: str
    default: bool
    owner: str
    description: str


# 정본 레지스트리. 새 플래그는 여기에 먼저 적는다 — 적지 않고 JSON 에만 넣으면
# 동등성 테스트가 잡는다(그 반대도 마찬가지).
FLAG_REGISTRY: dict[str, FlagSpec] = {
    spec.name: spec
    for spec in (
        # ── DB 소유(관리 콘솔 Settings 화면에서 켜고 끈다) ──────────────────────
        FlagSpec("maintenance_mode", False, OWNER_DB,
                 "유지보수 모드입니다. 설정 화면에서 바꾸며, 플래그 파일에 적어도 효과가 없습니다."),
        FlagSpec("document_automation_enabled", True, OWNER_DB,
                 "문서 자동화입니다. 설정 화면에서 바꿉니다."),
        # ── 파일 소유(배포 단위 토글) ─────────────────────────────────────────
        FlagSpec("self_approval_allowed", False, OWNER_FILE,
                 "본인이 올린 승인 요청을 본인이 승인할 수 있게 합니다."),
        FlagSpec("board_enabled", True, OWNER_FILE, "자유게시판 기능입니다."),
        FlagSpec("team_docs_enabled", True, OWNER_FILE, "팀 문서 기능입니다."),
        FlagSpec("games_enabled", True, OWNER_FILE, "팀 놀이 기능입니다."),
        FlagSpec("team_chat_enabled", True, OWNER_FILE, "팀 채팅 기능입니다."),
        # AI-45: 다른 선택적 모듈(게시판·팀 채팅·팀 문서·놀이)은 전부 테넌트별로 끌 수 있는데
        # AI 도우미 채팅만 빠져 있었다. 앱 셸(app/chat/router.py "/")은 이 플래그로 막지
        # 않는다 — 그 경로는 채팅 전용이 아니라 React 앱 전체의 진입점이다.
        # AI 기능 셋은 **DB 소유**다(계획 3.13, D-507). 예전에는 파일 소유였는데 그 파일은 운영에서
        # `/etc/clovirassist` 아래라 웹이 쓸 수 없어, 관리 화면에서 켜면 409 로 실패했다. AI 설정 화면이
        # 이 셋을 켜고 끈다. 옛 파일 값은 부팅 때 한 번 DB 로 옮긴다(`import_legacy_file_values`).
        FlagSpec("chat_enabled", True, OWNER_DB, "AI 도우미 채팅입니다(대화, 메시지, 사용 한도 조회)."),
        FlagSpec("game_ai_enabled", False, OWNER_DB,
                 "AI 퀴즈 생성입니다. 모델을 부르므로 기본값은 비활성화입니다."),
        FlagSpec("assistant_narrative_enabled", False, OWNER_DB,
                 "AI 도우미의 문장 요약 생성입니다. 비활성화해도 숫자와 목록은 모두 나옵니다."),
        # ── 소비자가 아직 없는 플래그 ─────────────────────────────────────────
        # 정직하게 적어 둔다: 읽는 코드가 하나도 없다. 지우지 않는 이유는 운영 파일에
        # 이미 들어가 있어서이고, 남겨 두는 대신 '효과 없음'을 여기에 못박는다 —
        # 관리자가 이 스위치를 켜고 무언가 달라지길 기대하지 않도록.
        FlagSpec("limited_service_actions_enabled", False, OWNER_FILE,
                 "(쓰는 기능 없음) 제한 서비스 모드입니다. 아직 이 값을 읽는 기능이 없습니다."),
    )
}

FILE_OWNED = tuple(
    name for name, spec in FLAG_REGISTRY.items() if spec.owner == OWNER_FILE
)
DB_OWNED = tuple(name for name, spec in FLAG_REGISTRY.items() if spec.owner == OWNER_DB)

# 파일이 정본인 플래그의 기본값. `load_feature_flags` 가 돌려주는 키 집합이 곧 이것이다.
_FILE_DEFAULTS: dict[str, bool] = {
    name: FLAG_REGISTRY[name].default for name in FILE_OWNED
}

FLAGS_FILENAME = "feature-flags.json"

# (해석된 경로, mtime_ns, size) → 파싱 결과. 파일이 바뀌면 키가 달라져 자동으로 무효화된다.
_cache: dict[tuple, dict] = {}
_cache_lock = threading.Lock()


def flags_path(config_dir: Path | str) -> Path:
    return Path(config_dir) / FLAGS_FILENAME


def _stat_key(path: Path) -> tuple | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), st.st_mtime_ns, st.st_size)


def _parse(path: Path) -> dict:
    """파일을 읽어 **파일 소유 플래그만** 담은 dict 로.

    DB 소유 키가 파일에 남아 있으면 조용히 버린다 — 돌려주면 부르는 쪽이 그 값을 진짜라고
    믿게 되고, 그게 바로 split-brain 이 다시 열리는 지점이다.
    """
    flags = dict(_FILE_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # 깨진 파일은 기본값으로 돈다. 여기서 예외를 던지면 파일 하나 때문에 앱 전체가
        # 500 이 된다 — 플래그는 그만한 권한을 가질 자격이 없다(fail-safe).
        return flags
    if not isinstance(data, dict):
        return flags
    for key, value in data.items():
        if key.startswith("_"):
            continue  # 주석 필드
        if key not in _FILE_DEFAULTS:
            continue
        # CORE-10: JSON 값을 그대로 담으면 `"game_ai_enabled": "false"`(따옴표 붙은
        # 문자열 — 손으로 편집할 때 흔한 실수)가 파이썬에서 **참**이라 파일엔 꺼져
        # 있는데 기능은 켜진다. 이 모듈의 존재 이유가 "설정했는데 아무 일도 안
        # 일어난다"를 없애는 것인데, 그 반대 방향(설정과 다르게 동작한다)이 뚫려
        # 있었다. 진짜 JSON boolean이 아니면 조용히 버리고 기본값으로 돈다 —
        # 문자열을 "true"/"false"로 해석해 주면 "0"/"no"/"off" 같은 다른 흔한
        # 오타에는 또 안 먹혀 문제를 절반만 없앤다.
        if not isinstance(value, bool):
            continue
        flags[key] = value
    return flags


def load_feature_flags(config_dir: Path | str) -> dict:
    """파일 소유 플래그의 현재 값. **DB 소유 키는 들어 있지 않다.**

    결과는 `(경로, mtime, 크기)` 로 캐시된다 — 팀 채팅처럼 뜨거운 라우터가 요청마다
    디스크를 읽지 않게. 파일을 고치면 stat 값이 달라져 다음 호출에서 다시 읽는다.
    """
    path = flags_path(config_dir)
    key = _stat_key(path)
    if key is None:
        return dict(_FILE_DEFAULTS)

    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None:
        # 사본을 준다 — 부르는 쪽이 dict 를 고쳐도 캐시가 오염되지 않게(불변성, §2-7).
        return dict(cached)

    parsed = _parse(path)
    with _cache_lock:
        # 캐시가 무한정 자라지 않게: 파일 하나뿐이라 항목도 사실상 하나다.
        # mtime 이 바뀔 때마다 새 키가 생기므로 옛 항목은 버린다.
        _cache.clear()
        _cache[key] = parsed
    return dict(parsed)


def reset_cache() -> None:
    """테스트용 — 파일을 만든 직후 mtime 해상도 때문에 같은 키가 나오는 경우를 피한다."""
    with _cache_lock:
        _cache.clear()


# 파일 소유였다가 DB 로 옮긴 플래그. 부팅 때 파일에 남은 옛 값을 한 번 DB 로 옮긴다.
MIGRATED_TO_DB: tuple[str, ...] = ("chat_enabled", "game_ai_enabled", "assistant_narrative_enabled")


def import_legacy_file_values(db, config_dir: Path | str, *, now=None) -> list[str]:
    """파일에 남은 옛 값을 DB 로 **한 번** 옮긴다. 옮긴 키 목록을 돌려준다. 커밋은 부르는 쪽 몫이다.

    - DB 에 이미 행이 있으면 건드리지 않는다(관리자가 화면에서 정한 값이 이긴다). 그래서 여러 번
      불러도 결과가 같고, 파일을 나중에 고쳐도 DB 값을 덮지 않는다.
    - 파일 값이 기본값과 같으면 행을 만들지 않는다(기본값은 행이 없어도 기본값이다).
    - 진짜 JSON boolean 만 믿는다(`_parse` 와 같은 규칙).

    업그레이드한 설치에서 `game_ai_enabled=true` 로 운영하던 곳이 조용히 꺼지지 않게 하려는 것이다.
    """
    from sqlalchemy.exc import IntegrityError

    from app.core.models_base import utcnow
    from app.settings.models import AppSetting

    path = flags_path(config_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    moved: list[str] = []
    stamp = now or utcnow()
    for key in MIGRATED_TO_DB:
        value = data.get(key)
        if not isinstance(value, bool) or value == FLAG_REGISTRY[key].default:
            continue
        if db.get(AppSetting, key) is not None:
            continue
        try:
            with db.begin_nested():
                db.add(AppSetting(
                    key=key, value_json=json.dumps(value), value_type="bool",
                    restart_required=False, updated_by=None, updated_at=stamp,
                ))
                db.flush()
        except IntegrityError:
            continue  # 다른 프로세스가 먼저 옮겼다
        moved.append(key)
    return moved


def db_flag(settings_cache, key: str) -> bool:
    """DB 소유 플래그의 지금 값. 캐시가 아직 없으면 레지스트리 기본값이다."""
    value = settings_cache.current_value(key) if settings_cache is not None else None
    if value is None:
        return FLAG_REGISTRY[key].default
    return bool(value)


def flag_value(key: str, *, settings_cache, config_dir) -> bool:
    """플래그의 지금 값 - 정본이 DB 든 파일이든 한 함수로 읽는다.

    AI 도우미의 도구처럼 여러 플래그를 함께 보는 자리가 쓴다(D-535). 소유자를 모르고 `db_flag` 로 파일 소유 플래그를
    읽으면 언제나 기본값이 나와, 관리자가 파일에서 끈 기능(게시판, 팀 채팅)이 도구에서는 켜진 채로 보인다.
    """
    spec = FLAG_REGISTRY[key]
    if spec.owner == OWNER_DB:
        return db_flag(settings_cache, key)
    return bool(load_feature_flags(config_dir).get(key, spec.default))
