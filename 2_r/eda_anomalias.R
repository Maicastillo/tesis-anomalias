# ============================================================================
# ANALISIS EXPLORATORIO DE DATOS (EDA)
# Tesis: Deteccion de Anomalias en los Gastos a partir de los Estados Contables
# Autor: Maira Castillo (Leg. 512452) - Especializacion en Ciencia de Datos ITBA
# Herramienta: R conectado a PostgreSQL via RPostgres
# ============================================================================

# ============================================================================
# PASO 1: INSTALAR PAQUETES (solo la primera vez)
# ============================================================================
# Descomentar y correr solo si no estan instalados:
# install.packages("RPostgres", repos = "http://cran.r-project.org")
# install.packages(c("DBI", "ggplot2", "dplyr", "tidyr", "corrplot", "GGally", "psych"),
#                  repos = "http://cran.r-project.org")

# ============================================================================
# PASO 2: CARGAR LIBRERIAS
# ============================================================================
library(DBI)
library(RPostgres)
library(ggplot2)
library(dplyr)
library(tidyr)
library(corrplot)
library(GGally)
library(psych)

# ============================================================================
# PASO 3: CONEXION A POSTGRESQL
# ============================================================================
con <- dbConnect(
  Postgres(),
  dbname   = "tesis_anomalias",
  host     = "localhost",
  port     = 5432,
  user     = "postgres",
  password = "postgres"   # cambiar si la contrasena es diferente
)

# Verificar conexion - debe mostrar lista de tablas
dbListTables(con)

# ============================================================================
# PASO 4: CARGAR DATOS
# ============================================================================
ratios <- dbReadTable(con, "ratios_panel")
wide   <- dbReadTable(con, "wide_panel_final")

# Verificar
cat("ratios_panel:", nrow(ratios), "filas x", ncol(ratios), "columnas\n")
cat("wide_panel_final:", nrow(wide), "filas x", ncol(wide), "columnas\n")

# ============================================================================
# PALETA DE COLORES (misma en todos los graficos)
# ============================================================================
colores <- c(
  "COP"  = "#7FBFFF",
  "CVX"  = "#FFB347",
  "EOG"  = "#98D98E",
  "EQNR" = "#FF9999",
  "OXY"  = "#C3A6E8",
  "PXD"  = "#FFD1A9",
  "SHEL" = "#85D4E3",
  "TTE"  = "#F4A7B9",
  "XOM"  = "#B5CC8E"
)

# ============================================================================
# FIGURA 1: Evolucion de Ingresos Totales por Empresa (2016-2024)
# ============================================================================
ggplot(wide, aes(x = fiscal_year, y = revenue_total / 1000,
                 color = company, group = company)) +
  geom_line(linewidth = 1) +
  geom_point(size = 2) +
  scale_color_manual(values = colores) +
  labs(
    title  = "Evolución de Ingresos Totales por Empresa (2016-2024)",
    x      = "Año fiscal",
    y      = "Ingresos (miles de millones USD)",
    color  = "Empresa"
  ) +
  theme_minimal() +
  scale_x_continuous(breaks = 2016:2024)

# Guardar: Export -> Save as Image -> "6.1 Evolucion de Ingresos totales por empresa.png"

# ============================================================================
# FIGURA 2a: Gastos Relacionados con Activos (DD&A vs Impairment)
# ============================================================================
ratios_2a <- ratios %>%
  select(company, fiscal_year, dda_pct_rev, impairment_pct_rev) %>%
  rename(
    `Depreciación y Amortización (DD&A)` = dda_pct_rev,
    `Deterioro de Activos (Impairment)`  = impairment_pct_rev
  ) %>%
  pivot_longer(cols = -c(company, fiscal_year),
               names_to = "categoria", values_to = "ratio_pct") %>%
  filter(!is.na(ratio_pct))

ggplot(ratios_2a, aes(x = categoria, y = ratio_pct, fill = categoria)) +
  geom_boxplot(outlier.color = "#CC4444", outlier.size = 2) +
  scale_fill_manual(values = c(
    "Depreciación y Amortización (DD&A)" = "#85D4E3",
    "Deterioro de Activos (Impairment)"  = "#FFB347"
  )) +
  labs(
    title    = "Gastos Relacionados con Activos sobre Ingresos (2016-2024)",
    subtitle = "Depreciación y Amortización vs. Deterioro de Activos",
    x = NULL, y = "% sobre ingresos totales"
  ) +
  theme_minimal() +
  theme(legend.position = "none", axis.text.x = element_text(size = 11))

# Guardar: "6.2a Gastos activos.png"

# ============================================================================
# FIGURA 2b: Gastos de Inversion y Financieros (Exploracion vs Intereses)
# ============================================================================
ratios_2b <- ratios %>%
  select(company, fiscal_year, exploration_pct_rev, interest_pct_rev) %>%
  rename(`Exploración` = exploration_pct_rev, `Intereses` = interest_pct_rev) %>%
  pivot_longer(cols = -c(company, fiscal_year),
               names_to = "categoria", values_to = "ratio_pct") %>%
  filter(!is.na(ratio_pct))

