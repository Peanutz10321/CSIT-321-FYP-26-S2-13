import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getCurrentUser } from '../utils/api.js'

function ViewAccount() {
  const navigate = useNavigate()
  const location = useLocation()
  const returnPath = location.state?.from || localStorage.getItem('backTo') || '/login'
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

  const roleLabel = user?.role === 'teacher' ? 'Teacher' : 'Student'

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-xl space-y-8">
        <h1 className="text-3xl font-semibold text-slate-100">View {roleLabel} Account</h1>

        <div className="rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg">
          <h2 className="mb-8 text-center text-xl font-semibold text-slate-100">Account Details</h2>

          <div className="space-y-5 text-sm text-slate-300">
            <p>
              <span className="font-semibold text-slate-100">Username: </span>
              {user?.username || 'Loading...'}
            </p>
            <p>
              <span className="font-semibold text-slate-100">{roleLabel} Email: </span>
              {user?.email || 'Loading...'}
            </p>
            <p>
              <span className="font-semibold text-slate-100">Password: </span>
              ••••••••
            </p>
            <p>
              <span className="font-semibold text-slate-100">Full Name: </span>
              {user?.full_name || 'Loading...'}
            </p>
            <p>
              <span className="font-semibold text-slate-100">School ID: </span>
              {user?.institution_id || 'Loading...'}
            </p>
          </div>
        </div>

        <div className="grid gap-4">
          <button
            onClick={() => navigate('/update-account')}
            className="rounded-2xl bg-blue-600 px-6 py-4 text-base font-semibold text-white transition hover:bg-blue-700"
          >
            Update Information
          </button>
          <button
            onClick={() => navigate(returnPath)}
            className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-4 text-base font-semibold text-slate-100 transition hover:bg-slate-700"
          >
            Back
          </button>
        </div>
      </div>
    </div>
  )
}

export default ViewAccount
