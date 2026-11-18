import { useState } from 'react'
import { useRead, url, type CatalogRow, type Page } from './api'
import { Command, SaveForm } from './actions'
import { Button } from './primitives'
import { AsyncState, Form, Pager, directionLabels, directions, required, type Field } from './ui'

const definitions = {
  venue: { title: 'Площадки', fields: [
    required('name', 'Название', { maxLength: 200 }), required('city', 'Город', { maxLength: 100 }),
    required('address', 'Адрес', { maxLength: 300 }), { key: 'capacity', label: 'Вместимость', kind: 'integer', min: 0, max: 2147483647 },
  ] },
  counterparty: { title: 'Контрагенты', fields: [
    required('name', 'Название', { maxLength: 200 }), required('kind', 'Тип контрагента', { maxLength: 20 }),
    { key: 'phone', label: 'Телефон', maxLength: 32 }, { key: 'email', label: 'Электронная почта', kind: 'email', maxLength: 254 },
    { key: 'details', label: 'Примечания', kind: 'textarea' },
  ] },
  finance_category: { title: 'Категории операций', fields: [
    required('code', 'Код', { maxLength: 40 }), required('name', 'Название', { maxLength: 100 }),
    required('normal_direction', 'Направление', { kind: 'select', options: directions }),
  ] },
} satisfies Record<string, { title: string; fields: Field[] }>

export type CatalogKind = keyof typeof definitions
export function Catalog({ kind }: { kind: CatalogKind }) {
  const { title, fields } = definitions[kind]
  const [query, setQuery] = useState('')
  const [archived, setArchived] = useState(false)
  const [offset, setOffset] = useState(0)
  const [editing, setEditing] = useState<number | null>(null)
  const list = useRead<Page<CatalogRow>>(url(`/${kind}`, { q: query, archived, offset }))
  return <>
    <h1>{title}</h1>
    <section aria-label="Новая запись">
      <h2>Новая запись</h2>
      <SaveForm fields={fields} path={`/${kind}`} submit="Добавить" onSaved={() => { setArchived(false); setQuery(''); setOffset(0) }} />
    </section>
    <section aria-label="Список">
      <h2>Список</h2>
      <Form fields={[{ key: 'q', label: 'Поиск', initial: query, maxLength: 300 }]}
        submit="Найти" onSubmit={({ q }) => { setQuery(String(q ?? '')); setOffset(0) }} />
      <label className="actions"><span>Архивные записи</span><input style={{ width: 'auto' }} type="checkbox"
        checked={archived} onChange={(event) => { setArchived(event.target.checked); setOffset(0); setEditing(null) }} /></label>
      <AsyncState pending={list.isPending} error={list.error} />
      {list.data?.items.map((row) => <section key={row.id} aria-label={row.name}>
        <h3>{row.name}</h3>
        {fields.filter((field) => field.key !== 'name' && row[field.key] != null).map((field) =>
          <p key={field.key}>{field.label}: {field.key === 'normal_direction' && row.normal_direction
            ? directionLabels[row.normal_direction] : String(row[field.key])}</p>)}
        {!archived && <div className="actions">
          <Button type="button" onClick={() => setEditing(row.id)}>Изменить</Button>
          <Command label="Архивировать" path={`/${kind}/${row.id}/archive`} body={{ version: row.version }} />
        </div>}
        {editing === row.id && !archived && <SaveForm key={row.version}
          fields={fields.map((field) => ({ ...field, initial: row[field.key] }))}
          method="PATCH" path={`/${kind}/${row.id}`} submit="Сохранить изменения"
          transform={(body) => ({ ...body, version: row.version })} onSaved={() => setEditing(null)}
          onCancel={() => setEditing(null)} />}
      </section>)}
      <Pager page={list.data} setOffset={setOffset} />
    </section>
  </>
}
