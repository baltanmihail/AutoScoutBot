"""Search endpoint -- semantic search + ML scoring + pgvector."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, func, text, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session, DATABASE_URL
from backend.models import Startup, StartupScore, StartupFinancial, Query, QueryResult
from backend.schemas import SearchRequest, SearchResponse, SearchResult, StartupBrief, HistoryResponse, QueryHistoryItem
from backend.routes.profile import get_current_user_from_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


def _startup_to_feature_row(startup, financials: list) -> dict:
    """Convert ORM Startup + financials into a flat dict for the predictor."""
    row = {
        "name": startup.name,
        "company_description": startup.company_description or "",
        "project_description": startup.project_description or "",
        "product_description": startup.product_description or "",
        "technologies": startup.technologies or "",
        "industries": startup.industries or "",
        "product_names": startup.product_names or "",
        "project_names": startup.project_names or "",
        "patents": startup.patents or "",
        "cluster": startup.cluster or "",
        "status": startup.status or "",
        "year_founded": startup.year_founded or "",
        "trl": startup.trl,
        "irl": startup.irl,
        "mrl": startup.mrl,
        "crl": startup.crl,
    }
    for fin in financials:
        row[f"revenue_{fin.year}"] = fin.revenue
        row[f"profit_{fin.year}"] = fin.profit
    return row


async def _pgvector_search(
    session: AsyncSession,
    query_text: str,
    top_k: int = 100,
) -> list[tuple[str, float]]:
    """
    Phase 4: Semantic search using pgvector embeddings.
    Returns list of (startup_id, similarity_score) pairs.
    Falls back to empty list if embeddings are not available.
    """
    if "postgresql" not in DATABASE_URL:
        return []

    try:
        from backend.models import StartupEmbedding

        # Check if embeddings table has data
        count = (await session.execute(
            select(func.count(StartupEmbedding.id))
        )).scalar() or 0

        if count == 0:
            return []

        # Compute query embedding (using GigaChat or sentence-transformers)
        query_embedding = await _compute_query_embedding(query_text)
        if query_embedding is None:
            return []

        # pgvector cosine similarity search
        stmt = (
            select(
                StartupEmbedding.startup_id,
                (1 - StartupEmbedding.embedding.cosine_distance(query_embedding)).label("similarity"),
            )
            .order_by(text("similarity DESC"))
            .limit(top_k)
        )
        rows = (await session.execute(stmt)).all()
        return [(r[0], float(r[1])) for r in rows]

    except Exception as e:
        logger.debug("pgvector search unavailable: %s", e)
        return []


async def _compute_query_embedding(query_text: str):
    """Compute embedding vector for a search query."""
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        embedding = model.encode(query_text).tolist()
        return embedding
    except ImportError:
        return None
    except Exception as e:
        logger.warning("Embedding computation failed: %s", e)
        return None


@router.post("/", response_model=SearchResponse)
async def search_startups(
    req: SearchRequest,
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Main search endpoint.
    Pipeline: pgvector similarity -> keyword fallback -> ML re-scoring -> ranking.
    """
    user = None
    if authorization:
        user = await get_current_user_from_token(authorization, session)
        
        # Check limits (but do not deduct yet)
        if req.model_type == "max":
            if user.requests_max <= 0:
                raise HTTPException(status_code=403, detail="Лимит запросов Max исчерпан.")
        elif req.model_type == "pro":
            if user.requests_pro <= 0:
                raise HTTPException(status_code=403, detail="Лимит запросов Pro исчерпан.")
        else:
            if user.requests_standard <= 0:
                raise HTTPException(status_code=403, detail="Лимит запросов Standard исчерпан.")
        
        req.user_id = user.id

    candidate_limit = max(req.top_k * 10, 100)

    # --- Phase 4: Try pgvector semantic search first ---
    vector_hits = await _pgvector_search(session, req.query, top_k=candidate_limit)
    vector_id_set = {sid for sid, _ in vector_hits}
    vector_scores = {sid: sim for sid, sim in vector_hits}

    # --- Build SQL query for candidates ---
    stmt = (
        select(Startup, StartupScore)
        .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
        .where(Startup.status != "")
    )

    # Apply filters
    filters = req.filters or {}
    if "cluster" in filters:
        stmt = stmt.where(Startup.cluster == filters["cluster"])
    if "status" in filters:
        stmt = stmt.where(Startup.status == filters["status"])
    if "min_trl" in filters:
        stmt = stmt.where(Startup.trl >= int(filters["min_trl"]))
    if "min_year" in filters:
        stmt = stmt.where(Startup.year_founded >= int(filters["min_year"]))
    if "min_score" in filters:
        stmt = stmt.where(StartupScore.score_overall >= float(filters["min_score"]))

    # If we have vector hits, prefer those; otherwise fall back to keyword search
    if vector_id_set:
        stmt = stmt.where(Startup.id.in_(vector_id_set))
    elif req.query:
        # Keyword fallback (ILIKE with multiple words + exact full phrase)
        import re
        from sqlalchemy import or_
        
        query_lower = req.query.lower()
        words = re.findall(r'\b\w{3,}\b', query_lower)
        if not words:
            words = [query_lower]
            
        words = words[:10]  # Limit to max 10 words
        
        full_pattern = f"%{query_lower}%"
        conditions = [
            Startup.name.ilike(full_pattern),
            Startup.inn.ilike(full_pattern),
            Startup.company_description.ilike(full_pattern)
        ]
        
        for word in words:
            like_pattern = f"%{word}%"
            conditions.append(
                Startup.name.ilike(like_pattern) |
                Startup.company_description.ilike(like_pattern) |
                Startup.technologies.ilike(like_pattern) |
                Startup.industries.ilike(like_pattern) |
                Startup.product_names.ilike(like_pattern)
            )
            
        if conditions:
            stmt = stmt.where(or_(*conditions))

    # Fetch more candidates than needed for ML re-ranking
    stmt = stmt.order_by(
        StartupScore.ml_score.desc().nullslast(),
        StartupScore.score_overall.desc().nullslast(),
    ).limit(candidate_limit)

    rows = (await session.execute(stmt)).all()

    # --- Phase 2: ML re-scoring ---
    ml_predictor = None
    try:
        from scoring.predictor import get_predictor
        predictor = get_predictor()
        if predictor.is_ready:
            ml_predictor = predictor
    except Exception as e:
        logger.debug("ML predictor not available: %s", e)

    import re
    query_lower = req.query.lower() if req.query else ""
    query_words = set(re.findall(r'\b\w{3,}\b', query_lower))

    scored_candidates = []
    for startup, db_score in rows:
        vector_sim = vector_scores.get(startup.id, 0.0)
        
        # Compute pseudo-semantic similarity if pgvector missed
        if not vector_id_set and query_lower:
            s_name = startup.name.lower()
            if query_lower in s_name or s_name in query_lower:
                vector_sim = max(vector_sim, 0.9)
            elif startup.inn and query_lower in startup.inn:
                vector_sim = max(vector_sim, 0.95)
            else:
                desc_text = f"{startup.company_description or ''} {startup.technologies or ''} {startup.industries or ''}".lower()
                desc_words = set(re.findall(r'\b\w{3,}\b', desc_text))
                if query_words:
                    overlap = len(query_words.intersection(desc_words))
                    word_sim = overlap / len(query_words)
                    vector_sim = max(vector_sim, word_sim * 0.6)

        proxy_overall = db_score.score_overall if db_score else 0.0
        existing_ml = db_score.ml_score if db_score else None

        scored_candidates.append({
            "startup": startup,
            "db_score": db_score,
            "vector_sim": vector_sim,
            "proxy_overall": proxy_overall,
            "ml_score": existing_ml,
        })

    # Run batch ML prediction on candidates that don't have ML scores
    if ml_predictor:
        needs_prediction = [c for c in scored_candidates if c["ml_score"] is None]
        if needs_prediction:
            # Load financials for these startups
            startup_ids = [c["startup"].id for c in needs_prediction]
            fin_stmt = select(StartupFinancial).where(StartupFinancial.startup_id.in_(startup_ids))
            all_fins = (await session.execute(fin_stmt)).scalars().all()
            fin_map: dict[str, list] = {}
            for f in all_fins:
                fin_map.setdefault(f.startup_id, []).append(f)

            feature_rows = [
                _startup_to_feature_row(c["startup"], fin_map.get(c["startup"].id, []))
                for c in needs_prediction
            ]

            try:
                batch_scores = ml_predictor.predict_batch(feature_rows)
                for c, ml_scores in zip(needs_prediction, batch_scores):
                    c["ml_score"] = ml_scores.get("overall")
            except Exception as e:
                logger.warning("Batch ML prediction failed: %s", e)

    # --- Combined ranking: weighted score ---
    for c in scored_candidates:
        ml = c["ml_score"] or 0.0
        proxy = c["proxy_overall"]
        vsim = c["vector_sim"]

        # Weighted combination: ML (50%) + proxy (30%) + vector similarity (20%)
        if ml > 0:
            c["rank_score"] = ml * 0.5 + proxy * 0.3 + vsim * 10 * 0.2
        else:
            c["rank_score"] = proxy * 0.7 + vsim * 10 * 0.3

    scored_candidates.sort(key=lambda c: c["rank_score"], reverse=True)
    top_results = scored_candidates[:req.top_k]

    # --- Save query ---
    q = Query(
        user_id=req.user_id,
        query_text=req.query,
        model_type=req.model_type,
    )
    session.add(q)
    await session.flush()

    results = []
    for idx, c in enumerate(top_results):
        startup = c["startup"]
        db_score = c["db_score"]

        brief = StartupBrief(
            id=startup.id,
            name=startup.name,
            cluster=startup.cluster,
            status=startup.status,
            year_founded=startup.year_founded,
            score_overall=db_score.score_overall if db_score else 0,
            ml_score=c["ml_score"],
        )
        sr = SearchResult(
            startup=brief,
            rag_similarity=round(c["vector_sim"], 4),
            ai_relevance=round(c["rank_score"], 4),
            ml_score=c["ml_score"],
        )
        results.append(sr)

        qr = QueryResult(
            query_id=q.id,
            startup_id=startup.id,
            startup_name=startup.name,
            rag_similarity=round(c["vector_sim"], 4),
            ai_relevance=round(c["rank_score"], 4),
            ml_score=c["ml_score"],
            position=idx + 1,
            cluster=startup.cluster,
            technologies=startup.technologies or "",
        )
        session.add(qr)

    if user and results:
        if req.model_type == "max":
            user.requests_max -= 1
        elif req.model_type == "pro":
            user.requests_pro -= 1
        else:
            user.requests_standard -= 1

    await session.commit()

    return SearchResponse(
        query_id=q.id,
        results=results,
        total_candidates=len(scored_candidates),
    )

