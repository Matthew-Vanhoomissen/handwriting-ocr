import { useEffect, useRef } from 'react'

// Modal yes/no prompt for destructive actions, built on the native <dialog>
// element (showModal gives focus trapping and Escape-to-cancel for free).
// Render it with `open` true to show it; the caller closes it in onConfirm/onCancel.
export default function ConfirmDialog({ open, title, message, confirmLabel = 'Delete', busy = false, onConfirm, onCancel }) {
  const ref = useRef(null)

  useEffect(() => {
    const dialog = ref.current
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className="confirm"
      onCancel={(e) => {
        e.preventDefault() // let the caller decide, so state stays in sync
        if (!busy) onCancel()
      }}
    >
      <h2>{title}</h2>
      <div className="confirm-message">{message}</div>
      <div className="row confirm-actions">
        <button type="button" onClick={onCancel} disabled={busy} autoFocus>
          Cancel
        </button>
        <button type="button" className="danger" onClick={onConfirm} disabled={busy}>
          {busy ? 'Deleting...' : confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
