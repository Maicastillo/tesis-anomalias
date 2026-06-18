-- ============================================================================
-- PIPELINE COMPLETO DE LIMPIEZA Y PREPARACION DE DATOS
-- Tesis: Deteccion de Anomalias en los Gastos a partir de los Estados Contables
-- Autor: Maira Castillo (Leg. 512452) - Especializacion en Ciencia de Datos ITBA
-- Empresas: XOM, CVX, COP, OXY, SHEL, TTE, EQNR, EOG, PXD
-- Periodo: 2016-2024
-- Base de datos: tesis_anomalias (PostgreSQL / pgAdmin 4)
--
-- PREREQUISITO: Las tablas raw_data, raw_data_clean y category_map ya existen
-- en la base de datos. Este script construye todas las vistas y tablas
-- derivadas desde cero, en orden de dependencia.
-- ============================================================================


-- ============================================================================
-- PASO 1: AJUSTES A category_map
-- ----------------------------------------------------------------------------
-- TotalEnergies reporta sus ingresos bajo multiples variantes de la etiqueta
-- "Revenue From Contracts With Customers" (con y sin impuestos al consumo).
-- Sin este ajuste, dos variantes quedan con la misma prioridad y se suman,
-- duplicando el ingreso. Se prioriza la version "excluyendo impuestos al
-- consumo" por ser la mas comparable entre empresas.
-- ============================================================================

UPDATE category_map SET priority = 2
WHERE category = 'REVENUE_TOTAL'
  AND readable_line_item IN (
    'Revenue From Contracts With Customers Excluding Excise Tax',
    'Revenue From Contract With Customer Excluding Assessed Tax',
    'Revenue From Contracts With Customers'
  );

UPDATE category_map SET priority = 3
WHERE category = 'REVENUE_TOTAL'
  AND readable_line_item IN (
    'Revenue From Contracts With Customers Including Excise Tax',
    'Revenue From Contract With Customer Including Assessed Tax'
  );


-- ============================================================================
-- PASO 2: ELIMINAR VISTAS Y TABLAS EXISTENTES (en orden de dependencia)
-- ============================================================================

DROP VIEW IF EXISTS ratios_panel CASCADE;
DROP VIEW IF EXISTS wide_panel_final CASCADE;
DROP VIEW IF EXISTS wide_panel CASCADE;
DROP VIEW IF EXISTS clean_long_final CASCADE;
DROP VIEW IF EXISTS clean_long CASCADE;
DROP VIEW IF EXISTS stg_deduped CASCADE;
DROP TABLE IF EXISTS manual_overrides CASCADE;


-- ============================================================================
-- PASO 3: stg_deduped
-- ----------------------------------------------------------------------------
-- Vista principal de deduplicacion. Filtra Estado de Resultados +
-- segmento "Consolidated (Total)", ventana 2016-2024.
--
-- Etapa A ("collapsed"): para cada (empresa, item, raw_tag, unidad, periodo,
-- ano de filing, ano fiscal), toma MAX(valor). Esto resuelve el problema
-- central: bajo "Consolidated (Total)" conviven el total consolidado real
-- y las desagregaciones por segmento; el total consolidado es siempre el
-- mayor valor del grupo para categorias aditivas no negativas.
--
-- Etapa B ("prioritized"): cuando un mismo ejercicio fiscal aparece en
-- multiples filings (el 10-K reporta el ano corriente + 1-2 anos comparativos),
-- se prioriza el filing propio (document_year = fiscal_year + 1).
-- ============================================================================

CREATE VIEW stg_deduped AS
WITH base AS (
    SELECT
        company,
        line_item,
        raw_tag,
        unit,
        period_end,
        document_year,
        EXTRACT(YEAR FROM period_end)::INT AS fiscal_year,
        value
    FROM raw_data_clean
    WHERE statement_type = 'Income statement'
      AND segment = 'Consolidated (Total)'
      AND period_end IS NOT NULL
),
collapsed AS (
    SELECT
        company, line_item, raw_tag, unit,
        period_end, document_year, fiscal_year,
        MAX(value) AS value
    FROM base
    WHERE fiscal_year BETWEEN 2016 AND 2024
    GROUP BY company, line_item, raw_tag, unit,
             period_end, document_year, fiscal_year
),
prioritized AS (
    SELECT
        *,
        (document_year - fiscal_year) AS doc_lag,
        CASE
            WHEN (document_year - fiscal_year) = 1 THEN 0
            WHEN (document_year - fiscal_year) > 1 THEN (document_year - fiscal_year)
            ELSE 99
        END AS priority,
        ROW_NUMBER() OVER (
            PARTITION BY company, line_item, fiscal_year
            ORDER BY
                CASE
                    WHEN (document_year - fiscal_year) = 1 THEN 0
                    WHEN (document_year - fiscal_year) > 1 THEN (document_year - fiscal_year)
                    ELSE 99
                END ASC,
                document_year ASC
        ) AS rn
    FROM collapsed
)
SELECT
    company,
    fiscal_year,
    period_end,
    line_item,
    raw_tag,
    value,
    unit,
    document_year AS source_doc_year,
    (priority = 0) AS as_originally_reported
