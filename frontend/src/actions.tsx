import { useState } from 'react'
import { useRead, useWrite, type Page } from './api'
import { AsyncState, ErrorMessage, Form, Pager, showTime, type Field } from './ui'

export function SaveForm<T>({ fields, submit, path, method, transform, onSaved, onCancel }: {
  fields: Field[]; submit: string; path: string; method?: string;
  transform?: (data: Record<string, unknown>) => Record<string, unknown>;
  onSaved?: (value: T) => void; onCancel?: () => void
}) {
  const mutation = useWrite<T>()
  const [reset, setReset] = useState(0)
  return <Form key={reset} fields={fields} submit={submit} pending={mutation.isPending}
    error={mutation.error} onCancel={onCancel}
    onSubmit={(data) => mutation.mutate({ path, method, body: transform?.(data) ?? data }, {
      onSuccess: (value) => { setReset((n) => n + 1); onSaved?.(value) },
    })}>
    {mutation.isSuccess && <p role="status">Сохранено</p>}
  </Form>
}

export function Command({ label, path, body }: { label: string; path: string; body: unknown }) {
  const mutation = useWrite()
  return <div><button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate({ path, body })}>
    {label}
  </button><ErrorMessage error={mutation.error} /></div>
}

export function Audit({ kind, id }: { kind: string; id: number }) {
  const [open, setOpen] = useState(false)
  const [offset, setOffset] = useState(0)
  const history = useRead<Page<{ id: number; occurred_at: string; actor_id: number; action: string; reason: string | null; before_data: unknown; after_data: unknown }>>(
    open ? `/audit/${kind}/${id}?offset=${offset}` : null,
  )
  return <details onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>История изменений</summary>
    {open && <>
      <AsyncState pending={history.isPending} error={history.error} />
      {history.data?.items.map((row) => <details key={row.id}>
        <summary>{showTime(row.occurred_at)} · {row.action} · Автор #{row.actor_id}{row.reason && ` · ${row.reason}`}</summary>
        <pre>{JSON.stringify({ до: row.before_data, после: row.after_data }, null, 2)}</pre>
      </details>)}
      <Pager page={history.data} setOffset={setOffset} />
    </>}
  </details>
}
