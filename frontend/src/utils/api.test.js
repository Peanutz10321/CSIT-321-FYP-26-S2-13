import { describe, it, expect, vi, beforeEach } from 'vitest'

import {
  BASE_URL,
  activateElection,
  addElectionVoter,
  createElection,
  createElectionDraft,
  decodeJwt,
  submitVote,
  updateElection,
} from './api.js'

function mockFetchOnce(responseObj = {}) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: 'OK',
    text: async () => JSON.stringify(responseObj),
  })
}

function lastRequest() {
  const calls = globalThis.fetch.mock.calls
  const [url, options] = calls[calls.length - 1]
  return { url, options }
}

function lastRequestBody() {
  return JSON.parse(lastRequest().options.body)
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

describe('core POST endpoints use the canonical backend paths', () => {
  // The backend registers these two routes as `@router.post("/")` under a prefix,
  // so the only paths it serves are `/votes/` and `/elections/`. Calling them
  // without the trailing slash earns a 307 whose Location is built from the ASGI
  // scheme — which is `http` behind a TLS-terminating proxy, so the browser blocks
  // the redirect as mixed content and the request never lands. These assertions
  // pin the exact URL, because a redirect that "works" in local HTTP would
  // otherwise hide the break until deployment.
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('submitVote posts to /votes/ with the ballot payload', async () => {
    mockFetchOnce({ id: 'ballot-1' })

    const payload = {
      election_id: 'election-1',
      candidate_ids: ['candidate-1', 'candidate-2'],
    }
    await submitVote(payload)

    const { url, options } = lastRequest()
    expect(url).toBe(`${BASE_URL}/votes/`)
    expect(url).not.toMatch(/\/votes$/)
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual(payload)
  })

  it('createElection posts to /elections/ with the election payload', async () => {
    mockFetchOnce({ id: 'e-1' })

    const payload = {
      title: 'Community Vote',
      candidates: [{ name: 'Candidate A' }],
      eligible_voter_external_ids: ['VOTER-001'],
    }
    await createElection(payload)

    const { url, options } = lastRequest()
    expect(url).toBe(`${BASE_URL}/elections/`)
    expect(url).not.toMatch(/\/elections$/)
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual(payload)
  })
})

describe('the draft lifecycle hits the existing election routes', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('createElectionDraft keeps its name and still posts to /elections/draft', async () => {
    mockFetchOnce({ id: 'draft-1' })

    const payload = {
      title: 'Draft Vote',
      candidates: [{ name: 'Candidate A' }],
      eligible_voter_external_ids: ['VOTER-001'],
    }
    const draft = await createElectionDraft(payload)

    const { url, options } = lastRequest()
    expect(url).toBe(`${BASE_URL}/elections/draft`)
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual(payload)
    expect(draft.id).toBe('draft-1')
  })

  it('updateElection PUTs the draft payload to the election it names', async () => {
    mockFetchOnce({ id: 'draft-1' })

    await updateElection('draft-1', { title: 'Renamed', eligible_voter_external_ids: ['VOTER-002'] })

    const { url, options } = lastRequest()
    expect(url).toBe(`${BASE_URL}/elections/draft-1`)
    expect(options.method).toBe('PUT')
    expect(JSON.parse(options.body).eligible_voter_external_ids).toEqual(['VOTER-002'])
  })

  it('activateElection PATCHes the existing activate route with no body', async () => {
    mockFetchOnce({ id: 'draft-1', status: 'active' })

    await activateElection('draft-1')

    const { url, options } = lastRequest()
    expect(url).toBe(`${BASE_URL}/elections/draft-1/activate`)
    expect(options.method).toBe('PATCH')
    expect(options.body).toBeUndefined()
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
