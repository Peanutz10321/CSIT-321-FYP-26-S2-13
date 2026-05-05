import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionHistory } from '../utils/api.js'

function ElectionHistory() {
  const [elections, setElections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const returnPath = location.state?.from || localStorage.getItem('backTo') || '/login'

  useEffect(() => {
    setLoading(true)
    getElectionHistory()
      .then((data) => setElections(data || []))
      .catch((err) => {
        setError(err.message || 'Failed to load election history.')
      })
      .finally(() => setLoading(false))
  }, [navigate])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 px-4 py-10">
        <div className="mx-auto max-w-5xl text-slate-700">Loading election history...</div>
      </div>
    )
  }

  const noData = !elections || elections.length === 0

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-600">Election History</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Election History</h1>

          <div className="mt-6 max-w-md">
            <label htmlFor="search" className="sr-only">Search</label>
            <input
              id="search"
              type="search"
              placeholder="Search elections"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">Start Date</span>
              <input
                type="date"
                className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">End Date</span>
              <input
                type="date"
                className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </label>
          </div>
        </div>

        <div className="space-y-4">
            {error && (
              <div className="rounded-3xl border border-rose-200 bg-rose-50 p-6 text-center text-rose-700">
                {error}
              </div>
            )}
            {noData && searchTerm === '' ? (
              <div className="rounded-3xl border border-slate-200 bg-white p-6 text-center text-slate-500">
                No completed elections found.
              </div>
            ) : (() => {
              const filteredElections = elections.filter((election) =>
                election.title.toLowerCase().includes(searchTerm.toLowerCase())
              )
              return filteredElections.length === 0 ? (
                <div className="rounded-3xl border border-slate-200 bg-white p-6 text-center text-slate-500">
                  No elections match your search.
                </div>
              ) : (
              elections.map((election) => (
                <div key={election.id} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="text-lg font-semibold text-slate-900">{election.title}</p>
                      <p className="mt-1 text-sm text-slate-500">{election.status.replace('_', ' ').toUpperCase()}</p>
                      <p className="mt-2 text-sm text-slate-500">
                        <span className="font-medium text-slate-700">Start Time:</span>{' '}
                        {election.start_date ? new Date(election.start_date).toLocaleString() : 'No start date'}
                      </p>
                      <p className="mt-1 text-sm text-slate-500">
                        <span className="font-medium text-slate-700">End Time:</span>{' '}
                        {election.end_date ? new Date(election.end_date).toLocaleString() : 'No end date'}
                      </p>
                      <p className="mt-2 text-sm text-slate-600">{election.candidates?.length ?? 0} candidates</p>
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
                        className="rounded-2xl border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
                      >
                        View Details
                      </button>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        <div className="pt-6 text-right">
          <button
            onClick={() => navigate(returnPath)}
            className="inline-flex items-center justify-center rounded-2xl border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}

export default ElectionHistory
