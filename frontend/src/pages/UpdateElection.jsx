import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getElectionDetails, getEligibleVoters, addElectionVoter, updateElection } from '../utils/api'

function UpdateElection() {
  const navigate = useNavigate()
  const { electionId } = useParams()

  const [election, setElection] = useState(null)
  const [eligibleVoters, setEligibleVoters] = useState([])
  const [loading, setLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [newInstitutionId, setNewInstitutionId] = useState('')
  const [addingVoter, setAddingVoter] = useState(false)
  const [title, setTitle] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [candidatesText, setCandidatesText] = useState('')

  useEffect(() => {
    const fetchElectionData = async () => {
      try {
        setLoading(true)
        const [electionData, votersData] = await Promise.all([
          getElectionDetails(electionId),
          getEligibleVoters(electionId),
        ])
        setElection(electionData)
        setEligibleVoters(votersData)
        setTitle(electionData.title || '')
        setStartDate(electionData.start_date ? new Date(electionData.start_date).toISOString().slice(0, 16) : '')
        setEndDate(electionData.end_date ? new Date(electionData.end_date).toISOString().slice(0, 16) : '')
        setCandidatesText(
          electionData.candidates?.map((candidate) => candidate.name).join('\n') || ''
        )
      } catch (error) {
        alert(`Failed to load election details: ${error.message}`)
        navigate('/election-drafts')
      } finally {
        setLoading(false)
      }
    }

    if (electionId) {
      fetchElectionData()
    }
  }, [electionId, navigate])

  const handleAddVoter = async () => {
    const institutionId = newInstitutionId.trim()
    if (!institutionId) {
      alert('Please enter an institution ID.')
      return
    }

    setAddingVoter(true)
    try {
      await addElectionVoter(electionId, institutionId)
      alert('Voter added successfully!')
      setNewInstitutionId('')
      // Refresh voters list
      const votersData = await getEligibleVoters(electionId)
      setEligibleVoters(votersData)
    } catch (error) {
      alert(`Failed to add voter: ${error.message}`)
    } finally {
      setAddingVoter(false)
    }
  }

  const handleSave = async () => {
    const trimmedTitle = title.trim()
    const trimmedStart = startDate.trim()
    const trimmedEnd = endDate.trim()

    if (!trimmedTitle) {
      alert('Please enter election title.')
      return
    }

    if (!trimmedStart || !trimmedEnd) {
      alert('Please enter both start and end date/time.')
      return
    }

    const candidateNames = candidatesText
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean)

    if (candidateNames.length === 0) {
      alert('Please enter at least one candidate.')
      return
    }

    const payload = {
      title: trimmedTitle,
      description: election.description ?? null,
      start_date: trimmedStart,
      end_date: trimmedEnd,
      candidates: candidateNames.map((name, index) => ({
        name,
        description: null,
        photo_url: null,
        display_order: index + 1,
      })),
    }

    setIsSaving(true)
    try {
      await updateElection(electionId, payload)
      alert('Election updated successfully!')
      navigate('/election-drafts')
    } catch (error) {
      alert(`Failed to update election: ${error.message}`)
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancel = () => {
    navigate('/election-drafts')
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 px-4 py-10">
        <div className="mx-auto max-w-4xl">
          <div className="rounded-3xl bg-white p-8 shadow-sm text-center">
            <p className="text-slate-600">Loading election details...</p>
          </div>
        </div>
      </div>
    )
  }

  if (!election) {
    return (
      <div className="min-h-screen bg-slate-50 px-4 py-10">
        <div className="mx-auto max-w-4xl">
          <div className="rounded-3xl bg-white p-8 shadow-sm text-center">
            <p className="text-slate-600">Election not found</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-amber-600">Update Election Details</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Update Election Details</h1>
          <div className="mt-8 space-y-6">
            <div>
              <label htmlFor="title" className="block text-sm font-medium text-slate-700">
                Election Title
              </label>
              <input
                id="title"
                type="text"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
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
                  type="datetime-local"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                  className="mt-2 block w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-100"
                />
              </div>
              <div>
                <label htmlFor="end" className="block text-sm font-medium text-slate-700">
                  End Date & Time
                </label>
                <input
                  id="end"
                  type="datetime-local"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
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
                rows="5"
                value={candidatesText}
                onChange={(event) => setCandidatesText(event.target.value)}
                placeholder="Enter candidate names, separated by commas or new lines"
                className="mt-2 block w-full rounded-3xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-100"
              />
            </div>
            <div>
              <label htmlFor="eligible-voters" className="block text-sm font-medium text-slate-700">
                Eligible Voters
              </label>
              <div className="mt-2 flex gap-3">
                <input
                  id="new-voter"
                  type="text"
                  value={newInstitutionId}
                  onChange={(e) => setNewInstitutionId(e.target.value)}
                  placeholder="Enter institution ID"
                  className="flex-1 rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-100"
                />
                <button
                  type="button"
                  onClick={handleAddVoter}
                  disabled={addingVoter}
                  className="inline-flex items-center rounded-2xl bg-amber-500 px-5 py-3 text-sm font-semibold text-slate-900 transition hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {addingVoter ? 'Adding...' : 'Add Voter'}
                </button>
              </div>

              {eligibleVoters.length > 0 && (
                <div className="mt-4 rounded-3xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm font-medium text-slate-700">Eligible Voters ({eligibleVoters.length})</p>
                  <ul className="mt-3 space-y-2">
                    {eligibleVoters.map((voter) => (
                      <li key={voter.id} className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3">
                        <div>
                          <span className="text-sm font-medium text-slate-900">{voter.student_full_name}</span>
                          <span className="ml-2 text-sm text-slate-500">({voter.student_institution_id})</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row">
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="w-full rounded-2xl bg-slate-900 px-6 py-4 text-base font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSaving ? 'Saving...' : 'Save Changes'}
          </button>
          <button
            type="button"
            onClick={handleCancel}
            className="w-full rounded-2xl border border-slate-300 bg-white px-6 py-4 text-base font-semibold text-slate-900 transition hover:bg-slate-100"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

export default UpdateElection
