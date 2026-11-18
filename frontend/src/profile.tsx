import { useState } from 'react'
import { api, useRead, type Role } from './api'
import { AsyncState, Form, required, roleLabels, type Field } from './ui'

type ProfileData = {
  full_name: string; login: string; position: string; roles: Role[]; email: string | null; phone: string | null
}

const passwordFields: Field[] = [
  required('current_password', 'Текущий пароль', { kind: 'password', maxLength: 256, autoComplete: 'current-password' }),
  required('new_password', 'Новый пароль', { kind: 'password', minLength: 12, maxLength: 256, autoComplete: 'new-password' }),
  required('repeat_password', 'Подтверждение пароля', { kind: 'password', minLength: 12, maxLength: 256, autoComplete: 'new-password' }),
]

export function Profile({ onPasswordChanged }: { onPasswordChanged: () => void }) {
  const profile = useRead<ProfileData>('/auth/profile')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const person = profile.data

  async function changePassword({ current_password, new_password, repeat_password }: Record<string, unknown>) {
    if (new_password !== repeat_password) {
      setError('Новый пароль и подтверждение не совпадают.')
      return
    }
    setError(null)
    setPending(true)
    try {
      await api('/auth/change-password', 'POST', { current_password, new_password })
      onPasswordChanged()
    } catch (failure) {
      setError(failure)
    } finally {
      setPending(false)
    }
  }

  return <>
    <div className="page-heading" data-enter><h1>Мой профиль</h1></div>
    <section><h2>Личные данные</h2>
      <AsyncState pending={profile.isPending} error={profile.error} />
      {person && <dl className="concert-facts">
        <div><dt>ФИО</dt><dd>{person.full_name}</dd></div>
        <div><dt>Логин</dt><dd>{person.login}</dd></div>
        <div><dt>Должность</dt><dd>{person.position}</dd></div>
        <div><dt>Роли</dt><dd>{person.roles.map((role) => roleLabels[role]).join(', ') || 'Без роли'}</dd></div>
        <div><dt>Электронная почта</dt><dd>{person.email ?? 'Не указана'}</dd></div>
        <div><dt>Телефон</dt><dd>{person.phone ?? 'Не указан'}</dd></div>
      </dl>}
    </section>
    <section><h2>Смена пароля</h2>
      <p>Новый пароль должен содержать не менее 12 символов. После смены потребуется войти заново на всех устройствах.</p>
      <Form fields={passwordFields} submit="Изменить пароль" pending={pending} error={error} onSubmit={changePassword} />
    </section>
  </>
}
