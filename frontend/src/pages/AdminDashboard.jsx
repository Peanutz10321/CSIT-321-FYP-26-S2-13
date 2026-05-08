import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser } from '../utils/api.js'

function AdminDashboard() {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)

  useEffect(() => {
    const token = localStorage.getItem('authToken')
    if (!token) {
      navigate('/login')
      return
    }

    getCurrentUser()
      .then(setUser)
      .catch(() => navigate('/login'))
  }, [navigate])

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-6xl">
        <header className="flex flex-col gap-4 rounded-3xl bg-slate-800 p-8 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-rose-400">Admin Dashboard</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-100">Welcome, {user?.full_name || 'Admin'}</h1>
          </div>
          <button
            onClick={() => navigate('/login')}
            className="inline-flex items-center justify-center rounded-2xl bg-slate-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-600"
          >
            Log Out
          </button>
        </header>

        <main className="mt-10 grid gap-6 xl:grid-cols-3">
          <button
            onClick={() => navigate('/manage-users')}
            className="rounded-3xl border border-slate-700 bg-slate-800 p-6 text-left shadow-sm transition hover:border-rose-500 hover:shadow-md"
          >
            <div className="text-sm font-semibold text-slate-100">Manage Users</div>
            <p className="mt-3 text-sm text-slate-400">View and edit user accounts</p>
          </button>

          <div className="rounded-3xl border border-slate-700 bg-slate-800 p-6 shadow-sm transition hover:border-sky-500 hover:shadow-md">
            <div className="text-sm font-semibold text-slate-100">System Overview</div>
            <div className="mt-5 grid gap-4">
              <div className="rounded-2xl bg-slate-700 p-4 text-sm text-slate-300">
                <p className="font-semibold text-slate-100">Total Students</p>
                <p className="mt-1 text-2xl">150</p>
              </div>
              <div className="rounded-2xl bg-slate-700 p-4 text-sm text-slate-300">
                <p className="font-semibold text-slate-100">Active Elections</p>
                <p className="mt-1 text-2xl">2</p>
              </div>
              <div className="rounded-2xl bg-slate-700 p-4 text-sm text-slate-300">
                <p className="font-semibold text-slate-100">Recent Security Logs</p>
                <p className="mt-1 text-slate-400">No anomalies detected</p>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default AdminDashboard
