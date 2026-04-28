from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()

try:
    result = db.execute(text("select now();"))
    print("Database connected:", result.scalar())
finally:
    db.close()