ggplot(ratios_2b, aes(x = categoria, y = ratio_pct, fill = categoria)) +
  geom_boxplot(outlier.color = "#CC4444", outlier.size = 2) +
  scale_fill_manual(values = c("Exploración" = "#98D98E", "Intereses" = "#F4A7B9")) +
  labs(
    title    = "Gastos de Inversión y Financieros sobre Ingresos (2016-2024)",
    subtitle = "Exploración vs. Intereses",
    x = NULL, y = "% sobre ingresos totales"
  ) +
  theme_minimal() +
  theme(legend.position = "none", axis.text.x = element_text(size = 11))

# Guardar: "6.2b Gastos inversion financieros.png"

# ============================================================================
# FIGURA 2c: Gastos de Administracion y Ventas (SG&A)
# ============================================================================
ratios_2c <- ratios %>%
  select(company, fiscal_year, sga_pct_rev) %>%
  rename(`Gastos de Administración y Ventas (SG&A)` = sga_pct_rev) %>%
  pivot_longer(cols = -c(company, fiscal_year),
               names_to = "categoria", values_to = "ratio_pct") %>%
  filter(!is.na(ratio_pct))

ggplot(ratios_2c, aes(x = categoria, y = ratio_pct, fill = categoria)) +
  geom_boxplot(outlier.color = "#CC4444", outlier.size = 2) +
  scale_fill_manual(values = c("Gastos de Administración y Ventas (SG&A)" = "#C3A6E8")) +
  labs(
    title    = "Gastos de Administración y Ventas sobre Ingresos (2016-2024)",
    subtitle = "Estructura de costos administrativos y comerciales",
    x = NULL, y = "% sobre ingresos totales"
  ) +
  theme_minimal() +
  theme(legend.position = "none", axis.text.x = element_text(size = 11))

# Guardar: "6.2c Gastos administracion.png"

# ============================================================================
# FIGURA 3: Evolucion DD&A por empresa
# ============================================================================
ggplot(ratios, aes(x = fiscal_year, y = dda_pct_rev,
                   color = company, group = company)) +
  geom_line(linewidth = 1) +
  geom_point(size = 2) +
  scale_color_manual(values = colores) +
  labs(
    title = "Depreciación, Depleción y Amortización sobre Ingresos (2016-2024)",
    x = "Año fiscal", y = "DD&A / Ingresos (%)", color = "Empresa"
  ) +
  theme_minimal() +
  scale_x_continuous(breaks = 2016:2024)

# Guardar: "6.3 Depreciacion, deplecion y amortizacion s....png"

# ============================================================================
# FIGURA 4: Evolucion Deterioro de Activos por empresa
# ============================================================================
ggplot(ratios, aes(x = fiscal_year, y = impairment_pct_rev,
                   color = company, group = company)) +
  geom_line(linewidth = 1) +
  geom_point(size = 2) +
  scale_color_manual(values = colores) +
  labs(
    title = "Deterioro de Activos sobre Ingresos (2016-2024)",
    x = "Año fiscal", y = "Impairment / Ingresos (%)", color = "Empresa"
  ) +
  theme_minimal() +
  scale_x_continuous(breaks = 2016:2024)

# Guardar: "6.4 Deterioro de gastos sobre ingresos.png"

# ============================================================================
# FIGURA 5: Mapa de calor - Promedio de ratios por empresa
# ============================================================================
ratios_promedio <- ratios %>%
  group_by(company) %>%
  summarise(
    DDA         = mean(dda_pct_rev,         na.rm = TRUE),
    Exploracion = mean(exploration_pct_rev, na.rm = TRUE),
    Impairment  = mean(impairment_pct_rev,  na.rm = TRUE),
    Interes     = mean(interest_pct_rev,    na.rm = TRUE),
    SGA         = mean(sga_pct_rev,         na.rm = TRUE)
  ) %>%
  pivot_longer(cols = -company, names_to = "categoria", values_to = "promedio")

ggplot(ratios_promedio, aes(x = categoria, y = company, fill = promedio)) +
  geom_tile(color = "white", linewidth = 0.5) +
  geom_text(aes(label = round(promedio, 1)), size = 3.5) +
  scale_fill_gradient(low = "#EEF4FF", high = "#2166AC") +
  labs(
    title = "Promedio de Ratios de Gasto por Empresa (2016-2024)",
    x = "Categoría de gasto", y = "Empresa", fill = "% sobre\ningresos"
  ) +
  theme_minimal()

# Guardar: "6.5 Promedio de Ratios de gastos por empresa.png"