@router.get("/history", response_model=HistoryResponse)
async def get_search_history(
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session),
):
    """Возвращает историю поисковых запросов пользователя."""
    user = await get_current_user_from_token(authorization, session)
    
    stmt = (
        select(Query, func.count(QueryResult.id).label("results_count"))
        .outerjoin(QueryResult, Query.id == QueryResult.query_id)
        .where(Query.user_id == user.id)
        .group_by(Query.id)
        .order_by(Query.created_at.desc())
        .limit(30)
    )
    
    rows = (await session.execute(stmt)).all()
    
    history_items = []
    for q, count in rows:
        history_items.append(
            QueryHistoryItem(
                id=q.id,
                query_text=q.query_text,
                model_type=q.model_type,
                created_at=q.created_at.isoformat() if q.created_at else "",
                results_count=count
            )
        )
        
    return HistoryResponse(history=history_items)

@router.get("/history/{query_id}", response_model=SearchResponse)
async def get_search_history_details(
    query_id: int,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session),
):
    """Возвращает результаты конкретного поискового запроса из истории."""
    user = await get_current_user_from_token(authorization, session)
    
    q_stmt = select(Query).where(Query.id == query_id, Query.user_id == user.id)
    q = (await session.execute(q_stmt)).scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="Запрос не найден")
        
    res_stmt = (
        select(QueryResult, Startup, StartupScore)
        .join(Startup, QueryResult.startup_id == Startup.id)
        .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
        .where(QueryResult.query_id == query_id)
        .order_by(QueryResult.position.asc())
    )
    
    rows = (await session.execute(res_stmt)).all()
    
    results = []
    for qr, startup, db_score in rows:
        brief = StartupBrief(
            id=startup.id,
            name=startup.name,
            cluster=startup.cluster,
            status=startup.status,
            year_founded=startup.year_founded,
            score_overall=db_score.score_overall if db_score else 0,
            ml_score=qr.ml_score,
        )
        sr = SearchResult(
            startup=brief,
            rag_similarity=qr.rag_similarity,
            ai_relevance=qr.ai_relevance,
            ml_score=qr.ml_score,
        )
        results.append(sr)
        
    return SearchResponse(
        query_id=q.id,
        results=results,
        total_candidates=len(results),
    )

@router.delete("/history/{query_id}")
async def delete_search_history(
    query_id: int,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session),
):
    """Удаляет поисковый запрос из истории."""
    user = await get_current_user_from_token(authorization, session)
    
    q_stmt = select(Query).where(Query.id == query_id, Query.user_id == user.id)
    q = (await session.execute(q_stmt)).scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="Запрос не найден")
        
    # Delete related QueryResults first
    from sqlalchemy import delete
    await session.execute(delete(QueryResult).where(QueryResult.query_id == query_id))
    
    # Delete the Query itself
    await session.delete(q)
    await session.commit()
    
    return {"status": "success", "detail": "Запрос удален"}