FROM prioritized
WHERE rn = 1;


-- ============================================================================
-- PASO 4: clean_long
-- ----------------------------------------------------------------------------
-- Asigna a cada registro su categoria estandarizada segun category_map.
-- Los registros sin mapeo quedan como 'UNCLASSIFIED'.
-- ============================================================================

CREATE VIEW clean_long AS
SELECT
    d.company,
    d.fiscal_year,
    d.period_end,
    d.line_item,
    d.raw_tag,
    COALESCE(m.category, 'UNCLASSIFIED')           AS category,
    COALESCE(m.category_label_es, 'Sin clasificar') AS category_label_es,
    COALESCE(m.is_expense, FALSE)                   AS is_expense,
    COALESCE(m.priority, 1)                         AS priority,
    d.value,
    d.unit,
    d.source_doc_year,
    d.as_originally_reported
FROM stg_deduped d
LEFT JOIN category_map m ON m.readable_line_item = d.line_item;


-- ============================================================================
-- PASO 5: clean_long_final
-- ----------------------------------------------------------------------------
-- Cuando mas de una etiqueta mapea a la misma categoria para una misma
-- empresa y ano, se conserva una sola: la de menor prioridad y, en caso
-- de empate, la de menor valor. Esto resuelve el caso de TotalEnergies
-- donde distintas variantes de la etiqueta de ingresos tienen la misma
-- prioridad para algunos anos.
-- ============================================================================

CREATE VIEW clean_long_final AS
WITH ranked AS (
    SELECT
        cl.*,
        ROW_NUMBER() OVER (
            PARTITION BY company, fiscal_year, category
            ORDER BY priority ASC, value ASC
        ) AS rn2
    FROM clean_long cl
)
SELECT
    company, fiscal_year, period_end, line_item, raw_tag,
    category, category_label_es, is_expense, priority,
    value, unit, source_doc_year, as_originally_reported
FROM ranked
WHERE rn2 = 1;


-- ============================================================================
-- PASO 6: wide_panel
-- ----------------------------------------------------------------------------
-- Panel ancho: una fila por (empresa, ano fiscal), una columna por categoria.
--
-- Nota sobre expenses_sum_detail: usa SUM(DISTINCT value) para evitar el
-- doble conteo cuando COGS y COGS_PURCHASES_OIL_GAS tienen exactamente el
-- mismo valor (misma cifra etiquetada de dos formas en el mismo filing).
-- Esto afecta a COP y CVX en 2016-2017, TTE en 2018-2019, y PXD en 2017.
-- ============================================================================

