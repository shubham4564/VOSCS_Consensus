from json import JSONDecodeError

from fastapi import APIRouter, HTTPException, Request

from blockchain.utils.helpers import BlockchainUtils

router = APIRouter()


@router.get("/transaction_pool/", name="Get all transactions in pool")
async def transaction_pool(request: Request):
    node = request.app.state.node
    return node.transaction_pool.transactions


@router.post("/create/", name="Create transaction")
async def create_transaction(request: Request):
    try:
        node = request.app.state.node
        try:
            payload = await request.json()
        except JSONDecodeError:
            raise HTTPException(status_code=400, detail="Can not parse request body.")
        if "transaction" not in payload:
            raise HTTPException(status_code=400, detail="Missing transaction value")

        try:
            transaction = BlockchainUtils.decode(payload["transaction"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to decode transaction: {str(e)}")
        
        try:
            node.handle_transaction(transaction, from_api=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to handle transaction: {str(e)}")
            
        return {"message": "Received transaction"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
