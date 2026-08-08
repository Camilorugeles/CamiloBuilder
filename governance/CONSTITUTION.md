# Constitución de CamiloBuilder

**Versión constitucional:** 2.0.0
**Estado:** Vigente tras el cutover coordinado de Constitution 2.0

## 1. Preámbulo y reconstitución

CamiloBuilder construye proyectos y componentes de Camilo OS de forma segura,
determinista, compatible y auditable. Esta Constitución gobierna las garantías,
invariantes y límites que deben preservarse mientras el sistema evoluciona.

Constitution 1.0.0 estableció garantías técnicas valiosas, especialmente la no
destrucción, el fallo seguro, el determinismo, la compatibilidad y la
trazabilidad. También contenía un defecto de bootstrap y sobreespecificaba los
mecanismos operativos de gobierno, creando dependencias circulares al intentar
gobernar la evolución del propio gobierno.

Constitution 2.0.0 supersede explícitamente Constitution 1.0.0 mediante una
decisión constituyente de la autoridad material real del repositorio. Esta
reconstitución no finge continuidad procedimental perfecta bajo el modelo
supersedido y no reconstruye, altera ni reinterpreta retrospectivamente Work
Orders, commits, schemas o decisiones históricas.

La historia de Constitution 1.0.0 permanece íntegra en Git. WORK-009, WORK-011
y los registros legacy conservan el significado que tenían al publicarse.

## 2. Identidad y propósito

CamiloBuilder es el constructor gobernado de estructuras de Camilo OS. Comprende
el CLI, los builders, el motor y catálogo de plantillas, las superficies
contractuales, las pruebas y los mecanismos técnicos de verificación.

CamiloBuilder DEBE:

- validar antes de modificar;
- preservar contenido existente;
- producir resultados deterministas;
- declarar y verificar compatibilidad;
- mantener evidencia proporcional al riesgo;
- evolucionar mediante cambios pequeños y reversibles;
- describir automáticamente los hechos derivables de sus fuentes canónicas.

CamiloBuilder NO DEBE convertirse implícitamente en runtime de Camilo OS,
gestor de paquetes, sistema de despliegue, ejecutor de código generado o motor
de plugins.

## 3. Alcance y autoridad

Esta Constitución es la norma superior dentro del repositorio. Gobierna el
comportamiento del software y el proceso por el que se preservan sus garantías.

La autoridad humana y material no es creada por JSON ni por CamiloBuilder.
Procede de las personas que mantienen realmente el proyecto y de mecanismos
externos como GitHub, los permisos del repositorio, branch protection, reviews
y control de publicación.

El repositorio PUEDE documentar esa autoridad y verificar aspectos técnicos,
pero NO DEBE presentar registros internos como prueba criptográfica de
legitimidad humana, independencia, consenso o mayoría.

CamiloBuilder no crea una Root of Trust interna, un IAM ni un Approval Registry.
La situación humana vigente se documenta de forma sencilla y trazable sin
simular estructuras organizativas inexistentes.

La precedencia normativa es:

1. Constitución vigente.
2. Garantías contractuales públicas vigentes.
3. Política operativa de governance.
4. Decisiones arquitectónicas y cambios gobernados aplicables.
5. Código, pruebas y documentación descriptiva.

Una fuente inferior NO DEBE reducir implícitamente una garantía superior.

## 4. Fuentes de verdad y límites de verificación

Las decisiones humanas, los hechos técnicos y la evidencia externa son clases
distintas de información:

- una persona decide o afirma autoridad, riesgo y aceptación;
- el software verifica únicamente hechos observables;
- Git conserva historia técnica, commits, diferencias y reversión;
- GitHub materializa publicación, permisos, reviews y checks;
- CI registra la ejecución de validaciones.

CamiloBuilder NO DEBE representar una decisión humana como si hubiese sido
demostrada automáticamente. Una obligación no automatizada DEBE permanecer
visible como afirmación manual u obligación no verificada.

La versión constitucional tiene una única fuente canónica: este documento.

## 5. Principios constitucionales

### 5.1 No Destrucción

Ninguna operación DEBE sobrescribir, eliminar o invalidar contenido existente
sin una acción explícita, acotada, trazable y reversible. La ausencia de
conflicto aparente NO autoriza destrucción silenciosa.

### 5.2 Fallo Seguro y Acceso Mínimo

Ante corrupción, ambigüedad, incompatibilidad o validación insuficiente,
CamiloBuilder DEBE detenerse sin modificar el destino ni presentar un estado
parcial como correcto.

Cada componente DEBE acceder únicamente a los archivos, rutas y capacidades
necesarios para su responsabilidad. La incertidumbre se resuelve mediante la
alternativa más segura y menos destructiva.

### 5.3 Determinismo

Las mismas entradas, versiones y fuentes DEBEN producir resultados equivalentes
y auditables. Listados y salidas de máquina DEBEN mantener orden estable.

Red, reloj, filesystem y estado externo NO DEBEN incorporarse implícitamente.
Cuando sean necesarios, deben proporcionarse como entradas explícitas.

### 5.4 Compatibilidad Explícita

La compatibilidad DEBE declararse y verificarse proporcionalmente al riesgo; no
se presume por intención. Un cambio incompatible exige migración, deprecación,
ventana de transición o versión incompatible explícita.

