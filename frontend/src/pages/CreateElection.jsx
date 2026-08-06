import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  activateElection,
  createElection,
  createElectionDraft,
  getElectionDrafts,
  getEligibleVoters,
  getGroups,
  getUsersByGroup,
  updateElection,
} from '../utils/api'
import { Button, Card, Combobox, Input, PageHeader, PageShell, Textarea } from '../components/ui.jsx'

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
  const [loadingDraft, setLoadingDraft] = useState(false)
  const [draftLoadError, setDraftLoadError] = useState(null)
  // Candidate description/photo_url as stored on the selected draft. The form only
  // edits names, so a save has to carry the rest back rather than blank it.
  const [draftCandidates, setDraftCandidates] = useState([])
  // Bumped on every selection. Only the newest load may write into the form, so a
  // slow response for draft A cannot land in draft B's fields.
  const draftLoadRef = useRef(0)
  // Organisation picker: a shortcut that fills the eligible-voter box from a group's
  // members. It only ever writes into that box — the draft lifecycle around it is
  // untouched, and the box stays directly editable afterwards.
  const [groups, setGroups] = useState([])
  const [selectedGroup, setSelectedGroup] = useState('')
  const [groupMemberCount, setGroupMemberCount] = useState(null)
  const [loadingMembers, setLoadingMembers] = useState(false)
  const [groupError, setGroupError] = useState(null)

  useEffect(() => {
    getElectionDrafts().then(setDrafts).catch(() => {})
    // A missing/forbidden group directory just leaves the picker empty; it is an
    // optional shortcut, so it must never block creating an election.
    getGroups().then(setGroups).catch(() => setGroups([]))
  }, [])

  const parseList = (text) =>
    text.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean)

  const normalizeDateTime = (dt) => (dt && dt.length === 16 ? `${dt}:00` : dt)

  const nowLocalNaive = () => {
    const d = new Date()
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
    return d.toISOString().slice(0, 19)
  }

  // Voters default to whatever is currently in the form, so a draft save carries the
  // eligibility list just like an active create does and can restore it on resume.
  const buildPayload = (candidateNames, voters = parseList(eligibleVotersText)) => ({
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

  // The update payload for an existing draft. It differs from the create payload in
  // what it deliberately leaves out: this form owns the title, candidate names,
  // deadline, ballot config and voter list, and nothing else. Anything it does not
  // show must survive a re-save untouched.
  const buildUpdatePayload = (candidateNames) => {
    const payload = buildPayload(candidateNames)

    // start_date is fixed when the election is created; re-sending a fresh "now"
    // would silently move it on every save.
    delete payload.start_date

    payload.candidates = payload.candidates.map((candidate) => {
      const stored = draftCandidates.find((item) => item.name === candidate.name)
      return stored
        ? {
            ...candidate,
            description: stored.description ?? null,
            photo_url: stored.photo_url ?? null,
          }
        : candidate
    })

    // The voter list never loaded, so the textarea is empty for a reason that has
    // nothing to do with the organizer's intent. Omitting the field entirely leaves
    // the stored list alone instead of clearing it.
    if (draftLoadError) {
      delete payload.eligible_voter_external_ids
    }

    return payload
  }

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

  const resetGroupSelection = () => {
    setSelectedGroup('')
    setGroupMemberCount(null)
    setGroupError(null)
    setLoadingMembers(false)
  }

  // Fills the eligible-voter box from a group's members. It replaces the box rather
  // than appending, so the selection and the field always agree; the organizer can
  // still edit the result by hand afterwards.
  const handleGroupSelect = async (groupName) => {
    setSelectedGroup(groupName)
    setGroupError(null)
    setGroupMemberCount(null)

    if (!groupName) return

    setLoadingMembers(true)
    try {
      const members = await getUsersByGroup(groupName)
      setEligibleVotersText(members.map((member) => member.external_id).join(', '))
      setGroupMemberCount(members.length)
      // The box now holds a list the organizer chose deliberately, so a stale
      // "we could not load the draft's voters" warning must not suppress it on save.
      setDraftLoadError(null)
    } catch (error) {
      setGroupError(`Failed to load members for “${groupName}”: ${error.message}`)
    } finally {
      setLoadingMembers(false)
    }
  }

  const handleSelectDraft = async (draft) => {
    const loadId = ++draftLoadRef.current

    setSelectedDraftId(draft.id)
    setTitle(draft.title)
    setCandidatesText(draft.candidates.map((c) => c.name).join(', '))
    setDraftCandidates(draft.candidates || [])
    setEndDate(draft.end_date ? draft.end_date.slice(0, 16) : '')
    setBallotType(draft.ballot_type || 'single')
    setMaxSelections(String(draft.max_selections ?? 1))
    setBallotError(null)
    setDraftLoadError(null)
    setEligibleVotersText('')
    setLoadingDraft(true)
    // The draft's own saved voters are about to be loaded, so any group shortcut
    // used on the previous form no longer describes what is in the box.
    resetGroupSelection()

    try {
      const voters = await getEligibleVoters(draft.id)
      if (draftLoadRef.current !== loadId) return
      setEligibleVotersText(voters.map((v) => v.voter_external_id).join(', '))
    } catch {
      if (draftLoadRef.current !== loadId) return
      setDraftLoadError(
        'Could not load this draft’s eligible voters. Select the draft again to retry — saving now will leave the saved list unchanged.',
      )
    } finally {
      if (draftLoadRef.current === loadId) setLoadingDraft(false)
    }
  }

  const handleClearSelection = () => {
    // Invalidates any load still in flight, so it cannot populate the blank form.
    draftLoadRef.current += 1

    setSelectedDraftId(null)
    setTitle('')
    setCandidatesText('')
    setDraftCandidates([])
    setEndDate('')
    setEligibleVotersText('')
    setBallotType('single')
    setMaxSelections('1')
    setBallotError(null)
    setDraftLoadError(null)
    setLoadingDraft(false)
    resetGroupSelection()
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
      const candidateNames = parseList(candidatesText)
      // A draft that is already open is edited in place; only a form with no draft
      // selected creates one. Otherwise every save would fork another draft.
      if (selectedDraftId) {
        await updateElection(selectedDraftId, buildUpdatePayload(candidateNames))
      } else {
        const draft = await createElectionDraft(buildPayload(candidateNames))
        setSelectedDraftId(draft.id)
        setDraftCandidates(draft.candidates || [])
      }
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
      let electionId

      if (selectedDraftId) {
        // Publishing a draft promotes that same row: save the latest edits, then
        // activate it. Creating a second election would orphan the draft. If
        // activation fails the election stays a draft with the edits already saved,
        // so the organizer can fix the problem and publish again.
        await updateElection(selectedDraftId, buildUpdatePayload(candidateNames))
        await activateElection(selectedDraftId)
        electionId = selectedDraftId
      } else {
        const election = await createElection(buildPayload(candidateNames))
        electionId = election.id
      }

      navigate('/election-detail', { state: { electionId, from: 'active', role: 'organizer' } })
    } catch (error) {
      alert(`Failed to create election: ${error.message}`)
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
              <label htmlFor="election-group" className={fieldLabel}>
                Add Voters by Organization{' '}
                <span className="font-normal text-slate-500">(optional)</span>
              </label>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="w-full flex-1">
                  <Combobox
                    id="election-group"
                    value={selectedGroup}
                    onChange={handleGroupSelect}
                    options={groups}
                    placeholder="Search organizations"
                    emptyMessage="No organizations match that search"
                    describedBy="election-group-hint"
                    // Same rule as Save/Create: the draft is still loading into the
                    // form, so nothing may overwrite the voter box yet.
                    disabled={loadingMembers || loadingDraft}
                  />
                </div>
                <p className="text-sm text-slate-400 sm:whitespace-nowrap">
                  {loadingMembers
                    ? 'Loading members...'
                    : groupMemberCount !== null
                      ? `${groupMemberCount} member${groupMemberCount === 1 ? '' : 's'} added below`
                      : ''}
                </p>
              </div>
              {groupError && (
                <p role="alert" className="mt-2 text-sm text-rose-400">
                  {groupError}
                </p>
              )}
              {groupMemberCount === 0 && !loadingMembers && (
                <p className="mt-2 text-sm text-amber-400">
                  No active voters are registered in this organization.
                </p>
              )}
              <p id="election-group-hint" className="mt-1.5 text-xs text-slate-500">
                {groups.length === 0
                  ? 'No organizations available yet — voters set one when they register.'
                  : 'Replaces the list below with every active voter in the organization. You can still edit it by hand.'}
              </p>
            </div>

            <div>
              <label htmlFor="election-voters" className={fieldLabel}>
                Eligible Voter External IDs
              </label>
              <Textarea
                id="election-voters"
                rows={3}
                value={eligibleVotersText}
                onChange={(e) => {
                  setEligibleVotersText(e.target.value)
                  // Typing here takes ownership of the field: what the organizer
                  // enters must be submitted, not suppressed by the failed load.
                  setDraftLoadError(null)
                }}
                placeholder="Comma or newline separated external IDs"
                className="resize-none"
              />
              <p className="mt-1.5 text-xs text-slate-500">
                Only these external IDs will be eligible to vote in this election.
              </p>
              {draftLoadError && (
                <p role="alert" className="mt-2 text-sm text-rose-400">
                  {draftLoadError}
                </p>
              )}
            </div>
          </div>

          <div className="mt-8 flex flex-col gap-3 border-t border-slate-800 pt-6 sm:flex-row sm:justify-end sm:gap-4">
            {/* Both actions submit the whole form, so neither may run while the
                selected draft is still loading into it. */}
            <Button
              variant="secondary"
              onClick={handleSaveDraft}
              disabled={saving || loadingDraft}
              className="sm:w-auto"
            >
              {saving ? 'Saving...' : 'Save Election Draft'}
            </Button>
            <Button onClick={handleCreate} disabled={saving || loadingDraft} className="sm:w-auto">
              {saving ? 'Creating...' : 'Create'}
            </Button>
          </div>
        </Card>
      </div>
    </PageShell>
  )
}

export default CreateElection
