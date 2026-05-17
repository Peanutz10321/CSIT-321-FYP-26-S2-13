import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getElectionDetails, updateElection, extendElectionDeadline } from '../utils/api'

function UpdateElection() {
  const navigate = useNavigate()
  const { electionId } = useParams()

  const [election, setElection] = useState(null)
  const [title, setTitle] = useState('')
  const [endDate, setEndDate] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getElectionDetails(electionId)
      .then((data) => {
        setElection(data)
        setTitle(data.title || '')
        setEndDate(data.end_date ? new Date(data.end_date).toISOString().slice(0, 16) : '')
      })
      .catch((err) => {
        alert(`Failed to load election: ${err.message}`)
        navigate(-1)
      })
      .finally(() => setLoading(false))
  }, [electionId, navigate])

  const normalizeDateTime = (dt) => (dt && dt.length === 16 ? `${dt}:00` : dt)

  const handleSave = async () => {
    setSaving(true)
    try {
      if (election.status === 'active') {
        await extendElectionDeadline(electionId, normalizeDateTime(endDate))
      } else {
        await updateElection(electionId, {
          title: title.trim(),
          description: election.description ?? null,
          start_date: election.start_date,
          end_date: normalizeDateTime(endDate),
          candidates: election.candidates?.map((c, i) => ({
            name: c.name,
            description: c.description ?? null,
            photo_url: c.photo_url ?? null,
            display_order: c.display_order ?? i + 1,
          })),
        })
      }
      alert('Election updated successfully!')
      navigate(-1)
    } catch (error) {
      alert(`Failed to update election: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 px-4 py-10">
        <div className="mx-auto max-w-xl text-slate-300">Loading...</div>
      </div>
    )
  }

  const isActive = election?.status === 'active'
  const inputClass =
    'flex-1 rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800'
  const labelClass = 'w-32 shrink-0 font-semibold text-slate-100'

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-xl space-y-6">

        <div className="rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg">
          <h2 className="mb-8 text-center text-xl font-semibold text-slate-100">Update Election Details</h2>

          <div className="space-y-6">
            <div className="flex items-center gap-4">
              <span className={labelClass}>Title:</span>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={isActive}
                placeholder="Election title"
                className={`${inputClass} ${isActive ? 'cursor-not-allowed opacity-50' : ''}`}
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
          </div>

          <div className="mt-10 flex justify-center">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="rounded-2xl bg-blue-600 px-8 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>

        <button
          type="button"
          onClick={() => navigate(-1)}
          className="w-full rounded-2xl border border-slate-600 bg-slate-800 px-6 py-4 text-base font-semibold text-slate-100 transition hover:bg-slate-700"
        >
          Back
        </button>

      </div>
    </div>
  )
}

export default UpdateElection
