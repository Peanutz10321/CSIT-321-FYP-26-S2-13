import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createElection,
  createElectionDraft,
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
    voter_institution_ids: voters,
  })

  const refreshDrafts = () => getElectionDrafts().then(setDrafts).catch(() => {})

  const handleSelectDraft = async (draft) => {
    setSelectedDraftId(draft.id)
    setTitle(draft.title)
    setCandidatesText(draft.candidates.map((c) => c.name).join(', '))
    setEndDate(draft.end_date ? draft.end_date.slice(0, 16) : '')
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
    if (!title.trim() && !candidatesText.trim() && !endDate && !eligibleVotersText.trim()) {
      alert('Please key in something at least before saving.')
      return
    }

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
    setSaving(true)
    try {
      const election = await createElection(buildPayload(parseList(candidatesText), parseList(eligibleVotersText)))
      navigate('/election-detail', { state: { electionId: election.id, from: 'active', role: 'teacher' } })
    } catch {
      alert('Missing field or invalid input detected. Please key in again.')
    } finally {
      setSaving(false)
    }
  }

  const inputClass =
    'w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800'
  const labelClass = 'font-semibold text-slate-100 sm:w-52 sm:shrink-0'

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-5xl">
        <div className="rounded-2xl border border-slate-600 bg-slate-800/80 shadow-lg md:rounded-sm md:border-2 md:border-slate-500">

          <div className="border-b border-slate-500 py-5">
            <h2 className="text-center text-xl font-semibold text-slate-100">Create Election</h2>
          </div>

          <div className="flex flex-col md:flex-row md:min-h-[480px]">

            {/* Sidebar */}
            <div className="w-full border-b border-slate-600 md:w-48 md:shrink-0 md:border-b-0 md:border-r md:border-slate-500">
              <p className="px-4 pt-3 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-400 md:hidden">Saved Drafts</p>
              <div className="max-h-40 overflow-y-auto md:max-h-none">
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
            <div className="flex flex-1 flex-col justify-between px-4 py-6 md:px-10 md:py-8">
              <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-400 md:hidden">Election Details</p>
              <div className="space-y-6">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
                  <span className={labelClass}>Title:</span>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Election title"
                    className={inputClass}
                  />
                </div>

                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
                  <span className={`${labelClass} sm:pt-3`}>Candidates:</span>
                  <textarea
                    rows={3}
                    value={candidatesText}
                    onChange={(e) => setCandidatesText(e.target.value)}
                    placeholder="Comma or newline separated names"
                    className={`${inputClass} resize-none`}
                  />
                </div>

                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
                  <span className={labelClass}>Deadline:</span>
                  <input
                    type="datetime-local"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className={inputClass}
                  />
                </div>

                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
                  <span className={`${labelClass} sm:pt-3`}>Eligible Student Votes:</span>
                  <textarea
                    rows={3}
                    value={eligibleVotersText}
                    onChange={(e) => setEligibleVotersText(e.target.value)}
                    placeholder="Comma or newline separated institution IDs"
                    className={`${inputClass} resize-none`}
                  />
                </div>
              </div>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-end sm:gap-4">
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={saving}
                  className="w-full rounded-2xl bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                >
                  {saving ? 'Creating...' : 'Create'}
                </button>
                <button
                  type="button"
                  onClick={handleSaveDraft}
                  disabled={saving}
                  className="w-full rounded-2xl border border-slate-600 bg-slate-800 px-6 py-3 text-base font-semibold text-slate-100 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
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
