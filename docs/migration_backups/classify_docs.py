"""109개 문서를 신규 택소노미로 분류(사용자 §6/§7 매핑 테이블 적용, 결정론적).

입력: team_docs_tagging_backup.json (원본 태깅)
출력: doc_classification.json  { page_id: {doc_type, work_field, tech_tags[], review, note} }
+ 분포 리포트 출력. 애매/미매핑은 '기타' + review=True 로 남긴다(임의 덮어쓰기 금지).
"""

import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
BACKUP = json.loads((HERE / "team_docs_tagging_backup.json").read_text(encoding="utf-8"))

DOC_TYPES = ["회의록", "기획서", "설계서", "작업 계획서", "매뉴얼", "보고서", "참고자료", "기타"]
WORK_FIELDS = ["인프라", "자동화", "개발", "운영", "보안", "사내 업무", "기타"]
TECH_TAGS = ["Linux", "Windows", "VMware", "Hyper-V", "AWS", "Docker", "Kubernetes", "Ansible",
             "Jenkins", "GitLab", "Nexus", "Python", "PowerShell", "Java", "Redfish",
             "네트워크", "스토리지", "데이터베이스", "Redis", "Grafana"]

# §6 유형 → (문서 종류, 업무 분야?, 기술 태그?, review?)
TYPE_MAP = {
    "Knowledge base": ("참고자료", None, None, False),
    "Linux": ("기타", None, "Linux", True),
    "개발자 레퍼런스 문서": ("참고자료", None, None, False),
    "고객사 별 배포 가이드": ("매뉴얼", None, None, False),
    "교육": ("참고자료", None, None, False),
    "기타 문서": ("기타", None, None, False),
    "보안 점검 보고서": ("보고서", "보안", None, False),
    "사용자 매뉴얼": ("매뉴얼", None, None, False),
    "아키텍처 설계서": ("설계서", None, None, False),
    "요구 사항 정의서": ("기획서", None, None, False),
    "요구 사항 명세서": ("기획서", None, None, False),
    "작업 계획서": ("작업 계획서", None, None, False),
    "테스트 결과서": ("보고서", None, None, False),
    "포탈 개발 컨벤션": ("참고자료", "개발", None, False),
    "회의록": ("회의록", None, None, False),
    "보안 취약점 진단 가이드": ("매뉴얼", "보안", None, False),
    "퇴사 관련 문서": ("기타", "사내 업무", None, False),
    "계약": ("기타", None, None, True),  # 계약서 형식이나 '계약서' 종류가 목록에 없어 검토
}

# §7 카테고리 → (업무 분야?, 문서 종류?, 기술 태그?, project_move?, review?)
CAT_MAP = {
    "docker": (None, None, "Docker", False, True),
    "고객 프로젝트": (None, None, None, True, False),  # 프로젝트 필드로(관계 유지), 분야 미지정
    "데이터 모니터링": ("운영", None, None, False, False),
    "데이터 모니터링 ": ("운영", None, None, False, False),
    "배포 관리": ("운영", None, None, False, False),
    "보안 컴플라이언스": ("보안", None, None, False, False),
    "운영 유지보수": ("운영", None, None, False, False),
    "인프라": ("인프라", None, None, False, False),
    "자동화 엔지니어링": ("자동화", None, None, False, False),
    "제품 및 플랫폼": ("개발", None, None, False, False),
    "지식 레퍼런스": (None, "참고자료", None, False, False),
    "행정 관리": ("사내 업무", None, None, False, False),
    "보안 정책": ("보안", None, None, False, False),
    "서버 모니터링": ("운영", None, None, False, False),
    "영업 프로세스": ("사내 업무", None, None, False, False),
    "계약 관리": ("사내 업무", None, None, False, False),
    "사내 포탈": ("개발", None, None, False, False),
    "보안점검": ("보안", None, None, False, False),
}

# 제목에서 기술 태그를 유추(정확 매칭 + 흔한 별칭).
TITLE_TECH = {
    "linux": "Linux", "리눅스": "Linux", "windows": "Windows", "윈도우": "Windows",
    "vmware": "VMware", "vcf": "VMware", "vsphere": "VMware", "esxi": "VMware",
    "hyper-v": "Hyper-V", "hyperv": "Hyper-V", "aws": "AWS", "docker": "Docker", "도커": "Docker",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes", "쿠버네티스": "Kubernetes",
    "ansible": "Ansible", "앤서블": "Ansible", "jenkins": "Jenkins", "젠킨스": "Jenkins",
    "gitlab": "GitLab", "nexus": "Nexus", "python": "Python", "파이썬": "Python",
    "powershell": "PowerShell", "파워쉘": "PowerShell", "java": "Java", "자바": "Java",
    "redfish": "Redfish", "네트워크": "네트워크", "스토리지": "스토리지",
    "데이터베이스": "데이터베이스", "database": "데이터베이스", "db": "데이터베이스",
    "redis": "Redis", "grafana": "Grafana", "그라파나": "Grafana",
}


