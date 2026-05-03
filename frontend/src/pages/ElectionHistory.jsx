import { useNavigate, useLocation } from 'react-router-dom'

const elections = [
  { id: 1, title: 'Student Council Election', date: 'Completed Date: 12 Jun 2026' },
  { id: 2, title: 'Presidential Election', date: 'Completed Date: 20 Jun 2026' },
  { id: 3, title: 'Library Committee Election', date: 'Completed Date: 28 Jun 2026' },
]

function ElectionHistory() {
  const navigate = useNavigate()
  const location = useLocation()
  const returnPath = location.state?.from || localStorage.getItem('backTo') || '/login'

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-600">Election History</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Election History</h1>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">Start Date</span>
              <input
                type="date"
                className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">End Date</span>
              <input
                type="date"
                className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </label>
          </div>
        </div>

        <div className="space-y-4">
          {elections.map((election) => (
            <div key={election.id} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-lg font-semibold text-slate-900">{election.title}</p>
                  <p className="mt-1 text-sm text-slate-500">{election.date}</p>
                </div>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <button
                    onClick={() => navigate('/election-results')}
                    className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
                  >
                    View Results
                  </button>
                  <button
                    onClick={() => navigate('/election-detail')}
                    className="rounded-2xl border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
                  >
                    View Details
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="pt-6 text-right">
          <button
            onClick={() => navigate(returnPath)}
            className="inline-flex items-center justify-center rounded-2xl border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}

export default ElectionHistory
