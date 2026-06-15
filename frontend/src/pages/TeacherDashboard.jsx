import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser, logout } from '../utils/api.js'

function TeacherDashboard() {
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
            <h1 className="mt-2 text-3xl font-semibold text-slate-100">Welcome, {user?.username || 'Teacher'}</h1>
          </div>
          <button
            onClick={() => { logout(); navigate('/login') }}
            className="inline-flex items-center justify-center rounded-2xl bg-slate-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-600"
          >
            Log Out
          </button>
        </header>

        <main className="mt-10 grid grid-cols-2 gap-6">
          {[
            { label: 'View User Account', action: () => { localStorage.setItem('backTo', '/teacher-dashboard'); navigate('/view-account', { state: { from: '/teacher-dashboard' } }) } },
            { label: 'New Election', action: () => navigate('/create-election') },
            { label: 'My Active Elections', action: () => navigate('/active-elections') },
            { label: 'My Election History', action: () => { localStorage.setItem('backTo', '/teacher-dashboard'); navigate('/election-history', { state: { from: '/teacher-dashboard' } }) } },
          ].map(({ label, action }) => (
            <button
              key={label}
              onClick={action}
              className="group rounded-3xl border border-slate-700 bg-slate-800 p-6 text-left shadow-sm transition hover:border-amber-500 hover:shadow-md"
            >
              <div className="text-sm font-semibold text-slate-100">{label}</div>
              <p className="mt-3 text-sm text-slate-400">Click to view details</p>
            </button>
          ))}
        </main>
      </div>
    </div>
  )
}

export default TeacherDashboard
