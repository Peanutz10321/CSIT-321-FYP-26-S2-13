import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser, logoutUser } from '../utils/api.js'

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
            <h1 className="mt-2 text-3xl font-semibold text-slate-100">Welcome, {user?.username || 'Admin'}</h1>
          </div>
          <button
            onClick={() => { logoutUser(); navigate('/login') }}
            className="inline-flex items-center justify-center rounded-2xl bg-slate-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-600"
          >
            Log Out
          </button>
        </header>

        <main className="mt-10 flex justify-center">
          <button
            onClick={() => navigate('/manage-users')}
            className="w-full max-w-sm rounded-3xl border border-slate-700 bg-slate-800 p-8 text-center shadow-sm transition hover:border-rose-500 hover:shadow-md"
          >
            <div className="text-lg font-semibold text-slate-100">Manage Users</div>
            <p className="mt-3 text-sm text-slate-400">View and edit user accounts</p>
          </button>
        </main>
      </div>
    </div>
  )
}

export default AdminDashboard