# ============================================================================
# FIGURA 6: Matriz de correlacion
# ============================================================================
ratios_num <- ratios %>%
  select(dda_pct_rev, exploration_pct_rev, impairment_pct_rev,
         interest_pct_rev, sga_pct_rev, other_taxes_pct_rev,
         net_margin_pct, operating_margin_pct) %>%
  rename(
    DDA        = dda_pct_rev,
    Exploracion = exploration_pct_rev,
    Impairment  = impairment_pct_rev,
    Interes     = interest_pct_rev,
    SGA         = sga_pct_rev,
    OtroImp     = other_taxes_pct_rev,
    MargenNeto  = net_margin_pct,
    MargenOp    = operating_margin_pct
  )

cor_matrix <- cor(ratios_num, use = "pairwise.complete.obs")

corrplot(cor_matrix,
         method = "color", type = "upper",
         col = colorRampPalette(c("#2166AC", "#FFFFFF", "#D73027"))(200),
         tl.col = "black", tl.cex = 0.9,
         addCoef.col = "black", number.cex = 0.7,
         title = "Correlación entre Ratios de Gasto (2016-2024)",
         mar = c(0, 0, 2, 0))

# Guardar: "6.6 Correlacion entre Ratios de Gastos.png"

# ============================================================================
# TABLA 1: Estadisticas descriptivas
# ============================================================================
ratios_vars <- ratios %>%
  select(dda_pct_rev, exploration_pct_rev, impairment_pct_rev,
         interest_pct_rev, sga_pct_rev, other_taxes_pct_rev,
         net_margin_pct, operating_margin_pct) %>%
  rename(
    DDA              = dda_pct_rev,
    Exploracion      = exploration_pct_rev,
    Impairment       = impairment_pct_rev,
    Intereses        = interest_pct_rev,
    SGA              = sga_pct_rev,
    `Otros Impuestos` = other_taxes_pct_rev,
    `Margen Neto`    = net_margin_pct,
    `Margen Operativo` = operating_margin_pct
  )

desc <- describe(ratios_vars)
print(round(desc[, c("n", "mean", "sd", "min", "median", "max", "skew", "kurtosis")], 2))

# ============================================================================
# FIGURA 7: Cobertura de categorias de gasto
# ============================================================================
cobertura <- ratios %>%
  select(company, fiscal_year,
         dda_pct_rev, exploration_pct_rev, impairment_pct_rev,
         interest_pct_rev, sga_pct_rev, other_taxes_pct_rev,
         cogs_pct_rev, production_expense_pct_rev,
         transport_marketing_pct_rev, employee_benefits_pct_rev,
         asset_retirement_pct_rev, other_operating_pct_rev,
         rnd_pct_rev, acquisition_costs_pct_rev) %>%
  pivot_longer(cols = -c(company, fiscal_year),
               names_to = "categoria", values_to = "valor") %>%
  group_by(categoria) %>%
  summarise(
    n_disponibles = sum(!is.na(valor)),
    n_nulos       = sum(is.na(valor)),
    cobertura_pct = round(100 * sum(!is.na(valor)) / n(), 1)
  ) %>%
  arrange(desc(cobertura_pct))

cobertura_es <- cobertura %>%
  mutate(categoria_es = recode(categoria,
    "dda_pct_rev"                = "Depreciación y Amortización",
    "exploration_pct_rev"        = "Exploración",
    "interest_pct_rev"           = "Intereses",
    "sga_pct_rev"                = "Gastos Adm. y Ventas",
    "other_taxes_pct_rev"        = "Otros Impuestos",
    "cogs_pct_rev"               = "Costo de Mercadería Vendida",
    "other_operating_pct_rev"    = "Otros Gastos Operativos",
    "impairment_pct_rev"         = "Deterioro de Activos",
    "production_expense_pct_rev" = "Gastos de Producción",
    "employee_benefits_pct_rev"  = "Beneficios al Personal",
    "transport_marketing_pct_rev"= "Transporte y Comercialización",
    "asset_retirement_pct_rev"   = "Desmantelamiento de Activos",
    "rnd_pct_rev"                = "Investigación y Desarrollo",
    "acquisition_costs_pct_rev"  = "Costos de Adquisiciones"
  ))

ggplot(cobertura_es, aes(x = reorder(categoria_es, cobertura_pct),
                          y = cobertura_pct, fill = cobertura_pct)) +
  geom_bar(stat = "identity") +
  geom_text(aes(label = paste0(cobertura_pct, "%")), hjust = -0.1, size = 3.5) +
  scale_fill_gradient(low = "#FFD1A9", high = "#2166AC") +
  coord_flip() +
  labs(
    title    = "Cobertura de Categorías de Gasto en el Dataset (2016-2024)",
    subtitle = "% de observaciones empresa-año con dato disponible sobre 81 totales",
    x = NULL, y = "% de cobertura"
  ) +
  theme_minimal() +
  theme(legend.position = "none") +
  ylim(0, 115)

# Guardar: "6.7 Cobertura de categorias.png"

# ============================================================================
# CERRAR CONEXION
# ============================================================================
dbDisconnect(con)
cat("Conexion cerrada. EDA completado.\n")
