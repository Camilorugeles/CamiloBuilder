# ADR-0001 — Simplify CamiloBuilder governance

**Estado:** Accepted
**Fecha:** 2026-08-08T17:46:16+02:00

## Contexto

WORK-009 introdujo Constitución, schemas, registros, introspección, auditoría y
CI constitucional. WORK-010 corrigió la disponibilidad de historia Git en CI.
WORK-011 expuso un defecto estructural: el sistema de governance requería que
sus mecanismos de legitimación fueran legitimados por mecanismos que todavía
no podían existir.

Un Red Team Review concluyó que los principios de seguridad eran sólidos, pero
que governance había crecido hasta superar en complejidad al producto funcional.

## Problema

El modelo 1.0 mezclaba decisiones humanas, validación de datos y evidencia Git.
Duplicaba información derivable, sobrecargaba Work Orders, usaba schemas para
ceremonia interna y producía autorreferencia al intentar registrar commits de
cierre dentro del mismo historial que los creaba.

La auditoría podía declarar `compliant` aunque no automatizara todas las
obligaciones. La evolución del metamodelo generaba una recursión entre Work
Orders, excepciones, autoridad y controles.

## Alternativas consideradas

### Mantener Constitution 1.0 y crear Work Order schema v3

Rechazada porque resolvía una representación local sin corregir la sobrecarga
del modelo ni su recursión.

### Root of Trust o Constitutional Origin Record

Rechazada porque trasladaba la autoridad humana a otro artefacto interno y
requería nuevos schemas, controles y reglas de terminación.

### Authority Registry y Approval Registry

Rechazados mientras no exista una necesidad organizativa real. Un JSON puede
registrar una afirmación, pero no demostrar legitimidad, independencia o
consenso humano.

### Continuar con excepciones bootstrap

Rechazada porque exigía primero el control y la autoridad que la propia
excepción pretendía permitir construir.

## Decisión

Reconstituir CamiloBuilder bajo Constitution 2.0.0 y GOVERNANCE 2.0.0.

La Constitución gobernará garantías, invariantes y límites. GOVERNANCE regirá
procesos operativos proporcionales al impacto. No todo cambio requerirá Work
Order. Git, GitHub y CI serán las fuentes canónicas de evidencia técnica que ya
proporcionan.

Las decisiones humanas, los hechos verificables por máquina y la evidencia
externa se mantendrán separados. La autoridad material se reconoce fuera del
repositorio y se documenta en `MAINTAINERS.md` sin crearla mediante JSON.

La versión constitucional se deriva únicamente de `CONSTITUTION.md`; el
registro arquitectónico deja de duplicarla.

Esta ADR documenta la decisión. No constituye autoridad por sí sola.

## Consecuencias

- Governance queda sustancialmente más pequeño.
- Los cambios rutinarios usan commit, pruebas y CI.
- Work Orders futuras serán ligeras.
- ADRs se reservan para decisiones arquitectónicas.
- La auditoría se redefinirá posteriormente para no afirmar más de lo que puede verificar.
- Los schemas legacy permanecen interpretables, pero no obligan al modelo futuro.

## Riesgos

- Coexistencia temporal entre consumidores legacy y política 2.0.
- Concentración real de autoridad en un único Maintainer.
- Divergencia futura entre `MAINTAINERS.md` y permisos de GitHub.
- Simplificación excesiva que elimine evidencia útil.
- Uso transitorio de la nomenclatura `compliant` hasta el siguiente bloque.

## Legacy

Constitution 1.0, GOVERNANCE 1.0, WORK-009, WORK-011, schemas y fixtures
históricos permanecen en Git con su significado original. No se reconstruyen ni
reinterpretan. WORK-011 permanece `proposed` durante este cutover.

## Reversibilidad

Antes de que existan dependencias 2.0, el commit coordinado puede revertirse
técnicamente con Git y validación completa. Después de gobernar cambios bajo
2.0, una versión posterior debe supersederla explícitamente; un revert no borra
el hecho histórico de su vigencia.
