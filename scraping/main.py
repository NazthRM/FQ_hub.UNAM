import os
import csv
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# PASO 1: FUNCIÓN PARA DESCARGAR EL HTML DE LA UNAM
# ==========================================
def extraer_horarios_completos(ruta_html):
    session = requests.Session()
    url_fase1 = "https://escolares.quimica.unam.mx/Horarios/hor_def_pre_e2.php4"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://escolares.quimica.unam.mx/Horarios/hor_def_pre_e1.php4",
        "Origin": "https://escolares.quimica.unam.mx",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    payload_fase1 = {"gb_action": "todas"}
    
    print("1. Solicitando página intermedia...")
    try:
        response_fase1 = session.post(url_fase1, data=payload_fase1, headers=headers, timeout=15)
        response_fase1.encoding = 'iso-8859-1'
        
        if response_fase1.status_code != 200:
            print(f"Fallo en el Paso 1. Código: {response_fase1.status_code}")
            return False
            
        html_intermedio = response_fase1.text
    except Exception as e:
        print(f"Fallo de conexión en el Paso 1: {e}")
        return False

    # Analizar y empaquetar formulario
    soup = BeautifulSoup(html_intermedio, "html.parser")
    payload_fase2 = {} 

    for hidden in soup.find_all("input", type=lambda t: t and t.lower() == "hidden"):
        name = hidden.get("name")
        value = hidden.get("value", "")
        if name:
            payload_fase2[name] = value

    patron_materias = re.compile(r"^num_uni\[\d+\]$")
    materias_encontradas = 0

    for checkbox in soup.find_all("input", attrs={"name": patron_materias}):
        name = checkbox.get("name")
        value = checkbox.get("value")
        if name and value:
            payload_fase2[name] = value  
            materias_encontradas += 1

    form_tag = soup.find("form")
    action_url = form_tag.get("action") if form_tag else "hor_tot_e2.php4" 
    target_url = f"https://escolares.quimica.unam.mx/Horarios/{action_url}"
    
    print(f"2. Enviando formulario para {materias_encontradas} materias...")

    try:
        response_fase2 = session.post(target_url, data=payload_fase2, headers=headers, timeout=15)
        response_fase2.encoding = 'iso-8859-1'
        
        if response_fase2.status_code == 200:
            # Aseguramos la creación de carpetas si no existen
            os.makedirs(os.path.dirname(ruta_html), exist_ok=True)
            
            with open(ruta_html, "w", encoding="utf-8") as file:
                file.write(response_fase2.text)
            print(f"HTML guardado en '{ruta_html}'.")
            return True
        else:
            print(f"El servidor falló en la descarga con código {response_fase2.status_code}")
            return False

    except Exception as e:
        print(f"Error en la descarga del HTML: {e}")
        return False


# ==========================================
# PASO 2: FUNCIÓN PARA PROCESAR EL HTML Y GUARDAR EN CSV
# ==========================================
def extraer_historial_cupos(ruta_html, ruta_csv):
    if not os.path.exists(ruta_html):
        print(f"No se encontró el archivo {ruta_html}. Se omite la lectura.")
        return

    with open(ruta_html, 'r', encoding='utf-8') as file:
        html_content = file.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    registros_extraccion = []
    
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
                tipo = celdas[3].get_text(strip=True)
                
                tipo_corto = "TEO" if "teor" in tipo.lower() else "LAB" if "lab" in tipo.lower() else tipo.upper()[:3]
                id_unico = f"{clave}-{grupo}-{tipo_corto}"
                
                cupo = "0"
                celda_cupo = fila.find('td', class_=lambda c: c and 'bg-green-600' in c)
                if celda_cupo:
                    spans_cupo = celda_cupo.find_all('span')
                    if len(spans_cupo) >= 2:
                        cupo_texto = spans_cupo[1].get_text(strip=True)
                        cupo = cupo_texto.replace('%', '').strip()

                registros_extraccion.append({
                    "id_unico": id_unico,
                    "Fecha_Hora_Extraccion": fecha_actual,
                    "cupo": cupo
                })

    # Guardar en CSV en formato largo
    os.makedirs(os.path.dirname(ruta_csv), exist_ok=True)
    archivo_existe = os.path.exists(ruta_csv)
    encabezados = ["id_unico", "Fecha_Hora_Extraccion", "cupo"]

    with open(ruta_csv, 'a', encoding='utf-8', newline='') as archivo_escritura:
        escritor = csv.DictWriter(archivo_escritura, fieldnames=encabezados)
        if not archivo_existe:
            escritor.writeheader()
        escritor.writerows(registros_extraccion)

    print(f"[{fecha_actual}] Éxito: Se añadieron {len(registros_extraccion)} registros a '{ruta_csv}'.")


# ==========================================
# SECUENCIA DE EJECUCIÓN DEL CRONJOB
# ==========================================
if __name__ == "__main__":
    # Definimos las variables de ruta en un solo lugar
    RUTA_HTML = "Documentación/datos_crudos.html"
    RUTA_CSV = "Documentación/matriz_cupos.csv"

    # 1. Se descarga el HTML más reciente de la UNAM
    descarga_correcta = extraer_horarios_completos(RUTA_HTML)
    
    # 2. Si la descarga fue exitosa, inmediatamente procesa y actualiza el CSV
    if descarga_correcta:
        extraer_historial_cupos(RUTA_HTML, RUTA_CSV)