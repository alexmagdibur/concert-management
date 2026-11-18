import { useState, type FormEvent, type ReactNode } from 'react'
import type { Page } from './api'

export type Option = { value: string | number; label: string }
export type Field = {
  key: string; label: string; kind?: 'text' | 'password' | 'email' | 'date' | 'datetime-local' | 'integer' | 'money' | 'textarea' | 'select' | 'multi';
  required?: boolean; options?: Option[]; initial?: unknown; min?: number; max?: number;
  minLength?: number; maxLength?: number; emptyLabel?: string
}
const defaultOptions: Option[] = [{ value: 'IN', label: 'Поступление' }, { value: 'OUT', label: 'Расход' }]
export const directions = defaultOptions
export const roles: Option[] = [{ value: 'MANAGER', label: 'Менеджер' }, { value: 'ADMIN', label: 'Администратор' }]

export function ErrorMessage({ error }: { error: unknown }) {
  return error ? <p role="alert" className="error">{error instanceof Error ? error.message : String(error)}</p> : null
}

export function Form({ fields, submit, onSubmit, pending, error, onCancel, children }: {
  fields: Field[]; submit: string; onSubmit: (data: Record<string, unknown>) => void;
  pending?: boolean; error?: unknown; onCancel?: () => void; children?: ReactNode
}) {
  const [validation, setValidation] = useState('')
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const data: Record<string, unknown> = {}
    for (const field of fields) {
      const values = form.getAll(field.key).map(String)
      const value = field.kind === 'password' ? values[0] || '' : (values[0] || '').trim()
      if (field.required && !value) { setValidation(`Заполните поле «${field.label}».`); return }
      if (field.kind === 'multi') data[field.key] = values
      else if (!value) data[field.key] = null
      else if (field.kind === 'datetime-local') data[field.key] = utcTimestamp(value)
      else if (field.kind === 'integer') {
        const integer = Number(value)
        if (!Number.isSafeInteger(integer)) { setValidation(`Введите целое число в поле «${field.label}».`); return }
        data[field.key] = integer
      } else if (field.kind === 'select' && field.options?.some((option) =>
        typeof option.value === 'number' && String(option.value) === value)) data[field.key] = Number(value)
      else data[field.key] = value
    }
    setValidation('')
    onSubmit(data)
  }

  return <form onSubmit={handleSubmit}>
    <fieldset disabled={pending} className="form-fields">
      {fields.map((field) => {
        const initial = field.kind === 'datetime-local' && field.initial
          ? localDateTime(String(field.initial)) : String(field.initial ?? '')
        const props = { name: field.key, required: field.required, defaultValue: initial,
          minLength: field.minLength, maxLength: field.maxLength }
        return <label key={field.key}>{field.label}{field.required && ' *'}
          {field.kind === 'select' || field.kind === 'multi'
            ? <select {...props} multiple={field.kind === 'multi'}
                defaultValue={field.kind === 'multi' ? (field.initial as string[] | undefined) || [] : initial}>
                {field.kind !== 'multi' && <option value="">{field.emptyLabel || 'Выберите'}</option>}
                {field.options?.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
              </select>
            : field.kind === 'textarea' ? <textarea {...props} rows={2} />
            : <input {...props} type={field.kind === 'integer' || field.kind === 'money' ? 'number' : field.kind || 'text'}
                min={field.min} max={field.max} step={field.kind === 'money' ? '0.01' : undefined}
                autoComplete={field.kind === 'password' ? 'off' : undefined} />}
        </label>
      })}
    </fieldset>
    {children}
    <ErrorMessage error={validation || error} />
    <div className="actions"><button type="submit" disabled={pending}>{submit}</button>
      {onCancel && <button type="button" onClick={onCancel} disabled={pending}>Закрыть форму</button>}
    </div>
  </form>
}

export function AsyncState({ pending, error }: { pending: boolean; error: unknown }) {
  return <>{pending && <p role="status">Загрузка…</p>}<ErrorMessage error={error} /></>
}
export function Pager<T>({ page, setOffset }: { page?: Page<T>; setOffset: (offset: number) => void }) {
  if (!page) return null
  return <div className="actions">
    <span>Всего: {page.total}</span>
    {page.offset > 0 && <button onClick={() => setOffset(Math.max(0, page.offset - page.limit))}>Назад</button>}
    {page.offset + page.limit < page.total && <button onClick={() => setOffset(page.offset + page.limit)}>Далее</button>}
  </div>
}

export function localDateTime(value: string) {
  const date = new Date(value)
  return new Date(date.valueOf() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}
function utcTimestamp(value: string) { return new Date(value).toISOString() }
export function showTime(value: string) { return new Date(value).toLocaleString('ru-RU') }
export function today() { return localDateTime(new Date().toISOString()).slice(0, 10) }
export function displayMoney(value: string) {
  // Group the string without converting Decimal amounts to floating point.
  const [whole, fraction = '00'] = value.split('.')
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f')},${fraction.padEnd(2, '0')} ₽`
}
export const statuses: Record<string, string> = {
  NEGOTIATING: 'На согласовании', CONFIRMED: 'Подтверждён', COMPLETED: 'Выполнено',
  CANCELLED: 'Отменено', PLANNED: 'Планируется', AGREED: 'Согласовано',
  DRAFT: 'Черновик', ACTIVE: 'Действует', CLOSED: 'Закрыт', POSTED: 'Учтена', VOID: 'Аннулирована',
}

export function options<T extends { id: number }>(items: T[] | undefined, format: (item: T) => string): Option[] {
  return (items || []).map((item) => ({ value: item.id, label: format(item) }))
}
export function withCurrent(items: Option[], id: number | null | undefined) {
  if (id == null || items.some((item) => item.value === id)) return items
  return [...items, { value: id, label: `Текущая запись #${id}` }]
}
export function required(key: string, label: string, extra: Partial<Field> = {}): Field {
  return { key, label, required: true, ...extra }
}
