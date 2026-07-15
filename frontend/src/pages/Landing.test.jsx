import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import Landing from './Landing.jsx'

function renderLanding() {
  render(
    <MemoryRouter>
      <Landing />
    </MemoryRouter>,
  )
}

describe('Landing page', () => {
  it('presents the project identity', () => {
    renderLanding()

    expect(
      screen.getByRole('heading', { name: 'Homomorphic Encryption E-Voting System' }),
    ).toBeInTheDocument()
    // Shown both as the hero eyebrow and in the footer.
    expect(screen.getAllByText('CSIT321 Final Year Project').length).toBeGreaterThanOrEqual(1)
    expect(
      screen.getByText('Homomorphic Encryption and its Applications to E-Voting'),
    ).toBeInTheDocument()
  })

  it('routes its call-to-action buttons to the existing login page', () => {
    renderLanding()

    const loginLinks = screen
      .getAllByRole('link')
      .filter((link) => ['Get Started', 'Login'].includes(link.textContent.trim()))

    expect(loginLinks.length).toBeGreaterThanOrEqual(2)
    for (const link of loginLinks) {
      expect(link).toHaveAttribute('href', '/login')
    }
  })

  it('offers a route to register an account', () => {
    renderLanding()

    expect(screen.getByRole('link', { name: 'Create Account' })).toHaveAttribute('href', '/register')
  })

  it('explains the project, the encryption privacy concept, features, roles, tech and team', () => {
    renderLanding()

    expect(screen.getByRole('heading', { name: 'About The Project' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'How Homomorphic Encryption Protects Your Vote' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Main Features' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'User Roles' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Technology Stack' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Project Team' })).toBeInTheDocument()

    // The privacy story must state that ballots are tallied without being decrypted.
    expect(screen.getByText(/without decrypting a single ballot/i)).toBeInTheDocument()
  })

  it('names the three user roles using the role names the app itself uses', () => {
    renderLanding()

    expect(screen.getByRole('heading', { name: 'Voter (Student)' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Organizer (Teacher)' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'System Admin' })).toBeInTheDocument()
  })

  it('lists the technology stack and the project team', () => {
    renderLanding()

    for (const tech of ['React', 'FastAPI', 'PostgreSQL', 'Homomorphic Encryption']) {
      expect(screen.getByText(tech)).toBeInTheDocument()
    }

    expect(screen.getByRole('heading', { name: 'Teddy Kwok' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Merrick' })).toBeInTheDocument()
  })
})
