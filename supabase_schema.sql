-- Schema para la tabla de gastos en Supabase
-- Ejecuta este SQL en el SQL Editor de Supabase

CREATE TABLE IF NOT EXISTS gastos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "user" TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    monto NUMERIC(12, 2) NOT NULL CHECK (monto > 0),
    item TEXT NOT NULL,
    categoria TEXT NOT NULL,
    metodo TEXT,
    raw_input TEXT,
    notas TEXT
);

-- Índices para mejorar el rendimiento de consultas
CREATE INDEX IF NOT EXISTS idx_gastos_user ON gastos("user");
CREATE INDEX IF NOT EXISTS idx_gastos_created_at ON gastos(created_at);
CREATE INDEX IF NOT EXISTS idx_gastos_categoria ON gastos(categoria);
CREATE INDEX IF NOT EXISTS idx_gastos_user_created_at ON gastos("user", created_at);

-- Comentarios para documentación
COMMENT ON TABLE gastos IS 'Tabla principal para almacenar los gastos registrados por los usuarios';
COMMENT ON COLUMN gastos.id IS 'Identificador único del gasto (UUID)';
COMMENT ON COLUMN gastos."user" IS 'Nombre del usuario que agregó el gasto';
COMMENT ON COLUMN gastos.created_at IS 'Fecha y hora del registro del gasto';
COMMENT ON COLUMN gastos.monto IS 'Valor de la compra en pesos colombianos';
COMMENT ON COLUMN gastos.item IS 'Descripción del gasto (ej: "Pizza")';
COMMENT ON COLUMN gastos.categoria IS 'Clasificación del gasto inferida por el LLM (ej: "Comida")';
COMMENT ON COLUMN gastos.metodo IS 'Método de pago (Efectivo, Tarjeta, etc.)';
COMMENT ON COLUMN gastos.raw_input IS 'El texto original o transcripción del usuario';
COMMENT ON COLUMN gastos.notas IS 'Contexto adicional opcional del usuario';

-- Habilitar Row Level Security (RLS) - opcional pero recomendado
ALTER TABLE gastos ENABLE ROW LEVEL SECURITY;

-- Política básica: permitir todas las operaciones (ajusta según tus necesidades de seguridad)
-- En producción, deberías crear políticas más restrictivas basadas en el usuario
CREATE POLICY "Allow all operations for authenticated users" ON gastos
    FOR ALL
    USING (true)
    WITH CHECK (true);

