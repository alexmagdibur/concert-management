import { useState } from 'react'
import { useOptions, useRead, url, type CatalogRow, type Concert, type Contract, type Engagement, type Entry, type Page } from './api'
import { Command, SaveForm } from './actions'
import { Button } from './primitives'
import { AsyncState, Pager, Status, directionLabels, directions, displayMoney, options, required, showTime, today, withCurrent, type Field } from './ui'

const kindLabels = { MAIN_SHOW: 'Основной договор', SERVICE: 'Договор услуг' }

function contractFields(parties: CatalogRow[] | undefined, concert: Concert, row?: Contract): Field[] {
  return [
    required('number', 'Номер договора', { maxLength: 80, initial: row?.number }),
    required('signed_on', 'Дата подписания', { kind: 'date', initial: row?.signed_on ?? today() }),
    required('counterparty_id', 'Контрагент', { kind: 'select', initial: row?.counterparty_id ?? concert.proposed_organizer_id,
      options: withCurrent(options(parties, (item) => item.name), row?.counterparty_id) }),
    required('kind', 'Вид договора', { kind: 'select', initial: row?.kind ?? 'MAIN_SHOW',
      options: Object.entries(kindLabels).map(([value, label]) => ({ value, label })) }),
    required('subject', 'Предмет', { kind: 'textarea', initial: row?.subject }),
    required('amount', 'Сумма договора', { kind: 'money', min: .01, max: 999999999999.99, initial: row?.amount }),
  ]
}
function contractDirection(body: Record<string, unknown>) {
  return { ...body, direction: body.kind === 'MAIN_SHOW' ? 'IN' : 'OUT' }
}
export function Contracts({ concert }: { concert: Concert }) {
  const [offset, setOffset] = useState(0)
  const [editing, setEditing] = useState<number | null>(null)
  const parties = useOptions<CatalogRow>('/counterparty')
  const list = useRead<Page<Contract>>(url('/contract', { concert_id: concert.id, offset }))
  return <section><h2>Договоры</h2>
    <AsyncState pending={parties.isPending || list.isPending} error={parties.error || list.error} />
    {list.data?.items.length === 0 && <p className="panel-empty">К этому концерту пока не добавлены договоры.</p>}
    {parties.data && <section aria-label="Новый договор"><h3>Новый договор</h3>
      <SaveForm fields={contractFields(parties.data, concert)} path="/contract" submit="Создать договор"
        transform={(body) => ({ ...contractDirection(body), concert_id: concert.id })} onSaved={() => setOffset(0)} />
    </section>}
    {list.data?.items.map((row) => <section key={row.id} aria-label={row.number}>
      <h3>{row.number}</h3><p>{kindLabels[row.kind]} · <Status code={row.status} /> · {displayMoney(row.amount)}</p>
      <p>{row.subject} · {row.signed_on}</p>
      {row.status === 'DRAFT' && <div className="actions">
        <Button type="button" onClick={() => setEditing(row.id)}>Изменить договор</Button>
        <Command label="Активировать договор" path={`/contract/${row.id}/activate`} body={{ version: row.version }} />
      </div>}
      {editing === row.id && row.status === 'DRAFT' && parties.data && <SaveForm key={row.version}
        fields={contractFields(parties.data, concert, row)} path={`/contract/${row.id}`} method="PATCH" submit="Сохранить договор"
        transform={(body) => ({ ...contractDirection(body), version: row.version })}
        onSaved={() => setEditing(null)} onCancel={() => setEditing(null)} />}
    </section>)}
    <Pager page={list.data} setOffset={setOffset} />
  </section>
}

