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
    r"IMPORTACI|EXPORTACI|IMPORTAR|EXPORTAR|IMPORTADOR|EXPORTADOR|COMERCIO EXTERIOR|ADUAN|CERTIFICADOS? DE ORIGEN|"
    r"DESTINACI|ZONAS? FRANCAS?|ORIGEN DE MERCADERIA|ORIGEN (NO )?PREFERENCIAL|TRANSITO INTERNACIONAL|DRAWBACK|DUMPING|LICENCIAS? NO AUTOMATICA"
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
    "CONEAU": "educacion",
    "ENREGE": "energia", "ENARGAS": "energia", "ARN": "energia",
    "CONICET": "ciencia_tecnologia", "Agencia I+D+i": "ciencia_tecnologia", "CNEA": "ciencia_tecnologia",
    "CONAE": "ciencia_tecnologia",
    "ACUMAR": "ambiente", "APN": "ambiente",
    "AABE": "propiedad",
    "ARCA": "impuestos", "TFN": "impuestos",
    "SENNAF": "familia",
    "CNCPS": "programas_sociales",
    "GNA": "seguridad", "PFA": "seguridad", "ARA": "seguridad",
    "RNR": "justicia", "OA": "justicia",
    "AAIP": "transversal",
    "SIYC": "consumo",
    "RPI": "propiedad", "TTN": "propiedad",
    "BN": "cultura", "BNM": "cultura", "MNBA": "cultura", "FNA": "cultura", "INAMU": "cultura", "CONABIP": "cultura",
    "AGN": "cultura",
    "SPF": "seguridad",
    "DINE": "identidad",
    "ONTI": "gestion_publica", "ONC": "gestion_publica",
    "CNCE": "comercio_exterior",
    "SECLO": "trabajo",
}

