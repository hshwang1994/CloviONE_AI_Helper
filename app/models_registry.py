"""Imports every model module so Base.metadata is complete.

Used by alembic/env.py for autogenerate and by tests. Add each new
module's models import here as milestones land.
"""

from __future__ import annotations

from app.core.models_base import Base  # noqa: F401

# Milestone model imports (append as they are created):
from app.approvals import models as approvals_models  # noqa: F401
from app.audit import models as audit_models  # noqa: F401
from app.board import models as board_models  # noqa: F401
from app.games import models as games_models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401
from app.backups import models as backups_models  # noqa: F401
from app.conversations import models as conversations_models  # noqa: F401
from app.health import models as health_models  # noqa: F401
from app.documents import models as documents_models  # noqa: F401
from app.notifications import models as notifications_models  # noqa: F401
from app.notion_mapping import models as notion_mapping_models  # noqa: F401
from app.observability import models as observability_models  # noqa: F401
from app.org import models as org_models  # noqa: F401
from app.settings import models as settings_models  # noqa: F401
from app.team_docs import models as team_docs_models  # noqa: F401
from app.tickets import models as tickets_models  # noqa: F401
from app.team_chat import models as team_chat_models  # noqa: F401
from app.core import versioning as versioning_models  # noqa: F401
from app.integrations import models as integrations_models  # noqa: F401
from app.jobs import models as jobs_models  # noqa: F401
from app.prompts import models as prompts_models  # noqa: F401
from app.runners import models as runners_models  # noqa: F401
from app.schedules import models as schedules_models  # noqa: F401
from app.templates import models as templates_models  # noqa: F401
from app.trash import models as trash_models  # noqa: F401
from app.users import models as users_models  # noqa: F401
from app.workflows import models as workflows_models  # noqa: F401
