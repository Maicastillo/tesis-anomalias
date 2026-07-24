import pandas as pd
import psycopg2
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ============================================================
# CONEXION Y CARGA DE DATOS
# ============================================================
conn = psycopg2.connect(
    dbname="tesis_anomalias", host="localhost",
    port=5432, user="postgres", password="postgres"
)

ratios  = pd.read_sql('SELECT * FROM ratios_panel ORDER BY company, fiscal_year', conn)
model_b = pd.read_sql('SELECT * FROM model_input_b ORDER BY company, fiscal_year', conn)
conn.close()

print(f"Datos cargados: {ratios.shape[0]} observaciones, {ratios.shape[1]} columnas")

# ============================================================
# CLASIFICACION DE EMPRESAS
# ============================================================
integradas = ['XOM', 'CVX', 'SHEL', 'TTE', 'COP', 'OXY']
ep_puras   = ['EOG', 'PXD', 'EQNR']

# ============================================================
# FEATURES
# ============================================================
features_base = [
    'dda_pct_rev', 'exploration_pct_rev', 'interest_pct_rev',
    'sga_pct_rev', 'other_taxes_pct_rev'
]

features_yoy = features_base + [
    'dda_pct_yoy', 'exploration_pct_yoy', 'interest_pct_yoy',
    'sga_pct_yoy', 'other_taxes_pct_yoy'
]

# ============================================================
# FUNCION: correr los 4 modelos
# ============================================================
def correr_modelos(df, features, nombre_dataset, contamination=0.1):
    print(f"\n{'='*60}")
    print(f"DATASET: {nombre_dataset} | {df.shape[0]} observaciones")
    print(f"Features: {features}")
    print('='*60)

    datos = df[['company', 'fiscal_year'] + features].dropna()
    print(f"Observaciones con datos completos: {datos.shape[0]}")

    X = datos[features].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    resultados = datos[['company', 'fiscal_year']].copy()

    # Isolation Forest
    iso = IsolationForest(contamination=contamination, random_state=42)
    resultados['IF_anomalia'] = iso.fit_predict(X_scaled)
    resultados['IF_score']    = iso.decision_function(X_scaled)
    resultados['IF_anomalia'] = resultados['IF_anomalia'].map({1: 0, -1: 1})

    # LOF
    lof = LocalOutlierFactor(n_neighbors=5, contamination=contamination)
    resultados['LOF_anomalia'] = lof.fit_predict(X_scaled)
    resultados['LOF_score']    = lof.negative_outlier_factor_
    resultados['LOF_anomalia'] = resultados['LOF_anomalia'].map({1: 0, -1: 1})

    # One-Class SVM
    ocsvm = OneClassSVM(nu=contamination, kernel='rbf', gamma='scale')
    resultados['SVM_anomalia'] = ocsvm.fit_predict(X_scaled)
    resultados['SVM_score']    = ocsvm.decision_function(X_scaled)
    resultados['SVM_anomalia'] = resultados['SVM_anomalia'].map({1: 0, -1: 1})

    # K-Means
    n_clusters = 3
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    kmeans.fit(X_scaled)
    distancias = np.min(kmeans.transform(X_scaled), axis=1)
    umbral_km  = np.percentile(distancias, (1 - contamination) * 100)
    resultados['KM_score']    = distancias
    resultados['KM_anomalia'] = (distancias > umbral_km).astype(int)

    # Consenso
    resultados['consenso'] = (
        resultados['IF_anomalia'] + resultados['LOF_anomalia'] +
        resultados['SVM_anomalia'] + resultados['KM_anomalia']
    )
    resultados['anomalia_consenso'] = (resultados['consenso'] >= 2).astype(int)

    anomalias = resultados[resultados['anomalia_consenso'] == 1].sort_values(
        'consenso', ascending=False)
    print(f"\nAnomalias detectadas por consenso (>=2 modelos): {len(anomalias)}")
    print(anomalias[['company', 'fiscal_year', 'IF_anomalia', 'LOF_anomalia',
                      'SVM_anomalia', 'KM_anomalia', 'consenso']].to_string())

    return resultados

