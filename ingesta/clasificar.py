"""Clasificación automática de trámites en la taxonomía de categorías (nivel 1).

    python -m ingesta.clasificar                 clasifica y guarda
    python -m ingesta.clasificar --dry-run       muestra el resultado y deshace
    python -m ingesta.clasificar --muestras 5    imprime ejemplos por regla para revisar

Reglas, en orden de prioridad:
  1. comercio_exterior: el nombre habla de importación, exportación, aduana, etc.
  2. organismo: organismos con competencia clara (SENASA -> agro, ANMAT -> salud).
  3. palabras clave del nombre.
  4. etiqueta temática de TAD ("Salud y Seguridad Social", "Derecho de autor"). La de VUCE no se usa:
     incluye trámites que no son de comercio exterior (metrología, registro de PCB).
  5. ministerio, solo para trámites del ministerio mismo (baja confianza).
Nunca pisa una categoría cargada a mano (tramite.categoria_origen = 'manual').
Si ninguna regla aplica, el trámite queda sin categoría.
"""

import argparse
import random
import re
import sys
from collections import Counter, defaultdict

import psycopg2

from ingesta import normalizar as n
from ingesta.tad import DATABASE_URL

COMERCIO_EXTERIOR = re.compile(
    r"IMPORTACI|EXPORTACI|IMPORTAR|EXPORTAR|IMPORTADOR|EXPORTADOR|COMERCIO EXTERIOR|ADUAN|CERTIFICADO DE ORIGEN|"
    r"DESTINACI|ZONAS? FRANCAS?|ORIGEN DE MERCADERIA|TRANSITO INTERNACIONAL|DRAWBACK|DUMPING|LICENCIAS? NO AUTOMATICA"
)

POR_ORGANISMO = {
    "SENASA": "agro", "INV": "agro", "INASE": "agro", "INTA": "agro",
    "ANMAT": "salud", "SSS": "salud", "HP": "salud", "INCUCAI": "salud", "INSSJP": "salud", "IOSFA": "salud",
    "SND": "discapacidad",
    "ENACOM": "telecomunicaciones", "NIC Argentina": "telecomunicaciones",
    "IGJ": "empresas", "CNDC": "empresas", "INTI": "empresas",
    "INAES": "organizaciones", "AFE": "organizaciones",
    "CNV": "finanzas", "SSN": "finanzas", "BICE": "finanzas",
    "ANAC": "transporte", "CNRT": "transporte", "PNA": "transporte", "ORSNA": "transporte", "JST": "transporte",
    "AGP": "transporte", "ADIFSE": "transporte", "SOFSE": "transporte", "DNV": "transporte",
    "ANSV": "vehiculos", "DNRPA": "vehiculos",
    "RENAR": "armas",
    "RENAPER": "identidad",
    "DNM": "migraciones",
    "ANSES": "seguridad_social", "IAFPRPM": "seguridad_social", "CRJPPF": "seguridad_social",
    "SRT": "trabajo", "STEYSS": "trabajo",
    "DNDA": "propiedad_intelectual", "INPI": "propiedad_intelectual",
    "INCAA": "cultura",
    "CONEAU": "educacion", "CONICET": "educacion",
    "ACUMAR": "ambiente", "APN": "ambiente",
    "AABE": "propiedad",
    "ARCA": "impuestos", "TFN": "impuestos",
    "SENNAF": "familia",
    "CNCPS": "programas_sociales",
    "GNA": "seguridad", "PFA": "seguridad", "ARA": "seguridad",
    "RNR": "justicia", "OA": "justicia",
    "AAIP": "transversal",
    "SIYC": "consumo",
}

