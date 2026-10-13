-- Para bases creadas antes de que schema.sql incluyera el tipo de fuente 'api_tad'.
BEGIN;
ALTER TABLE fuente DROP CONSTRAINT fuente_tipo_check;
ALTER TABLE fuente ADD CONSTRAINT fuente_tipo_check
    CHECK (tipo IN ('csv_tad', 'api_tad', 'ficha_argentina_gob_ar', 'sitio_organismo',
                    'boletin_oficial', 'acceso_informacion', 'manual'));
COMMIT;
