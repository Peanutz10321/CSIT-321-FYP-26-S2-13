import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import VoteReceipt from './VoteReceipt.jsx'
import { getVoteDetails, getElectionDetails, getCurrentUser } from '../utils/api.js'

vi.mock('../utils/api.js', () => ({
  getVoteDetails: vi.fn(),
  getElectionDetails: vi.fn(),
  getCurrentUser: vi.fn(),
}))

// What the backend returns for a stored ballot: the plaintext choice is gone.
const storedVote = {
  id: 'v1',
  election_id: 'e1',
  receipt_code: 'RCPT-ABC123',
  submitted_at: '2026-07-01T10:00:00',
  bulletin_status: 'published',
  candidate_name: null,
  candidate_names: [],
  abstained: null,
}

const election = {
  id: 'e1',
  title: 'Club Election',
  organizer_username: 'org1',
  start_date: '2026-06-30T10:00:00',
  end_date: '2026-07-02T10:00:00',
  candidates: [
    { id: 'c1', name: 'Alice' },
    { id: 'c2', name: 'Bob' },
  ],
}

async function renderReceipt(state) {
  getCurrentUser.mockResolvedValue({ external_id: 'INST-1' })
  getVoteDetails.mockResolvedValue(storedVote)
  getElectionDetails.mockResolvedValue(election)

  render(
    <MemoryRouter initialEntries={[{ pathname: '/vote-receipt/v1', state }]}>
      <Routes>
        <Route path="/vote-receipt/:voteId" element={<VoteReceipt />} />
      </Routes>
    </MemoryRouter>,
  )

  await screen.findByText('Vote Details')
}

function selectionRow() {
  return screen.getByText('Your Selection:').closest('p')
}

describe('VoteReceipt privacy behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('immediate single receipt displays the selected candidate', async () => {
    await renderReceipt({
      submittedVote: { ...storedVote, candidate_name: 'Alice', candidate_names: ['Alice'], abstained: false },
    })

    expect(selectionRow()).toHaveTextContent('Alice')
    expect(selectionRow()).not.toHaveTextContent('Bob')
  })

  it('immediate multi receipt displays every selected candidate', async () => {
    await renderReceipt({
      submittedVote: { ...storedVote, candidate_name: null, candidate_names: ['Alice', 'Bob'], abstained: false },
    })

    expect(selectionRow()).toHaveTextContent('Alice, Bob')
  })

  it('immediate abstention receipt displays Abstained', async () => {
    await renderReceipt({
      submittedVote: { ...storedVote, candidate_name: null, candidate_names: [], abstained: true },
    })

    expect(selectionRow()).toHaveTextContent('Abstained')
  })

  it('a receipt opened from history shows the privacy-safe message', async () => {
    await renderReceipt(undefined)

    expect(
      screen.getByText(/not retained in plaintext and is only shown immediately after submission/i),
    ).toBeInTheDocument()
  })

  it('never lists the election candidates as the voter\'s choice', async () => {
    await renderReceipt(undefined)

    const row = selectionRow()
    expect(row).not.toHaveTextContent('Alice')
    expect(row).not.toHaveTextContent('Bob')
    expect(row).not.toHaveTextContent('Abstained')
  })

  it('ignores navigation state whose id does not match the route', async () => {
    await renderReceipt({
      submittedVote: { ...storedVote, id: 'other-vote', candidate_names: ['Alice'], abstained: false },
    })

    expect(selectionRow()).not.toHaveTextContent('Alice')
    expect(
      screen.getByText(/not retained in plaintext/i),
    ).toBeInTheDocument()
  })

  it('keeps showing the receipt code and safe metadata', async () => {
    await renderReceipt(undefined)

    expect(screen.getByText('RCPT-ABC123')).toBeInTheDocument()
    expect(screen.getByText('Club Election')).toBeInTheDocument()
  })
})
