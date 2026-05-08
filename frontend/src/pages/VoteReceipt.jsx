import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getVoteDetails, getElectionDetails } from '../utils/api'

function VoteReceipt() {
  const navigate = useNavigate()
  const { voteId } = useParams()
  const [vote, setVote] = useState(null)
  const [election, setElection] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!voteId) {
      setError('No vote ID provided')
      setLoading(false)
      return
    }

    getVoteDetails(voteId)
      .then((voteData) => {
        setVote(voteData)
        return getElectionDetails(voteData.election_id)
      })
      .then(setElection)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [voteId])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <p className="text-slate-300">Loading receipt...</p>
      </div>
    )
  }

  if (error || !vote) {
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

  // MVP encrypted_vote format: "encrypted_placeholder:{candidate_id}"
  const candidateId = vote.encrypted_vote.split(':')[1]
  const votedCandidate = election?.candidates?.find((c) => c.id === candidateId) ?? null

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-400">Vote Receipt</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-100">{election?.title ?? '—'}</h1>
          <div className="mt-6 space-y-5 text-sm text-slate-300">
            <div>
              <p className="font-semibold text-slate-100">Receipt Code</p>
              <p>{vote.receipt_code}</p>
            </div>
            {election?.candidates?.length > 0 && (
              <div>
                <p className="font-semibold text-slate-100">List of Candidates</p>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {election.candidates.map((c) => (
                    <li key={c.id}>{c.name}</li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <p className="font-semibold text-slate-100">Election Commence Date and Time</p>
              <p>{election ? new Date(election.start_date).toLocaleString() : '—'}</p>
            </div>
            <div>
              <p className="font-semibold text-slate-100">Election End Date and Time</p>
              <p>{election ? new Date(election.end_date).toLocaleString() : '—'}</p>
            </div>
            <div>
              <p className="font-semibold text-slate-100">Date and Time Vote Casted</p>
              <p>{new Date(vote.submitted_at).toLocaleString()}</p>
            </div>
            {votedCandidate && (
              <div>
                <p className="font-semibold text-slate-100">Voted Candidate</p>
                <p>{votedCandidate.name}</p>
              </div>
            )}
            <div>
              <p className="font-semibold text-slate-100">Vote Hash</p>
              <p className="break-all font-mono text-xs text-slate-400">{vote.vote_hash}</p>
            </div>
          </div>
        </div>

        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <button
            onClick={() => navigate('/vote-history')}
            className="w-full rounded-2xl bg-blue-600 px-5 py-4 text-base font-semibold text-white transition hover:bg-blue-700"
          >
            Back to History
          </button>
        </div>
      </div>
    </div>
  )
}

export default VoteReceipt
