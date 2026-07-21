import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionDetails, getEligibleVoters, getVoteHistory } from '../utils/api.js'
import {
  Button,
  Card,
  ErrorState,
  LoadingState,
  PageHeader,
  PageShell,
  StatusBadge,
} from '../components/ui.jsx'

// Module-level so React does not recreate it on each render.
function MetaRow({ label, children }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-slate-800/70 py-3 last:border-0 sm:flex-row sm:justify-between sm:gap-4">
      <span className="text-sm font-medium text-slate-400">{label}</span>
      <span className="text-sm text-slate-100 sm:text-right">{children}</span>
    </div>
  )
}

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
      role === 'organizer' ? getEligibleVoters(electionId).catch(() => null) : Promise.resolve(null),
      role === 'voter' && from === 'active' ? getVoteHistory().catch(() => []) : Promise.resolve([]),
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
      <PageShell width="max-w-2xl">
        <Card padded={false}>
          <LoadingState message="Loading election details..." />
        </Card>
      </PageShell>
    )
  }

  if (error || !election) {
    return (
      <PageShell width="max-w-2xl">
        <ErrorState message={error ?? 'Election not found.'} />
        <Button variant="secondary" onClick={() => navigate(backPath)}>
          Go Back
        </Button>
      </PageShell>
    )
  }

  const isOrganizerActive = role === 'organizer' && from === 'active'
  const isMulti = election.ballot_type === 'multi'

  return (
    <PageShell width="max-w-2xl">
      <PageHeader
        eyebrow="Elections"
        title="Election Details"
        subtitle={election.title}
        actions={
          <Button variant="secondary" onClick={() => navigate(backPath)}>
            Back
          </Button>
        }
      />

      <Card>
        <div>
          <p className="text-sm font-medium text-slate-400">Candidates</p>
          {election.candidates?.length > 0 ? (
            <ul className="mt-2 space-y-1 pl-4 text-sm text-slate-100">
              {election.candidates.map((c) => (
                <li key={c.id} className="list-disc">{c.name}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-sm text-slate-400">No candidates listed.</p>
          )}
        </div>

        <div className="mt-5 text-sm">
          {/* Ballot type is rendered in exactly one place to keep it scannable. */}
          <MetaRow label="Ballot Type">
            <StatusBadge tone={isMulti ? 'blue' : 'slate'}>
              {isMulti ? 'Multiple choice' : 'Single choice'}
            </StatusBadge>
            {isMulti && (
              <span className="ml-2 text-xs text-slate-400">
                up to {election.max_selections ?? 1} selections
              </span>
            )}
          </MetaRow>

          <MetaRow label="Deadline">
            {election.end_date ? new Date(election.end_date).toLocaleDateString() : '—'}
          </MetaRow>

          {isOrganizerActive ? (
            <MetaRow label="Eligible Voters">{eligibleCount !== null ? eligibleCount : '—'}</MetaRow>
          ) : (
            <MetaRow label="Election Organizer">{election.organizer_username ?? '—'}</MetaRow>
          )}
        </div>

        {isOrganizerActive && (
          <div className="mt-6 border-t border-slate-800 pt-6">
            <Button fullWidth size="lg" onClick={() => navigate(`/update-election/${election.id}`)}>
              Update Election
            </Button>
          </div>
        )}

        {role === 'voter' && from === 'active' && (
          <div className="mt-6 border-t border-slate-800 pt-6">
            {existingVoteId ? (
              <div className="flex flex-col items-center gap-3">
                <StatusBadge tone="emerald">Voted</StatusBadge>
                <Button
                  fullWidth
                  size="lg"
                  variant="secondary"
                  onClick={() => navigate(`/vote-receipt/${existingVoteId}`)}
                >
                  View Vote Details
                </Button>
              </div>
            ) : (
              <Button
                fullWidth
                size="lg"
                onClick={() => navigate('/cast-vote', { state: { electionId: election.id } })}
              >
                Cast Vote
              </Button>
            )}
          </div>
        )}
      </Card>
    </PageShell>
  )
}

export default ElectionDetail
