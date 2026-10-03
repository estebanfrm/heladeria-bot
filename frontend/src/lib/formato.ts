const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

export function escaparHtml(texto: string): string {
  return texto.replace(/[&<>"']/g, (caracter) => ESCAPES[caracter] ?? caracter)
}

/**
 * Formato de WhatsApp (*negrita*) a HTML seguro para v-html.
 * Primero se escapa TODO (el texto del bot puede repetir lo que escribió el cliente)
 * y solo después se agrega la negrita.
 */
export function formatearMensaje(texto: string): string {
  return escaparHtml(texto).replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>')
}
