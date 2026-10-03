# 🍦 Heladería Bot

Chatbot de pedidos por WhatsApp para una heladería: toma el pedido completo
(menú → productos → opciones → total → dirección → pago), lo envía al personal
con botones de estado y lo registra en un panel.

> Proyecto en desarrollo. Ver la planeación completa en [`PLANEACION.md`](PLANEACION.md).

## Stack

FastAPI · PostgreSQL · SQLAlchemy · Alembic · Vue 3 · Docker · WhatsApp Cloud API · IA intercambiable (Gemini / Groq / Ollama / OpenAI / Anthropic)

**Principio:** la IA interpreta el texto del cliente; el código valida contra el menú y calcula los precios.

## Estructura

```
├── backend/            API FastAPI
│   ├── app/
│   │   ├── config.py       Configuración desde .env
│   │   ├── main.py         Endpoints (/health, /menu) + routers de canales
│   │   ├── models/         Modelos SQLAlchemy (menú, conversaciones, pedidos)
│   │   ├── menu/           Esquema del seed y carga a la BD
│   │   ├── pedidos/        Carrito (reglas y montos) y registro de pedidos
│   │   ├── ia/             IA intercambiable: prompt, proveedores, evaluación
│   │   ├── conversacion/   Motor (máquina de estados) y textos del bot
│   │   └── canales/        Adaptadores: chat web (/chat); WhatsApp en la Fase 2
│   ├── migrations/         Alembic
│   └── tests/
├── frontend/           Panel + chat web (Vue, Fase 2)
├── seeds/
│   └── demo.json       Menú de "Heladería Demo" (datos ficticios de pago)
├── docker-compose.yml
└── .env.example
```

## Correr en local

```bash
cp .env.example .env

# Opción A: todo en Docker
docker compose up --build
# → http://localhost:8000/health y http://localhost:8000/docs

# Opción B: backend local con uv (BD en Docker)
# (si ya tienes otro Postgres en el 5432, cambia DB_PORT y DATABASE_URL en .env)
docker compose up -d db
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.menu.carga     # carga seeds/demo.json en la BD
uv run uvicorn app.main:app --reload

# Chat web (otra terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

## Probar el bot

Con el backend arriba, abre http://localhost:8000/docs y usa `POST /chat`:

```json
{"texto": "Una copa queso con brownie y fresa y un banana split"}
```

La respuesta trae una `sesion`; mándala en los siguientes mensajes para seguir la misma conversación.
Los botones se envían como `{"sesion": "...", "boton": "confirmar"}`. Para el texto libre hace falta una IA
configurada en `.env`: Gemini (`IA_API_KEY`) o, en local y gratis, Ollama:

```env
IA_PROVIDER=ollama
IA_MODEL=gemma4:12b
IA_REASONING_EFFORT=none   # sin esto el modelo "razona" y tarda ~2 min por mensaje
```

Sin IA, `/health` muestra `"ia": "no configurada"` y solo responden los botones.

## Conectar WhatsApp en local (número de prueba de Meta)

1. En Meta → Conectar en WhatsApp → Paso 1, obtener el ID del número y generar el
   identificador de acceso. Guardarlos en `.env` como `WA_PHONE_NUMBER_ID` y
   `WA_ACCESS_TOKEN`. Guardar el secreto de Información básica de la aplicación como
   `WA_APP_SECRET`. `WA_VERIFY_TOKEN` es una cadena propia que debe coincidir con Meta.
2. Con la BD y el menú ya preparados, desde `backend/`:
   `uv run uvicorn app.whatsapp_demo:app --host 127.0.0.1 --port 8001 --no-access-log`.
   Esta entrada publica únicamente `/webhook/whatsapp`; el chat web sigue en el puerto 8000.
3. Abrir un túnel de prueba con el cliente oficial de Cloudflare:
   `cloudflared tunnel --url http://127.0.0.1:8001`.
   La URL es temporal y cambia al reiniciar el túnel.
