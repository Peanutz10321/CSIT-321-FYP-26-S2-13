import { describe, it, expect } from 'vitest'

import {
  DEV_FALLBACK_BASE_URL,
  MISSING_BASE_URL_MESSAGE,
  buildApiUrl,
  normaliseBaseUrl,
  resolveApiBaseUrl,
  validateApiBaseUrl,
} from './apiConfig.js'

describe('validateApiBaseUrl', () => {
  it('accepts a plain HTTPS URL', () => {
    expect(validateApiBaseUrl('https://api.example.edu')).toBe('https://api.example.edu')
  })

  it('accepts an HTTPS URL with a port', () => {
    expect(validateApiBaseUrl('https://api.example.edu:8443')).toBe(
      'https://api.example.edu:8443',
    )
  })

  it('accepts an optional base path and strips a trailing slash', () => {
    expect(validateApiBaseUrl('https://api.example.edu/v1/')).toBe(
      'https://api.example.edu/v1',
    )
  })

  it('accepts http when https is not required (development)', () => {
    expect(validateApiBaseUrl('http://localhost:8000', { requireHttps: false })).toBe(
      'http://localhost:8000',
    )
  })

  it.each([undefined, null, '', '   '])('rejects a missing or blank value (%p)', (value) => {
    expect(() => validateApiBaseUrl(value)).toThrow(/VITE_API_BASE_URL/)
  })

  it('rejects a value that is not a URL', () => {
    expect(() => validateApiBaseUrl('not-a-url')).toThrow(/VITE_API_BASE_URL/)
  })

  it.each(['javascript:alert(1)', 'ftp://api.example.edu', 'file:///etc/passwd'])(
    'rejects a non-http(s) scheme (%s)',
    (value) => {
      expect(() => validateApiBaseUrl(value)).toThrow(/http/)
    },
  )

  it.each([
    'https://user:pass@api.example.edu',
    'https://user@api.example.edu',
  ])('rejects embedded credentials (%s)', (value) => {
    expect(() => validateApiBaseUrl(value)).toThrow(/credential/i)
  })

  it('rejects a malformed port', () => {
    expect(() => validateApiBaseUrl('https://api.example.edu:bad')).toThrow(
      /VITE_API_BASE_URL/,
    )
  })

  it('rejects an out-of-range port', () => {
    expect(() => validateApiBaseUrl('https://api.example.edu:99999')).toThrow(
      /VITE_API_BASE_URL/,
    )
  })

  it.each(['https://api.example.edu?token=abc', 'https://api.example.edu#frag'])(
    'rejects a query string or fragment (%s)',
    (value) => {
      expect(() => validateApiBaseUrl(value)).toThrow(/query|fragment/i)
    },
  )

  it('rejects http when https is required (production)', () => {
    expect(() => validateApiBaseUrl('http://api.example.edu', { requireHttps: true })).toThrow(
      /https/,
    )
  })

  it('accepts https when https is required (production)', () => {
    expect(
      validateApiBaseUrl('https://api.example.edu', { requireHttps: true }),
    ).toBe('https://api.example.edu')
  })
})

describe('resolveApiBaseUrl', () => {
  it('uses VITE_API_BASE_URL when configured', () => {
    expect(resolveApiBaseUrl({ VITE_API_BASE_URL: 'https://api.example.edu' })).toBe(
      'https://api.example.edu',
    )
  })

  it('strips a trailing slash from the configured value', () => {
    expect(resolveApiBaseUrl({ VITE_API_BASE_URL: 'https://api.example.edu/' })).toBe(
      'https://api.example.edu',
    )
  })

  it('strips repeated trailing slashes', () => {
    expect(resolveApiBaseUrl({ VITE_API_BASE_URL: 'https://api.example.edu///' })).toBe(
      'https://api.example.edu',
    )
  })

  it('ignores surrounding whitespace', () => {
    expect(resolveApiBaseUrl({ VITE_API_BASE_URL: '  https://api.example.edu  ' })).toBe(
      'https://api.example.edu',
    )
  })

  it('falls back to localhost in development', () => {
    expect(resolveApiBaseUrl({ PROD: false })).toBe(DEV_FALLBACK_BASE_URL)
  })

  it('falls back when the configured value is blank', () => {
    expect(resolveApiBaseUrl({ VITE_API_BASE_URL: '   ', PROD: false })).toBe(
      DEV_FALLBACK_BASE_URL,
    )
  })

  it('throws in a production build when unset', () => {
    expect(() => resolveApiBaseUrl({ PROD: true })).toThrow(MISSING_BASE_URL_MESSAGE)
  })

  it('throws in a production build when blank', () => {
    expect(() => resolveApiBaseUrl({ VITE_API_BASE_URL: '', PROD: true })).toThrow(
      MISSING_BASE_URL_MESSAGE,
    )
  })

  it('never falls back to localhost in a production build', () => {
    let resolved
    try {
      resolved = resolveApiBaseUrl({ PROD: true })
    } catch {
      resolved = 'threw'
    }
    expect(resolved).not.toBe(DEV_FALLBACK_BASE_URL)
  })

  it('accepts an explicit value in a production build', () => {
    expect(
      resolveApiBaseUrl({ VITE_API_BASE_URL: 'https://api.example.edu', PROD: true }),
    ).toBe('https://api.example.edu')
  })

  it('rejects a plain-HTTP value in a production build', () => {
    expect(() =>
      resolveApiBaseUrl({ VITE_API_BASE_URL: 'http://api.example.edu', PROD: true }),
    ).toThrow(/https/)
  })

  it('rejects a malformed value in a production build', () => {
    expect(() =>
      resolveApiBaseUrl({ VITE_API_BASE_URL: 'not-a-url', PROD: true }),
    ).toThrow(/VITE_API_BASE_URL/)
  })

  it('rejects a malformed value even in development (no silent fallback)', () => {
    expect(() =>
      resolveApiBaseUrl({ VITE_API_BASE_URL: 'not-a-url', PROD: false }),
    ).toThrow(/VITE_API_BASE_URL/)
  })

  it('allows a plain-HTTP value in development', () => {
    expect(
      resolveApiBaseUrl({ VITE_API_BASE_URL: 'http://localhost:8000', PROD: false }),
    ).toBe('http://localhost:8000')
  })
})

describe('normaliseBaseUrl', () => {
  it('leaves a clean URL untouched', () => {
    expect(normaliseBaseUrl('https://api.example.edu')).toBe('https://api.example.edu')
  })

  it('preserves a port', () => {
    expect(normaliseBaseUrl('http://localhost:8000/')).toBe('http://localhost:8000')
  })
})

describe('buildApiUrl', () => {
  it('joins base and path with a single slash', () => {
    expect(buildApiUrl('https://api.example.edu', '/auth/login')).toBe(
      'https://api.example.edu/auth/login',
    )
  })

  it('does not double the slash when the base has a trailing one', () => {
    expect(buildApiUrl('https://api.example.edu/', '/auth/login')).toBe(
      'https://api.example.edu/auth/login',
    )
  })

  it('adds the separator when the path has no leading slash', () => {
    expect(buildApiUrl('https://api.example.edu', 'auth/login')).toBe(
      'https://api.example.edu/auth/login',
    )
  })

  it('preserves query strings', () => {
    expect(buildApiUrl('https://api.example.edu', '/admin/users?role=voter')).toBe(
      'https://api.example.edu/admin/users?role=voter',
    )
  })

  it('returns the bare base for an empty path', () => {
    expect(buildApiUrl('https://api.example.edu', '')).toBe('https://api.example.edu')
  })
})
