import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { activateElection, deleteElection, getElectionDrafts } from '../utils/api'

function ElectionDraft() {
  const navigate = useNavigate()
  const [drafts, setDrafts] = useState([])
  const [loading, setLoading] = useState(true)
  const [activatingId, setActivatingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    setLoading(true)
    getElectionDrafts({ search: searchQuery })
      .then((data) => setDrafts(data))
      .catch((error) => {
        alert(`Unable to load draft elections: ${error.message}`)
      })
      .finally(() => setLoading(false))
  }, [searchQuery])

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-slate-800 p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-amber-400">Election Drafts</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-100">Election Drafts</h1>
          <form onSubmit={(e) => { e.preventDefault(); setSearchQuery(searchInput.trim()) }} className="mt-6 flex max-w-md gap-3">
            <label htmlFor="search" className="sr-only">Search</label>
            <input
              id="search"
              type="text"
              placeholder="Search drafts"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            />
            <button
              type="submit"
              className="rounded-2xl bg-blue-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
            >
              Search
            </button>
          </form>
        </div>

        {loading ? (
          <div className="rounded-3xl border border-slate-700 bg-slate-800 p-6 text-slate-300">Loading drafts...</div>
        ) : drafts.length === 0 ? (
          <div className="rounded-3xl border border-slate-700 bg-slate-800 p-6 text-slate-300">
            {searchQuery ? 'No drafts match your search.' : 'No drafts available. Create one to get started!'}
          </div>
        ) : (
          <div className="space-y-4">
            {drafts.map((draft) => {
              return (
                <div key={draft.id} className="rounded-3xl border border-slate-700 bg-slate-800 p-6 shadow-sm">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="text-lg font-semibold text-slate-100">{draft.title}</p>
                      {draft.candidates?.length ? (
                        <p className="mt-2 text-sm text-slate-400">
                          Candidates: {draft.candidates.map((candidate) => candidate.name).join(', ')}
                        </p>
                      ) : null}
                      <p className="mt-3 text-sm text-slate-400">
                        <span className="font-medium text-slate-300">Start Time:</span>{' '}
                        {draft.start_date ? new Date(draft.start_date).toLocaleString() : 'TBD'}
                      </p>
                      <p className="mt-1 text-sm text-slate-400">
                        <span className="font-medium text-slate-300">End Time:</span>{' '}
                        {draft.end_date ? new Date(draft.end_date).toLocaleString() : 'TBD'}
                      </p>
                    </div>
                    <div className="flex flex-col gap-3 sm:flex-row">
                      <button
                        type="button"
                        onClick={() => navigate(`/update-election/${draft.id}`)}
                        className="inline-flex items-center justify-center rounded-2xl bg-slate-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-600"
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
                        className="inline-flex items-center justify-center rounded-2xl border border-slate-600 bg-slate-800 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {activatingId === draft.id ? 'Activating...' : 'Activate'}
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          if (!window.confirm('Are you sure you want to delete this draft?')) {
                            return
                          }
                          setDeletingId(draft.id)
                          try {
                            await deleteElection(draft.id)
                            setDrafts((current) => current.filter((d) => d.id !== draft.id))
                            alert('Draft deleted successfully!')
                          } catch (error) {
                            alert(`Failed to delete draft: ${error.message}`)
                          } finally {
                            setDeletingId(null)
                          }
                        }}
                        disabled={deletingId === draft.id}
                        className="inline-flex items-center justify-center rounded-2xl border border-slate-600 bg-slate-800 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {deletingId === draft.id ? 'Deleting...' : 'Delete'}
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        <div className="pt-4">
          <button
            onClick={() => navigate('/teacher-dashboard')}
            className="inline-flex items-center justify-center rounded-2xl border border-slate-600 bg-slate-800 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}

export default ElectionDraft
