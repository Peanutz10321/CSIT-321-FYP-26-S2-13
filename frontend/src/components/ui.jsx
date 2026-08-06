import { useEffect, useState } from 'react'

// Internal app UI kit — the shared visual pattern for signed-in pages.
//
// It matches the public Landing/Login/Register language: a slate-950 canvas,
// slate-900/60 cards with slate-800 borders, blue primary actions, and
// consistent headers, spacing, focus states, and loading/empty/error states.
//
// The Voter pages are the first consumers and act as the reference; Organizer
// and Admin pages can adopt these same primitives later for one consistent app.

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950'

// ---------------------------------------------------------------------------
// Icons (inline SVG — no assets, matches the landing brand)
// ---------------------------------------------------------------------------

export function LockIcon({ className = 'h-4 w-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
      <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" />
    </svg>
  )
}

export function CheckIcon({ className = 'h-4 w-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true">
      <path d="M4 12.5l5 5 11-11" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export function PageShell({ children, width = 'max-w-5xl', className = '' }) {
  return (
    <div className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100 sm:py-10">
      <div className={`mx-auto ${width} space-y-6 sm:space-y-8 ${className}`}>{children}</div>
    </div>
  )
}

export function PageHeader({ eyebrow, title, subtitle, actions, className = '' }) {
  return (
    <div className={`flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between ${className}`}>
      <div className="min-w-0">
        {eyebrow && (
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-400">{eyebrow}</p>
        )}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-100 sm:text-3xl">
          {title}
        </h1>
        {subtitle && <p className="mt-2 max-w-2xl text-sm text-slate-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </div>
  )
}

export function Card({ as: As = 'div', className = '', padded = true, children, ...props }) {
  return (
    <As
      className={`rounded-2xl border border-slate-800 bg-slate-900/60 shadow-lg shadow-slate-950/40 ${
        padded ? 'p-6 sm:p-7' : ''
      } ${className}`}
      {...props}
    >
      {children}
    </As>
  )
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

const BUTTON_SIZES = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-5 py-2.5 text-sm',
  lg: 'px-6 py-3 text-base',
}

const BUTTON_VARIANTS = {
  primary: 'bg-blue-600 text-white hover:bg-blue-500',
  secondary: 'border border-slate-700 bg-slate-900/60 text-slate-100 hover:border-blue-400 hover:text-blue-300',
  subtle: 'border border-slate-800 bg-slate-800/60 text-slate-200 hover:bg-slate-800',
  danger: 'bg-rose-600 text-white hover:bg-rose-500',
  success: 'bg-emerald-600 text-white hover:bg-emerald-500',
}

export function Button({
  as: As = 'button',
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  className = '',
  type,
  children,
  ...props
}) {
  const classes = `inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition ${focusRing} disabled:cursor-not-allowed disabled:opacity-60 ${
    BUTTON_SIZES[size]
  } ${BUTTON_VARIANTS[variant]} ${fullWidth ? 'w-full' : ''} ${className}`

  if (As === 'button') {
    return (
      <button type={type || 'button'} className={classes} {...props}>
        {children}
      </button>
    )
  }
  return (
    <As className={classes} {...props}>
      {children}
    </As>
  )
}

// ---------------------------------------------------------------------------
// Forms
// ---------------------------------------------------------------------------

export function Input({ className = '', ...props }) {
  return (
    <input
      className={`block w-full rounded-lg border border-slate-700 bg-slate-950/60 px-4 py-2.5 text-slate-100 placeholder-slate-500 transition focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 ${className}`}
      {...props}
    />
  )
}

export function Textarea({ className = '', ...props }) {
  return (
    <textarea
      className={`block w-full rounded-lg border border-slate-700 bg-slate-950/60 px-4 py-2.5 text-slate-100 placeholder-slate-500 transition focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 ${className}`}
      {...props}
    />
  )
}

// A select-only combobox: a text box that filters a list of allowed values.
//
// Typed text is a search term, never a value. `onChange` only ever fires with an
// exact member of `options`, or '' when the box is cleared, so a caller can treat
// it exactly like the <select> it replaces. Anything half-typed is discarded when
// the field loses focus.
export function Combobox({
  id,
  value,
  onChange,
  options,
  placeholder = 'Search…',
  disabled = false,
  emptyMessage = 'No matches',
  describedBy,
  // Half a row, so a sixth match is visibly cut off and the list reads as scrollable
  // rather than looking like it ends at five.
  visibleRows = 5.5,
}) {
  // The search term while one is being typed, and null the rest of the time. Null
  // means "show the committed value", so the box follows `value` for free when the
  // selection is changed from outside — by a reset, or by loading another record —
  // with no state to keep in sync.
  const [search, setSearch] = useState(null)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  const listId = `${id}-listbox`
  const optionId = (index) => `${id}-option-${index}`
  const text = search ?? value

  // An untouched selection lists everything, so reopening the box behaves like the
  // dropdown it replaces instead of filtering down to the one item already chosen.
  const needle = (search ?? '').trim().toLowerCase()
  const matches = needle
    ? options.filter((option) => option.toLowerCase().includes(needle))
    : options

  // Keeps the highlighted row visible when arrowing past the scroll edge. Guarded
  // because jsdom does not implement scrollIntoView.
  useEffect(() => {
    if (!open) return
    document.getElementById(optionId(activeIndex))?.scrollIntoView?.({ block: 'nearest' })
  }, [open, activeIndex]) // eslint-disable-line react-hooks/exhaustive-deps

  const commit = (option) => {
    setOpen(false)
    setActiveIndex(0)
    setSearch(null)
    // Re-picking the current value is not a change, matching how a <select> stays
    // silent when the already-selected option is chosen again.
    if (option !== value) onChange(option)
  }

  const handleChange = (event) => {
    setSearch(event.target.value)
    setActiveIndex(0)
    setOpen(true)
  }

  const handleBlur = () => {
    setOpen(false)
    setActiveIndex(0)
    // An emptied box clears the selection. Anything else left half-typed was only
    // ever a search term, so dropping it restores the committed value.
    if (search !== null && !search.trim() && value) onChange('')
    setSearch(null)
  }

  const handleKeyDown = (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (!open) {
        setOpen(true)
        return
      }
      setActiveIndex((index) => Math.min(index + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter') {
      if (open && matches[activeIndex]) {
        event.preventDefault()
        commit(matches[activeIndex])
      }
    } else if (event.key === 'Escape') {
      setOpen(false)
      setActiveIndex(0)
      setSearch(null)
    }
  }

  return (
    <div className="relative">
      <input
        id={id}
        type="text"
        role="combobox"
        autoComplete="off"
        value={text}
        placeholder={placeholder}
        disabled={disabled}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && matches.length ? optionId(activeIndex) : undefined}
        aria-describedby={describedBy}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={() => setOpen(true)}
        onBlur={handleBlur}
        className={`block w-full rounded-lg border border-slate-700 bg-slate-950/60 px-4 py-2.5 pr-10 text-slate-100 placeholder-slate-500 transition focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-60`}
      />
      <span
        className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-slate-500"
        aria-hidden="true"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>

      {open && (
        <ul
          id={listId}
          role="listbox"
          // The press must not blur the input before the click lands, or the
          // blur handler would revert the text and the choice would be lost.
          onMouseDown={(event) => event.preventDefault()}
          // A row is py-2 (1rem) around a text-sm line (1.25rem); the extra 0.5rem is
          // the list's own py-1. Set as a style rather than a Tailwind
          // class because the class name would have to be built at runtime, which
          // the JIT compiler cannot see.
          style={{ maxHeight: `calc(${visibleRows} * 2.25rem + 0.5rem)` }}
          className="absolute z-20 mt-1 w-full overflow-auto rounded-lg border border-slate-700 bg-slate-900 py-1 shadow-xl shadow-slate-950/60"
        >
          {matches.length === 0 ? (
            <li className="px-4 py-2 text-sm text-slate-500">{emptyMessage}</li>
          ) : (
            matches.map((option, index) => (
              <li
                key={option}
                id={optionId(index)}
                role="option"
                aria-selected={option === value}
                onClick={() => commit(option)}
                onMouseEnter={() => setActiveIndex(index)}
                className={`cursor-pointer px-4 py-2 text-sm ${
                  index === activeIndex ? 'bg-blue-600/20 text-blue-200' : 'text-slate-200'
                }`}
              >
                {option}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Status / feedback
// ---------------------------------------------------------------------------

const BADGE_TONES = {
  emerald: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  amber: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  rose: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
  blue: 'border-blue-500/30 bg-blue-500/10 text-blue-300',
  slate: 'border-slate-500/30 bg-slate-500/10 text-slate-300',
}

// Status is conveyed by the text label; the dot is decorative so colour is
// never the only signal.
export function StatusBadge({ tone = 'slate', children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        BADGE_TONES[tone] ?? BADGE_TONES.slate
      } ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {children}
    </span>
  )
}

export function LoadingState({ message = 'Loading…', className = '' }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-center justify-center gap-3 px-6 py-12 text-sm text-slate-400 ${className}`}
    >
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-slate-700 border-t-blue-400"
        aria-hidden="true"
      />
      {message}
    </div>
  )
}

export function EmptyState({ title = 'Nothing to show', message, icon = '∅', className = '' }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-2 px-6 py-12 text-center ${className}`}>
      <div
        className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-800 bg-slate-900 text-lg text-slate-500"
        aria-hidden="true"
      >
        {icon}
      </div>
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {message && <p className="max-w-sm text-sm text-slate-500">{message}</p>}
    </div>
  )
}

export function ErrorState({ message, onRetryLabel, onRetry, className = '' }) {
  return (
    <div
      role="alert"
      className={`rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 text-center text-sm text-rose-300 ${className}`}
    >
      <p>{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className={`mt-4 rounded-xl border border-rose-500/40 px-4 py-2 text-xs font-semibold text-rose-200 transition hover:bg-rose-500/10 ${focusRing}`}
        >
          {onRetryLabel || 'Try again'}
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Responsive list / table — reads as a table on desktop, stacked cards on mobile
// ---------------------------------------------------------------------------

export function ResponsiveListTable({
  primary,
  secondary,
  action,
  items,
  getKey,
  loading = false,
  error = null,
  emptyTitle = 'No records found.',
  emptyMessage,
  loadingMessage = 'Loading…',
}) {
  const gridCols = secondary
    ? 'sm:grid-cols-[minmax(0,2.2fr)_minmax(0,1.3fr)_auto]'
    : 'sm:grid-cols-[minmax(0,1fr)_auto]'

  return (
    <Card padded={false} className="overflow-hidden">
      <div
        className={`hidden gap-4 border-b border-slate-800 bg-slate-900/80 px-5 py-3 text-xs font-semibold uppercase tracking-wide text-slate-400 sm:grid ${gridCols}`}
      >
        <span>{primary.header}</span>
        {secondary && <span>{secondary.header}</span>}
        {action && <span className="text-right">View</span>}
      </div>

      <div className="divide-y divide-slate-800/70">
        {loading ? (
          <LoadingState message={loadingMessage} />
        ) : error ? (
          <div className="px-6 py-10 text-center text-sm text-rose-400">{error}</div>
        ) : items.length === 0 ? (
          <EmptyState title={emptyTitle} message={emptyMessage} />
        ) : (
          items.map((item) => (
            <div
              key={getKey(item)}
              className={`grid grid-cols-1 gap-2 px-5 py-4 text-sm text-slate-300 sm:items-center sm:gap-4 ${gridCols}`}
            >
              <div className="min-w-0 font-medium text-slate-100">{primary.cell(item)}</div>
              {secondary && (
                <div className="text-slate-300">
                  <span className="mr-1 text-xs uppercase tracking-wide text-slate-500 sm:hidden">
                    {secondary.header}:
                  </span>
                  {secondary.cell(item)}
                </div>
              )}
              {action && <div className="pt-1 sm:justify-self-end sm:pt-0">{action(item)}</div>}
            </div>
          ))
        )}
      </div>
    </Card>
  )
}
