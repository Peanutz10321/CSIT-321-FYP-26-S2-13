import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { getVoteDetails, getElectionDetails, getCurrentUser } from '../utils/api'
import { Button, Card, LoadingState, PageShell } from '../components/ui.jsx'

function ReceiptField({ label, children }) {
  return (
    <p className="flex flex-col gap-0.5 border-b border-slate-800/70 py-3 last:border-0 sm:flex-row sm:justify-between sm:gap-4">
      <span className="text-sm font-medium text-slate-400">{label}</span>
      <span className="text-sm text-slate-100 sm:text-right">{children}</span>
    </p>
  )
}

function VoteReceipt() {
  const navigate = useNavigate()
  const location = useLocation()
  const { voteId } = useParams()

  // The plaintext selection only exists in the immediate submission response,
  // passed here through in-memory router state. It is never persisted, so a
  // receipt opened from history or after a refresh cannot (and must not try to)
  // reconstruct the choice. Only trust state that matches this route's vote id.
  const submittedVote = location.state?.submittedVote
  const isImmediate = Boolean(submittedVote && submittedVote.id === voteId)
  const [vote, setVote] = useState(null)
  const [election, setElection] = useState(null)
  const [currentUser, setCurrentUser] = useState(null)
  // A missing vote id is known before any fetch, so it is derived at
  // initialization instead of being set inside the effect.
  const [loading, setLoading] = useState(() => Boolean(voteId))
  const [error, setError] = useState(() => (voteId ? null : 'No vote ID provided'))

  useEffect(() => {
    if (!voteId) return

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
      <PageShell width="max-w-xl">
        <Card padded={false}>
          <LoadingState message="Loading receipt..." />
        </Card>
      </PageShell>
    )
  }

  if (error || !vote || !election) {
    return (
      <PageShell width="max-w-xl">
        <Card className="border-rose-500/30 bg-rose-500/10 text-center text-sm text-rose-300">
          {error ?? 'Receipt not found.'}
        </Card>
        <Button variant="secondary" onClick={() => navigate('/vote-history')}>
          Back to History
        </Button>
      </PageShell>
    )
  }

  const candidateNames = election.candidates?.map((c) => c.name).join(', ') || '—'

  let selectionDisplay = null
  if (isImmediate) {
    if (submittedVote.abstained) {
      selectionDisplay = 'Abstained'
    } else if (submittedVote.candidate_names?.length > 0) {
      selectionDisplay = submittedVote.candidate_names.join(', ')
    } else if (submittedVote.candidate_name) {
      selectionDisplay = submittedVote.candidate_name
    } else {
      selectionDisplay = '—'
    }
  }

  return (
    <PageShell width="max-w-xl">
      <div className="text-center">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300">
          <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
          Vote recorded
        </span>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-100">Vote Details</h1>
        <p className="mt-1 text-sm text-slate-400">Keep this receipt for your reference.</p>
      </div>

      <Card>
        {/* Receipt code — the official confirmation the voter keeps. */}
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-center">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Receipt Code</p>
          <p className="mt-1 font-mono text-lg font-semibold tracking-wider text-blue-300">
            {vote.receipt_code ?? '—'}
          </p>
        </div>

        {/* Your selection — shown in full only immediately after submission. */}
        <p className="mt-5 flex flex-col gap-1 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
          <span className="text-sm font-semibold text-slate-100">Your Selection:</span>
          {isImmediate ? (
            <span className="text-sm text-slate-100">{selectionDisplay}</span>
          ) : (
            <span className="text-sm text-slate-400">
              Your selection is not retained in plaintext and is only shown immediately after
              submission.
            </span>
          )}
        </p>

        <div className="mt-5 text-sm">
          <ReceiptField label="External ID">{currentUser?.external_id ?? '—'}</ReceiptField>
          <ReceiptField label="Election Title">{election.title}</ReceiptField>
          <ReceiptField label="Election Candidates">{candidateNames}</ReceiptField>
          <ReceiptField label="Election Commence">
            {election.start_date ? new Date(election.start_date).toLocaleString() : '—'}
          </ReceiptField>
          <ReceiptField label="Election End">
            {election.end_date ? new Date(election.end_date).toLocaleString() : '—'}
          </ReceiptField>
          <ReceiptField label="Vote Cast At">
            {vote.submitted_at ? new Date(vote.submitted_at).toLocaleString() : '—'}
          </ReceiptField>
          <ReceiptField label="Election Organizer">{election.organizer_username ?? '—'}</ReceiptField>
        </div>

        <p className="mt-5 rounded-lg border border-slate-800 bg-slate-950/40 px-4 py-3 text-xs leading-relaxed text-slate-400">
          Ballots are stored as encrypted values and counted in aggregate. Individual ballots are
          not normally decrypted during tallying.
        </p>
      </Card>

      <Button variant="secondary" onClick={() => navigate('/vote-history')}>
        Back to History
      </Button>
    </PageShell>
  )
}

export default VoteReceipt
