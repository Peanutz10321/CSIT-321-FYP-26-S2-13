import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import ManageUsers from './ManageUsers.jsx'
import { listUsers } from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  listUsers: vi.fn(),
}))

function renderManageUsers() {
  render(
    <MemoryRouter>
      <ManageUsers />
    </MemoryRouter>,
  )
}

describe('ManageUsers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listUsers.mockResolvedValue([
      { id: 'u1', username: 'alice', status: 'active' },
      { id: 'u2', username: 'bob', status: 'suspended' },
    ])
  })

  it('loads and shows the user list', async () => {
    renderManageUsers()

    await waitFor(() => expect(listUsers).toHaveBeenCalled())
    expect(await screen.findByText('alice')).toBeInTheDocument()
    expect(screen.getByText('bob')).toBeInTheDocument()
  })

  it('no longer offers an organizer-provisioning form', async () => {
    renderManageUsers()
    await waitFor(() => expect(listUsers).toHaveBeenCalled())

    expect(screen.queryByRole('button', { name: /create organizer/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Temporary password')).not.toBeInTheDocument()
  })

  it('searches the user list', async () => {
    renderManageUsers()
    await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByLabelText('Search users'), {
      target: { value: 'alice' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() =>
      expect(listUsers).toHaveBeenLastCalledWith({ search: 'alice' }),
    )
  })
})
