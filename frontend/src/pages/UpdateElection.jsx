import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getElectionDetails, updateElection, extendElectionDeadline } from '../utils/api'

function UpdateElection() {
  const navigate = useNavigate()
  const { electionId } = useParams()

  const [election, setElection] = useState(null)
  const [title, setTitle] = useState('')
  const [endDate, setEndDate] = useState('')
  const [ballotType, setBallotType] = useState('single')
  const [maxSelections, setMaxSelections] = useState('1')
  const [ballotError, setBallotError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getElectionDetails(electionId)
      .then((data) => {
        setElection(data)
        setTitle(data.title || '')
        setEndDate(data.end_date ? new Date(data.end_date).toISOString().slice(0, 16) : '')
        setBallotType(data.ballot_type || 'single')
        setMaxSelections(String(data.max_selections ?? 1))
      })
      .catch((err) => {
        alert(`Failed to load election: ${err.message}`)
        navigate(-1)
      })
      .finally(() => setLoading(false))
  }, [electionId, navigate])

  const normalizeDateTime = (dt) => (dt && dt.length === 16 ? `${dt}:00` : dt)

  const handleSave = async () => {
    if (election.status !== 'active' && ballotType === 'multi') {
      const max = Number(maxSelections)
      if (!Number.isInteger(max) || max < 1) {
        setBallotError('Maximum selections must be a whole number of at least 1.')
        return
      }
    }
    setBallotError(null)

    setSaving(true)
    try {
      if (election.status === 'active') {
        // Active elections only support deadline extension; the ballot
        // configuration is locked and never sent to this endpoint.
        await extendElectionDeadline(electionId, normalizeDateTime(endDate), title.trim())
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
          ballot_type: ballotType,
          max_selections: ballotType === 'single' ? 1 : Number(maxSelections),
        })
      }
      alert('Election updated successfully!')
      navigate(-1)
    } catch {
      alert('Missing field or invalid input detected. Please key in again.')
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

  const inputClass =
    'w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800'
  const labelClass = 'font-semibold text-slate-100 sm:w-32 sm:shrink-0'

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-xl space-y-6">

        <div className="rounded-sm border-2 border-slate-500 bg-slate-800/80 px-4 py-6 shadow-lg sm:px-8 sm:py-10">
          <h2 className="mb-8 text-center text-xl font-semibold text-slate-100">Update Election Details</h2>

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

            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
              <span className={labelClass}>Deadline:</span>
              <input
                type="datetime-local"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className={inputClass}
              />
            </div>

            {election?.status === 'draft' ? (
              <fieldset className="space-y-3">
                <legend className="font-semibold text-slate-100">Ballot Type:</legend>
                <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:gap-8">
                  <label className="flex cursor-pointer items-center gap-3 py-1 text-slate-100">
                    <input
                      type="radio"
                      name="ballot-type"
                      value="single"
                      checked={ballotType === 'single'}
                      onChange={() => {
                        setBallotType('single')
                        setBallotError(null)
                      }}
                      className="h-5 w-5 cursor-pointer accent-blue-500"
                    />
                    Single choice
                  </label>
                  <label className="flex cursor-pointer items-center gap-3 py-1 text-slate-100">
                    <input
                      type="radio"
                      name="ballot-type"
                      value="multi"
                      checked={ballotType === 'multi'}
                      onChange={() => {
                        setBallotType('multi')
                        setBallotError(null)
                      }}
                      className="h-5 w-5 cursor-pointer accent-blue-500"
                    />
                    Multiple choice
                  </label>
                </div>
                {ballotType === 'multi' && (
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
                    <label htmlFor="max-selections" className="text-sm text-slate-300">
                      Maximum selections
                    </label>
                    <input
                      id="max-selections"
                      type="number"
                      min="1"
                      step="1"
                      value={maxSelections}
                      onChange={(e) => {
                        setMaxSelections(e.target.value)
                        setBallotError(null)
                      }}
                      className="w-28 rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
                    />
                  </div>
                )}
                {ballotError && (
                  <p role="alert" className="text-sm text-rose-400">
                    {ballotError}
                  </p>
                )}
              </fieldset>
            ) : (
              <p className="text-sm text-slate-300">
                <span className="font-semibold text-slate-100">Ballot Type: </span>
                {ballotType === 'multi'
                  ? `Multiple choice — up to ${maxSelections} selections`
                  : 'Single choice'}
                <span className="mt-1 block text-xs text-slate-400">
                  The ballot configuration is locked once the election is active.
                </span>
              </p>
            )}
          </div>

          <div className="mt-10 sm:flex sm:justify-center">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="w-full rounded-2xl bg-blue-600 px-8 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
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
