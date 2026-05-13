import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getVoteDetails, getElectionDetails, getCurrentUser } from '../utils/api'

function VoteReceipt() {
  const navigate = useNavigate()
  const { voteId } = useParams()
  const [vote, setVote] = useState(null)
  const [election, setElection] = useState(null)
  const [currentUser, setCurrentUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!voteId) {
      setError('No vote ID provided')
      setLoading(false)
      return
    }

    Promise.all([
      getCurrentUser(),
      getVoteDetails(voteId).then((voteData) => {
        setVote(voteData)
        return getElectionDetails(voteData.election_id).then((electionData) => {
          setElection(electionData)
        })
      }),
    ])
      .then(([user]) => setCurrentUser(user))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [voteId])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <p className="text-slate-300">Loading...</p>
      </div>
    )
  }

  if (error || !vote || !election) {
    return (
      <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center gap-4">
        <p className="text-red-400">{error ?? 'Receipt not found.'}</p>
        <button
          onClick={() => navigate('/vote-history')}
          className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Back to History
        </button>
      </div>
    )
  }

  const candidateNames = election.candidates?.map((c) => c.name).join(', ') || '—'

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-xl space-y-8">
        <div className="rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg">
          <h2 className="mb-8 text-center text-xl font-semibold text-slate-100">Vote Details</h2>

          <div className="space-y-5 text-sm text-slate-300">
            <p>
              <span className="font-semibold text-slate-100">School ID: </span>
              {currentUser?.institution_id ?? '—'}
            </p>
            <p>
              <span className="font-semibold text-slate-100">Election Title: </span>
              {election.title}
            </p>
            <p>
              <span className="font-semibold text-slate-100">Candidates: </span>
              {candidateNames}
            </p>
            <p>
              <span className="font-semibold text-slate-100">Election Commence Date And Time: </span>
              {election.start_date ? new Date(election.start_date).toLocaleString() : '—'}
            </p>
            <p>
              <span className="font-semibold text-slate-100">Election End Date And Time: </span>
              {election.end_date ? new Date(election.end_date).toLocaleString() : '—'}
            </p>
            <p>
              <span className="font-semibold text-slate-100">Date And Time Vote Casted: </span>
              {vote.submitted_at ? new Date(vote.submitted_at).toLocaleString() : '—'}
            </p>
            <p>
              <span className="font-semibold text-slate-100">Election Organizer: </span>
              {election.teacher_username ?? '—'}
            </p>
            <p>
              <span className="font-semibold text-slate-100">Candidate Voted: </span>
              {vote.candidate_name ?? '—'}
            </p>
          </div>
        </div>

        <button
          onClick={() => navigate('/vote-history')}
          className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-4 text-base font-semibold text-slate-100 transition hover:bg-slate-700"
        >
          Back to History
        </button>
      </div>
    </div>
  )
}

export default VoteReceipt
