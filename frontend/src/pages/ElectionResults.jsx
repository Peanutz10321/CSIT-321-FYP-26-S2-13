import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionDetails, getElectionResults, getEligibleVoters } from '../utils/api.js'

function ElectionResults() {
  const navigate = useNavigate()
  const location = useLocation()
  const electionId = location.state?.electionId
  const role = location.state?.role ?? 'student'

  const [election, setElection] = useState(null)
  const [results, setResults] = useState(null)
  const [eligibleCount, setEligibleCount] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!electionId) {
      navigate('/election-history')
      return
    }

    Promise.all([
      getElectionDetails(electionId),
      getElectionResults(electionId).catch((err) => ({ _error: err.message })),
      role === 'teacher' ? getEligibleVoters(electionId).catch(() => null) : Promise.resolve(null),
    ])
      .then(([electionData, resultsData, votersData]) => {
        setElection(electionData)
        setResults(resultsData)
        if (votersData !== null) setEligibleCount(votersData ? votersData.length : null)
      })
      .catch((err) => setError(err.message || 'Failed to load election data.'))
      .finally(() => setLoading(false))
  }, [electionId, navigate, role])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-2xl text-slate-300">Loading results...</div>
      </div>
    )
  }

  if (error || !election) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-2xl space-y-4">
          <div className="rounded-sm border-2 border-rose-800 bg-rose-950 p-6 text-center text-rose-400">
            {error ?? 'Election not found.'}
          </div>
          <button
            onClick={() => navigate(-1)}
            className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-4 text-base font-semibold text-slate-100 transition hover:bg-slate-700"
          >
            Back
          </button>
        </div>
      </div>
    )
  }

  const resultsError = results?._error ?? null
  const resultsList = results?.results ?? []
  const totalVotes = results?.total_votes ?? 0
  const tiedCandidates = results?.tied_candidates ?? []
  const winner = results?.winner ?? '—'
  const candidateNames = election.candidates?.map((c) => c.name).join(', ') || '—'

  const Row = ({ label, children }) => (
    <div className="border-b border-slate-700 py-4">
      <span className="font-semibold text-slate-100">{label}: </span>
      <span className="text-slate-300">{children}</span>
    </div>
  )

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-2xl space-y-6">

        <div className="rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg">
          <h2 className="mb-6 text-center text-xl font-semibold text-slate-100">Election Results</h2>

          <div className="text-sm">
            <Row label="Title">{election.title}</Row>
            <Row label="Candidates">{candidateNames}</Row>
            <Row label="Commence Date And Time">
              {election.start_date ? new Date(election.start_date).toLocaleString() : '—'}
            </Row>
            <Row label="End Date And Time">
              {election.end_date ? new Date(election.end_date).toLocaleString() : '—'}
            </Row>
            <Row label="Total Votes Cast">
              {resultsError ? '—' : totalVotes}
            </Row>
            {role === 'teacher' ? (
              <Row label="Eligible Student Voters">
                {eligibleCount !== null ? eligibleCount : '—'}
              </Row>
            ) : (
              <Row label="Election Organizer">
                {election.teacher_username ?? '—'}
              </Row>
            )}
            <Row label="Number Of Votes Per Candidate">
              {resultsError ? (
                <span className="text-amber-400">{resultsError}</span>
              ) : resultsList.length === 0 ? (
                'No votes cast'
              ) : (
                resultsList.map((r) => `${r.candidate_name}: ${r.total_votes}`).join(', ')
              )}
            </Row>
            <div className="pt-4">
              <span className="font-semibold text-slate-100">Winner: </span>
              <span className="text-slate-300">
                {resultsError || totalVotes === 0
                  ? '—'
                  : tiedCandidates.length > 0
                    ? `— (Tie: ${tiedCandidates.join(', ')})`
                    : winner}
              </span>
            </div>
          </div>
        </div>

        <button
          onClick={() => navigate(-1)}
          className="w-full rounded-2xl border border-slate-600 bg-slate-800 px-6 py-4 text-base font-semibold text-slate-100 transition hover:bg-slate-700"
        >
          Back
        </button>

      </div>
    </div>
  )
}

export default ElectionResults
