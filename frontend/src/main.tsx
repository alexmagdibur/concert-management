import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Auth, useSession } from './auth'
import { Catalog } from './catalog'
import { ConcertCard, ConcertList, NewConcert } from './concert'
import { Analytics, Reports } from './reports'
import { Admin } from './admin'
import { ErrorMessage } from './ui'
import './style.css'

const cache = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 15_000 } } })
const managerLinks = [
  ['/concerts', 'Концерты'], ['/venues', 'Площадки'], ['/counterparties', 'Контрагенты'],
  ['/categories', 'Категории операций'], ['/reports', 'Финансовый отчёт'], ['/analytics', 'Аналитика'],
]

function Shell({ logout, pending, error }: { logout: () => void; pending: boolean; error: unknown }) {
  const session = useSession()
  const manager = session.roles.includes('MANAGER')
  const admin = session.roles.includes('ADMIN')
  const first = manager ? '/concerts' : admin ? '/users' : '/no-access'
  return <div className="shell">
    <aside><strong>Concert CRM</strong><p>{session.login}</p>
      <nav aria-label="Основная навигация">
        {manager && managerLinks.map(([path, label]) => <NavLink key={path} to={path}>{label}</NavLink>)}
        {admin && <NavLink to="/users">Пользователи</NavLink>}
      </nav>
      <button onClick={logout} disabled={pending}>Выйти</button><ErrorMessage error={error} />
    </aside>
    <main><Routes>
      {manager && <>
        <Route path="/concerts" element={<ConcertList />} />
        <Route path="/concerts/new" element={<NewConcert />} />
        <Route path="/concerts/:id" element={<ConcertCard />} />
        <Route path="/venues" element={<Catalog key="venue" kind="venue" />} />
        <Route path="/counterparties" element={<Catalog key="party" kind="counterparty" />} />
        <Route path="/categories" element={<Catalog key="category" kind="finance_category" />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/analytics" element={<Analytics />} />
      </>}
      {admin && <Route path="/users" element={<Admin />} />}
      <Route path="/no-access" element={<p>Для этой учётной записи нет доступных разделов.</p>} />
      <Route path="*" element={<Navigate to={first} replace />} />
    </Routes></main>
  </div>
}

createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={cache}>
    <BrowserRouter><Auth>{(logout, pending, error) => <Shell logout={logout} pending={pending} error={error} />}</Auth></BrowserRouter>
  </QueryClientProvider>,
)
