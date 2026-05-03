import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createElectionDraft } from '../utils/api'

function CreateElection() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [candidatesText, setCandidatesText] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSaveDraft = async () => {
    const candidateNames = candidatesText
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean)

    if (!title.trim()) {
      alert('Please enter election title.')
      return
    }

    if (!startDate || !endDate) {
      alert('Please enter both start and end date/time.')
      return
    }

    if (candidateNames.length === 0) {
      alert('Please enter at least one candidate.')
      return
    }

    setSaving(true)

    try {
      const payload = {
        title: title.trim(),
        description: null,
        start_date: startDate,
        end_date: endDate,
        candidates: candidateNames.map((name, index) => ({
          name,
          description: null,
          photo_url: null,
          display_order: index + 1,
        })),
      }

      await createElectionDraft(payload)
      alert('Draft created successfully!')
      navigate('/election-drafts')
    } catch (error) {
      alert(`Failed to create draft: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handlePublish = () => {
    alert('Election Published!')
    navigate('/teacher-dashboard')
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-amber-600">Create Election</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Create Election</h1>
          <div className="mt-8 space-y-6">
            <div>
              <label htmlFor="title" className="block text-sm font-medium text-slate-700">
                Election Title
              </label>
              <input
                id="title"
                name="title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                type="text"
                placeholder="Enter election title"
                className="mt-2 block w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-100"
              />
            </div>
            <div className="grid gap-6 sm:grid-cols-2">
              <div>
                <label htmlFor="start" className="block text-sm font-medium text-slate-700">
                  Start Date & Time
                </label>
                <input
                  id="start"
                  name="start"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                  type="datetime-local"
                  className="mt-2 block w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-100"
                />
              </div>
              <div>
                <label htmlFor="end" className="block text-sm font-medium text-slate-700">
                  End Date & Time
                </label>
                <input
                  id="end"
                  name="end"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                  type="datetime-local"
                  className="mt-2 block w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-100"
                />
              </div>
            </div>
            <div>
              <label htmlFor="candidates" className="block text-sm font-medium text-slate-700">
                Candidates
              </label>
              <textarea
                id="candidates"
                name="candidates"
                rows="5"
                value={candidatesText}
                onChange={(event) => setCandidatesText(event.target.value)}
                placeholder="Enter candidate names, separated by commas or new lines"
                className="mt-2 block w-full rounded-3xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-100"
              />
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row">
          <button
            type="button"
            onClick={handleSaveDraft}
            disabled={saving}
            className="w-full rounded-2xl bg-slate-900 px-6 py-4 text-base font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? 'Saving Draft...' : 'Save as Draft'}
          </button>
          <button
            type="button"
            onClick={handlePublish}
            className="w-full rounded-2xl bg-amber-500 px-6 py-4 text-base font-semibold text-slate-900 transition hover:bg-amber-600"
          >
            Publish Election
          </button>
        </div>
      </div>
    </div>
  )
}

export default CreateElection
