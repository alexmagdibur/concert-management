import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useOptions, useRead, url, type CatalogRow, type Concert, type Page, type Responsible } from './api'
import { Audit, Command, SaveForm } from './actions'
import { Contracts, Engagements, Journal } from './concert-details'
import { AsyncState, ErrorMessage, Form, Pager, Status, displayMoney, options, required, showTime, statuses, withCurrent, type Field } from './ui'
import { Button, TableView } from './primitives'
import { ArrowUpRight, CalendarDays, Plus } from 'lucide-react'

export const concertStatuses: Record<Concert['status'], string> = {
  NEGOTIATING: statuses.NEGOTIATING, CONFIRMED: statuses.CONFIRMED,
  COMPLETED: 'Проведён', CANCELLED: 'Отменён',
}

export function ConcertList() {
  const [params, setParams] = useSearchParams()
  const filters = Object.fromEntries(['q', 'starts_from', 'starts_before', 'city', 'status']
    .map((key) => [key, params.get(key) ?? '']).filter(([, value]) => value))
  const [offset, setOffset] = useState(0)
  const list = useRead<Page<Concert>>(url('/concert', { ...filters, offset }))
  const rows = list.data?.items ?? []
  const statusCounts = Object.entries(concertStatuses).map(([code, label]) =>
    ({ code, label, count: rows.filter((row) => row.status === code).length }))
  return <><div className="page-heading" data-enter><div><h1>Концерты</h1><p>Расписание и состояние концертов</p></div>
      <Button asChild variant="default"><Link to="/concerts/new"><Plus size={17} aria-hidden="true" />Создать концерт</Link></Button>
    </div>
    {list.data && <div className="concert-overview">
      <section className="overview-count"><div><h2>Концерты в выборке</h2><span className="overview-icon"><CalendarDays size={18} aria-hidden="true" /></span></div>
        <strong>{list.data.total}</strong><small>{Object.keys(filters).length ? 'По выбранным фильтрам' : 'Всего в расписании'}</small>
      </section>
      <section className="overview-mix"><h2>Статусы на странице</h2>
        {rows.length > 0 ? <div className="status-bar" aria-hidden="true">
          {statusCounts.filter(({ count }) => count > 0).map(({ code, count }) => <div key={code} data-status={code} style={{ flex: count }} />)}
        </div> : <p className="mix-empty">На этой странице пока нет концертов.</p>}
        <ul className="status-legend">{statusCounts.map(({ code, label, count }) => <li key={code} data-status={code}>
          <span aria-hidden="true" /><span>{label}</span><strong>{count}</strong>
        </li>)}</ul>
      </section>
    </div>}
    <section className="results-card">
      <h2>Расписание</h2>
      <Form key={params.toString()} fields={[
        { key: 'q', label: 'Название концерта', maxLength: 200, initial: filters.q },
        { key: 'starts_from', label: 'Начало периода', kind: 'datetime-local', initial: filters.starts_from },
        { key: 'starts_before', label: 'Конец периода (до)', kind: 'datetime-local', initial: filters.starts_before },
        { key: 'city', label: 'Город площадки', maxLength: 100, initial: filters.city },
        { key: 'status', label: 'Состояние', kind: 'select', initial: filters.status, emptyLabel: 'Все', options: Object.entries(concertStatuses).map(([value, label]) => ({ value, label })) },
      ]} submit="Найти концерты" onSubmit={(data) => {
        setParams(Object.fromEntries(Object.entries(data).filter((value): value is [string, string] => typeof value[1] === 'string')))
        setOffset(0)
      }} onCancel={Object.keys(filters).length ? () => { setParams({}); setOffset(0) } : undefined} cancelLabel="Сбросить фильтры" />
      <AsyncState pending={list.isPending} error={list.error} />
      {list.data && <TableView label="Расписание концертов" rows={rows} rowKey={(row) => row.id} empty="Концерты не найдены"
        columns={[
          { title: 'Название', render: (row) => <Link className="table-link" to={`/concerts/${row.id}`}>{row.name}<ArrowUpRight size={14} aria-hidden="true" /></Link> },
          { title: 'Начало', render: (row) => showTime(row.starts_at) },
          { title: 'Состояние', render: (row) => <Status code={row.status} label={concertStatuses[row.status]} /> },
          { title: 'Бюджет', numeric: true, render: (row) => displayMoney(row.expense_budget) },
        ]} />}<Pager page={list.data} setOffset={setOffset} />
    </section>
  </>
}

function useConcertOptions() {
  const venues = useOptions<CatalogRow>('/venue')
  const parties = useOptions<CatalogRow>('/counterparty')
  const people = useOptions<Responsible>('/concert/responsibles')
  return { venues, parties, people, pending: venues.isPending || parties.isPending || people.isPending,
    error: venues.error || parties.error || people.error }
}

