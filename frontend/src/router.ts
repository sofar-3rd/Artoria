import { useEffect, useState } from 'react'

export type Route =
  | { page: 'chat' }
  | { page: 'kbs' }
  | { page: 'traces'; threadId: string | null }
  | { page: 'trace'; id: string }

export function parseRoute(pathname: string, search: string): Route {
  const detail = pathname.match(/^\/traces\/([^/]+)\/?$/)
  if (detail) return { page: 'trace', id: detail[1] }
  if (/^\/traces\/?$/.test(pathname)) {
    return { page: 'traces', threadId: new URLSearchParams(search).get('thread') }
  }
  if (/^\/kbs\/?$/.test(pathname)) return { page: 'kbs' }
  return { page: 'chat' }
}

export function navigate(to: string) {
  history.pushState(null, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function useRoute(): Route {
  const read = () => parseRoute(location.pathname, location.search)
  const [route, setRoute] = useState<Route>(read)
  useEffect(() => {
    const onChange = () => setRoute(read())
    window.addEventListener('popstate', onChange)
    return () => window.removeEventListener('popstate', onChange)
  }, [])
  return route
}
