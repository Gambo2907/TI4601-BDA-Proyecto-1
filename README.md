# Proyecto 1: Base de datos distribuida para banca regional

## 1. Descripción

Este proyecto implementa una base de datos distribuida a pequeña escala para un escenario de banca / billetera regional utilizando CockroachDB.

El sistema utiliza tres regiones simuladas:

- `cr-sj`
- `cr-limon`
- `us-east`

La implementación reutiliza la infraestructura de tres nodos de CockroachDB proporcionada por el Lab 1 del curso. Sobre dicha infraestructura se implementa un esquema propio compuesto por las siguientes relaciones:

- `cliente`
- `cuenta`
- `movimiento`
- `referencia_cuenta`

Las tablas `cliente`, `cuenta` y `movimiento` utilizan localidad `REGIONAL BY ROW`, mientras que `referencia_cuenta` utiliza localidad `GLOBAL`.

El atributo `region` tiene una semántica diferente según la relación:

- `cliente.region`: región de apertura del cliente.
- `cuenta.region`: región a la que pertenece la cuenta.
- `movimiento.region`: región donde se genera el movimiento.
- `referencia_cuenta.region`: región de la cuenta referenciada.

Un cliente posee como mínimo una cuenta en su región de apertura, aunque puede tener cuentas adicionales en otras regiones.

---

## 2. Requisitos

Para reproducir el proyecto se requiere:

- Linux
- Git
- Docker
- Docker Compose
- Python 3
- `make`

Docker debe encontrarse iniciado y funcionando.


## 3. Repositorios utilizados

La implementación utiliza dos repositorios:

1. **Repositorio del Lab 1**, que contiene la infraestructura de CockroachDB, Docker Compose y los comandos `make`.
2. **Repositorio del Proyecto 1**, que contiene el esquema, generador de datos, seed y evidencias propias del equipo.

Una posible organización local es:

```text
trabajo/
├── BDA-TI4601/
│   ├── docker-compose.yml
│   ├── Makefile
│   └── ...
│
└── TI4601-BDA-Proyecto-1/
    ├── schema.sql
    ├── seed.sql
    ├── scripts/
    │   └── generate_seed.py
    ├── evidencia/
    └── README.md
```

No es obligatorio utilizar esta estructura. Los repositorios pueden estar en cualquier ubicación mientras se configuren correctamente las rutas indicadas en la siguiente sección.

---

## 4. Configuración de rutas

Primero se debe abrir una terminal en el repositorio de este proyecto:

```bash
cd /ruta/al/TI4601-BDA-Proyecto-1
```

Guardar su ruta absoluta:

```bash
export PROYECTO="$(pwd)"
```

Luego definir la ubicación del repositorio del Lab 1:

```bash
export LAB1_REPO="/ruta/al/BDA-TI4601"
```

Verificar ambas rutas:

```bash
echo "$PROYECTO"
echo "$LAB1_REPO"
```

---

## 5. Levantar el clúster de CockroachDB

Entrar al repositorio del Lab 1:

```bash
cd "$LAB1_REPO"
```

Levantar el clúster:

```bash
make lab1-up
```

Verificar el estado:

```bash
make lab1-status
```

El entorno debe contener tres nodos CockroachDB asociados con las regiones simuladas:

| Nodo | Región |
|---|---|
| `crdb-1` | `cr-sj` |
| `crdb-2` | `cr-limon` |
| `crdb-3` | `us-east` |

---

## 6. Configurar las regiones

Entrar al contenedor cliente:

```bash
make lab1-shell
```

Dentro del contenedor iniciar `psql`:

```bash
psql -X -v ON_ERROR_STOP=1
```

Verificar primero las regiones actualmente configuradas:

```sql
SHOW REGIONS FROM DATABASE ti4601;
```

En una base recién creada, configurar:

```sql
ALTER DATABASE ti4601 PRIMARY REGION "cr-sj";
ALTER DATABASE ti4601 ADD REGION "cr-limon";
ALTER DATABASE ti4601 ADD REGION "us-east";
```

Comprobar nuevamente:

```sql
SHOW REGIONS FROM DATABASE ti4601;
```

El resultado debe contener:

```text
cr-sj
cr-limon
us-east
```

> Si las regiones ya están configuradas, no es necesario ejecutar nuevamente los comandos `ALTER DATABASE`.

Salir de `psql`:

```text
\q
```

Salir del contenedor:

```bash
exit
```

---

## 7. Crear el esquema del proyecto

Desde el repositorio del Lab 1:

```bash
cd "$LAB1_REPO"
```

Ejecutar el esquema almacenado en el repositorio del proyecto:

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb \
  psql -X -v ON_ERROR_STOP=1 \
  < "$PROYECTO/schema.sql"
