# Constitución de CamiloBuilder

**Versión constitucional:** 1.0.0  
**Work Order constituyente:** WORK-009 — Establish CamiloBuilder Constitution  
**Estado:** Normativa inicial

## 1. Preámbulo

CamiloBuilder existe para construir estructuras de Camilo OS de forma segura,
determinista, compatible y auditable. Esta Constitución establece las reglas
permanentes que gobiernan su arquitectura, sus contratos, su evolución y las
decisiones tomadas en su nombre.

La Constitución no pretende congelar el sistema. Su finalidad es permitir que
evolucione sin perder trazabilidad, seguridad, compatibilidad ni capacidad de
reversión. Toda persona, proceso o agente que modifique CamiloBuilder queda
sujeto a estas reglas dentro de su alcance normativo.

## 2. Identidad y propósito

CamiloBuilder es el constructor gobernado de proyectos y componentes de Camilo
OS. Su identidad comprende el código ejecutable, los builders, el CLI, el motor
de plantillas, las plantillas registradas, los contratos públicos y los
registros de gobierno aprobados.

CamiloBuilder DEBE:

- Generar estructuras mediante contratos explícitos y plantillas verificables.
- Validar entradas, manifiestos, variables, rutas y conflictos antes de escribir.
- Preservar contenido existente salvo autorización destructiva explícita.
- Describir y auditar su arquitectura y capacidades de forma reproducible.
- Evolucionar mediante Work Orders pequeñas, trazables y reversibles.

CamiloBuilder NO DEBE convertirse implícitamente en runtime de Camilo OS,
gestor de paquetes, sistema de despliegue, ejecutor de código generado o motor
de plugins.

## 3. Alcance normativo y descriptivo

### 3.1 Contenido normativo

Son normativas las secciones 1 a 18 de este documento. También son normativas
las reglas identificadas mediante los términos DEBE, NO DEBE, DEBERÍA y PUEDE.

Estos términos significan:

- **DEBE:** obligación necesaria para declarar conformidad.
- **NO DEBE:** prohibición necesaria para declarar conformidad.
- **DEBERÍA:** expectativa fuerte; apartarse requiere justificación trazable.
- **PUEDE:** capacidad permitida, nunca una obligación.

Los contratos declarados estables, las reglas de compatibilidad, las reglas de
aprobación y los criterios de cumplimiento también son normativos.

### 3.2 Contenido descriptivo

Los anexos marcados expresamente como descriptivos, los diagramas, los ejemplos,
las notas históricas y los inventarios derivados son descriptivos. Su finalidad
es explicar el sistema, no crear obligaciones.

El contenido descriptivo NO DEBE reducir, sustituir ni reinterpretar una regla
normativa. Cuando un texto no esté clasificado de manera inequívoca, se tratará
como descriptivo hasta que una enmienda lo convierta expresamente en normativo.

## 4. Autoridad y precedencia

Esta Constitución es la autoridad normativa superior dentro del repositorio de
CamiloBuilder. Su precedencia es:

1. Constitución vigente.
2. Contratos gobernados vigentes.
3. Work Orders aprobadas.
4. Políticas y registros arquitectónicos aprobados.
5. Código ejecutable y pruebas.
6. Documentación descriptiva y ejemplos.

Una fuente inferior NO DEBE modificar implícitamente una fuente superior. La
existencia de código desplegado o de comportamiento histórico no constituye por
sí sola una enmienda constitucional.

Ante ambigüedad, prevalece la interpretación más protectora de los datos, la
compatibilidad, el mínimo privilegio y la reversibilidad.

## 5. Principios constitucionales

### 5.1 Principio de Autoconocimiento

CamiloBuilder DEBE poder describir automáticamente su identidad, arquitectura,
capacidades, contratos, limitaciones, builders, comandos, plantillas,
dependencias y Work Orders.

