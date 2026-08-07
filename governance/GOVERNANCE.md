# Política de gobierno de CamiloBuilder

**Versión de la política:** 1.0.0  
**Versión constitucional aplicable:** 1.0.0  
**Estado:** provisional  
**Contrato:** `contract.governance-policy`  
**Work Order:** WORK-009 — Establish CamiloBuilder Constitution

## 1. Propósito

Esta política define cómo CamiloBuilder gobierna versiones, estabilidad,
contratos, cambios, deprecaciones, migraciones, Work Orders, excepciones,
aprobaciones, releases y publicación.

CamiloBuilder DEBE aplicar esta política para convertir las obligaciones de la
Constitución en decisiones operativas consistentes, trazables y auditables.
Esta política NO DEBE crear capacidades de generación, ampliar el CLI ni
mantener inventarios derivados del sistema ejecutable.

## 2. Alcance

Esta política gobierna cualquier cambio que afecte al código, documentación
normativa, arquitectura, contratos, esquemas, registros, plantillas, pruebas,
automatización de gobierno o artefactos publicados de CamiloBuilder.

Toda Work Order DEBE identificar su alcance. Un cambio fuera de ese alcance NO
DEBE incorporarse a la misma Work Order salvo una ampliación explícita,
aprobada y trazable.

## 3. Contenido normativo y descriptivo

Las secciones 1 a 23, incluido el glosario, son **contenido normativo**. Los
términos DEBE, NO DEBE, DEBERÍA y PUEDE conservan exactamente el significado
que les asigna `governance/CONSTITUTION.md`; esta política NO los redefine.

El anexo de la sección 24 es **contenido descriptivo**. PUEDE facilitar la
aplicación de las reglas, pero NO DEBE crear obligaciones, reducir garantías ni
resolver contradicciones con contenido normativo.

## 4. Autoridad y precedencia

Esta política está subordinada a `governance/CONSTITUTION.md`.

- `GOVERNANCE.md` NO modifica la Constitución.
- `GOVERNANCE.md` NO DEBE reducir garantías constitucionales.
- Ante cualquier conflicto, DEBE prevalecer `CONSTITUTION.md`.
- Un conflicto DEBE bloquear la publicación y la release afectadas hasta que
  exista remediación, reversión o enmienda constitucional válida.
- Una aprobación conforme a esta política NO sustituye una aprobación exigida
  por la Constitución.

La precedencia normativa restante es la definida por la Constitución. El
comportamiento existente NO DEBE utilizarse para justificar una desviación.

## 5. Roles

Los roles son categorías de responsabilidad. Esta política no asigna
identidades, no crea un registro de personas y no define firmas criptográficas.

### 5.1 Arquitecto Responsable

El Arquitecto Responsable DEBE proteger la coherencia constitucional,
arquitectónica y contractual. Aprueba los cambios para los que esta política o
la Constitución requieren autoridad arquitectónica. NO DEBE sustituir la
evidencia, las pruebas ni una revisión independiente obligatoria.

### 5.2 Maintainer

Un Maintainer mantiene e integra cambios, verifica su calidad técnica y
preserva las superficies estables. NO DEBE declarar conforme un cambio que no
satisfaga sus gates. Cuando sea autor material y se requiera independencia, NO
DEBE actuar también como único Revisor independiente.

### 5.3 Revisor independiente

El Revisor independiente DEBE evaluar alcance, compatibilidad, riesgos,
pruebas y reversión sin haber sido autor material principal del cambio. NO
DEBE ampliar silenciosamente el alcance durante la aprobación.

### 5.4 Autor de Work Order

El Autor de Work Order DEBE definir objetivo, alcance, impacto contractual,
dependencias, riesgos, pruebas, criterios de aceptación y reversión. La autoría
NO autoriza por sí sola aprobación, publicación ni release.

### 5.5 Aprobador

Un Aprobador DEBE emitir una decisión explícita dentro de su autoridad. NO
DEBE reducir el quórum aplicable ni aprobar evidencia que no pueda verificarse.

### 5.6 Responsable de release

El Responsable de release DEBE comprobar todos los gates, determinar la
versión y ejecutar o autorizar la publicación de la release. NO DEBE dispensar
CI, auditoría, clasificación contractual, Work Orders publicadas ni rollback.

## 6. Separación de responsabilidades

Una misma persona PUEDE ejercer varios roles cuando la Constitución lo permita,
pero NO DEBE simularse independencia mediante acumulación de roles. La persona
que implementa un cambio NO DEBERÍA ser su único aprobador.

