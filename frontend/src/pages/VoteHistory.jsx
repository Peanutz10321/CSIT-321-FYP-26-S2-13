import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getVoteHistory } from '../utils/api'

function VoteHistory() {
  const navigate = useNavigate()
  const [voteHistory, setVoteHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  useEffect(() => {
    getVoteHistory()
      .then(setVoteHistory)
      .catch((fetchError) => {
        setError(fetchError.message)
      })
      .finally(() => setLoading(false))
  }, [])

  const filteredHistory = voteHistory.filter((item) => {
    const q = searchQuery.toLowerCase()
    const matchesText =
      item.election_title?.toLowerCase().includes(q) ||
      item.receipt_code?.toLowerCase().includes(q)

    if (!matchesText) return false

    const votedAt = new Date(item.submitted_at)
    if (startDate && votedAt < new Date(startDate + 'T00:00:00')) return false
    if (endDate && votedAt > new Date(endDate + 'T23:59:59')) return false

    return true
  })

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-400">My Vote History</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-100">Vote History</h1>

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
              placeholder="Search by election name or receipt code..."
              className="w-full rounded-2xl border border-slate-600 bg-slate-700 py-3 pl-11 pr-4 text-slate-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            />
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">Start Date</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">End Date</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              />
            </label>
          </div>
        </div>

        <div className="space-y-4">
          {loading ? (
            <div className="rounded-3xl border border-slate-700 bg-slate-800 p-6 shadow-sm text-slate-300">
              Loading vote history...
            </div>
          ) : error ? (
            <div className="rounded-3xl border border-red-800 bg-red-950 p-6 shadow-sm text-red-400">
              Error loading vote history: {error}
            </div>
          ) : voteHistory.length === 0 ? (
            <div className="rounded-3xl border border-slate-700 bg-slate-800 p-6 shadow-sm text-slate-300">
              No voting history found.
            </div>
          ) : filteredHistory.length === 0 ? (
            <div className="rounded-3xl border border-slate-700 bg-slate-800 p-6 shadow-sm text-slate-400 text-center">
              No results match your current filters.
            </div>
          ) : (
            filteredHistory.map((item) => (
              <div key={item.id} className="rounded-3xl border border-slate-700 bg-slate-800 p-6 shadow-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-lg font-semibold text-slate-100">{item.election_title}</p>
                    <p className="mt-1 text-sm text-slate-400">
                      Voted on {new Date(item.submitted_at).toLocaleString()}
                    </p>
                    <p className="mt-1 text-sm text-slate-400">Receipt: {item.receipt_code}</p>
                  </div>
                  <button
                    onClick={() => navigate(`/vote-receipt/${item.id}`)}
                    className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
                  >
                    View Receipt
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="pt-6 text-right">
          <button
            onClick={() => navigate('/student-dashboard')}
            className="inline-flex items-center justify-center rounded-2xl border border-slate-600 bg-slate-800 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}

export default VoteHistory
