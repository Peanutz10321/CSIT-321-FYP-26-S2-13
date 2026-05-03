import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser, updateCurrentUser } from '../utils/api'

function UpdateAccount() {
  const navigate = useNavigate()
  const [formValues, setFormValues] = useState({
    username: '',
    full_name: '',
    email: '',
    password: '',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getCurrentUser()
      .then((user) => {
        setFormValues({
          username: user.username || '',
          full_name: user.full_name || '',
          email: user.email || '',
          password: '',
        })
      })
      .catch((error) => {
        alert(`Unable to load profile: ${error.message}`)
        navigate('/login')
      })
      .finally(() => setLoading(false))
  }, [navigate])

  const handleInputChange = (event) => {
    const { name, value } = event.target
    setFormValues((prev) => ({ ...prev, [name]: value }))
  }

  const handleSave = async (event) => {
    event.preventDefault()
    setSaving(true)

    try {
      const payload = {
        username: formValues.username,
        full_name: formValues.full_name,
        email: formValues.email,
      }

      if (formValues.password.trim()) {
        payload.password = formValues.password
      }

      await updateCurrentUser(payload)
      alert('Profile updated successfully!')
      navigate(-1)
    } catch (error) {
      alert(`Failed to update profile: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-600">Update Account</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Update Account</h1>
          <div className="mt-8 space-y-6">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-700">
                Username
              </label>
              <input
                id="username"
                name="username"
                value={formValues.username}
                onChange={handleInputChange}
                type="text"
                placeholder="Username"
                className="mt-2 block w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <div>
              <label htmlFor="full_name" className="block text-sm font-medium text-slate-700">
                Full Name
              </label>
              <input
                id="full_name"
                name="full_name"
                value={formValues.full_name}
                onChange={handleInputChange}
                type="text"
                placeholder="Full Name"
                className="mt-2 block w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-700">
                Email
              </label>
              <input
                id="email"
                name="email"
                value={formValues.email}
                onChange={handleInputChange}
                type="email"
                placeholder="Email"
                className="mt-2 block w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                New Password
              </label>
              <input
                id="password"
                name="password"
                value={formValues.password}
                onChange={handleInputChange}
                type="password"
                placeholder="New Password"
                className="mt-2 block w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="rounded-2xl bg-blue-600 px-6 py-4 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="rounded-2xl border border-slate-300 bg-white px-6 py-4 text-base font-semibold text-slate-900 transition hover:bg-slate-100"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

export default UpdateAccount
