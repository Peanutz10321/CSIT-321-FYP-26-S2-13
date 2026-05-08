import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAdminUsers } from '../utils/api.js'

function ManageUsers() {
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getAdminUsers()
      .then((data) => setUsers(data))
      .catch(() => {
        navigate('/login')
      })
      .finally(() => setLoading(false))
  }, [navigate])

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-6xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-rose-400">User Management</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-100">User Management</h1>
        </div>

        <div className="overflow-hidden rounded-3xl border border-slate-700 bg-slate-800 shadow-sm">
          <div className="grid grid-cols-4 gap-4 border-b border-slate-700 bg-slate-700 px-6 py-4 text-sm font-semibold text-slate-300">
            <span>Name</span>
            <span>Role</span>
            <span>Status</span>
            <span className="text-right">Actions</span>
          </div>
          <div className="divide-y divide-slate-700">
            {users.map((user) => (
              <div key={user.id} className="grid grid-cols-4 gap-4 px-6 py-5 text-sm text-slate-300 items-center">
                <span>{user.name}</span>
                <span>{user.role}</span>
                <span>{user.status}</span>
                <div className="flex justify-end gap-3">
                  <button
                    onClick={() => {
                      localStorage.setItem('backTo', '/manage-users')
                      navigate('/view-account', { state: { from: '/manage-users' } })
                    }}
                    className="rounded-2xl bg-blue-600 px-4 py-2 text-white transition hover:bg-blue-700"
                  >
                    View Details
                  </button>
                  <button
                    type="button"
                    className="rounded-2xl border border-slate-600 bg-slate-800 px-4 py-2 text-slate-100 transition hover:bg-slate-700"
                  >
                    Toggle Status
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <button
            onClick={() => navigate('/admin-dashboard')}
            className="rounded-2xl bg-slate-700 px-6 py-4 text-base font-semibold text-white transition hover:bg-slate-600"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}

export default ManageUsers
