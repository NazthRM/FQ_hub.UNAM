import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from pathlib import Path

# ==============================================================================
# CONFIGURACIÓN DE RUTAS Y CONSTANTES
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

DOCS_DIR = BASE_DIR / "Documentación"
CARPETA_PLANES = DOCS_DIR / "planes_estudio"

RUTA_HTML = DOCS_DIR / "datos_crudos.html"
RUTA_HORARIOS = DOCS_DIR / "IDs_horarios.json"
RUTA_SALIDA = DOCS_DIR / "IDs_horarios_enriquecido.json"

CARRERAS_2021 = {
    "IQ": "212021INGENIERIA QUIMICA",
    "IQM": "222021INGENIERIA QUIMICA METALURGICA",
    "Q": "232021QUIMICA",
    "QFB": "242021QUIMICA FARMACEUTICA BIOLOGICA",
    "QA": "282021QUIMICA DE ALIMENTOS",
    "QIM": "292021QUIMICA E INGENIERIA EN MATERIALES",
}

# ==============================================================================
# PASO 1: EXTRAER HORARIOS DE HTML LOCAL
# ==============================================================================
def paso1_extraer_asignaturas(ruta_html, ruta_json):
    print("--- [PASO 1] Extrayendo horarios base ---")
    if not os.path.exists(ruta_html):
        print(f"Error: No se encontró {ruta_html}")
        return

    with open(ruta_html, 'r', encoding='utf-8') as file:
        html_content = file.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    asignaturas = []
    dias_validos = ['Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab']
    tbodys = soup.find_all('tbody', class_='divide-y divide-gray-200 bg-white')

    for tbody in tbodys:
        filas = tbody.find_all('tr', recursive=False)
        for fila in filas:
            celdas = fila.find_all('td', recursive=False)
            if len(celdas) >= 5:
                clave = celdas[0].get_text(strip=True)
                if not clave.isdigit(): 
                    continue 
                
                grupo = celdas[2].get_text(strip=True)
                tipo = celdas[3].get_text(strip=True)  # Únicamente aquí existe el Tipo
                tipo_corto = "TEO" if "teor" in tipo.lower() else "LAB" if "lab" in tipo.lower() else tipo.upper()[:3]
                materia_id = f"{clave}-{grupo}-{tipo_corto}"
                
                nombre_asignatura = celdas[1].find('td').get_text(strip=True) if celdas[1].find('td') else celdas[1].get_text(strip=True)
                profesores_tags = celdas[4].find_all('span', class_='ml-1')
                profesores = [prof.get_text(strip=True) for prof in profesores_tags]
                
                horarios = []
                todos_los_divs = fila.find_all('div')
                for div in todos_los_divs:
                    spans = div.find_all('span', recursive=False)
                    if len(spans) >= 3:
                        dia = spans[0].get_text(strip=True)
                        horas = spans[1].get_text(strip=True)
                        salon = spans[2].get_text(strip=True)
                        if dia in dias_validos and "a" in horas:
                            horarios.append({"dia": dia, "horas": horas, "salon": salon})
                
                asignaturas.append({
                    "id_unico": materia_id,
                    "clave": clave,
                    "asignatura": nombre_asignatura,
                    "grupo": grupo,
                    "tipo": tipo,  
                    "profesores": profesores,
                    "horarios": horarios,
                })

    os.makedirs(os.path.dirname(ruta_json), exist_ok=True)
    with open(ruta_json, 'w', encoding='utf-8') as json_file:
        json.dump(asignaturas, json_file, ensure_ascii=False, indent=4)
        
    print(f"¡Éxito! Se han extraído {len(asignaturas)} asignaturas en {ruta_json}")

# ==============================================================================
# PASO 2: SCRAPING DE PLANES DE ESTUDIO
# ==============================================================================
def extraer_materias_de_tabla(table, es_inorganica=False):
    materias = []
    for row in table.find_all("tr"):
        if row.find("th") or row.find("td", attrs={"colSpan": "5"}):
            continue
        cols = row.find_all("td")
        min_cols = 4 if es_inorganica else 5
        if len(cols) >= min_cols:
            has_checkbox = row.find("input", type=lambda t: t and t.lower() == "checkbox")
            if not has_checkbox:
                continue
            clave = cols[1].get_text(strip=True)
            nombre = cols[2].get_text(strip=True)
            creditos_raw = cols[3].get_text(strip=True) if es_inorganica else cols[4].get_text(strip=True)

            if clave and clave.isdigit():
                materias.append({
                    "clave": clave,
                    "asignatura": nombre,
                    "creditos": int(creditos_raw) if creditos_raw.isdigit() else 0,
                })
    return materias

