/**
 * Backend API base-URL configuration.
 *
 * The base URL comes from VITE_API_BASE_URL. Vite inlines that at build time, so
 * a production bundle carries whatever value was set when it was built — there is
 * no runtime override.
 *
 * Local development falls back to DEV_FALLBACK_BASE_URL so a fresh clone runs
 * without configuration. That fallback is deliberately NOT available in a
 * production build: shipping a bundle that quietly points at localhost is worse
 * than failing, because every request fails in the browser with no explanation.
 */

export const DEV_FALLBACK_BASE_URL = 'http://localhost:8000'

export const MISSING_BASE_URL_MESSAGE =
  'VITE_API_BASE_URL is not set. A production build requires it, for example ' +
  'VITE_API_BASE_URL=https://api.example.edu npm run build'

const API_BASE_URL_SHAPE =
  'It must be an absolute http(s) URL with no credentials, query string or ' +
  'fragment, for example https://api.example.edu or https://api.example.edu/v1'

/**
 * Strip trailing slashes so joining a path never produces a double slash.
 * '//' in a URL path is not equivalent to '/' for most routers.
 */
export function normaliseBaseUrl(baseUrl) {
  return String(baseUrl).trim().replace(/\/+$/, '')
}

/**
 * Validate a configured API base URL and return it normalised.
 *
 * This is the single source of truth for what a valid base URL is; both the
 * runtime resolver below and the Vite production build guard call it, so the
 * rules cannot drift apart. Rejects anything that is not exactly an absolute
 * http(s) origin with an optional base path: no other scheme (blocking
 * javascript:/ftp:/file:), no embedded credentials, no query or fragment, and
 * no malformed/out-of-range port (WHATWG `URL` rejects those outright).
 *
 * @param {unknown} rawUrl        the configured value
 * @param {object}  [options]
 * @param {boolean} [options.requireHttps]  demand https (production)
 * @returns {string} the normalised URL
 * @throws {Error} with an actionable message when the value is unusable
 */
export function validateApiBaseUrl(rawUrl, { requireHttps = false } = {}) {
  if (typeof rawUrl !== 'string' || rawUrl.trim() === '') {
    throw new Error(`VITE_API_BASE_URL is missing or blank. ${API_BASE_URL_SHAPE}`)
  }

  const trimmed = rawUrl.trim()

  let parsed
  try {
    parsed = new URL(trimmed)
  } catch {
    throw new Error(`VITE_API_BASE_URL is not a valid URL: "${trimmed}". ${API_BASE_URL_SHAPE}`)
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(
      `VITE_API_BASE_URL must use http or https, not "${parsed.protocol}". ${API_BASE_URL_SHAPE}`,
    )
  }

  if (parsed.username !== '' || parsed.password !== '') {
    throw new Error(
      `VITE_API_BASE_URL must not embed credentials (user:pass@). ${API_BASE_URL_SHAPE}`,
    )
  }

  if (parsed.search !== '' || parsed.hash !== '') {
    throw new Error(
      `VITE_API_BASE_URL must not contain a query string or fragment. ${API_BASE_URL_SHAPE}`,
    )
  }

  if (requireHttps && parsed.protocol !== 'https:') {
    throw new Error(
      `VITE_API_BASE_URL must use https in a production build, got "${trimmed}". ${API_BASE_URL_SHAPE}`,
    )
  }

  return normaliseBaseUrl(trimmed)
}

/**
 * Resolve the API base URL from a Vite-style env object.
 *
 * Missing or blank fails the production build loudly (rather than shipping a
 * page of failed requests) but falls back to localhost in development so a
 * fresh clone runs unconfigured. A value that IS provided is always validated,
 * in either mode — a malformed value is a mistake, not a reason to silently use
 * the fallback.
 */
export function resolveApiBaseUrl(env) {
  const configured = env?.VITE_API_BASE_URL
  const isProduction = Boolean(env?.PROD)
  const provided = typeof configured === 'string' ? configured.trim() : ''

  if (provided === '') {
    if (isProduction) {
      throw new Error(MISSING_BASE_URL_MESSAGE)
    }
    return DEV_FALLBACK_BASE_URL
  }

  return validateApiBaseUrl(configured, { requireHttps: isProduction })
}

/**
 * Join the base URL and a request path with exactly one separating slash.
 * Callers pass paths like '/auth/login'; tolerate a missing leading slash too.
 */
export function buildApiUrl(baseUrl, path) {
  const base = normaliseBaseUrl(baseUrl)
  const suffix = String(path ?? '')

  if (suffix === '') {
    return base
  }

  return suffix.startsWith('/') ? `${base}${suffix}` : `${base}/${suffix}`
}
