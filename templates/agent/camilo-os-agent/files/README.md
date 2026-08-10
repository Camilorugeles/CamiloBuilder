# {{ component_name }}

Piloto sintético `invoice-intake` para Camilo OS.

Analiza mensajes proporcionados por un connector in-memory, extrae campos
sintéticos y propone un destino que siempre requiere revisión humana. No se
conecta a Gmail, Drive ni a ningún sistema externo.

Requiere que el proyecto contenga el service template `agent-core` generado con
el nombre técnico `agent_core`.
