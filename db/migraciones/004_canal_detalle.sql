-- Aclaración libre del canal ("Junta evaluadora con turno", "Atención Virtual o Mi ANSES").
BEGIN;
ALTER TABLE canal ADD COLUMN detalle text;
COMMIT;
