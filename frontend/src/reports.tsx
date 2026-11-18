import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useOptions, useRead, url, type Concert, type Entry, type Page } from './api'
import { AsyncState, Form, Pager, displayMoney, options, required, showTime, today, type Field } from './ui'
import { TableView } from './primitives'

type Period = { date_from: string; date_to: string; as_of: string }
type Totals = { income: string; expenses: string; net: string }
type Report = Totals & {
  expense_budget: string; actual_expenses: string; budget_remaining: string;
  contracts: { contract_id: number; number: string; amount: string; net_paid: string; unpaid: string; overpaid: string }[];
  operations: Page<Entry>
}
type Rank = Totals & { concert_id: number; name: string; starts_at: string }
type Ranking = { count: number; best: Rank[]; worst: Rank[] }
type Forecast = {
  n: number; incomplete_count: number; message: string | null; reason: string | null;
  forecast: { expected_expenses: string; ci_lower: string; ci_upper: string; mean_ratio: string } | null
}
function periodFields(): Field[] {
  const current = today()
  return [
    required('date_from', 'Начало периода', { kind: 'date', initial: current.slice(0, 4) + '-01-01' }),
    required('date_to', 'Конец периода', { kind: 'date', initial: current }),
    required('as_of', 'Дата среза', { kind: 'date', initial: current }),
  ]
}
function MoneySummary({ totals }: { totals: Totals }) {
  return <dl>
    <dt>Поступления</dt><dd>{displayMoney(totals.income)}</dd>
    <dt>Расходы</dt><dd>{displayMoney(totals.expenses)}</dd>
    <dt>Денежный результат</dt><dd data-testid="net-result">{displayMoney(totals.net)}</dd>
  </dl>
}

export function Reports() {
  const [search] = useSearchParams()
  const [filter, setFilter] = useState<(Period & { concert: number }) | null>(null)
  const [offset, setOffset] = useState(0)
  const concerts = useOptions<Concert>('/concert')
  const report = useRead<Report>(filter ? url(`/concert/${filter.concert}/finance/report`, {
    date_from: filter.date_from, date_to: filter.date_to, as_of: filter.as_of, offset,
  }) : null)
  return <><h1>Финансовый отчёт</h1><section>
    <AsyncState pending={concerts.isPending} error={concerts.error} />
    {concerts.data && <Form fields={[
      required('concert', 'Концерт', { kind: 'select', initial: search.get('concert'), options: options(concerts.data, (item) => item.name) }),
      ...periodFields(),
    ]} submit="Сформировать отчёт" onSubmit={(body) => { setFilter(body as Period & { concert: number }); setOffset(0) }} />}
    {filter && <AsyncState pending={report.isPending} error={report.error} />}
    {filter && report.data && <>
      <h2>Итоги</h2><p>{filter.date_from} — {filter.date_to} · Срез {filter.as_of}</p>
      <MoneySummary totals={report.data} />
      <p>Плановый бюджет: {displayMoney(report.data.expense_budget)} · Фактические расходы: {displayMoney(report.data.actual_expenses)} · Остаток бюджета: {displayMoney(report.data.budget_remaining)}</p>
      <h2>Расчёты по договорам</h2>
      <TableView label="Расчёты по договорам" rows={report.data.contracts} rowKey={(row) => row.contract_id}
        empty="В отчёте нет договоров" columns={[
          { title: 'Договор', render: (row) => row.number },
          { title: 'Сумма', numeric: true, render: (row) => displayMoney(row.amount) },
          { title: 'Оплачено', numeric: true, render: (row) => displayMoney(row.net_paid) },
          { title: 'Остаток', numeric: true, render: (row) => displayMoney(row.unpaid) },
          { title: 'Переплата', numeric: true, render: (row) => displayMoney(row.overpaid) },
        ]} />
      <h2>Операции за период</h2>
      <TableView label="Операции за период" rows={report.data.operations.items} rowKey={(row) => row.id}
        empty="За выбранный период нет операций" columns={[
          { title: 'Дата', render: (row) => row.occurred_on },
          { title: 'Вид', render: (row) => row.direction === 'IN' ? 'Поступление' : 'Расход' },
          { title: 'Основание', render: (row) => <>{row.basis}{row.original_id != null && ` · возврат по #${row.original_id}`}</> },
          { title: 'Сумма', numeric: true, render: (row) => displayMoney(row.amount) },
        ]} />
      <Pager page={report.data.operations} setOffset={setOffset} />
    </>}
  </section></>
}

