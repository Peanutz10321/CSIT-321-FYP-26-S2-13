import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import ElectionDetail from './ElectionDetail.jsx'
import { getElectionDetails, getEligibleVoters, getVoteHistory } from '../utils/api.js'

vi.mock('../utils/api.js', () => ({
  getElectionDetails: vi.fn(),
  getEligibleVoters: vi.fn(),
  getVoteHistory: vi.fn(),
}))

const baseElection = {
  id: 'e1',
  title: 'Club Election',
  organizer_username: 'org1',
  end_date: '2026-07-02T10:00:00',
  candidates: [
    { id: 'c1', name: 'Alice' },
    { id: 'c2', name: 'Bob' },
  ],
}

async function renderDetail(election) {
  getElectionDetails.mockResolvedValue(election)
  getEligibleVoters.mockResolvedValue([])
  getVoteHistory.mockResolvedValue([])

  render(
    <MemoryRouter
      initialEntries={[
        { pathname: '/election-detail', state: { electionId: 'e1', from: 'active', role: 'voter' } },
      ]}
    >
      <Routes>
        <Route path="/election-detail" element={<ElectionDetail />} />
      </Routes>
    </MemoryRouter>,
  )

  await screen.findByText('Election Details')
}

describe('ElectionDetail ballot configuration display', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('describes a multi ballot with its maximum selections', async () => {
    await renderDetail({ ...baseElection, ballot_type: 'multi', max_selections: 2 })

    expect(screen.getByText(/multiple choice/i)).toBeInTheDocument()
    expect(screen.getByText(/up to 2 selections/)).toBeInTheDocument()
  })

  it('describes a single ballot as single choice', async () => {
    await renderDetail({ ...baseElection, ballot_type: 'single', max_selections: 1 })

    expect(screen.getByText('Single choice')).toBeInTheDocument()
    expect(screen.queryByText(/up to/)).not.toBeInTheDocument()
  })
})
