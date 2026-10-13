-- Control de calidad de la base antes de exportar. Correr con:
--   docker compose exec -T db psql -U tramites -d tramites < scripts/calidad.sql
-- Cada consulta lista casos a revisar; ninguna modifica datos.

\echo '== Resumen de trámites por estado'
SELECT estado, count(*) FROM tramite GROUP BY 1 ORDER BY 2 DESC;

\echo '== Trámites vigentes sin categoría (por organismo)'
SELECT o.nombre_oficial AS organismo, count(*) AS tramites
FROM tramite t JOIN organismo o ON o.id = t.organismo_id
WHERE t.estado = 'vigente' AND t.categoria_id IS NULL
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;

\echo '== Trámites vigentes sin destinatario (por categoría)'
SELECT coalesce(c.nombre, '(sin categoría)') AS categoria, count(*) AS tramites
FROM tramite t LEFT JOIN categoria c ON c.id = t.categoria_id
WHERE t.estado = 'vigente' AND NOT EXISTS (SELECT 1 FROM tramite_destinatario d WHERE d.tramite_id = t.id)
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;

\echo '== Trámites vigentes sin ningún canal'
SELECT t.slug, t.nombre_ciudadano FROM tramite t
WHERE t.estado = 'vigente' AND NOT EXISTS (SELECT 1 FROM canal c WHERE c.tramite_id = t.id AND c.activo)
ORDER BY 1 LIMIT 30;

\echo '== Organismos marcados para revisar'
SELECT * FROM v_organismo_a_revisar;

\echo '== Costos en pesos que no coinciden entre fuentes (misma variante)'
SELECT t.slug, c1.concepto AS concepto_1, c1.monto_max AS monto_1, c2.concepto AS concepto_2, c2.monto_max AS monto_2
FROM costo c1
JOIN costo c2 ON c2.tramite_id = c1.tramite_id AND c2.id > c1.id AND c2.unidad = c1.unidad
               AND coalesce(c2.variante_id, 0) = coalesce(c1.variante_id, 0) AND c2.concepto <> c1.concepto
JOIN tramite t ON t.id = c1.tramite_id
WHERE c1.vigente_hasta IS NULL AND c2.vigente_hasta IS NULL AND c1.unidad = 'ARS'
  AND NOT c1.gratuito AND NOT c2.gratuito AND c1.monto_max IS NOT NULL AND c2.monto_max IS NOT NULL
  AND NOT (c1.monto_min <= c2.monto_max AND c1.monto_max >= c2.monto_min)
ORDER BY 1;

\echo '== Trámites de prueba del catálogo de TAD (se excluyen de los análisis)'
SELECT t.slug, t.nombre_ciudadano FROM tramite t WHERE t.nombre_ciudadano ~* 'testing de performance|prueba adm';

\echo '== Fichas de argentina.gob.ar vinculadas a un trámite fusionado o dado de baja'
SELECT f.id_externo, t.estado, t.nombre_ciudadano FROM fuente f JOIN tramite t ON t.id = f.tramite_id
WHERE f.tipo = 'ficha_argentina_gob_ar' AND t.estado <> 'vigente';

\echo '== Requisitos sospechosamente largos (posible texto que no es requisito)'
SELECT t.slug, left(r.descripcion, 120) AS requisito FROM requisito r JOIN tramite t ON t.id = r.tramite_id
WHERE length(r.descripcion) > 400 ORDER BY length(r.descripcion) DESC LIMIT 15;

\echo '== Últimas corridas de ingesta'
SELECT id, fuente_tipo, estado, iniciada_en::date, filas_leidas, altas, cambios, bajas, sin_cambios
FROM ingesta_corrida ORDER BY id DESC LIMIT 10;
