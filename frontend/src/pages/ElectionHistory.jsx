import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionHistory } from '../utils/api.js'

function ElectionHistory() {
  const [elections, setElections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [searchInput, setSearchInput] = useState('')
  const [startDateInput, setStartDateInput] = useState('')
  const [endDateInput, setEndDateInput] = useState('')

  const [searchQuery, setSearchQuery] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const navigate = useNavigate()
  const location = useLocation()
  const returnPath = location.state?.from || localStorage.getItem('backTo') || '/login'
  const role = returnPath.includes('organizer') ? 'organizer' : 'voter'

  useEffect(() => {
    setLoading(true)
    setError(null)
    getElectionHistory({ search: searchQuery, start_date: startDate, end_date: endDate })
      .then((data) => setElections(data || []))
      .catch((err) => setError(err.message || 'Failed to load election history.'))
      .finally(() => setLoading(false))
  }, [searchQuery, startDate, endDate])

  const handleSearch = (e) => {
    e.preventDefault()
    setSearchQuery(searchInput)
    setStartDate(startDateInput)
    setEndDate(endDateInput)
  }

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <h1 className="text-3xl font-semibold text-slate-100">My Election History</h1>

          <form onSubmit={handleSearch} className="mt-6">
            <div className="grid grid-cols-3 gap-6">
              <div className="space-y-3">
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
              </div>

              <div className="space-y-3">
                <p className="text-sm font-medium text-slate-300">Start Date</p>
                <input
                  type="date"
                  value={startDateInput}
                  onChange={(e) => setStartDateInput(e.target.value)}
                  className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
                />
              </div>

              <div className="space-y-3">
                <p className="text-sm font-medium text-slate-300">End Date</p>
                <input
                  type="date"
                  value={endDateInput}
                  onChange={(e) => setEndDateInput(e.target.value)}
                  className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
                />
              </div>
            </div>
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
              <div className="px-6 py-8 text-center text-sm text-slate-400">Loading election history...</div>
            ) : error ? (
              <div className="px-6 py-8 text-center text-sm text-rose-400">{error}</div>
            ) : elections.length === 0 ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">No elections found.</div>
            ) : (
              elections.map((election) => (
                <div key={election.id} className="grid grid-cols-3 gap-4 px-6 py-5 text-sm text-slate-300 items-center">
                  <span className="font-medium text-slate-100">{election.title}</span>
                  <span>
                    {election.end_date ? new Date(election.end_date).toLocaleDateString() : '—'}
                  </span>
                  <div className="flex justify-end">
                    <button
                      onClick={() =>
                        navigate('/election-results', { state: { electionId: election.id, role } })
                      }
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
          onClick={() => navigate(returnPath)}
          className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-4 text-base font-semibold text-slate-100 transition hover:bg-slate-700"
        >
          Back to Dashboard
        </button>
      </div>
    </div>
  )
}

export default ElectionHistory
