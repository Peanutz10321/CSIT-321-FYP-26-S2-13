import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listUsers, createOrganizer } from '../utils/api.js'
import {
  Button,
  Card,
  Input,
  PageHeader,
  PageShell,
  ResponsiveListTable,
  StatusBadge,
} from '../components/ui.jsx'

const STATUS_LABEL = {
  active: 'Active',
  inactive: 'Inactive',
  suspended: 'Suspended',
}

const STATUS_TONE = {
  active: 'emerald',
  inactive: 'amber',
  suspended: 'rose',
}

const EMPTY_ORGANIZER_FORM = {
  username: '',
  email: '',
  password: '',
  full_name: '',
}

function ManageUsers() {
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  // Organizer accounts cannot be self-registered, so an admin provisions them here.
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [organizerForm, setOrganizerForm] = useState(EMPTY_ORGANIZER_FORM)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [createSuccess, setCreateSuccess] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    async function loadUsers() {
      setLoading(true)
      setError('')
      try {
        const data = await listUsers({ search: searchQuery })
        setUsers(data)
      } catch (err) {
        if (err.message?.toLowerCase().includes('not authenticated')) {
          navigate('/login')
          return
        }
        setError(err.message || 'Failed to load users.')
      } finally {
        setLoading(false)
      }
    }
    loadUsers()
  }, [searchQuery, navigate, refreshKey])

  const handleOrganizerFieldChange = (field) => (e) => {
    setOrganizerForm((current) => ({ ...current, [field]: e.target.value }))
  }

  const handleCreateOrganizer = async (e) => {
    e.preventDefault()
    setCreating(true)
    setCreateError('')
    setCreateSuccess('')

    try {
      const created = await createOrganizer({
        username: organizerForm.username.trim(),
        email: organizerForm.email.trim(),
        password: organizerForm.password,
        full_name: organizerForm.full_name.trim() || null,
      })

      setCreateSuccess(`Organizer ${created.username} created (${created.external_id}).`)
      setOrganizerForm(EMPTY_ORGANIZER_FORM)
      setRefreshKey((key) => key + 1)
    } catch (err) {
      setCreateError(err.message || 'Failed to create organizer.')
    } finally {
      setCreating(false)
    }
  }

  const handleSearch = (e) => {
    e.preventDefault()
    setSearchQuery(searchInput.trim())
  }

  const handleClearSearch = () => {
    setSearchInput('')
    setSearchQuery('')
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow="Admin"
        title="User Accounts"
        subtitle="Search by username, email, or school ID."
        actions={
          <>
            <Button
              onClick={() => {
                setShowCreateForm((shown) => !shown)
                setCreateError('')
                setCreateSuccess('')
              }}
            >
              {showCreateForm ? 'Cancel' : 'Create Organizer'}
            </Button>
            <Button variant="secondary" onClick={() => navigate('/admin-dashboard')}>
              Back to Dashboard
            </Button>
          </>
        }
      />

      {showCreateForm && (
        <Card>
          <h2 className="text-lg font-semibold text-slate-100">Create Organizer Account</h2>
          <p className="mt-1 text-sm text-slate-400">
            Organizers can create and manage elections, so accounts are provisioned here
            rather than through public registration.
          </p>

          {createError && (
            <div
              role="alert"
              className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300"
            >
              {createError}
            </div>
          )}

          <form onSubmit={handleCreateOrganizer} className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="organizer-username" className="mb-2 block text-sm text-slate-300">
                Username
              </label>
              <Input
                id="organizer-username"
                type="text"
                required
                value={organizerForm.username}
                onChange={handleOrganizerFieldChange('username')}
              />
            </div>

            <div>
              <label htmlFor="organizer-email" className="mb-2 block text-sm text-slate-300">
                Email
              </label>
              <Input
                id="organizer-email"
                type="email"
                required
                value={organizerForm.email}
                onChange={handleOrganizerFieldChange('email')}
              />
            </div>

            <div>
              <label htmlFor="organizer-full-name" className="mb-2 block text-sm text-slate-300">
                Full name (optional)
              </label>
              <Input
                id="organizer-full-name"
                type="text"
                value={organizerForm.full_name}
                onChange={handleOrganizerFieldChange('full_name')}
              />
            </div>

            <div>
              <label htmlFor="organizer-password" className="mb-2 block text-sm text-slate-300">
                Temporary password
              </label>
              <Input
                id="organizer-password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={organizerForm.password}
                onChange={handleOrganizerFieldChange('password')}
              />
            </div>

            <div className="sm:col-span-2">
              <Button type="submit" disabled={creating} className="sm:w-auto">
                {creating ? 'Creating...' : 'Create Organizer'}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {createSuccess && (
        <div
          role="status"
          className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300"
        >
          {createSuccess}
        </div>
      )}

      <Card>
        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row">
          <label htmlFor="user-search" className="sr-only">
            Search users
          </label>
          <Input
            id="user-search"
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by username, email, or school ID..."
          />
          <Button type="submit" className="sm:w-auto">
            Search
          </Button>
          {searchQuery && (
            <Button type="button" variant="secondary" onClick={handleClearSearch} className="sm:w-auto">
              Clear
            </Button>
          )}
        </form>

        {searchQuery && (
          <p className="mt-4 text-sm text-slate-400">
            Showing results for: <span className="font-semibold text-slate-200">{searchQuery}</span>
          </p>
        )}
      </Card>

      <ResponsiveListTable
        primary={{ header: 'Username', cell: (u) => u.username }}
        secondary={{
          header: 'Status',
          cell: (u) => (
            <StatusBadge tone={STATUS_TONE[u.status] ?? 'slate'}>
              {STATUS_LABEL[u.status] ?? u.status}
            </StatusBadge>
          ),
        }}
        action={(u) => (
          <Button size="sm" onClick={() => navigate(`/admin/users/${u.id}`)}>
            View
          </Button>
        )}
        items={users}
        getKey={(u) => u.id}
        loading={loading}
        error={error || null}
        loadingMessage="Loading users..."
        emptyTitle="No users found."
        emptyMessage="Try a different search term."
      />
    </PageShell>
  )
}

export default ManageUsers