La descripción DEBE derivarse de fuentes canónicas, ser legible por máquinas,
tener formato versionado y producir resultados deterministas. Una capacidad que
no pueda describirse, vincularse y auditarse NO DEBE considerarse plenamente
gobernada.

### 5.2 Principio de No Deriva

CamiloBuilder NO DEBE mantener manualmente información que pueda descubrirse de
forma fiable desde el sistema ejecutable.

La documentación normativa y los datos derivados DEBEN permanecer separados.
Los comandos, builders, componentes y plantillas DEBERÍAN derivarse de sus
registros ejecutables canónicos. Los datos derivados NO DEBEN convertirse en
una segunda fuente de verdad y DEBEN poder recalcularse.

Las decisiones, contratos, riesgos y dependencias conceptuales PUEDE que
requieran declaración manual porque no siempre son deducibles del runtime.

### 5.3 Principio de Trazabilidad

Cada capacidad gobernada DEBE vincularse con:

- Su Work Order.
- Sus commits de implementación.
- Las pruebas que la verifican.
- Los contratos que crea, modifica o consume.
- Los componentes dependientes.
- Los riesgos conocidos.
- Su estrategia de reversión.

La trazabilidad DEBE funcionar desde la capacidad hacia su origen y desde la
Work Order, contrato o componente hacia sus implementaciones. Una Work Order NO
DEBE cerrarse sin evidencias de implementación, validación y reversión.

### 5.4 Principio de Gobernanza de Contratos

Todo cambio DEBE declarar, para cada contrato afectado, si:

- Crea un contrato.
- Modifica un contrato de forma compatible.
- Modifica un contrato de forma incompatible.
- Depreca un contrato.
- Elimina un contrato.
- No afecta contratos públicos.

La declaración de ausencia de impacto DEBE respaldarse mediante pruebas cuando
el cambio atraviese una superficie pública. Un contrato estable NO DEBE cambiar
de forma incompatible sin Work Order, clasificación mayor, migración,
aprobación correspondiente y estrategia de reversión.

### 5.5 Principio de Arquitectura Viva

La arquitectura DEBE verificarse continuamente mediante auditoría, pruebas y
CI. NO DEBE limitarse a documentación estática.

Toda declaración arquitectónica verificable DEBERÍA disponer de auditor,
prueba contractual, validación de esquema o comprobación en CI. Un fallo de
auditoría constitucional DEBE impedir declarar una versión como validada o
publicable.

Mientras la auditoría ejecutable todavía no exista, las pruebas documentales y
la revisión de Work Orders constituyen controles transitorios, no sustitutos
permanentes.

### 5.6 Principio de No Destrucción

Ninguna operación DEBE sobrescribir, truncar, reemplazar o eliminar contenido
existente sin una acción destructiva explícita, limitada, trazable y reversible
o respaldada por una copia recuperable.

La ausencia de una opción destructiva explícita DEBE interpretarse como una
obligación de preservar. Las operaciones idempotentes DEBEN conservar las
personalizaciones existentes.

### 5.7 Principio de Mínimo Privilegio

Cada módulo, builder, comando y operación DEBE acceder únicamente a los
archivos, rutas, permisos, red y capacidades estrictamente necesarios.

Las consultas y validaciones NO DEBEN adquirir permisos de escritura. La
generación DEBE limitarse al proyecto y componente seleccionados. Una
ampliación de permisos DEBE ser explícita, acotada y trazable.

### 5.8 Principio de Fallo Seguro

Ante ambigüedad, corrupción, incompatibilidad, conflicto estructural,
validación incompleta o falta de autoridad, CamiloBuilder DEBE detenerse sin
modificar el destino.

Los errores DEBEN ser claros, usar código no cero cuando corresponda y evitar
exponer secretos. Una entrada desconocida NO DEBE reinterpretarse como una
operación más permisiva. La recuperación silenciosa solo PUEDE utilizarse si
está definida por contrato y es demostrablemente segura.

