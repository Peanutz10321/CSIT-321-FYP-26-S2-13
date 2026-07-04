import { describe, it, expect, vi, beforeEach } from 'vitest'

import { addElectionVoter, createElection, decodeJwt } from './api.js'

function mockFetchOnce(responseObj = {}) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: 'OK',
    text: async () => JSON.stringify(responseObj),
  })
}

function lastRequestBody() {
  const calls = global.fetch.mock.calls
  const [, options] = calls[calls.length - 1]
  return JSON.parse(options.body)
}

describe('API payloads use the new e-voting terminology', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('addElectionVoter sends external_id (not institution_id)', async () => {
    mockFetchOnce({ id: 'ev-1' })

    await addElectionVoter('election-1', 'VOTER-001')

    const body = lastRequestBody()
    expect(body).toEqual({ external_id: 'VOTER-001' })
    expect(body).not.toHaveProperty('institution_id')
  })

  it('createElection forwards eligible_voter_external_ids (not voter_institution_ids)', async () => {
    mockFetchOnce({ id: 'e-1' })

    await createElection({
      title: 'Community Vote',
      candidates: [],
      eligible_voter_external_ids: ['VOTER-001', 'VOTER-002'],
    })

    const body = lastRequestBody()
    expect(body.eligible_voter_external_ids).toEqual(['VOTER-001', 'VOTER-002'])
    expect(body).not.toHaveProperty('voter_institution_ids')
  })
})

describe('decodeJwt', () => {
  it('extracts the role claim from the token', () => {
    const claims = { sub: 'user-1', role: 'organizer' }
    const encoded = btoa(JSON.stringify(claims))
    const token = `header.${encoded}.signature`

    expect(decodeJwt(token).role).toBe('organizer')
  })
})
