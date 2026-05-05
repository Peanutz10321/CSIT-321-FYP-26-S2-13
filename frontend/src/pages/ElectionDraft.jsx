import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { activateElection, getElectionDrafts, getEligibleVoters, addElectionVoter } from '../utils/api'

function ElectionDraft() {
  const navigate = useNavigate()
  const [drafts, setDrafts] = useState([])
  const [loading, setLoading] = useState(true)
  const [activatingId, setActivatingId] = useState(null)
  const [visibleVoterPanel, setVisibleVoterPanel] = useState(null)
  const [votersByElection, setVotersByElection] = useState({})
  const [voterLoading, setVoterLoading] = useState({})
  const [newInstitutionId, setNewInstitutionId] = useState({})
  const [addingVoterId, setAddingVoterId] = useState(null)

  useEffect(() => {
    getElectionDrafts()
      .then((data) => setDrafts(data))
      .catch((error) => {
        alert(`Unable to load draft elections: ${error.message}`)
      })
      .finally(() => setLoading(false))
  }, [])

  const fetchEligibleVoters = async (electionId) => {
    setVoterLoading((prev) => ({ ...prev, [electionId]: true }))

    try {
      const voters = await getEligibleVoters(electionId)
      setVotersByElection((prev) => ({ ...prev, [electionId]: voters }))
    } catch (error) {
      alert(`Unable to load eligible voters: ${error.message}`)
    } finally {
      setVoterLoading((prev) => ({ ...prev, [electionId]: false }))
    }
  }

  const handleToggleVoterPanel = (electionId) => {
    const isOpen = visibleVoterPanel === electionId
    setVisibleVoterPanel(isOpen ? null : electionId)

    if (!isOpen && !votersByElection[electionId]) {
      fetchEligibleVoters(electionId)
    }
  }

  const handleInstitutionIdChange = (electionId, value) => {
    setNewInstitutionId((prev) => ({ ...prev, [electionId]: value }))
  }

  const handleAddVoter = async (electionId) => {
    const institution_id = (newInstitutionId[electionId] || '').trim()
    if (!institution_id) {
      alert('Please enter an institution ID for the voter.')
      return
    }

    setAddingVoterId(electionId)

    try {
      await addElectionVoter(electionId, institution_id)
      alert('Voter added successfully!')
      setNewInstitutionId((prev) => ({ ...prev, [electionId]: '' }))
      await fetchEligibleVoters(electionId)
    } catch (error) {
      alert(`Failed to add voter: ${error.message}`)
    } finally {
      setAddingVoterId(null)
    }
  }

  const noDrafts = !loading && drafts.length === 0

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-amber-600">Election Drafts</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Election Drafts</h1>
        </div>

        {loading ? (
          <div className="rounded-3xl border border-slate-200 bg-white p-6 text-slate-700">Loading drafts...</div>
        ) : noDrafts ? (
          <div className="rounded-3xl border border-slate-200 bg-white p-6 text-slate-700">
            No drafts available. Create one to get started!
          </div>
        ) : (
          <div className="space-y-4">
            {drafts.map((draft) => {
              const voters = votersByElection[draft.id] || []
              const votersLoading = voterLoading[draft.id]
              const isPanelOpen = visibleVoterPanel === draft.id

              return (
                <div key={draft.id} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="text-lg font-semibold text-slate-900">{draft.title}</p>
                      {draft.candidates?.length ? (
                        <p className="mt-2 text-sm text-slate-500">
                          Candidates: {draft.candidates.map((candidate) => candidate.name).join(', ')}
                        </p>
                      ) : null}
                      <p className="mt-3 text-sm text-slate-500">
                        <span className="font-medium text-slate-700">Start Time:</span>{' '}
                        {draft.start_date ? new Date(draft.start_date).toLocaleString() : 'TBD'}
                      </p>
                      <p className="mt-1 text-sm text-slate-500">
                        <span className="font-medium text-slate-700">End Time:</span>{' '}
                        {draft.end_date ? new Date(draft.end_date).toLocaleString() : 'TBD'}
                      </p>
                    </div>
                    <div className="flex flex-col gap-3 sm:flex-row">
                      <button
                        type="button"
                        onClick={() => navigate('/update-election')}
                        className="inline-flex items-center justify-center rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleVoterPanel(draft.id)}
                        className="inline-flex items-center justify-center rounded-2xl border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
                      >
                        {isPanelOpen ? 'Hide Voters' : 'Manage Voters'}
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          if (!window.confirm('Activate this draft election?')) {
                            return
                          }

                          setActivatingId(draft.id)
                          try {
                            await activateElection(draft.id)
                            alert('Election activated!')
                            navigate('/active-elections')
                          } catch (error) {
                            alert(`Failed to activate election: ${error.message}`)
                          } finally {
                            setActivatingId(null)
                          }
                        }}
                        disabled={activatingId === draft.id}
                        className="inline-flex items-center justify-center rounded-2xl border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {activatingId === draft.id ? 'Activating...' : 'Activate'}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm('Are you sure you want to delete this draft?')) {
                            alert('Draft deleted!')
                          }
                        }}
                        className="inline-flex items-center justify-center rounded-2xl border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
                      >
                        Delete
                      </button>
                    </div>
                  </div>

                  {isPanelOpen ? (
                    <div className="mt-6 rounded-3xl border border-slate-200 bg-slate-50 p-5">
                      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">Eligible voters</p>
                          <p className="text-sm text-slate-500">{voters.length} voter{voters.length === 1 ? '' : 's'}</p>
                        </div>
                      </div>

                      <div className="mt-4 space-y-4">
                        {votersLoading ? (
                          <div className="rounded-2xl bg-white p-4 text-slate-700">Loading voters...</div>
                        ) : voters.length === 0 ? (
                          <div className="rounded-2xl bg-white p-4 text-slate-700">No eligible voters yet.</div>
                        ) : (
                          <div className="space-y-3">
                            {voters.map((voter) => (
                              <div key={voter.id} className="rounded-2xl bg-white p-4 shadow-sm">
                                <p className="font-medium text-slate-900">{voter.student_full_name}</p>
                                <p className="text-sm text-slate-500">{voter.student_email}</p>
                                <p className="text-sm text-slate-500">Institution ID: {voter.student_institution_id}</p>
                              </div>
                            ))}
                          </div>
                        )}

                        <div className="rounded-2xl bg-white p-4 shadow-sm">
                          <label htmlFor={`institution-${draft.id}`} className="block text-sm font-medium text-slate-700">
                            Add eligible voter by institution ID
                          </label>
                          <input
                            id={`institution-${draft.id}`}
                            value={newInstitutionId[draft.id] || ''}
                            onChange={(event) => handleInstitutionIdChange(draft.id, event.target.value)}
                            placeholder="Institution ID"
                            className="mt-2 w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                          />
                          <button
                            type="button"
                            onClick={() => handleAddVoter(draft.id)}
                            disabled={addingVoterId === draft.id}
                            className="mt-4 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {addingVoterId === draft.id ? 'Adding...' : 'Add Voter'}
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        )}

        <div className="pt-4">
          <button
            onClick={() => navigate('/teacher-dashboard')}
            className="inline-flex items-center justify-center rounded-2xl border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}

export default ElectionDraft
