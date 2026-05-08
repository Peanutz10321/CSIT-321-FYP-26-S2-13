import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionDetails } from '../utils/api.js'

const STATUS_STYLES = {
  active:    'bg-emerald-900 text-emerald-300',
  completed: 'bg-blue-900 text-blue-300',
  cancelled: 'bg-red-900 text-red-300',
  archived:  'bg-slate-700 text-slate-400',
  draft:     'bg-amber-900 text-amber-300',
}

function ElectionDetail() {
  const navigate = useNavigate()
  const location = useLocation()
  const electionId = location.state?.electionId

  const [election, setElection] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!electionId) {
      navigate('/election-history')
      return
    }
    getElectionDetails(electionId)
      .then(setElection)
      .catch((err) => setError(err.message || 'Failed to load election details.'))
      .finally(() => setLoading(false))
  }, [electionId, navigate])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-4xl text-slate-300">Loading election details...</div>
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

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-400">Election Details</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-100">{election.title}</h1>
          <span
            className={`mt-3 inline-block rounded-full px-3 py-0.5 text-xs font-semibold uppercase tracking-wide ${STATUS_STYLES[election.status] ?? 'bg-slate-700 text-slate-400'}`}
          >
            {election.status.replace('_', ' ')}
          </span>

          <div className="mt-8 space-y-5 text-sm text-slate-300">
            {election.description && (
              <div>
                <p className="font-semibold text-slate-100">Description</p>
                <p className="mt-1">{election.description}</p>
              </div>
            )}
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
            <div>
              <p className="font-semibold text-slate-100">
                Candidates ({election.candidates?.length ?? 0})
              </p>
              {election.candidates?.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {election.candidates.map((candidate) => (
                    <li
                      key={candidate.id}
                      className="rounded-2xl bg-slate-700 px-4 py-3 font-medium text-slate-100"
                    >
                      {candidate.name}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-slate-400">No candidates registered.</p>
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

export default ElectionDetail
