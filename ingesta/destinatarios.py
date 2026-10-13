"""Destinatarios automáticos de los trámites (quién lo hace: persona, empresa, organismo…).

    python -m ingesta.destinatarios                 asigna y guarda
    python -m ingesta.destinatarios --dry-run       muestra el resultado y deshace
    python -m ingesta.destinatarios --muestras 5    ejemplos por destinatario para revisar

Un trámite puede tener varios destinatarios. Se asignan por palabras del nombre (y del
"¿A quién está dirigido?" de la ficha de argentina.gob.ar, si la tiene), por el
validador de identidad de TAD y, si nada coincide, por la categoría. Los trámites con
algún destinatario manual (inventario) no se tocan.
"""

import argparse
import random
import re
import sys
from collections import Counter, defaultdict

import psycopg2

from ingesta import normalizar as n
from ingesta.tad import DATABASE_URL

# Trámites entre organismos del Estado: comunicaciones con el Congreso, AGN, firma digital
# para autoridades de registro, servicios de integración, municipios y provincias.
ORGANISMO_PUBLICO = re.compile(
    r"^PLN\b|AUDITORIA GENERAL|\bAGN\b|AUTORIDAD(ES)? DE REGISTRO|\bAC ONTI\b|AC MODERNIZACION|AUTENTICAR|\bVPN\b|"
    r"FIRMA DIGITAL (BAJA|CESE|CONFORMACION|DESIGNACION|MODIFICACION|SOLICITUD)|PROYECTOS TECNOLOGICOS DEL SECTOR PUBLICO|"
    r"BIENES INFORMATICOS|BIENES Y SERVICIOS TIC|NUBE HIBRIDA|\bMUNICIPIOS?\b|\bPROVINCIAS\b|ORGANISMOS? PUBLICOS?|"
    r"ENTE LICENCIANTE|PREVIA CONFORMIDAD"
)

POR_NOMBRE = [
    ("organismo_publico", ORGANISMO_PUBLICO),
    ("empresa", re.compile(
        r"PERSONAS? JURIDICAS?|SOCIEDAD|EMPRESA|\bPYMES?\b|MIPYME|IMPORTADOR|EXPORTADOR|FABRICANTE|COMERCIALIZADOR|"
        r"DISTRIBUIDOR|PROVEEDOR|\bSIPRO\b|FACTURA|ORDEN DE COMPRA|LICENCIATARI|CONCESIONARI|DROGUERIA|LABORATORIO|"
        r"\bPLANTAS?\b|INDUSTRI|ASEGURADORA|AGENTES? DEL MERCADO|EMISORA|OPERADOR(ES)? (POSTAL|DE TELECOM|LOGISTIC)")),
    ("profesional", re.compile(
        r"PROFESIONAL|MATRICUL|DIRECTOR(ES)? TECNICO|ESCRIBAN|CONTADOR|ABOGAD|INSTRUCTOR|\bPILOTO|"
        r"DESPACHANTE|PRODUCTOR(ES)? ASESOR|MANDATARI|PERITO|TRADUCTOR|CERTIFICADO DE OPERADOR|INVESTIGADOR")),
    ("cooperativa_mutual", re.compile(r"COOPERATIV|MUTUAL")),
    ("organizacion_civil", re.compile(
        r"ASOCIACION(ES)? CIVIL|FUNDACI|\bONGS?\b|BIEN PUBLICO|ENTIDAD(ES)? RELIGIOS|REGISTRO NACIONAL DE CULTOS|"
        r"\bCLUB(ES)?\b|BIBLIOTECAS? POPULAR|CONABIP|BOMBEROS|SINDICA|GREMIAL|FEDERACION|CONFEDERACION|"
        r"ASOCIACIONES SINDICALES|EFECTOR(ES)? SOCIAL")),
    ("emprendedor", re.compile(r"EMPRENDED|MONOTRIBUT")),
    ("pf_no_residente", re.compile(r"NO RESIDENTE")),
    ("pf_extranjero_residente", re.compile(
        r"\bRADICACION|RESIDENCIA (PERMANENTE|TEMPORARIA|TRANSITORIA|PRECARIA)|PERSONAS? EXTRANJERAS?|"
        r"CIUDADANOS? EXTRANJEROS?")),
    ("pf_ciudadano", re.compile(
        r"PERSONAS? HUMANAS?|CIUDADAN|\bPARTICULAR|JUBILAD|PENSIONAD|BENEFICIARI|ESTUDIANT|\bDNI\b|PASAPORTE|"
        r"ANTECEDENTES PENALES|LICENCIA DE CONDUCIR|CONSUMIDOR|DENUNCIA|RECLAMO|CERTIFICADO NAUTICO|"
        r"DISCAPACI|VETERANO|EX SOLDADO|HIJO|FAMILIA")),
]

