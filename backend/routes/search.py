"""Search endpoint -- semantic search + ML scoring + pgvector."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, func, text, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session, DATABASE_URL
from backend.models import Startup, StartupScore, StartupFinancial, Query, QueryResult, ExternalData
from backend.schemas import SearchRequest, SearchResponse, SearchResult, StartupBrief, HistoryResponse, QueryHistoryItem
from backend.routes.profile import get_current_user_from_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])

# Служебные слова, совпадение по ним слабо различает стартапы; не используем в OR alone.
_RU_STOP = frozenset(
    "и в на с по к о об от у за из для как что это какой которого которой"
    " при без над под пред все или же да не мы вы их он она оно а но то бы ли быть ещё еще"
    " также уже только очень мне нас вас тут там этот эта мой ваш наш вашего от до из"
    " стартап стартапы проект проекты ищу сфере сферу нужен нужно желательно ищем".split()
)


def _query_tokens(query_lower: str) -> list[str]:
    """Слова/токены запроса (рус/лат, длина >= 3), без стоп-слов."""
    import re

    raw = re.findall(r"[0-9A-Za-zА-Яа-яЁё]{3,}", query_lower)
    out = [t for t in raw if t not in _RU_STOP]
    if not out and raw:
        out = list(raw)
    if not out and len(query_lower.strip()) >= 3:
        return [query_lower.strip()[:500]]
    return out


def _relevance_01_query(startup, query_lower: str, tokens: list[str]) -> float:
    """
    Оценка 0..1: насколько карточка стартапа пересекается с текстом запроса
    (имя, описания, технологии, продукты, отрасль, кластер).
    """
    if not query_lower or not tokens:
        return 0.0
    parts = [
        startup.name or "",
        startup.company_description or "",
        startup.technologies or "",
        startup.industries or "",
        startup.product_names or "",
        startup.product_description or "",
        startup.project_names or "",
        startup.project_description or "",
        startup.cluster or "",
    ]
    text = " ".join(parts).lower()
    name = (startup.name or "").lower()
    n = max(len(tokens), 1)
    strong_hits = 0
    name_hits = 0
    for t in tokens:
        if t in text:
            strong_hits += 1
        if t in name:
            name_hits += 1
    # Фраза целиком (если не слишком длинная)
    if 10 <= len(query_lower) <= 200 and query_lower in text:
        return min(1.0, 0.35 + 0.55 * (strong_hits / n) + 0.1 * (name_hits / n))
    return min(1.0, 0.1 + 0.75 * (strong_hits / n) + 0.15 * (name_hits / n))


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
    if req.exclude_ids:
        vector_hits = [(sid, sim) for sid, sim in vector_hits if sid not in req.exclude_ids]
    
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
    if req.exclude_ids:
        stmt = stmt.where(Startup.id.notin_(req.exclude_ids))

    # If we have vector hits, prefer those; otherwise fall back to keyword search
    if vector_id_set:
        stmt = stmt.where(Startup.id.in_(vector_id_set))
    elif req.query:
        # Keyword fallback (ILIKE with multiple words + exact full phrase)
        from sqlalchemy import or_
        
        query_lower = req.query.lower()
        words = _query_tokens(query_lower)
        
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

    # ВАЖНО: не сортировать по ML в SQL до ранжирования по запросу — иначе при OR по словам
    # всегда в выборку попадают одни и те же «топ по ML», а релевантность запросу теряется.
    fetch_limit = candidate_limit
    if not vector_id_set:
        fetch_limit = min(2000, max(candidate_limit * 20, 400))

    stmt = stmt.limit(fetch_limit)
    rows = (await session.execute(stmt)).all()

    # Если pgvector вернул порядок — восстанавливаем его (SQL IN не сохраняет similarity order)
    if vector_id_set and vector_hits:
        order = [sid for sid, _ in vector_hits]
        pos = {sid: i for i, sid in enumerate(order)}
        rows = sorted(rows, key=lambda r: pos.get(r[0].id, 10**9))

    # --- Phase 2: ML re-scoring ---
    ml_predictor = None
    try:
        from scoring.predictor import get_predictor
        predictor = get_predictor()
        if predictor.is_ready:
            ml_predictor = predictor
    except Exception as e:
        logger.debug("ML predictor not available: %s", e)

    query_lower = (req.query or "").lower()
    query_tokens = _query_tokens(query_lower)

    scored_candidates = []
    for startup, db_score in rows:
        vector_sim = float(vector_scores.get(startup.id, 0.0) or 0.0)
        if vector_id_set:
            # similarity 0..1 от pgvector
            relevance_01 = max(0.0, min(1.0, vector_sim))
        else:
            relevance_01 = _relevance_01_query(startup, query_lower, query_tokens)

        proxy_overall = db_score.score_overall if db_score else 0.0
        existing_ml = db_score.ml_score if db_score else None

        scored_candidates.append({
            "startup": startup,
            "db_score": db_score,
            "vector_sim": vector_sim,
            "relevance_01": relevance_01,
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

    # --- Итоговый ранк: в приоритете релевантность запросу, ML/proxy — уточнение ---
    for c in scored_candidates:
        ml = c["ml_score"] or 0.0
        proxy = c["proxy_overall"]
        rel = c["relevance_01"]
        
        # Если это текстовый поиск и нет никаких внятных пересечений по токенам (rel <= 0.15)
        # мы жестко занижаем оценку, чтобы высокооцененные ML-моделью стартапы не вылезали 
        # просто так по OR-совпадениям.
        if not vector_id_set:
            if rel <= 0.15:
                # Нет пересечений вообще
                c["rank_score"] = 0.1 * ml + 0.1 * proxy
            else:
                # Текстовое совпадение: умножаем ml и proxy на relevance, чтобы нерелевантные стартапы не выигрывали за счет скора
                penalty = min(1.0, rel * 2.0)
                c["rank_score"] = 0.55 * (rel * 10.0) + 0.25 * (ml * penalty) + 0.20 * (proxy * penalty)
        else:
            c["rank_score"] = 0.50 * (rel * 10.0) + 0.32 * ml + 0.18 * proxy

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
            company_description=startup.company_description or "",
            technologies=startup.technologies or "",
        )
        sr = SearchResult(
            startup=brief,
            rag_similarity=round(c["relevance_01"], 4),
            ai_relevance=round(c["rank_score"], 4),
            ml_score=c["ml_score"],
        )
        results.append(sr)

        qr = QueryResult(
            query_id=q.id,
            startup_id=startup.id,
            startup_name=startup.name,
            rag_similarity=round(c["relevance_01"], 4),
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

@router.get("/dashboard_startups")
async def get_dashboard_startups(
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Возвращает стартапы для дашборда:
    - Сначала берем до 5 стартапов из последних поисков пользователя.
    - Добавляем 3 "стартовых" топовых стартапов для всех.
    Удаляем дубликаты.
    """
    import json
    
    user = await get_current_user_from_token(authorization, session)
    
    # 1. Get recent startups from user's queries
    recent_stmt = (
        select(Startup, StartupScore)
        .join(QueryResult, QueryResult.startup_id == Startup.id)
        .join(Query, Query.id == QueryResult.query_id)
        .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
        .where(Query.user_id == user.id)
        .order_by(Query.created_at.desc(), QueryResult.ai_relevance.desc())
        .limit(10)
    )
    recent_rows = (await session.execute(recent_stmt)).all()
    
    seen_ids = set()
    collected = []
    
    for startup, sc in recent_rows:
        if startup.id not in seen_ids:
            seen_ids.add(startup.id)
            collected.append((startup, sc, True))
            if len(collected) >= 5:
                break
                
    # 2. Get global top startups
    top_stmt = (
        select(Startup, StartupScore)
        .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
        .where(Startup.status != "")
        .order_by(StartupScore.score_overall.desc().nullslast())
        .limit(3)
    )
    top_rows = (await session.execute(top_stmt)).all()
    
    for startup, sc in top_rows:
        if startup.id not in seen_ids:
            seen_ids.add(startup.id)
            collected.append((startup, sc, False))

    if not seen_ids:
        return {"top_startups": []}

    # Fetch financials for CAGR
    fin_stmt = select(StartupFinancial).where(StartupFinancial.startup_id.in_(seen_ids))
    all_fins = (await session.execute(fin_stmt)).scalars().all()
    fin_map = {}
    for f in all_fins:
        fin_map.setdefault(f.startup_id, []).append(f)

    # Fetch external data for Z-score and Team size
    ext_stmt = select(ExternalData).where(ExternalData.startup_id.in_(seen_ids))
    all_exts = (await session.execute(ext_stmt)).scalars().all()
    ext_map = {}
    for e in all_exts:
        ext_map.setdefault(e.startup_id, []).append(e)

    results = []
    for startup, sc, is_recent in collected:
        fins = fin_map.get(startup.id, [])
        exts = ext_map.get(startup.id, [])

        # Calculate CAGR (Compound Annual Growth Rate) over available years
        revenue_cagr = None
        if fins:
            fins_sorted = sorted(fins, key=lambda x: x.year)
            start_fin = next((f for f in fins_sorted if f.revenue and f.revenue > 0), None)
            end_fin = next((f for f in reversed(fins_sorted) if f.revenue and f.revenue > 0), None)
            if start_fin and end_fin and start_fin.year < end_fin.year:
                years = end_fin.year - start_fin.year
                if years > 0:
                    revenue_cagr = (end_fin.revenue / start_fin.revenue) ** (1 / years) - 1

        # Calculate Z-Score (Altman for private non-manufacturing: 6.56T1 + 3.26T2 + 6.72T3 + 1.05T4) and Team Size
        z_score = None
        team_size = None
        for ext in exts:
            try:
                data = json.loads(ext.data_json)
                if ext.source == "checko":
                    # Checko might have employee count in company_details
                    comp_data = data.get("company_details", {})
                    if "СведССЧР" in comp_data:
                        team_size = comp_data["СведССЧР"].get("КолРаб")
                if ext.source == "bfo":
                    # BFO for Z-score (latest year)
                    if data:
                        latest_year = max(data.keys(), key=int)
                        bfo_fin = data[latest_year]
                        ta = bfo_fin.get("total_assets", 0)
                        if ta > 0:
                            tl = bfo_fin.get("total_liabilities", 0)
                            ca = bfo_fin.get("current_assets", 0)
                            cl = bfo_fin.get("current_liabilities", 0)
                            re = bfo_fin.get("retained_earnings", 0)
                            ebit = bfo_fin.get("operating_profit", 0)
                            eq = bfo_fin.get("equity", 0)

                            t1 = (ca - cl) / ta
                            t2 = re / ta
                            t3 = ebit / ta
                            t4 = eq / tl if tl > 0 else 0

                            z_score = 6.56 * t1 + 3.26 * t2 + 6.72 * t3 + 1.05 * t4
            except Exception:
                pass

        revenue_latest = None
        if fins:
            fins_sorted = sorted(fins, key=lambda x: x.year)
            if fins_sorted[-1].revenue:
                revenue_latest = fins_sorted[-1].revenue

        results.append({
            "id": startup.id,
            "name": startup.name,
            "inn": startup.inn,
            "cluster": startup.cluster,
            "status": startup.status,
            "year_founded": startup.year_founded,
            "trl": startup.trl,
            "irl": startup.irl,
            "crl": startup.crl,
            "mrl": startup.mrl,
            "patents": startup.patents,
            "score_overall": sc.score_overall if sc else 5.0,
            "score_market_potential": sc.score_market_potential if sc else 5.0,
            "ml_score": sc.ml_score if sc else None,
            "company_description": startup.company_description or startup.technologies or "Описание отсутствует.",
            "is_recent_search": is_recent,
            "revenue_cagr": revenue_cagr,
            "revenue_latest": revenue_latest,
            "z_score": z_score,
            "team_size": team_size
        })

    return {"top_startups": results}

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
            inn=startup.inn or "",
            cluster=startup.cluster,
            status=startup.status,
            year_founded=startup.year_founded,
            score_overall=db_score.score_overall if db_score else 0,
            ml_score=qr.ml_score,
            company_description=startup.company_description or "",
            technologies=startup.technologies or "",
            trl=startup.trl or 0,
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