```

El esquema crea las siguientes tablas:

```text
cliente
cuenta
movimiento
referencia_cuenta
```

Las primeras tres utilizan:

```sql
LOCALITY REGIONAL BY ROW AS region
```

mientras que `referencia_cuenta` utiliza:

```sql
LOCALITY GLOBAL
```

---

## 8. Verificar las tablas creadas

Se puede comprobar el esquema mediante:

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb \
  psql -X -v ON_ERROR_STOP=1 \
  -c "SHOW TABLES;"
```

También se recomienda inspeccionar la definición generada por CockroachDB:

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb \
  psql -X -v ON_ERROR_STOP=1 \
  -c "SHOW CREATE TABLE cliente;" \
  -c "SHOW CREATE TABLE cuenta;" \
  -c "SHOW CREATE TABLE movimiento;" \
  -c "SHOW CREATE TABLE referencia_cuenta;"
```

Esto permite verificar:

- claves primarias;
- claves foráneas;
- restricciones `CHECK`;
- tipos de datos;
- localidad de cada tabla.


---

## 9. Generar el conjunto de datos

El proyecto incluye un generador reproducible:

```text
scripts/generate_seed.py
```

Ejecutarlo mediante:

```bash
python3 "$PROYECTO/scripts/generate_seed.py"
```

El programa utiliza una semilla fija:

```text
SEED = 4601
```

por lo que ejecuciones sucesivas producen el mismo conjunto de datos.

El generador crea:

```text
seed.sql
```

en la raíz del repositorio.

### Volumen generado

| Región | Clientes | Cuentas | Movimientos |
|---|---:|---:|---:|
| `cr-sj` | 50 | 60 | 100 |
| `cr-limon` | 27 | 30 | 50 |
| `us-east` | 100 | 330 | 500 |
| **Total** | **177** | **420** | **650** |

También se generan `420` filas en `referencia_cuenta`, una por cada cuenta existente.

### Distribución de movimientos

| Tipo | Cantidad | Porcentaje aproximado |
|---|---:|---:|
| `TRANSFERENCIA` | 325 | 50 % |
| `DEPOSITO` | 98 | 15 % |
| `RETIRO` | 227 | 35 % |


El generador incluye tanto transferencias locales como transferencias entre regiones.

---

## 10. Cargar los datos

Desde el repositorio del Lab 1:

```bash
cd "$LAB1_REPO"
```

Cargar el seed:

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb \
  psql -X -v ON_ERROR_STOP=1 \
  < "$PROYECTO/seed.sql"
```

Una carga correcta debe finalizar con `COMMIT`.

Los valores esperados son:

```text
INSERT 0 177
INSERT 0 420
INSERT 0 420
INSERT 0 650
COMMIT
```

El `seed.sql` elimina previamente únicamente los datos correspondientes a las tablas propias del proyecto y los vuelve a insertar, respetando el orden de dependencias entre claves foráneas.

---

## 11. Validar los datos cargados

### Clientes por región

```sql
SELECT region, COUNT(*) AS clientes
FROM cliente
GROUP BY region
ORDER BY region;
```

Resultado esperado:

```text
cr-limon     27
cr-sj        50
us-east     100
```

### Cuentas por región

```sql
SELECT region, COUNT(*) AS cuentas
FROM cuenta
GROUP BY region
ORDER BY region;
```

Resultado esperado:

```text
cr-limon     30
cr-sj        60
us-east     330
```

### Movimientos por región

```sql
SELECT region, COUNT(*) AS movimientos
FROM movimiento
GROUP BY region
ORDER BY region;
```

Resultado esperado:

```text
cr-limon      50
cr-sj        100
us-east      500
```

### Movimientos por tipo

```sql
SELECT tipo, COUNT(*) AS cantidad
FROM movimiento
GROUP BY tipo
ORDER BY tipo;
```

Resultado esperado:

```text
DEPOSITO           98
RETIRO            227
TRANSFERENCIA     325
```

### Verificar referencias de cuenta

```sql
SELECT
    (SELECT COUNT(*) FROM cuenta) AS cuentas,
    (SELECT COUNT(*) FROM referencia_cuenta) AS referencias;
```

Resultado esperado:

```text
cuentas | referencias
--------+------------
420     | 420
```

---

## 12. Validaciones del modelo

### Clientes con cuentas en otras regiones

El diseño permite que un cliente posea cuentas adicionales en regiones diferentes a su región de apertura.

```sql
SELECT
    c.cliente_id,
    c.region AS region_cliente,
    q.cuenta_id,
    q.region AS region_cuenta
FROM cliente c
JOIN cuenta q
    ON q.cliente_id = c.cliente_id
WHERE c.region <> q.region
LIMIT 10;
```

### Verificar que todo cliente tenga una cuenta en su región

```sql
SELECT COUNT(*) AS clientes_sin_cuenta_inicial_regional
FROM cliente c
WHERE NOT EXISTS (
    SELECT 1
    FROM cuenta q
    WHERE q.cliente_id = c.cliente_id
      AND q.region = c.region
);
```

Resultado esperado:

```text
0
```