CREATE VIEW wide_panel AS
SELECT
    company,
    fiscal_year,
    SUM(value) FILTER (WHERE category = 'REVENUE_TOTAL')
        AS revenue_total,
    SUM(value) FILTER (WHERE category = 'REVENUE_AND_OTHER_INCOME')
        AS revenue_and_other_income,
    SUM(value) FILTER (WHERE category = 'OPERATING_INCOME')
        AS operating_income,
    SUM(value) FILTER (WHERE category = 'INCOME_BEFORE_TAX')
        AS income_before_tax,
    SUM(value) FILTER (WHERE category = 'INCOME_TAX_EXPENSE')
        AS income_tax_expense,
    SUM(value) FILTER (WHERE category = 'NET_INCOME')
        AS net_income,
    SUM(value) FILTER (WHERE category = 'COGS')
        AS cogs,
    SUM(value) FILTER (WHERE category = 'COGS_PURCHASES_OIL_GAS')
        AS cogs_purchases_oil_gas,
    SUM(value) FILTER (WHERE category = 'PRODUCTION_EXPENSE')
        AS production_expense,
    SUM(value) FILTER (WHERE category = 'TRANSPORTATION_MARKETING_EXPENSE')
        AS transportation_marketing_expense,
    SUM(value) FILTER (WHERE category = 'SGA_EXPENSE')
        AS sga_expense,
    SUM(value) FILTER (WHERE category = 'DEPRECIATION_DEPLETION_AMORTIZATION')
        AS depreciation_depletion_amortization,
    SUM(value) FILTER (WHERE category = 'EXPLORATION_EXPENSE')
        AS exploration_expense,
    SUM(value) FILTER (WHERE category = 'IMPAIRMENT_EXPENSE')
        AS impairment_expense,
    SUM(value) FILTER (WHERE category = 'OTHER_TAXES_EXPENSE')
        AS other_taxes_expense,
    SUM(value) FILTER (WHERE category = 'INTEREST_EXPENSE')
        AS interest_expense,
    SUM(value) FILTER (WHERE category = 'EMPLOYEE_BENEFITS_EXPENSE')
        AS employee_benefits_expense,
    SUM(value) FILTER (WHERE category = 'ASSET_RETIREMENT_ACCRETION_EXPENSE')
        AS asset_retirement_accretion_expense,
    SUM(value) FILTER (WHERE category = 'OTHER_OPERATING_EXPENSE')
        AS other_operating_expense,
    SUM(value) FILTER (WHERE category = 'RND_EXPENSE')
        AS rnd_expense,
    SUM(value) FILTER (WHERE category = 'ACQUISITION_RELATED_COSTS')
        AS acquisition_related_costs,
    SUM(value) FILTER (WHERE category = 'TOTAL_COSTS_AND_EXPENSES')
        AS total_costs_and_expenses,
    SUM(value) FILTER (WHERE category = 'TOTAL_OPERATING_EXPENSE')
        AS total_operating_expense,
    SUM(DISTINCT value) FILTER (WHERE category IN (
        'COGS', 'COGS_PURCHASES_OIL_GAS', 'PRODUCTION_EXPENSE',
        'TRANSPORTATION_MARKETING_EXPENSE', 'SGA_EXPENSE',
        'DEPRECIATION_DEPLETION_AMORTIZATION', 'EXPLORATION_EXPENSE',
        'IMPAIRMENT_EXPENSE', 'OTHER_TAXES_EXPENSE', 'INTEREST_EXPENSE',
        'EMPLOYEE_BENEFITS_EXPENSE', 'ASSET_RETIREMENT_ACCRETION_EXPENSE',
        'OTHER_OPERATING_EXPENSE', 'RND_EXPENSE', 'ACQUISITION_RELATED_COSTS'
    )) AS expenses_sum_detail
FROM clean_long_final
GROUP BY company, fiscal_year
ORDER BY company, fiscal_year;


-- ============================================================================
-- PASO 7: manual_overrides
-- ----------------------------------------------------------------------------
-- Correcciones puntuales validadas contra los 10-K originales publicados
-- en la SEC. Unico caso identificado: ExxonMobil 2024.
--
-- Causa: la adquisicion de Pioneer Natural Resources (mayo 2024) amplio
-- la estructura de segmentos de XOM e introdujo un subtotal de ingresos
-- brutos por segmento (478.091) etiquetado bajo "Consolidated (Total)"
-- junto al total consolidado real (349.585), lo que hizo que la regla
-- del MAX tomara el valor incorrecto. Todos los valores corregidos fueron
-- verificados directamente en el Consolidated Statement of Income del
-- 10-K de XOM presentado ante la SEC en febrero de 2025.
-- ============================================================================

CREATE TABLE manual_overrides (
    company         TEXT,
    fiscal_year     INT,
    field           TEXT,
    corrected_value NUMERIC,
    original_value  NUMERIC,
    note            TEXT
);

INSERT INTO manual_overrides
    (company, fiscal_year, field, corrected_value, original_value, note)
VALUES
('XOM', 2024, 'revenue_total',
    349585.00, 478091.00,
    'Total revenues and other income. Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'total_costs_and_expenses',
    300712.00, 426918.00,
    'Total costs and other deductions. Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'cogs_purchases_oil_gas',
    199454.00, 326773.00,
    'Crude oil and product purchases. Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'production_expense',
    39609.00, NULL,
    'Production and manufacturing expenses. Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'sga_expense',
    9976.00, NULL,
    'Selling, general and administrative expenses. Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'depreciation_depletion_amortization',
    23442.00, NULL,
    'Depreciation and depletion (includes impairments). Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'exploration_expense',
    826.00, NULL,
    'Exploration expenses including dry holes. Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'employee_benefits_expense',
    121.00, NULL,
    'Non-service pension and postretirement benefit expense. Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'interest_expense',
    996.00, NULL,
    'Interest expense. Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'other_taxes_expense',
    26288.00, NULL,
    'Other taxes and duties. Verificado en 10-K XOM FY2024 (SEC, febrero 2025).'),
