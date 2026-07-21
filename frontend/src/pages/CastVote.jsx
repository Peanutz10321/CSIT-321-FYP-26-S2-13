import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getCurrentUser, getElectionDetails, getVoteHistory, submitVote } from '../utils/api'
import { Button, Card, LoadingState, LockIcon, PageShell } from '../components/ui.jsx'

function CastVote() {
  const navigate = useNavigate()
  const location = useLocation()
  const [currentUser, setCurrentUser] = useState(null)
  const [election, setElection] = useState(null)
  // selectedIds + abstain are kept in memory only — the selection is never written
  // to localStorage, sessionStorage, the URL, or logs.
  const [selectedIds, setSelectedIds] = useState([])
  const [abstain, setAbstain] = useState(false)
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

  const chooseSingle = (candidateId) => {
    setSelectedIds([candidateId])
    setAbstain(false)
  }

  const toggleMulti = (candidateId, maxSelections) => {
    setAbstain(false)
    setSelectedIds((prev) => {
      if (prev.includes(candidateId)) {
        return prev.filter((id) => id !== candidateId)
      }
      // Never silently drop an existing selection: at the limit the extra
      // selection is simply not applied (the checkbox is also disabled).
      if (prev.length >= maxSelections) {
        return prev
      }
      return [...prev, candidateId]
    })
  }

  const chooseAbstain = () => {
    setAbstain(true)
    setSelectedIds([])
  }

  const handleVote = async () => {
    const chosenNames = election.candidates
      .filter((c) => selectedIds.includes(c.id))
      .map((c) => c.name)

    const confirmMessage = abstain
      ? 'You are abstaining: no candidate will receive your vote. Submit this ballot?'
      : chosenNames.length === 1
        ? `Confirm your vote for ${chosenNames[0]}?`
        : `Confirm your selections: ${chosenNames.join(', ')}?`

    if (!window.confirm(confirmMessage)) return

    setSubmitting(true)
    try {
      const vote = await submitVote({
        election_id: electionId,
        candidate_ids: abstain ? [] : selectedIds,
      })
      // The immediate response is handed to the receipt via in-memory router
      // state only; it is never persisted, so a later visit cannot recover it.
      navigate(`/vote-receipt/${vote.id}`, { state: { submittedVote: vote } })
    } catch (error) {
      alert(`Failed to submit vote: ${error.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading || userLoading) {
    return (
      <PageShell width="max-w-xl">
        <Card padded={false}>
          <LoadingState message="Loading ballot..." />
        </Card>
      </PageShell>
    )
  }

  if (!election || !currentUser) return null

  const isVoter = currentUser.role === 'voter'
  const isMulti = election.ballot_type === 'multi'
  const maxSelections = election.max_selections ?? 1
  const atLimit = isMulti && selectedIds.length >= maxSelections
  const hasChoice = abstain || selectedIds.length > 0

  const optionClass = (checked, disabled) =>
    `flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 transition ${
      checked
        ? 'border-blue-500 bg-blue-500/10'
        : 'border-slate-800 bg-slate-950/40 hover:border-slate-600'
    } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`

  return (
    <PageShell width="max-w-xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Cast Your Vote</h1>
        <p className="mt-1 text-sm text-slate-400">
          {election.title} · voting as <span className="text-slate-300">{currentUser.external_id}</span>
        </p>
      </div>

      <Card>
        <fieldset>
          <legend className="text-sm font-semibold text-slate-100">
            {isMulti
              ? `Select up to ${maxSelections} candidate${maxSelections === 1 ? '' : 's'}, or abstain`
              : 'Select one candidate, or abstain'}
          </legend>

          {isMulti && (
            <p
              aria-live="polite"
              className="mt-2 inline-flex rounded-full bg-slate-800/70 px-2.5 py-0.5 text-xs font-medium text-slate-200"
            >
              {selectedIds.length} of {maxSelections} selections
            </p>
          )}

          <div className="mt-4 space-y-2.5">
            {election.candidates.map((candidate) => {
              const checked = !abstain && selectedIds.includes(candidate.id)
              const disabled = !isVoter || (isMulti && !checked && atLimit)
              return (
                <label key={candidate.id} className={optionClass(checked, disabled)}>
                  {isMulti ? (
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleMulti(candidate.id, maxSelections)}
                      disabled={disabled}
                      className="h-5 w-5 cursor-pointer rounded border-slate-500 accent-blue-500 disabled:cursor-not-allowed"
                    />
                  ) : (
                    <input
                      type="radio"
                      name="ballot-choice"
                      checked={checked}
                      onChange={() => chooseSingle(candidate.id)}
                      disabled={disabled}
                      className="h-5 w-5 cursor-pointer border-slate-500 accent-blue-500 disabled:cursor-not-allowed"
                    />
                  )}
                  <span className="text-sm font-medium text-slate-100">{candidate.name}</span>
                </label>
              )
            })}

            <label className={`${optionClass(abstain, !isVoter)} mt-2 border-dashed`}>
              {isMulti ? (
                <input
                  type="checkbox"
                  checked={abstain}
                  onChange={(e) => (e.target.checked ? chooseAbstain() : setAbstain(false))}
                  disabled={!isVoter}
                  className="h-5 w-5 cursor-pointer rounded border-slate-500 accent-blue-500 disabled:cursor-not-allowed"
                />
              ) : (
                <input
                  type="radio"
                  name="ballot-choice"
                  checked={abstain}
                  onChange={chooseAbstain}
                  disabled={!isVoter}
                  className="h-5 w-5 cursor-pointer border-slate-500 accent-blue-500 disabled:cursor-not-allowed"
                />
              )}
              <span className="text-sm italic text-slate-300">
                Abstain (no candidate receives your vote)
              </span>
            </label>
          </div>
        </fieldset>

        <p className="mt-5 flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-4 py-3 text-xs text-slate-400">
          <LockIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
          Your ballot is encrypted when you submit. You will be asked to confirm before it is cast.
        </p>

        {!isVoter && (
          <p className="mt-4 text-xs text-slate-400">Voting is restricted to voters.</p>
        )}

        {isVoter && (
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <Button
              size="lg"
              onClick={handleVote}
              disabled={submitting || !hasChoice || !!existingVoteId}
            >
              {existingVoteId ? 'Voted' : submitting ? 'Submitting...' : 'Submit Vote'}
            </Button>
            {existingVoteId && (
              <Button
                size="lg"
                variant="secondary"
                onClick={() => navigate(`/vote-receipt/${existingVoteId}`)}
              >
                View Vote Details
              </Button>
            )}
          </div>
        )}
      </Card>
    </PageShell>
  )
}

export default CastVote