4. En Meta → Paso 2, usar `https://<URL-del-tunel>/webhook/whatsapp` como URL de
   devolución de llamada y el valor de `WA_VERIFY_TOKEN` como identificador de
   verificación; verificar y guardar, y suscribir el campo `messages`.
5. Comprobar que la app también está vinculada a la cuenta de WhatsApp Business:
   `GET /<WABA_ID>/subscribed_apps` en la Graph API debe incluir el ID de nuestra app.
   Si falta, `POST /<WABA_ID>/subscribed_apps` con el token de acceso de esa app la
   vincula. Activar el campo `messages` por sí solo no completa esta vinculación.
6. Reiniciar el servidor del puerto 8001 después de cambiar `.env`. Registrar y
   verificar el destinatario de prueba en Meta antes de probar el bot desde ese teléfono.

El panel de Meta puede requerir publicar la aplicación para entregar eventos fuera
de sus pruebas del panel. La verificación del webhook por sí sola no demuestra que
los mensajes reales lleguen al bot. No usar este túnel temporal para producción.

Los secretos permanecen en `.env`, excluido de Git. Los binarios y registros locales
de esta configuración se guardan en `.local/`, también excluido de Git.

Si el botón «Nuevo chat» aparece recibido en el historial pero no llega el saludo,
revisar el envío a Meta: el token temporal puede haber vencido aunque los webhooks
sigan entrando. El error 190 con subcódigo 463 indica una sesión expirada. Generar
un identificador nuevo en el Paso 1, actualizar `WA_ACCESS_TOKEN` en `.env` y reiniciar
el backend. Después se puede pulsar de nuevo el botón, sin recuperar el carrito anterior.
El token permanente para producción sigue pendiente.

### Menú en PDF

Guardar el archivo en `.local/menu.pdf` y configurar `WA_MENU_PDF_FILE=.local/menu.pdf`
en `.env`. Reiniciar el backend. En WhatsApp, el botón de menú o el mensaje «menú»
envía ese documento con un texto breve; el chat web conserva la carta en texto.
El cliente sube el archivo mediante la API de medios de Meta y reutiliza su ID
durante un día, o lo vuelve a subir si cambia el PDF. Para Docker, montar el archivo
como volumen y configurar su ruta dentro del contenedor.

Si un chat quedó en modo humano, «bot» o «volver al bot» reanuda las respuestas
automáticas conservando el carrito y los datos de entrega. Ese modo todavía no
notifica a un asesor. Durante el paso de entrega, direcciones como «Cra 8 #80-70»
se reconocen directamente; «Cra 8» pide completar el número sin contar como fallo de IA.
Las variantes con espacios, como «CRA 40 96A 02», también se reconocen. Un formato
compacto como «CRA 40 96a02» pide confirmar o corregir y conserva el texto original;
no registra el pedido hasta confirmarlo. Si la IA falla durante la entrega, se
solicitan los datos que falten sin cambiar automáticamente el chat a modo humano.

### Cierre por inactividad

`CHAT_INACTIVITY_MINUTES=30` cierra la sesión tras 30 minutos sin interacción.
El servidor revisa cada `CHAT_INACTIVITY_POLL_SECONDS=60` segundos, por lo que el
aviso puede llegar hasta un minuto después. El temporizador se ejecuta tanto con
`app.main` como con `app.whatsapp_demo`; requiere mantener el servidor encendido.
`CHAT_INACTIVITY_WORKER_ENABLED=false` desactiva la revisión periódica, pero al
recibir un mensaje el motor sigue comprobando si la sesión ya venció.

El cierre descarta el carrito sin registrar, conserva historial y pedidos, y ofrece
«Nuevo chat». El usuario debe pulsar ese botón o escribir «nuevo chat» para comenzar
con el saludo y un carrito vacío. Los botones del pedido anterior no lo reactivan.
Los chats en `ESPERANDO_PAGO` siguen abiertos para recibir el comprobante; su plazo
de pago y recordatorios se implementarán aparte.

