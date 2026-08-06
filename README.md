# CamiloBuilder

Versión mínima estable del constructor de proyectos de Camilo OS.

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

## Pruebas

```bash
python3 -m unittest discover -v
```