# Palabras clave sobre el nombre normalizado (n.clave). Gana la primera que coincide.
PALABRAS_CLAVE = [
    ("discapacidad", r"DISCAPACI"),
    ("armas", r"\bARMAS?\b|EXPLOSIV|MATERIALES CONTROLADOS|LEGITIMO USUARIO"),
    ("migraciones", r"MIGRA|RADICACI|\bVISAS?\b|RESIDENCIA PRECARIA"),
    ("identidad", r"\bDNI\b|DOCUMENTO NACIONAL DE IDENTIDAD|IDENTIDAD DE GENERO|IDENTIDAD BIOLOGICA|"
                  r"PADRON ELECTORAL|CIUDADANIA|NATURALIZ"),
    ("viajes", r"APOSTILL|LEGALIZACI|CONSULA|PASAPORTE|RESIDENCIA EN EL EXTERIOR|FIRMANTES DE DOCUMENTOS PUBLICOS"),
    # Trámites del Estado consigo mismo: Congreso (PLN), AGN, firma digital de autoridades de
    # registro, integración de sistemas, facturas de proveedores de un organismo.
    ("gestion_publica", r"^PLN\b|RESOLUCIONES AGN|AUDITORIA GENERAL DE LA NACION|AUTORIDAD(ES)? (DE )?REGISTRO|"
                        r"\bAC[ -]ONTI\b|AC MODERNIZACION|\bPFDR\b|PLATAFORMA FIRMA DIGITAL REMOTA|AUTENTICAR|"
                        r"APLICACION CLIENTE|\bVPN\b|FACTURAS? (NO )?VINCULADAS|INVENTARIO NACIONAL DE BIENES|\bINBIST\b|"
                        r"PROYECTOS TECNOLOGICOS DEL SECTOR PUBLICO|NUBE HIBRIDA|AUTORIDAD CONTABLE|PAUTA PUBLICITARIA|"
                        r"DECRETOS PRESIDENCIALES|AUTORIDADES ELECTAS|DECLARACION JURADA DE INTERESES|PREVIA CONFORMIDAD|"
                        r"NOMINA DE FIRMANTES|PROYECTOS PNUD|ASOCIACION DE APLICACION|ALTA LOCAL VIRTUAL|"
                        r"RESTITUCION DE FONDOS|COLEGIOS DE ESCRIBANOS|^MUNICIPIOS$"),
    ("propiedad_intelectual", r"PROPIEDAD INTELECTUAL|\bMARCAS?\b|PATENTE|DERECHO DE AUTOR|OBRAS? INEDITA|"
                              r"CULTIVAR|PUBLICACION PERIODICA"),
    ("seguridad_social", r"JUBILACI|PENSION|PREVISIONAL|HABER(ES)? DE (RETIRO|PASIVIDAD)|RETIRO MILITAR"),
    ("programas_sociales", r"ASIGNACION UNIVERSAL|\bAUH\b|AYUDA ESCOLAR|ASIGNACION(ES)? FAMILIAR|ASIGNACION POR|"
                           r"PROGRAMA HOGAR|GARRAFA|AYUDAS? DIRECTAS|ASISTENCIA ECONOMICA|EFECTOR(ES)? SOCIAL|"
                           r"MICROCREDITO|SUBSIDIO DE LA|\bPROGRESAR\b|100% NUESTRO|TARIFA SOCIAL"),
    ("vehiculos", r"VEHICUL|AUTOMOTOR|LICENCIA DE CONDUCIR|MOTOVEHICUL"),
    ("energia", r"ENERG|ELECTRIC|\bGAS\b|GAS NATURAL|\bGNC\b|\bGLP\b|GASODUCTO|HIDROCARBUR|PETROL|COMBUSTIBLE|"
                r"NUCLEAR|RENOVABLE"),
    ("trabajo", r"\bEMPLEO|TRABAJADOR|LABORAL|SINDICA|GREMIAL|CONVENIO COLECTIVO|PASANTIA|\bTRABAJO\b|"
                r"TELETRABAJO|RECIBOS? DE SUELDO|\bSECLO\b|PREVENTIVO DE CRISIS|FORMACION PROFESIONAL|\bREPRO\b|"
                r"CUIDADORES|CHOFERES|GUARDAVIDAS"),
    # "Investigación" sola no: "investigación de origen" (comercio), "comisiones investigadoras" (Congreso).
    ("ciencia_tecnologia", r"CIENTIFIC|CIENCIA|INVESTIGACION CIENTIFICA|PROYECTOS DE INVESTIGACION|"
                           r"\bINVESTIGADOR(ES)?\b|INNOVACION|DESARROLLO TECNOLOGICO|ROECYT|BIOTECNOLOG|NANOTECNOLOG"),
    ("educacion", r"EDUCA|ESCUELA|UNIVERSI|\bTITULOS?\b|CONVALIDACI|\bBECAS?\b|ESTUDIANT|DOCENTE|PLANES DE ESTUDIO|"
                  r"POS(T)?GRADO|CARRERAS? DE GRADO|SECUNDARIO|TERCIARIO|BRAILLE|DIDACTIC|CAPACITACIONES GDE|"
                  r"^INSCRIBIRSE EN (?!EL |LA |LOS |LAS )"),  # cursos: "Inscribirse en Visualización de Datos"
    ("salud", r"SALUD|\bMEDIC(O|A|OS|AS|AMENTOS?|INA)\b|HOSPITAL|SANITARI|FARMAC|DROGUER|ODONTOLOG|ENFERMER|"
              r"VACUN|OBRA SOCIAL"),
    ("cultura", r"CULTUR|ARTIST|MUSEO|INCAA|CREATIVAS|DOMINIO PUBLICO|\bLIBROS?\b|BIBLIO|CONABIP|LECTORES|GUIONISTA|AUDIOVISUAL|\bCINE|TEATRO|MUSICA|"
                r"PATRIMONIO (CULTURAL|HISTORICO)"),
    ("familia", r"NINEZ|\bNIN(A|O)S?\b|ADOLESCEN|FAMILIA|ADOPCI|MATRIMONIO|PRIMERA INFANCIA|\bHIJ(A|O)S\b"),
    ("empresas", r"SIPRO|PROVEEDOR"),  # registro de proveedores del Estado, aunque nombre cooperativas
    ("organizaciones", r"CLUBES DE BARRIO|COOPERATIV|MUTUAL|ASOCIACION(ES)? CIVIL|FUNDACI|BIEN PUBLICO|BOMBEROS|REGISTRO NACIONAL DE CULTOS|RELIGIOS"),
    ("consumo", r"CONSUMIDOR|LEALTAD COMERCIAL|TARJETAS? DE CREDITO|\bNO LLAME\b|\bSIPRE\b|INFORMAR LOS PRECIOS"),
    ("finanzas", r"\bSEGUROS?\b|ASEGURADOR|REASEGUR|FINANCIER|MERCADO DE CAPITALES|FONDOS? COMUN|FIDEICOMISO|"
                 r"CAPITALIZACION Y AHORRO"),
    ("transporte", r"TRANSPORT|FERROVI|FERROCARRIL|AEROPUERT|AERONAV|AEROCLUB|\bPUERTOS?\b|PORTUARI|BUQUE|"
                   r"EMBARCACI|NAVEGACI|NAUTIC|PEAJE"),
    ("ambiente", r"AMBIENT|RESIDUO|FORESTAL|BOSQUE|FAUNA|FLORA|CLIMA|EMISION|EFLUENTE|PARQUES? NACIONAL|"
                 r"BIODIVERSIDAD|\bPCB\b|OZONO|SUSTENTABLE|MEDIDAS EFICACES DE CONSERVACION|CONVENIO DE ESTOCOLMO|"
                 r"ANTARTIDA|SIN VUELCO|MOVIMIENTO TRANSFRONTERIZO|DESTRUCCION DE MERCADERIAS"),
    ("agro", r"AGRO|AGRIC|GANAD|PESCA|PESQUER|SEMILLA|CULTIVO|VITIVIN|\bVINOS?\b|BOVIN|PORCIN|AVICOL|APICOL|"
             r"LECHER|\bGRANOS?\b|FITOSANIT|ZOOSANIT"),
    # Después de transporte y agro: "certificado náutico deportivo", "pesca deportiva".
    ("turismo_deporte", r"TURIS|AGENCIAS? DE VIAJES|\bTERMAS\b|\bUVT\b|\bINTUR\b|DEPORTIV|DEPORTES|"
                        r"SUSTANCIAS PROHIBIDAS"),
    ("telecomunicaciones", r"TELECOMUNIC|INTERNET|RADIODIFUS|TELEVISI|POSTAL|ESPECTRO|SATELIT|\bSMM?S\b|"
                           r"GEOESTACIONARI|ENTE LICENCIANTE|ESTACION(ES)? TERRENA|RADIOASTRONOM|\bM2M\b"),
    ("justicia", r"JUDICIAL|\bOFICIOS?\b|ANTECEDENTES PENALES|MEDIACI|REINCIDENCIA|DELITO|VIOLENCIA INSTITUCIONAL|"
                 r"RECLAMO ADMINISTRATIVO"),
    ("impuestos", r"IMPUEST|TRIBUT|\bFISCAL\b|GANANCIAS|MONOTRIBUT"),
    ("propiedad", r"INMUEBLE|VIVIENDA|CATASTR|TIERRAS? FISCAL|BIENES DEL ESTADO|LOCACION|MENSURA"),
    ("empresas", r"SOCIEDAD|EMPRESA|PYME|INDUSTRI|INVERSION|REGIMEN DE PROMOCION|PROVEEDOR|SIPRO|PRODUCTIV|"
                 r"EMPRENDED|\bRIGI\b|CONCENTRACION(ES)? ECONOMICA|CONCESIONARIOS|PRIVATIZACIONES|FONDO ACELERACION|"
                 r"CASA MATRIZ|CERTIFICACION DE CALIDAD"),
    ("seguridad", r"SEGURIDAD|POLICI|GENDARMER|PREFECTUR|FUERZAS ARMADAS|DEFENSA NACIONAL|MILITAR"),
    ("transversal", r"ACCESO A LA INFORMACION|INFORMACION PUBLICA|TOMA DE VISTA|VISTA DE (LAS )?ACTUACIONES|"
                    r"PRESENTACION (GENERAL|CIUDADANA)|RECURSO|SOLICITUD GENERAL|FIRMA DIGITAL|FIRMA(R|DOS)? DIGITALMENTE|"
                    r"MESA DE ENTRADAS|VISTA DE UN EXPEDIENTE|CERTIFICADO DE CUMPLIMIENTO"),
]
PALABRAS_CLAVE = [(codigo, re.compile(patron)) for codigo, patron in PALABRAS_CLAVE]
PROGRAMAS_SOCIALES = next(patron for codigo, patron in PALABRAS_CLAVE if codigo == "programas_sociales")

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
    "ELECTRICIDAD": "energia",
    "GAS POR REDES": "energia",
    "SUBSIDIO ENERGETICO": "energia",
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
    # ANSES atiende jubilaciones y también asignaciones: las asignaciones ganan sobre el organismo.
    if PROGRAMAS_SOCIALES.search(k):
        return "programas_sociales", "palabra_clave"
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


