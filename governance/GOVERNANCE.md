# Política de governance de CamiloBuilder

**Versión de la política:** 2.0.0
**Constitución aplicable:** Constitution 2.0.0
**Estado:** Vigente tras el cutover coordinado

## 1. Propósito

Esta política convierte las garantías constitucionales en un proceso operativo
proporcional al impacto de cada cambio. Su objetivo es preservar seguridad,
compatibilidad, trazabilidad y reversibilidad sin introducir ceremonia que no
aporte evidencia o control real.

Esta política está subordinada a `CONSTITUTION.md`. Ante conflicto prevalece la
Constitución.

## 2. Autoridad y equipos pequeños

La autoridad material procede de las personas y mecanismos externos que
mantienen realmente el repositorio. `MAINTAINERS.md` documenta el estado humano
declarado, pero no crea identidad ni demuestra legitimidad criptográfica.

Cuando exista un único Maintainer:

- no se habla de mayoría;
- no se simula independencia;
- una aprobación unipersonal explícita puede bastar para cambios ordinarios;
- la ausencia de revisión independiente se declara;
- cambios especialmente sensibles DEBERÍAN buscar revisión externa cuando esté disponible.

No se requiere IAM, Root of Trust ni Approval Registry interno.

## 3. Fuentes canónicas

- Git conserva commits, historia, diferencias, autoría técnica y reversión.
- GitHub materializa publicación, permisos, reviews y checks.
- CI registra ejecución de pruebas y verificaciones.
- La Constitución define garantías.
- Esta política define proceso operativo.
- ADRs documentan decisiones arquitectónicas.
- Work Orders documentan cambios gobernados cuando son necesarias.

Los registros deben referenciar estas fuentes en vez de duplicarlas.

## 4. Categorías de cambio

### 4.1 Cambio rutinario

Incluye correcciones internas compatibles, tests, documentación descriptiva,
mantenimiento acotado y refactors sin efecto observable.

Requiere:

- commit claro;
- pruebas proporcionales;
- CI;
- reversión mediante Git.

No requiere Work Order ni ADR.

### 4.2 Cambio gobernado

Incluye nueva capacidad, modificación observable compatible, migración, cambio
relevante de política operativa o nuevo formato consumido por máquinas.

Requiere:

- Work Order ligera;
- alcance e impacto contractual;
- riesgos y reversión;
- pruebas proporcionales;
- revisión humana disponible.

No requiere ADR salvo que también sea una decisión arquitectónica.

### 4.3 Decisión arquitectónica

Incluye cambios de límites entre módulos, modelo de governance, dependencias
transversales, alternativas relevantes o decisiones difíciles de revertir.

Requiere:

- ADR;
- Work Order ligera cuando exista implementación;
- análisis de consecuencias y reversibilidad;
- revisión arquitectónica disponible.

Una ADR documenta decisión y razonamiento. No constituye aprobación automática
ni sustituye Git, CI o pruebas.

### 4.4 Cambio incompatible

Incluye ruptura de CLI, JSON público, API Python pública, manifests, estructura
generada, garantías de idempotencia o no sobrescritura, y retirada de una
superficie estable.

Requiere:

- ADR;
- Work Order;
- clasificación incompatible;
- migración, deprecación o ventana de transición;
- versión MAJOR cuando corresponda;
- reversión y revisión humana explícita.

## 5. Evidencia y pruebas

La evidencia debe ser proporcional al riesgo. No todo cambio requiere Work
Order. Todo cambio requiere al menos un commit trazable y las pruebas necesarias
para no presentar una regresión conocida como válida.

Los resultados completos de CI y la historia Git no se copian en registros.
Pueden utilizarse referencias estables cuando aporten contexto.

## 6. Work Orders

Una Work Order contiene solo información que no tenga una fuente mejor en Git o
CI. El modelo conceptual mínimo incluye:

- identificador y título;
- objetivo y alcance;
- estado;
- impacto contractual;
- riesgos;
- reversión;
- referencias a evidencia.

Los estados conceptuales son `proposed`, `active`, `done` y `cancelled`.
Publicación y ejecución de pruebas se derivan de Git, GitHub y CI; no necesitan
ser estados administrativos duplicados.

Este documento no impone todavía un formato ni un schema para nuevas Work
Orders. Los registros legacy conservan su formato histórico.

## 7. ADRs

Una ADR se utiliza para decisiones que cambian arquitectura, límites,
dependencias, governance o compromisos difíciles de revertir. Debe explicar:

- contexto y problema;
- decisión;
- alternativas consideradas;
- consecuencias;
- riesgos;
- reversibilidad;
- estado de la decisión.

No se usa una ADR para mantenimiento rutinario ni como sustituto de aprobación.

## 8. Impacto contractual

