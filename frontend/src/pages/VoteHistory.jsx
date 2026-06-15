import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getVoteHistory } from '../utils/api'

function VoteHistory() {
  const navigate = useNavigate()
  const [voteHistory, setVoteHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [searchInput, setSearchInput] = useState('')
  const [startDateInput, setStartDateInput] = useState('')
  const [endDateInput, setEndDateInput] = useState('')

  const [searchQuery, setSearchQuery] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  useEffect(() => {
    setLoading(true)
    setError(null)
    getVoteHistory({ search: searchQuery, start_date: startDate, end_date: endDate })
      .then(setVoteHistory)
      .catch((err) => setError(err.message))
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
          <h1 className="text-3xl font-semibold text-slate-100">My Vote History</h1>

          <form onSubmit={handleSearch} className="mt-6">
            <div className="grid grid-cols-3 gap-6">
              <div className="space-y-3">
                <p className="text-sm font-medium text-slate-300">Search</p>
                <input
                  type="text"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Search votes..."
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
            <span>Voted Date</span>
            <span className="text-right">View</span>
          </div>
          <div className="divide-y divide-slate-700">
            {loading ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">Loading vote history...</div>
            ) : error ? (
              <div className="px-6 py-8 text-center text-sm text-rose-400">{error}</div>
            ) : voteHistory.length === 0 ? (
              <div className="px-6 py-8 text-center text-sm text-slate-400">No vote history found.</div>
            ) : (
              voteHistory.map((item) => (
                <div key={item.id} className="grid grid-cols-3 gap-4 px-6 py-5 text-sm text-slate-300 items-center">
                  <span className="font-medium text-slate-100">{item.election_title}</span>
                  <span>
                    {item.submitted_at ? new Date(item.submitted_at).toLocaleDateString() : '—'}
                  </span>
                  <div className="flex justify-end">
                    <button
                      onClick={() => navigate(`/vote-receipt/${item.id}`)}
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
          onClick={() => navigate('/student-dashboard')}
          className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-4 text-base font-semibold text-slate-100 transition hover:bg-slate-700"
        >
          Back to Dashboard
        </button>
      </div>
    </div>
  )
}

export default VoteHistory
