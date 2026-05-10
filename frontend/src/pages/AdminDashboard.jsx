import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser, getAdminStats } from '../utils/api.js'

function StatCard({ label, value, loading }) {
  return (
    <div className="rounded-2xl bg-slate-700 p-4 text-sm text-slate-300">
      <p className="font-semibold text-slate-100">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-100">
        {loading ? <span className="text-base font-normal text-slate-400">Loading…</span> : value}
      </p>
    </div>
  )
}

function AdminDashboard() {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)
  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('authToken')
    if (!token) {
      navigate('/login')
      return
    }

    getCurrentUser()
      .then(setUser)
      .catch(() => navigate('/login'))

    getAdminStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false))
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

          <div className="rounded-3xl border border-slate-700 bg-slate-800 p-6 shadow-sm xl:col-span-2">
            <div className="text-sm font-semibold text-slate-100">System Overview</div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <StatCard label="Total Students" value={stats?.total_students ?? '—'} loading={statsLoading} />
              <StatCard label="Total Teachers" value={stats?.total_teachers ?? '—'} loading={statsLoading} />
              <StatCard label="Total Admins" value={stats?.total_admins ?? '—'} loading={statsLoading} />
              <StatCard label="Active Elections" value={stats?.active_elections ?? '—'} loading={statsLoading} />
              <StatCard label="Votes Cast" value={stats?.total_votes_cast ?? '—'} loading={statsLoading} />
              <StatCard
                label="Participation Rate"
                value={stats ? `${stats.participation_rate}%` : '—'}
                loading={statsLoading}
              />
            </div>
            {!statsLoading && stats === null && (
              <p className="mt-4 text-xs text-red-400">Could not load stats. Check your connection.</p>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

export default AdminDashboard
