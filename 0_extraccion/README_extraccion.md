# Extracción de datos — SEC EDGAR (via sec-api.io)

Este script genera el archivo `raw_data` que alimenta el pipeline SQL
(`1_sql/pipeline_completo_final.sql`). **No hace falta correrlo para
reproducir el resto de la tesis**: el dato ya extraído está guardado en
`data/raw/Base_de_datos_1.xlsx`. Esta carpeta queda como documentación del
método de extracción y por si se necesita volver a correrlo (por ejemplo,
para sumar años nuevos).

## Qué hace

Para cada una de las 9 empresas petroleras de la muestra (más BP, que
luego se excluye en el análisis), busca los últimos 10-K (o 20-F para
filers extranjeros: Shell, TotalEnergies, Equinor) vía la API de
[sec-api.io](https://sec-api.io), convierte cada filing de XBRL a JSON, y
vuelca las líneas de Balance Sheet, Income Statement, Cash Flow,
Comprehensive Income y Equity a un Excel (`Master_Energy_Financials.xlsx`)
con las columnas:

```
Company | Document Year | Readable Line Item | Segment / Context |
Raw Tag (GAAP) | Value (in Millions) | Period End | Unit
```

## Requisitos

- Node.js 18 o superior
- Una key propia de [sec-api.io](https://sec-api.io) (tienen free tier,
  pero es un cupo limitado de por vida, no mensual — revisar el dashboard
  antes de correr)

## Instalación

```bash
cd 0_extraccion
npm install
```

## Configurar la key

Abrir `index.js` y pegar tu key real en la constante `API_TOKEN`
(al principio del archivo, reemplazando `'PASTE_YOUR_KEY_HERE'`).

## Correr

```bash
npm start
```

## ⚠️ IMPORTANTE antes de subir a git

Antes de cualquier `git add` / `git commit` / `git push`, volvé a dejar
`API_TOKEN = 'PASTE_YOUR_KEY_HERE'` en `index.js`. **Nunca subir el
archivo con la key real adentro** — GitHub es público y cualquiera que
vea el código va a poder usar esa key.

Genera `Master_Energy_Financials.xlsx` en esta misma carpeta (también
ignorado por git — es un archivo de salida regenerable, no se versiona).

## Nota importante sobre reproducibilidad

Los datos de SEC EDGAR no son estáticos: aparecen filings nuevos y a
veces hay reexpresiones de años anteriores. Correr este script hoy **no
va a devolver exactamente los mismos valores** que están en
`data/raw/Base_de_datos_1.xlsx` (la foto usada para esta tesis). Por eso
el archivo ya extraído es la fuente de verdad para reproducir los
resultados, no una nueva corrida de este script.
