# Runbook del piloto real read-only

Este procedimiento ejecuta `invoice-intake` sobre un lote cerrado sin listar el
buzón, leer cuerpos de correo, modificar Gmail o escribir en Drive. El piloto
permanece en Shadow Mode.

## Precondiciones

- release instalada y auditorías verdes;
- proyecto generado con `agent-core`, `google-connectors`, `invoice-intake` y el
  agente `invoice-intake-shadow`;
- credencial OAuth externa con el único scope `gmail.readonly`;
- manifiesto cerrado validado;
- ground truth autorizado y separado si se van a publicar métricas;
- destino de ejecución fuera del repositorio.

La credencial nunca se escribe en el manifiesto, configuración, logs o base de
datos. El proveedor de secretos del despliegue la entrega en memoria como
`CredentialMaterial`.

## Manifiesto

El archivo `pilot-real-manifest.json` debe ser regular, no symlink, tener como
máximo 64 KiB y permisos `0600`. Cada caso contiene solo:

- `case_id` opaco;
- `provider: gmail`;
- `message_ref` y `attachment_ref` opacos;
- MIME esperado;
- propósito;
- fecha de autorización;
- estado del ground truth.

Los casos se ordenan por `case_id`, no se repiten y el `message_id` incluido en
la referencia del adjunto debe coincidir con `message_ref`. REAL-002 permanece
excluido mientras no exista una adquisición original verificable.

## Ensamblaje

1. Cargar el manifiesto con `load_pilot_manifest`.
2. Derivar la allowlist mediante `attachment_allowlist`.
3. Crear `GmailByteOnlyAttachmentClient` con esa allowlist.
4. Inyectarlo en `GmailReadOnlyAdapter` con permiso exclusivo `content.read`.
5. Envolver el adapter con `ManifestBoundGmailConnector`.
6. Ejecutar `InvoiceIntakeShadowBehavior` mediante `run_agent`.
7. Construir el reporte A-E con `build_integrity_report`.
8. Persistir únicamente el execution record, Review Card, campos autorizados y
   reporte A-E saneado.

`ManifestBoundGmailConnector` resuelve mensajes localmente desde el manifiesto.
La única petición de red permitida es:

`GET /gmail/v1/users/me/messages/{messageId}/attachments/{attachmentId}`

No existe llamada a listado, cuerpo, preview, metadata remota, Drive o mutadores.

## Secuencia de despliegue

1. Ejecutar toda la suite sin red.
2. Ejecutar un dry run sintético.
3. Revisar que el reporte no contiene `data`, bytes, texto ni secretos.
4. Ejecutar un único caso real autorizado.
5. Confirmar hash A-E y resultado de framing.
6. Repetir con la misma `operation_key`; no debe producir una nueva descarga.
7. Ampliar al lote cerrado únicamente si no hay MISMATCH.

## Controles por ejecución

- `gmail_mutations = 0`;
- `unread_changes = 0`;
- `label_changes = 0`;
- `drive_writes = 0`;
- `messages_outside_manifest = 0`;
- `attachments_outside_manifest = 0`;
- `proposed_actions = []`;
- `executed_actions = []`;
- ningún contenido documental en logs o commits.

El flujo opera en memoria y no necesita crear copias temporales del adjunto. Si
un despliegue externo introduce una copia temporal, debe estar fuera del repo,
ser un archivo regular no symlink, tener modo `0600` y verificarse inexistente
después de su eliminación.

## Apagado

El apagado inmediato consiste en detener el proceso y retirar del proveedor de
secretos la referencia de credencial del piloto. No se cambia Gmail y no se
eliminan datos remotos. Un reintento posterior conserva idempotencia mediante el
execution store.

## Incidentes

Detener el lote ante cualquiera de estas condiciones:

- referencia fuera del manifiesto;
- MIME diferente del autorizado;
- tamaño o base64url inválidos;
- hash inesperado entre B, C, D o E;
- framing desconocido;
- PDF cifrado, corrupto o ambiguo;
- XML con DTD o entidades;
- contenido documental o secreto en un log;
- MISMATCH nuevo;
- cualquier intento de mutación externa.

Conservar solo códigos saneados, referencias opacas, tamaños y hashes. Revocar la
credencial si pudo exponerse. No copiar el payload al informe del incidente.

## Rollback

Desactivar el piloto retirando la configuración y credencial externas. Para una
regresión de código, aplicar `git revert` al commit concreto, ejecutar ACTIVE,
HISTORICAL, governance, compileall y `git diff --check`, y publicar mediante push
normal. No reescribir historia ni modificar documentos reales.
