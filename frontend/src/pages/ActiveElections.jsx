import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getActiveElections, getCurrentUser } from '../utils/api.js'

function ActiveElections() {
  const navigate = useNavigate()
  const [activeElections, setActiveElections] = useState([])
  const [currentUser, setCurrentUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCurrentUser()
      .then(setCurrentUser)
      .catch(() => {
        navigate('/login')
      })

    getActiveElections()
      .then((data) => setActiveElections(data))
      .catch(() => {
        navigate('/login')
      })
      .finally(() => setLoading(false))
  }, [navigate])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 px-4 py-10">
        <div className="mx-auto max-w-5xl text-slate-700">Loading data...</div>
      </div>
    )
  }

  const noData = activeElections.length === 0

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-sky-600">My Active Elections</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Active Elections</h1>
          <div className="mt-6 max-w-md">
            <label htmlFor="search" className="sr-only">Search</label>
            <input
              id="search"
              type="search"
              placeholder="Search elections"
              className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
        </div>

        <div className="space-y-4">
          {noData ? (
            <div className="rounded-3xl border border-slate-200 bg-white p-6 text-center text-slate-500">
              No data available at the moment.
            </div>
          ) : (
            activeElections.map((election) => (
              <div key={election.id} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-lg font-semibold text-slate-900">{election.title}</p>
                    <p className="mt-1 text-sm text-slate-500">{election.end_date ? new Date(election.end_date).toLocaleDateString() : 'Active election'}</p>
                  </div>
                  <button
                    onClick={() => navigate('/cast-vote', { state: { electionId: election.id } })}
                    className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
                  >
                    {currentUser?.role === 'student' ? 'Vote' : 'View Details'}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default ActiveElections
