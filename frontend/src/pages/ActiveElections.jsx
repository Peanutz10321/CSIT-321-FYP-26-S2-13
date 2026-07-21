import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getActiveElections, getCurrentUser } from '../utils/api.js'
import { Button, Card, Input, PageHeader, PageShell, ResponsiveListTable } from '../components/ui.jsx'

function ActiveElections() {
  const navigate = useNavigate()
  const [activeElections, setActiveElections] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [role, setRole] = useState('')

  useEffect(() => {
    getCurrentUser()
      .then((user) => setRole(user.role || ''))
      .catch(() => navigate('/login'))
  }, [navigate])

  useEffect(() => {
    setLoading(true)
    getActiveElections({ search: searchQuery })
      .then(setActiveElections)
      .catch(() => navigate('/login'))
      .finally(() => setLoading(false))
  }, [searchQuery, navigate])

  const handleSearch = (e) => {
    e.preventDefault()
    setSearchQuery(searchInput)
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow="Voting"
        title="My Active Elections"
        subtitle="Elections that are currently open. Select one to view details or cast your vote."
        actions={
          <Button
            variant="secondary"
            onClick={() => navigate(role === 'organizer' ? '/organizer-dashboard' : '/voter-dashboard')}
          >
            Back to Dashboard
          </Button>
        }
      />

      <Card>
        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row">
          <label htmlFor="election-search" className="sr-only">
            Search elections
          </label>
          <Input
            id="election-search"
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search elections by title..."
          />
          <Button type="submit" className="sm:w-auto">
            Search
          </Button>
        </form>
      </Card>

      <ResponsiveListTable
        primary={{ header: 'Election Title', cell: (e) => e.title }}
        secondary={{
          header: 'Deadline',
          cell: (e) => (e.end_date ? new Date(e.end_date).toLocaleDateString() : '—'),
        }}
        action={(e) => (
          <Button
            size="sm"
            onClick={() =>
              navigate('/election-detail', { state: { electionId: e.id, from: 'active', role } })
            }
          >
            View
          </Button>
        )}
        items={activeElections}
        getKey={(e) => e.id}
        loading={loading}
        loadingMessage="Loading elections..."
        emptyTitle="No elections found."
        emptyMessage="You have no active elections right now."
      />
    </PageShell>
  )
}

export default ActiveElections