# Palabras clave sobre el nombre normalizado (n.clave). Gana la primera que coincide.
PALABRAS_CLAVE = [
    ("discapacidad", r"DISCAPACI"),
    ("armas", r"\bARMAS?\b|EXPLOSIV|MATERIALES CONTROLADOS|LEGITIMO USUARIO"),
    ("migraciones", r"MIGRA|RADICACI|\bVISAS?\b|RESIDENCIA PRECARIA"),
    ("viajes", r"APOSTILL|LEGALIZACI|CONSULA|PASAPORTE"),
    ("propiedad_intelectual", r"PROPIEDAD INTELECTUAL|\bMARCAS?\b|PATENTE|DERECHO DE AUTOR|OBRAS? INEDITA|"
                              r"CULTIVAR|PUBLICACION PERIODICA"),
    ("seguridad_social", r"JUBILACI|PENSION|PREVISIONAL|HABER(ES)? DE (RETIRO|PASIVIDAD)|RETIRO MILITAR"),
    ("vehiculos", r"VEHICUL|AUTOMOTOR|LICENCIA DE CONDUCIR|MOTOVEHICUL"),
    ("trabajo", r"\bEMPLEO|TRABAJADOR|LABORAL|SINDICA|GREMIAL|CONVENIO COLECTIVO|PASANTIA|\bTRABAJO\b"),
    ("educacion", r"EDUCA|ESCUELA|UNIVERSIT|\bTITULOS?\b|CONVALIDACI|\bBECAS?\b|ESTUDIANT|DOCENTE|INVESTIGADOR|"
                  r"CIENTIFIC|POS(T)?GRADO|CARRERAS? DE GRADO"),
    ("salud", r"SALUD|\bMEDIC(O|A|OS|AS|AMENTOS?|INA)\b|HOSPITAL|SANITARI|FARMAC|DROGUER|ODONTOLOG|ENFERMER|"
              r"VACUN|OBRA SOCIAL"),
    ("cultura", r"CULTUR|ARTIST|MUSEO|\bLIBROS?\b|BIBLIOTEC|AUDIOVISUAL|\bCINE|TEATRO|MUSICA|"
                r"PATRIMONIO (CULTURAL|HISTORICO)"),
    ("familia", r"NINEZ|\bNIN(A|O)S?\b|ADOLESCEN|FAMILIA|ADOPCI|MATRIMONIO"),
    ("empresas", r"SIPRO|PROVEEDOR"),  # registro de proveedores del Estado, aunque nombre cooperativas
    ("organizaciones", r"COOPERATIV|MUTUAL|ASOCIACION(ES)? CIVIL|FUNDACI|BIEN PUBLICO|BOMBEROS"),
    ("consumo", r"CONSUMIDOR|LEALTAD COMERCIAL"),
    ("finanzas", r"\bSEGUROS?\b|ASEGURADOR|REASEGUR|FINANCIER|MERCADO DE CAPITALES|FONDOS? COMUN|FIDEICOMISO|"
                 r"CAPITALIZACION Y AHORRO"),
    ("transporte", r"TRANSPORT|FERROVI|FERROCARRIL|AEROPUERT|AERONAV|AEROCLUB|\bPUERTOS?\b|PORTUARI|BUQUE|"
                   r"EMBARCACI|NAVEGACI|NAUTIC|PEAJE"),
    ("ambiente", r"AMBIENT|RESIDUO|FORESTAL|BOSQUE|FAUNA|FLORA|CLIMA|EMISION|EFLUENTE|PARQUES? NACIONAL|"
                 r"BIODIVERSIDAD"),
    ("agro", r"AGRO|AGRIC|GANAD|PESCA|PESQUER|SEMILLA|CULTIVO|VITIVIN|\bVINOS?\b|BOVIN|PORCIN|AVICOL|APICOL|"
             r"LECHER|\bGRANOS?\b|FITOSANIT|ZOOSANIT"),
    ("telecomunicaciones", r"TELECOMUNIC|INTERNET|RADIODIFUS|TELEVISI|POSTAL|ESPECTRO|SATELIT"),
    ("justicia", r"JUDICIAL|\bOFICIOS?\b|ANTECEDENTES PENALES|MEDIACI|REINCIDENCIA"),
    ("impuestos", r"IMPUEST|TRIBUT|\bFISCAL\b|GANANCIAS|MONOTRIBUT"),
    ("propiedad", r"INMUEBLE|VIVIENDA|CATASTR|TIERRAS? FISCAL|BIENES DEL ESTADO|LOCACION"),
    ("empresas", r"SOCIEDAD|EMPRESA|PYME|INDUSTRI|INVERSION|REGIMEN DE PROMOCION|PROVEEDOR|SIPRO|PRODUCTIV|"
                 r"EMPRENDED|\bRIGI\b|CONCENTRACION(ES)? ECONOMICA"),
    ("seguridad", r"SEGURIDAD|POLICI|GENDARMER|PREFECTUR|FUERZAS ARMADAS|DEFENSA NACIONAL|MILITAR"),
    ("transversal", r"ACCESO A LA INFORMACION|INFORMACION PUBLICA|TOMA DE VISTA|VISTA DE (LAS )?ACTUACIONES|"
                    r"PRESENTACION (GENERAL|CIUDADANA)|RECURSO|SOLICITUD GENERAL"),
]
PALABRAS_CLAVE = [(codigo, re.compile(patron)) for codigo, patron in PALABRAS_CLAVE]