El aviso queda pendiente si falla el envío y se reintenta. Se omite si la sesión
se reabrió o si ya terminó la [ventana de respuesta de WhatsApp de 24 horas](https://whatsappbusiness.com/policy/).
El bloqueo de la conversación coordina los temporizadores y mensajes entrantes
cuando hay varios procesos. La sesión también vence al volver a escribir después
de una interrupción del servidor.

## Ejecutar pruebas

### Cambiar un pedido y conservar sus precios

El cliente puede pulsar «Cambiar pedido» o escribir «cambiar pedido», también después
de confirmar un pedido pendiente de pago. En efectivo o datáfono se permite mientras
no conste pago, comprobante o despacho. Se recuperan los productos y datos de entrega;
el bot presenta un nuevo resumen y guarda los cambios solo al confirmarlo, conservando
el número del pedido. «Mantener pedido» descarta el borrador de cambios.

El servidor vuelve a comprobar el estado al guardar. Un comprobante recibido durante
la edición se asocia al pedido original, conserva su importe y descarta el borrador.
Recibir una imagen o «ya pagué» nunca verifica el pago. Verificar comprobantes y
notificar al personal siguen pendientes en la Fase 3; «Hablar con alguien» activa
el modo humano, pero todavía no envía una notificación a un asesor.

Descuentos, cupones, promociones inventadas y roles administrativos escritos por
el cliente no alteran importes. Los precios y cuentas se toman del menú y la BD;
los campos de precio, total o estado generados por la IA se ignoran. Las cantidades
deben ser enteros positivos; `ORDER_MAX_UNITS=50` limita unidades y adicionales,
`ORDER_MAX_ITEMS=20` limita líneas de productos y `BOT_MAX_TEXT_CHARS=500` limita
el texto por mensaje. Los pedidos mayores requieren consultar al equipo.

Los errores ortográficos claros se interpretan con IA y se revisan en el resumen.
Las elecciones incompletas se preguntan y los productos inexistentes no se sustituyen
por otro. Una opción única que la IA entregue como texto se normaliza a una lista
de un elemento y conserva la validación contra el menú.

Para mezclas del menú, mencionar un ingrediente no selecciona automáticamente toda
la mezcla. «Todas maracuya» en cinco micheladas ofrece confirmar «Frutos amarillos
(maracuyá y lulo)» con un botón. «Sí» confirma esa propuesta si es única; luego se
muestra el resumen con las cinco unidades. No se ofrecen mezclas agotadas ni se
deduce una mezcla cuando varias comparten el mismo ingrediente.

### Evaluar mensajes con la IA real

Desde `backend/`, `uv run python -m app.ia.evaluar_robustez` ejecuta 28 escenarios
con el proveedor configurado. Usa siempre `seeds/demo.json`, clientes ficticios y
transacciones revertidas en `heladeria_test`; no envía WhatsApp ni registra pedidos
reales. Guarda mensajes, respuestas, JSON del modelo y resultados en
`.local/robustez.json`, excluido de Git. `--casos copa_keso malteada` permite repetir
casos concretos y `--salida ../.local/robustez-final.json` elige otro informe.

Si Ollama falla con `std::bad_alloc`, revisar memoria y caché antes de atribuirlo
a la interpretación. En este portátil se configuró `gemma4-heladeria:12b` a partir
de `gemma4:12b`, con `num_ctx=4096` y `num_batch=64`, y se inició el servidor con
`LLAMA_ARG_CACHE_RAM=0` y `LLAMA_ARG_CTX_CHECKPOINTS=0`. Es un ajuste local del mismo
modelo; debe conservarse al reiniciar Ollama. Los parámetros del modelo se pueden
configurar con su [API oficial de creación](https://docs.ollama.com/api/create).

### Pruebas automáticas

```bash
docker compose up -d db   # los tests de modelos/migraciones usan Postgres real (BD heladeria_test)
cd backend
uv run pytest
uv run ruff check .
```
