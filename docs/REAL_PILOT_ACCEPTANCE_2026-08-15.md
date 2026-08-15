# Aceptación del piloto real read-only — 2026-08-15

## Alcance

Se ejecutó el lote cerrado autorizado REAL-001/003/004/005 mediante la frontera
Gmail byte-only. REAL-002 permaneció excluido como `F — INDETERMINATE`. No se
listó el buzón, no se leyeron cuerpos de correo y no se utilizaron previews.

## Integridad

Los cuatro adjuntos fueron PDF puros, no cifrados, válidos con `pypdf
strict=True`, con una única firma `%PDF-` situada en el offset cero. En cada
caso se demostró igualdad byte a byte entre B, C, D y E.

| Caso | Bytes | Páginas | SHA-256 canónico |
| --- | ---: | ---: | --- |
| REAL-001 | 155307 | 1 | `68ba9b2ea91294cb155b4f168f10a205dcac2fc0ca21626bedf7e91723bf6ade` |
| REAL-003 | 153810 | 8 | `e2eabfd73f7c2a478604612e1370e609b70bbb59426025c8e5f45f065a7aa6b7` |
| REAL-004 | 48804 | 5 | `429eadb9cdda0e801390379115e9a183a665b0fddd6186adb28bda71d2f96e9f` |
| REAL-005 | 42491 | 1 | `482536cd2b5521521e077bb226da06079baca5fa7c7fe69a127ef85a486a886f` |

Estos hashes coinciden exactamente con los resultados congelados de la última
aceptación del extractor. Desde esa aceptación no cambiaron `layout.py`,
`candidates.py` ni `resolvers.py`; por tanto, la evaluación campo por campo
continúa siendo aplicable al lote adquirido.

## Métricas

| Caso | Evaluables | MATCH | MISMATCH | UNKNOWN | CONFLICT | Cobertura | Precisión resuelta | Abstención segura |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| REAL-001 | 12 | 2 | 0 | 10 | 0 | 16,7 % | 100 % | 83,3 % |
| REAL-003 | 12 | 0 | 0 | 12 | 0 | 0,0 % | N/A | 100 % |
| REAL-004 | 11 | 7 | 0 | 4 | 0 | 63,6 % | 100 % | 36,4 % |
| REAL-005 | 11 | 3 | 0 | 7 | 1 | 27,3 % | 100 % | 72,7 % |
| **Total** | **46** | **12** | **0** | **33** | **1** | **26,1 %** | **100 %** | **73,9 %** |

Las cifras describen exclusivamente este corpus cerrado y no constituyen una
estimación del rendimiento general. La prioridad conservadora se cumplió:
`MISMATCH = 0`.

## Controles operativos

- lecturas de adjuntos autorizadas: 4;
- mensajes fuera del manifiesto: 0;
- adjuntos fuera del manifiesto: 0;
- mutaciones Gmail: 0;
- cambios UNREAD: 0;
- cambios de labels: 0;
- escrituras Drive: 0;
- `proposed_actions=[]`;
- `executed_actions=[]`;
- repetición idempotente: verificada;
- datos documentales persistidos: 0;
- temporales del piloto: eliminados y su ausencia verificada.

## Decisión

El canal Gmail → base64url → bytes → framing → extractor queda aceptado para
pilotos cerrados en Shadow Mode. La ampliación del lote debe permanecer gradual
y supeditada a mantener cero MISMATCH. No se autoriza ninguna acción de
escritura en Gmail, Drive ni sistemas empresariales.

