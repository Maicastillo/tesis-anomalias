# Tesis — Detección de Anomalías en los Gastos a partir de los Estados Contables
## Maira Castillo (Leg. 512452) — Especialización en Ciencia de Datos — ITBA — Junio 2026

---

## Estructura del repositorio

```
codigo_tesis/
├── README.md                          ← este archivo
├── 1_sql/
│   └── pipeline_completo_final.sql    ← pipeline de limpieza en PostgreSQL
├── 2_r/
│   └── eda_anomalias.R                ← análisis exploratorio de datos
└── 3_python/
    └── modelos_anomalias.py           ← modelos de detección de anomalías
```

---

## Requisitos previos

### Base de datos
- PostgreSQL instalado localmente
- Base de datos `tesis_anomalias` creada
- Tablas `raw_data`, `raw_data_clean` y `category_map` ya cargadas
- Usuario: `postgres`, contraseña: `postgres`, puerto: `5432`

### R
- R 4.4.1 o superior
- RStudio recomendado
- Paquetes: RPostgres, DBI, ggplot2, dplyr, tidyr, corrplot, GGally, psych

### Python
- Python 3.11 o superior
- Paquetes: psycopg2-binary, scikit-learn, pandas, matplotlib, seaborn, numpy

---

## Orden de ejecución

### PASO 1 — SQL (pgAdmin 4)
Abrir `1_sql/pipeline_completo_final.sql` en pgAdmin y ejecutar completo.
Esto crea todas las vistas y tablas derivadas en la base `tesis_anomalias`.

**Resultado esperado:**
- 9 vistas: stg_deduped, clean_long, clean_long_final, wide_panel, wide_panel_final, ratios_panel, yoy_panel, model_input_b, long_panel
- 1 tabla: manual_overrides
- 81 observaciones (9 empresas × 9 años 2016-2024)

### PASO 2 — R (RStudio)
Abrir `2_r/eda_anomalias.R` en RStudio y ejecutar sección por sección.
Genera 7 gráficos del análisis exploratorio y la tabla de estadísticas descriptivas.

### PASO 3 — Python (VSCode o terminal)
```bash
cd 3_python
python modelos_anomalias.py
```
Corre los 4 modelos de detección de anomalías (Isolation Forest, LOF, One-Class SVM, K-Means)
en 3 configuraciones: sin imputación, con imputación, y análisis dentro de empresa (XOM y CVX).
Genera 5 gráficos de resultados.

---

## Descripción de los modelos

| Modelo | Descripción |
|---|---|
| Isolation Forest | Aísla anomalías construyendo árboles aleatorios. Las anomalías se aíslan con menos cortes. |
| LOF | Compara la densidad local de cada observación con sus vecinos. |
| One-Class SVM | Aprende una frontera que encierra las observaciones normales. |
| K-Means | Usa la distancia al centroide del cluster como score de anomalía. |

## Features utilizadas

| Feature | Descripción | Cobertura |
|---|---|---|
| dda_pct_rev | Depreciación, Depleción y Amortización / Ingresos | 98.8% |
| exploration_pct_rev | Exploración / Ingresos | 98.8% |
| interest_pct_rev | Intereses / Ingresos | 96.3% |
| sga_pct_rev | Gastos Adm. y Ventas / Ingresos | 87.7% |
| other_taxes_pct_rev | Otros Impuestos / Ingresos | 76.5% |
| impairment_pct_rev | Deterioro de Activos / Ingresos | 35.8% (escenario especial) |