# ============================================================
# FUNCION: diagnostico de features
# ============================================================
def diagnosticar_anomalias(df, features, resultados, nombre):
    print(f"\n{'='*60}")
    print(f"DIAGNOSTICO: {nombre}")
    print('='*60)

    datos = df[['company', 'fiscal_year'] + features].dropna()

    for f in features:
        media = datos[f].mean()
        std   = datos[f].std()
        datos[f'z_{f}'] = (datos[f] - media) / std

    diag = resultados[resultados['anomalia_consenso'] == 1][
        ['company', 'fiscal_year', 'consenso']
    ].merge(datos, on=['company', 'fiscal_year'])

    for _, row in diag.iterrows():
        z_vals = {f: round(row[f'z_{f}'], 2) for f in features}
        feature_max = max(z_vals, key=lambda x: abs(z_vals[x]))
        print(f"\n{row['company']} {int(row['fiscal_year'])} "
              f"(detectado por {int(row['consenso'])} modelos)")
        print(f"  Z-scores: {z_vals}")
        print(f"  >> Feature mas anomala: {feature_max} "
              f"(z = {z_vals[feature_max]})")

# ============================================================
# PARTE 1: ESCENARIOS SIN IMPUTACION (dropna)
# ============================================================
print("\n\n" + "="*60)
print("PARTE 1: SIN IMPUTACION (se descartan filas con NULLs)")
print("="*60)

r1 = correr_modelos(ratios, features_base,
    "ANCHO - Todas las empresas")
r2 = correr_modelos(model_b, features_yoy,
    "ANCHO+YoY - Todas las empresas")
r3 = correr_modelos(
    ratios[ratios['company'].isin(integradas)],
    features_base, "ANCHO - Solo integradas")
r4 = correr_modelos(
    ratios[ratios['company'].isin(ep_puras)],
    features_base, "ANCHO - Solo E&P puras")

diagnosticar_anomalias(ratios, features_base, r1,
    "Todas las empresas")
diagnosticar_anomalias(
    ratios[ratios['company'].isin(integradas)],
    features_base, r3, "Solo integradas")
diagnosticar_anomalias(
    ratios[ratios['company'].isin(ep_puras)],
    features_base, r4, "Solo E&P puras")

# ============================================================
# PARTE 2: ESCENARIOS CON IMPUTACION POR PROMEDIO DE CATEGORIA
# ============================================================
print("\n\n" + "="*60)
print("PARTE 2: CON IMPUTACION POR PROMEDIO DE CATEGORIA")
print("="*60)

def imputar_por_categoria(df, features):
    df_imp = df[['company', 'fiscal_year'] + features].copy()
    for f in features:
        media = df_imp[f].mean()
        df_imp[f] = df_imp[f].fillna(media)
    return df_imp

ratios_imp  = imputar_por_categoria(ratios,  features_base)
model_b_imp = imputar_por_categoria(model_b, features_yoy)

r1_imp = correr_modelos(ratios_imp, features_base,
    "IMP - ANCHO Todas las empresas")
r2_imp = correr_modelos(model_b_imp, features_yoy,
    "IMP - ANCHO+YoY Todas las empresas")
r3_imp = correr_modelos(
    ratios_imp[ratios_imp['company'].isin(integradas)],
    features_base, "IMP - Solo integradas")
r4_imp = correr_modelos(
    ratios_imp[ratios_imp['company'].isin(ep_puras)],
    features_base, "IMP - Solo E&P puras")

diagnosticar_anomalias(ratios_imp, features_base, r1_imp,
    "IMP - Todas las empresas")
diagnosticar_anomalias(
    ratios_imp[ratios_imp['company'].isin(integradas)],
    features_base, r3_imp, "IMP - Solo integradas")
diagnosticar_anomalias(
    ratios_imp[ratios_imp['company'].isin(ep_puras)],
    features_base, r4_imp, "IMP - Solo E&P puras")

# ============================================================
# PARTE 3: ANALISIS DENTRO DE EMPRESA (XOM y CVX)
# ============================================================
print("\n\n" + "="*60)
print("PARTE 3: ANALISIS DENTRO DE EMPRESA - XOM y CVX")
print("="*60)

