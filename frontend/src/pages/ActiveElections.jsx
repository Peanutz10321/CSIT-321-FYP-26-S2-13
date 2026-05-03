import { useNavigate } from 'react-router-dom'

const activeElections = [
  { id: 1, title: 'Student Council Election', date: 'Complete Date: 12 Jun 2026' },
  { id: 2, title: 'Presidential Election', date: 'Complete Date: 20 Jun 2026' },
  { id: 3, title: 'Library Committee Vote', date: 'Complete Date: 28 Jun 2026' },
]

function ActiveElections() {
  const navigate = useNavigate()

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
          {activeElections.map((election) => (
            <div key={election.id} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-lg font-semibold text-slate-900">{election.title}</p>
                  <p className="mt-1 text-sm text-slate-500">{election.date}</p>
                </div>
                <button
                  onClick={() => navigate('/cast-vote')}
                  className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
                >
                  View
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default ActiveElections
