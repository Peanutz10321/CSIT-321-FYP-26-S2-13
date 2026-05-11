import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAdminUsers, getCurrentUser, updateUserStatus } from '../utils/api.js'

const FIELD = ({ label, value }) => (
  <p className="text-sm text-slate-300">
    <span className="font-semibold text-slate-100">{label}: </span>
    {value || '—'}
  </p>
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
  const [currentUser, setCurrentUser] = useState(null)
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedUser, setSelectedUser] = useState(null)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [toggling, setToggling] = useState(false)

  useEffect(() => {
    getCurrentUser()
      .then(setCurrentUser)
      .catch(() => navigate('/login'))

    getAdminUsers()
      .then((data) => setUsers(data))
      .catch(() => navigate('/login'))
      .finally(() => setLoading(false))
  }, [navigate])

  const isAdmin = currentUser?.role === 'system_admin'

  async function handleToggleSuspend() {
    if (!selectedUser) return
    const newStatus = selectedUser.status === 'suspended' ? 'active' : 'suspended'
    setToggling(true)
    try {
      await updateUserStatus(selectedUser.id, newStatus)
      const updated = { ...selectedUser, status: newStatus }
      setSelectedUser(updated)
      setUsers((prev) => prev.map((u) => (u.id === selectedUser.id ? updated : u)))
    } catch (err) {
      alert(`Failed to update status: ${err.message}`)
    } finally {
      setToggling(false)
    }
  }

  const handleSearch = (e) => {
    e.preventDefault()
    setSearchQuery(searchInput)
  }

  const filteredUsers = users.filter((user) => {
    const q = searchQuery.toLowerCase()
    if (!q) return true
    return (
      user.username?.toLowerCase().includes(q) ||
      user.email?.toLowerCase().includes(q)
    )
  })

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-6xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <h1 className="text-3xl font-semibold text-slate-100">User Accounts</h1>

          <form onSubmit={handleSearch} className="mt-6 space-y-3">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search by username or email..."
              className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            />
            <button
              type="submit"
              className="rounded-2xl bg-blue-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
            >
              Search
            </button>
          </form>
        </div>

        <div className="overflow-hidden rounded-3xl border border-slate-700 bg-slate-800 shadow-sm">
          <div className="grid grid-cols-3 gap-4 border-b border-slate-700 bg-slate-700 px-6 py-4 text-sm font-semibold text-slate-300">
            <span>Username</span>
            <span>Status</span>
            <span className="text-right">View</span>
          </div>
          <div className="divide-y divide-slate-700">
            {loading ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">Loading users...</div>
            ) : filteredUsers.length === 0 ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">No users found.</div>
            ) : (
              filteredUsers.map((user) => (
                <div key={user.id} className="grid grid-cols-3 gap-4 px-6 py-5 text-sm text-slate-300 items-center">
                  <span>{user.username}</span>
                  <span className={`font-medium ${STATUS_BADGE[user.status] ?? 'text-slate-300'}`}>
                    {STATUS_LABEL[user.status] ?? user.status}
                  </span>
                  <div className="flex justify-end">
                    <button
                      onClick={() => setSelectedUser(user)}
                      className="rounded-xl bg-blue-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-blue-700"
                    >
                      View
                    </button>
                  </div>
                </div>
              ))
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
              <h2 className="text-xl font-semibold text-slate-100">Account Details</h2>
              <button
                onClick={() => setSelectedUser(null)}
                className="ml-4 rounded-xl p-2 text-slate-400 transition hover:bg-slate-700 hover:text-slate-100"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="space-y-3 text">
              <FIELD label="Username" value={selectedUser.username} />
              <FIELD label="Email" value={selectedUser.email} />
              <FIELD label="School ID" value={selectedUser.institution_id} />
              <FIELD label="Account Type" value={selectedUser.role?.replace('_', ' ')} />
              <div className="flex items-center  gap-3">
                <p className="text-sm text-slate-300">
                  <span className="font-semibold text-slate-100">Status: </span>
                  <span className={`font-medium ${STATUS_BADGE[selectedUser.status] ?? 'text-slate-300'}`}>
                    {STATUS_LABEL[selectedUser.status] ?? selectedUser.status}
                  </span>
                </p>
                {isAdmin && currentUser.id !== selectedUser.id && (
                  <button
                    onClick={handleToggleSuspend}
                    disabled={toggling}
                    className={`rounded-lg px-3 py-1 text-xs font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60 ${
                      selectedUser.status === 'suspended'
                        ? 'bg-green-600 hover:bg-green-700'
                        : 'bg-red-600 hover:bg-red-700'
                    }`}
                  >
                    {toggling
                      ? 'Updating...'
                      : selectedUser.status === 'suspended'
                      ? 'Unsuspend'
                      : 'Suspend'}
                  </button>
                )}
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
