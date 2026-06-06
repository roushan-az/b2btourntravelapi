# app/core/templates.py
from fastapi import APIRouter

# You MUST define this router object
router = APIRouter()

# Example endpoint
@router.get("/hello")
async def hello():
    return {"message": "Hello from templates"}