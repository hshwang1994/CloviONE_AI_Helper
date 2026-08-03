"""놀이 입력 스키마 (경계 검증, extra=forbid)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from app.games.models import GAME_TYPES

# 정수여야 하는 방 설정 키(범위는 service 에서 clamp). 문자열이 와도 int 로 강제하거나 버린다.
_NUMERIC_CONFIG_KEYS = frozenset({"winners", "teams", "min", "max", "timer_seconds"})


class RoomCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    game_type: str
    max_players: int = 8
    allow_spectators: bool = True
    config: dict = {}

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("방 제목을 입력하세요.")
        if len(v) > 120:
            raise ValueError("방 제목은 120자 이하여야 합니다.")
        return v

    @field_validator("game_type")
    @classmethod
    def _gt(cls, v: str) -> str:
        if v not in GAME_TYPES:
            raise ValueError("지원하지 않는 게임입니다.")
        return v

    @field_validator("max_players")
    @classmethod
    def _mp(cls, v: int) -> int:
        return max(2, min(int(v or 8), 50))

    @field_validator("config")
    @classmethod
    def _cfg(cls, v: dict) -> dict:
        # 값은 허용된 스칼라로 제한(임의 중첩/거대 객체 차단). 예외 둘: 'options'는 짧은 문자열
        # 리스트(빠른 투표/사다리 선택지), 'questions'는 퀴즈 문제 리스트를 허용한다.
        out: dict = {}
        for k, val in (v or {}).items():
            if not isinstance(k, str):
                continue
            key = str(k)[:40]
            if key == "options" and isinstance(val, list):
                # 중복 라벨을 지우지 않는다 — 사다리는 같은 도착지(예: '꽝' 2개)가 의미가 있고,
                # 빠른 투표는 인덱스로 집계하므로 중복이 있어도 정합성에 무해하다. 예전엔 여기서
                # 조용히 dedup 해 프런트(중복 유지)와 개수가 어긋나 방이 시작 불가가 되거나
                # 사다리 당첨/꽝 개수가 바뀌었다.
                opts: list[str] = []
                for x in val[:10]:
                    if isinstance(x, (str, int, float)):
                        s = str(x).strip()[:40]
                        if s:
                            opts.append(s)
                if opts:
                    out[key] = opts
            elif key == "questions" and isinstance(val, list):
                qs = _clean_questions(val)
                if qs:
                    out[key] = qs
            elif key in _NUMERIC_CONFIG_KEYS:
                # 숫자 설정은 정수로 강제한다 — 조작된 문자열이 service 정수 연산에서 500을 내던 걸 막는다
                # (범위 clamp 는 service 가 담당). 숫자가 아니면 버려 service 기본값을 쓰게 한다.
                try:
                    out[key] = int(val)
                except (TypeError, ValueError):
                    continue
            elif isinstance(val, (str, int, float, bool)) and len(str(val)) <= 120:
                out[key] = val
        return out


def _clean_questions(val: list) -> list[dict]:
    """퀴즈 문제 리스트 정제: 각 {q, options[2~6], answer} 구조·범위를 강제한다(최대 20문항)."""
    qs: list[dict] = []
    for item in val[:20]:
        if not isinstance(item, dict):
            continue
        qtext = str(item.get("q", "")).strip()[:200]
        opts: list[str] = []
        for o in (item.get("options") or [])[:6]:
            if isinstance(o, (str, int, float)):
                s = str(o).strip()[:80]
                if s:
                    opts.append(s)
        try:
            ans = int(item.get("answer"))
        except (TypeError, ValueError):
            ans = 0
        if qtext and len(opts) >= 2 and 0 <= ans < len(opts):
            qs.append({"q": qtext, "options": opts, "answer": ans})
    return qs


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str

    @field_validator("text")
    @classmethod
    def _t(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("메시지를 입력하세요.")
        return v[:500]


class ReadyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready: bool = True


class VoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option: int

    @field_validator("option")
    @classmethod
    def _opt(cls, v: int) -> int:
        v = int(v)
        if v < 0:
            raise ValueError("선택지 번호가 올바르지 않습니다.")
        return v


class NumberInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int

    @field_validator("value")
    @classmethod
    def _val(cls, v: int) -> int:
        return int(v)  # 범위(min~max)는 방 설정에 따라 service에서 검증한다.


class QuizGenerateInput(BaseModel):
    """AI 퀴즈 생성 요청(§7-9). 주제로 문제를 만든다. topic은 데이터일 뿐, 지시로 쓰지 않는다."""

    model_config = ConfigDict(extra="forbid")

    topic: str
    count: int = 5
    num_options: int = 4

    @field_validator("topic")
    @classmethod
    def _topic(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("퀴즈 주제를 입력하세요.")
        return v[:200]

    @field_validator("count")
    @classmethod
    def _count(cls, v: int) -> int:
        return max(1, min(int(v or 5), 20))

    @field_validator("num_options")
    @classmethod
    def _num_options(cls, v: int) -> int:
        return max(2, min(int(v or 4), 6))
