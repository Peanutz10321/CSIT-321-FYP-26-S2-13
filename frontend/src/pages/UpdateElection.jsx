import { useNavigate } from 'react-router-dom'

function UpdateElection() {
  const navigate = useNavigate()

  const handleSave = () => {
    alert('Changes Saved')
    navigate('/election-drafts')
  }

  const handleCancel = () => {
    navigate('/election-drafts')
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
                placeholder="Enter candidate names, separated by commas or new lines"
                className="mt-2 block w-full rounded-3xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-100"
              />
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row">
          <button
            type="button"
            onClick={handleSave}
            className="w-full rounded-2xl bg-slate-900 px-6 py-4 text-base font-semibold text-white transition hover:bg-slate-800"
          >
            Save Changes
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
