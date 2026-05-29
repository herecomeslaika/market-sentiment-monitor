export function useApi() {
  const baseUrl = ''

  async function request(path, options = {}) {
    const resp = await fetch(baseUrl + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
    if (!resp.ok) throw new Error(`API ${resp.status}`)
    return resp.json()
  }

  return {
    get: (path) => request(path),
    post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
    put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
    del: (path) => request(path, { method: 'DELETE' }),
  }
}
