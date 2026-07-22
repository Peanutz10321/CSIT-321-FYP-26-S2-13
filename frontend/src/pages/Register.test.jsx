import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import Register from './Register.jsx'
import { registerUser, loginUser, decodeJwt } from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  registerUser: vi.fn(),
  loginUser: vi.fn(),
  decodeJwt: vi.fn(),
}))

function renderRegister() {
  render(
    <MemoryRouter>
      <Register />
    </MemoryRouter>,
  )
}

function fillCredentials() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'newuser' } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@test.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw123456' } })
}

describe('Register role selection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('offers no role picker at all', () => {
    renderRegister()
    expect(screen.queryByLabelText('Profile')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('does not offer an Organizer option', () => {
    renderRegister()
    expect(screen.queryByRole('option', { name: 'Organizer' })).not.toBeInTheDocument()
  })

  it('tells the user organizer accounts are provisioned by an admin', () => {
    renderRegister()
    expect(screen.getByText(/provisioned by a system administrator/i)).toBeInTheDocument()
  })
})

describe('Register submit flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    registerUser.mockResolvedValue({})
    loginUser.mockResolvedValue({ access_token: 'fake.jwt.token' })
  })

  it('registers a voter and redirects to the voter dashboard', async () => {
    decodeJwt.mockReturnValue({ role: 'voter' })

    renderRegister()
    fillCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() =>
      expect(registerUser).toHaveBeenCalledWith(expect.objectContaining({ role: 'voter' })),
    )
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/voter-dashboard'))
  })

  it('always submits the voter role, never organizer', async () => {
    decodeJwt.mockReturnValue({ role: 'voter' })

    renderRegister()
    fillCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() => expect(registerUser).toHaveBeenCalled())

    const payload = registerUser.mock.calls[0][0]
    expect(payload.role).toBe('voter')
    expect(payload.role).not.toBe('organizer')
  })
})
