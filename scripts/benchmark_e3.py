#!/usr/bin/env python3

import csv
import math
import statistics
import time
import uuid
from decimal import Decimal
from pathlib import Path

import psycopg



# Configuracion


LOCAL_REGION = "cr-sj"
REMOTE_REGION = "cr-limon"

RUNS = 50
WARMUP = 5

TRANSFER_AMOUNT = Decimal("0.01")

OUTPUT_FILE = Path("/proyecto/evidencia/e3-mediciones.csv")



# Utilidades

def ms(inicio_ns, fin_ns):
    """Convierte nanosegundos a milisegundos."""
    return (fin_ns - inicio_ns) / 1_000_000


def percentil_nearest_rank(valores, percentil):
    """
    Calcula un percentil usando nearest-rank.
    Para p99 usamos percentil = 0.99.
    """
    ordenados = sorted(valores)

    posicion = math.ceil(percentil * len(ordenados))

    return ordenados[posicion - 1]


def seleccionar_cuentas(conn, region, cantidad):
    """
    Selecciona cuentas de una region.
    Se prefieren las de mayor saldo para evitar problemas
    durante las transferencias del benchmark.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT cuenta_id, saldo, region
            FROM cuenta
            WHERE region = %s
            ORDER BY saldo DESC
            LIMIT %s
            """,
            (region, cantidad),
        )

        return cur.fetchall()



# Lecturas


