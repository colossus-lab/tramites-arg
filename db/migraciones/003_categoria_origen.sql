-- Origen de la categoría: 'manual' (inventario o edición) o 'auto' (ingesta.clasificar).
-- La clasificación automática nunca pisa una categoría manual.
BEGIN;
ALTER TABLE tramite ADD COLUMN categoria_origen text CHECK (categoria_origen IN ('manual', 'auto'));
COMMIT;
