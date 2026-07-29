"""조직 명부 — 부서(department)와 직책(job title) 목록.

users.department/title이 자유 입력 문자열이던 시절에는 'ClovirONE팀'과 'ClovirOne팀'이
서로 다른 부서였고, 부서명이 바뀌면 전 직원의 행을 하나씩 고쳐야 했다. 이름을 여기
한 곳에만 두고 사용자는 FK로 가리키게 해서, 한 곳을 고치면 전원에 반영되게 한다.
"""
