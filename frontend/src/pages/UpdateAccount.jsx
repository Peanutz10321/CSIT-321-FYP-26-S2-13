import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser, updateCurrentUser } from '../utils/api'
import { Button, Card, Input, LoadingState, PageHeader, PageShell } from '../components/ui.jsx'

function UpdateAccount() {
  const navigate = useNavigate()
  const [formValues, setFormValues] = useState({
    username: '',
    email: '',
    password: '',
  })
  const [role, setRole] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getCurrentUser()
      .then((user) => {
        setRole(user.role || '')
        setFormValues({
          username: user.username || '',
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
        email: formValues.email,
      }

      if (formValues.password.trim()) {
        payload.password = formValues.password
      }

      await updateCurrentUser(payload)
      navigate(-1)
    } catch {
      alert('Missing field or invalid input detected. Please key in again.')
    } finally {
      setSaving(false)
    }
  }

  const labelClass = 'mb-2 block text-sm font-medium text-slate-200'

  if (loading) {
    return (
      <PageShell width="max-w-xl">
        <Card padded={false}>
          <LoadingState message="Loading profile..." />
        </Card>
      </PageShell>
    )
  }

  return (
    <PageShell width="max-w-xl">
      <PageHeader
        eyebrow="Account"
        title="Update Account"
        actions={
          <Button variant="secondary" onClick={() => navigate(-1)}>
            Back
          </Button>
        }
      />

      <Card>
        <div className="space-y-6">
          <div>
            <label htmlFor="username" className={labelClass}>
              Username
            </label>
            <Input
              id="username"
              name="username"
              value={formValues.username}
              onChange={handleInputChange}
              type="text"
              placeholder="Username"
            />
          </div>

          <div>
            <label htmlFor="email" className={labelClass}>
              {role === 'organizer' ? 'Organizer Email' : 'Voter Email'}
            </label>
            <Input
              id="email"
              name="email"
              value={formValues.email}
              onChange={handleInputChange}
              type="email"
              placeholder="Email"
            />
          </div>

          <div>
            <label htmlFor="password" className={labelClass}>
              New Password
            </label>
            <Input
              id="password"
              name="password"
              value={formValues.password}
              onChange={handleInputChange}
              type="password"
              autoComplete="new-password"
              placeholder="New Password"
            />
            <p className="mt-1.5 text-xs text-slate-500">Leave blank to keep your current password.</p>
          </div>

          <div className="border-t border-slate-800 pt-6 sm:flex sm:justify-end">
            <Button type="button" onClick={handleSave} disabled={saving} className="sm:w-auto">
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </div>
      </Card>
    </PageShell>
  )
}

export default UpdateAccount
