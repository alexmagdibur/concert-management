import { useState, type FormEvent, type ReactNode } from 'react'
import type { Direction, Page, Role } from './api'
import { AlertCircle, LoaderCircle } from 'lucide-react'
import { Button, Input, Textarea } from './primitives'

export type Option = { value: string | number; label: string }
export type Field = {
  key: string; label: string; kind?: 'text' | 'password' | 'email' | 'date' | 'datetime-local' | 'integer' | 'money' | 'textarea' | 'select' | 'multi';
  required?: boolean; options?: Option[]; initial?: unknown; min?: number; max?: number;
  minLength?: number; maxLength?: number; emptyLabel?: string; autoComplete?: string
}
export const directionLabels: Record<Direction, string> = { IN: 'Поступление', OUT: 'Расход' }
export const roleLabels: Record<Role, string> = { MANAGER: 'Менеджер', ADMIN: 'Администратор' }
export const directions: Option[] = Object.entries(directionLabels).map(([value, label]) => ({ value, label }))
export const roles: Option[] = Object.entries(roleLabels).map(([value, label]) => ({ value, label }))

export function ErrorMessage({ error }: { error: unknown }) {
  return error ? <p role="alert" className="error"><AlertCircle size={17} aria-hidden="true" /><span>{error instanceof Error ? error.message : String(error)}</span></p> : null
}

export function Form({ fields, submit, onSubmit, pending, error, onCancel, children, cancelLabel = 'Закрыть форму' }: {
  fields: Field[]; submit: string; onSubmit: (data: Record<string, unknown>) => void;
  pending?: boolean; error?: unknown; onCancel?: () => void; children?: ReactNode; cancelLabel?: string
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
            ? <select {...props} className="ui-field" multiple={field.kind === 'multi'}
                defaultValue={field.kind === 'multi' ? (field.initial as string[] | undefined) || [] : initial}>
                {field.kind !== 'multi' && <option value="">{field.emptyLabel || 'Выберите'}</option>}
                {field.options?.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
              </select>
            : field.kind === 'textarea' ? <Textarea {...props} rows={2} />
            : <Input {...props} type={field.kind === 'integer' || field.kind === 'money' ? 'number' : field.kind || 'text'}
                min={field.min} max={field.max} step={field.kind === 'money' ? '0.01' : undefined}
                autoComplete={field.autoComplete ?? (field.kind === 'password' ? 'off' : undefined)} />}
        </label>
      })}
    </fieldset>
    {children}
    <ErrorMessage error={validation || error} />
    <div className="actions"><Button variant="default" type="submit" disabled={pending}>{pending && <LoaderCircle className="spin" size={15} aria-hidden="true" />}{submit}</Button>
      {onCancel && <Button type="button" onClick={onCancel} disabled={pending}>{cancelLabel}</Button>}
    </div>
  </form>
}

export function AsyncState({ pending, error }: { pending: boolean; error: unknown }) {
  return <>{pending && <p role="status" className="loading"><LoaderCircle className="spin" size={17} aria-hidden="true" />Загрузка…</p>}<ErrorMessage error={error} /></>
}
export function Pager<T>({ page, setOffset }: { page?: Page<T>; setOffset: (offset: number) => void }) {
  if (!page) return null
  return <div className="actions pager">
    <span>Всего: {page.total}</span>
    {page.offset > 0 && <Button type="button" onClick={() => setOffset(Math.max(0, page.offset - page.limit))}>Назад</Button>}
    {page.offset + page.limit < page.total && <Button type="button" onClick={() => setOffset(page.offset + page.limit)}>Далее</Button>}
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
export function Status({ code, label }: { code: string; label?: string }) {
  const tone = ['CONFIRMED', 'ACTIVE', 'POSTED', 'COMPLETED', 'AGREED'].includes(code) ? 'good'
    : ['NEGOTIATING', 'PLANNED', 'DRAFT'].includes(code) ? 'wait'
    : ['VOID', 'CANCELLED', 'BLOCKED'].includes(code) ? 'off' : 'neutral'
  return <span className="status-pill" data-tone={tone} data-status={code}>{label ?? statuses[code] ?? code}</span>
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