export function Engagements({ concert }: { concert: Concert }) {
  const [offset, setOffset] = useState(0)
  const parties = useOptions<CatalogRow>('/counterparty')
  const contracts = useOptions<Contract>(url('/contract', { concert_id: concert.id }))
  const list = useRead<Page<Engagement>>(`/concert/${concert.id}/engagement?offset=${offset}`)
  return <section><h2>Подрядчики</h2>
    <AsyncState pending={parties.isPending || contracts.isPending || list.isPending}
      error={parties.error || contracts.error || list.error} />
    {list.data?.items.length === 0 && <p className="panel-empty">К этому концерту пока не добавлены работы подрядчиков.</p>}
    {parties.data && <section><h3>Новая работа</h3>
      <SaveForm fields={[
        required('counterparty_id', 'Подрядчик', { kind: 'select', options: options(parties.data, (item) => item.name) }),
        required('description', 'Описание работы', { kind: 'textarea' }),
        required('due_at', 'Срок', { kind: 'datetime-local' }),
        required('agreed_amount', 'Согласованная стоимость', { kind: 'money', min: .01, max: 999999999999.99 }),
      ]} path="/engagement" submit="Добавить работу" transform={(body) => ({ ...body, concert_id: concert.id })}
        onSaved={() => setOffset(0)} />
    </section>}
    {list.data?.items.map((row) => <section key={row.id} aria-label={row.description}>
      <h3>{row.description}</h3><p><Status code={row.status} /> · {displayMoney(row.agreed_amount)} · {showTime(row.due_at)}</p>
      <p>Подрядчик: {parties.data?.find((item) => item.id === row.counterparty_id)?.name ?? `#${row.counterparty_id}`}
        {row.contract_id != null && ` · Договор: ${contracts.data?.find((item) => item.id === row.contract_id)?.number ?? '#' + row.contract_id}`}</p>
      {row.cancel_reason && <p>Причина отмены: {row.cancel_reason}</p>}
      {row.status === 'PLANNED' && contracts.data && <SaveForm fields={[
        required('contract_id', 'Договор на работы', { kind: 'select', options: options(
          contracts.data.filter((item) => item.kind === 'SERVICE' && item.counterparty_id === row.counterparty_id),
          (item) => `${item.number} · ${displayMoney(item.amount)}`,
        ) }),
      ]} path={`/engagement/${row.id}/agree`} submit="Согласовать работу"
        transform={(body) => ({ ...body, version: row.version })} />}
      {row.status === 'AGREED' && <Command label="Отметить выполнение"
        path={`/engagement/${row.id}/complete`} body={{ version: row.version }} />}
      {['PLANNED', 'AGREED'].includes(row.status) && <details><summary>Отмена работы</summary>
        <SaveForm fields={[{ key: 'reason', label: 'Причина отмены' }]}
          path={`/engagement/${row.id}/cancel`} submit="Отменить работу"
          transform={(body) => ({ ...body, version: row.version })} />
      </details>}
    </section>)}
    <Pager page={list.data} setOffset={setOffset} />
  </section>
}

