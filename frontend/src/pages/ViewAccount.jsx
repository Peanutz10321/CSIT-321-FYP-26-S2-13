import { useNavigate, useLocation } from 'react-router-dom'

function ViewAccount() {
  const navigate = useNavigate()
  const location = useLocation()
  const returnPath = location.state?.from || localStorage.getItem('backTo') || '/login'

  const handleBack = () => {
    navigate(returnPath)
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-600">Account Details</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Account Details</h1>
          <div className="mt-8 space-y-5 text-sm text-slate-700">
            <div>
              <p className="font-semibold text-slate-900">Username</p>
              <p>student123</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Full Name</p>
              <p>Alice Johnson</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">School ID</p>
              <p>SCH-00123</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Email</p>
              <p>alice.johnson@example.com</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Role</p>
              <p>Student</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Account Status</p>
              <p>Active</p>
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <button
            onClick={() => navigate('/update-account')}
            className="rounded-2xl bg-blue-600 px-6 py-4 text-base font-semibold text-white transition hover:bg-blue-700"
          >
            Update Information
          </button>
          <button
            onClick={handleBack}
            className="rounded-2xl border border-slate-300 bg-white px-6 py-4 text-base font-semibold text-slate-900 transition hover:bg-slate-100"
          >
            Back
          </button>
        </div>
      </div>
    </div>
  )
}

export default ViewAccount
