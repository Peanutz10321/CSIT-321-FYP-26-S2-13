import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAdminUsers } from '../utils/api.js'

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
  const [error, setError] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')

    getAdminUsers({ search: searchQuery })
      .then((data) => setUsers(data))
      .catch((err) => {
        if (err.message?.toLowerCase().includes('not authenticated')) {
          navigate('/login')
          return
        }
        setError(err.message || 'Failed to load users.')
      })
      .finally(() => setLoading(false))
  }, [searchQuery, navigate])

  const handleSearch = (e) => {
    e.preventDefault()
    setSearchQuery(searchInput.trim())
  }

  const handleClearSearch = () => {
    setSearchInput('')
    setSearchQuery('')
  }

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-6xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <h1 className="text-3xl font-semibold text-slate-100">User Accounts</h1>
          <p className="mt-2 text-sm text-slate-400">
            Search by username, email, or school ID.
          </p>

          <form onSubmit={handleSearch} className="mt-6 flex flex-col gap-3 sm:flex-row">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search by username, email, or school ID..."
              className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            />
            <button
              type="submit"
              className="rounded-2xl bg-blue-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
            >
              Search
            </button>
            {searchQuery && (
              <button
                type="button"
                onClick={handleClearSearch}
                className="rounded-2xl bg-slate-700 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-600"
              >
                Clear
              </button>
            )}
          </form>

          {searchQuery && (
            <p className="mt-4 text-sm text-slate-400">
              Showing results for: <span className="font-semibold text-slate-200">{searchQuery}</span>
            </p>
          )}

          {error && (
            <p className="mt-4 rounded-xl bg-red-900/40 px-4 py-3 text-sm text-red-300">{error}</p>
          )}
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
            ) : users.length === 0 ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">No users found.</div>
            ) : (
              users.map((user) => (
                <div key={user.id} className="grid grid-cols-3 gap-4 px-6 py-5 text-sm text-slate-300 items-center">
                  <span>{user.username}</span>
                  <span className={`font-medium ${STATUS_BADGE[user.status] ?? 'text-slate-300'}`}>
                    {STATUS_LABEL[user.status] ?? user.status}
                  </span>
                  <div className="flex justify-end">
                    <button
                      onClick={() => navigate(`/admin/users/${user.id}`)}
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
    </div>
  )
}

export default ManageUsers