def procesar_carrera(html_text, clave_carrera, nombre_carrera):
    soup = BeautifulSoup(html_text, "html.parser")
    plan_carrera = {
        "carrera": nombre_carrera, 
        "clave_carrera": clave_carrera,
        "plan": "2021", 
        "semestres": {}, 
        "optativas": [], 
        "sociohumanisticas": []
    }
    tables = soup.find_all("table", attrs={"frame": "box"})
    if not tables:
        tables = soup.find_all("table")

    for table in tables:
        es_optativa = False
        llave_semestre = None
        encabezado = table.find("td", attrs={"colSpan": "5"})
        if encabezado:
            texto_encabezado = encabezado.get_text(strip=True).lower()
            match = re.search(r"semestre:\s*(\d+)", texto_encabezado, re.IGNORECASE)
            if match: llave_semestre = f"semestre_{match.group(1)}"
            else: es_optativa = True
        else:
            texto_tabla = table.get_text().lower()
            match = re.search(r"semestre:\s*(\d+)", texto_tabla, re.IGNORECASE)
            if match: llave_semestre = f"semestre_{match.group(1)}"
            else: es_optativa = True

        materias = extraer_materias_de_tabla(table)
        if materias:
            if es_optativa or not llave_semestre:
                # REGLA: Optativas sin semestre -> "disciplinaria"
                for m in materias: m["caracter"] = "disciplinaria"
                plan_carrera["optativas"].extend(materias)
            else:
                # REGLA: Con semestre -> "semestre"
                for m in materias: m["caracter"] = "semestre"
                if llave_semestre in plan_carrera["semestres"]:
                    plan_carrera["semestres"][llave_semestre].extend(materias)
                else:
                    plan_carrera["semestres"][llave_semestre] = materias
    return plan_carrera

