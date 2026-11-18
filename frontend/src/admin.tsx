import { useState } from 'react'
import { useOptions, useRead, url, type Account, type Page } from './api'
import { Audit, SaveForm } from './actions'
import { AsyncState, Pager, Status, required, roleLabels, roles, type Field } from './ui'

const createFields: Field[] = [
  required('full_name', 'ФИО', { maxLength: 150 }), required('position', 'Должность', { maxLength: 80 }),
  required('login', 'Логин', { maxLength: 80 }),
  required('password', 'Пароль', { kind: 'password', minLength: 12, maxLength: 256 }),
  { key: 'phone', label: 'Телефон', maxLength: 32 },
  { key: 'email', label: 'Электронная почта', kind: 'email', maxLength: 254 },
  required('roles', 'Роли', { kind: 'multi', options: roles }),
]
export function Admin() {
  const [offset, setOffset] = useState(0)
  const list = useRead<Page<Account>>(url('/admin/accounts', { offset }))
  const staff = useOptions<Account>('/admin/accounts')
  return <><h1>Пользователи</h1>
    <section aria-label="Новый пользователь"><h2>Новый пользователь</h2>
      <SaveForm fields={createFields} path="/admin/accounts" submit="Создать пользователя" onSaved={() => setOffset(0)} />
    </section>
    <AsyncState pending={list.isPending || staff.isPending} error={list.error || staff.error} />
    {list.data?.items.map((row) => {
      const transfer: Field = { key: 'replacement_employee_id', label: 'Передать концерты менеджеру', kind: 'select',
        emptyLabel: 'Без передачи', options: staff.data?.filter((person) =>
          person.id !== row.id && person.active && person.roles.includes('MANAGER'))
          .map((person) => ({ value: person.employee_id, label: person.full_name })) }
      const reason = required('reason', 'Причина')
      return <section key={row.id} aria-label={row.login}>
        <h2>{row.full_name}</h2><p>{row.login} · {row.position} · <Status code={row.active ? 'ACTIVE' : 'BLOCKED'}
          label={row.active ? 'Активен' : 'Заблокирован'} /> · {row.roles.map((role) => roleLabels[role]).join(', ')}</p>
        {row.active && staff.data && <>
          <details><summary>Изменение ролей</summary>
            <SaveForm key={`roles-${row.version}`} fields={[
              required('roles', 'Роли', { kind: 'multi', options: roles, initial: row.roles }), reason, transfer,
            ]} path={`/admin/accounts/${row.id}/roles`} method="PUT" submit="Сохранить роли"
              transform={(body) => ({ ...body, version: row.version })} />
          </details>
          <details><summary>Блокировка пользователя</summary>
            <SaveForm key={`block-${row.version}`} fields={[reason, transfer]}
              path={`/admin/accounts/${row.id}/block`} submit="Заблокировать пользователя"
              transform={(body) => ({ ...body, version: row.version })} />
          </details>
        </>}
        <Audit kind="account" id={row.id} />
      </section>
    })}
    <Pager page={list.data} setOffset={setOffset} />
  </>
}
