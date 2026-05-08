import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getVoteHistory } from '../utils/api'

function VoteHistory() {
  const navigate = useNavigate()
  const [voteHistory, setVoteHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getVoteHistory()
      .then(setVoteHistory)
      .catch((fetchError) => {
        setError(fetchError.message)
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-400">My Vote History</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-100">Vote History</h1>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">Start Date</span>
              <input
                type="date"
                className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">End Date</span>
              <input
                type="date"
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
          ) : (
            voteHistory.map((item) => (
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
