# Invoice Intake (Shadow Mode)

Servicio generado para analizar un lote cerrado de referencias opacas. No modifica
Gmail, Drive, contabilidad ni los documentos originales. La configuración real,
credenciales, destinos y conocimiento empresarial viven fuera del código generado.

Los PDF se limitan a texto embebido; no se realiza OCR. XML con DTD o entidades se
rechaza. Un destino es siempre una propuesta analítica y nunca una orden de movimiento.

`integrity.build_integrity_report()` produce la cadena A-E del piloto real usando
solo referencias opacas, tamaños, hashes, framing y estados de validación. El
reporte nunca contiene bytes, base64url, texto extraído, previews o secretos.
