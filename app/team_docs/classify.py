"""문서 자동 분류 (팀 공간 §17 개편).

기존 Notion 유형/카테고리 + 제목으로 신규 택소노미(문서 종류·업무 분야·기술 태그)를
결정론적으로 계산한다. 사용자 매핑 테이블(§6/§7) + 제목 키워드 휴리스틱. 동기화 때마다
호출되지만, 사용자가 수동으로 고친 문서는 sync가 덮어쓰지 않는다(classification_manual).

옵션 목록은 여기 상수로만 둔다(공통 상수, §9 — 여러 곳 하드코딩 금지).
"""

from __future__ import annotations

DOC_TYPES = ["회의록", "기획서", "설계서", "작업 계획서", "매뉴얼", "보고서", "참고자료", "기타"]
WORK_FIELDS = ["인프라", "자동화", "개발", "운영", "보안", "사내 업무", "기타"]
TECH_TAGS = [
    "Linux", "Windows", "VMware", "Hyper-V", "AWS", "Docker", "Kubernetes", "Ansible",
    "Jenkins", "GitLab", "Nexus", "Python", "PowerShell", "Java", "Redfish",
    "네트워크", "스토리지", "데이터베이스", "Redis", "Grafana",
]

# §6 유형 → (문서 종류, 업무 분야|None, 기술 태그|None)
_TYPE_MAP = {
    "Knowledge base": ("참고자료", None, None),
    "Linux": ("기타", None, "Linux"),
    "개발자 레퍼런스 문서": ("참고자료", None, None),
    "고객사 별 배포 가이드": ("매뉴얼", None, None),
    "교육": ("참고자료", None, None),
    "기타 문서": ("기타", None, None),
    "보안 점검 보고서": ("보고서", "보안", None),
    "사용자 매뉴얼": ("매뉴얼", None, None),
    "아키텍처 설계서": ("설계서", None, None),
    "요구 사항 정의서": ("기획서", None, None),
    "요구 사항 명세서": ("기획서", None, None),
    "작업 계획서": ("작업 계획서", None, None),
    "테스트 결과서": ("보고서", None, None),
    "포탈 개발 컨벤션": ("참고자료", "개발", None),
    "회의록": ("회의록", None, None),
    "보안 취약점 진단 가이드": ("매뉴얼", "보안", None),
    "퇴사 관련 문서": ("기타", "사내 업무", None),
}
# §7 카테고리 → (업무 분야|None, 문서 종류|None, 기술 태그|None)
_CAT_MAP = {
    "docker": (None, None, "Docker"),
    "데이터 모니터링": ("운영", None, None),
    "배포 관리": ("운영", None, None),
    "보안 컴플라이언스": ("보안", None, None),
    "운영 유지보수": ("운영", None, None),
    "인프라": ("인프라", None, None),
    "자동화 엔지니어링": ("자동화", None, None),
    "제품 및 플랫폼": ("개발", None, None),
    "지식 레퍼런스": (None, "참고자료", None),
    "행정 관리": ("사내 업무", None, None),
    "보안 정책": ("보안", None, None),
    "서버 모니터링": ("운영", None, None),
    "영업 프로세스": ("사내 업무", None, None),
    "계약 관리": ("사내 업무", None, None),
    "사내 포탈": ("개발", None, None),
    "보안점검": ("보안", None, None),
}
_TITLE_TECH = {
    "linux": "Linux", "리눅스": "Linux", "ubuntu": "Linux", "rocky": "Linux", "lvm": "Linux",
    "windows": "Windows", "윈도우": "Windows", "vmware": "VMware", "vcf": "VMware",
    "vsphere": "VMware", "esxi": "VMware", "tanzu": "VMware", "hyper-v": "Hyper-V",
    "aws": "AWS", "docker": "Docker", "도커": "Docker", "kubernetes": "Kubernetes",
    "k8s": "Kubernetes", "쿠버네티스": "Kubernetes", "microk8s": "Kubernetes",
    "ansible": "Ansible", "jenkins": "Jenkins", "gitlab": "GitLab", "nexus": "Nexus",
    "python": "Python", "파이썬": "Python", "powershell": "PowerShell", "java": "Java",
    "redfish": "Redfish", "네트워크": "네트워크", "스토리지": "스토리지",
    "데이터베이스": "데이터베이스", "mariadb": "데이터베이스", "oracle": "데이터베이스",
    "redis": "Redis", "grafana": "Grafana",
}
_TITLE_TYPE = [
    (["회의", "미팅", "협의", "meeting", "cadence", "시연"], "회의록"),
    (["보안취약점", "취약점", "보안 점검", "점검", "테스트", "결과"], "보고서"),
    (["요구사항", "요구 사항", "정의서"], "기획서"),
    (["설계", "아키텍처", "전략", "구조", "컨벤션", "scm"], "설계서"),
    (["작업", "지원", "오픈준비", "오픈 준비", "업그레이드", "upgrade", "버그", "수정",
      "변경", "체크리스트", "checklist", "todo", "고도화", "조치", "리팩토링"], "작업 계획서"),
    (["가이드", "설치", "절차", "방법", "생성", "연동", "setting"], "매뉴얼"),
    (["정보", "레퍼런스", "공유", "설정", "plugin", "repo", "커리큘럼"], "참고자료"),
]
_TITLE_FIELD = [
    (["보안취약점", "취약점", "보안", "컴플라이언스"], "보안"),
    (["docker", "도커", "kubernetes", "k8s", "쿠버", "jenkins", "gitlab", "ci/cd", "ci ",
      "파이프라인", "자동화", "containerd", "registry", "xscan", "ansible", "microk8s"], "자동화"),
    (["esxi", "vsphere", "vcf", "tanzu", "vmware", "네트워크", "스토리지", "os ", "인프라",
      "aci", "cisco", "kvm", "paloalto", "rocky", "ubuntu", "windows", "이미지", "디스크",
      "lvm", "cloud-init", "펌웨어", "tcp/ip", "chrony", "assembler", "aria"], "인프라"),
    (["포탈", "포털", "기능", "api", "request.js", "카탈로그", "yaml", "mariadb", "oracle",
      "dml", "ddl", "adfs", "빅데이터", "gpu", "엔티티", "외부시스템", "빌링", "요금", "액션"], "개발"),
    (["운영", "유지보수", "모니터링", "배포", "오픈", "eos", "장애"], "운영"),
    (["교육", "인수인계", "조직개편", "신입", "행정", "영업", "계약", "인사"], "사내 업무"),
]