### 5.9 Principio de Determinismo

Las mismas entradas, versiones, plantillas, variables y condiciones
contractuales DEBEN producir resultados equivalentes y auditables.

Los listados, archivos inspeccionados, JSON públicos, resolución de plantillas,
mensajes y códigos contractuales DEBEN mantener un orden y una forma estables.
Las fechas, valores aleatorios y rutas dependientes del entorno NO DEBEN
incorporarse implícitamente a resultados generados.

### 5.10 Principio de Evolución Incremental

Cada cambio DEBE ser pequeño, acotado, verificable, reversible y asociado a una
Work Order. DEBE declarar impacto contractual, riesgos, dependencias, pruebas y
reversión.

Una Work Order NO DEBE combinar refactors, capacidades y migraciones no
relacionadas. Los bloques dependientes NO DEBERÍAN comenzar antes de validar,
publicar y verificar el bloque anterior. La complejidad futura no justifica por
sí sola una abstracción presente.

## 6. Responsabilidades

CamiloBuilder es responsable de:

- Validar nombres, proyectos, manifiestos, variables, rutas y plantillas.
- Resolver plantillas con precedencia explícita y determinista.
- Generar proyectos y componentes dentro del destino autorizado.
- Preservar contenido existente.
- Proporcionar salidas y códigos conformes con sus contratos.
- Exponer inventarios de capacidades y arquitectura cuando se implemente el
  mecanismo constitucional correspondiente.
- Registrar y auditar su evolución mediante Work Orders.
- Mantener pruebas proporcionales al riesgo de cada cambio.

## 7. Límites

CamiloBuilder no garantiza actualmente:

- Escritura transaccional ante fallos físicos.
- Coordinación entre procesos concurrentes.
- Ejecución o validez funcional del código generado.
- Descarga remota de plantillas.
- Descubrimiento dinámico de plugins.
- Migración automática de proyectos antiguos.

Estas limitaciones DEBEN registrarse como riesgos conocidos. Una limitación NO
DEBE reinterpretarse como permiso para actuar de forma destructiva o insegura.

## 8. Contratos gobernados

Son contratos gobernados, como mínimo:

- Comandos y argumentos del CLI.
- Textos públicos y mensajes de error.
- Códigos de salida.
- Salidas JSON y orden de sus campos.
- Interfaces públicas de builders.
- Manifiestos y resolución de plantillas.
- Estructuras y contenido generado.
- Reglas de idempotencia y no sobrescritura.
- Registros arquitectónicos y de Work Orders.

Cada contrato DEBE tener identificador, versión, estabilidad, consumidores,
reglas compatibles, reglas incompatibles y evidencia de prueba. Hasta que el
registro contractual exista, las pruebas actuales y esta Constitución son la
evidencia transitoria de los contratos vigentes.

## 9. Compatibilidad

La compatibilidad DEBE declararse y probarse; NO DEBE asumirse.

Un cambio compatible PUEDE añadir comportamiento opcional sin modificar el
comportamiento vigente. Un cambio incompatible incluye, entre otros, renombrar
comandos, cambiar argumentos, alterar JSON estable, sobrescribir contenido
preservado, retirar plantillas heredadas o modificar estructuras
predeterminadas.

Una deprecación DEBE proporcionar alternativa, periodo de transición, pruebas
del comportamiento antiguo y nuevo, y una Work Order separada para la
eliminación. Una migración DEBE ser explícita, idempotente y reversible o
acompañada de respaldo recuperable.

## 10. Versionado

La versión constitucional inicial es **1.0.0** y sigue versionado semántico:

- **PATCH:** enmienda E0 o corrección que no cambia significado normativo.
- **MINOR:** enmienda E2 compatible que añade obligaciones o gobierno.
- **MAJOR:** enmienda E3 que modifica alcance, principios o garantías.

