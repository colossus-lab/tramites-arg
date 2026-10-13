-- Requisitos y costos extraídos automáticamente de la descripción HTML de TAD.
BEGIN;
ALTER TABLE requisito
    ADD COLUMN fuente_id integer REFERENCES fuente (id) ON DELETE CASCADE,
    ADD COLUMN seccion text,
    ADD COLUMN obligatorio boolean NOT NULL DEFAULT true;
CREATE INDEX requisito_fuente_idx ON requisito (fuente_id);
ALTER TABLE costo ADD COLUMN detalle text;
COMMIT;
