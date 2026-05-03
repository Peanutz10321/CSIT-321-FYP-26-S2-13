import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser } from '../utils/api.js'

function StudentDashboard() {
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
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-6xl">
        <header className="flex flex-col gap-4 rounded-3xl bg-white p-8 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-sky-600">Student Dashboard</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-900">Welcome, {user?.full_name || 'Student'}</h1>
          </div>
          <button
            onClick={() => navigate('/login')}
            className="inline-flex items-center justify-center rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
          >
            Log Out
          </button>
        </header>

        <main className="mt-10 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          {[
            'View User Account',
            'My Active Elections',
            'My Vote History',
            'My Election History',
          ].map((label) => (
            <button
              key={label}
              onClick={() => {
                if (label === 'View User Account') {
                  localStorage.setItem('backTo', '/student-dashboard')
                  return navigate('/view-account', { state: { from: '/student-dashboard' } })
                }
                if (label === 'My Active Elections') return navigate('/active-elections')
                if (label === 'My Vote History') return navigate('/vote-history')
                if (label === 'My Election History') {
                  localStorage.setItem('backTo', '/student-dashboard')
                  return navigate('/election-history', { state: { from: '/student-dashboard' } })
                }
              }}
              className="group rounded-3xl border border-slate-200 bg-white p-6 text-left shadow-sm transition hover:border-blue-300 hover:shadow-md"
            >
              <div className="text-sm font-semibold text-slate-900">{label}</div>
              <p className="mt-3 text-sm text-slate-500">Click to view details</p>
            </button>
          ))}
        </main>
      </div>
    </div>
  )
}

export default StudentDashboard