Una aclaración E1 PUEDE requerir PATCH si cambia la redacción publicada. Las
versiones de Constitución, arquitectura, manifiestos, Work Orders, capacidades
y contratos DEBEN evolucionar de manera independiente.

## 11. Work Orders y trazabilidad

WORK-009 se denomina conceptualmente **Establish CamiloBuilder Constitution**.

Toda Work Order DEBE registrar, como mínimo:

- Identificador y título.
- Estado y fechas.
- Impacto contractual.
- Componentes afectados.
- Dependencias.
- Commits de implementación.
- Pruebas ejecutadas y resultados.
- Riesgos.
- Estrategia de reversión.

Un commit no puede contener su propio hash. Los commits de implementación DEBEN
crearse primero y registrarse posteriormente en un commit de cierre. El commit
de cierre se obtiene del historial y NO DEBE intentar autorreferenciarse.

## 12. Auditoría

El cumplimiento DEBE auditarse mediante pruebas, validaciones y, cuando se
implemente, auditoría ejecutable y CI.

La auditoría DEBE poder detectar:

- Entidades registradas inexistentes.
- Capacidades ejecutables no gobernadas.
- Contratos sin pruebas o clasificación.
- Dependencias desconocidas o prohibidas.
- Builders y plantillas incoherentes.
- Work Orders incompletas.
- Excepciones expiradas.
- Versiones incompatibles.
- Deriva entre fuentes normativas y runtime.

Un resultado de auditoría fallido NO DEBE declararse conforme ni publicable.

## 13. Conflictos entre código y Constitución

Cuando el código, una prueba, un registro o una Work Order entre en conflicto
con esta Constitución:

1. La Constitución DEBE prevalecer.
2. El sistema afectado DEBE considerarse no conforme.
3. La publicación afectada DEBE detenerse.
4. DEBE abrirse una Work Order de remediación.
5. El código DEBE revertirse o la Constitución DEBE enmendarse válidamente.
6. Mientras no exista resolución, DEBE aplicarse el comportamiento menos
   destructivo y más seguro.

El comportamiento existente NO DEBE utilizarse como justificación automática
para cambiar la Constitución.

## 14. Enmiendas E0–E3

### 14.1 E0 — Editorial

Corrige ortografía, formato, enlaces o contenido descriptivo sin cambiar el
significado normativo.

Requiere aprobación de un Maintainer. No requiere cambio de versión normativa
si el contenido publicado no cambia materialmente.

### 14.2 E1 — Clarificación normativa compatible

Adecua la redacción sin ampliar ni reducir materialmente una obligación.

Requiere Work Order, mayoría simple de Maintainers activos y aprobación del
Arquitecto Responsable. DEBE aportar evidencia de ausencia de cambio
contractual.

### 14.3 E2 — Nueva norma compatible

Añade una obligación o mecanismo de gobierno sin debilitar principios ni romper
contratos estables.

Requiere Work Order, mayoría absoluta de Maintainers activos, aprobación del
Arquitecto Responsable, análisis de contratos, riesgos y reversión. Incrementa
la versión MINOR.

### 14.4 E3 — Enmienda mayor

Modifica o elimina principios, reduce garantías, cambia precedencia o reglas de
aprobación, autoriza nuevas acciones destructivas o elimina contratos estables.

Requiere Work Order específica, dos tercios de Maintainers activos, aprobación
explícita del Arquitecto Responsable y revisión independiente cuando existan al
menos dos Maintainers. DEBE incluir migración, reversión y periodo de revisión.
Incrementa la versión MAJOR.

### 14.5 Quórum y procedimiento

El quórum general es de dos tercios de Maintainers activos. Si solo existe uno,
una E3 requiere aprobación documentada y ratificación en una Work Order
posterior tras auditoría y pruebas.

Toda enmienda normativa DEBE identificar texto anterior y propuesto,
clasificación E0–E3, contratos, compatibilidad, riesgos, pruebas, reversión,
aprobaciones, versión y fecha de entrada en vigor.