POR_ETIQUETA = {
    "SALUD Y SEGURIDAD SOCIAL": "salud",
    "EDUCACION Y CULTURA": "educacion",
    "SEGURIDAD Y DEFENSA": "seguridad",
    "DERECHO DE AUTOR": "propiedad_intelectual",
    "PRODUCCION TURISMO Y TRABAJO": "empresas",
    "EMPRENDEDORES": "empresas",
    "PEQUENAS Y MEDIANAS EMPRESAS": "empresas",
    "MIPYME": "empresas",
    "TECNOLOGIA DE LA INFORMACION Y COMUNICACION TIC": "telecomunicaciones",
    "DOMINIOS DE INTERNET": "telecomunicaciones",
    "REGISTRO NACIONAL DE EFECTORES DE DESARROLLO LOCAL Y ECONOMIA SOCIAL": "organizaciones",
}

POR_MINISTERIO = {
    "MSAL": "salud", "MJ": "justicia", "MSN": "seguridad", "MD": "seguridad", "MECON": "empresas",
}


def clasificar(nombre, organismo, ministerio, etiquetas):
    """-> (código de categoría, regla) o (None, None)."""
    k = n.clave(nombre or "")
    if COMERCIO_EXTERIOR.search(k):
        return "comercio_exterior", "comercio_exterior"
    if organismo in POR_ORGANISMO:
        return POR_ORGANISMO[organismo], "organismo"
    for codigo, patron in PALABRAS_CLAVE:
        if patron.search(k):
            return codigo, "palabra_clave"
    for etiqueta in etiquetas or []:
        codigo = POR_ETIQUETA.get(n.clave(etiqueta))
        if codigo:
            return codigo, "etiqueta"
    if organismo == ministerio and ministerio in POR_MINISTERIO:
        return POR_MINISTERIO[ministerio], "ministerio"
    return None, None


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--dry-run", action="store_true", help="clasifica y hace rollback")
    parser.add_argument("--muestras", type=int, default=0, help="ejemplos por regla a imprimir")
    args = parser.parse_args(argv)

    por_categoria, por_regla, ejemplos = Counter(), Counter(), defaultdict(list)
    cambios = 0
    conn = psycopg2.connect(args.database_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, id FROM categoria")
            categorias = dict(cur.fetchall())
            cur.execute(
                """SELECT t.id, t.nombre_ciudadano, o.sigla, coalesce(p.sigla, o.sigla),
                          coalesce(api.datos -> 'etiquetas', '[]'::jsonb), t.categoria_id, t.categoria_regla
                   FROM tramite t
                   JOIN organismo o ON o.id = t.organismo_id
                   LEFT JOIN organismo p ON p.id = o.padre_id
                   LEFT JOIN fuente api ON api.tramite_id = t.id AND api.tipo = 'api_tad'
                   WHERE t.categoria_origen IS DISTINCT FROM 'manual'"""
            )
            for tramite_id, nombre, organismo, ministerio, etiquetas, actual, regla_actual in cur.fetchall():
                codigo, regla = clasificar(nombre, organismo, ministerio, etiquetas)
                por_categoria[codigo or "(sin categoría)"] += 1
                por_regla[regla or "(ninguna)"] += 1
                ejemplos[regla or "(ninguna)"].append((codigo, organismo, nombre))
                categoria_id = categorias.get(codigo)
                if (categoria_id, regla) != (actual, regla_actual):
                    cur.execute(
                        """UPDATE tramite SET categoria_id = %s, categoria_regla = %s,
                                  categoria_origen = CASE WHEN %s IS NULL THEN NULL ELSE 'auto' END
                           WHERE id = %s""",
                        (categoria_id, regla, categoria_id, tramite_id),
                    )
                    cambios += 1
            cur.execute("SELECT count(*) FROM tramite WHERE categoria_origen = 'manual'")
            manuales = cur.fetchone()[0]
            if args.dry_run:
                conn.rollback()
    finally:
        conn.close()

    total = sum(por_regla.values())
    print(f"\n{'Simulación' if args.dry_run else 'Clasificación'}: {total} trámites automáticos "
          f"(+{manuales} con categoría manual) | cambios: {cambios}")
    print("  por regla: " + ", ".join(f"{r} {k} ({k / total:.0%})" for r, k in por_regla.most_common()))
    print("  por categoría:")
    for codigo, k in por_categoria.most_common():
        print(f"    {k:5d}  {codigo}")
    if args.muestras:
        random.seed(1)
        for regla, filas in ejemplos.items():
            print(f"\n  == {regla}")
            for codigo, organismo, nombre in random.sample(filas, min(args.muestras, len(filas))):
                print(f"    {codigo or '-':22} {organismo or '':8} {nombre[:90]}")


if __name__ == "__main__":
    sys.exit(main())
