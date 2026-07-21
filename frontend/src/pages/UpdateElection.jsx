import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getElectionDetails, updateElection, extendElectionDeadline } from '../utils/api'
import { Button, Card, Input, LoadingState, PageHeader, PageShell, StatusBadge } from '../components/ui.jsx'

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
      <PageShell width="max-w-xl">
        <Card padded={false}>
          <LoadingState message="Loading election..." />
        </Card>
      </PageShell>
    )
  }

  const isActive = election?.status === 'active'
  const fieldLabel = 'mb-2 block text-sm font-medium text-slate-200'
  const radioOption = (active) =>
    `flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium transition ${
      active
        ? 'border-blue-400 bg-blue-500/10 text-blue-200'
        : 'border-slate-700 bg-slate-950/40 text-slate-200 hover:border-slate-600'
    }`

  return (
    <PageShell width="max-w-xl">
      <PageHeader
        eyebrow="Elections"
        title="Update Election Details"
        subtitle={
          isActive
            ? 'This election is live — you can extend its deadline. Ballot settings are locked.'
            : 'This election is still a draft, so every detail can still be changed.'
        }
        actions={
          <StatusBadge tone={isActive ? 'emerald' : 'amber'}>
            {isActive ? 'Active' : 'Draft'}
          </StatusBadge>
        }
      />

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

          {election?.status === 'draft' ? (
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
          ) : (
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <p className={fieldLabel}>Ballot Type</p>
              <p className="text-sm text-slate-100">
                {ballotType === 'multi'
                  ? `Multiple choice — up to ${maxSelections} selections`
                  : 'Single choice'}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                The ballot configuration is locked once the election is active.
              </p>
            </div>
          )}
        </div>

        <div className="mt-8 flex flex-col gap-3 border-t border-slate-800 pt-6 sm:flex-row sm:justify-end sm:gap-4">
          <Button variant="secondary" onClick={() => navigate(-1)} className="sm:w-auto">
            Back
          </Button>
          <Button onClick={handleSave} disabled={saving} className="sm:w-auto">
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </Card>
    </PageShell>
  )
}

export default UpdateElection
