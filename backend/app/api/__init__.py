from fastapi import APIRouter

from app.api import auth, tasks, sse, rules, metrics

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tasks.router)
api_router.include_router(sse.router)
api_router.include_router(rules.router)
api_router.include_router(metrics.router)
