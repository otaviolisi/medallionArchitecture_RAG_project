import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status

from bussola.api.auth import verify_api_key
from bussola.api.schema import AskRequest, AskResponse
from bussola.api import sql_agent

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bussola.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    required = ["DATABASE_URL", "OPENAI_API_KEY", "API_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {missing}")
    log.info("Bússola Pública API started.")
    yield


app = FastAPI(
    title="Bússola Pública API",
    description="Natural language queries over Brazilian legislative data.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(verify_api_key)])
async def ask(body: AskRequest):
    if not body.question.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question cannot be empty.",
        )
    try:
        result = sql_agent.run(
            question=body.question,
            database_url=os.environ["DATABASE_URL"],
            openai_api_key=os.environ["OPENAI_API_KEY"],
        )
    except ValueError as exc:
        # Safety check failure — blocked SQL
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsafe query blocked: {exc}",
        )
    except Exception as exc:
        log.exception("Unexpected error processing question.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    return result
