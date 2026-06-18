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

print("\n\nLISTO - Todos los escenarios corrieron correctamente")