('XOM', 2024, 'expenses_sum_detail',
    301712.00, 428285.00,
    'Suma de partidas individuales verificadas en 10-K XOM FY2024 (SEC, febrero 2025).');


-- ============================================================================
-- PASO 8: wide_panel_final
-- ----------------------------------------------------------------------------
-- Panel ancho definitivo: wide_panel con las correcciones manuales aplicadas
-- via COALESCE. Para las observaciones sin override, el valor original de
-- wide_panel se mantiene sin cambios.
-- ============================================================================

CREATE VIEW wide_panel_final AS
SELECT
    w.company,
    w.fiscal_year,
    COALESCE(o_rev.corrected_value,  w.revenue_total)            AS revenue_total,
    w.revenue_and_other_income,
    w.operating_income,
    w.income_before_tax,
    w.income_tax_expense,
    w.net_income,
    w.cogs,
    COALESCE(o_cpg.corrected_value,  w.cogs_purchases_oil_gas)   AS cogs_purchases_oil_gas,
    COALESCE(o_pe.corrected_value,   w.production_expense)       AS production_expense,
    w.transportation_marketing_expense,
    COALESCE(o_sga.corrected_value,  w.sga_expense)              AS sga_expense,
    COALESCE(o_dda.corrected_value,  w.depreciation_depletion_amortization)
                                                                  AS depreciation_depletion_amortization,
    COALESCE(o_exp.corrected_value,  w.exploration_expense)      AS exploration_expense,
    w.impairment_expense,
    COALESCE(o_ote.corrected_value,  w.other_taxes_expense)      AS other_taxes_expense,
    COALESCE(o_int.corrected_value,  w.interest_expense)         AS interest_expense,
    COALESCE(o_emp.corrected_value,  w.employee_benefits_expense) AS employee_benefits_expense,
    w.asset_retirement_accretion_expense,
    w.other_operating_expense,
    w.rnd_expense,
    w.acquisition_related_costs,
    COALESCE(o_tce.corrected_value,  w.total_costs_and_expenses) AS total_costs_and_expenses,
    w.total_operating_expense,
    COALESCE(o_esd.corrected_value,  w.expenses_sum_detail)      AS expenses_sum_detail
FROM wide_panel w
LEFT JOIN manual_overrides o_rev
    ON o_rev.company = w.company AND o_rev.fiscal_year = w.fiscal_year
    AND o_rev.field = 'revenue_total'
LEFT JOIN manual_overrides o_cpg
    ON o_cpg.company = w.company AND o_cpg.fiscal_year = w.fiscal_year
    AND o_cpg.field = 'cogs_purchases_oil_gas'
LEFT JOIN manual_overrides o_pe
    ON o_pe.company = w.company AND o_pe.fiscal_year = w.fiscal_year
    AND o_pe.field = 'production_expense'
LEFT JOIN manual_overrides o_sga
    ON o_sga.company = w.company AND o_sga.fiscal_year = w.fiscal_year
    AND o_sga.field = 'sga_expense'
LEFT JOIN manual_overrides o_dda
    ON o_dda.company = w.company AND o_dda.fiscal_year = w.fiscal_year
    AND o_dda.field = 'depreciation_depletion_amortization'
LEFT JOIN manual_overrides o_exp
    ON o_exp.company = w.company AND o_exp.fiscal_year = w.fiscal_year
    AND o_exp.field = 'exploration_expense'
LEFT JOIN manual_overrides o_ote
    ON o_ote.company = w.company AND o_ote.fiscal_year = w.fiscal_year
    AND o_ote.field = 'other_taxes_expense'
LEFT JOIN manual_overrides o_int
    ON o_int.company = w.company AND o_int.fiscal_year = w.fiscal_year
    AND o_int.field = 'interest_expense'
LEFT JOIN manual_overrides o_emp
    ON o_emp.company = w.company AND o_emp.fiscal_year = w.fiscal_year
    AND o_emp.field = 'employee_benefits_expense'
LEFT JOIN manual_overrides o_tce
    ON o_tce.company = w.company AND o_tce.fiscal_year = w.fiscal_year
    AND o_tce.field = 'total_costs_and_expenses'
LEFT JOIN manual_overrides o_esd
    ON o_esd.company = w.company AND o_esd.fiscal_year = w.fiscal_year
    AND o_esd.field = 'expenses_sum_detail'
ORDER BY w.company, w.fiscal_year;


