import { useState } from 'react'
import { useRead, useWrite, type Page } from './api'
import { AsyncState, ErrorMessage, Form, Pager, showTime, type Field } from './ui'
import { Button, ConfirmDialog } from './primitives'

const confirmations: Record<string, string> = {
  archive: 'Запись исчезнет из списка действующих. Связи с другими записями сохранятся.',
  cancel: 'Статус будет изменён на «Отменено». Проверьте причину отмены.',
  void: 'Операция останется в истории и будет исключена из финансовых итогов.',
  refund: 'Возврат появится в финансовом журнале отдельной операцией.',
  block: 'Пользователь потеряет доступ. Его активные сессии завершатся.',
  roles: 'Новые роли изменят права пользователя.',
}
const confirmationFor = (path: string) => confirmations[path.split('/').at(-1) ?? '']

export function SaveForm<T>({ fields, submit, path, method, transform, onSaved, onCancel }: {
  fields: Field[]; submit: string; path: string; method?: string;
  transform?: (data: Record<string, unknown>) => Record<string, unknown>;
  onSaved?: (value: T) => void; onCancel?: () => void
}) {
  const mutation = useWrite<T>()
  const [reset, setReset] = useState(0)
  const [confirmation, setConfirmation] = useState<Record<string, unknown> | null>(null)
  const description = confirmationFor(path)
  const save = (body: Record<string, unknown>) => mutation.mutate({ path, method, body }, {
    onSuccess: (value) => { setReset((n) => n + 1); onSaved?.(value) },
  })
  return <><Form key={reset} fields={fields} submit={submit} pending={mutation.isPending}
    error={mutation.error} onCancel={onCancel}
    onSubmit={(data) => {
      const body = transform?.(data) ?? data
      if (description) setConfirmation(body)
      else save(body)
    }}>
    {mutation.isSuccess && <p role="status">Сохранено</p>}
  </Form>{description && <ConfirmDialog open={confirmation !== null}
    setOpen={(open) => { if (!open) setConfirmation(null) }} title={submit} description={description}
    confirm={() => { if (confirmation !== null) save(confirmation) }} />}
  </>
}

export function Command({ label, path, body }: { label: string; path: string; body: unknown }) {
  const mutation = useWrite()
  const [open, setOpen] = useState(false)
  const description = confirmationFor(path)
  const execute = () => mutation.mutate({ path, body })
  return <div><Button type="button" disabled={mutation.isPending} onClick={() => description ? setOpen(true) : execute()}>
    {label}
  </Button><ErrorMessage error={mutation.error} />{description &&
    <ConfirmDialog open={open} setOpen={setOpen} description={description} title={label} confirm={execute} />}</div>
}

export function Audit({ kind, id, standalone = false }: { kind: string; id: number; standalone?: boolean }) {
  const [open, setOpen] = useState(false)
  const [offset, setOffset] = useState(0)
  const history = useRead<Page<{ id: number; occurred_at: string; actor_id: number; action: string; reason: string | null; before_data: unknown; after_data: unknown }>>(
    open || standalone ? `/audit/${kind}/${id}?offset=${offset}` : null,
  )
  const entries = <>
      <AsyncState pending={history.isPending} error={history.error} />
      {history.data?.items.length === 0 && <p className="panel-empty">Изменений пока нет.</p>}
      {history.data?.items.map((row) => <details key={row.id}>
        <summary>{showTime(row.occurred_at)} · {row.action} · Автор #{row.actor_id}{row.reason && ` · ${row.reason}`}</summary>
        <pre>{JSON.stringify({ до: row.before_data, после: row.after_data }, null, 2)}</pre>
      </details>)}
      <Pager page={history.data} setOffset={setOffset} />
  </>
  return standalone ? <section><h2>История изменений</h2>{entries}</section> : <details onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>История изменений</summary>
    {open && entries}
  </details>
}