La creación, revisión, aprobación y publicación DEBERÍAN dejar evidencia
separada. La ausencia actual de un registro canónico de identidades limita la
verificación automática y NO elimina estas responsabilidades.

## 7. Modelo de versiones

CamiloBuilder separa seis familias de versión:

- `constitution_version`: versión normativa de la Constitución.
- `architecture_version`: versión de relaciones, límites y responsabilidades
  arquitectónicas.
- `record_version`: versión SemVer de un documento gobernado concreto.
- `schema_version`: generación estructural de un esquema y sus documentos.
- `contract_version`: versión independiente de un contrato.
- `release_version`: versión publicada de CamiloBuilder.

Cada Work Order DEBE declarar cuáles afecta. Un cambio en una familia NO DEBE
implicar automáticamente un cambio en otra.

Los esquemas publicados son inmutables. Un cambio material que no pueda
representarse correctamente DEBE crear una nueva `schema_version`. Una revisión
compatible del contenido de un registro DEBE incrementar su `record_version`
cuando cambie materialmente. `architecture_version` DEBE cambiar únicamente
cuando cambie la arquitectura gobernada.

## 8. Clasificación contractual

Por cada contrato afectado, el modelo normativo distingue:

- `creates`;
- `modifies compatible`;
- `modifies incompatible`;
- `deprecates`;
- `removes`;
- `none`.

La clasificación DEBE basarse en el efecto observable y no en la intención del
autor. `none` DEBE respaldarse mediante pruebas cuando el cambio atraviese una
superficie pública.

### 8.1 Limitación gobernada de Work Order schema v2

El Work Order schema v2 solo representa el valor `modifies` y todavía no puede
distinguir de forma suficiente `modifies compatible` de `modifies
incompatible`.

Por tanto, ninguna **nueva** Work Order que modifique un contrato PUEDE pasar a
`approved` mientras utilice un esquema que no represente explícitamente esa
distinción. Las Work Orders históricas ya existentes NO DEBEN reinterpretarse
retroactivamente como compatibles o incompatibles.

Resolver esta limitación requiere una versión futura del schema de Work Orders.
La versión v2 NO DEBE modificarse. Esta limitación es estado gobernado y NO es
una excepción implícita, una autorización para aprobar modificaciones ni una
relajación temporal del contrato.

## 9. Política SemVer de releases

Una release DEBE usar SemVer. El impacto más severo acumulado desde la release
anterior determina su incremento mínimo.

### 9.1 PATCH

PATCH comprende correcciones compatibles, documentación, pruebas y cambios
internos sin impacto contractual. Una corrección PUEDE ser PATCH únicamente si
preserva el contrato público y existe evidencia de regresión suficiente.

### 9.2 MINOR

MINOR comprende un contrato nuevo compatible, una capacidad nueva compatible,
una modificación pública compatible o el inicio de una deprecación.

### 9.3 MAJOR

MAJOR comprende una modificación contractual incompatible, la eliminación de
un contrato `stable`, un cambio incompatible de CLI, JSON, manifiestos o
estructura generada, o una reducción de garantías públicas.

Una clasificación de menor severidad NO DEBE emplearse para evitar las
aprobaciones, migraciones o garantías de una release MAJOR.

## 10. Estabilidad

Los estados de estabilidad son:

- `experimental`: sin garantía de compatibilidad; requiere adopción explícita.
- `provisional`: contrato definido, sujeto aún a evolución compatible.
- `stable`: compatibilidad protegida; una ruptura exige procedimiento MAJOR.
- `deprecated`: disponible durante una ventana de compatibilidad y con
  alternativa declarada.
- `removed`: no disponible; conserva trazabilidad histórica.

Las transiciones ordinarias permitidas son:

```text
experimental -> provisional -> stable -> deprecated -> removed
experimental -> removed
provisional -> deprecated
```

Toda transición DEBE estar asociada a una Work Order y justificada. Un elemento
`removed` es terminal. La estabilidad NO DEBE degradarse para evitar una
versión MAJOR, una migración o una ventana de compatibilidad.

## 11. Gobierno de contratos

Todo contrato gobernado DEBE tener identificador estable, `contract_version`,
estabilidad, proveedor, consumidores conocidos, garantías, compatibilidad y
pruebas. Los contratos PUEDEN evolucionar independientemente de la release,
pero una release DEBE reflejar el efecto público acumulado.

