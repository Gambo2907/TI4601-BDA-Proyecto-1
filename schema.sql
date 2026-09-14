-- Esquema da la base de datos para el Proyecto 1

CREATE TABLE IF NOT EXISTS cliente(
    cliente_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre STRING NOT NULL,
    documento STRING NOT NULL,
    region crdb_internal_region NOT NULL 
) LOCALITY REGIONAL BY ROW AS region; -- esto es la "fragmentación horizontal"



CREATE TABLE IF NOT EXISTS cuenta(
    cuenta_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id UUID NOT NULL,
    saldo DECIMAL(12, 2) NOT NULL CHECK (saldo >= 0),
    region crdb_internal_region NOT NULL,

     CONSTRAINT FK_cuenta_clientes
        FOREIGN KEY (cliente_id)
        REFERENCES cliente(cliente_id)
        ON DELETE RESTRICT  -- Evita borrar un cliente si tiene cuentas asociadas
)LOCALITY REGIONAL BY ROW AS region;



CREATE TABLE IF NOT EXISTS movimiento (
    mov_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cuenta_ori_id UUID,
    cuenta_dest_id UUID,
    monto DECIMAL(12, 2) NOT NULL CHECK (monto > 0),
    tipo STRING NOT NULL CHECK (tipo IN ('TRANSFERENCIA','DEPOSITO', 'RETIRO')),
    fecha TIMESTAMPTZ NOT NULL DEFAULT now(),
    region crdb_internal_region NOT NULL,

    CONSTRAINT check_cuenta
    CHECK (
        (tipo = 'TRANSFERENCIA' 
        AND cuenta_ori_id IS NOT NULL 
        AND cuenta_dest_id IS NOT NULL
        AND cuenta_ori_id <> cuenta_dest_id)

        OR

        (tipo = 'DEPOSITO' 
        AND cuenta_ori_id IS NULL 
        AND cuenta_dest_id IS NOT NULL)

        OR

        (tipo = 'RETIRO' 
        AND cuenta_ori_id IS NOT NULL 
        AND cuenta_dest_id IS NULL)
    ),

     CONSTRAINT FK_cuenta_ori_movimiento
        FOREIGN KEY (cuenta_ori_id)
        REFERENCES cuenta(cuenta_id)
        ON DELETE RESTRICT,  -- Evita borrar una cuenta mientras exista un movimiento que la referencie

    CONSTRAINT FK_cuenta_dest_movimiento    
        FOREIGN KEY (cuenta_dest_id)
        REFERENCES cuenta(cuenta_id)
        ON DELETE RESTRICT  -- Evita borrar una cuenta mientras exista un movimiento que la referencie

)LOCALITY REGIONAL BY ROW AS region;

CREATE TABLE ReferenciaCuenta (
    cuenta_id UUID PRIMARY KEY,
    region crdb_internal_region NOT NULL

    CONSTRAINT fk_referencia_cuenta
        FOREIGN KEY (cuenta_id)
        REFERENCES cuenta(cuenta_id)
        ON DELETE RESTRICT
) LOCALITY GLOBAL;




