-- Bronze: copia fiel del CSV. Todo en texto para que un cambio de formato en la
-- fuente no rompa la carga; la validación ocurre en Silver. 'fila' conserva el
-- orden original del archivo y decide qué duplicado se conserva.
CREATE TABLE IF NOT EXISTS bronze.telemetria_cruda (
    fila            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts              text,
    dispositivo_id  text,
    p_ac_kw         text,
    irradiancia_wm2 text,
    temp_modulo_c   text
);