`contract.governance-policy` es proporcionado por `module.governance`, tiene
estabilidad inicial `provisional` y es consumido inicialmente por
`module.constitutional-audit`. Esta declaración no crea otros contratos ni
modifica dependencias arquitectónicas.

## 12. Deprecaciones y retirada

Toda deprecación DEBE registrar:

- Work Order;
- contrato afectado;
- alternativa recomendada;
- fecha o versión de inicio;
- ventana de compatibilidad;
- pruebas del comportamiento antiguo y nuevo;
- condición de retirada;
- procedimiento de migración;
- estrategia de reversión.

Un contrato `stable` NO DEBE eliminarse directamente salvo mediante un
procedimiento MAJOR constitucionalmente válido. La retirada DEBE realizarse en
una Work Order diferenciable de la que inició la deprecación.

## 13. Migraciones

Toda migración DEBE ser:

- explícita;
- idempotente;
- probada con fixtures;
- verificable antes y después;
- reversible o respaldada por recuperación documentada;
- separada de consultas;
- separada de cambios no relacionados.

Una migración NO DEBE ejecutarse implícitamente durante introspección,
validación, inspección o auditoría. Ante ambigüedad o validación incompleta,
DEBE detenerse sin presentar un estado parcial como completo.

## 14. Ciclo de Work Orders

Los estados gobernados son `proposed`, `approved`, `in_progress`, `completed`,
`published`, `reverted` y `cancelled`.

Las transiciones ordinarias son:

```text
proposed -> approved -> in_progress -> completed -> published
proposed -> cancelled
approved -> cancelled
in_progress -> cancelled
completed -> reverted
published -> reverted
```

Evidencia mínima:

- `proposed`: objetivo, alcance y autor identificados.
- `approved`: clasificación contractual representable, dependencias, riesgos,
  criterios de aceptación, reversión y aprobaciones exigidas.
- `in_progress`: aprobación vigente y evidencia de inicio.
- `completed`: commits de implementación, pruebas satisfactorias, riesgos
  explícitos y reversión comprobable.
- `published`: todos los commits exigidos publicados en el remoto canónico y
  evidencia registral de publicación.
- `reverted`: causa, alcance, reversión ejecutada y validación posterior.
- `cancelled`: razón registrada y ausencia de trabajo presentado como vigente.

`completed` NO equivale a `published`. `published` NO equivale a una release.
Los estados terminales NO DEBEN reabrirse; continuar el objetivo requiere una
nueva Work Order vinculada.

## 15. Aprobaciones

Los mínimos operativos son:

- PATCH: aprobación de Maintainer y revisión independiente cuando exista cambio
  ejecutable.
- MINOR: Maintainer, Revisor independiente y Arquitecto Responsable.
- MAJOR: Arquitecto Responsable, revisión independiente y quórum constitucional
  aplicable.

Las enmiendas E0–E3 DEBEN seguir exactamente las reglas de la Constitución;
esta política las referencia y NO las redefine.

Una excepción ordinaria DEBE cumplir la aprobación constitucional del
Arquitecto Responsable y mayoría simple. Una excepción sobre No Destrucción,
Mínimo Privilegio o Fallo Seguro DEBE cumplir la política crítica
constitucional, incluidos dos tercios y revisión independiente cuando exista.

Hasta que exista un registro canónico de identidades y aprobaciones, estas
decisiones DEBEN documentarse de forma trazable y su verificación automática
será limitada. Esa limitación NO reduce el quórum.

## 16. Excepciones

Toda excepción DEBE ser temporal, explícita y no crear precedente. DEBE tener
expiración, riesgos, controles compensatorios, remediación, criterio de cierre,
reversión y aprobaciones.

La vigencia DEBE evaluarse frente al instante real y explícito de evaluación.
Una excepción expirada NO DEBE justificar conformidad. Las excepciones NO
DEBEN renovarse implícitamente y una renovación requiere un nuevo identificador
conforme a la Constitución.

Los registros concretos permanecen en su fuente canónica y NO DEBEN copiarse en
este documento.

## 17. Releases

Una revisión de `main` solo PUEDE declararse release cuando:

- la CI constitucional pasa;
- la auditoría resulta `compliant` o `compliant_with_exceptions` válido;
- el árbol de trabajo está limpio;
- las Work Orders incluidas están `published`;
- los contratos están clasificados;
- los schemas seleccionados son compatibles;
- las excepciones activas están identificadas y vigentes;
- `release_version` está determinada;
- existe rollback conocido.

`non_compliant` e `indeterminate` DEBEN bloquear la release. Una excepción
expirada DEBE bloquearla. Esta política no automatiza releases.