-- ============================================================================
-- PASO 9: ratios_panel
-- ----------------------------------------------------------------------------
-- Cada categoria de gasto expresada como porcentaje del ingreso total.
-- Incluye margenes y tasa impositiva efectiva como variables de referencia.
-- sanity_flag = TRUE indica observaciones donde la suma de gastos y margen
-- neto se aleja mas de 30 puntos porcentuales de 100%, lo que sugiere
-- que alguna partida de gasto esta mal medida para esa observacion.
-- Las 12 observaciones flaggeadas corresponden a EOG (8), PXD (2),
-- OXY (1) y EQNR (1) y estan documentadas en la seccion 5.4.7 de la tesis.
-- ============================================================================

CREATE VIEW ratios_panel AS
SELECT
    company,
    fiscal_year,
    revenue_total,
    ROUND(100 * cogs / revenue_total, 2)
        AS cogs_pct_rev,
    ROUND(100 * cogs_purchases_oil_gas / revenue_total, 2)
        AS cogs_purchases_oil_gas_pct_rev,
    ROUND(100 * production_expense / revenue_total, 2)
        AS production_expense_pct_rev,
    ROUND(100 * transportation_marketing_expense / revenue_total, 2)
        AS transport_marketing_pct_rev,
    ROUND(100 * sga_expense / revenue_total, 2)
        AS sga_pct_rev,
    ROUND(100 * depreciation_depletion_amortization / revenue_total, 2)
        AS dda_pct_rev,
    ROUND(100 * exploration_expense / revenue_total, 2)
        AS exploration_pct_rev,
    ROUND(100 * impairment_expense / revenue_total, 2)
        AS impairment_pct_rev,
    ROUND(100 * other_taxes_expense / revenue_total, 2)
        AS other_taxes_pct_rev,
    ROUND(100 * interest_expense / revenue_total, 2)
        AS interest_pct_rev,
    ROUND(100 * employee_benefits_expense / revenue_total, 2)
        AS employee_benefits_pct_rev,
    ROUND(100 * asset_retirement_accretion_expense / revenue_total, 2)
        AS asset_retirement_pct_rev,
    ROUND(100 * other_operating_expense / revenue_total, 2)
        AS other_operating_pct_rev,
    ROUND(100 * rnd_expense / revenue_total, 2)
        AS rnd_pct_rev,
    ROUND(100 * acquisition_related_costs / revenue_total, 2)
        AS acquisition_costs_pct_rev,
    ROUND(100 * expenses_sum_detail / revenue_total, 2)
        AS expenses_sum_detail_pct_rev,
    ROUND(100 * operating_income / revenue_total, 2)
        AS operating_margin_pct,
    ROUND(100 * net_income / revenue_total, 2)
        AS net_margin_pct,
    ROUND(100 * income_tax_expense / income_before_tax, 2)
        AS effective_tax_rate_pct,
    CASE
        WHEN ABS(
            (100 * expenses_sum_detail / revenue_total) +
            (100 * net_income / revenue_total) - 100
        ) > 30 THEN TRUE
        ELSE FALSE
    END AS sanity_flag
FROM wide_panel_final
ORDER BY company, fiscal_year;


-- ============================================================================
-- VERIFICACIONES FINALES
-- ============================================================================

-- a) Cantidad de anos por empresa (esperado: 9 anos, 2016-2024)
SELECT
    company,
    COUNT(DISTINCT fiscal_year) AS n_anios,
    MIN(fiscal_year)            AS desde,
    MAX(fiscal_year)            AS hasta
FROM stg_deduped
GROUP BY company
ORDER BY company;

-- b) Panel final (81 filas)
SELECT * FROM wide_panel_final ORDER BY company, fiscal_year;

-- c) Panel de ratios (81 filas)
SELECT * FROM ratios_panel ORDER BY company, fiscal_year;

-- d) Observaciones con sanity_flag = TRUE (esperado: 12 filas)
SELECT company, fiscal_year, expenses_sum_detail_pct_rev, net_margin_pct
FROM ratios_panel
WHERE sanity_flag = TRUE
ORDER BY company, fiscal_year;

-- e) Verificacion XOM 2024 (valores corregidos del 10-K)
SELECT company, fiscal_year, revenue_total, expenses_sum_detail,
       ROUND(100 * expenses_sum_detail / revenue_total, 2) AS expenses_pct,
       net_income,
       ROUND(100 * net_income / revenue_total, 2)          AS net_margin
FROM wide_panel_final
WHERE company = 'XOM' AND fiscal_year = 2024;