function KeyedForm({ fields, path, submit, extra, onSaved }: {
  fields: Field[]; path: string; submit: string; extra?: Record<string, unknown>; onSaved?: () => void
}) {
  const [key, setKey] = useState(() => crypto.randomUUID())
  return <SaveForm fields={fields} path={path} submit={submit}
    transform={(body) => ({ ...body, ...extra, request_key: key })}
    onSaved={() => { setKey(crypto.randomUUID()); onSaved?.() }} />
}
function entryFields(categories: CatalogRow[], contracts: Contract[], row?: Entry): Field[] {
  return [
    required('direction', 'Вид операции', { kind: 'select', options: directions, initial: row?.direction }),
    required('category_id', 'Категория', { kind: 'select', initial: row?.category_id,
      options: withCurrent(options(categories, (item) => item.normal_direction
        ? `${item.name} · ${directionLabels[item.normal_direction]}` : item.name), row?.category_id) }),
    { key: 'contract_id', label: 'Договор', kind: 'select', emptyLabel: 'Без договора', initial: row?.contract_id,
      options: withCurrent(options(contracts, (item) => `${item.number} · ${directionLabels[item.direction]}`), row?.contract_id) },
    required('occurred_on', 'Дата операции', { kind: 'date', initial: row?.occurred_on ?? today() }),
    required('amount', 'Сумма операции', { kind: 'money', min: .01, max: 999999999999.99, initial: row?.amount }),
    required('basis', 'Основание', { kind: 'textarea', initial: row?.basis }),
  ]
}
export function Journal({ concert }: { concert: Concert }) {
  const [offset, setOffset] = useState(0)
  const [draft, setDraft] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const categories = useOptions<CatalogRow>('/finance_category')
  const contracts = useOptions<Contract>(url('/contract', { concert_id: concert.id }))
  const list = useRead<Page<Entry>>(`/concert/${concert.id}/finance?offset=${offset}`)
  const fields = categories.data && contracts.data ? entryFields(categories.data, contracts.data) : null
  return <section><h2>Финансовый журнал</h2>
    {list.data?.items.length === 0 && <p className="panel-empty">По этому концерту пока нет финансовых операций.</p>}
    <AsyncState pending={categories.isPending || contracts.isPending || list.isPending}
      error={categories.error || contracts.error || list.error} />
    {fields && <section aria-label="Новая операция"><h3>Новая операция</h3>
      <label className="actions"><span>Создать черновик</span><input style={{ width: 'auto' }} type="checkbox"
        checked={draft} onChange={(event) => setDraft(event.target.checked)} /></label>
      {draft ? <SaveForm fields={fields} path="/finance/draft" submit="Сохранить черновик"
        transform={(body) => ({ ...body, concert_id: concert.id })} onSaved={() => setOffset(0)} />
        : <KeyedForm fields={fields} path="/finance" submit="Учесть операцию"
          extra={{ concert_id: concert.id }} onSaved={() => setOffset(0)} />}
    </section>}
    {list.data?.items.map((row) => <section key={row.id} aria-label={row.basis}>
      <h3>{row.basis}</h3>
      <p>{row.direction === 'IN' ? 'Поступление' : 'Расход'} · {displayMoney(row.amount)} · {row.occurred_on} · <Status code={row.status} /></p>
      {row.original_id !== null && <p>Возврат по операции #{row.original_id}</p>}
      {row.void_reason && <p>Причина аннулирования: {row.void_reason}</p>}
      {row.status === 'DRAFT' && <>
        <div className="actions"><Button type="button" onClick={() => setEditing(row.id)}>Изменить черновик</Button>
          <KeyedForm fields={[]} path={`/finance/${row.id}/post`} submit="Провести черновик" extra={{ version: row.version }} />
        </div>
        {editing === row.id && categories.data && contracts.data && <SaveForm key={row.version}
          fields={entryFields(categories.data, contracts.data, row)} path={`/finance/${row.id}`} method="PATCH"
          submit="Сохранить черновик" transform={(body) => ({ ...body, version: row.version })}
          onSaved={() => setEditing(null)} onCancel={() => setEditing(null)} />}
      </>}
      {row.status === 'POSTED' && <>
        <details><summary>Аннулирование</summary><SaveForm
          fields={[required('reason', 'Причина аннулирования', { kind: 'textarea' })]}
          path={`/finance/${row.id}/void`} submit="Аннулировать операцию"
          transform={(body) => ({ ...body, version: row.version })} /></details>
        {row.original_id === null && <details><summary>Возврат</summary>
          <KeyedForm fields={[
            required('occurred_on', 'Дата возврата', { kind: 'date', initial: today(), }),
            required('amount', 'Сумма возврата', { kind: 'money', min: .01, max: 999999999999.99 }),
            required('basis', 'Основание возврата', { kind: 'textarea' }),
          ]} path={`/finance/${row.id}/refund`} submit="Учесть возврат" onSaved={() => setOffset(0)} />
        </details>}
      </>}
    </section>)}
    <Pager page={list.data} setOffset={setOffset} />
  </section>
}
