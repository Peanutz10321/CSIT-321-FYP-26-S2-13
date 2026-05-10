import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAdminUsers, updateUserStatus } from '../utils/api.js'

const FIELD = ({ label, value }) => (
  <div>
    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
    <p className="mt-1 text-sm text-slate-100">{value || '—'}</p>
  </div>
)

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

function ManageUsers() {
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [togglingId, setTogglingId] = useState(null)
  const [selectedUser, setSelectedUser] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    getAdminUsers()
      .then((data) => setUsers(data))
      .catch(() => navigate('/login'))
      .finally(() => setLoading(false))
  }, [navigate])

  async function handleSetStatus(userId, newStatus) {
    setTogglingId(userId)
    try {
      await updateUserStatus(userId, newStatus)
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, status: newStatus } : u))
      )
    } catch (err) {
      alert(`Failed to update status: ${err.message}`)
    } finally {
      setTogglingId(null)
    }
  }

  const filteredUsers = users.filter((user) => {
    const q = searchQuery.toLowerCase()
    const displayName = user.full_name || user.username || ''
    const matchesSearch =
      displayName.toLowerCase().includes(q) ||
      user.email?.toLowerCase().includes(q)

    const matchesRole = roleFilter === 'all' || user.role?.toLowerCase() === roleFilter
    const matchesStatus = statusFilter === 'all' || user.status?.toLowerCase() === statusFilter

    return matchesSearch && matchesRole && matchesStatus
  })

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-6xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-rose-400">User Management</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-100">User Management</h1>

          <div className="mt-6 relative">
            <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-slate-400">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.3-4.3" />
              </svg>
            </span>
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name or email..."
              className="w-full rounded-2xl border border-slate-600 bg-slate-700 py-3 pl-11 pr-4 text-slate-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            />
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">Role</span>
              <select
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
                className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              >
                <option value="all">All Roles</option>
                <option value="system_admin">Admin</option>
                <option value="teacher">Teacher</option>
                <option value="student">Student</option>
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">Status</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              >
                <option value="all">All Status</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="suspended">Suspended</option>
              </select>
            </label>
          </div>
        </div>

        <div className="overflow-hidden rounded-3xl border border-slate-700 bg-slate-800 shadow-sm">
          <div className="grid grid-cols-4 gap-4 border-b border-slate-700 bg-slate-700 px-6 py-4 text-sm font-semibold text-slate-300">
            <span>Name</span>
            <span>Role</span>
            <span>Status</span>
            <span className="text-right">Actions</span>
          </div>
          <div className="divide-y divide-slate-700">
            {loading ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">Loading users...</div>
            ) : filteredUsers.length === 0 ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">No users match your filters.</div>
            ) : (
              filteredUsers.map((user) => {
                const isToggling = togglingId === user.id
                return (
                  <div key={user.id} className="grid grid-cols-4 gap-4 px-6 py-5 text-sm text-slate-300 items-center">
                    <span>{user.full_name || user.username}</span>
                    <span className="capitalize">{user.role?.replace('_', ' ')}</span>
                    <span className={`font-medium ${STATUS_BADGE[user.status] ?? 'text-slate-300'}`}>
                      {STATUS_LABEL[user.status] ?? user.status}
                    </span>
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setSelectedUser(user)}
                        className="rounded-xl bg-blue-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-blue-700"
                      >
                        View
                      </button>
                      <select
                        value=""
                        onChange={(e) => {
                          if (e.target.value) handleSetStatus(user.id, e.target.value)
                        }}
                        disabled={isToggling}
                        className="rounded-xl border border-slate-600 bg-slate-700 px-2 py-2 text-xs text-slate-100 focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <option value="" disabled>
                          {isToggling ? 'Updating…' : 'Set status…'}
                        </option>
                        <option value="active" disabled={user.status === 'active'}>Set Active</option>
                        <option value="inactive" disabled={user.status === 'inactive'}>Set Inactive</option>
                        <option value="suspended" disabled={user.status === 'suspended'}>Suspend</option>
                      </select>
                    </div>
                  </div>
                )
              })
            )}
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

      {selectedUser && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm"
          onClick={() => setSelectedUser(null)}
        >
          <div
            className="w-full max-w-md rounded-3xl bg-slate-800 p-8 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-6 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-rose-400">User Details</p>
                <h2 className="mt-1 text-xl font-semibold text-slate-100">
                  {selectedUser.full_name || selectedUser.username}
                </h2>
              </div>
              <button
                onClick={() => setSelectedUser(null)}
                className="ml-4 rounded-xl p-2 text-slate-400 transition hover:bg-slate-700 hover:text-slate-100"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="space-y-4">
              <FIELD label="Username" value={selectedUser.username} />
              <FIELD label="Full Name" value={selectedUser.full_name} />
              <FIELD label="School ID" value={selectedUser.institution_id} />
              <FIELD label="Email" value={selectedUser.email} />
              <FIELD label="Role" value={selectedUser.role?.replace('_', ' ')} />
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Status</p>
                <p className={`mt-1 text-sm font-medium ${STATUS_BADGE[selectedUser.status] ?? 'text-slate-300'}`}>
                  {STATUS_LABEL[selectedUser.status] ?? selectedUser.status}
                </p>
              </div>
            </div>

            <button
              onClick={() => setSelectedUser(null)}
              className="mt-8 w-full rounded-2xl border border-slate-600 bg-slate-700 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-600"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default ManageUsers
