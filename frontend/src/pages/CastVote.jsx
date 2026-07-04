import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getCurrentUser, getElectionDetails, getVoteHistory, submitVote } from '../utils/api'

function CastVote() {
  const navigate = useNavigate()
  const location = useLocation()
  const [currentUser, setCurrentUser] = useState(null)
  const [election, setElection] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [loading, setLoading] = useState(true)
  const [userLoading, setUserLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [existingVoteId, setExistingVoteId] = useState(null)
  const electionId = location.state?.electionId || new URLSearchParams(location.search).get('id')

  useEffect(() => {
    if (!electionId) {
      alert('No election selected.')
      navigate('/active-elections')
      return
    }

    getElectionDetails(electionId)
      .then((data) => {
        setElection(data)
        return getVoteHistory()
      })
      .then((history) => {
        const existing = history.find((v) => v.election_id === electionId)
        if (existing) setExistingVoteId(existing.id)
      })
      .catch((error) => {
        alert(`Unable to load election: ${error.message}`)
        navigate('/active-elections')
      })
      .finally(() => setLoading(false))
  }, [electionId, navigate])

  useEffect(() => {
    getCurrentUser()
      .then(setCurrentUser)
      .catch(() => navigate('/login'))
      .finally(() => setUserLoading(false))
  }, [navigate])

  const handleVote = async () => {
    setSubmitting(true)
    try {
      const vote = await submitVote({ election_id: electionId, candidate_id: selectedCandidateId })
      navigate(`/vote-receipt/${vote.id}`)
    } catch (error) {
      alert(`Failed to submit vote: ${error.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading || userLoading) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-xl text-slate-300">Loading...</div>
      </div>
    )
  }

  if (!election || !currentUser) return null

  const isVoter = currentUser.role === 'voter'

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-xl rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg">
        <h1 className="mb-8 text-2xl font-semibold text-slate-100">Cast Your Vote</h1>

        <div className="space-y-6">
          <p className="text-sm text-slate-300">
            <span className="font-semibold text-slate-100">External ID: </span>
            {currentUser.external_id}
          </p>

          <div className="space-y-3">
            {election.candidates.map((candidate) => (
              <label
                key={candidate.id}
                className="flex cursor-pointer items-center justify-between border-b border-slate-600 pb-3"
              >
                <span className="text-sm text-slate-100">{candidate.name}</span>
                <input
                  type="checkbox"
                  checked={selectedCandidateId === candidate.id}
                  onChange={() => setSelectedCandidateId(candidate.id)}
                  disabled={!isVoter}
                  className="h-4 w-4 cursor-pointer rounded border-slate-500 accent-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                />
              </label>
            ))}
          </div>

          {!isVoter && (
            <p className="text-xs text-slate-400">Voting is restricted to voters.</p>
          )}

          {isVoter && (
            <div className="flex justify-center gap-4 pt-2">
              <button
                type="button"
                onClick={handleVote}
                disabled={submitting || !selectedCandidateId || !!existingVoteId}
                className="border-2 border-slate-500 bg-slate-900/70 px-8 py-3 text-base font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {existingVoteId ? 'Voted' : submitting ? 'Submitting...' : 'Submit Vote'}
              </button>
              {existingVoteId && (
                <button
                  type="button"
                  onClick={() => navigate(`/vote-receipt/${existingVoteId}`)}
                  className="border-2 border-blue-500 bg-slate-900/70 px-8 py-3 text-base font-medium text-blue-300 transition hover:border-blue-400 hover:text-blue-200"
                >
                  View Vote Details
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default CastVote