# Servicios de consulta: ver un dato propio o público sin pedir nada al organismo.
CONSULTA = re.compile(
    r"^(CONSULTAR? (EL|LA|LOS|LAS|TU|SI|CUANDO|ESTADO|MI|CONDUCTORES|CONVENIOS|LICITACIONES|MATERIAL|PUBLICACIONES|"
    r"DECLARACIONES JURADAS DE FUNCIONARIOS)\b|CONSULTA (DE|DEL|MIS|PRESENCIAL|PUBLICA DE)\b|CONOCER\b|VALIDA\b|"
    r"SIMULA\b|CALCULAR\b)"
)
# Consultas formales que el organismo responde con un acto propio: son trámites.
CONSULTA_FORMAL = re.compile(r"^CONSULTA DE CLASIFICACION")


def naturaleza(nombre):
    k = n.clave(nombre or "")
    return "consulta" if CONSULTA.search(k) and not CONSULTA_FORMAL.search(k) else "tramite"


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

            cur.execute("SELECT id, nombre_ciudadano, naturaleza FROM tramite "
                        "WHERE naturaleza_origen IS DISTINCT FROM 'manual'")
            consultas = 0
            for tramite_id, nombre, actual in cur.fetchall():
                deseada = naturaleza(nombre)
                consultas += deseada == "consulta"
                if deseada != actual:
                    cur.execute("UPDATE tramite SET naturaleza = %s, naturaleza_origen = 'auto' WHERE id = %s",
                                (deseada, tramite_id))
                    cambios += 1
            if args.dry_run:
                conn.rollback()
    finally:
        conn.close()

    total = sum(por_regla.values())
    print(f"\n{'Simulación' if args.dry_run else 'Clasificación'}: {total} trámites automáticos "
          f"(+{manuales} con categoría manual) | consultas: {consultas} | cambios: {cambios}")
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
