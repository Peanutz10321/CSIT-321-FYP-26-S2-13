import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionDetails, getEligibleVoters, getVoteHistory } from '../utils/api.js'

function ElectionDetail() {
  const navigate = useNavigate()
  const location = useLocation()
  const electionId = location.state?.electionId
  const from = location.state?.from
  const role = location.state?.role

  const [election, setElection] = useState(null)
  const [eligibleCount, setEligibleCount] = useState(null)
  const [existingVoteId, setExistingVoteId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!electionId) {
      navigate(from === 'active' ? '/active-elections' : '/election-history')
      return
    }

    Promise.all([
      getElectionDetails(electionId),
      role === 'teacher' ? getEligibleVoters(electionId).catch(() => null) : Promise.resolve(null),
      role === 'student' && from === 'active' ? getVoteHistory().catch(() => []) : Promise.resolve([]),
    ])
      .then(([electionData, votersData, voteHistory]) => {
        setElection(electionData)
        if (votersData !== null) setEligibleCount(votersData ? votersData.length : null)
        const existing = voteHistory.find((v) => v.election_id === electionId)
        if (existing) setExistingVoteId(existing.id)
      })
      .catch((err) => setError(err.message || 'Failed to load election details.'))
      .finally(() => setLoading(false))
  }, [electionId, navigate, from, role])

  const backPath = from === 'active' ? '/active-elections' : '/election-history'

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-xl text-slate-300">Loading election details...</div>
      </div>
    )
  }

  if (error || !election) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-xl space-y-4">
          <p className="text-center text-rose-400">{error ?? 'Election not found.'}</p>
          <button
            onClick={() => navigate(backPath)}
            className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700"
          >
            Go Back
          </button>
        </div>
      </div>
    )
  }

  const isTeacherActive = role === 'teacher' && from === 'active'

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-xl space-y-8">
        <div className="rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg">
          <h2 className="mb-8 text-center text-xl font-semibold text-slate-100">Election Details</h2>

          <div className="space-y-6 text-sm text-slate-300">
            <p>
              <span className="font-semibold text-slate-100">Title: </span>
              {election.title}
            </p>

            <div>
              <p className="font-semibold text-slate-100">Candidates:</p>
              {election.candidates?.length > 0 ? (
                <ul className="mt-2 space-y-1 pl-4">
                  {election.candidates.map((c) => (
                    <li key={c.id} className="list-disc">{c.name}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-slate-400">No candidates listed.</p>
              )}
            </div>

            <p>
              <span className="font-semibold text-slate-100">Deadline: </span>
              {election.end_date ? new Date(election.end_date).toLocaleDateString() : '—'}
            </p>

            {isTeacherActive ? (
              <p>
                <span className="font-semibold text-slate-100">Eligible Student Voters: </span>
                {eligibleCount !== null ? eligibleCount : '—'}
              </p>
            ) : (
              <p>
                <span className="font-semibold text-slate-100">Election Organizer: </span>
                {election.teacher_username ?? '—'}
              </p>
            )}
          </div>

          {isTeacherActive && (
            <div className="mt-10 flex justify-center">
              <button
                onClick={() => navigate(`/update-election/${election.id}`)}
                className="border-2 border-slate-500 bg-slate-900/70 px-8 py-3 text-lg font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300"
              >
                Update Election
              </button>
            </div>
          )}

          {role === 'student' && from === 'active' && (
            <div className="mt-10 flex justify-center gap-4">
              <button
                onClick={() => !existingVoteId && navigate('/cast-vote', { state: { electionId: election.id } })}
                disabled={!!existingVoteId}
                className="border-2 border-slate-500 bg-slate-900/70 px-8 py-3 text-lg font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {existingVoteId ? 'Voted' : 'Cast Vote'}
              </button>
              {existingVoteId && (
                <button
                  onClick={() => navigate(`/vote-receipt/${existingVoteId}`)}
                  className="border-2 border-blue-500 bg-slate-900/70 px-8 py-3 text-lg font-medium text-blue-300 transition hover:border-blue-400 hover:text-blue-200"
                >
                  View Vote Details
                </button>
              )}
            </div>
          )}
        </div>

        <button
          onClick={() => navigate(backPath)}
          className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-4 text-base font-semibold text-slate-100 transition hover:bg-slate-700"
        >
          Back
        </button>
      </div>
    </div>
  )
}

export default ElectionDetail
