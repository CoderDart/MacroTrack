import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from src.api.routes import router as rest_router
from src.api.graphql_schema import schema as graphql_schema

app = FastAPI(
    title="MacroTrack Multi-Agent Nutrition Tracking API",
    description="Multi-agent nutrition system featuring Gemini 3.5 Flash, mem0 episodic memory, INDb Indian Nutrition Database, Neo4j/NetworkX knowledge graph, and adaptive reminders.",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST endpoints
app.include_router(rest_router)

# Mount Strawberry GraphQL endpoint
graphql_app = GraphQLRouter(graphql_schema)
app.include_router(graphql_app, prefix="/graphql")

@app.get("/")
def root_endpoint():
    return {
        "system": "MacroTrack Multi-Agent Nutrition Swarm",
        "status": "operational",
        "llm_engine": "Gemini 3.5 Flash",
        "memory_layer": "mem0 Episodic Memory",
        "database": "INDb (Indian Food Composition Tables) + Supabase/SQLite",
        "knowledge_graph": "Query-driven Anuvaad INDB graph",
        "endpoints": {
            "rest_docs": "/docs",
            "graphql_explorer": "/graphql",
            "whatsapp_webhook": "/api/webhook/whatsapp"
        }
    }

if __name__ == "__main__":
    import uvicorn
    from src.config import HOST, PORT
    uvicorn.run("src.api.app:app", host=HOST, port=PORT, reload=True)
