-- Regla de ingesta.clasificar que asignó la categoría automática (para auditar las de baja confianza).
BEGIN;
ALTER TABLE tramite ADD COLUMN categoria_regla text;
COMMIT;
