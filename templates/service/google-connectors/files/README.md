# Google Connectors

Adapters read-only for injected Gmail and Drive clients. Deployment configuration
contains logical aliases and secret references only; credentials remain external.

## Piloto real cerrado

`pilot_manifest.load_pilot_manifest()` valida un lote de hasta 15 referencias
opacas, ordenadas y únicas. `GmailByteOnlyAttachmentClient` solo invoca el endpoint
oficial de un adjunto incluido en ese manifiesto. No lista el buzón, no lee cuerpos,
no genera previews y no implementa operaciones de escritura.

El cliente recibe el token desde el proveedor de secretos y nunca lo conserva en
el manifiesto o en sus observaciones. `observation()` devuelve únicamente tamaños,
hashes y MIME esperado; no devuelve `data`, bytes ni texto documental.

`GmailInvoiceDiscoveryClient` permite la operación continua read-only. Ejecuta
una búsqueda fija y limitada a adjuntos PDF/XML de los últimos 30 días y solicita
mediante `fields` únicamente IDs, MIME, filename y `attachmentId`. No solicita
headers, snippet, cuerpo ni `body.data`; su salida es un manifiesto opaco pendiente
de revisión.

`ManifestBoundGmailConnector` construye la entrada del agente exclusivamente con
referencias opacas del manifiesto y delega solo `read_content`. Por tanto, el piloto
no necesita listar el buzón, leer el cuerpo ni solicitar filenames reales.