# Si el nombre no dice nada, la categoría da una pista razonable.
POR_CATEGORIA = {
    "identidad": "pf_ciudadano", "viajes": "pf_ciudadano", "seguridad_social": "pf_ciudadano",
    "programas_sociales": "pf_ciudadano", "discapacidad": "pf_ciudadano", "familia": "pf_ciudadano",
    "migraciones": "pf_extranjero_residente", "consumo": "pf_ciudadano",
    "comercio_exterior": "empresa", "empresas": "empresa", "finanzas": "empresa", "energia": "empresa",
    "organizaciones": "organizacion_civil",
}


# "Matrícula" o "profesional" que no hablan de una persona que ejerce una profesión.
NO_ES_PROFESIONAL = re.compile(r"BUQUE|AERONAV|EMBARCACI|VEHICUL|ENFERMEDADES PROFESIONALES|FORMACION PROFESIONAL")


def destinatarios(nombre, validadores, categoria):
    """-> {tipo: regla}. Vacío si nada coincide."""
    k = n.clave(nombre or "")
    resultado = {}
    for tipo, patron in POR_NOMBRE:
        if patron.search(k) and not (tipo == "profesional" and NO_ES_PROFESIONAL.search(k)):
            resultado[tipo] = "palabra_clave"
    if "organismo_publico" in resultado:
        # Un trámite entre organismos no es a la vez para el público general.
        return {"organismo_publico": "palabra_clave"}
    if not resultado and categoria in POR_CATEGORIA:
        resultado[POR_CATEGORIA[categoria]] = "categoria"
    if any(n.clave(v) in ("NIC", "NIC AFIP") for v in validadores or []):
        resultado.setdefault("pf_no_residente", "validador")
    return resultado


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--dry-run", action="store_true", help="asigna y hace rollback")
    parser.add_argument("--muestras", type=int, default=0, help="ejemplos por destinatario a imprimir")
    args = parser.parse_args(argv)

    por_tipo, por_regla, ejemplos, cambios, sin_destinatario = Counter(), Counter(), defaultdict(list), 0, 0
    conn = psycopg2.connect(args.database_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """SELECT t.id, t.nombre_ciudadano || coalesce(' ' || (SELECT string_agg(fi.datos ->> 'dirigido', ' ')
                                                                 FROM fuente fi WHERE fi.tramite_id = t.id
                                                                 AND fi.tipo = 'ficha_argentina_gob_ar'), ''),
                          c.codigo,
                          coalesce(csv.datos -> 'validadores', '[]'::jsonb),
                          coalesce((SELECT jsonb_object_agg(d.tipo, d.regla) FROM tramite_destinatario d
                                    WHERE d.tramite_id = t.id AND d.origen = 'auto'), '{}'::jsonb)
                   FROM tramite t
                   LEFT JOIN categoria c ON c.id = t.categoria_id
                   LEFT JOIN fuente csv ON csv.tramite_id = t.id AND csv.tipo = 'csv_tad'
                   WHERE NOT EXISTS (SELECT 1 FROM tramite_destinatario d WHERE d.tramite_id = t.id AND d.origen = 'manual')"""
            )
            for tramite_id, nombre, categoria, validadores, actuales in cur.fetchall():
                deseados = destinatarios(nombre, validadores, categoria)
                sin_destinatario += not deseados
                for tipo, regla in deseados.items():
                    por_tipo[tipo] += 1
                    por_regla[regla] += 1
                    ejemplos[tipo].append((regla, nombre))
                if deseados == actuales:
                    continue
                cambios += 1
                cur.execute("DELETE FROM tramite_destinatario WHERE tramite_id = %s AND origen = 'auto'", (tramite_id,))
                for tipo, regla in deseados.items():
                    cur.execute(
                        "INSERT INTO tramite_destinatario (tramite_id, tipo, origen, regla) VALUES (%s, %s, 'auto', %s)",
                        (tramite_id, tipo, regla),
                    )
            if args.dry_run:
                conn.rollback()
    finally:
        conn.close()

    print(f"\n{'Simulación' if args.dry_run else 'Destinatarios'}: cambios en {cambios} trámites | "
          f"sin destinatario: {sin_destinatario}")
    print("  por regla: " + ", ".join(f"{r} {k}" for r, k in por_regla.most_common()))
    for tipo, k in por_tipo.most_common():
        print(f"    {k:5d}  {tipo}")
    if args.muestras:
        random.seed(2)
        for tipo, filas in ejemplos.items():
            print(f"\n  == {tipo}")
            for regla, nombre in random.sample(filas, min(args.muestras, len(filas))):
                print(f"    {regla:13} {nombre[:95]}")


if __name__ == "__main__":
    sys.exit(main())
