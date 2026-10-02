import { describe, expect, it } from 'vitest'

import { escaparHtml, formatearMensaje } from '@/lib/formato'

describe('formatearMensaje', () => {
  it('convierte la negrita de WhatsApp', () => {
    expect(formatearMensaje('*Total: $24.000*')).toBe('<strong>Total: $24.000</strong>')
    expect(formatearMensaje('Pedido *#0042* registrado ✅')).toBe(
      'Pedido <strong>#0042</strong> registrado ✅',
    )
  })

  it('escapa el HTML antes de formatear (el bot puede repetir lo que escribió el cliente)', () => {
    const malicioso = '⚠️ No recibimos «<img src=x onerror=alert(1)>»'
    const html = formatearMensaje(malicioso)
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;')
    expect(formatearMensaje('*<script>*')).toBe('<strong>&lt;script&gt;</strong>')
  })

  it('no une negritas entre líneas distintas', () => {
    expect(formatearMensaje('2 × 3 *a\nb* c')).toBe('2 × 3 *a\nb* c')
  })
})

describe('escaparHtml', () => {
  it('escapa los cinco caracteres especiales', () => {
    expect(escaparHtml(`&<>"'`)).toBe('&amp;&lt;&gt;&quot;&#39;')
  })
})