## 15. Excepciones temporales

Una excepción es temporal, no modifica la Constitución, no crea precedente y
NO DEBE utilizarse para evitar permanentemente una enmienda.

Solo PUEDE concederse cuando existe necesidad concreta, la conformidad inmediata
no es razonablemente posible, los riesgos están identificados y existen
controles compensatorios, fecha de expiración, remediación y reversión.

Toda excepción DEBE registrar:

- Identificador y norma afectada.
- Justificación y alcance exacto.
- Componentes y contratos afectados.
- Riesgos y controles compensatorios.
- Responsable, inicio y expiración.
- Work Order de remediación.
- Criterio de cierre y reversión.
- Aprobaciones.

Una excepción ordinaria requiere Arquitecto Responsable y mayoría simple. Una
excepción a No Destrucción, Mínimo Privilegio o Fallo Seguro requiere dos
tercios, Arquitecto Responsable, revisión independiente cuando exista y una
duración máxima de 30 días.

Las excepciones expiran automáticamente y NO DEBEN renovarse implícitamente.
Dos renovaciones consecutivas obligan a corregir el incumplimiento o proponer
una enmienda. Una excepción expirada DEBE provocar fallo de auditoría.

## 16. Incumplimiento y remediación

Existe incumplimiento cuando una obligación normativa no se satisface y no hay
una excepción vigente.

Ante incumplimiento:

1. DEBE detenerse la publicación afectada.
2. DEBE registrarse evidencia y alcance.
3. DEBE abrirse una Work Order de remediación.
4. DEBEN identificarse contratos y capacidades afectadas.
5. DEBE elegirse reversión, corrección o enmienda válida.
6. DEBEN ejecutarse pruebas y auditoría antes del cierre.

Un incumplimiento de No Destrucción, Mínimo Privilegio o Fallo Seguro DEBE
tratarse como prioridad crítica. El silencio, la falta de auditoría o el
desconocimiento NO DEBEN considerarse conformidad.

## 17. Entrada en vigor

Esta Constitución, versión 1.0.0, entra en vigor cuando el commit que la
incorpora haya superado la suite completa, sea aprobado conforme a WORK-009 y
sea publicado y verificado en la rama principal.

Las capacidades anteriores a su entrada en vigor DEBEN inventariarse y
auditarse de forma incremental. La entrada en vigor no convierte automáticamente
la deuda conocida en incumplimiento crítico, pero obliga a registrarla y
priorizarla.

## 18. Glosario mínimo

- **Arquitecto Responsable:** rol que custodia coherencia y decisiones
  constitucionales.
- **Auditoría:** comprobación reproducible entre normas, registros y runtime.
- **Builder:** componente que valida y construye una estructura gobernada.
- **Capacidad:** comportamiento que CamiloBuilder puede describir y ejecutar.
- **Contrato:** comportamiento público cuya estabilidad está gobernada.
- **Dato derivado:** información calculable desde una fuente canónica.
- **Excepción:** autorización temporal y trazable de incumplimiento limitado.
- **Maintainer:** persona autorizada para aprobar cambios del repositorio.
- **Normativo:** contenido que crea obligaciones constitucionales.
- **Plantilla:** fuente declarativa de archivos y estructura generada.
- **Reversión:** procedimiento para restaurar un estado conforme anterior.
- **Runtime:** estado ejecutable del sistema y sus registros activos.
- **Work Order:** unidad gobernada, incremental y trazable de cambio.

## Anexo A — Nota descriptiva

Este anexo es descriptivo y no crea obligaciones adicionales. La versión 1.0.0
se adopta antes de implementar registros JSON, API de capacidades, auditoría
ejecutable o CI constitucional. Esos mecanismos pertenecen a bloques posteriores
de WORK-009 y deberán implementarse mediante Work Orders aprobadas.
