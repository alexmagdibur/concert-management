import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useOptions, useRead, url, type Concert, type Entry, type Page } from './api'
import { AsyncState, Form, Pager, displayMoney, options, required, showTime, today, type Field } from './ui'

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
      <div className="table-scroll"><table><thead><tr><th>Договор</th><th>Сумма</th><th>Оплачено</th><th>Остаток</th><th>Переплата</th></tr></thead>
        <tbody>{report.data.contracts.map((item) => <tr key={item.contract_id}>
          <td>{item.number}</td><td>{displayMoney(item.amount)}</td><td>{displayMoney(item.net_paid)}</td>
          <td>{displayMoney(item.unpaid)}</td><td>{displayMoney(item.overpaid)}</td>
        </tr>)}</tbody>
      </table></div>
      <h2>Операции за период</h2>
      <div className="table-scroll"><table><thead><tr><th>Дата</th><th>Вид</th><th>Основание</th><th>Сумма</th></tr></thead>
        <tbody>{report.data.operations.items.map((item) => <tr key={item.id}>
          <td>{item.occurred_on}</td><td>{item.direction === 'IN' ? 'Поступление' : 'Расход'}</td>
          <td>{item.basis}{item.original_id != null && ` · возврат по #${item.original_id}`}</td><td>{displayMoney(item.amount)}</td>
        </tr>)}</tbody>
      </table></div><Pager page={report.data.operations} setOffset={setOffset} />
    </>}
  </section></>
}

function RankList({ title, items }: { title: string; items: Rank[] }) {
  return <><h3>{title}</h3>{items.length === 0 ? <p>Нет проведённых концертов за период.</p> :
    <ol>{items.map((item) => <li key={item.concert_id}>
      <Link to={`/concerts/${item.concert_id}`}>{item.name}</Link> · {showTime(item.starts_at)} · {displayMoney(item.net)}
    </li>)}</ol>}
  </>
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
  return <><h1>Аналитика</h1>
    <section><h2>Рейтинг проведённых концертов</h2>
      <Form fields={periodFields()} submit="Показать рейтинг" onSubmit={(data) => setRanking(data as Period)} />
      {rankingFilter && <AsyncState pending={ranking.isPending} error={ranking.error} />}
      {ranking.data && <><p>Концертов в выборке: {ranking.data.count}</p>
        <RankList title="Лучшие" items={ranking.data.best} /><RankList title="Худшие" items={ranking.data.worst} /></>}
    </section>
    <section><h2>Прогноз расходов</h2>
      <AsyncState pending={concerts.isPending} error={concerts.error} />
      {concerts.data && <Form fields={[
        required('concert', 'Планируемый концерт', { kind: 'select', options: options(
          concerts.data.filter(({ status }) => status === 'NEGOTIATING' || status === 'CONFIRMED'),
          (item) => item.name,
        ) }), ...periodFields(),
      ]} submit="Рассчитать прогноз" onSubmit={(data) => setForecast(data as Period & { concert: number })} />}
      {forecastFilter && <AsyncState pending={forecast.isPending} error={forecast.error} />}
      {forecast.data && <><p>Наблюдений: {forecast.data.n} · Неполных: {forecast.data.incomplete_count}</p>
        {forecast.data.forecast ? <>
          <p>Ожидаемые расходы: {displayMoney(forecast.data.forecast.expected_expenses)}</p>
          <p>95%-й доверительный интервал среднего: {displayMoney(forecast.data.forecast.ci_lower)} — {displayMoney(forecast.data.forecast.ci_upper)}</p>
          <p>Интервал характеризует неопределённость среднего. Расходы отдельного концерта могут выходить за эти границы.</p>
        </> : <p>{reasons[forecast.data.reason ?? ''] || forecast.data.message || 'Прогноз недоступен.'}</p>}
      </>}
    </section>
  </>
}
