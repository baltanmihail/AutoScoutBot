# backend -- FastAPI server + PostgreSQL models
#
# Modules:
#   app        -- FastAPI application with lifespan management
#   database   -- PostgreSQL / SQLite async engine
#   models     -- SQLAlchemy ORM models (startups, scores, financials, users, etc.)
#   schemas    -- Pydantic request/response schemas
#   migrate_csv-- CSV -> PostgreSQL migration
#   embeddings -- Phase 4: sentence-transformer embeddings for pgvector
#   routes/    -- API endpoints (search, score, admin)
#   parsers/   -- Phase 3: external data parsers (EGRUL, Checko, News)