Las superficies contractuales incluyen CLI, JSON público, API Python pública,
manifests, estructura y contenido generado, idempotencia, no sobrescritura y
formatos de máquina consumidos externamente.

### 5.5 Trazabilidad

Todo cambio relevante DEBE poder relacionarse con su decisión, alcance,
evidencia técnica, riesgos y reversión. La evidencia DEBE referenciar su fuente
canónica y NO DEBE duplicarse sin una necesidad demostrable.

La trazabilidad no exige que todo cambio utilice el mismo artefacto ni que toda
información se mantenga dentro de una Work Order.

### 5.6 Reversibilidad

Todo cambio relevante DEBE tener una estrategia realista para restaurar un
estado seguro. Cuando una decisión no sea reversible, esa condición y sus
consecuencias DEBEN declararse antes de adoptarla.

Un git revert restaura contenido técnico, pero no borra el hecho histórico de
que una norma o decisión estuvo vigente.

### 5.7 Evolución Incremental

Los cambios DEBEN ser pequeños, verificables y separables. La evidencia y la
ceremonia DEBEN ser proporcionales al impacto. Un cambio rutinario no requiere
automáticamente una Work Order.

Los mecanismos operativos de governance PUEDEN evolucionar mediante decisiones
arquitectónicas y cambios trazables siempre que no reduzcan estas garantías.

### 5.8 No Deriva y Autoconocimiento

La información derivable DEBE calcularse desde su fuente canónica. No debe
mantenerse una segunda fuente normativa para facilitar una lectura que pueda
realizarse de forma fiable.

CamiloBuilder DEBE describir automáticamente aquello que sea realmente
derivable del runtime y de fuentes gobernadas. NO DEBE fingir que puede derivar
legitimidad, autoridad o calidad de una decisión humana.

### 5.9 Simplicidad Arquitectónica

No DEBE introducirse un mecanismo cuyo coste conceptual u operativo exceda el
problema real que resuelve. Toda abstracción, registro o schema requiere un
consumidor, una responsabilidad y una necesidad demostrables.

La arquitectura se mantiene viva mediante trazabilidad, pruebas, verificaciones
y evolución incremental, no mediante acumulación de ceremonias.

## 6. Separación entre Constitución y Governance

Esta Constitución gobierna garantías, invariantes, límites y precedencia.

`GOVERNANCE.md` gobierna procesos operativos como categorías de cambio, Work
Orders, ADRs, revisión, excepciones, migraciones, versiones y releases.

La política operativa PUEDE cambiar de representación sin enmienda
constitucional cuando preserve estas garantías. No puede reducirlas ni ocultar
obligaciones no verificadas.

La Constitución NO fija campos JSON, schemas, estados concretos de Work Orders,
mecánica de commits, implementación de CI ni detalles internos del CLI,
builders o plantillas.

## 7. Metagobierno

Un cambio de esta Constitución requiere una decisión constituyente explícita,
impacto declarado, riesgos, evidencia y tratamiento de reversibilidad. Una
reducción de garantías exige una nueva versión mayor.

Una modificación de governance que preserve garantías puede seguir el proceso
arquitectónico definido por la política vigente. Ningún procedimiento puede
declararse legítimo solo porque un archivo JSON lo acepte.

## 8. Conflictos y comportamiento seguro

Ante conflicto entre Constitución, política, registros, código o ejecución:

1. prevalece la garantía constitucional aplicable;
2. se detiene la publicación afectada cuando exista riesgo material;
3. se identifica alcance y evidencia;
4. se elige corrección, reversión o supersesión explícita;
5. se ejecutan las verificaciones aplicables antes de reanudar.

La ambigüedad NO DEBE resolverse reduciendo garantías.

## 9. Historia y legacy

Constitution 1.0.0, GOVERNANCE 1.0.0, WORK-009, WORK-011, schemas v1/v2 y sus
fixtures permanecen interpretables como legacy governance records.

Legacy significa preservado para lectura histórica, no obligatorio como modelo
para nuevos cambios. No existe migración implícita ni reinterpretación
retrospectiva.

WORK-010 podrá documentarse posteriormente como registro histórico ligero.
WORK-011 permanece sin cambios hasta una cancelación futura explícita de su
alcance anterior.

## 10. Entrada en vigor

Constitution 2.0.0 entra en vigor cuando el commit coordinado que contiene esta
Constitución, GOVERNANCE 2.0, la declaración del Maintainer y las adaptaciones
técnicas mínimas supera la suite completa, la verificación técnica vigente y CI,
y es publicado en la rama principal.

La declaración humana correspondiente se conserva en `MAINTAINERS.md` y la
decisión arquitectónica en ADR-0001. La ADR documenta la decisión; no crea por
sí sola autoridad humana.

## 11. Glosario mínimo

- **ADR:** registro de una decisión arquitectónica y su razonamiento.
- **Autoridad material:** capacidad humana y externa real para mantener y publicar el proyecto.
- **Contrato:** comportamiento observable cuya compatibilidad está protegida.
- **Dato derivado:** información calculable desde una fuente canónica.
- **Legacy:** artefacto histórico preservado pero no obligatorio para nuevos cambios.
- **Maintainer:** persona con responsabilidad material de mantenimiento.
- **Reconstitución:** supersesión explícita que reconoce discontinuidad normativa.
- **Reversión:** procedimiento para restaurar un estado técnico seguro.
- **Work Order:** registro ligero de un cambio gobernado cuando su impacto lo requiere.
