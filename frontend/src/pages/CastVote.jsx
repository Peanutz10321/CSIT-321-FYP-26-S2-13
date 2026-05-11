import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getCurrentUser, getElectionDetails, submitVote } from '../utils/api'

function CastVote() {
  const navigate = useNavigate()
  const location = useLocation()
  const [currentUser, setCurrentUser] = useState(null)
  const [election, setElection] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [loading, setLoading] = useState(true)
  const [userLoading, setUserLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const electionId = location.state?.electionId || new URLSearchParams(location.search).get('id')

  useEffect(() => {
    if (!electionId) {
      alert('No election selected.')
      navigate('/active-elections')
      return
    }

    getElectionDetails(electionId)
      .then((data) => setElection(data))
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
    if (!selectedCandidateId) {
      alert('Please select a candidate before submitting your vote.')
      return
    }

    setSubmitting(true)
    try {
      await submitVote({ election_id: electionId, candidate_id: selectedCandidateId })
      alert('Vote submitted successfully!')
      navigate('/vote-history')
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

  const isStudent = currentUser.role === 'student'

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-xl rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg">
        <h1 className="mb-8 text-2xl font-semibold text-slate-100">Cast Your Vote</h1>

        <div className="space-y-6">
          <p className="text-sm text-slate-300">
            <span className="font-semibold text-slate-100">School ID: </span>
            {currentUser.institution_id}
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
                  disabled={!isStudent}
                  className="h-4 w-4 cursor-pointer rounded border-slate-500 accent-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                />
              </label>
            ))}
          </div>

          {!isStudent && (
            <p className="text-xs text-slate-400">Voting is restricted to students.</p>
          )}

          {isStudent && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={handleVote}
                disabled={submitting || !selectedCandidateId}
                className="border-2 border-slate-500 bg-slate-900/70 px-8 py-3 text-base font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? 'Submitting...' : 'Submit Vote'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default CastVote
