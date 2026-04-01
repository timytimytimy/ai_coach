from server.routes.analysis import router as analysis_router
from server.routes.auth import router as auth_router
from server.routes.videos import router as videos_router
from server.routes.workouts import router as workouts_router

__all__ = [
    "analysis_router",
    "auth_router",
    "videos_router",
    "workouts_router",
]
