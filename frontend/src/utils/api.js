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
    const detail = payload?.detail
    const message = Array.isArray(detail)
      ? detail.map((e) => e.msg || e.message || JSON.stringify(e)).join('; ')
      : detail || payload?.message || response.statusText || 'Request failed'
    throw new Error(message)
  }

  return payload
}

async function registerUser(data) {
  return request('/auth/register', {
    method: 'POST',
    data,
  })
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

async function listUsers(search = {}) {
  const params = new URLSearchParams()

  if (search.search?.trim()) {
    params.set('search', search.search.trim())
  }

  if (search.role?.trim()) {
    params.set('role', search.role.trim())
  }

  if (search.status?.trim()) {
    params.set('status', search.status.trim())
  }

  const query = params.toString()
  return request(`/admin/users${query ? `?${query}` : ''}`)
}

// Organizer accounts cannot be self-registered; a system admin provisions them.
async function createOrganizer(data) {
  return request('/admin/users/organizers', {
    method: 'POST',
    data,
  })
}

async function getActiveElections(search = {}) {
  const params = new URLSearchParams()
  if (search.search?.trim()) params.set('search', search.search.trim())
  const query = params.toString()
  return request(`/elections/active${query ? `?${query}` : ''}`)
}

async function getElectionHistory(search = {}) {
  const params = new URLSearchParams()
  if (search.search?.trim()) params.set('search', search.search.trim())
  if (search.start_date) params.set('start_date', search.start_date)
  if (search.end_date) params.set('end_date', search.end_date)
  const query = params.toString()
  return request(`/elections/history${query ? `?${query}` : ''}`)
}

async function getElectionDrafts(search = {}) {
  const params = new URLSearchParams()
  if (search.search?.trim()) params.set('search', search.search.trim())
  const query = params.toString()
  return request(`/elections/drafts${query ? `?${query}` : ''}`)
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

async function addElectionVoter(electionId, externalId) {
  return addEligibleVoter(electionId, { external_id: externalId })
}

async function getElectionDetails(electionId) {
  return request(`/elections/${electionId}`)
}

async function getElectionResults(electionId) {
  return request(`/results/elections/${electionId}`)
}

async function updateElection(electionId, data) {
  return request(`/elections/${electionId}`, {
    method: 'PUT',
    data,
  })
}

async function extendElectionDeadline(electionId, newEndDate, title) {
  return request(`/elections/${electionId}/extend-deadline`, {
    method: 'PATCH',
    data: { new_end_date: newEndDate, ...(title !== undefined ? { title } : {}) },
  })
}

async function submitVote(data) {
  return request('/votes', {
    method: 'POST',
    data,
  })
}

async function getVoteHistory(search = {}) {
  const params = new URLSearchParams()
  if (search.search?.trim()) params.set('search', search.search.trim())
  if (search.start_date) params.set('start_date', search.start_date)
  if (search.end_date) params.set('end_date', search.end_date)
  const query = params.toString()
  return request(`/votes/history${query ? `?${query}` : ''}`)
}

async function getVoteDetails(voteId) {
  return request(`/votes/${voteId}`)
}

async function createElectionDraft(data) {
  return request('/elections/draft', {
    method: 'POST',
    data,
  })
}

async function createElection(data) {
  return request('/elections', {
    method: 'POST',
    data,
  })
}

async function getAdminStats() {
  return request('/admin/stats')
}

async function viewUser(userId) {
  return request(`/admin/users/${userId}`)
}

async function updateUserStatus(userId, status) {
  return request(`/admin/users/${userId}/status`, {
    method: 'PATCH',
    data: { status },
  })
}

function logout() {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
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
  } catch {
    return null
  }
}

export {
  BASE_URL,
  TOKEN_STORAGE_KEY,
  getAuthToken,
  request,
  registerUser,
  loginUser,
  getCurrentUser,
  updateCurrentUser,
  listUsers,
  createOrganizer,
  viewUser,
  getActiveElections,
  getElectionHistory,
  getVoteHistory,
  getVoteDetails,
  getElectionDrafts,
  getEligibleVoters,
  addEligibleVoter,
  addElectionVoter,
  getElectionDetails,
  getElectionResults,
  updateElection,
  createElectionDraft,
  createElection,
  extendElectionDeadline,
  submitVote,
  getAdminStats,
  updateUserStatus,
  logout,
  decodeJwt,
}
