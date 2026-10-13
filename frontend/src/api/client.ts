const BASE_URL = ''

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}

  // Only set Content-Type for JSON requests (not multipart/form-data)
  if (!(options?.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  const res = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers: { ...headers, ...options?.headers },
  })

  const json = await res.json() as { data?: T; error?: { code: string; message: string } }
  if (json.error) {
    throw new ApiError(json.error.code, json.error.message)
  }
  return json.data as T
}
