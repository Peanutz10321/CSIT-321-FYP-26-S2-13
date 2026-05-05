const BASE_URL = 'http://localhost:8000'
const TOKEN_STORAGE_KEY = 'authToken'

function getAuthToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY)
}

function getHeaders(isJson = true) {
  const headers = {}

  if (isJson) {
    headers['Content-Type'] = 'application/json'
  }

  const token = getAuthToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  return headers
}

async function request(path, options = {}) {
  const { method = 'GET', data, headers = {}, ...rest } = options
  const url = `${BASE_URL}${path}`

  const response = await fetch(url, {
    method,
    headers: {
      ...getHeaders(Boolean(data)),
      ...headers,
    },
    body: data ? JSON.stringify(data) : undefined,
    ...rest,
  })

  const text = await response.text()
  const payload = text ? JSON.parse(text) : null

  if (!response.ok) {
    const message = payload?.detail || payload?.message || response.statusText || 'Request failed'
    throw new Error(message)
  }

  return payload
}

async function loginUser(email, password) {
  return request('/auth/login', {
    method: 'POST',
    data: { email, password },
  })
}

async function getCurrentUser() {
  return request('/users/me')
}

async function updateCurrentUser(data) {
  return request('/users/me', {
    method: 'PUT',
    data,
  })
}

async function getAdminUsers() {
  return request('/admin/users')
}

async function getActiveElections() {
  return request('/elections/active')
}

async function getElectionHistory() {
  return request('/elections/history')
}

async function getElectionDrafts() {
  return request('/elections/drafts')
}

async function getEligibleVoters(electionId) {
  return request(`/elections/${electionId}/voters`)
}

async function addEligibleVoter(electionId, data) {
  return request(`/elections/${electionId}/voters`, {
    method: 'POST',
    data,
  })
}

async function addElectionVoter(electionId, institutionId) {
  return addEligibleVoter(electionId, { institution_id: institutionId })
}

async function getElectionDetails(electionId) {
  return request(`/elections/${electionId}`)
}

async function updateElection(electionId, data) {
  return request(`/elections/${electionId}`, {
    method: 'PUT',
    data,
  })
}

async function activateElection(electionId) {
  return request(`/elections/${electionId}/activate`, {
    method: 'PATCH',
  })
}

async function submitVote(data) {
  return request('/votes', {
    method: 'POST',
    data,
  })
}

async function getVoteHistory() {
  return request('/votes/history')
}

async function getVoteDetails(voteId) {
  return request(`/votes/${voteId}`)
}

async function createElectionDraft(data) {
  return request('/elections', {
    method: 'POST',
    data,
  })
}

function decodeJwt(token) {
  if (!token) return null
  const parts = token.split('.')
  if (parts.length !== 3) return null

  const payload = parts[1]
  const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
  const decoded = atob(padded)

  try {
    return JSON.parse(decoded)
  } catch (error) {
    return null
  }
}

export {
  BASE_URL,
  TOKEN_STORAGE_KEY,
  getAuthToken,
  request,
  loginUser,
  getCurrentUser,
  updateCurrentUser,
  getAdminUsers,
  getActiveElections,
  getElectionHistory,
  getVoteHistory,
  getVoteDetails,
  getElectionDrafts,
  getEligibleVoters,
  addEligibleVoter,
  addElectionVoter,
  getElectionDetails,
  updateElection,
  createElectionDraft,
  activateElection,
  submitVote,
  decodeJwt,
}
