-- Variante que proviene de un trámite TAD fusionado: conserva su link, costos y requisitos.
BEGIN;
ALTER TABLE tramite_variante ADD COLUMN tramite_origen_id uuid REFERENCES tramite (id) ON DELETE SET NULL;
COMMIT;
