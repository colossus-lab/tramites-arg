-- Origen del destinatario: 'manual' (inventario) o 'auto' (ingesta.destinatarios), y regla que lo asignó.
BEGIN;
ALTER TABLE tramite_destinatario
    ADD COLUMN origen text NOT NULL DEFAULT 'manual' CHECK (origen IN ('manual', 'auto')),
    ADD COLUMN regla text;
COMMIT;
