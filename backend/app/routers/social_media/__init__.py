"""社媒功能路由集合。"""

from .analytics import router
from .topics import router as topic_router

router.include_router(topic_router, prefix="/topic", tags=["topics"])

__all__ = ["router"]