def analisis_dentro_empresa(df, features, empresa):
    print(f"\n{'='*60}")
    print(f"EMPRESA: {empresa}")
    print('='*60)

    # Imputar por promedio historico de la misma empresa
    df_emp = df[df['company'] == empresa][
        ['company', 'fiscal_year'] + features
    ].copy()

    for f in features:
        media_emp = df_emp[f].mean()
        df_emp[f] = df_emp[f].fillna(media_emp)

    print(f"Anos disponibles: {sorted(df_emp['fiscal_year'].tolist())}")
    print(f"Observaciones: {len(df_emp)}")

    X = df_emp[features].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    resultados = df_emp[['company', 'fiscal_year']].copy()

    # Isolation Forest
    iso = IsolationForest(contamination=0.15, random_state=42)
    resultados['IF_anomalia'] = iso.fit_predict(X_scaled)
    resultados['IF_anomalia'] = resultados['IF_anomalia'].map({1:0, -1:1})

    # LOF
    lof = LocalOutlierFactor(n_neighbors=3, contamination=0.15)
    resultados['LOF_anomalia'] = lof.fit_predict(X_scaled)
    resultados['LOF_anomalia'] = resultados['LOF_anomalia'].map({1:0, -1:1})

    # One-Class SVM
    ocsvm = OneClassSVM(nu=0.15, kernel='rbf', gamma='scale')
    resultados['SVM_anomalia'] = ocsvm.fit_predict(X_scaled)
    resultados['SVM_anomalia'] = resultados['SVM_anomalia'].map({1:0, -1:1})

    # KMeans
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
    kmeans.fit(X_scaled)
    distancias = np.min(kmeans.transform(X_scaled), axis=1)
    umbral_km  = np.percentile(distancias, 85)
    resultados['KM_anomalia'] = (distancias > umbral_km).astype(int)

    # Consenso
    resultados['consenso'] = (
        resultados['IF_anomalia'] + resultados['LOF_anomalia'] +
        resultados['SVM_anomalia'] + resultados['KM_anomalia']
    )
    resultados['anomalia_consenso'] = (resultados['consenso'] >= 2).astype(int)

    print(f"\nTodos los anos con su score de anomalia:")
    todos = resultados.merge(df_emp, on=['company', 'fiscal_year'])
    print(todos[['fiscal_year', 'IF_anomalia', 'LOF_anomalia',
                 'SVM_anomalia', 'KM_anomalia', 'consenso']].to_string())

    anomalias = resultados[resultados['anomalia_consenso'] == 1]
    print(f"\nAnomalias detectadas (>=2 modelos): {len(anomalias)}")

    if len(anomalias) > 0:
        diag = anomalias.merge(df_emp, on=['company', 'fiscal_year'])
        for _, row in diag.iterrows():
            z_vals = {}
            for f in features:
                media = df_emp[f].mean()
                std   = df_emp[f].std()
                z_vals[f] = round((row[f] - media) / std, 2) if std > 0 else 0.0
            feature_max = max(z_vals, key=lambda x: abs(z_vals[x]))
            print(f"\n  {int(row['fiscal_year'])} | consenso={int(row['consenso'])}")
            print(f"  Z-scores: {z_vals}")
            print(f"  >> Feature mas anomala: {feature_max} "
                  f"(z = {z_vals[feature_max]})")

    return resultados

analisis_dentro_empresa(ratios, features_base, 'XOM')
analisis_dentro_empresa(ratios, features_base, 'CVX')


# ============================================================
# GRAFICOS DE RESULTADOS
# ============================================================

# Colores por empresa (los mismos que en R)
colores_empresa = {
    'COP': '#7FBFFF', 'CVX': '#FFB347', 'EOG': '#98D98E',
    'EQNR': '#FF9999', 'OXY': '#C3A6E8', 'PXD': '#FFD1A9',
    'SHEL': '#85D4E3', 'TTE': '#F4A7B9', 'XOM': '#B5CC8E'
}

# ============================================================
# GRAFICO 1: Heatmap de anomalias - Sin imputacion
# ============================================================
empresas_orden = ['XOM', 'CVX', 'SHEL', 'TTE', 'COP', 'OXY', 'EOG', 'PXD', 'EQNR']
anos = list(range(2016, 2025))

# Construir matriz de consenso
matriz = pd.DataFrame(index=empresas_orden, columns=anos, data=0)
for _, row in r1.iterrows():
    emp = row['company']
    ano = int(row['fiscal_year'])
    if emp in empresas_orden and ano in anos:
        matriz.loc[emp, ano] = int(row['consenso'])

# Marcar observaciones sin datos (NaN en features)
datos_disponibles = ratios[['company', 'fiscal_year'] + features_base].dropna()
for emp in empresas_orden:
    for ano in anos:
        tiene_dato = len(datos_disponibles[
            (datos_disponibles['company'] == emp) &
            (datos_disponibles['fiscal_year'] == ano)
        ]) > 0
        if not tiene_dato:
            matriz.loc[emp, ano] = -1

