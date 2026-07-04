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

describe('Register role dropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('offers Voter and Organizer, not Student/Teacher', () => {
    renderRegister()
    expect(screen.getByRole('option', { name: 'Voter' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Organizer' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Student' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Teacher' })).not.toBeInTheDocument()
  })

  it('defaults the selected role to voter', () => {
    renderRegister()
    expect(screen.getByLabelText('Profile')).toHaveValue('voter')
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

  it('registers an organizer and redirects to the organizer dashboard', async () => {
    decodeJwt.mockReturnValue({ role: 'organizer' })

    renderRegister()
    fillCredentials()
    fireEvent.change(screen.getByLabelText('Profile'), { target: { value: 'organizer' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() =>
      expect(registerUser).toHaveBeenCalledWith(expect.objectContaining({ role: 'organizer' })),
    )
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/organizer-dashboard'))
  })
})
