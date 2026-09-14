#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import random
import uuid


# ============================================================
# Configuración reproducible
# ============================================================

SEED = 4601
rng = random.Random(SEED)

REGIONES = ("cr-sj", "cr-limon", "us-east")

CLIENTES_POR_REGION = {
    "cr-sj": 50,
    "cr-limon": 27,
    "us-east": 100,
}

CUENTAS_POR_REGION = {
    "cr-sj": 60,
    "cr-limon": 30,
    "us-east": 330,
}

# Distribución aproximada:
# 50 % TRANSFERENCIA
# 15 % DEPOSITO
# 35 % RETIRO
MOVIMIENTOS_POR_REGION = {
    "cr-sj": {
        "TRANSFERENCIA": 50,
        "DEPOSITO": 15,
        "RETIRO": 35,
    },
    "cr-limon": {
        "TRANSFERENCIA": 25,
        "DEPOSITO": 8,
        "RETIRO": 17,
    },
    "us-east": {
        "TRANSFERENCIA": 250,
        "DEPOSITO": 75,
        "RETIRO": 175,
    },
}

# Aproximadamente 30 % de las cuentas adicionales pertenecerán
# a clientes cuya región de apertura es distinta.
PROB_CUENTA_INTERREGIONAL = 0.30


# ============================================================
# Utilidades
# ============================================================

def deterministic_uuid(tipo: str, numero: int) -> str:
    """
    Genera UUID determinísticos.
    Al volver a ejecutar el script se obtienen exactamente
    los mismos identificadores.
    """
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"ti4601-proyecto1/{tipo}/{numero}"
        )
    )


def sql_string(valor: str) -> str:
    """Escapa un string para colocarlo entre comillas SQL."""
    return "'" + valor.replace("'", "''") + "'"


def dinero(minimo: int, maximo: int) -> str:
    """Genera un monto reproducible con dos decimales."""
    centavos = rng.randint(minimo * 100, maximo * 100)
    valor = Decimal(centavos) / Decimal(100)
    return f"{valor:.2f}"


# ============================================================
# 1. Clientes
# ============================================================

clientes = []
clientes_por_region = {region: [] for region in REGIONES}

cliente_num = 1

for region in REGIONES:
    cantidad = CLIENTES_POR_REGION[region]

    for indice in range(1, cantidad + 1):
        cliente = {
            "cliente_id": deterministic_uuid("cliente", cliente_num),
            "nombre": f"Cliente {region} {indice:03d}",
            "documento": f"DOC-{region.upper()}-{indice:04d}",
            "region": region,
        }

        clientes.append(cliente)
        clientes_por_region[region].append(cliente)

        cliente_num += 1


# ============================================================
# 2. Cuentas
# ============================================================

cuentas = []
cuentas_por_region = {region: [] for region in REGIONES}

cuenta_num = 1


def crear_cuenta(cliente, region):
    global cuenta_num

    cuenta = {
        "cuenta_id": deterministic_uuid("cuenta", cuenta_num),
        "cliente_id": cliente["cliente_id"],
        "saldo": dinero(100, 10000),
        "region": region,
    }

    cuentas.append(cuenta)
    cuentas_por_region[region].append(cuenta)

    cuenta_num += 1


# ------------------------------------------------------------
# Primera cuenta obligatoria:
# misma región que el cliente.
# ------------------------------------------------------------

for cliente in clientes:
    crear_cuenta(cliente, cliente["region"])


# ------------------------------------------------------------
# Cuentas adicionales hasta alcanzar los totales regionales.
#
# Algunas pertenecen intencionalmente a clientes de otra región.
# Esto permite representar clientes con cuentas regionalmente
# distribuidas.
# ------------------------------------------------------------

for region in REGIONES:

    faltantes = (
        CUENTAS_POR_REGION[region]
        - len(cuentas_por_region[region])
    )

    clientes_locales = clientes_por_region[region]

    clientes_otras_regiones = [
        cliente
        for cliente in clientes
        if cliente["region"] != region
    ]

    for _ in range(faltantes):

        if rng.random() < PROB_CUENTA_INTERREGIONAL:
            propietario = rng.choice(clientes_otras_regiones)
        else:
            propietario = rng.choice(clientes_locales)

        crear_cuenta(propietario, region)


# ============================================================
# 3. ReferenciaCuenta
# ============================================================

referencias = [
    {
        "cuenta_id": cuenta["cuenta_id"],
        "region": cuenta["region"],
    }
    for cuenta in cuentas
]


# ============================================================
# 4. Movimientos
# ============================================================

movimientos = []
movimiento_num = 1

fecha_base = datetime(
    2026, 1, 1, 8, 0, 0,
    tzinfo=timezone.utc
)


def nueva_fecha():
    """
    Produce timestamps determinísticos separados por minutos.
    """
    return fecha_base + timedelta(minutes=len(movimientos))


