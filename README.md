# CamiloBuilder

Versión mínima estable del constructor de proyectos de Camilo OS.

## Comandos

```bash
python3 builder.py status
python3 builder.py create-project mi-proyecto
```

El segundo comando crea el proyecto en `output/`. Para elegir otro destino:

```bash
python3 builder.py create-project mi-proyecto --output /ruta/de/salida
```

## Pruebas

```bash
python3 -m unittest discover -v
```