## 18. Publicación

- **Commit local:** objeto Git presente en el repositorio local.
- **Commit publicado:** commit verificado en el remoto canónico.
- **Bloque validado:** alcance cuyas pruebas y auditoría requeridas pasaron.
- **Work Order completed:** implementación terminada con evidencia suficiente.
- **Work Order published:** implementación y registro confirmados en el remoto.
- **Release publicada:** versión identificada y distribuida tras todos los
  gates de release.

Un `push` NO convierte automáticamente una Work Order en `published`. Una
revisión de `main` NO constituye automáticamente una release publicada.

## 19. Evidencia y trazabilidad

Cada cambio DEBE vincular Work Order, contratos, componentes, capacidades,
commits de implementación, pruebas, riesgos, dependencias y reversión cuando
sean aplicables. Las referencias DEBEN usar identificadores canónicos y NO
duplicar objetos gobernados.

Los hashes y estados concretos DEBEN permanecer en sus registros canónicos, no
en esta política. La evidencia derivable desde Git o el runtime DEBERÍA
referenciarse en lugar de copiarse.

## 20. Auditoría y aplicación

La auditoría DEBE comprobar obligaciones vigentes y NO roadmap futuro. Esta
política identifica como automatizables en bloques posteriores:

- presencia, versión y precedencia de la política;
- clasificación contractual y correspondencia SemVer;
- transiciones de estabilidad;
- evidencia exigida por estado de Work Order;
- ventanas de deprecación y condiciones de retirada;
- requisitos de migración;
- gates de release y publicación;
- vigencia de excepciones;
- coherencia entre commits publicados y estados registrales;
- independencia de aprobaciones cuando exista una fuente canónica de personas.

Hasta que exista automatización, revisión y pruebas documentales PUEDE servir
como control transitorio, pero NO DEBE declarar conforme lo que no pueda
verificarse con evidencia suficiente.

## 21. Conflictos y remediación

Ante conflicto entre esta política, un registro, código o ejecución:

1. DEBE prevalecer la Constitución.
2. La publicación y la release afectadas DEBEN detenerse.
3. DEBE identificarse alcance y evidencia.
4. DEBE abrirse o actualizarse una Work Order de remediación.
5. DEBE elegirse corrección, reversión o enmienda válida.
6. Pruebas y auditoría DEBEN pasar antes de reanudar publicación.

La ambigüedad NO DEBE resolverse reduciendo garantías.

## 22. Modificación de esta política

Toda modificación normativa de esta política DEBE usar una Work Order,
clasificar contratos, compatibilidad y SemVer, identificar riesgos, pruebas,
aprobaciones y reversión, y actualizar `contract.governance-policy` cuando
corresponda.

Un cambio editorial PUEDE ser PATCH. Una ampliación compatible de gobierno DEBE
ser al menos MINOR. Una reducción de garantías o incompatibilidad DEBE ser
MAJOR y PUEDE requerir una enmienda constitucional E3.

Ninguna modificación de esta política PUEDE sustituir el procedimiento E0–E3
cuando el contenido afectado pertenezca a la Constitución.

## 23. Entrada en vigor y glosario

Esta política entra en vigor como versión 1.0.0 cuando su commit se publique y
la Work Order correspondiente alcance el estado exigido por el proceso
constitucional vigente.

- **Contrato:** compromiso gobernado y observable entre proveedor y consumidor.
- **Compatibilidad:** preservación demostrada de las garantías aplicables.
- **Gate:** condición obligatoria para avanzar de estado.
- **Migración:** transformación explícita entre representaciones o contratos.
- **Rollback:** procedimiento conocido para restaurar un estado conforme.
- **Release:** versión de CamiloBuilder identificada y publicada.
- **Fuente canónica:** única autoridad mantenida para un dato gobernado.
- **Inventario derivado:** información recalculable de forma fiable desde el
  runtime o una fuente canónica ejecutable.

## 24. Anexo descriptivo: matriz de decisión

Este anexo es descriptivo y no altera las reglas anteriores.

| Efecto principal | Incremento mínimo | Gate destacado |
|---|---|---|
| Corrección interna compatible | PATCH | Pruebas de regresión |
| Contrato o capacidad compatible nueva | MINOR | Arquitecto y revisión independiente |
| Inicio de deprecación | MINOR | Ventana y migración |
| Ruptura contractual o retirada estable | MAJOR | Quórum, migración y rollback |
| Conflicto constitucional | Bloqueado | Remediación, reversión o enmienda válida |
