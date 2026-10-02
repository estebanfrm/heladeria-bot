# Chatbot de pedidos para heladería — Planeación

> **Autor:** Esteban Giraldo Montenegro
> **Fecha:** 1 de octubre de 2026
> **Estado:** Planeación aprobada — se inicia con desarrollo gratuito (demo para portafolio) y posible migración a producción si la heladería lo adopta.

---

## Índice

1. [Resumen](#1-resumen)
2. [Contexto: cómo atienden hoy](#2-contexto-cómo-atienden-hoy)
3. [El menú y sus reglas](#3-el-menú-y-sus-reglas)
4. [Objetivos y alcance](#4-objetivos-y-alcance)
5. [Decisiones tomadas](#5-decisiones-tomadas)
6. [Arquitectura](#6-arquitectura)
7. [Flujo de la conversación](#7-flujo-de-la-conversación)
8. [Modelo de datos](#8-modelo-de-datos)
9. [Costos](#9-costos)
10. [Diseño para migrar fácil](#10-diseño-para-migrar-fácil)
11. [Fases y tareas](#11-fases-y-tareas)
12. [Riesgos y mitigación](#12-riesgos-y-mitigación)
13. [Pendientes por confirmar](#13-pendientes-por-confirmar)
14. [Fuentes](#14-fuentes)

---

## 1. Resumen

La heladería recibe pedidos por WhatsApp y los responde **manualmente**. El proyecto es un **chatbot que toma el pedido completo** (menú → productos → opciones → total → dirección → pago), lo registra en una base de datos y lo muestra en un **panel** para que la heladería lo prepare y despache, pasando a una persona cuando el bot no entienda.

**Estrategia:**

- **Etapa 1 — Demo gratis ($0/mes):** proyecto de portafolio con datos de ejemplo ("Heladería Demo"), chat web público + WhatsApp.
- **Etapa 2 — Producción (≈ USD 8–14/mes, a cargo de la heladería):** solo si la heladería lo quiere; se migra cambiando configuración, no código.

---

## 2. Contexto: cómo atienden hoy

Análisis de un chat real exportado (28/09/2026):

| Hora | Quién | Mensaje |
|---|---|---|
| 7:36 | Cliente | Hola buenas noches |
| 7:37 | Heladería | ¿Desea ver nuestro menú? |
| 7:38 | Heladería | *(envía menu.pdf)* |
| 7:53 | Cliente | Una copa queso, con brownie… y fresa. Y un banana split |
| 7:54 | Heladería | ¿Los dos sabores de brownie? / Elige 1 salsa y 1 topping |
| 7:56 | Cliente | Brownie, vainilla chips, brownie · frutos rojos · oreo |
| 7:56 | Heladería | ¿Y para la copa queso qué salsa y topping? |
| 7:57 | Heladería | Serían $24.000 · ¿Con cuánto cancela? · Dirección |
| 7:58 | Cliente | Por Nequi, me mandas el número · Cra 40 #96a18 |
| 7:58 | Heladería | Con gusto, ya se te prepara |
| 8:03 | Cliente | *(imagen — comprobante)* |
| 8:14 | Heladería | Ya salió tu pedido |

**Flujo actual:** saludo → PDF del menú → pedido en texto libre → preguntas de opciones → total → pago y dirección → comprobante → preparación → despacho.

**Problemas detectados:**

- **15 minutos** entre el envío del PDF y el pedido (el cliente tiene que leer un PDF de 6 páginas).
- Las opciones se preguntan **por partes** (sabores, luego salsa/topping de un producto, luego del otro).
- **No hay resumen** del pedido antes del total.
- "¿Con cuánto cancela?" y "dirección" se envían como mensajes sueltos.
- El cliente tuvo que **pedir el número de Nequi**.
- El comprobante se acepta **sin confirmación** explícita.
- No se informa **costo de domicilio** ni **tiempo estimado** de entrega.

**Validación de precios:** Copa queso $12.000 + Banana split $12.000 = **$24.000** ✔ (coincide con el chat; no se cobró domicilio aparte).

---

## 3. El menú y sus reglas

Fuente: `menu.pdf` de la heladería (6 páginas). Cada producto tiene **reglas configurables** (cuántos sabores, salsas, toppings, frutas incluye). Esto es el núcleo del bot.

### 3.1 Productos armables

| Producto | Precio | Sabores helado | Salsa | Topping | Otros incluidos |
|---|---|---|---|---|---|
| Waffle "arma a tu gusto" | $17.000 | 1 | 1 | 2 | 1 fruta, chantilly, waffle artesanal |
| Malteada 12 oz | $12.000 | 1 | 1 | 1 | chantilly |
| Malteada 16 oz | $14.000 | 1 | 1 | 1 | chantilly |
| Copa queso | $12.000 | 2 | 1 | 1 | queso, chantilly, galleta |
| Brownie con helado | $10.000 | 1 | 1 | 1 | brownie caliente, galleta |
| Ensalada de frutas | $16.000 | 1 | 1 | 1 | 5 frutas, queso |
| Banana split | $12.000 | 3 | 1 | 1 | banano, chantilly, galleta |

### 3.2 Productos fijos

| Producto | Precio | Descripción |
|---|---|---|
| Copa frutos rojos | $14.000 | Vainilla y fresa, melado y salsa de frutos rojos, chantilly, galleta |
| Copa ácida | $14.000 | Vainilla y maracuyá, pulpa y salsa de maracuyá, chantilly, galleta |
| Infantiles (Búho, Araña, Payaso, Ratón) | $6.000 | Elegir figura |
| Cono 1 bola / 2 bolas | $3.500 / $6.500 | Elegir sabor(es) |
| Estrella 1 / 2 / 3 bolas | $4.500 / $9.000 / $10.000 | Elegir sabor(es) |

### 3.3 Bebidas

| Producto | Precio | Variantes |
|---|---|---|
| Granizado | $8.000 | Maracuyá, lulo, mora, limón, mango viche |
| Granizado | $10.000 | Café, limonada de coco, limonada cerezada |
| Michelada con soda | $9.500 | Frutos rojos, frutos amarillos, frutos verdes |
| Michelada con ginger | $10.500 | Ídem |
| Michelada con cerveza | $12.500 | Ídem |

### 3.4 Opciones

| Tipo | Valores | Nota |
|---|---|---|
| Salsas (waffle) | Frutos rojos, chocolate (Hershey), maracuyá, leche condensada | |
| Salsas (malteada, copa queso) | Frutos rojos, maracuyá, lecherita | En el chat también ofrecieron **mora** y **fresa** → confirmar |
| Toppings (waffle) | Maní, barquillo, pepitas de colores, oreo triturado, gomitas, chips de chocolate, masmelos, M&M | |
| Toppings (malteada, copa queso) | Oreo, maní, lluvia de colores, pepitas de colores | |
| Frutas (waffle) | Fresa, manzana, banano | |
| Sabores de helado (11) | Vainilla chips, vainilla, brownie, barrilete, maracuyá, mandarina limón, fresa, lulo, yogurt frutos rojos, chocolate, ron con pasas | Confirmados con la heladería (02/10/2026) |

> Las listas de salsas/toppings **varían por producto**, así que el modelo de datos debe permitir asociar un conjunto de opciones a cada producto.

### 3.5 Adicionales

| Adicional | Precio |
|---|---|
| Topping | $1.700 |
| Fruta | $1.800 |
| Chantilly | $3.000 |
| Queso | $3.000 |
| Bola de helado | $3.000 |

### 3.6 Medios de pago

Bancolombia, Davivienda, Nequi, Daviplata, datáfono, efectivo.
⚠️ En el **demo público se usan números de cuenta ficticios**; los reales solo en producción.

---

## 4. Objetivos y alcance

### Objetivos

- Reducir el tiempo de toma de pedido (hoy ≈ 20 min por pedido de chat).
- Eliminar errores de opciones faltantes y de cálculo del total.
- Que la heladería vea todos los pedidos en un solo lugar con su estado.
- Proyecto de portafolio que demuestre: backend FastAPI, integración con API oficial de WhatsApp, IA aplicada, frontend Vue, Docker.

### Dentro del alcance (MVP)

1. Saludo y menú interactivo (listas/botones de WhatsApp en vez de PDF).
2. Pedido en texto libre interpretado por IA → validado por código.
3. Preguntar **en un solo mensaje** todas las opciones faltantes de cada producto.
4. Adicionales con precio.
5. Resumen del pedido + total calculado por código.
6. Dirección + medio de pago en un solo paso; envío automático de la cuenta elegida.
7. Recepción de comprobante (imagen) → confirmación humana desde el panel.
8. Notificaciones de estado al cliente ("en preparación", "ya salió tu pedido").
8b. **Resumen del pedido por WhatsApp al personal** (quien prepara y despacha), con comprobante y botones para cambiar el estado — ver sección 7.1.
9. Paso a humano (cliente lo pide o el bot no entiende 2 veces).
10. Panel web: pedidos por estado, editar menú, marcar agotados.
11. Chat web público (para el portafolio) usando el mismo motor.

### Fuera del alcance (por ahora)

- Pago nivel 2 (lectura del comprobante con IA) y nivel 3 (pasarela Wompi/Bold).
- Campañas de marketing / mensajes masivos.
- Programa de fidelización, reportes avanzados.
- Facturación electrónica.

---

## 5. Decisiones tomadas

| # | Decisión | Motivo |
|---|---|---|
| D1 | **Desarrollo gratis primero (demo de portafolio)**, migración posterior si la heladería lo adopta | Cero costo mientras se valida |
| D2 | **WhatsApp Cloud API oficial** (no librerías no oficiales como whatsapp-web.js/Baileys) | Evita bloqueo del número; mismo código sirve en producción |
| D3 | Canal WhatsApp del demo: **número de prueba de Meta** (hasta 5 destinatarios registrados). Los visitantes del portafolio prueban el **chat web**; WhatsApp se muestra en video | Gratis y sin SIM; 5 números bastan para desarrollo y demostraciones. El número secundario de Esteban queda como plan B |
| D4 | **FastAPI + PostgreSQL + Vue + Docker** (código propio, no n8n) | La lógica del pedido es compleja; demuestra más en el portafolio; n8n Cloud sale más caro por ejecuciones |
| D5 | **"La IA interpreta, el código decide"** | La IA convierte texto → JSON; precios, reglas y validación los hace el backend. El bot nunca inventa sabores ni precios |
| D6 | **IA intercambiable** por configuración | Demo: capa gratis (Gemini/Groq) u Ollama local. Producción: GPT-5.6 Luna, con Claude Haiku 4.5 de respaldo |
| D7 | **Botones/listas para opciones cerradas**, IA solo para texto libre | Menos llamadas a la IA = menos costo y menos errores |
| D8 | **Pago nivel 1 (manual) en el MVP:** el bot envía cuenta + monto, reenvía el comprobante al personal y este confirma con un botón tras revisar Nequi. Niveles 2 (IA lee comprobante) y 3 (pasarela) quedan como mejoras futuras, detrás de una interfaz `ProveedorPago` | Simple, $0, sin requisitos legales; la confirmación humana es necesaria de todos modos sin pasarela |
| D9 | **Datos ficticios en el demo** ("Heladería Demo", cuentas falsas) salvo permiso explícito de la heladería | Privacidad y uso de marca |
| D10 | **El personal recibe cada pedido por WhatsApp** con botones de estado; el panel web queda para menú, historial y modo humano | Es donde ya trabajan; no necesitan tener el panel abierto |

### Plan B: número secundario (D3)

Solo si más adelante se quiere que cualquier persona escriba al bot por WhatsApp:

- El número **no puede estar activo en la app de WhatsApp** (personal o Business) al registrarlo en la Cloud API, salvo la modalidad de coexistencia. Si lo tiene, hay que eliminar esa cuenta de WhatsApp primero.
- Sin verificación de negocio, Meta limita los mensajes **iniciados por el negocio**, pero **responder a quien escribe** funciona normal — suficiente para el demo.
- Requiere poder recibir **SMS o llamada** para el código de verificación.
- Meta debe aprobar el **nombre visible** (ej. "Heladería Demo · Bot").

---

## 6. Arquitectura

```
                 ┌──────────────────────┐      ┌───────────────────────┐
  Cliente ──────►│ WhatsApp Cloud API   │      │ Chat web (Vue widget) │◄── Visitante
                 └──────────┬───────────┘      └───────────┬───────────┘
                            │ webhook                      │ REST/WebSocket
                            ▼                              ▼
                 ┌─────────────────────────────────────────────────────┐
                 │                 Backend FastAPI                     │
                 │  ┌─────────────┐   ┌──────────────────────────────┐ │
                 │  │ Adaptadores │──►│ Motor de conversación        │ │
                 │  │ de canal    │   │ (máquina de estados)         │ │
                 │  └─────────────┘   └──────┬──────────────┬────────┘ │
                 │                           │              │          │
                 │              ┌────────────▼───┐   ┌──────▼───────┐  │
                 │              │ Servicio de IA │   │ Carrito /    │  │
                 │              │ texto → JSON   │   │ reglas menú  │  │
                 │              │ (proveedor     │   │ / precios    │  │
                 │              │  intercambiable)│  └──────────────┘  │
                 │              └────────────────┘                     │
                 └──────────────────────────┬──────────────────────────┘
                                            ▼
                                   ┌─────────────────┐
                                   │   PostgreSQL    │
                                   └────────▲────────┘
                                            │
                              ┌─────────────┴────────────┐
                              │ Panel heladería (Vue)    │
                              │ pedidos · menú · agotados│
                              └──────────────────────────┘
```

### Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Base de datos | PostgreSQL |
| Frontend (panel + chat web) | Vue 3, Vite |
| IA | Capa de abstracción propia; proveedores: Gemini / Groq / Ollama (demo), OpenAI Luna / Anthropic Haiku (producción) |
| Mensajería | WhatsApp Cloud API (Meta Graph API) |
| Contenedores | Docker, docker-compose |
| Pruebas | pytest (motor, carrito, parser de IA con casos reales) |

### Herramientas de desarrollo

| Para qué | Herramienta |
|---|---|
| Editor | VS Code + extensiones: Python, Pylance, Ruff, Vue - Official, Docker, ESLint, Prettier |
| Control de versiones | Git + GitHub (`estebanfrm`) |
| Contenedores | Docker Desktop (con WSL 2 en Windows) |
| Python | Python 3.12 + **uv** (entornos y dependencias) |
| Node | Node.js 22 LTS + pnpm |
| Base de datos local | PostgreSQL 16 en Docker + DBeaver como cliente gráfico |
| Exponer el webhook local a Meta | **Cloudflare Tunnel** (`cloudflared`) o ngrok |
| Probar la API | Swagger de FastAPI (`/docs`) + Bruno |
| IA local (opcional) | Ollama (si el equipo tiene ≥ 16 GB de RAM) |
| Calidad | pytest, Ruff, pre-commit |
| CI | GitHub Actions (lint + tests en cada push) |

**Librerías backend:** fastapi, uvicorn, sqlalchemy 2, alembic, psycopg 3, pydantic 2, pydantic-settings, httpx, google-genai / groq (IA), pytest.
**Librerías frontend:** Vue 3, Vite, TypeScript, Vue Router, Pinia, Tailwind CSS.

**Cuentas necesarias (todas gratis):** GitHub, Meta for Developers (+ portafolio de Meta Business), Google AI Studio (Gemini), Groq, Render, Neon, Vercel.

### Principio clave: "la IA interpreta, el código decide"

```
"una copa queso con brownie y fresa, frutos rojos y maní"
                    │  IA
                    ▼
{ "items": [ { "producto": "copa_queso",
               "sabores": ["brownie", "fresa"],
               "salsa": "frutos_rojos",
               "topping": "mani" } ] }
                    │  Código
                    ▼
Valida contra el menú → pregunta lo que falte → calcula $12.000
```

---

## 7. Flujo de la conversación

### Estados

```
INICIO
  └─► SALUDO (menú interactivo: categorías)
        └─► TOMANDO_PEDIDO  ◄────────────────┐
              │ (texto libre o selección)    │
              ▼                              │
            COMPLETANDO_OPCIONES             │ "agregar algo más"
              │ (pregunta todo lo faltante   │
              │  de cada ítem, en 1 mensaje) │
              ▼                              │
            RESUMEN ─── "agregar/cambiar" ───┘
              │ "confirmar"
              ▼
            DATOS_ENTREGA (dirección o recoger + medio de pago)
              ▼
            ESPERANDO_PAGO (envía cuenta; espera comprobante)
              │  efectivo/datáfono → salta
              ▼
            PEDIDO_CONFIRMADO ──► (WhatsApp personal o panel) EN_PREPARACION ──► ENVIADO ──► FIN

  En cualquier estado:  "asesor"/2 fallos → HUMANO (bot se pausa)
                        inactividad 30 min → recordatorio → cancelado
```

### Ejemplo de conversación objetivo

> **Cliente:** Hola
> **Bot:** ¡Hola! 🍦 Bienvenido a Heladería Demo. ¿Qué se te antoja? *[Ver menú]* *[Hacer pedido]* *[Hablar con alguien]*
> **Cliente:** una copa queso con brownie y fresa y un banana split
> **Bot:** ¡Listo! Para completar:
> • **Copa queso** (brownie, fresa): elige 1 salsa *(frutos rojos / maracuyá / lecherita)* y 1 topping *(oreo / maní / lluvia / pepitas)*
> • **Banana split**: elige 3 sabores, 1 salsa y 1 topping
> **Cliente:** copa: frutos rojos y maní. banana: brownie, vainilla chips, brownie, frutos rojos, oreo
> **Bot:** 📝 **Tu pedido:**
> 1× Copa queso — brownie, fresa · frutos rojos · maní — $12.000
> 1× Banana split — brownie, vainilla chips, brownie · frutos rojos · oreo — $12.000
> **Total: $24.000** *[Confirmar]* *[Agregar algo]* *[Cambiar]*
> **Cliente:** *[Confirmar]*
> **Bot:** ¿A qué dirección lo enviamos y cómo pagas? *[Nequi]* *[Daviplata]* *[Bancolombia]* *[Efectivo]*
> **Cliente:** Cra 40 #96a18, Nequi
> **Bot:** Envía $24.000 al Nequi **300 000 0000** a nombre de Heladería Demo y mándame el comprobante 📸
> **Cliente:** *(imagen)*
> **Bot:** ¡Recibido! En cuanto confirmemos el pago empezamos a preparar tu pedido ✅
> *(panel: pago verificado → en preparación → enviado)*
> **Bot:** 🛵 ¡Tu pedido ya salió! Llega en aprox. 20 min.


### 7.1 Notificación al personal (quien prepara y despacha)

Cada pedido confirmado se envía por WhatsApp a los números del personal (configurables en `.env` / panel). Los botones actualizan el pedido y avisan al cliente automáticamente.

```
🍦 PEDIDO #0042 — 7:57 p. m.
👤 Laura · 300 123 4567
📍 Cra 40 #96a18
💳 Nequi — comprobante adjunto ⬇️

1× Copa queso — $12.000
   Sabores: brownie, fresa
   Salsa: frutos rojos · Topping: maní
1× Banana split — $12.000
   Sabores: brownie, vainilla chips, brownie
   Salsa: frutos rojos · Topping: oreo

TOTAL: $24.000

[✅ Pago OK]  [❌ Pago no llega]  [🛵 Despachado]
```

| Botón | Acción en el sistema | Mensaje al cliente |
|---|---|---|
| ✅ Pago OK | `PAGO_VERIFICADO → EN_PREPARACION` | "Pago confirmado, ya preparamos tu pedido" |
| ❌ Pago no llega | Marca alerta; pasa la conversación a humano | "No vemos el pago aún, ¿nos reenvías el comprobante?" |
| 🛵 Despachado | `ENVIADO` | "¡Tu pedido ya salió! Llega en aprox. X min" |

**Reglas de WhatsApp a tener en cuenta:**

- **Ventana de 24 h:** los mensajes que el negocio inicia fuera de las 24 h desde el último mensaje de esa persona requieren una **plantilla aprobada** (categoría utilidad), que se cobra por mensaje. Dentro de la ventana, el texto libre y las plantillas de utilidad son **gratis**.
- **Truco del turno:** al iniciar el turno, el personal le escribe "turno" al bot → se abre la ventana de 24 h y todas las notificaciones del día salen gratis. Cada toque de botón también renueva la ventana.
- **Respaldo:** si la ventana está cerrada, el bot usa la plantilla `nuevo_pedido` (cuesta una fracción de centavo de dólar) y el pedido igual aparece en el panel.
- **Número de prueba:** el teléfono del personal debe ser uno de los 5 números registrados.
- **Producción:** el número del personal **no puede ser el mismo número del bot**; se usan los celulares personales de quienes atienden.
- Se envía a **números individuales**, no a grupos de WhatsApp.


### 7.2 Comprobación del pago (Nequi y transferencias)

Un pantallazo de comprobante **se puede editar o reutilizar**, así que sin pasarela la confirmación final la hace una persona mirando la app de Nequi/banco. El sistema se diseña con una interfaz `ProveedorPago` para pasar de un nivel a otro sin reescribir.

| Nivel | Cómo funciona | Costo | Uso |
|---|---|---|---|
| 1. Manual | El bot envía cuenta + monto exacto; reenvía el comprobante al personal; el personal revisa Nequi y toca **✅ Pago OK** | $0 | **✔ Elegido para el MVP** |
| 2. Asistido por IA | La IA lee el comprobante (monto, fecha/hora, destinatario, referencia) y el código lo valida; el personal confirma con un toque | $0 extra (1 llamada de visión) | Mejora futura |
| 3. Pasarela (Wompi o Bold) | El bot genera un link/cobro con la referencia del pedido; el cliente paga con Nequi/PSE/tarjeta; el webhook confirma solo | Sandbox gratis; producción ≈ 1,79 % por pago con Nequi (≈ $430 en un pedido de $24.000) | Mejora futura (sandbox para demo; producción opcional) |

**Flujo elegido (nivel 1):**

1. El cliente elige medio de pago → el bot envía la cuenta correspondiente y el **monto exacto**, y pide el comprobante.
2. Efectivo o datáfono → no se pide comprobante; el pedido pasa directo a preparación con nota "cobrar $X al entregar".
3. Llega la imagen → el bot responde "Recibido, estamos verificando" y la reenvía al personal junto al resumen, con **[✅ Pago OK] [❌ Pago no llega]**.
4. ✅ → `PAGO_VERIFICADO` y aviso al cliente. ❌ → el bot pide reenviar el comprobante y la conversación pasa a humano.
5. Sin comprobante a los 15 min → recordatorio; a los 60 min → pedido cancelado.

**Validaciones del nivel 2 (las hace el código, no la IA):**

- Monto del comprobante = total del pedido.
- Destinatario = número/cuenta de la heladería.
- Fecha y hora posteriores a la creación del pedido (y no más de ~1 h después).
- **Referencia no usada antes** (detecta el mismo pantallazo enviado dos veces).
- La imagen parece un comprobante de Nequi/banco.

Resultado en el mensaje al personal:

```
💳 Comprobante Nequi — análisis automático
✅ Monto: $24.000 (coincide)
✅ Destino: 300 000 0000 (cuenta de la heladería)
✅ Hora: 7:59 p. m. (pedido creado 7:57 p. m.)
⚠️ Referencia M1234567 ya usada en el pedido #0031
→ Verifica en la app de Nequi antes de confirmar
[✅ Pago OK]  [❌ Pago no llega]
```

**Nivel 3 — requisitos para producción:** cuenta de comercio en la pasarela (RUT, cuenta bancaria, documentos del negocio), aprobación y la comisión por transacción. Para desarrollo basta el **sandbox**, que simula pagos aprobados y rechazados sin dinero real.

**Descartado:** leer las notificaciones push de Nequi desde el celular de la heladería con apps reenviadoras — frágil y riesgoso para la seguridad de la cuenta.

**A futuro:** Bre-B (pagos inmediatos del Banco de la República) y las pasarelas que lo integren podrían permitir confirmación automática con menor costo; revisar cuando se pase a producción.

---

## 8. Modelo de datos

```
producto           (id, nombre, categoria, precio, descripcion, activo,
                    num_sabores, num_salsas, num_toppings, num_frutas)
grupo_opcion       (id, tipo: sabor|salsa|topping|fruta|variante, nombre)
opcion             (id, grupo_id, nombre, disponible)
producto_grupo     (producto_id, grupo_id, cantidad)   -- qué listas aplica a cada producto
adicional          (id, nombre, precio)
medio_pago         (id, nombre, numero_cuenta, titular, activo)

cliente            (id, telefono, nombre, ultima_direccion, acepto_datos, creado)
conversacion       (id, cliente_id, canal: whatsapp|web, estado, contexto_json,
                    modo: bot|humano, actualizado)
mensaje            (id, conversacion_id, origen: cliente|bot|humano, texto, media_url, creado)

pedido             (id, cliente_id, conversacion_id, estado, subtotal, domicilio, total,
                    direccion, medio_pago_id, comprobante_url, creado)
item_pedido        (id, pedido_id, producto_id, cantidad, precio_unitario, notas)
item_opcion        (item_id, opcion_id)
item_adicional     (item_id, adicional_id, cantidad, precio)
```

Estados del pedido: `BORRADOR → PENDIENTE_PAGO → PAGO_VERIFICADO → EN_PREPARACION → ENVIADO → ENTREGADO` (+ `CANCELADO`).

---

## 9. Costos

### Etapa 1 — Demo / portafolio: **$0/mes**

| Pieza | Opción gratis | Limitación |
|---|---|---|
| WhatsApp | Cloud API + número de prueba de Meta | Solo 5 destinatarios registrados; responder es gratis |
| IA | Capa gratis de Gemini API o Groq; Ollama local en desarrollo | Límites de peticiones; en capa gratis de Gemini, Google puede usar los datos |
| Backend | Render (plan gratis) u Oracle Cloud Always Free | Render "se duerme": 1er mensaje tarda ~30–60 s |
| Base de datos | Neon o Supabase (plan gratis) | Poco espacio, suficiente para demo |
| Frontend | Vercel (donde ya está el portafolio) | — |
| Dominio | Subdominios gratis con HTTPS (`onrender.com`, `vercel.app`) | — |

*Las capas gratis cambian; verificar condiciones al registrarse.*

**Protecciones de costo:** límite de mensajes por sesión en el chat web (ej. 20), tope de gasto en la consola del proveedor de IA si se usa uno pago.

### Etapa 2 — Producción (si la heladería lo adopta): **≈ USD 8–14/mes**

| Concepto | Costo / mes |
|---|---|
| WhatsApp Cloud API (respuestas dentro de 24 h) | $0 |
| IA — GPT-5.6 Luna (~900 pedidos/mes, ~3 llamadas por pedido) | ≈ USD 2–4 |
| VPS (FastAPI + PostgreSQL + panel) | ≈ USD 5–7 |
| Dominio | ≈ USD 1 (≈ USD 12/año) |
| **Total** | **≈ USD 8–14 (≈ COP 30.000–55.000)** |

Referencias: con Claude Haiku 4.5 el total sería ≈ USD 15–25/mes. n8n Cloud sumaría €20–50/mes (y el plan de €20 no alcanza las ~9.000 ejecuciones/mes estimadas). Mensajes de marketing iniciados por el negocio se cobran aparte por mensaje.

*Conversión aproximada: USD 1 ≈ COP 4.000.*

---

## 10. Diseño para migrar fácil

Reglas obligatorias desde el día 1:

1. **Docker** — la misma imagen corre en Render, VPS o local.
2. **Toda la configuración en `.env`** — nada de credenciales ni URLs en el código.
3. **PostgreSQL estándar + Alembic** — migrar datos con `pg_dump` / `pg_restore`.
4. **IA detrás de una interfaz** — `IA_PROVIDER` y `IA_MODEL` en `.env`.
5. **Canales como adaptadores** — WhatsApp y chat web comparten el motor.
6. **Menú en la base de datos**, cargado desde archivos semilla: `seeds/demo.json` y `seeds/heladeria.json`.
7. **Nada exclusivo de un proveedor** — Supabase/Neon solo como Postgres.

### Variables de entorno previstas (`.env.example`)

```env
# App
APP_ENV=development
APP_BASE_URL=http://localhost:8000
SEED_FILE=seeds/demo.json

# Base de datos
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/heladeria

# WhatsApp Cloud API
WA_PHONE_NUMBER_ID=
WA_ACCESS_TOKEN=
WA_VERIFY_TOKEN=
WA_APP_SECRET=

# IA
IA_PROVIDER=gemini        # gemini | groq | ollama | openai | anthropic
IA_MODEL=
IA_API_KEY=

# Límites
WEB_CHAT_MAX_MSGS_PER_SESSION=20
```

### Qué cambia al migrar

| Demo | → | Producción |
|---|---|---|
| Render | misma imagen Docker | VPS |
| Neon | `pg_dump` | PostgreSQL en el VPS |
| Gemini gratis | `.env` | GPT-5.6 Luna |
| Número de prueba de Meta | `.env` + Meta | Número de la heladería |
| `seeds/demo.json` | `.env` | `seeds/heladeria.json` |

### Pasos no técnicos de la migración

| Paso | Tiempo aprox. |
|---|---|
| La heladería crea **su propia** cuenta Meta Business y la verifica | días – 2 semanas |
| Registrar su número en la API (coexistencia con la app o migración) | 1 día |
| Aprobación del nombre visible | 1–3 días |
| Cargar menú real, sabores, cuentas, domicilio | horas |
| Piloto con clientes reales + capacitación del panel | 1 semana |
| Política de privacidad (Meta + Ley 1581 de 2012) | horas |

---

## 11. Fases y tareas

### Fase 0 — Preparación
- [x] Analizar chat real y menú
- [x] Definir arquitectura, costos y estrategia
- [x] Lista de sabores de helado (11 sabores)
- [ ] Crear repositorio en GitHub (`estebanfrm/heladeria-bot` o similar)
- [x] Estructura del repo, `docker-compose.yml`, `.env.example`
- [x] `seeds/demo.json` con el menú estructurado + validación (`app/menu/schema.py` + test)

### Fase 1 — Núcleo (sin WhatsApp)
- [ ] Modelos SQLAlchemy + migraciones Alembic
- [ ] Carga de semillas
- [ ] Carrito y reglas: validación de opciones, adicionales, total
- [ ] Servicio de IA (interfaz + 1 proveedor) → texto a JSON
- [ ] Motor de conversación (máquina de estados)
- [ ] Endpoint de prueba `/chat` + pruebas con pytest usando los mensajes del chat real

### Fase 2 — Canales
- [ ] Chat web (widget Vue) contra `/chat`
- [ ] Configurar app en Meta for Developers + número de prueba
- [ ] Webhook de WhatsApp (verificación, firma, recepción, envío)
- [ ] Mensajes interactivos (listas y botones)
- [ ] Notificación de pedidos al personal (resumen + comprobante + botones de estado)
- [ ] Comando "turno" para abrir la ventana de 24 h del personal
- [ ] Pago nivel 1: enviar cuenta + monto según medio elegido, recibir comprobante, reenviarlo al personal con botones
- [ ] Recordatorio si no llega comprobante en 15 min; cancelar a los 60 min
- [ ] Plantilla de utilidad "nuevo_pedido" (respaldo si la ventana está cerrada)
- [ ] Generar token permanente (usuario del sistema) — el token de prueba vence a las 24 h
- [ ] Registrar los 5 números de prueba

### Fase 3 — Panel
- [ ] Login simple para la heladería
- [ ] Tablero de pedidos por estado (con notificación al cliente al cambiar)
- [ ] Verificar comprobante
- [ ] Editar menú y marcar agotados
- [ ] Modo humano: ver y responder conversaciones desde el panel

### Fase 4 — Publicación del demo
- [ ] Desplegar backend (Render), BD (Neon), frontend (Vercel)
- [ ] Límite de mensajes y tope de gasto
- [ ] Política de privacidad y aviso de tratamiento de datos en el bot
- [ ] README con arquitectura, capturas y video de 60 s
- [ ] Publicar en portafolio y LinkedIn

### Fase 5 — Producción (opcional)
- [ ] Presentar demo a la heladería
- [ ] Ejecutar pasos de migración (sección 10)
- [ ] Piloto 1 semana → ajustes → lanzamiento

---

## 12. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| La IA interpreta mal un pedido | Validación por código + resumen obligatorio antes de confirmar + pruebas con mensajes reales |
| Inventa productos o precios | La IA solo devuelve IDs del menú; precios siempre desde la BD |
| Abuso del chat público (gasto) | Límite por sesión, rate limiting, tope de gasto |
| Capa gratis cambia o desaparece | IA intercambiable por `.env`; Ollama como alternativa |
| Render dormido retrasa el webhook | Aceptable en demo; en producción, VPS siempre encendido |
| Comprobantes falsos | Confirmación humana (botón en WhatsApp del personal o panel) |
| Número bloqueado por Meta | Solo API oficial; sin mensajes masivos no solicitados |
| Datos personales (teléfono, dirección) | Autorización de tratamiento de datos (Ley 1581), política de privacidad, mínimos datos necesarios |
| Uso de marca/datos reales sin permiso | Demo con "Heladería Demo" y cuentas ficticias |

---

## 13. Pendientes por confirmar

**Con la heladería (o definir para el demo):**
- [x] Lista completa de sabores de helado
- [ ] ¿Salsas mora y fresa aplican a qué productos? (aparecen en el chat, no en el menú)
- [ ] Costo y zonas de domicilio; ¿recogen en el local?
- [ ] Horario de atención
- [ ] Tiempo promedio de preparación y entrega
- [ ] ¿Cuántos pedidos por día reciben?
- [ ] ¿Se pueden pedir adicionales en cualquier producto?
- [ ] Permiso para usar nombre/menú real en el portafolio

**Técnicos:**
- [ ] Elegir proveedor de IA gratis para el demo (probar Gemini vs Groq con los casos reales)
- [ ] Nombre del repositorio

---

## 14. Fuentes

- [WhatsApp Business Platform — Pricing (Meta)](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)
- [Pasarelas de pago en Colombia 2026 — tarifas (Guía de Software)](https://www.guiadesoftware.com/blog/mejor-pasarela-pago-colombia)
- [Claude API Pricing (Anthropic)](https://platform.claude.com/docs/en/about-claude/pricing)
- [GPT-5.6 Luna — precio y posicionamiento (vpsranking)](https://vpsranking.com/news/ai/ai-2026-07-30-openai-gpt-56-price-performance/)
- [n8n Pricing 2026 (Sliplane)](https://frontend.sliplane.io/blog/n8n-pricing)
- Chat exportado de WhatsApp (28/09/2026) y `menu.pdf` de la heladería