Las superficies contractuales actuales incluyen:

- CLI y códigos de salida;
- JSON público;
- API Python pública;
- manifests;
- estructura y contenido generado;
- idempotencia y no sobrescritura;
- formatos de máquina consumidos externamente.

El impacto se clasifica como `none`, `compatible`, `incompatible` o
`deprecation`. Si existen varias superficies, pueden clasificarse por separado.
No se necesita un Contract Registry mientras no exista una necesidad operativa
demostrada.

## 9. Compatibilidad y deprecación

La compatibilidad no se presume. Un cambio compatible preserva garantías
observables y debe respaldarse con pruebas.

Una deprecación debe indicar alternativa, ventana de transición, condición de
retirada y reversión. La eliminación posterior es un cambio incompatible
separado.

## 10. Migraciones

Una migración debe ser explícita, idempotente, verificable y reversible o
acompañada de recuperación documentada. No debe ejecutarse implícitamente por
una consulta, introspección o auditoría.

Las migraciones deben separarse de cambios no relacionados y probarse con
fixtures cuando transformen datos o formatos persistidos.

## 11. Excepciones

Una excepción es una autorización humana temporal frente a una obligación
concreta. Debe declarar alcance, responsable, expiración, riesgos, controles
compensatorios, remediación y cierre.

Governance 2.0 no dispone actualmente de un mecanismo ejecutable activo para
registrar o aplicar excepciones. Los schemas e índices de excepciones anteriores
son artefactos legacy legibles, pero la verificación activa no admite excepciones
declaradas ni los reactiva o reinterpreta.

Introducir un mecanismo futuro de excepciones requiere un cambio gobernado
explícito. El software podrá verificar su estructura y aplicabilidad técnica,
pero no afirmar legitimidad humana ni calidad de la decisión.

## 12. Versionado y releases

CamiloBuilder usa SemVer para releases:

- PATCH: corrección compatible o cambio interno;
- MINOR: capacidad o superficie compatible nueva, o deprecación;
- MAJOR: incompatibilidad o reducción de garantía pública.

Una release exige CI satisfactoria, árbol limpio, impacto conocido y rollback.
Las decisiones humanas de publicación permanecen humanas; CI aporta evidencia
técnica, no legitimidad.

## 13. Git, GitHub y CI

Git es la fuente canónica de historia técnica. GitHub es la fuente externa de
publicación, permisos, reviews y checks. CI es la fuente de ejecución de
validaciones.

Los documentos internos no deben duplicar hashes, estados remotos o resultados
completos salvo una referencia útil y estable.

## 14. JSON Schema

JSON Schema se exige cuando existe un consumidor automático que necesita
rechazar datos incompatibles de forma segura.

No se utiliza para demostrar autoridad, aprobación humana, legitimidad,
consenso, mayoría ni ceremonia administrativa. Los schemas legacy permanecen
interpretables para sus documentos históricos.

## 15. Auditoría y límites de automatización

La auditoría automatizada verifica controles técnicos. No certifica legitimidad
humana total, independencia real ni corrección conceptual de una decisión.

Governance verification separa `automated_controls`, `manual_assertions` y
`unverified_obligations`. Una obligación no automatizada permanece visible. El
resultado `verified` significa únicamente que pasaron todos los controles
técnicos automatizados obligatorios y aplicables; no significa conformidad
constitucional total, legitimidad humana ni validación de decisiones humanas.

## 16. Legacy

WORK-009 permanece como registro legacy publicado e intacto. WORK-010 existe
como registro histórico ligero en estado `done`. WORK-011 permanece como
registro legacy schema v2 en estado `cancelled`. Constitution 1.0, GOVERNANCE
1.0 y los schemas v1/v2 continúan históricos e interpretables.

Los registros históricos no se reescriben ni migran implícitamente, y los
formatos legacy no son obligatorios para nuevos cambios.

## 17. Modificación de esta política

Esta política puede evolucionar mediante un cambio gobernado o decisión
arquitectónica proporcional a su impacto. Una modificación que reduzca
garantías constitucionales requiere cambiar primero la Constitución.

Cambiar la representación operativa no exige una enmienda constitucional si
preserva seguridad, trazabilidad, compatibilidad y reversibilidad.

## 18. Glosario

- **ADR:** registro de una decisión arquitectónica y sus alternativas.
- **Cambio gobernado:** cambio relevante que requiere Work Order ligera.
- **Cambio rutinario:** cambio acotado que requiere commit, pruebas y CI.
- **Fuente canónica:** fuente original mantenida para un hecho.
- **Legacy:** artefacto histórico preservado pero no obligatorio hacia delante.
- **Superficie contractual:** comportamiento observable protegido por compatibilidad.
- **Work Order:** registro ligero de objetivo, alcance, riesgo y reversión.
