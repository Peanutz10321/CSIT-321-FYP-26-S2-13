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

Make sure you have the following installed before getting started:

- [Python 3.10+](https://www.python.org/downloads/)
- [Node.js 18+](https://nodejs.org/)
- [PostgreSQL](https://www.postgresql.org/download/)
- Git

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Peanutz10321/CSIT-321-FYP-26-S2-13
cd CSIT-321-FYP-26-S2-13
```

---

### 2. Set up the database

Create a PostgreSQL database for the project:

```sql
CREATE DATABASE voting_system;
```

---

### 3. Configure environment variables

Create a `.env` file inside the `backend/` directory:

```env
DATABASE_URL=postgresql://your_pg_user:your_pg_password@localhost:5432/voting_system
JWT_SECRET=your_secret_key
```

> Replace `your_pg_user`, `your_pg_password`, and `your_secret_key` with your actual values.

---

### 4. Run the backend and frontend

You will need **two separate terminals** open at the same time — one for the backend and one for the frontend.

#### Terminal 1 — Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the backend server
uvicorn app.main:app --reload
```

The backend will be running at: http://127.0.0.1:8000

Interactive API docs: http://127.0.0.1:8000/docs

#### Terminal 2 — Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the frontend dev server
npm run dev
```

The app will be running at: http://localhost:5173

---

## Running Tests

With the virtual environment activated, run from the `backend/` directory:

```bash
cd backend
pytest
```
