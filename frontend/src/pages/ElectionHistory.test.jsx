import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import ElectionHistory from './ElectionHistory.jsx'
import { getElectionHistory } from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  getElectionHistory: vi.fn(),
}))

// The history endpoint returns completed elections alongside active elections
// whose deadline has passed but that were never closed.
const completedElection = {
  id: 'e-completed',
  title: 'Completed Election',
  status: 'completed',
  end_date: '2026-07-01T10:00:00',
}
const activeExpiredElection = {
  id: 'e-active',
  title: 'Expired Not Closed',
  status: 'active',
  end_date: '2026-07-02T10:00:00',
}

async function renderHistory(elections, fromState = '/organizer-dashboard') {
  getElectionHistory.mockResolvedValue(elections)

  render(
    <MemoryRouter initialEntries={[{ pathname: '/election-history', state: { from: fromState } }]}>
      <ElectionHistory />
    </MemoryRouter>,
  )

  await screen.findByText(elections[0].title)
}

function viewButtonForRow(title) {
  return screen.getByText(title).closest('.grid').querySelector('button')
}

describe('ElectionHistory View navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('opens Election Results for a completed election', async () => {
    await renderHistory([completedElection])

    fireEvent.click(viewButtonForRow('Completed Election'))

    expect(navigateMock).toHaveBeenCalledWith('/election-results', {
      state: { electionId: 'e-completed', role: 'organizer' },
    })
  })

  it('opens Election Results for an election that is not completed', async () => {
    await renderHistory([activeExpiredElection])

    fireEvent.click(viewButtonForRow('Expired Not Closed'))

    expect(navigateMock).toHaveBeenCalledWith('/election-results', {
      state: { electionId: 'e-active', role: 'organizer' },
    })
  })

  it('never navigates to Election Detail from history', async () => {
    await renderHistory([completedElection, activeExpiredElection])

    fireEvent.click(viewButtonForRow('Completed Election'))
    fireEvent.click(viewButtonForRow('Expired Not Closed'))

    expect(navigateMock).not.toHaveBeenCalledWith('/election-detail', expect.anything())
    expect(navigateMock).toHaveBeenCalledTimes(2)
  })

  it('routes every row to Election Results with its own election id', async () => {
    await renderHistory([completedElection, activeExpiredElection])

    // Existing rendering still works: both rows render with a View button.
    expect(screen.getAllByRole('button', { name: 'View' })).toHaveLength(2)

    fireEvent.click(viewButtonForRow('Completed Election'))
    expect(navigateMock).toHaveBeenLastCalledWith('/election-results', {
      state: { electionId: 'e-completed', role: 'organizer' },
    })

    fireEvent.click(viewButtonForRow('Expired Not Closed'))
    expect(navigateMock).toHaveBeenLastCalledWith('/election-results', {
      state: { electionId: 'e-active', role: 'organizer' },
    })
  })

  it('preserves the voter role so voter history opens results as a voter', async () => {
    await renderHistory([completedElection], '/voter-dashboard')

    fireEvent.click(viewButtonForRow('Completed Election'))

    expect(navigateMock).toHaveBeenCalledWith('/election-results', {
      state: { electionId: 'e-completed', role: 'voter' },
    })
  })

  it('shows the empty state when there is no history', async () => {
    getElectionHistory.mockResolvedValue([])

    render(
      <MemoryRouter initialEntries={[{ pathname: '/election-history', state: {} }]}>
        <ElectionHistory />
      </MemoryRouter>,
    )

    expect(await screen.findByText('No elections found.')).toBeInTheDocument()
  })
})
