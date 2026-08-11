/** Normalized API client errors for user-visible messaging. */

export class ApiClientError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.detail = detail
  }
}

function messageFromDetail(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim()
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0]
    if (typeof first === 'string' && first.trim()) {
      return first.trim()
    }
    if (first && typeof first === 'object' && 'msg' in first) {
      const msg = (first as { msg: unknown }).msg
      if (typeof msg === 'string' && msg.trim()) {
        return msg.trim()
      }
    }
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const msg = (detail as { message: unknown }).message
    if (typeof msg === 'string' && msg.trim()) {
      return msg.trim()
    }
  }
  return null
}

/** Parse a failed Response body into ApiClientError. */
export function parseApiError(status: number, bodyText: string): ApiClientError {
  const trimmed = bodyText.trim()
  if (!trimmed) {
    return new ApiClientError(status, `HTTP ${status}`)
  }
  try {
    const parsed: unknown = JSON.parse(trimmed)
    if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
      const detail = (parsed as { detail: unknown }).detail
      const message = messageFromDetail(detail) ?? `HTTP ${status}`
      return new ApiClientError(status, message, detail)
    }
    const message = messageFromDetail(parsed)
    if (message) {
      return new ApiClientError(status, message, parsed)
    }
  } catch {
    // not JSON
  }
  if (trimmed.length < 280 && !trimmed.startsWith('{')) {
    return new ApiClientError(status, trimmed)
  }
  return new ApiClientError(status, `HTTP ${status}`, trimmed)
}

export function formatErrorMessage(err: unknown): string {
  if (err instanceof ApiClientError) {
    return err.message
  }
  if (err instanceof Error && err.message.trim()) {
    const m = err.message.trim()
    if (m.startsWith('{')) {
      try {
        const parsed: unknown = JSON.parse(m)
        if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
          return (
            messageFromDetail((parsed as { detail: unknown }).detail) ?? 'Request failed'
          )
        }
      } catch {
        return 'Request failed'
      }
    }
    return m
  }
  return 'Request failed'
}
