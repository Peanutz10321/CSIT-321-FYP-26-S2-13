# app/main.py

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.routes.auth_routes import router as auth_router
from app.routes.user_routes import router as user_router

app = FastAPI(title="Homomorphic E-Voting API")

app.include_router(auth_router)
app.include_router(user_router)

@app.get("/")
def root():
    return {"message": "E-Voting backend is running"}


@app.get("/health/db")
def database_health_check(db: Session = Depends(get_db)):
    result = db.execute(text("select now();"))
    return {
        "database": "connected",
        "time": str(result.scalar()),
    }