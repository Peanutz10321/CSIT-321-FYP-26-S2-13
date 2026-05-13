import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { viewUser, getCurrentUser, updateUserStatus } from '../utils/api.js'

const STATUS_LABEL = {
  active: 'Active',
  inactive: 'Inactive',
  suspended: 'Suspended',
}

const STATUS_BADGE = {
  active: 'text-green-400',
  inactive: 'text-yellow-400',
  suspended: 'text-red-400',
}

function AdminViewUser() {
  const navigate = useNavigate()
  const { userId } = useParams()
  const [currentUser, setCurrentUser] = useState(null)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toggling, setToggling] = useState(false)

  useEffect(() => {
    Promise.all([getCurrentUser(), viewUser(userId)])
      .then(([me, target]) => {
        setCurrentUser(me)
        setUser(target)
      })
      .catch((err) => {
        if (err.message?.toLowerCase().includes('not authenticated')) {
          navigate('/login')
          return
        }
        setError(err.message || 'Failed to load user.')
      })
      .finally(() => setLoading(false))
  }, [userId, navigate])

  async function handleToggleSuspend() {
    const newStatus = user.status === 'suspended' ? 'active' : 'suspended'
    setToggling(true)
    try {
      const updated = await updateUserStatus(user.id, newStatus)
      setUser(updated)
    } catch (err) {
      alert(`Failed to update status: ${err.message}`)
    } finally {
      setToggling(false)
    }
  }

  const isAdmin = currentUser?.role === 'system_admin'
  const canToggle = isAdmin && currentUser?.id !== user?.id

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-xl space-y-8">
        <h1 className="text-3xl font-semibold text-slate-100">View User Account</h1>

        {error && (
          <p className="rounded-xl bg-red-900/40 px-4 py-3 text-sm text-red-300">{error}</p>
        )}

        <div className="rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg">
          <h2 className="mb-8 text-center text-xl font-semibold text-slate-100">Account Details</h2>

          {loading ? (
            <p className="text-center text-sm text-slate-400">Loading...</p>
          ) : (
            <div className="space-y-5 text-sm text-slate-300">
              <p>
                <span className="font-semibold text-slate-100">Username: </span>
                {user?.username || '—'}
              </p>
              <p>
                <span className="font-semibold text-slate-100">Email: </span>
                {user?.email || '—'}
              </p>
              <p>
                <span className="font-semibold text-slate-100">Full Name: </span>
                {user?.full_name || '—'}
              </p>
              <p>
                <span className="font-semibold text-slate-100">School ID: </span>
                {user?.institution_id || '—'}
              </p>
              <p>
                <span className="font-semibold text-slate-100">Account Type: </span>
                <span className="capitalize">{user?.role?.replace('_', ' ') || '—'}</span>
              </p>
              <div className="flex items-center gap-3">
                <p>
                  <span className="font-semibold text-slate-100">Status: </span>
                  <span className={`font-medium ${STATUS_BADGE[user?.status] ?? 'text-slate-300'}`}>
                    {STATUS_LABEL[user?.status] ?? user?.status ?? '—'}
                  </span>
                </p>
                {canToggle && (
                  <button
                    onClick={handleToggleSuspend}
                    disabled={toggling}
                    className={`rounded-lg px-3 py-1 text-xs font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60 ${
                      user.status === 'suspended'
                        ? 'bg-green-600 hover:bg-green-700'
                        : 'bg-red-600 hover:bg-red-700'
                    }`}
                  >
                    {toggling
                      ? 'Updating...'
                      : user.status === 'suspended'
                        ? 'Unsuspend'
                        : 'Suspend'}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        <button
          onClick={() => navigate('/manage-users')}
          className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-4 text-base font-semibold text-slate-100 transition hover:bg-slate-700"
        >
          Back
        </button>
      </div>
    </div>
  )
}

export default AdminViewUser
