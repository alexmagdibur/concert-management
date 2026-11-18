import { createContext, useContext, useEffect, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api, setSession, type Session } from './api'
import { AsyncState, Form, required } from './ui'

const sessionKey = ['session']
const Current = createContext<Session | null>(null)
export function useSession() {
  const session = useContext(Current)
  if (!session) throw new Error('Сессия отсутствует')
  return session
}

export function Auth({ children }: { children: (logout: () => void, pending: boolean, error: unknown) => ReactNode }) {
  const cache = useQueryClient()
  const session = useQuery({
    queryKey: sessionKey,
    queryFn: async ({ signal }) => {
      try {
        const value = await api<Session>('/auth/me', 'GET', undefined, signal)
        setSession(value)
        return value
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          setSession(null)
          cache.removeQueries({ queryKey: ['api'] })
          return null
        }
        throw error
      }
    },
    staleTime: 30_000,
    retry: false,
  })

  function clearSession() {
    setSession(null)
    void cache.cancelQueries()
    cache.removeQueries({ queryKey: ['api'] })
    cache.setQueryData(sessionKey, null)
  }
  useEffect(() => {
    window.addEventListener('session-expired', clearSession)
    return () => window.removeEventListener('session-expired', clearSession)
  })
  const login = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Session>('/auth/login', 'POST', body),
    onSuccess: (value) => { setSession(value); cache.setQueryData(sessionKey, value) },
  })
  const logout = useMutation({
    mutationFn: () => api('/auth/logout', 'POST'),
    onSuccess: clearSession,
  })
  if (session.isPending || session.error) return <main><h1>Concert CRM</h1>
    <AsyncState pending={session.isPending} error={session.error} />
    {session.error && <button onClick={() => void session.refetch()}>Повторить</button>}
  </main>
  if (!session.data) return <main className="login"><h1>Concert CRM</h1>
    <h2>Вход</h2><Form fields={[
      required('login', 'Логин', { maxLength: 80 }),
      required('password', 'Пароль', { kind: 'password', maxLength: 256 }),
    ]} submit="Войти" onSubmit={(data) => login.mutate(data)} pending={login.isPending} error={login.error} />
  </main>
  return <Current.Provider value={session.data}>
    {children(() => logout.mutate(), logout.isPending, logout.error)}
  </Current.Provider>
}
