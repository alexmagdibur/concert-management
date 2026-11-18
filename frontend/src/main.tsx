import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Auth, useSession } from './auth'
import { Catalog } from './catalog'
import { ConcertCard, ConcertList, NewConcert } from './concert'
import { Analytics, Reports } from './reports'
import { Admin } from './admin'
import { Profile } from './profile'
import { Dashboard } from './dashboard'
import { ErrorMessage } from './ui'
import { CalendarDays, ChartNoAxesCombined, ChevronRight, FileText, LogOut, MapPin, Menu, Monitor, Moon, Shield, Sun, Tags, UsersRound } from 'lucide-react'
import { Button } from './primitives'
import { LayoutDashboard } from 'lucide-react'
import { Wordmark } from './wordmark'
import '@fontsource-variable/inter'
import '@fontsource-variable/unbounded'
import './style.css'

const cache = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 15_000 } } })
const groups = [
  { title: 'Планирование', links: [
    { path: '/dashboard', label: 'Главная', Icon: LayoutDashboard },
    { path: '/concerts', label: 'Концерты', Icon: CalendarDays },
    { path: '/venues', label: 'Площадки', Icon: MapPin },
    { path: '/counterparties', label: 'Контрагенты', Icon: UsersRound },
  ] },
  { title: 'Финансы', links: [
    { path: '/categories', label: 'Категории операций', Icon: Tags },
    { path: '/reports', label: 'Финансовый отчёт', Icon: FileText },
    { path: '/analytics', label: 'Аналитика', Icon: ChartNoAxesCombined },
  ] },
]

type Theme = 'dark' | 'light' | 'system'
function Application() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem('concert-theme')
      if (saved === 'dark' || saved === 'light' || saved === 'system') return saved
    } catch { /* storage may be disabled */ }
    return 'dark'
  })
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('concert-theme', theme) } catch { /* storage may be disabled */ }
  }, [theme])
  return <Auth themeControl={<ThemeControl theme={theme} setTheme={setTheme} />}>
    {(logout, pending, error, passwordChanged) => <Shell logout={logout} pending={pending} error={error}
      passwordChanged={passwordChanged} theme={theme} setTheme={setTheme} />}
  </Auth>
}

function ThemeControl({ theme, setTheme }: { theme: Theme; setTheme: (value: Theme) => void }) {
  const Icon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor
  return <label className="theme-control"><Icon size={17} aria-hidden="true" />
    <select aria-label="Цветовая тема" value={theme} onChange={(event) => setTheme(event.target.value as Theme)}>
      <option value="dark">Тёмная</option><option value="light">Светлая</option><option value="system">Как в системе</option>
    </select>
  </label>
}

function Shell({ logout, pending, error, passwordChanged, theme, setTheme }: {
  logout: () => void; pending: boolean; error: unknown; passwordChanged: () => void;
  theme: Theme; setTheme: (value: Theme) => void
}) {
  const session = useSession()
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const manager = session.roles.includes('MANAGER')
  const admin = session.roles.includes('ADMIN')
  const first = manager ? '/dashboard' : admin ? '/users' : '/no-access'
  const navigation = [...(manager ? groups : []), ...(admin ? [{ title: 'Доступ', links: [{ path: '/users', label: 'Пользователи', Icon: Shield }] }] : [])]
  const active = navigation.flatMap(({ links }) => links).find(({ path }) => pathname === path || pathname.startsWith(path + '/'))
  const initials = session.login.slice(0, 2).toLocaleUpperCase('ru')
  return <div className="shell">
    <a href="#content" className="skip-link">К содержанию</a>
    <aside className={menuOpen ? 'sidebar sidebar-open' : 'sidebar'} id="navigation-panel">
      <NavLink className="brand" to={first} onClick={() => setMenuOpen(false)}>
        <Wordmark />
      </NavLink>
      <nav aria-label="Основная навигация">
        {navigation.map(({ title, links }) => <div className="nav-group" key={title}>
          <span className="nav-section">{title}</span>
          {links.map(({ path, label, Icon }) => <NavLink key={path} to={path} title={label} onClick={() => setMenuOpen(false)}>
            <span className="nav-icon"><Icon size={18} aria-hidden="true" /></span><span className="nav-label">{label}</span>
          </NavLink>)}
        </div>)}
      </nav>
      <NavLink to="/profile" aria-label="Мой профиль" title="Мой профиль" className="sidebar-bottom" onClick={() => setMenuOpen(false)}>
        <span className="avatar" aria-hidden="true">{initials}</span><div>
        <strong>{session.login}</strong><small>{admin && manager ? 'Менеджер · Администратор' : admin ? 'Администратор' : 'Менеджер'}</small>
      </div></NavLink>
    </aside>
    <div className="workspace min-w-0">
      <header className="topbar">
        <div className="breadcrumbs">
          <Button className="menu-toggle" type="button" size="icon" aria-label={menuOpen ? 'Закрыть меню' : 'Открыть меню'}
            aria-expanded={menuOpen} aria-controls="navigation-panel" onClick={() => setMenuOpen(!menuOpen)}><Menu size={18} /></Button>
          <NavLink to={first} className="compact-brand"><Wordmark /></NavLink>
          <span className="workspace-label">Мой кабинет</span><ChevronRight size={14} aria-hidden="true" />
          <strong>{pathname === '/profile' ? 'Профиль' : active?.label ?? 'Мой кабинет'}</strong>
        </div>
        <div className="top-actions"><ThemeControl theme={theme} setTheme={setTheme} />
          <Button type="button" onClick={logout} disabled={pending}><LogOut size={16} aria-hidden="true" />Выйти</Button>
        </div>
      </header>
      <main id="content" tabIndex={-1} className="app-frame"><ErrorMessage error={error} /><Routes>
      <Route path="/profile" element={<Profile onPasswordChanged={passwordChanged} />} />
      {manager && <>
        <Route path="/dashboard" element={<Dashboard />} />
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
  </div>
}

createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={cache}>
    <BrowserRouter><Application /></BrowserRouter>
  </QueryClientProvider>,
)
