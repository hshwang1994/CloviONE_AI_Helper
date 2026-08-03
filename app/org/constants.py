"""조직(organization) 고정 상수.

제품화 대비(§7.1.A)로 organizations 를 1급 엔티티로 두되, 지금은 단일 조직 한 행만 쓴다.
그 한 행의 id 를 랜덤 UUID 로 두면 마이그레이션·시드·테스트가 서로 다른 값을 보게 되므로,
채팅 '전체 방'(_GLOBAL_ROOM_ID)·문서 sync 싱글턴(SYNC_STATE_ID)과 같은 관례로 **고정 id**를 쓴다.

여기 값은 마이그레이션(0022)과 애플리케이션 코드가 공유하는 단 하나의 정의다 — 두 곳에
따로 적어 두면 반드시 어긋난다.
"""

from __future__ import annotations

# 36자(8-4-4-4-12) UUID 모양의 고정 id. 마지막 그룹에 'org1'을 넣어 DB를 눈으로 볼 때
# 바로 알아볼 수 있게 한다(chat_rooms 의 '0000cha70001' 과 같은 관례).
DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"
DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "ClovirONE"

# 조직 상태. 지금은 active 하나만 쓰지만, 제품화 때 정지/해지를 붙일 자리를 열어 둔다.
ORG_ACTIVE = "active"
ORG_SUSPENDED = "suspended"
