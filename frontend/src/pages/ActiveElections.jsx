import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getActiveElections, getCurrentUser } from '../utils/api.js'

function ActiveElections() {
  const navigate = useNavigate()
  const [activeElections, setActiveElections] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [role, setRole] = useState('')

  useEffect(() => {
    Promise.all([getActiveElections(), getCurrentUser()])
      .then(([elections, user]) => {
        setActiveElections(elections)
        setRole(user.role || '')
      })
      .catch(() => navigate('/login'))
      .finally(() => setLoading(false))
  }, [navigate])

  const handleSearch = (e) => {
    e.preventDefault()
    setSearchQuery(searchInput)
  }

  const filteredElections = activeElections.filter((election) => {
    const q = searchQuery.toLowerCase()
    if (!q) return true
    return election.title.toLowerCase().includes(q)
  })

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <h1 className="text-3xl font-semibold text-slate-100">My Active Elections</h1>

          <form onSubmit={handleSearch} className="mt-6 space-y-3">
            <p className="text-sm font-medium text-slate-300">Search</p>
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search elections..."
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
            <span>Election Title</span>
            <span>Complete Date</span>
            <span className="text-right">View</span>
          </div>
          <div className="divide-y divide-slate-700">
            {loading ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">Loading elections...</div>
            ) : filteredElections.length === 0 ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">No elections found.</div>
            ) : (
              filteredElections.map((election) => (
                <div key={election.id} className="grid grid-cols-3 gap-4 px-6 py-5 text-sm text-slate-300 items-center">
                  <span className="font-medium text-slate-100">{election.title}</span>
                  <span>
                    {election.end_date
                      ? new Date(election.end_date).toLocaleDateString()
                      : '—'}
                  </span>
                  <div className="flex justify-end">
                    <button
                      onClick={() => navigate('/election-detail', { state: { electionId: election.id, from: 'active', role } })}
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

        <button
          onClick={() => navigate(-1)}
          className="rounded-2xl bg-slate-800 px-6 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 border border-slate-600"
        >
          Back to Dashboard
        </button>
      </div>
    </div>
  )
}

export default ActiveElections
