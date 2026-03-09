/**
 * ConfirmModal.jsx – Modal de confirmação para ações destrutivas.
 *
 * Exibe um overlay com título, mensagem e botões Confirmar/Cancelar.
 * Fecha ao clicar fora ou pressionar Escape.
 */

import React, { useEffect, useRef } from "react";

export default function ConfirmModal({
  open,
  title = "Confirmar ação",
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  variant = "danger",
  onConfirm,
  onCancel,
}) {
  const overlayRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleKey(e) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="confirm-overlay"
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onCancel(); }}
    >
      <div className="confirm-modal">
        <div className="confirm-icon" data-variant={variant}>
          {variant === "danger" ? "⚠" : "ℹ"}
        </div>
        <h3 className="confirm-title">{title}</h3>
        <p className="confirm-message">{message}</p>
        <div className="confirm-actions">
          <button className="small secondary" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            className={`small ${variant === "danger" ? "danger" : ""}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