### Verificar consistencia de `referencia_cuenta`

```sql
SELECT COUNT(*) AS referencias_region_incorrecta
FROM referencia_cuenta r
JOIN cuenta q
    ON q.cuenta_id = r.cuenta_id
WHERE r.region <> q.region;
```

Resultado esperado:

```text
0
```

### Transferencias entre regiones

```sql
SELECT COUNT(*) AS transferencias_interregionales
FROM movimiento m
JOIN cuenta origen
    ON origen.cuenta_id = m.cuenta_ori_id
JOIN cuenta destino
    ON destino.cuenta_id = m.cuenta_dest_id
WHERE m.tipo = 'TRANSFERENCIA'
  AND origen.region <> destino.region;
```

Con el seed actual se esperan:

```text
162
```

transferencias entre cuentas ubicadas en regiones diferentes.

---

## 13. Inspeccionar la distribución mediante `SHOW RANGES`

CockroachDB permite observar la distribución de rangos y sus réplicas mediante `SHOW RANGES`.

Ejecutar:

```sql
SHOW RANGES FROM TABLE cliente WITH DETAILS;
SHOW RANGES FROM TABLE cuenta WITH DETAILS;
SHOW RANGES FROM TABLE movimiento WITH DETAILS;
SHOW RANGES FROM TABLE referencia_cuenta WITH DETAILS;
```

En las tablas `cliente`, `cuenta` y `movimiento`, los rangos regionales deben mostrar afinidad del lease con las localidades:

```text
region=cr-sj
region=cr-limon
region=us-east
```

de acuerdo con el valor de `region`.

`referencia_cuenta`, al utilizar `LOCALITY GLOBAL`, presenta un comportamiento distinto y se encuentra disponible globalmente.

### Réplicas Raft

Es importante distinguir entre la localidad lógica del dato y las réplicas internas mantenidas por CockroachDB.

En `SHOW RANGES` pueden observarse réplicas votantes en los tres nodos, por ejemplo:

```text
voting_replicas = {1,2,3}
```

Esto no implica que `REGIONAL BY ROW` haya dejado de funcionar.

CockroachDB mantiene réplicas Raft para tolerancia a fallos, mientras que la localidad regional determina principalmente la región hogar y la ubicación preferida del lease.

Por tanto, esta implementación representa fragmentación primaria y afinidad regional, pero no demuestra residencia física estricta de todas las copias de los datos en una única región.

---

## 14. Evidencia

Las salidas utilizadas para verificar la implementación se almacenan en:

```text
evidencia/
```

Entre los archivos generados se encuentran:

```text
evidencia/
├── e2-regiones.txt
├── e2-show-tables.txt
├── e2-show-create.txt
├── e2-show-columns.txt
├── e2-show-constraints.txt
├── e2-seed-load.txt
├── e2-seed-validation.txt
├── e2-pruebas-restricciones.txt
├── e2-show-ranges.txt
└── e2-show-ranges-resumen.txt
```

Estas evidencias permiten comprobar:

- configuración de regiones;
- creación de las tablas;
- restricciones del esquema;
- carga reproducible del dataset;
- distribución de los datos;
- `REGIONAL BY ROW`;
- `GLOBAL`;
- comportamiento de las claves foráneas y restricciones `CHECK`.

---

## 15. Detener el entorno

Para detener el clúster:

```bash
cd "$LAB1_REPO"
make lab1-down
```

---

## 16. Mediciones de rendimiento


Las mediciones del Entregable 3 se ejecutan desde el gateway ubicado en
`cr-sj`, manteniendo el mismo clúster y las mismas condiciones de recursos para todos los casos.

Se consideran cuatro operaciones:

- **Lectura local:** consulta realizada desde `cr-sj` sobre una cuenta cuya
  región hogar es `cr-sj`.
- **Lectura remota:** consulta realizada desde `cr-sj` sobre una cuenta cuya
  región hogar es `cr-limon`.
- **Escritura local:** transferencia entre dos cuentas ubicadas en `cr-sj`.
- **Escritura interregional:** transferencia cuya cuenta origen pertenece a
  `cr-sj` y cuya cuenta destino pertenece a `cr-limon`.

Para evitar que el arranque inicial afecte los resultados, se ejecutan 5 operaciones de calentamiento por caso que no se incluyen en las estadísticas. Posteriormente se realizan 50 mediciones por operación.

La latencia se mide con `time.perf_counter_ns()` y se expresa en milisegundos. Para cada caso se reportan la mediana (p50) y el percentil 99 (p99).

El benchmark se ejecuta con:

```bash
docker compose --profile lab1 run --rm --no-deps \
  -v "$PROYECTO:/proyecto" \
  app-crdb \
  python /proyecto/scripts/benchmark_e3.py
```

Los resultados individuales y la salida completa de la corrida utilizada como evidencia se almacenan en:

```text
evidencia/
├── e3-mediciones.txt
├── e3-resumen.txt
```

