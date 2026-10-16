"""메일 화면의 고정 안내 (D-572) — 받은 편지함에서 보낸 사람 자리에 그림(아이콘)이 서는 조건.

받는 쪽 메일 프로그램이 정하는 일이라 이 서버가 끝낼 수 없다. 화면(`InboxIconHelp`)은 이 목록을 그대로 그리고 조건을 지어내지 않는다.
항목은 `{provider, what, who, external, note}` 다 - 제공자 · 무엇이 보이는가 · 하는 사람 · 이 서버 밖의 일인가 · 덧붙임.
사실 근거: 클래식 · 새 Outlook 과 Microsoft 365 는 BIMI 를 그리지 않고, 같은 회사(테넌트) 받은 편지함의 보낸 사람 사진은 그 주소에 연결된
사서함 · 메일 연락처의 사진이다(인증 통과가 전제). Gmail · Apple · Yahoo 의 로고는 BIMI 이고 DMARC 강제 정책 · SVG Tiny PS 로고 · VMC 가
필요하다. 아이콘보다 먼저 인증이 통과해야 받은 편지함에 들어간다.
"""

from __future__ import annotations

INBOX_ICON_HELP: list[dict] = [
    {
        "provider": "Outlook(Microsoft 365)",
        "what": "같은 회사 Outlook은 보낸 사람 주소에 연결된 공유 사서함이나 메일 연락처의 사진을 보여 줍니다.",
        "who": "Microsoft 365 관리자",
        "external": True,
        "note": "SPF와 DKIM 인증이 통과해야 사진이 보입니다. 인증이 실패하면 물음표 아이콘과 「보낸 사람의 ID를 확인할 수 없습니다」 표시가 붙습니다.",
    },
    {
        "provider": "Gmail, Apple 메일, Yahoo",
        "what": "BIMI로 보낸 사람 자리에 회사 로고를 보여 줍니다. Outlook은 BIMI를 그리지 않습니다.",
        "who": "도메인 DNS 담당자와 인증서 발급 기관",
        "external": True,
        "note": "DMARC 정책이 quarantine 이나 reject 여야 하고, SVG Tiny PS 형식의 로고와 유료 VMC 인증서가 필요합니다.",
    },
    {
        "provider": "받은 편지함 배치",
        "what": "아이콘보다 먼저 인증이 통과해야 정크 메일함이 아니라 받은 편지함에 들어갑니다.",
        "who": "도메인 DNS 담당자와 회선 업체",
        "external": True,
        "note": "SPF, DKIM, 역방향 이름(PTR)이 통과하면 정크 분류가 줄어듭니다. 스팸 필터 예외는 필요하지 않습니다.",
    },
]
