"""Admin console HTML shell (spec §24.4). RBAC is enforced by the JSON APIs;
this page requires operator+ (regular users are redirected to chat)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse

from app.core.deps import AuthContext, get_page_auth
from app.users.models import ROLE_USER

router = APIRouter(tags=["admin"])

# React 콘솔 셸(app/static/react/index.html). 인증은 이 라우트가 서버측에서 게이팅하고
# (미인증→/login), 화면 렌더는 React가 맡는다. no-store로 배포 때마다 새 셸을 받게 한다
# (셸이 참조하는 자산은 해시가 붙어 캐시 버스팅됨).
_REACT_INDEX = Path(__file__).resolve().parents[1] / "static" / "react" / "index.html"


def _react_shell() -> FileResponse:
    return FileResponse(_REACT_INDEX, headers={"Cache-Control": "no-store"})


@router.get("/admin")
def admin_console(request: Request, auth: AuthContext = Depends(get_page_auth)):
    if auth.user.must_change_password:
        return RedirectResponse("/change-password", status_code=303)
    if auth.user.role == ROLE_USER:
        return RedirectResponse("/", status_code=303)
    return _react_shell()
