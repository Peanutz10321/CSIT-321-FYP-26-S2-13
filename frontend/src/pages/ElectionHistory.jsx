import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionHistory } from '../utils/api.js'

const STATUS_STYLES = {
  active:    'bg-emerald-900 text-emerald-300',
  completed: 'bg-blue-900 text-blue-300',
  cancelled: 'bg-red-900 text-red-300',
  archived:  'bg-slate-700 text-slate-400',
}

function ElectionHistory() {
  const [elections, setElections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const returnPath = location.state?.from || localStorage.getItem('backTo') || '/login'

  useEffect(() => {
    setLoading(true)
    setError(null)
    getElectionHistory()
      .then((data) => setElections(data || []))
      .catch((err) => setError(err.message || 'Failed to load election history.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-5xl text-slate-300">Loading election history...</div>
      </div>
    )
  }

  const filteredElections = elections.filter((election) => {
    const matchesText = election.title.toLowerCase().includes(searchTerm.toLowerCase())
    if (!matchesText) return false

    const electionStart = new Date(election.start_date)
    if (startDate && electionStart < new Date(startDate + 'T00:00:00')) return false
    if (endDate && electionStart > new Date(endDate + 'T23:59:59')) return false

    return true
  })

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-400">Election History</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-100">Election History</h1>

          <div className="mt-6 max-w-md">
            <label htmlFor="search" className="sr-only">Search</label>
            <input
              id="search"
              type="search"
              placeholder="Search elections"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            />
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
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
          {error ? (
            <div className="rounded-3xl border border-rose-800 bg-rose-950 p-6 text-center text-rose-400">
              {error}
            </div>
          ) : elections.length === 0 ? (
            <div className="rounded-3xl border border-slate-700 bg-slate-800 p-6 text-center text-slate-400">
              No elections found.
            </div>
          ) : filteredElections.length === 0 ? (
            <div className="rounded-3xl border border-slate-700 bg-slate-800 p-6 text-center text-slate-400">
              No elections match your current filters.
            </div>
          ) : (
            filteredElections.map((election) => (
              <div key={election.id} className="rounded-3xl border border-slate-700 bg-slate-800 p-6 shadow-sm">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-lg font-semibold text-slate-100">{election.title}</p>
                    <span
                      className={`mt-1 inline-block rounded-full px-3 py-0.5 text-xs font-semibold uppercase tracking-wide ${STATUS_STYLES[election.status] ?? 'bg-slate-700 text-slate-400'}`}
                    >
                      {election.status.replace('_', ' ')}
                    </span>
                    <p className="mt-2 text-sm text-slate-400">
                      <span className="font-medium text-slate-300">Start:</span>{' '}
                      {election.start_date ? new Date(election.start_date).toLocaleString() : 'TBD'}
                    </p>
                    <p className="mt-1 text-sm text-slate-400">
                      <span className="font-medium text-slate-300">End:</span>{' '}
                      {election.end_date ? new Date(election.end_date).toLocaleString() : 'TBD'}
                    </p>
                    <p className="mt-2 text-sm text-slate-400">
                      {election.candidates?.length ?? 0} candidate{election.candidates?.length !== 1 ? 's' : ''}
                    </p>
                  </div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <button
                      onClick={() => navigate('/election-results', { state: { electionId: election.id } })}
                      className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
                    >
                      View Results
                    </button>
                    <button
                      onClick={() => navigate('/election-detail', { state: { electionId: election.id } })}
                      className="rounded-2xl border border-slate-600 bg-slate-800 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700"
                    >
                      View Details
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="pt-6 text-right">
          <button
            onClick={() => navigate(returnPath)}
            className="inline-flex items-center justify-center rounded-2xl border border-slate-600 bg-slate-800 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}

export default ElectionHistory
