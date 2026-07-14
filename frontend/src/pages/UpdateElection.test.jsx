import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import UpdateElection from './UpdateElection.jsx'
import { getElectionDetails, updateElection, extendElectionDeadline } from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  getElectionDetails: vi.fn(),
  updateElection: vi.fn(),
  extendElectionDeadline: vi.fn(),
}))

const baseElection = {
  id: 'e1',
  title: 'Club Election',
  description: null,
  start_date: '2026-07-01T00:00:00',
  end_date: '2026-08-01T10:00:00',
  candidates: [
    { id: 'c1', name: 'A', description: null, photo_url: null, display_order: 1 },
    { id: 'c2', name: 'B', description: null, photo_url: null, display_order: 2 },
  ],
}

async function renderUpdate(election) {
  getElectionDetails.mockResolvedValue(election)
  render(
    <MemoryRouter initialEntries={['/update-election/e1']}>
      <Routes>
        <Route path="/update-election/:electionId" element={<UpdateElection />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByText('Update Election Details')
}

describe('UpdateElection ballot configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'alert').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the configuration read-only for an active election', async () => {
    await renderUpdate({ ...baseElection, status: 'active', ballot_type: 'multi', max_selections: 2 })

    expect(screen.getByText(/up to 2 selections/)).toBeInTheDocument()
    expect(screen.getByText(/locked once the election is active/i)).toBeInTheDocument()
    expect(screen.queryAllByRole('radio')).toHaveLength(0)
    expect(screen.queryByLabelText('Maximum selections')).not.toBeInTheDocument()
  })

  it('an active election save extends the deadline without ballot configuration', async () => {
    extendElectionDeadline.mockResolvedValue({})
    await renderUpdate({ ...baseElection, status: 'active', ballot_type: 'multi', max_selections: 2 })

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(extendElectionDeadline).toHaveBeenCalled())
    // The deadline endpoint only ever receives (id, new_end_date, title).
    expect(extendElectionDeadline).toHaveBeenCalledWith('e1', expect.any(String), 'Club Election')
    expect(updateElection).not.toHaveBeenCalled()
  })

  it('a draft can switch to multi and sends the configuration in the update payload', async () => {
    updateElection.mockResolvedValue({})
    await renderUpdate({ ...baseElection, status: 'draft', ballot_type: 'single', max_selections: 1 })

    expect(screen.getByRole('radio', { name: 'Single choice' })).toBeChecked()

    fireEvent.click(screen.getByRole('radio', { name: 'Multiple choice' }))
    fireEvent.change(screen.getByLabelText('Maximum selections'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(updateElection).toHaveBeenCalledWith(
        'e1',
        expect.objectContaining({
          ballot_type: 'multi',
          max_selections: 2,
          candidates: [
            expect.objectContaining({ name: 'A' }),
            expect.objectContaining({ name: 'B' }),
          ],
        }),
      ),
    )
  })

  it('switching a draft back to single always sends max_selections 1', async () => {
    updateElection.mockResolvedValue({})
    await renderUpdate({ ...baseElection, status: 'draft', ballot_type: 'multi', max_selections: 3 })

    expect(screen.getByRole('radio', { name: 'Multiple choice' })).toBeChecked()

    fireEvent.click(screen.getByRole('radio', { name: 'Single choice' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(updateElection).toHaveBeenCalledWith(
        'e1',
        expect.objectContaining({ ballot_type: 'single', max_selections: 1 }),
      ),
    )
  })

  it('a draft rejects an invalid max selections inline instead of saving', async () => {
    await renderUpdate({ ...baseElection, status: 'draft', ballot_type: 'multi', max_selections: 2 })

    fireEvent.change(screen.getByLabelText('Maximum selections'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Maximum selections must be a whole number of at least 1.',
    )
    expect(updateElection).not.toHaveBeenCalled()
  })
})
