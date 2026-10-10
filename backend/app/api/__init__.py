from fastapi import APIRouter

from app.api import (analysis, assets, audit, auth, dashboard, metrics, notices,
                     rules, sse, tasks, teams, users)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(teams.router)
api_router.include_router(notices.router)
api_router.include_router(users.router)
api_router.include_router(assets.router)
api_router.include_router(audit.router)
api_router.include_router(tasks.router)
api_router.include_router(analysis.router)
api_router.include_router(sse.router)
api_router.include_router(rules.router)
api_router.include_router(metrics.router)
