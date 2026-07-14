import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getCurrentUser, getElectionDetails, getVoteHistory, submitVote } from '../utils/api'

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
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-xl text-slate-300">Loading...</div>
      </div>
    )
  }

  if (!election || !currentUser) return null

  const isVoter = currentUser.role === 'voter'
  const isMulti = election.ballot_type === 'multi'
  const maxSelections = election.max_selections ?? 1
  const atLimit = isMulti && selectedIds.length >= maxSelections
  const hasChoice = abstain || selectedIds.length > 0

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-xl rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg">
        <h1 className="mb-8 text-2xl font-semibold text-slate-100">Cast Your Vote</h1>

        <div className="space-y-6">
          <p className="text-sm text-slate-300">
            <span className="font-semibold text-slate-100">External ID: </span>
            {currentUser.external_id}
          </p>

          <fieldset>
            <legend className="mb-3 text-sm font-semibold text-slate-100">
              {isMulti
                ? `Select up to ${maxSelections} candidate${maxSelections === 1 ? '' : 's'}, or abstain`
                : 'Select one candidate, or abstain'}
            </legend>

            {isMulti && (
              <p aria-live="polite" className="mb-3 text-xs text-slate-300">
                {selectedIds.length} of {maxSelections} selections
              </p>
            )}

            <div className="space-y-3">
              {election.candidates.map((candidate) => {
                const checked = !abstain && selectedIds.includes(candidate.id)
                return (
                  <label
                    key={candidate.id}
                    className="flex cursor-pointer items-center justify-between border-b border-slate-600 py-2"
                  >
                    <span className="text-sm text-slate-100">{candidate.name}</span>
                    {isMulti ? (
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleMulti(candidate.id, maxSelections)}
                        disabled={!isVoter || (!checked && atLimit)}
                        className="h-5 w-5 cursor-pointer rounded border-slate-500 accent-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                      />
                    ) : (
                      <input
                        type="radio"
                        name="ballot-choice"
                        checked={checked}
                        onChange={() => chooseSingle(candidate.id)}
                        disabled={!isVoter}
                        className="h-5 w-5 cursor-pointer border-slate-500 accent-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                      />
                    )}
                  </label>
                )
              })}

              <label className="flex cursor-pointer items-center justify-between border-b border-slate-600 py-2">
                <span className="text-sm italic text-slate-300">Abstain (no candidate receives your vote)</span>
                {isMulti ? (
                  <input
                    type="checkbox"
                    checked={abstain}
                    onChange={(e) => (e.target.checked ? chooseAbstain() : setAbstain(false))}
                    disabled={!isVoter}
                    className="h-5 w-5 cursor-pointer rounded border-slate-500 accent-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                  />
                ) : (
                  <input
                    type="radio"
                    name="ballot-choice"
                    checked={abstain}
                    onChange={chooseAbstain}
                    disabled={!isVoter}
                    className="h-5 w-5 cursor-pointer border-slate-500 accent-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                  />
                )}
              </label>
            </div>
          </fieldset>

          {!isVoter && (
            <p className="text-xs text-slate-400">Voting is restricted to voters.</p>
          )}

          {isVoter && (
            <div className="flex justify-center gap-4 pt-2">
              <button
                type="button"
                onClick={handleVote}
                disabled={submitting || !hasChoice || !!existingVoteId}
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
