import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionDetails, getElectionResults } from '../utils/api.js'

function ElectionResults() {
  const navigate = useNavigate()
  const location = useLocation()
  const electionId = location.state?.electionId

  const [election, setElection] = useState(null)
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!electionId) {
      navigate('/election-history')
      return
    }

    Promise.all([
      getElectionDetails(electionId),
      getElectionResults(electionId).catch(() => null),
    ])
      .then(([electionData, resultsData]) => {
        setElection(electionData)
        setResults(resultsData)
      })
      .catch((err) => setError(err.message || 'Failed to load election data.'))
      .finally(() => setLoading(false))
  }, [electionId, navigate])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-4xl text-slate-300">Loading results...</div>
      </div>
    )
  }

  if (error || !election) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-4xl space-y-4">
          <div className="rounded-3xl border border-rose-800 bg-rose-950 p-6 text-center text-rose-400">
            {error ?? 'Election not found.'}
          </div>
          <button
            onClick={() => navigate('/election-history')}
            className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700"
          >
            Back to History
          </button>
        </div>
      </div>
    )
  }

  const sortedResults = results?.results
    ? [...results.results].sort((a, b) => b.total_votes - a.total_votes)
    : []
  const totalVotes = sortedResults.reduce((sum, r) => sum + r.total_votes, 0)
  const winnerId = sortedResults[0]?.candidate_id

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-400">Election Results</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-100">{election.title}</h1>

          <div className="mt-8 space-y-6 text-sm text-slate-300">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="font-semibold text-slate-100">Start Date &amp; Time</p>
                <p className="mt-1">
                  {election.start_date ? new Date(election.start_date).toLocaleString() : 'TBD'}
                </p>
              </div>
              <div>
                <p className="font-semibold text-slate-100">End Date &amp; Time</p>
                <p className="mt-1">
                  {election.end_date ? new Date(election.end_date).toLocaleString() : 'TBD'}
                </p>
              </div>
            </div>

            <div>
              <p className="font-semibold text-slate-100">Total Votes Cast</p>
              <p className="mt-1">{totalVotes}</p>
            </div>

            <div>
              <p className="font-semibold text-slate-100">Results by Candidate</p>

              {results === null ? (
                <div className="mt-3 rounded-2xl border border-amber-800 bg-amber-950 px-4 py-3 text-amber-300">
                  Results are not yet available. This election may still be in progress.
                </div>
              ) : sortedResults.length === 0 ? (
                <p className="mt-3 text-slate-400">No votes have been cast.</p>
              ) : (
                <ul className="mt-3 space-y-4">
                  {sortedResults.map((r) => {
                    const pct = totalVotes > 0 ? Math.round((r.total_votes / totalVotes) * 100) : 0
                    const isWinner = r.candidate_id === winnerId && totalVotes > 0

                    return (
                      <li key={r.candidate_id} className="rounded-2xl bg-slate-700 p-4">
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <span className="font-medium text-slate-100">{r.candidate_name}</span>
                            {isWinner && (
                              <span className="ml-2 rounded-full bg-emerald-900 px-2 py-0.5 text-xs font-semibold text-emerald-300">
                                Winner
                              </span>
                            )}
                          </div>
                          <span className="shrink-0 text-slate-300">
                            {r.total_votes} vote{r.total_votes !== 1 ? 's' : ''} ({pct}%)
                          </span>
                        </div>
                        <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-600">
                          <div
                            className="h-full rounded-full bg-blue-500 transition-all duration-500"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>

        <div className="rounded-3xl bg-slate-800 p-6 shadow-sm">
          <button
            onClick={() => navigate('/election-history')}
            className="w-full rounded-2xl bg-blue-600 px-5 py-4 text-base font-semibold text-white transition hover:bg-blue-700"
          >
            Back to History
          </button>
        </div>
      </div>
    </div>
  )
}

export default ElectionResults