fig, ax = plt.subplots(figsize=(14, 6))
matriz_plot = matriz.astype(float).replace(-1, np.nan)
sns.heatmap(
    matriz_plot,
    annot=True, fmt='.0f',
    cmap='YlOrRd',
    vmin=0, vmax=4,
    linewidths=0.5, linecolor='white',
    ax=ax,
    cbar_kws={'label': 'Modelos que detectaron anomalia (0-4)'}
)
ax.set_title('Figura 10. Mapa de Anomalías por Empresa y Año\n(Sin imputación — celdas grises = sin dato)',
             fontsize=13, pad=15)
ax.set_xlabel('Año fiscal', fontsize=11)
ax.set_ylabel('Empresa', fontsize=11)
plt.tight_layout()
plt.savefig('10_heatmap_anomalias_sin_imputacion.png', dpi=150, bbox_inches='tight')
plt.close()
print("Grafico 10 guardado")

# ============================================================
# GRAFICO 2: Heatmap de anomalias - Con imputacion
# ============================================================
matriz_imp = pd.DataFrame(index=empresas_orden, columns=anos, data=0)
for _, row in r1_imp.iterrows():
    emp = row['company']
    ano = int(row['fiscal_year'])
    if emp in empresas_orden and ano in anos:
        matriz_imp.loc[emp, ano] = int(row['consenso'])

fig, ax = plt.subplots(figsize=(14, 6))
sns.heatmap(
    matriz_imp.astype(float),
    annot=True, fmt='.0f',
    cmap='YlOrRd',
    vmin=0, vmax=4,
    linewidths=0.5, linecolor='white',
    ax=ax,
    cbar_kws={'label': 'Modelos que detectaron anomalia (0-4)'}
)
ax.set_title('Figura 11. Mapa de Anomalías por Empresa y Año\n(Con imputación por promedio de categoría)',
             fontsize=13, pad=15)
ax.set_xlabel('Año fiscal', fontsize=11)
ax.set_ylabel('Empresa', fontsize=11)
plt.tight_layout()
plt.savefig('11_heatmap_anomalias_con_imputacion.png', dpi=150, bbox_inches='tight')
plt.close()
print("Grafico 11 guardado")

# ============================================================
# GRAFICO 3: Comparacion de modelos por escenario
# ============================================================
escenarios = [
    ('Todas\n(sin imp.)',    r1),
    ('Todas\n(con imp.)',    r1_imp),
    ('Integradas\n(sin imp.)', r3),
    ('Integradas\n(con imp.)', r3_imp),
    ('E&P\n(sin imp.)',      r4),
    ('E&P\n(con imp.)',      r4_imp),
]

modelos = ['IF_anomalia', 'LOF_anomalia', 'SVM_anomalia', 'KM_anomalia']
nombres = ['Isolation Forest', 'LOF', 'One-Class SVM', 'K-Means']
colores_modelos = ['#2166AC', '#85D4E3', '#FFB347', '#98D98E']

x = np.arange(len(escenarios))
width = 0.2

fig, ax = plt.subplots(figsize=(14, 6))
for i, (modelo, nombre, color) in enumerate(zip(modelos, nombres, colores_modelos)):
    valores = []
    for _, df_esc in escenarios:
        if modelo in df_esc.columns:
            valores.append(df_esc[modelo].sum())
        else:
            valores.append(0)
    ax.bar(x + i * width, valores, width, label=nombre, color=color)

ax.set_xlabel('Escenario', fontsize=11)
ax.set_ylabel('Anomalías detectadas', fontsize=11)
ax.set_title('Figura 12. Anomalías Detectadas por Modelo y Escenario', fontsize=13)
ax.set_xticks(x + width * 1.5)
ax.set_xticklabels([e[0] for e in escenarios], fontsize=9)
ax.legend(fontsize=10)
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig('12_comparacion_modelos_escenarios.png', dpi=150, bbox_inches='tight')
plt.close()
print("Grafico 12 guardado")

# ============================================================
# GRAFICO 4: Evolucion de ratios XOM con anomalias marcadas
# ============================================================
xom = ratios[ratios['company'] == 'XOM'].copy()
xom_res = analisis_dentro_empresa(ratios, features_base, 'XOM')
anos_anomalos_xom = xom_res[xom_res['anomalia_consenso'] == 1]['fiscal_year'].tolist()

