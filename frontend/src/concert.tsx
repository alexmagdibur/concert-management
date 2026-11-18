import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useOptions, useRead, url, type CatalogRow, type Concert, type Page, type Responsible } from './api'
import { Audit, Command, SaveForm } from './actions'
import { Contracts, Engagements, Journal } from './concert-details'
import { AsyncState, ErrorMessage, Form, Pager, displayMoney, options, required, showTime, statuses, withCurrent, type Field } from './ui'

const concertStatuses: Record<Concert['status'], string> = {
  NEGOTIATING: statuses.NEGOTIATING, CONFIRMED: statuses.CONFIRMED,
  COMPLETED: 'Проведён', CANCELLED: 'Отменён',
}

export function ConcertList() {
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [offset, setOffset] = useState(0)
  const list = useRead<Page<Concert>>(url('/concert', { ...filters, offset }))
  return <><h1>Концерты</h1><Link to="/concerts/new">Создать концерт</Link>
    <section>
      <Form fields={[
        { key: 'starts_from', label: 'Начало периода', kind: 'datetime-local' },
        { key: 'starts_before', label: 'Конец периода (до)', kind: 'datetime-local' },
        { key: 'city', label: 'Город площадки', maxLength: 100 },
        { key: 'status', label: 'Состояние', kind: 'select', emptyLabel: 'Все', options: Object.entries(concertStatuses).map(([value, label]) => ({ value, label })) },
      ]} submit="Найти концерты" onSubmit={(data) => {
        setFilters(Object.fromEntries(Object.entries(data).filter((value): value is [string, string] => typeof value[1] === 'string')))
        setOffset(0)
      }} />
      <AsyncState pending={list.isPending} error={list.error} />
      <div className="table-scroll"><table><thead><tr><th>Название</th><th>Начало</th><th>Состояние</th><th>Бюджет</th></tr></thead>
        <tbody>{list.data?.items.map((row) => <tr key={row.id}><td><Link to={`/concerts/${row.id}`}>{row.name}</Link></td>
          <td>{showTime(row.starts_at)}</td><td>{concertStatuses[row.status]}</td><td>{displayMoney(row.expense_budget)}</td></tr>)}</tbody>
      </table></div><Pager page={list.data} setOffset={setOffset} />
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
  const detail = useRead<Concert>(`/concert/${id}`)
  const [editing, setEditing] = useState(false)
  const [tab, setTab] = useState('Общее')
  const row = detail.data
  if (!row) return <AsyncState pending={detail.isPending} error={detail.error} />
  const root = `/concert/${row.id}`
  return <>
    <Link to="/concerts">К списку концертов</Link>
    <h1>{row.name}</h1><p role="status">{concertStatuses[row.status]}</p><ErrorMessage error={detail.error} />
    <div className="actions" aria-label="Разделы концерта">
      {['Общее', 'Договоры', 'Подрядчики', 'Финансовый журнал'].map((name) =>
        <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name}</button>)}
      <Link to={`/reports?concert=${row.id}`}>Финансовый отчёт</Link>
    </div>
    {tab === 'Общее' && <><section>
      <p>{showTime(row.starts_at)} — {showTime(row.ends_at)}</p>
      <p>Плановый бюджет: {displayMoney(row.expense_budget)}</p>
      <p>Площадка: {row.venue_id == null ? 'не выбрана' : `#${row.venue_id}`} · Организатор: {row.proposed_organizer_id == null ? 'не выбран' : `#${row.proposed_organizer_id}`} · Ответственный #{row.responsible_id}</p>
      {row.cancel_reason && <p>Причина отмены: {row.cancel_reason}</p>}
      {editing ? <ConcertForm concert={row} onSaved={() => setEditing(false)} />
        : <button onClick={() => setEditing(true)}>Изменить концерт</button>}
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
    </section><Audit kind="concert" id={row.id} /></>}
    {tab === 'Договоры' && <Contracts concert={row} />}
    {tab === 'Подрядчики' && <Engagements concert={row} />}
    {tab === 'Финансовый журнал' && <Journal concert={row} />}
  </>
}
