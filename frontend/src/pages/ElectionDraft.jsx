import { useNavigate } from 'react-router-dom'

const draftItems = [
  { id: 1, title: 'Draft 1: Class President' },
  { id: 2, title: 'Draft 2: Prom King' },
]

function ElectionDraft() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-amber-600">Election Drafts</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Election Drafts</h1>
        </div>

        <div className="space-y-4">
          {draftItems.map((draft) => (
            <div key={draft.id} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-lg font-semibold text-slate-900">{draft.title}</p>
                </div>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <button
                    onClick={() => navigate('/update-election')}
                    className="inline-flex items-center justify-center rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                  >
                    Edit
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
          ))}
        </div>

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
