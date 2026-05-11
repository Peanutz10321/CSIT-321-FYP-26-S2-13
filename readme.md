# Online Voting System

A web-based election management and voting platform built as a Final Year Project. Supports three user roles — **Admin**, **Teacher**, and **Student** — each with their own dashboard and permissions.

## Features

| Role | Capabilities |
|------|-------------|
| Admin | Manage users, view system stats, oversee all elections |
| Teacher | Create and manage elections, view results |
| Student | Vote in active elections, view vote history and receipts |

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy, PostgreSQL, Python
- **Frontend:** React 19, React Router, Tailwind CSS, Vite
- **Auth:** JWT (python-jose), bcrypt
- **Testing:** Pytest
- **CI:** GitHub Actions

## Project Structure

```
backend/
  app/
    models/
    routes/
    schemas/
    security/
    services/
frontend/
  src/
    pages/
    utils/
  package.json
  vite.config.js
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL

## Setup

### Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs available at: http://127.0.0.1:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App available at: http://localhost:5173

## Environment Variables

Create a `.env` file inside the `backend/` directory:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/yourdbname
JWT_SECRET=your_secret_key
```

## Running Tests

```bash
cd backend
pytest
```