def crear_movimiento(
    region,
    tipo,
    origen=None,
    destino=None,
):
    global movimiento_num

    movimiento = {
        "mov_id": deterministic_uuid(
            "movimiento",
            movimiento_num
        ),
        "cuenta_ori_id": (
            origen["cuenta_id"]
            if origen is not None
            else None
        ),
        "cuenta_dest_id": (
            destino["cuenta_id"]
            if destino is not None
            else None
        ),
        "monto": dinero(1, 500),
        "tipo": tipo,
        "fecha": nueva_fecha(),
        "region": region,
    }

    movimientos.append(movimiento)
    movimiento_num += 1


for region in REGIONES:

    config = MOVIMIENTOS_POR_REGION[region]

    cuentas_locales = cuentas_por_region[region]

    cuentas_remotas = [
        cuenta
        for cuenta in cuentas
        if cuenta["region"] != region
    ]

    # --------------------------------------------------------
    # TRANSFERENCIAS
    #
    # Alternamos:
    # - transferencia local
    # - transferencia entre regiones
    #
    # En ambas, la cuenta origen pertenece a la región donde
    # se genera el movimiento.
    # --------------------------------------------------------

    for i in range(config["TRANSFERENCIA"]):

        origen = rng.choice(cuentas_locales)

        if i % 2 == 0:
            # Transferencia local
            posibles_destinos = [
                cuenta
                for cuenta in cuentas_locales
                if cuenta["cuenta_id"] != origen["cuenta_id"]
            ]
        else:
            # Transferencia entre regiones
            posibles_destinos = cuentas_remotas

        destino = rng.choice(posibles_destinos)

        crear_movimiento(
            region=region,
            tipo="TRANSFERENCIA",
            origen=origen,
            destino=destino,
        )

    # --------------------------------------------------------
    # DEPÓSITOS
    #
    # origen = NULL
    # destino = cuenta
    # --------------------------------------------------------

    for _ in range(config["DEPOSITO"]):

        destino = rng.choice(cuentas_locales)

        crear_movimiento(
            region=region,
            tipo="DEPOSITO",
            origen=None,
            destino=destino,
        )

    # --------------------------------------------------------
    # RETIROS
    #
    # origen = cuenta
    # destino = NULL
    # --------------------------------------------------------

    for _ in range(config["RETIRO"]):

        origen = rng.choice(cuentas_locales)

        crear_movimiento(
            region=region,
            tipo="RETIRO",
            origen=origen,
            destino=None,
        )


# ============================================================
# 5. Validaciones antes de generar SQL
# ============================================================

assert len(clientes) == 177
assert len(cuentas) == 420
assert len(referencias) == 420
assert len(movimientos) == 650

for region in REGIONES:

    assert (
        len(clientes_por_region[region])
        == CLIENTES_POR_REGION[region]
    )

    assert (
        len(cuentas_por_region[region])
        == CUENTAS_POR_REGION[region]
    )

for cuenta in cuentas:
    assert Decimal(cuenta["saldo"]) >= 0

for mov in movimientos:
    assert Decimal(mov["monto"]) > 0

    if mov["tipo"] == "TRANSFERENCIA":
        assert mov["cuenta_ori_id"] is not None
        assert mov["cuenta_dest_id"] is not None
        assert mov["cuenta_ori_id"] != mov["cuenta_dest_id"]

    elif mov["tipo"] == "DEPOSITO":
        assert mov["cuenta_ori_id"] is None
        assert mov["cuenta_dest_id"] is not None

    elif mov["tipo"] == "RETIRO":
        assert mov["cuenta_ori_id"] is not None
        assert mov["cuenta_dest_id"] is None


# ============================================================
# 6. Generación de seed.sql
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT = PROJECT_DIR / "seed.sql"

sql = []

sql.append("""\
-- ============================================================
-- Proyecto 1 - Base de datos distribuida
-- Seed reproducible
--
-- Generado automáticamente por scripts/generate_seed.py
-- SEED = 4601
--
-- Totales:
--   Cliente:          177
--   Cuenta:           420
--   ReferenciaCuenta: 420
--   Movimiento:       650
-- ============================================================

BEGIN;

-- Limpiar únicamente las tablas propias del Proyecto 1.
-- Se respeta el orden de dependencias de las FK.
DELETE FROM movimiento;
DELETE FROM referencia_cuenta;
DELETE FROM cuenta;
DELETE FROM cliente;

""")


# ------------------------------------------------------------
# Clientes
# ------------------------------------------------------------

sql.append(
    "-- ========================================================\n"
    "-- CLIENTES\n"
    "-- ========================================================\n\n"
)

sql.append(
    "INSERT INTO cliente "
    "(cliente_id, nombre, documento, region)\nVALUES\n"
)

filas = []

