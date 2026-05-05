import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { activateElection, getElectionDrafts } from '../utils/api'

function ElectionDraft() {
  const navigate = useNavigate()
  const [drafts, setDrafts] = useState([])
  const [loading, setLoading] = useState(true)
  const [activatingId, setActivatingId] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    getElectionDrafts()
      .then((data) => setDrafts(data))
      .catch((error) => {
        alert(`Unable to load draft elections: ${error.message}`)
      })
      .finally(() => setLoading(false))
  }, [])

  const noDrafts = !loading && drafts.length === 0

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-amber-600">Election Drafts</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Election Drafts</h1>
          <div className="mt-6 max-w-md">
            <label htmlFor="search" className="sr-only">Search</label>
            <input
              id="search"
              type="search"
              placeholder="Search drafts"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
        </div>

        {loading ? (
          <div className="rounded-3xl border border-slate-200 bg-white p-6 text-slate-700">Loading drafts...</div>
        ) : noDrafts && searchTerm === '' ? (
          <div className="rounded-3xl border border-slate-200 bg-white p-6 text-slate-700">
            No drafts available. Create one to get started!
          </div>
        ) : (() => {
          const filteredDrafts = drafts.filter((draft) =>
            draft.title.toLowerCase().includes(searchTerm.toLowerCase())
          )
          return filteredDrafts.length === 0 ? (
            <div className="rounded-3xl border border-slate-200 bg-white p-6 text-slate-700">
              No drafts match your search.
            </div>
          ) : (
          <div className="space-y-4">
            {filteredDrafts.map((draft) => {
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
                        onClick={() => navigate(`/update-election/${draft.id}`)}
                        className="inline-flex items-center justify-center rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                      >
                        Edit
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
                </div>
              )
            })}
          </div>
          );
        })()}

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
