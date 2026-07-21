import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createElection,
  createElectionDraft,
  getElectionDrafts,
  getEligibleVoters,
} from '../utils/api'
import { Button, Card, Input, PageHeader, PageShell, Textarea } from '../components/ui.jsx'

function CreateElection() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [endDate, setEndDate] = useState('')
  const [candidatesText, setCandidatesText] = useState('')
  const [eligibleVotersText, setEligibleVotersText] = useState('')
  const [ballotType, setBallotType] = useState('single')
  const [maxSelections, setMaxSelections] = useState('1')
  const [ballotError, setBallotError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [drafts, setDrafts] = useState([])
  const [selectedDraftId, setSelectedDraftId] = useState(null)

  useEffect(() => {
    getElectionDrafts().then(setDrafts).catch(() => {})
  }, [])

  const parseList = (text) =>
    text.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean)

  const normalizeDateTime = (dt) => (dt && dt.length === 16 ? `${dt}:00` : dt)

  const nowLocalNaive = () => {
    const d = new Date()
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
    return d.toISOString().slice(0, 19)
  }

  const buildPayload = (candidateNames, voters = []) => ({
    title: title.trim(),
    description: null,
    start_date: nowLocalNaive(),
    end_date: endDate ? normalizeDateTime(endDate) : null,
    candidates: candidateNames.map((name, index) => ({
      name,
      description: null,
      photo_url: null,
      display_order: index + 1,
    })),
    eligible_voter_external_ids: voters,
    ballot_type: ballotType,
    max_selections: ballotType === 'single' ? 1 : Number(maxSelections),
  })

  // Drafts may hold an incomplete configuration (backend re-validates the candidate
  // count at activation), so the count rule only applies to final active creation.
  // Invalid values are reported inline — never silently clamped.
  const validateBallotConfig = (candidateCount, forActiveCreate) => {
    if (ballotType === 'single') return null
    const max = Number(maxSelections)
    if (!Number.isInteger(max) || max < 1) {
      return 'Maximum selections must be a whole number of at least 1.'
    }
    if (forActiveCreate && max > candidateCount) {
      return `Maximum selections cannot exceed the number of candidates (${candidateCount}).`
    }
    return null
  }

  const refreshDrafts = () => getElectionDrafts().then(setDrafts).catch(() => {})

  const handleSelectDraft = async (draft) => {
    setSelectedDraftId(draft.id)
    setTitle(draft.title)
    setCandidatesText(draft.candidates.map((c) => c.name).join(', '))
    setEndDate(draft.end_date ? draft.end_date.slice(0, 16) : '')
    setBallotType(draft.ballot_type || 'single')
    setMaxSelections(String(draft.max_selections ?? 1))
    setBallotError(null)
    try {
      const voters = await getEligibleVoters(draft.id)
      setEligibleVotersText(voters.map((v) => v.voter_external_id).join(', '))
    } catch {
      setEligibleVotersText('')
    }
  }

  const handleClearSelection = () => {
    setSelectedDraftId(null)
    setTitle('')
    setCandidatesText('')
    setEndDate('')
    setEligibleVotersText('')
    setBallotType('single')
    setMaxSelections('1')
    setBallotError(null)
  }

  const handleSaveDraft = async () => {
    if (!title.trim() && !candidatesText.trim() && !endDate && !eligibleVotersText.trim()) {
      alert('Please key in something at least before saving.')
      return
    }

    const configError = validateBallotConfig(parseList(candidatesText).length, false)
    if (configError) {
      setBallotError(configError)
      return
    }
    setBallotError(null)

    setSaving(true)
    try {
      await createElectionDraft(buildPayload(parseList(candidatesText)))
      await refreshDrafts()
    } catch (error) {
      alert(`Failed to save draft: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async () => {
    const candidateNames = parseList(candidatesText)

    const configError = validateBallotConfig(candidateNames.length, true)
    if (configError) {
      setBallotError(configError)
      return
    }
    setBallotError(null)

    setSaving(true)
    try {
      const election = await createElection(buildPayload(candidateNames, parseList(eligibleVotersText)))
      navigate('/election-detail', { state: { electionId: election.id, from: 'active', role: 'organizer' } })
    } catch {
      alert('Missing field or invalid input detected. Please key in again.')
    } finally {
      setSaving(false)
    }
  }

  const fieldLabel = 'mb-2 block text-sm font-medium text-slate-200'
  const radioOption = (active) =>
    `flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium transition ${
      active
        ? 'border-blue-400 bg-blue-500/10 text-blue-200'
        : 'border-slate-700 bg-slate-950/40 text-slate-200 hover:border-slate-600'
    }`

  return (
    <PageShell>
      <PageHeader
        eyebrow="Elections"
        title="Create Election"
        subtitle="Configure a new voting event. Save a draft to finish later, or create it to open voting."
        actions={
          <Button variant="secondary" onClick={() => navigate('/organizer-dashboard')}>
            Back to Dashboard
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        {/* Saved drafts */}
        <Card padded={false} className="h-max overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Saved Drafts</p>
            {selectedDraftId && (
              <Button size="sm" variant="subtle" onClick={handleClearSelection}>
                + New
              </Button>
            )}
          </div>
          {drafts.length === 0 ? (
            <p className="px-5 py-6 text-center text-xs text-slate-500">No drafts yet</p>
          ) : (
            <ul className="max-h-64 divide-y divide-slate-800/70 overflow-y-auto lg:max-h-none">
              {drafts.map((draft) => (
                <li key={draft.id}>
                  <button
                    type="button"
                    onClick={() => handleSelectDraft(draft)}
                    className={`w-full px-5 py-3 text-left text-sm transition hover:bg-slate-800/60 ${
                      selectedDraftId === draft.id
                        ? 'bg-slate-800/60 font-semibold text-blue-300'
                        : 'text-slate-300'
                    }`}
                  >
                    {draft.title}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Election form */}
        <Card>
          <div className="space-y-6">
            <div>
              <label htmlFor="election-title" className={fieldLabel}>
                Title
              </label>
              <Input
                id="election-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Election title"
              />
            </div>

            <div>
              <label htmlFor="election-candidates" className={fieldLabel}>
                Candidates
              </label>
              <Textarea
                id="election-candidates"
                rows={3}
                value={candidatesText}
                onChange={(e) => setCandidatesText(e.target.value)}
                placeholder="Comma or newline separated names"
                className="resize-none"
              />
              <p className="mt-1.5 text-xs text-slate-500">
                Separate each candidate with a comma or a new line.
              </p>
            </div>

            <div>
              <label htmlFor="election-deadline" className={fieldLabel}>
                Deadline
              </label>
              <Input
                id="election-deadline"
                type="datetime-local"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>

            <fieldset>
              <legend className={fieldLabel}>Ballot Type</legend>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className={radioOption(ballotType === 'single')}>
                  <input
                    type="radio"
                    name="ballot-type"
                    value="single"
                    checked={ballotType === 'single'}
                    onChange={() => {
                      setBallotType('single')
                      setBallotError(null)
                    }}
                    className="h-4 w-4 cursor-pointer accent-blue-500"
                  />
                  Single choice
                </label>
                <label className={radioOption(ballotType === 'multi')}>
                  <input
                    type="radio"
                    name="ballot-type"
                    value="multi"
                    checked={ballotType === 'multi'}
                    onChange={() => {
                      setBallotType('multi')
                      setBallotError(null)
                    }}
                    className="h-4 w-4 cursor-pointer accent-blue-500"
                  />
                  Multiple choice
                </label>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                {ballotType === 'multi'
                  ? 'Voters may pick several candidates, up to the limit below.'
                  : 'Voters pick exactly one candidate.'}
              </p>

              {ballotType === 'multi' && (
                <div className="mt-4 max-w-[12rem]">
                  <label htmlFor="max-selections" className={fieldLabel}>
                    Maximum selections
                  </label>
                  <Input
                    id="max-selections"
                    type="number"
                    min="1"
                    step="1"
                    value={maxSelections}
                    onChange={(e) => {
                      setMaxSelections(e.target.value)
                      setBallotError(null)
                    }}
                  />
                </div>
              )}

              {ballotError && (
                <p role="alert" className="mt-3 text-sm text-rose-400">
                  {ballotError}
                </p>
              )}
            </fieldset>

            <div>
              <label htmlFor="election-voters" className={fieldLabel}>
                Eligible Voter External IDs
              </label>
              <Textarea
                id="election-voters"
                rows={3}
                value={eligibleVotersText}
                onChange={(e) => setEligibleVotersText(e.target.value)}
                placeholder="Comma or newline separated external IDs"
                className="resize-none"
              />
              <p className="mt-1.5 text-xs text-slate-500">
                Only these external IDs will be eligible to vote in this election.
              </p>
            </div>
          </div>

          <div className="mt-8 flex flex-col gap-3 border-t border-slate-800 pt-6 sm:flex-row sm:justify-end sm:gap-4">
            <Button variant="secondary" onClick={handleSaveDraft} disabled={saving} className="sm:w-auto">
              {saving ? 'Saving...' : 'Save Election Draft'}
            </Button>
            <Button onClick={handleCreate} disabled={saving} className="sm:w-auto">
              {saving ? 'Creating...' : 'Create'}
            </Button>
          </div>
        </Card>
      </div>
    </PageShell>
  )
}

export default CreateElection