for cliente in clientes:
    filas.append(
        "    ("
        f"{sql_string(cliente['cliente_id'])}, "
        f"{sql_string(cliente['nombre'])}, "
        f"{sql_string(cliente['documento'])}, "
        f"{sql_string(cliente['region'])}"
        ")"
    )

sql.append(",\n".join(filas))
sql.append(";\n\n")


# ------------------------------------------------------------
# Cuentas
# ------------------------------------------------------------

sql.append(
    "-- ========================================================\n"
    "-- CUENTAS\n"
    "-- ========================================================\n\n"
)

sql.append(
    "INSERT INTO cuenta "
    "(cuenta_id, cliente_id, saldo, region)\nVALUES\n"
)

filas = []

for cuenta in cuentas:
    filas.append(
        "    ("
        f"{sql_string(cuenta['cuenta_id'])}, "
        f"{sql_string(cuenta['cliente_id'])}, "
        f"{cuenta['saldo']}, "
        f"{sql_string(cuenta['region'])}"
        ")"
    )

sql.append(",\n".join(filas))
sql.append(";\n\n")


# ------------------------------------------------------------
# ReferenciaCuenta
# ------------------------------------------------------------

sql.append(
    "-- ========================================================\n"
    "-- REFERENCIA_CUENTA\n"
    "-- ========================================================\n\n"
)

sql.append(
    "INSERT INTO referencia_cuenta "
    "(cuenta_id, region)\nVALUES\n"
)

filas = []

for referencia in referencias:
    filas.append(
        "    ("
        f"{sql_string(referencia['cuenta_id'])}, "
        f"{sql_string(referencia['region'])}"
        ")"
    )

sql.append(",\n".join(filas))
sql.append(";\n\n")


# ------------------------------------------------------------
# Movimientos
# ------------------------------------------------------------

sql.append(
    "-- ========================================================\n"
    "-- MOVIMIENTOS\n"
    "-- ========================================================\n\n"
)

sql.append(
    "INSERT INTO movimiento "
    "("
    "mov_id, "
    "cuenta_ori_id, "
    "cuenta_dest_id, "
    "monto, "
    "tipo, "
    "fecha, "
    "region"
    ")\nVALUES\n"
)

filas = []

for movimiento in movimientos:

    origen = (
        "NULL"
        if movimiento["cuenta_ori_id"] is None
        else sql_string(movimiento["cuenta_ori_id"])
    )

    destino = (
        "NULL"
        if movimiento["cuenta_dest_id"] is None
        else sql_string(movimiento["cuenta_dest_id"])
    )

    fecha = movimiento["fecha"].isoformat()

    filas.append(
        "    ("
        f"{sql_string(movimiento['mov_id'])}, "
        f"{origen}, "
        f"{destino}, "
        f"{movimiento['monto']}, "
        f"{sql_string(movimiento['tipo'])}, "
        f"{sql_string(fecha)}, "
        f"{sql_string(movimiento['region'])}"
        ")"
    )

sql.append(",\n".join(filas))
sql.append(";\n\n")

sql.append("COMMIT;\n")

OUTPUT.write_text(
    "".join(sql),
    encoding="utf-8"
)


# ============================================================
# 7. Resumen
# ============================================================

print(f"Seed generado correctamente: {OUTPUT}")
print()
print("Resumen:")
print(f"  Clientes:          {len(clientes)}")
print(f"  Cuentas:           {len(cuentas)}")
print(f"  ReferenciasCuenta: {len(referencias)}")
print(f"  Movimientos:       {len(movimientos)}")
print()

for region in REGIONES:

    movimientos_region = [
        m for m in movimientos
        if m["region"] == region
    ]

    transferencias = sum(
        1 for m in movimientos_region
        if m["tipo"] == "TRANSFERENCIA"
    )

    depositos = sum(
        1 for m in movimientos_region
        if m["tipo"] == "DEPOSITO"
    )

    retiros = sum(
        1 for m in movimientos_region
        if m["tipo"] == "RETIRO"
    )

    print(region)
    print(
        f"  Clientes:     "
        f"{len(clientes_por_region[region])}"
    )
    print(
        f"  Cuentas:      "
        f"{len(cuentas_por_region[region])}"
    )
    print(
        f"  Movimientos:  "
        f"{len(movimientos_region)}"
    )
    print(
        f"    Transferencias: {transferencias}"
    )
    print(
        f"    Depositos:      {depositos}"
    )
    print(
        f"    Retiros:        {retiros}"
    )
    print()


# Mostrar cuántas cuentas pertenecen a clientes
# cuya región es distinta.
cliente_region = {
    cliente["cliente_id"]: cliente["region"]
    for cliente in clientes
}

cuentas_interregionales = sum(
    1
    for cuenta in cuentas
    if cliente_region[cuenta["cliente_id"]]
    != cuenta["region"]
)

print(
    "Cuentas cuya región difiere "
    f"de la región del cliente: {cuentas_interregionales}"
)