from fastapi import APIRouter, Request

from .blockchain import views as blockchain
from .transaction import views as transaction

router = APIRouter()


@router.get("/health/", name="API health check", tags=["Healthcheck"])
async def api_health_check(request: Request):
	# Backwards-compatible health endpoint.
	# Delegate to the node health implementation under /blockchain/health/.
	return await blockchain.health_check(request)

router.include_router(blockchain.router, prefix="/blockchain", tags=["Blockchain"])
router.include_router(transaction.router, prefix="/transaction", tags=["Transactions"])
