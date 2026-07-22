import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import ManageUsers from './ManageUsers.jsx'
import { listUsers, createOrganizer } from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  listUsers: vi.fn(),
  createOrganizer: vi.fn(),
}))

function renderManageUsers() {
  render(
    <MemoryRouter>
      <ManageUsers />
    </MemoryRouter>,
  )
}

function fillOrganizerForm() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'new_org' } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new_org@test.com' } })
  fireEvent.change(screen.getByLabelText('Temporary password'), {
    target: { value: 'password123' },
  })
}

describe('ManageUsers organizer provisioning', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listUsers.mockResolvedValue([])
    createOrganizer.mockResolvedValue({
      username: 'new_org',
      external_id: 'ORG-001',
      role: 'organizer',
    })
  })

  it('hides the create form until the admin opens it', async () => {
    renderManageUsers()
    await waitFor(() => expect(listUsers).toHaveBeenCalled())

    expect(screen.queryByLabelText('Temporary password')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Create Organizer' }))

    expect(screen.getByLabelText('Temporary password')).toBeInTheDocument()
  })

  it('submits the organizer details to the admin-only endpoint', async () => {
    renderManageUsers()
    await waitFor(() => expect(listUsers).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: 'Create Organizer' }))
    fillOrganizerForm()
    fireEvent.click(screen.getByRole('button', { name: 'Create Organizer' }))

    await waitFor(() =>
      expect(createOrganizer).toHaveBeenCalledWith(
        expect.objectContaining({
          username: 'new_org',
          email: 'new_org@test.com',
          password: 'password123',
        }),
      ),
    )
  })

  it('confirms creation and reloads the user list', async () => {
    renderManageUsers()
    await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: 'Create Organizer' }))
    fillOrganizerForm()
    fireEvent.click(screen.getByRole('button', { name: 'Create Organizer' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('ORG-001'))
    await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(2))
  })

  it('surfaces a backend rejection without claiming success', async () => {
    createOrganizer.mockRejectedValue(new Error('Account already exists.'))

    renderManageUsers()
    await waitFor(() => expect(listUsers).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: 'Create Organizer' }))
    fillOrganizerForm()
    fireEvent.click(screen.getByRole('button', { name: 'Create Organizer' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Account already exists.'),
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
