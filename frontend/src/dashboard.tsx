import { useState } from 'react'
import { ArrowDownLeft, ArrowUpRight, CalendarDays, ChevronLeft, ChevronRight, CircleDollarSign, Plus, Wallet } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useOptions, useRead, url, type Concert } from './api'
import { concertStatuses } from './concert'
import { Button, TableView } from './primitives'
import { AsyncState, Form, displayMoney, required, today } from './ui'

type Totals = { income: string; expenses: string; net: string }
type Month = Totals & { month: string }
type Summary = Totals & { upcoming_count: number; months: Month[] }
type Range = { date_from: string; date_to: string }

const monthName = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' })
const shortMonth = new Intl.DateTimeFormat('ru-RU', { month: 'short', year: '2-digit', timeZone: 'UTC' })
const dayTime = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' })
const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const metrics = [
  { key: 'income', label: 'Поступления', Icon: ArrowDownLeft },
  { key: 'expenses', label: 'Расходы', Icon: ArrowUpRight },
  { key: 'net', label: 'Денежный результат', Icon: Wallet },
] as const

function initialRange(): Range {
  const end = today()
  const [year, month] = end.split('-').map(Number)
  const first = new Date(Date.UTC(year, month - 6, 1))
  return { date_from: first.toISOString().slice(0, 10), date_to: end }
}

function chartMonths(months: Month[], range: Range): Month[] {
  const index = new Map(months.map((month) => [month.month, month]))
  const cursor = new Date(`${range.date_from.slice(0, 7)}-01T00:00:00Z`)
  const end = Date.parse(range.date_to)
  const result: Month[] = []
  while (cursor.getTime() <= end) {
    const month = cursor.toISOString().slice(0, 10)
    result.push(index.get(month) ?? { month, income: '0.00', expenses: '0.00', net: '0.00' })
    cursor.setUTCMonth(cursor.getUTCMonth() + 1)
  }
  return result
}

function FinanceChart({ months }: { months: Month[] }) {
  const values = months.flatMap((month) => metrics.map(({ key }) => Number(month[key])))
  const positive = Math.max(0, ...values)
  const negative = -Math.min(0, ...values)
  const span = positive + negative || 1
  const baseline = (positive || (!negative ? 1 : 0)) / span * 100
  return <>
    <ul className="chart-legend">{metrics.map(({ key, label }) => <li key={key} data-series={key}>{label}</li>)}</ul>
    <div className="chart-scroll">
      <div className="finance-chart" role="img" aria-label="График поступлений, расходов и денежного результата по месяцам. Точные суммы приведены в таблице.">
        {months.map((month) => <div key={month.month} className="chart-month" style={{ minWidth: months.length > 7 ? 60 : 46 }}>
          <div className="chart-plot">
            <div className="chart-zero" style={{ top: `${baseline}%` }} />
            {metrics.map(({ key, label }) => {
              const amount = Number(month[key])
              const size = Math.abs(amount) / span * 100
              return <div key={key} className="chart-bar-slot">
                <div className="chart-bar" data-series={key} title={`${label}: ${displayMoney(month[key])}`}
                  style={{ height: `${size}%`, top: `${amount >= 0 ? baseline - size : baseline}%` }} />
              </div>
            })}
          </div>
          <span>{shortMonth.format(new Date(month.month))}</span>
        </div>)}
      </div>
    </div>
    <details className="chart-data"><summary>Точные суммы по месяцам</summary>
      <TableView label="Финансовые показатели по месяцам" rows={months} rowKey={(month) => month.month} columns={[
        { title: 'Месяц', render: (month) => shortMonth.format(new Date(month.month)) },
        ...metrics.map(({ key, label }) => ({ title: label, numeric: true, render: (month: Month) => displayMoney(month[key]) })),
      ]} />
    </details>
  </>
}