fig, axes = plt.subplots(2, 2, figsize=(14, 8))
fig.suptitle('Figura 13. Evolución de Ratios de Gasto — ExxonMobil (2016-2024)\n(Años anómalos marcados en rojo)',
             fontsize=13)

features_plot = [
    ('dda_pct_rev',         'DD&A / Ingresos (%)'),
    ('exploration_pct_rev', 'Exploración / Ingresos (%)'),
    ('interest_pct_rev',    'Intereses / Ingresos (%)'),
    ('sga_pct_rev',         'SGA / Ingresos (%)')
]

for ax, (feat, label) in zip(axes.flat, features_plot):
    ax.plot(xom['fiscal_year'], xom[feat],
            color='#B5CC8E', linewidth=2, marker='o', markersize=5)
    for ano in anos_anomalos_xom:
        val = xom[xom['fiscal_year'] == ano][feat]
        if len(val) > 0 and not val.isna().values[0]:
            ax.axvline(x=ano, color='red', linestyle='--', alpha=0.5)
            ax.scatter([ano], [val.values[0]], color='red', zorder=5, s=80)
    ax.set_title(label, fontsize=10)
    ax.set_xlabel('Año', fontsize=9)
    ax.set_xticks(range(2016, 2025))
    ax.tick_params(axis='x', rotation=45)
    ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig('13_evolucion_xom_anomalias.png', dpi=150, bbox_inches='tight')
plt.close()
print("Grafico 13 guardado")

# ============================================================
# GRAFICO 5: Evolucion de ratios CVX con anomalias marcadas
# ============================================================
cvx = ratios[ratios['company'] == 'CVX'].copy()

# Obtener anos anomalos CVX del analisis dentro de empresa
xom_res = analisis_dentro_empresa(ratios, features_base, 'XOM')
cvx_res = analisis_dentro_empresa(ratios, features_base, 'CVX')
anos_anomalos_cvx = cvx_res[cvx_res['anomalia_consenso'] == 1]['fiscal_year'].tolist()

fig, axes = plt.subplots(2, 2, figsize=(14, 8))
fig.suptitle('Figura 14. Evolución de Ratios de Gasto — Chevron (2016-2024)\n(Años anómalos marcados en rojo)',
             fontsize=13)

for ax, (feat, label) in zip(axes.flat, features_plot):
    ax.plot(cvx['fiscal_year'], cvx[feat],
            color='#FFB347', linewidth=2, marker='o', markersize=5)
    for ano in anos_anomalos_cvx:
        val = cvx[cvx['fiscal_year'] == ano][feat]
        if len(val) > 0 and not val.isna().values[0]:
            ax.axvline(x=ano, color='red', linestyle='--', alpha=0.5)
            ax.scatter([ano], [val.values[0]], color='red', zorder=5, s=80)
    ax.set_title(label, fontsize=10)
    ax.set_xlabel('Año', fontsize=9)
    ax.set_xticks(range(2016, 2025))
    ax.tick_params(axis='x', rotation=45)
    ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig('14_evolucion_cvx_anomalias.png', dpi=150, bbox_inches='tight')
plt.close()
print("Grafico 14 guardado")

print("\nTodos los graficos guardados en la carpeta tesis_modelos")

print("\n\nLISTO - Todos los escenarios corrieron correctamente")


# ============================================================
# GRAFICO 10b: Heatmap solo integradas - Sin imputacion
# ============================================================
empresas_integradas_orden = ['XOM', 'CVX', 'SHEL', 'TTE', 'COP', 'OXY']
anos = list(range(2016, 2025))

matriz_int = pd.DataFrame(index=empresas_integradas_orden, columns=anos, data=0)
for _, row in r3.iterrows():
    emp = row['company']
    ano = int(row['fiscal_year'])
    if emp in empresas_integradas_orden and ano in anos:
        matriz_int.loc[emp, ano] = int(row['consenso'])

# Marcar sin datos
datos_disp_int = ratios[ratios['company'].isin(integradas)][['company', 'fiscal_year'] + features_base].dropna()
for emp in empresas_integradas_orden:
    for ano in anos:
        tiene_dato = len(datos_disp_int[
            (datos_disp_int['company'] == emp) &
            (datos_disp_int['fiscal_year'] == ano)
        ]) > 0
        if not tiene_dato:
            matriz_int.loc[emp, ano] = -1

