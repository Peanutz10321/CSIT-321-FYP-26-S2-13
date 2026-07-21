import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listUsers } from '../utils/api.js'
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

function ManageUsers() {
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

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
  }, [searchQuery, navigate])

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
          <Button variant="secondary" onClick={() => navigate('/admin-dashboard')}>
            Back to Dashboard
          </Button>
        }
      />

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
