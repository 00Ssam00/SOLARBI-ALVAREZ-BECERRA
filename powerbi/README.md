# Power BI

- `SolarBI.pbix`: informe completo (3 páginas, modelo estrella con 10 tablas y 15 relaciones, medidas DAX, parámetro what-if de tarifa). Conecta a PostgreSQL `solarbi` con el rol `lector_bi` en modo Importar; las credenciales no se guardan en el archivo.
- `medidas.dax`: todas las medidas en texto, para comparar cambios con Git.
- `SolarBI.pbix.texto/`: la parte textual del `.pbix` (definición de páginas y visuales en JSON, diseño del modelo), extraída para poder ver diferencias en Git. El modelo de datos (`DataModel`) es binario y solo está dentro del `.pbix`.

Para guardar en formato PBIP desde Power BI Desktop: Archivo > Opciones > Características en versión preliminar > "Guardar con formato de proyecto de Power BI (.pbip)", y luego Guardar como `.pbip`.