fig, ax = plt.subplots(figsize=(14, 5))
matriz_int_plot = matriz_int.astype(float).replace(-1, np.nan)
sns.heatmap(
    matriz_int_plot,
    annot=True, fmt='.0f',
    cmap='YlOrRd',
    vmin=0, vmax=4,
    linewidths=0.5, linecolor='white',
    ax=ax,
    cbar_kws={'label': 'Modelos que detectaron anomalia (0-4)'}
)
ax.set_title('Figura 10b. Mapa de Anomalías — Solo Empresas Integradas\n(Sin imputación — celdas grises = sin dato)',
             fontsize=13, pad=15)
ax.set_xlabel('Año fiscal', fontsize=11)
ax.set_ylabel('Empresa', fontsize=11)
plt.tight_layout()
plt.savefig('10b_heatmap_anomalias_integradas.png', dpi=150, bbox_inches='tight')
plt.close()
print("Grafico 10b guardado")


# ============================================================
# GRAFICO 11b: Heatmap solo integradas - Con imputacion
# ============================================================
matriz_int_imp = pd.DataFrame(index=empresas_integradas_orden, columns=anos, data=0)
for _, row in r3_imp.iterrows():
    emp = row['company']
    ano = int(row['fiscal_year'])
    if emp in empresas_integradas_orden and ano in anos:
        matriz_int_imp.loc[emp, ano] = int(row['consenso'])

fig, ax = plt.subplots(figsize=(14, 5))
sns.heatmap(
    matriz_int_imp.astype(float),
    annot=True, fmt='.0f',
    cmap='YlOrRd',
    vmin=0, vmax=4,
    linewidths=0.5, linecolor='white',
    ax=ax,
    cbar_kws={'label': 'Modelos que detectaron anomalia (0-4)'}
)
ax.set_title('Figura 11b. Mapa de Anomalías — Solo Empresas Integradas\n(Con imputación por promedio de categoría)',
             fontsize=13, pad=15)
ax.set_xlabel('Año fiscal', fontsize=11)
ax.set_ylabel('Empresa', fontsize=11)
plt.tight_layout()
plt.savefig('11b_heatmap_anomalias_integradas_imputacion.png', dpi=150, bbox_inches='tight')
plt.close()
print("Grafico 11b guardado")

# ============================================================
# ESCENARIO ESPECIAL: Con impairment como feature adicional
# ============================================================
features_impairment = features_base + ['impairment_pct_rev']

print("\n\n" + "="*60)
print("ESCENARIO ESPECIAL: Con impairment como feature adicional")
print("="*60)

r_imp_especial = correr_modelos(ratios, features_impairment,
    "Con impairment - Todas las empresas")
diagnosticar_anomalias(ratios, features_impairment, r_imp_especial,
    "Con impairment - Todas las empresas")

# Grafico
empresas_orden = ['XOM', 'CVX', 'SHEL', 'TTE', 'COP', 'OXY', 'EOG', 'PXD', 'EQNR']
anos = list(range(2016, 2025))

matriz_imp_esp = pd.DataFrame(index=empresas_orden, columns=anos, data=0)
for _, row in r_imp_especial.iterrows():
    emp = row['company']
    ano = int(row['fiscal_year'])
    if emp in empresas_orden and ano in anos:
        matriz_imp_esp.loc[emp, ano] = int(row['consenso'])

datos_imp = ratios[['company', 'fiscal_year'] + features_impairment].dropna()
for emp in empresas_orden:
    for ano in anos:
        tiene_dato = len(datos_imp[
            (datos_imp['company'] == emp) &
            (datos_imp['fiscal_year'] == ano)
        ]) > 0
        if not tiene_dato:
            matriz_imp_esp.loc[emp, ano] = -1

fig, ax = plt.subplots(figsize=(14, 6))
sns.heatmap(
    matriz_imp_esp.astype(float).replace(-1, np.nan),
    annot=True, fmt='.0f',
    cmap='YlOrRd',
    vmin=0, vmax=4,
    linewidths=0.5, linecolor='white',
    ax=ax,
    cbar_kws={'label': 'Modelos que detectaron anomalia (0-4)'}
)
ax.set_title('Figura 10c. Mapa de Anomalías — Con Impairment como Feature\n(celdas grises = sin dato)',
             fontsize=13, pad=15)
ax.set_xlabel('Año fiscal', fontsize=11)
ax.set_ylabel('Empresa', fontsize=11)
plt.tight_layout()
plt.savefig('10c_heatmap_impairment.png', dpi=150, bbox_inches='tight')
plt.close()
print("Grafico 10c guardado")
