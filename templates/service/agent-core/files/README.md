# {{ component_name }}

Núcleo local para ejecutar agentes de Camilo OS.

Este servicio valida Agent Definition v1 y Execution Record v1, aplica permisos
lógicos, separa propuestas de acciones aprobadas y conserva registros
deterministas. Las implementaciones incluidas son exclusivamente in-memory: no
usan red, OAuth, credenciales ni sistemas empresariales.

Debe generarse con el nombre técnico `agent_core`, que es la ubicación estable
usada por las plantillas de agentes de Camilo OS. Su única dependencia externa
está declarada en `requirements.txt`.