def tech_from_title(title):
    n = (title or "").lower()
    tags = []
    for k, v in TITLE_TECH.items():
        if k in n and v not in tags:
            tags.append(v)
    return tags


# 매핑으로 결정 못한 문서를 제목 키워드로 보강(결정론적, 검토 가능).
TITLE_TYPE = [
    (["회의", "미팅", "협의", "meeting", "cadence", "시연"], "회의록"),
    (["보안취약점", "취약점", "보안 점검", "점검", "테스트", "결과"], "보고서"),
    (["요구사항", "요구 사항", "정의서"], "기획서"),
    (["설계", "아키텍처", "전략", "구조", "컨벤션", "scm"], "설계서"),
    (["작업", "지원", "오픈 준비", "오픈준비", "업그레이드", "upgrade", "버그", "수정",
      "변경", "체크리스트", "checklist", "todo", "고도화", "조치", "리팩토링"], "작업 계획서"),
    (["가이드", "설치", "절차", "방법", "생성", "연동", "setting"], "매뉴얼"),
    (["정보", "레퍼런스", "공유", "설정", "plugin", "repo", "커리큘럼"], "참고자료"),
]
TITLE_FIELD = [
    (["보안취약점", "취약점", "보안", "컴플라이언스"], "보안"),
    (["docker", "도커", "kubernetes", "k8s", "쿠버", "jenkins", "gitlab", "ci/cd", "ci ",
      "파이프라인", "자동화", "containerd", "registry", "xscan", "ansible", "microk8s"], "자동화"),
    (["esxi", "vsphere", "vcf", "tanzu", "vmware", "네트워크", "스토리지", "os ", "인프라",
      "l4", "aci", "cisco", "kvm", "paloalto", "rocky", "ubuntu", "windows", "이미지",
      "디스크", "lvm", "cloud-init", "펌웨어", "tcp/ip", "chrony", "assembler", "aria"], "인프라"),
    (["포탈", "포털", "기능", "api", "request.js", "카탈로그", "yaml", "mariadb", "oracle",
      "dml", "ddl", "adfs", "빅데이터", "gpu", "엔티티", "외부시스템", "cytoscape",
      "빌링", "요금", "ad 연동", "액션"], "개발"),
    (["운영", "유지보수", "모니터링", "배포", "오픈", "eos", "장애"], "운영"),
    (["교육", "인수인계", "조직개편", "신입", "행정", "영업", "계약", "인사"], "사내 업무"),
]


def heur(title, table):
    n = (title or "").lower()
    for kws, val in table:
        if any(k.lower() in n for k in kws):
            return val
    return None


out = {}
dt_c, wf_c, tag_c, review = Counter(), Counter(), Counter(), 0
for d in BACKUP["documents"]:
    types = [t for t in d.get("type_names", []) if t]
    cats = [c for c in d.get("category_names", []) if c]
    doc_type, work_field, tags, rev, notes = None, None, [], False, []

    for t in types:
        m = TYPE_MAP.get(t.strip())
        if m:
            dt, wf, tag, r = m
            doc_type = doc_type or dt
            work_field = work_field or wf
            if tag and tag not in tags:
                tags.append(tag)
            rev = rev or r
        else:
            notes.append(f"유형 미매핑:{t}")
            rev = True
    for c in cats:
        m = CAT_MAP.get(c.strip())
        if m:
            wf, dt, tag, projmove, r = m
            if wf and not work_field:
                work_field = wf
            if dt and not doc_type:
                doc_type = dt
            if tag and tag not in tags:
                tags.append(tag)
            rev = rev or r
        else:
            notes.append(f"카테고리 미매핑:{c}")
            rev = True

    # 제목 기반 기술 태그 보강
    for tg in tech_from_title(d.get("title", "")):
        if tg not in tags:
            tags.append(tg)

    # 제목 휴리스틱으로 보강.
    if not doc_type:
        doc_type = heur(d.get("title", ""), TITLE_TYPE)
        if not doc_type:
            doc_type = "기타"
            rev = True
            notes.append("문서종류 미결정")
    if not work_field or work_field == "기타":
        wf = heur(d.get("title", ""), TITLE_FIELD)
        if wf:
            work_field = wf
        elif not work_field:
            work_field = "기타"
            rev = True
            notes.append("분야 미결정")

    out[d["page_id"]] = {
        "title": d.get("title"), "doc_type": doc_type, "work_field": work_field,
        "tech_tags": tags, "project_ids": d.get("project_ids", []),
        "project_names": d.get("project_names", []), "review": rev, "notes": notes,
    }
    dt_c[doc_type] += 1
    wf_c[work_field] += 1
    for tg in tags:
        tag_c[tg] += 1
    review += 1 if rev else 0

(HERE / "doc_classification.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("총 문서:", len(out), "| 검토 필요:", review)
print("문서 종류 분포:", dict(dt_c.most_common()))
print("업무 분야 분포:", dict(wf_c.most_common()))
print("기술 태그 분포:", dict(tag_c.most_common()))