function RankList({ title, items, scale }: { title: string; items: Rank[]; scale: number }) {
  return <><h3>{title}</h3>{items.length === 0 ? <p>Нет проведённых концертов за период.</p> :
    <ol className="rank-list">{items.map((item) => {
      const value = Number(item.net)
      const width = Math.abs(value) / scale * 50
      return <li key={item.concert_id}>
        <div className="rank-label"><Link to={`/concerts/${item.concert_id}`}>{item.name}</Link><strong>{displayMoney(item.net)}</strong></div>
        <div className="rank-track" aria-hidden="true">
          <span data-series={value < 0 ? 'expenses' : 'income'} style={{ width: `${width}%`, left: `${value < 0 ? 50 - width : 50}%` }} />
        </div>
        <small>{showTime(item.starts_at)}</small>
      </li>
    })}</ol>}
  </>
}

function RankingChart({ ranking }: { ranking: Ranking }) {
  const scale = Math.max(...[...ranking.best, ...ranking.worst].map(({ net }) => Math.abs(Number(net)))) || 1
  return <div className="ranking-panels">
    <div><RankList title="Лучшие" items={ranking.best} scale={scale} /></div>
    <div><RankList title="Худшие" items={ranking.worst} scale={scale} /></div>
  </div>
}

function ForecastInterval({ estimate }: { estimate: NonNullable<Forecast['forecast']> }) {
  const from = Number(estimate.ci_lower)
  const to = Number(estimate.ci_upper)
  const point = to === from ? 50 : Math.min(100, Math.max(0, (Number(estimate.expected_expenses) - from) / (to - from) * 100))
  return <figure className="forecast-chart">
    <figcaption>95%-й доверительный интервал среднего</figcaption>
    <div className="forecast-amount"><small>Ожидаемые расходы</small><strong>{displayMoney(estimate.expected_expenses)}</strong></div>
    <div className="forecast-track" data-single={from === to} aria-hidden="true"><span style={{ left: `${point}%` }} /></div>
    <div className="forecast-labels">
      <span>Нижняя граница <strong>{displayMoney(estimate.ci_lower)}</strong></span>
      <span>Верхняя граница <strong>{displayMoney(estimate.ci_upper)}</strong></span>
    </div>
    <p>Интервал характеризует неопределённость среднего. Расходы отдельного концерта могут выходить за эти границы.</p>
  </figure>
}
const reasons: Record<string, string> = {
  budget_required: 'Для прогноза нужен положительный плановый бюджет.',
  insufficient_observations: 'Для прогноза нужно не менее 10 пригодных наблюдений.',
  incomplete_history: 'Исторические данные о расходах неполны.',
}

export function Analytics() {
  const [rankingFilter, setRanking] = useState<Period | null>(null)
  const [forecastFilter, setForecast] = useState<(Period & { concert: number }) | null>(null)
  const ranking = useRead<Ranking>(rankingFilter ? url('/analytics/ranking', rankingFilter) : null)
  const forecast = useRead<Forecast>(forecastFilter ? url(`/concert/${forecastFilter.concert}/finance/forecast`, {
    date_from: forecastFilter.date_from, date_to: forecastFilter.date_to, as_of: forecastFilter.as_of,
  }) : null)
  const concerts = useOptions<Concert>('/concert')
  const planned = concerts.data?.filter(({ status }) => status === 'NEGOTIATING' || status === 'CONFIRMED')
  return <><h1>Аналитика</h1>
    <section><h2>Рейтинг проведённых концертов</h2>
      <Form fields={periodFields()} submit="Показать рейтинг" onSubmit={(data) => setRanking(data as Period)} />
      {rankingFilter && <AsyncState pending={ranking.isPending} error={ranking.error} />}
      {ranking.data && <><p>Концертов в выборке: {ranking.data.count}</p>
        {ranking.data.count ? <RankingChart ranking={ranking.data} /> : <p className="panel-empty">Нет проведённых концертов за период.</p>}</>}
    </section>
    <section><h2>Прогноз расходов</h2>
      <AsyncState pending={concerts.isPending} error={concerts.error} />
      {planned?.length === 0 && <p className="panel-empty">Нет планируемых концертов для расчёта прогноза.</p>}
      {!!planned?.length && <Form fields={[
        required('concert', 'Планируемый концерт', { kind: 'select', options: options(planned, (item) => item.name) }), ...periodFields(),
      ]} submit="Рассчитать прогноз" onSubmit={(data) => setForecast(data as Period & { concert: number })} />}
      {forecastFilter && <AsyncState pending={forecast.isPending} error={forecast.error} />}
      {forecast.data && <><p>Наблюдений: {forecast.data.n} · Неполных: {forecast.data.incomplete_count}</p>
        {forecast.data.forecast ? <ForecastInterval estimate={forecast.data.forecast} />
          : <p className="panel-empty">{reasons[forecast.data.reason ?? ''] || forecast.data.message || 'Прогноз недоступен.'}</p>}
      </>}
    </section>
  </>
}