def extraer_adicionales_q(session, headers, folder_salida):
    print("  -> Extrayendo datos adicionales...")
    url = "https://escolares.quimica.unam.mx/Horarios/hor_def_pre_e2.php4"
    payload = {"gb_action": "carrera", "carrera": "232005QUIMICA"}
    try:
        resp = session.post(url, data=payload, headers=headers, timeout=15)
        resp.encoding = "iso-8859-1"
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")
            materias_socio = []
            materias_inorg = []
            for table in tables:
                if table.find("table"): continue
                texto_tabla = table.get_text(" ", strip=True).lower()
                if re.search(r"qu[ií]mica\s+inorg[aá]nica", texto_tabla) and "elecci" in texto_tabla:
                    materias_inorg.extend(extraer_materias_de_tabla(table, es_inorganica=True))
                elif re.search(r"sociohuman[ií]stica", texto_tabla):
                    materias_socio.extend(extraer_materias_de_tabla(table))
                    
            if materias_socio:
                # REGLA: Sociohumanísticas -> "sociohumanistica"
                for m in materias_socio: m["caracter"] = "sociohumanistica"
                for clave_carrera in CARRERAS_2021.keys():
                    ruta_plan = folder_salida / f"plan_2021_{clave_carrera}.json"
                    if ruta_plan.exists():
                        with open(ruta_plan, "r", encoding="utf-8") as f:
                            plan = json.load(f)
                        plan["sociohumanisticas"] = materias_socio
                        with open(ruta_plan, "w", encoding="utf-8") as f:
                            json.dump(plan, f, ensure_ascii=False, indent=4)
                            
            if materias_inorg:
                claves_bloqueadas = {
                    "1400", "1401", "1402", "1404", "1413", 
                    "1502", "1503", "1504", "1506", 
                    "1602", "1603", "1604", "1606"
                }
                materias_inorg = [m for m in materias_inorg if m.get("clave") not in claves_bloqueadas]
                
                # REGLA: Obligatorias de Elección Inorgánica -> "inorgánicas de elección"
                for m in materias_inorg: m["caracter"] = "inorgánicas de elección"
                
                ruta_q = folder_salida / "plan_2021_Q.json"
                if ruta_q.exists():
                    with open(ruta_q, "r", encoding="utf-8") as f:
                        plan_q = json.load(f)
                    plan_q["obligatorias_eleccion_inorganica"] = materias_inorg
                    with open(ruta_q, "w", encoding="utf-8") as f:
                        json.dump(plan_q, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error procesando adicionales: {e}")

def paso2_generar_archivos_por_carrera():
    print("\n--- [PASO 2] Extrayendo planes de estudio por carrera ---")
    os.makedirs(CARPETA_PLANES, exist_ok=True)
    url_fase1 = "https://escolares.quimica.unam.mx/Horarios/hor_def_pre_e2.php4"
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://escolares.quimica.unam.mx/Horarios/hor_def_pre_e1.php4",
        "Origin": "https://escolares.quimica.unam.mx",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    for clave_carrera, valor_payload in CARRERAS_2021.items():
        payload_fase1 = {"gb_action": "carrera", "carrera": valor_payload}
        try:
            resp = session.post(url_fase1, data=payload_fase1, headers=headers, timeout=15)
            resp.encoding = "iso-8859-1"
            if resp.status_code == 200:
                datos_carrera = procesar_carrera(resp.text, clave_carrera, valor_payload)
                archivo_carrera = CARPETA_PLANES / f"plan_2021_{clave_carrera}.json"
                with open(archivo_carrera, "w", encoding="utf-8") as f:
                    json.dump(datos_carrera, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error procesando {clave_carrera}: {e}")
        time.sleep(1)
    extraer_adicionales_q(session, headers, CARPETA_PLANES)

# ==============================================================================
# PASO 3: ENRIQUECER Y ESTANDARIZAR HORARIOS
# ==============================================================================
def cargar_json(ruta):
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def extraer_numero_semestre(texto_semestre):
    match = re.search(r'\d+', str(texto_semestre))
    if match: 
        return int(match.group())
    return ""

def paso3_enriquecer_horarios():
    print("\n--- [PASO 3] Enriqueciendo archivo final de horarios ---")
    horarios = cargar_json(RUTA_HORARIOS)
    if not horarios:
        print("No se pudo cargar IDs_horarios.json")
        return

    mapa_materias = {}
    archivos_planes = list(CARPETA_PLANES.glob("*.json"))

    for ruta_plan in archivos_planes:
        datos_plan = cargar_json(ruta_plan)
        if not datos_plan or not isinstance(datos_plan, dict): 
            continue

        clave_carrera = datos_plan.get("clave_carrera") or datos_plan.get("carrera", "DESCONOCIDA")
        
        # 1. SEMESTRES -> "semestre"
        for nombre_sem, lista_materias in datos_plan.get("semestres", {}).items():
            num_semestre = extraer_numero_semestre(nombre_sem)
            for materia in lista_materias:
                clave = materia.get("clave")
                if not clave: continue
                if clave not in mapa_materias:
                    mapa_materias[clave] = {"creditos": materia.get("creditos"), "carreras": []}
                registro = {
                    "carrera": clave_carrera, 
                    "semestre": num_semestre, 
                    "caracter": "semestre"
                }
                if registro not in mapa_materias[clave]["carreras"]:
                    mapa_materias[clave]["carreras"].append(registro)

        # 2. OPTATIVAS -> "disciplinaria"
        for materia in datos_plan.get("optativas", []):
            clave = materia.get("clave")
            if not clave: continue
            if clave not in mapa_materias:
                mapa_materias[clave] = {"creditos": materia.get("creditos"), "carreras": []}
            registro = {
                "carrera": clave_carrera, 
                "semestre": "", 
                "caracter": "disciplinaria"
            }
            if registro not in mapa_materias[clave]["carreras"]:
                mapa_materias[clave]["carreras"].append(registro)

        # 3. OBLIGATORIAS ELECCIÓN INORGÁNICA -> "inorgánicas de elección"
        for materia in datos_plan.get("obligatorias_eleccion_inorganica", []):
            clave = materia.get("clave")
            if not clave: continue
            if clave not in mapa_materias:
                mapa_materias[clave] = {"creditos": materia.get("creditos"), "carreras": []}
            registro = {
                "carrera": clave_carrera, 
                "semestre": "", 
                "caracter": "inorgánicas de elección"
            }
            if registro not in mapa_materias[clave]["carreras"]:
                mapa_materias[clave]["carreras"].append(registro)

        # 4. SOCIOHUMANISTICAS -> "sociohumanistica"
        for materia in datos_plan.get("sociohumanisticas", []):
            clave = materia.get("clave")
            if not clave: continue
            if clave not in mapa_materias:
                mapa_materias[clave] = {"creditos": materia.get("creditos"), "carreras": []}
            registro = {
                "carrera": clave_carrera, 
                "semestre": "", 
                "caracter": "sociohumanistica"
            }
            if registro not in mapa_materias[clave]["carreras"]:
                mapa_materias[clave]["carreras"].append(registro)

    coincidencias = 0
    for grupo in horarios:
        clave_grupo = grupo.get("clave")
        if clave_grupo in mapa_materias:
            info_curricular = mapa_materias[clave_grupo]
            grupo["creditos"] = info_curricular["creditos"]
            grupo["carreras_asociadas"] = info_curricular["carreras"]
            coincidencias += 1
        else:
            grupo["creditos"] = None
            grupo["carreras_asociadas"] = []

    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(horarios, f, ensure_ascii=False, indent=4)

    print(f"Proceso completado. {coincidencias} grupos fueron enriquecidos.")
    print(f"Archivo generado: {RUTA_SALIDA}")

# ==============================================================================
# EJECUCIÓN PRINCIPAL
# ==============================================================================
if __name__ == "__main__":
    paso1_extraer_asignaturas(RUTA_HTML, RUTA_HORARIOS)
    paso2_generar_archivos_por_carrera()
    paso3_enriquecer_horarios()
    print("\n¡Pipeline finalizado con éxito!")