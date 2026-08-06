# CamiloBuilder

Versión mínima estable del constructor de proyectos de Camilo OS.

## Comandos

```bash
python3 builder.py status
python3 builder.py create-project mi-proyecto
python3 builder.py create-agent mi-proyecto mi-agente
python3 builder.py create-department mi-proyecto operaciones
```

Los comandos crean o amplían proyectos dentro de `output/`. Para elegir otro destino:

```bash
python3 builder.py create-project mi-proyecto --output /ruta/de/salida
python3 builder.py create-agent mi-proyecto mi-agente --output /ruta/de/salida
python3 builder.py create-department mi-proyecto operaciones --output /ruta/de/salida
```

Los agentes y departamentos pueden inicializarse desde un directorio de plantilla:

```bash
python3 builder.py create-agent mi-proyecto mi-agente --template ./plantillas/agente
```

Los archivos de texto de la plantilla admiten los marcadores
`{{ component_name }}` y `{{ component_type }}`. Los archivos existentes no se
sobrescriben al volver a ejecutar el comando.

## Pruebas

```bash
python3 -m unittest discover -v
```