def medir_lectura(conn, cuenta_id, region):
    """
    Ejecuta una lectura de una cuenta y devuelve
    la latencia en milisegundos.
    """

    inicio = time.perf_counter_ns()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT saldo
            FROM cuenta
            WHERE region = %s
              AND cuenta_id = %s
            """,
            (region, cuenta_id),
        )

        resultado = cur.fetchone()

    fin = time.perf_counter_ns()

    if resultado is None:
        raise RuntimeError(
            f"No se encontró la cuenta {cuenta_id}"
        )

    return ms(inicio, fin)



# Escrituras

def medir_transferencia(
    conn,
    cuenta_origen,
    region_origen,
    cuenta_destino,
    region_destino,
):
    """
    Ejecuta una transferencia bancaria.

    La medicion incluye:
      1. debito de cuenta origen;
      2. credito de cuenta destino;
      3. INSERT en movimiento;
      4. COMMIT.

    Devuelve:
      latencia_ms, mov_id
    """

    mov_id = str(uuid.uuid4())

    inicio = time.perf_counter_ns()

    with conn.transaction():

        with conn.cursor() as cur:

            # Debito
            cur.execute(
                """
                UPDATE cuenta
                SET saldo = saldo - %s
                WHERE region = %s
                  AND cuenta_id = %s
                  AND saldo >= %s
                """,
                (
                    TRANSFER_AMOUNT,
                    region_origen,
                    cuenta_origen,
                    TRANSFER_AMOUNT,
                ),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "No se pudo debitar la cuenta origen."
                )

            # Crédito
            cur.execute(
                """
                UPDATE cuenta
                SET saldo = saldo + %s
                WHERE region = %s
                  AND cuenta_id = %s
                """,
                (
                    TRANSFER_AMOUNT,
                    region_destino,
                    cuenta_destino,
                ),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "No se pudo acreditar la cuenta destino."
                )

            # Movimiento
            cur.execute(
                """
                INSERT INTO movimiento (
                    mov_id,
                    cuenta_ori_id,
                    cuenta_dest_id,
                    monto,
                    tipo,
                    region
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    'TRANSFERENCIA',
                    %s
                )
                """,
                (
                    mov_id,
                    cuenta_origen,
                    cuenta_destino,
                    TRANSFER_AMOUNT,
                    region_origen,
                ),
            )

    # Al salir de conn.transaction() ya ocurrió el COMMIT.
    fin = time.perf_counter_ns()

    return ms(inicio, fin), mov_id



# Limpieza

def limpiar_transferencias(
    conn,
    movimientos,
    cuentas_originales,
):
    """
    Elimina los movimientos creados por el benchmark
    y restaura los saldos originales.
    """

    print("\nRestaurando base de datos...")

    with conn.transaction():

        with conn.cursor() as cur:

            for mov_id in movimientos:
                cur.execute(
                    """
                    DELETE FROM movimiento
                    WHERE mov_id = %s
                    """,
                    (mov_id,),
                )

            for cuenta_id, region, saldo_original in cuentas_originales:

                cur.execute(
                    """
                    UPDATE cuenta
                    SET saldo = %s
                    WHERE cuenta_id = %s
                      AND region = %s
                    """,
                    (
                        saldo_original,
                        cuenta_id,
                        region,
                    ),
                )

    print("Base de datos restaurada.")



# Estadisticas


def mostrar_resultado(nombre, valores):
    p50 = statistics.median(valores)
    p99 = percentil_nearest_rank(valores, 0.99)

    print(
        f"{nombre:<32}"
        f"{len(valores):>5}"
        f"{p50:>15.3f}"
        f"{p99:>15.3f}"
    )



# Programa principal


def main():

    print("==========================================")
    print(" Benchmark E3 - Base de Datos Distribuida")
    print("==========================================")

    print(f"Región local:          {LOCAL_REGION}")
    print(f"Región remota:         {REMOTE_REGION}")
    print(f"Warm-up:               {WARMUP}")
    print(f"Corridas por caso:     {RUNS}")

    # La conexión toma PGHOST, PGPORT, PGUSER, PGDATABASE, etc.
    # del contenedor app-crdb.
    conn = psycopg.connect(autocommit=True)

    movimientos_creados = []

    try:

        
        # Verificar desde que region estamos ejecutando
        

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT gateway_region()
                """
            )

            gateway = cur.fetchone()[0]

        print(f"Gateway utilizado:     {gateway}")

        if str(gateway) != LOCAL_REGION:
            raise RuntimeError(
                f"El benchmark debe ejecutarse desde "
                f"{LOCAL_REGION}, pero el gateway actual es "
                f"{gateway}."
            )

        
        # Seleccionar cuentas
        

        cuentas_locales = seleccionar_cuentas(
            conn,
            LOCAL_REGION,
            5,
        )

        cuentas_remotas = seleccionar_cuentas(
            conn,
            REMOTE_REGION,
            3,
        )

        if len(cuentas_locales) < 5:
            raise RuntimeError(
                f"No hay suficientes cuentas en {LOCAL_REGION}"
            )

        if len(cuentas_remotas) < 3:
            raise RuntimeError(
                f"No hay suficientes cuentas en {REMOTE_REGION}"
            )

        
        # Cuentas utilizadas
        
        lectura_local = cuentas_locales[0]
        lectura_remota = cuentas_remotas[0]

        origen_local = cuentas_locales[1]
        destino_local = cuentas_locales[2]

        origen_interregional = cuentas_locales[3]
        destino_interregional = cuentas_remotas[1]

        print("\nCuentas seleccionadas:")
        print(
            f"Lectura local:          {lectura_local[0]}"
        )
        print(
            f"Lectura remota:         {lectura_remota[0]}"
        )
        print(
            f"Transferencia local:    "
            f"{origen_local[0]} -> {destino_local[0]}"
        )
        print(
            f"Transferencia remota:   "
            f"{origen_interregional[0]} -> "
            f"{destino_interregional[0]}"
        )

        
        # Guardar saldos iniciales
       

        cuentas_originales = [
            (
                origen_local[0],
                LOCAL_REGION,
                origen_local[1],
            ),
            (
                destino_local[0],
                LOCAL_REGION,
                destino_local[1],
            ),
            (
                origen_interregional[0],
                LOCAL_REGION,
                origen_interregional[1],
            ),
            (
                destino_interregional[0],
                REMOTE_REGION,
                destino_interregional[1],
            ),
        ]

       
        # Resultados
        

        resultados = {
            "lectura_local": [],
            "lectura_remota": [],
            "escritura_local": [],
            "escritura_interregional": [],
        }

        #
        # 1. LECTURA LOCAL
        

        print("\n[1/4] Lectura local")

        for _ in range(WARMUP):
            medir_lectura(
                conn,
                lectura_local[0],
                LOCAL_REGION,
            )

        for corrida in range(1, RUNS + 1):

            latencia = medir_lectura(
                conn,
                lectura_local[0],
                LOCAL_REGION,
            )

            resultados["lectura_local"].append(
                latencia
            )

            print(
                f"\rCorrida {corrida}/{RUNS}",
                end="",
                flush=True,
            )

        print()

        
        # 2. LECTURA REMOTA
        

        print("\n[2/4] Lectura remota")

        for _ in range(WARMUP):
            medir_lectura(
                conn,
                lectura_remota[0],
                REMOTE_REGION,
            )

        for corrida in range(1, RUNS + 1):

            latencia = medir_lectura(
                conn,
                lectura_remota[0],
                REMOTE_REGION,
            )

            resultados["lectura_remota"].append(
                latencia
            )

            print(
                f"\rCorrida {corrida}/{RUNS}",
                end="",
                flush=True,
            )

        print()

       
        # 3. ESCRITURA LOCAL
        

        print("\n[3/4] Escritura local")

        for _ in range(WARMUP):

            _, mov_id = medir_transferencia(
                conn,
                origen_local[0],
                LOCAL_REGION,
                destino_local[0],
                LOCAL_REGION,
            )

            movimientos_creados.append(mov_id)

        for corrida in range(1, RUNS + 1):

            latencia, mov_id = medir_transferencia(
                conn,
                origen_local[0],
                LOCAL_REGION,
                destino_local[0],
                LOCAL_REGION,
            )

            movimientos_creados.append(mov_id)

            resultados["escritura_local"].append(
                latencia
            )

            print(
                f"\rCorrida {corrida}/{RUNS}",
                end="",
                flush=True,
            )

        print()

        
        # 4. ESCRITURA INTERREGIONAL
        

        print("\n[4/4] Escritura interregional")

        for _ in range(WARMUP):

            _, mov_id = medir_transferencia(
                conn,
                origen_interregional[0],
                LOCAL_REGION,
                destino_interregional[0],
                REMOTE_REGION,
            )

            movimientos_creados.append(mov_id)

        for corrida in range(1, RUNS + 1):

            latencia, mov_id = medir_transferencia(
                conn,
                origen_interregional[0],
                LOCAL_REGION,
                destino_interregional[0],
                REMOTE_REGION,
            )

            movimientos_creados.append(mov_id)

            resultados[
                "escritura_interregional"
            ].append(latencia)

            print(
                f"\rCorrida {corrida}/{RUNS}",
                end="",
                flush=True,
            )

        print()

        
        # Guardar CSV
        

        OUTPUT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with OUTPUT_FILE.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as archivo:

            writer = csv.writer(archivo)

            writer.writerow(
                [
                    "tipo",
                    "corrida",
                    "latencia_ms",
                ]
            )

            for tipo, valores in resultados.items():

                for corrida, valor in enumerate(
                    valores,
                    start=1,
                ):

                    writer.writerow(
                        [
                            tipo,
                            corrida,
                            f"{valor:.6f}",
                        ]
                    )

        
        # Resumen
        

        print("\n")
        print(
            f"{'Operación':<32}"
            f"{'n':>5}"
            f"{'p50 (ms)':>15}"
            f"{'p99 (ms)':>15}"
        )

        print("-" * 67)

        mostrar_resultado(
            "Lectura local",
            resultados["lectura_local"],
        )

        mostrar_resultado(
            "Lectura remota",
            resultados["lectura_remota"],
        )

        mostrar_resultado(
            "Escritura local",
            resultados["escritura_local"],
        )

        mostrar_resultado(
            "Escritura interregional",
            resultados["escritura_interregional"],
        )

        print(
            f"\nCSV generado en: {OUTPUT_FILE}"
        )

    finally:

       
        # Restaurar BD incluso si ocurre un error
        

        if movimientos_creados:

            try:
                limpiar_transferencias(
                    conn,
                    movimientos_creados,
                    cuentas_originales,
                )

            except Exception as error:
                print(
                    "\nADVERTENCIA: hubo un error "
                    "durante la restauración:"
                )
                print(error)

        conn.close()


if __name__ == "__main__":
    main()
