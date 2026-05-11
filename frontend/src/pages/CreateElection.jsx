import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  addElectionVoter,
  activateElection,
  createElectionDraft,
  updateElection,
  getElectionDrafts,
  getEligibleVoters,
} from '../utils/api'

function CreateElection() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [endDate, setEndDate] = useState('')
  const [candidatesText, setCandidatesText] = useState('')
  const [eligibleVotersText, setEligibleVotersText] = useState('')
  const [saving, setSaving] = useState(false)
  const [drafts, setDrafts] = useState([])
  const [selectedDraftId, setSelectedDraftId] = useState(null)

  useEffect(() => {
    getElectionDrafts().then(setDrafts).catch(() => {})
  }, [])

  const parseList = (text) =>
    text
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean)

  const normalizeDateTime = (dt) => (dt && dt.length === 16 ? `${dt}:00` : dt)

  const buildPayload = (candidateNames) => ({
    title: title.trim(),
    description: null,
    start_date: new Date().toISOString().slice(0, 19),
    end_date: normalizeDateTime(endDate),
    candidates: candidateNames.map((name, index) => ({
      name,
      description: null,
      photo_url: null,
      display_order: index + 1,
    })),
  })

  const validate = (requireVoters = false) => {
    const candidateNames = parseList(candidatesText)
    if (!title.trim()) { alert('Please enter election title.'); return null }
    if (!endDate) { alert('Please enter a deadline.'); return null }
    if (candidateNames.length === 0) { alert('Please enter at least one candidate.'); return null }
    const voters = parseList(eligibleVotersText)
    if (requireVoters && voters.length === 0) {
      alert('You must add at least one eligible student to create an active election.')
      return null
    }
    return { candidateNames, voters }
  }

  const refreshDrafts = () =>
    getElectionDrafts().then(setDrafts).catch(() => {})

  const handleSelectDraft = async (draft) => {
    setSelectedDraftId(draft.id)
    setTitle(draft.title)
    setCandidatesText(draft.candidates.map((c) => c.name).join(', '))
    setEndDate(draft.end_date.slice(0, 16))
    try {
      const voters = await getEligibleVoters(draft.id)
      setEligibleVotersText(voters.map((v) => v.student_institution_id).join(', '))
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
  }

  const handleSaveDraft = async () => {
    const result = validate(false)
    if (!result) return
    const { candidateNames, voters } = result
    setSaving(true)
    try {
      if (selectedDraftId) {
        await updateElection(selectedDraftId, buildPayload(candidateNames))
        alert('Draft updated successfully!')
      } else {
        const election = await createElectionDraft(buildPayload(candidateNames))
        for (const institutionId of voters) {
          await addElectionVoter(election.id, institutionId)
        }
        setSelectedDraftId(election.id)
        alert('Draft saved successfully!')
      }
      await refreshDrafts()
    } catch (error) {
      alert(`Failed to save draft: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async () => {
    const result = validate(true)
    if (!result) return
    const { candidateNames, voters } = result
    setSaving(true)
    try {
      let electionId = selectedDraftId
      if (selectedDraftId) {
        await updateElection(selectedDraftId, buildPayload(candidateNames))
        for (const institutionId of voters) {
          try { await addElectionVoter(selectedDraftId, institutionId) } catch { /* already added */ }
        }
        electionId = selectedDraftId
      } else {
        const election = await createElectionDraft(buildPayload(candidateNames))
        for (const institutionId of voters) {
          await addElectionVoter(election.id, institutionId)
        }
        electionId = election.id
      }
      await activateElection(electionId)
      alert('Election created successfully!')
      navigate('/election-drafts')
    } catch (error) {
      alert(`Failed to create election: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const inputClass =
    'flex-1 rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800'
  const labelClass = 'w-52 shrink-0 font-semibold text-slate-100'

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-5xl">

        {/* Single bordered card */}
        <div className="rounded-sm border-2 border-slate-500 bg-slate-800/80 shadow-lg">

          {/* Title spanning full width */}
          <div className="border-b border-slate-500 py-5">
            <h2 className="text-center text-xl font-semibold text-slate-100">Create Election</h2>
          </div>

          {/* Body: sidebar + divider + form */}
          <div className="flex min-h-[480px]">

            {/* Sidebar */}
            <div className="w-48 shrink-0 border-r border-slate-500">
              <div className="overflow-y-auto">
                {drafts.length === 0 ? (
                  <p className="px-4 py-6 text-center text-xs text-slate-400">No drafts yet</p>
                ) : (
                  <ul className="divide-y divide-slate-700">
                    {drafts.map((draft) => (
                      <li key={draft.id}>
                        <button
                          type="button"
                          onClick={() => handleSelectDraft(draft)}
                          className={`w-full px-4 py-3 text-left text-sm transition hover:bg-slate-700 ${
                            selectedDraftId === draft.id
                              ? 'bg-slate-700 font-semibold text-blue-400'
                              : 'text-slate-300'
                          }`}
                        >
                          {draft.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {selectedDraftId && (
                <div className="border-t border-slate-600 px-3 py-3">
                  <button
                    type="button"
                    onClick={handleClearSelection}
                    className="w-full rounded-xl bg-slate-700 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-600"
                  >
                    + New
                  </button>
                </div>
              )}
            </div>

            {/* Form */}
            <div className="flex flex-1 flex-col justify-between px-10 py-8">
              <div className="space-y-6">
                <div className="flex items-center gap-4">
                  <span className={labelClass}>Title:</span>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Election title"
                    className={inputClass}
                  />
                </div>

                <div className="flex items-start gap-4">
                  <span className={`${labelClass} pt-3`}>Candidates:</span>
                  <textarea
                    rows={3}
                    value={candidatesText}
                    onChange={(e) => setCandidatesText(e.target.value)}
                    placeholder="Comma or newline separated names"
                    className={`${inputClass} resize-none`}
                  />
                </div>

                <div className="flex items-center gap-4">
                  <span className={labelClass}>Deadline:</span>
                  <input
                    type="datetime-local"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className={inputClass}
                  />
                </div>

                <div className="flex items-start gap-4">
                  <span className={`${labelClass} pt-3`}>Eligible Student Votes:</span>
                  <textarea
                    rows={3}
                    value={eligibleVotersText}
                    onChange={(e) => setEligibleVotersText(e.target.value)}
                    placeholder="Comma or newline separated institution IDs"
                    className={`${inputClass} resize-none`}
                  />
                </div>
              </div>

              {/* Buttons pinned to bottom-right */}
              <div className="mt-8 flex justify-end gap-4">
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={saving}
                  className="rounded-2xl bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {saving ? 'Creating...' : 'Create'}
                </button>
                <button
                  type="button"
                  onClick={handleSaveDraft}
                  disabled={saving}
                  className="rounded-2xl border border-slate-600 bg-slate-800 px-6 py-3 text-base font-semibold text-slate-100 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {saving ? 'Saving...' : 'Save Election Draft'}
                </button>
              </div>
            </div>

          </div>
        </div>

      </div>
    </div>
  )
}

export default CreateElection
