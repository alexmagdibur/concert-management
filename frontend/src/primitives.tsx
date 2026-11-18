import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { clsx, type ClassValue } from 'clsx'
import { ShieldAlert } from 'lucide-react'
import { twMerge } from 'tailwind-merge'
import type { ComponentProps, ReactNode } from 'react'

function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)) }
const buttonVariants = cva('ui-button inline-flex shrink-0 items-center justify-center gap-2 rounded-full text-sm font-semibold disabled:pointer-events-none disabled:opacity-50', {
  variants: {
    variant: {
      default: 'ui-primary',
      outline: 'ui-outline',
      ghost: 'ui-ghost',
      destructive: 'ui-destructive',
    },
    size: { default: 'min-h-10 px-4', icon: 'size-10 p-0' },
  },
  defaultVariants: { variant: 'outline', size: 'default' },
})
export function Button({ className, variant, size, asChild, ...props }: ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Component = asChild ? Slot : 'button'
  return <Component data-slot="button" className={cn(buttonVariants({ variant, size }), className)} {...props} />
}
export function Input({ className, ...props }: ComponentProps<'input'>) {
  return <input data-slot="input" className={cn('ui-field w-full min-w-0 rounded-xl px-3', className)} {...props} />
}
export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return <textarea data-slot="textarea" className={cn('ui-field w-full min-w-0 rounded-xl px-3 py-2', className)} {...props} />
}
export function TableView<T>({ rows, columns, rowKey, empty = 'Нет записей', label }: {
  rows: T[]; columns: { title: string; render: (row: T) => ReactNode; numeric?: boolean }[];
  rowKey: (row: T) => string | number; empty?: string; label: string
}) {
  return <div data-slot="table-container" className="table-scroll relative w-full overflow-x-auto" tabIndex={0} role="region" aria-label={label}>
    <table data-slot="table" className="w-full text-sm">
      <thead><tr>{columns.map(({ title, numeric }) => <th scope="col" key={title} className={numeric ? 'numeric' : undefined}>{title}</th>)}</tr></thead>
      <tbody>{rows.map((row) => <tr key={rowKey(row)}>{columns.map(({ title, render, numeric }) => (
        <td key={title} className={numeric ? 'numeric' : undefined}>{render(row)}</td>
      ))}</tr>)}
        {rows.length === 0 && <tr><td colSpan={columns.length} className="empty-cell">{empty}</td></tr>}
      </tbody>
    </table>
  </div>
}

export function ConfirmDialog({ open, setOpen, description, title, confirm }: {
  open: boolean; setOpen: (open: boolean) => void; description: string; title: string; confirm: () => void
}) {
  return <AlertDialog.Root open={open} onOpenChange={setOpen}>
    <AlertDialog.Portal>
      <AlertDialog.Overlay className="dialog-overlay fixed inset-0 z-40" />
      <AlertDialog.Content className="dialog-content fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-1/2 rounded-3xl p-6">
        <div className="dialog-icon"><ShieldAlert size={20} aria-hidden="true" /></div>
        <AlertDialog.Title className="dialog-title">{title}</AlertDialog.Title>
        <AlertDialog.Description className="dialog-description">{description}</AlertDialog.Description>
        <div className="flex flex-wrap justify-end gap-2 pt-5">
          <AlertDialog.Cancel asChild><Button type="button">Вернуться</Button></AlertDialog.Cancel>
          <AlertDialog.Action asChild><Button type="button" variant="destructive" onClick={confirm}>Подтвердить действие</Button></AlertDialog.Action>
        </div>
      </AlertDialog.Content>
    </AlertDialog.Portal>
  </AlertDialog.Root>
}