export function ConcertForm({ concert, onSaved }: { concert?: Concert; onSaved?: () => void }) {
  const navigate = useNavigate()
  const { venues, parties, people, pending, error } = useConcertOptions()
  const fields: Field[] = [
    required('name', 'Название', { maxLength: 200, initial: concert?.name }),
    required('starts_at', 'Начало', { kind: 'datetime-local', initial: concert?.starts_at }),
    required('ends_at', 'Окончание', { kind: 'datetime-local', initial: concert?.ends_at }),
    { key: 'venue_id', label: 'Площадка', kind: 'select', emptyLabel: 'Без площадки', initial: concert?.venue_id,
      options: withCurrent(options(venues.data, (v) => `${v.name} · ${v.city}`), concert?.venue_id) },
    { key: 'proposed_organizer_id', label: 'Организатор', kind: 'select', emptyLabel: 'Без организатора', initial: concert?.proposed_organizer_id,
      options: withCurrent(options(parties.data, (p) => p.name), concert?.proposed_organizer_id) },
    required('responsible_id', 'Ответственный', { kind: 'select', initial: concert?.responsible_id,
      options: withCurrent(options(people.data, (p) => p.full_name), concert?.responsible_id) }),
    required('expense_budget', 'Плановый бюджет', { kind: 'money', min: 0, max: 999999999999.99, initial: concert?.expense_budget }),
  ]
  if (pending || error) return <AsyncState pending={pending} error={error} />
  return <SaveForm<Concert> key={concert?.version} fields={fields} path={concert ? `/concert/${concert.id}` : '/concert'}
    method={concert ? 'PATCH' : 'POST'} submit={concert ? 'Сохранить концерт' : 'Создать концерт'}
    transform={concert ? (body) => ({ ...body, version: concert.version }) : undefined}
    onSaved={(row) => concert ? onSaved?.() : navigate(`/concerts/${row.id}`)}
    onCancel={concert ? onSaved : undefined} />
}

export function NewConcert() {
  return <><h1>Новый концерт</h1><section><ConcertForm /></section></>
}

export function ConcertCard() {
  const { id } = useParams()
  return <ConcertCardBody key={id} id={id} />
}

const detailTabs = [
  { key: 'overview', label: 'Общее' },
  { key: 'contracts', label: 'Договоры' },
  { key: 'engagements', label: 'Подрядчики' },
  { key: 'finance', label: 'Финансовый журнал' },
  { key: 'history', label: 'История' },
] as const

function ConcertCardBody({ id }: { id?: string }) {
  const detail = useRead<Concert>(`/concert/${id}`)
  const [editing, setEditing] = useState(false)
  const [params, setParams] = useSearchParams()
  const tab = detailTabs.find(({ key }) => key === params.get('tab'))?.key ?? 'overview'
  const row = detail.data
  const venue = useRead<CatalogRow>(row?.venue_id != null && tab === 'overview' ? `/venue/${row.venue_id}` : null)
  const organizer = useRead<CatalogRow>(row?.proposed_organizer_id != null && tab === 'overview' ? `/counterparty/${row.proposed_organizer_id}` : null)
  const people = useOptions<Responsible>(row && tab === 'overview' ? '/concert/responsibles' : null)
  const responsible = people.data?.find(({ id }) => id === row?.responsible_id)
  if (!row) return <AsyncState pending={detail.isPending} error={detail.error} />
  const root = `/concert/${row.id}`
  return <>
    <Link to="/concerts">К списку концертов</Link>
    <div className="page-heading" data-enter><h1>{row.name}</h1><p role="status"><Status code={row.status} label={concertStatuses[row.status]} /></p></div><ErrorMessage error={detail.error} />
    <div className="actions concert-tabs" role="group" aria-label="Разделы концерта">
      {detailTabs.map(({ key, label }) =>
        <Button type="button" key={key} aria-pressed={tab === key} onClick={() => setParams(key === 'overview' ? {} : { tab: key })}>{label}</Button>)}
      <Link to={`/reports?concert=${row.id}`}>Финансовый отчёт</Link>
    </div>
    {tab === 'overview' && <section>
      <h2>Основные данные</h2>
      <dl className="concert-facts">
        <div><dt>Начало</dt><dd>{showTime(row.starts_at)}</dd></div>
        <div><dt>Окончание</dt><dd>{showTime(row.ends_at)}</dd></div>
        <div><dt>Площадка</dt><dd>{venue.data ? `${venue.data.name} · ${venue.data.city}` : row.venue_id == null ? 'Не выбрана' : `#${row.venue_id}`}</dd></div>
        <div><dt>Организатор</dt><dd>{organizer.data?.name ?? (row.proposed_organizer_id == null ? 'Не выбран' : `#${row.proposed_organizer_id}`)}</dd></div>
        <div><dt>Ответственный</dt><dd>{responsible?.full_name ?? `#${row.responsible_id}`}</dd></div>
        <div><dt>Плановый бюджет</dt><dd>{displayMoney(row.expense_budget)}</dd></div>
      </dl>
      {row.cancel_reason && <p>Причина отмены: {row.cancel_reason}</p>}
      {editing ? <ConcertForm concert={row} onSaved={() => setEditing(false)} />
        : <Button type="button" onClick={() => setEditing(true)}>Изменить концерт</Button>}
      <div className="actions">
        {row.status === 'NEGOTIATING' && <Command label="Подтвердить концерт" path={root + '/confirm'} body={{ version: row.version }} />}
        {row.status === 'CONFIRMED' && <Command label="Отметить проведение" path={root + '/complete'} body={{ version: row.version }} />}
      </div>
      {['NEGOTIATING', 'CONFIRMED'].includes(row.status) && <details>
        <summary>Отмена концерта</summary>
        <SaveForm fields={[required('reason', 'Причина отмены', { kind: 'textarea' })]}
          path={root + '/cancel'} submit="Отменить концерт"
          transform={(body) => ({ ...body, version: row.version })} />
      </details>}
    </section>}
    {tab === 'contracts' && <Contracts concert={row} />}
    {tab === 'engagements' && <Engagements concert={row} />}
    {tab === 'finance' && <Journal concert={row} />}
    {tab === 'history' && <Audit kind="concert" id={row.id} standalone />}
  </>
}
