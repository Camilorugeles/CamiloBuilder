# CamiloBuilder

Versión mínima estable del constructor de proyectos de Camilo OS.

CamiloBuilder genera proyectos y componentes sin sobrescribir archivos existentes.
Incluye un runtime determinista para agentes, conectores Google de solo lectura y
un piloto de análisis de facturas en Shadow Mode. El piloto propone resultados para
revisión, pero no modifica Gmail, Drive, contabilidad ni los documentos originales.

## Requisitos

- Python 3.13 para reproducir el entorno de CI;
- dependencias de desarrollo fijadas en `requirements-dev.txt`.

Preparación recomendada:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --requirement requirements-dev.txt
```

## Comandos

```bash
python3 builder.py status
python3 builder.py create-project mi-proyecto
python3 builder.py create-agent mi-proyecto mi-agente
python3 builder.py create-department mi-proyecto operaciones
python3 builder.py create-service mi-proyecto notificaciones
python3 builder.py list-agents mi-proyecto
python3 builder.py list-departments mi-proyecto
python3 builder.py inspect-agent mi-proyecto mi-agente
python3 builder.py inspect-department mi-proyecto operaciones
python3 builder.py list-services mi-proyecto
python3 builder.py inspect-service mi-proyecto notificaciones
python3 builder.py list-templates
python3 builder.py list-templates --type agent
python3 builder.py inspect-template default --type agent
python3 builder.py validate-template default --type agent
python3 builder.py validate-template ./plantillas/agente --type agent
```

Los comandos crean o amplían proyectos dentro de `output/`. Para elegir otro destino:

```bash
python3 builder.py create-project mi-proyecto --output /ruta/de/salida
python3 builder.py create-agent mi-proyecto mi-agente --output /ruta/de/salida
python3 builder.py create-department mi-proyecto operaciones --output /ruta/de/salida
python3 builder.py create-service mi-proyecto notificaciones --output /ruta/de/salida
```

Los agentes y departamentos pueden inicializarse desde un directorio de plantilla:

```bash
python3 builder.py create-agent mi-proyecto mi-agente --template ./plantillas/agente
```

Los archivos de texto de la plantilla admiten los marcadores
`{{ component_name }}` y `{{ component_type }}`. Los archivos existentes no se
sobrescriben al volver a ejecutar el comando.

Los comandos `list-agents` y `list-departments` imprimen los nombres ordenados.
Los comandos `inspect-agent` e `inspect-department` devuelven JSON con el nombre,
tipo, ruta y archivos del componente.

## Plantillas integradas

- `agent-core`: runtime local, contratos, aprobación e idempotencia;
- `google-connectors`: adaptadores Google configurados externamente y de solo lectura;
- `invoice-intake`: extracción determinista de PDF/XML, revisión y clasificación;
- `invoice-intake-shadow`: agente documental sin acciones externas;
- `camilo-os-agent`: agente operativo para el piloto sintético.

Ejemplo mínimo:

```bash
python3 builder.py create-project demo
python3 builder.py create-service demo agent_core --template agent-core
python3 builder.py create-service demo google_connectors --template google-connectors
python3 builder.py create-service demo invoice_intake --template invoice-intake
python3 builder.py create-agent demo invoice_intake --template invoice-intake-shadow
```

## Garantías del piloto documental

- Shadow Mode: `proposed_actions=[]` y `executed_actions=[]`;
- PDF con texto embebido mediante `pypdf`; no incluye OCR ni LLM;
- framing PDF cerrado, límites de tamaño y rechazo de contenido ambiguo;
- XML sin DTD ni entidades;
- SQLite e idempotencia para ejecuciones y duplicados;
- resolución conservadora: ante evidencia insuficiente devuelve `unknown` o
  `conflict` en lugar de fabricar un valor;
- configuración, credenciales, destinos y conocimiento empresarial fuera del código.

Los contratos detallados del servicio generado están en los README y schemas de
las plantillas correspondientes.

El procedimiento para operar un lote real cerrado, byte-only y de solo lectura
está en [`docs/REAL_PILOT_RUNBOOK.md`](docs/REAL_PILOT_RUNBOOK.md).

## Pruebas

```bash
python3 -m unittest discover -v
```

La aceptación completa utilizada por CI añade:

```bash
python3 -m unittest discover -s tests/historical -p 'historical_*.py' -v
python3 -m compileall -q builder.py builder_cli.py builders template_system capability_introspection constitutional_audit tests
git diff --check
```

`Constitutional Audit` se ejecuta en cada push. `Historical Governance Audit` se
ejecuta manualmente contra `main` para comprobar el historial completo.

## Límites

CamiloBuilder es un constructor y un runtime de referencia, no un servicio desplegado.
No contiene credenciales reales, configuración empresarial, OCR, conciliación
contable automática ni permisos de escritura sobre proveedores externos. Cualquier
ampliación de esas fronteras requiere un cambio gobernado separado.