def _heur(title: str, table) -> str | None:
    n = (title or "").lower()
    for kws, val in table:
        if any(k.lower() in n for k in kws):
            return val
    return None


def classify(type_names, category_names, title: str) -> tuple[str, str, list[str]]:
    """(문서 종류, 업무 분야, 기술 태그[]) 를 돌려준다. 항상 유효한 값(기타 폴백)."""
    doc_type: str | None = None
    work_field: str | None = None
    tags: list[str] = []

    for t in type_names or []:
        m = _TYPE_MAP.get((t or "").strip())
        if m:
            dt, wf, tag = m
            doc_type = doc_type or dt
            work_field = work_field or wf
            if tag and tag not in tags:
                tags.append(tag)
    for c in category_names or []:
        m = _CAT_MAP.get((c or "").strip())
        if m:
            wf, dt, tag = m
            work_field = work_field or wf
            doc_type = doc_type or dt
            if tag and tag not in tags:
                tags.append(tag)

    n = (title or "").lower()
    for k, v in _TITLE_TECH.items():
        if k in n and v not in tags:
            tags.append(v)

    if not doc_type:
        doc_type = _heur(title, _TITLE_TYPE) or "기타"
    if not work_field or work_field == "기타":
        wf = _heur(title, _TITLE_FIELD)
        work_field = wf or work_field or "기타"

    # 기술 태그는 고정 목록 밖 금지(공통 상수).
    tags = [t for t in tags if t in TECH_TAGS]
    return doc_type, work_field, tags