function Calendar() {
  const [month, setMonth] = useState(() => {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth(), 1)
  })
  const [status, setStatus] = useState('')
  const year = month.getFullYear()
  const index = month.getMonth()
  const next = new Date(year, index + 1, 1)
  const concerts = useOptions<Concert>(url('/concert', {
    starts_from: month.toISOString(), starts_before: next.toISOString(), status,
  }))
  const byDay = new Map<number, Concert[]>()
  for (const row of concerts.data ?? []) {
    const day = new Date(row.starts_at).getDate()
    const rows = byDay.get(day) ?? []
    rows.push(row)
    byDay.set(day, rows)
  }
  const first = (month.getDay() + 6) % 7
  const days = new Date(year, index + 1, 0).getDate()
  const current = new Date()
  return <section aria-label="Календарь выступлений">
    <div className="panel-heading">
      <h2>Календарь выступлений</h2>
      <label>Состояние<select className="ui-field" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">Все состояния</option>
        {Object.entries(concertStatuses).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
      </select></label>
    </div>
    <div className="calendar-controls">
      <Button type="button" size="icon" aria-label="Предыдущий месяц" onClick={() => setMonth(new Date(year, index - 1, 1))}><ChevronLeft size={17} /></Button>
      <strong aria-live="polite">{monthName.format(month)}</strong>
      <Button type="button" size="icon" aria-label="Следующий месяц" onClick={() => setMonth(next)}><ChevronRight size={17} /></Button>
      <input className="ui-field calendar-month-input" type="month" aria-label="Перейти к месяцу"
        value={`${year}-${String(index + 1).padStart(2, '0')}`} onChange={(event) => {
          if (!event.target.value) return
          setMonth(new Date(`${event.target.value}-01T00:00:00`))
        }} />
    </div>
    <AsyncState pending={concerts.isPending} error={concerts.error} />
    {concerts.data?.length === 0 && <p className="panel-empty">В этом месяце нет концертов по выбранному фильтру.</p>}
    <div className="calendar-grid">
      {weekdays.map((day) => <div className="calendar-weekday" key={day} aria-hidden="true">{day}</div>)}
      {Array.from({ length: first }, (_, day) => <div className="calendar-gap" aria-hidden="true" key={`gap-${day}`} />)}
      {Array.from({ length: days }, (_, i) => {
        const day = i + 1
        const events = byDay.get(day)
        const isToday = year === current.getFullYear() && index === current.getMonth() && day === current.getDate()
        return <div className="calendar-day" data-has-events={Boolean(events)} key={day}>
          <time className="calendar-date" dateTime={`${year}-${String(index + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`}
            aria-current={isToday ? 'date' : undefined}>{day}</time>
          {events?.map((row) => <Link className="calendar-event" data-status={row.status} key={row.id} to={`/concerts/${row.id}`}
            title={concertStatuses[row.status]} aria-label={`${row.name}, ${dayTime.format(new Date(row.starts_at))}, ${concertStatuses[row.status]}`}>
            <span>{dayTime.format(new Date(row.starts_at))}</span>{row.name}
          </Link>)}
        </div>
      })}
    </div>
  </section>
}

export function Dashboard() {
  const [range, setRange] = useState(initialRange)
  const summary = useRead<Summary>(url('/dashboard', range))
  const data = summary.data
  return <>
    <div className="page-heading" data-enter><h1>Главная</h1>
      <Button asChild variant="default"><Link to="/concerts/new"><Plus size={17} aria-hidden="true" />Создать концерт</Link></Button>
    </div>
    <section className="dashboard-finance" aria-label="Финансовая сводка">
      <div className="panel-heading"><h2>Финансовая сводка</h2>
        <Link className="table-link" to="/reports">К отчётам <ArrowUpRight size={15} aria-hidden="true" /></Link>
      </div>
      <Form fields={[
        required('date_from', 'Начало периода', { kind: 'date', initial: range.date_from }),
        required('date_to', 'Конец периода', { kind: 'date', initial: range.date_to }),
      ]} submit="Применить период" onSubmit={(body) => setRange(body as Range)} />
      <AsyncState pending={summary.isPending} error={summary.error} />
      {data && <>
        <div className="dashboard-metrics">
          <article className="metric-card"><CalendarDays size={18} aria-hidden="true" /><h3>Предстоящие концерты</h3>
            <strong data-testid="dashboard-upcoming">{data.upcoming_count}</strong><small>Все будущие даты</small>
          </article>
          {metrics.map(({ key, label, Icon }) => <article className="metric-card" data-series={key} key={key}>
            <Icon size={18} aria-hidden="true" /><h3>{label}</h3><strong data-testid={`dashboard-${key}`}>{displayMoney(data[key])}</strong>
            <small>За выбранный период</small>
          </article>)}
        </div>
        <div className="panel-heading chart-heading"><CircleDollarSign size={19} aria-hidden="true" /><h3>Динамика по месяцам</h3></div>
        {data.months.length > 0 ? <FinanceChart months={chartMonths(data.months, range)} />
          : <p className="panel-empty">За выбранный период нет учтённых операций.</p>}
      </>}
    </section>
    <Calendar />
  </>
}
