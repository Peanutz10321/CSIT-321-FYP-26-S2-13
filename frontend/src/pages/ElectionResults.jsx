import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionDetails, getElectionResults, getEligibleVoters } from '../utils/api.js'
import { Button, Card, LoadingState, PageHeader, PageShell, StatusBadge } from '../components/ui.jsx'

// Module-level so React does not recreate these on each render.
function MetaRow({ label, children }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-slate-800/70 py-3 last:border-0 sm:flex-row sm:justify-between sm:gap-4">
      <span className="text-sm font-medium text-slate-400">{label}</span>
      <span className="text-sm text-slate-100 sm:text-right">{children}</span>
    </div>
  )
}

function StatTile({ label, children }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <div className="mt-2 text-slate-100">{children}</div>
    </div>
  )
}

function ElectionResults() {
  const navigate = useNavigate()
  const location = useLocation()
  const electionId = location.state?.electionId
  const role = location.state?.role ?? 'voter'

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
      role === 'organizer' ? getEligibleVoters(electionId).catch(() => null) : Promise.resolve(null),
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
      <PageShell width="max-w-3xl">
        <Card padded={false}>
          <LoadingState message="Loading results..." />
        </Card>
      </PageShell>
    )
  }

  if (error || !election) {
    return (
      <PageShell width="max-w-3xl">
        <Card className="border-rose-500/30 bg-rose-500/10 text-center text-sm text-rose-300">
          {error ?? 'Election not found.'}
        </Card>
        <Button variant="secondary" onClick={() => navigate(-1)}>
          Back
        </Button>
      </PageShell>
    )
  }

  const resultsError = results?._error ?? null
  const resultsList = results?.results ?? []
  // Turnout comes straight from the backend (ballots cast). It must never be
  // recomputed by summing candidate totals: a multi-select ballot counts toward
  // several candidates but is one ballot, and an abstention counts toward none.
  const totalVotes = results?.total_votes ?? 0
  const tiedCandidates = results?.tied_candidates ?? []
  const winner = results?.winner ?? '—'
  const candidateNames = election.candidates?.map((c) => c.name).join(', ') || '—'
  const isMulti = election.ballot_type === 'multi'
  const perCandidateLabel = isMulti ? 'Selections Per Candidate' : 'Votes Per Candidate'

  const winnerDisplay =
    resultsError || totalVotes === 0
      ? '—'
      : tiedCandidates.length > 0
        ? `Tie: ${tiedCandidates.join(', ')}`
        : winner

  // Stable text summary (also read by assistive tech); the bars are the visual
  // representation of the same data.
  const perCandidateText =
    resultsList.length === 0
      ? 'No votes cast'
      : resultsList.map((r) => `${r.candidate_name}: ${r.total_votes}`).join(', ')
  const maxCount = Math.max(1, ...resultsList.map((r) => r.total_votes))

  return (
    <PageShell width="max-w-3xl">
      <PageHeader
        eyebrow="Results"
        title="Election Results"
        subtitle={election.title}
        actions={
          <Button variant="secondary" onClick={() => navigate(-1)}>
            Back
          </Button>
        }
      />

      {/* Summary highlights */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatTile label="Total Ballots Cast:">
          <span className="text-3xl font-semibold tracking-tight">
            {resultsError ? '—' : totalVotes}
          </span>
          <span className="ml-2 text-xs text-slate-400">ballots / turnout</span>
        </StatTile>
        <StatTile label="Winner:">
          {winnerDisplay === '—' ? (
            <span className="text-lg">—</span>
          ) : (
            <StatusBadge tone={tiedCandidates.length > 0 ? 'amber' : 'emerald'}>
              {winnerDisplay}
            </StatusBadge>
          )}
        </StatTile>
      </div>

      {/* Per-candidate breakdown */}
      <Card>
        <h2 className="text-sm font-semibold text-slate-100">{perCandidateLabel}:</h2>
        <span className="sr-only">{perCandidateText}</span>
        {resultsError ? (
          <p className="mt-3 text-sm text-amber-400">{resultsError}</p>
        ) : resultsList.length === 0 ? (
          <p className="mt-3 text-sm text-slate-400">No votes cast</p>
        ) : (
          <ul className="mt-4 space-y-3" aria-hidden="true">
            {resultsList.map((r) => (
              <li key={r.candidate_id}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="text-slate-200">{r.candidate_name}</span>
                  <span className="font-semibold text-slate-100">{r.total_votes}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-blue-500"
                    style={{ width: `${(r.total_votes / maxCount) * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Metadata */}
      <Card>
        <div className="text-sm">
          <MetaRow label="Title">{election.title}</MetaRow>
          <MetaRow label="Candidates">{candidateNames}</MetaRow>
          <MetaRow label="Ballot Type">
            {isMulti
              ? `Multiple choice — up to ${election.max_selections ?? 1} selections`
              : 'Single choice'}
          </MetaRow>
          <MetaRow label="Commence Date And Time">
            {election.start_date ? new Date(election.start_date).toLocaleString() : '—'}
          </MetaRow>
          <MetaRow label="End Date And Time">
            {election.end_date ? new Date(election.end_date).toLocaleString() : '—'}
          </MetaRow>
          {role === 'organizer' ? (
            <MetaRow label="Eligible Voters">{eligibleCount !== null ? eligibleCount : '—'}</MetaRow>
          ) : (
            <MetaRow label="Election Organizer">{election.organizer_username ?? '—'}</MetaRow>
          )}
        </div>
      </Card>
    </PageShell>
  )
}

export default ElectionResults
