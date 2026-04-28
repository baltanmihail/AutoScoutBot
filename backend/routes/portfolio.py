from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from backend.database import get_session
from backend.models import PortfolioItem, Startup, StartupScore
from backend.routes.profile import get_current_user_from_token

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

class PortfolioItemResponse(BaseModel):
    id: str
    name: str
    industry: str
    score: float
    rating: str
    column: str

class AddPortfolioRequest(BaseModel):
    startup_id: str
    column_id: str = "screening"

class MovePortfolioRequest(BaseModel):
    column_id: str

@router.get("", response_model=List[PortfolioItemResponse])
async def get_portfolio(
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Get user's portfolio items"""
    user = await get_current_user_from_token(authorization, session)
    
    stmt = (
        select(PortfolioItem, Startup, StartupScore)
        .join(Startup, PortfolioItem.startup_id == Startup.id)
        .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
        .where(PortfolioItem.user_id == user.id)
    )
    
    results = await session.execute(stmt)
    
    response = []
    for item, startup, score in results.all():
        # Determine rating based on score
        sc = score.ml_score if score and score.ml_score is not None else 0
        rating = "C"
        if sc >= 8: rating = "AAA"
        elif sc >= 7: rating = "AA"
        elif sc >= 6: rating = "A"
        elif sc >= 5: rating = "BBB"
        elif sc >= 4: rating = "BB"
        elif sc >= 3: rating = "B"
        
        response.append(PortfolioItemResponse(
            id=startup.id,
            name=startup.name,
            industry=startup.industries or startup.cluster or "Н/Д",
            score=sc,
            rating=rating,
            column=item.column_id
        ))
        
    return response

@router.post("")
async def add_to_portfolio(
    req: AddPortfolioRequest,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Add a startup to the portfolio"""
    user = await get_current_user_from_token(authorization, session)
    
    # Check if startup exists
    startup = await session.get(Startup, req.startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")
        
    # Check if already in portfolio
    existing = (await session.execute(
        select(PortfolioItem)
        .where(PortfolioItem.user_id == user.id, PortfolioItem.startup_id == req.startup_id)
    )).scalar_one_or_none()
    
    if existing:
        return {"status": "ok", "message": "Already in portfolio"}
        
    # Add
    new_item = PortfolioItem(
        user_id=user.id,
        startup_id=req.startup_id,
        column_id=req.column_id
    )
    session.add(new_item)
    await session.commit()
    
    return {"status": "ok", "message": "Added to portfolio"}

@router.put("/{startup_id}")
async def move_portfolio_item(
    startup_id: str,
    req: MovePortfolioRequest,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Move a startup to a different column"""
    user = await get_current_user_from_token(authorization, session)
    
    item = (await session.execute(
        select(PortfolioItem)
        .where(PortfolioItem.user_id == user.id, PortfolioItem.startup_id == startup_id)
    )).scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in portfolio")
        
    item.column_id = req.column_id
    await session.commit()
    
    return {"status": "ok"}

@router.delete("/{startup_id}")
async def remove_from_portfolio(
    startup_id: str,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Remove a startup from portfolio"""
    user = await get_current_user_from_token(authorization, session)
    
    stmt = delete(PortfolioItem).where(
        PortfolioItem.user_id == user.id, 
        PortfolioItem.startup_id == startup_id
    )
    await session.execute(stmt)
    await session.commit()
    
    return {"status": "ok"}

@router.get("/search")
async def search_startups_for_portfolio(
    q: str,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Simple autocomplete search to add startups to portfolio"""
    user = await get_current_user_from_token(authorization, session)
    if not q or len(q) < 2:
        return []
        
    stmt = (
        select(Startup.id, Startup.name, Startup.inn)
        .where(Startup.name.ilike(f"%{q}%") | Startup.inn.ilike(f"%{q}%"))
        .limit(10)
    )
    results = await session.execute(stmt)
    
    response = []
    for row in results.all():
        response.append({
            "id": row.id,
            "name": row.name,
            "inn": row.inn or ""
        })
    return response
