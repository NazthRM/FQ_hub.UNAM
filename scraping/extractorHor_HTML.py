import requests
from bs4 import BeautifulSoup
import re

def extraer_horarios_completos():
    # Iniciamos una sesión para mantener las cookies entre el Paso 1 y el Paso 2
    session = requests.Session()
    
    # ==========================================
    # PASO 1: OBTENER EL FORMULARIO (Tu script original)
    # ==========================================
    # Endpoint objetivo oficial de la primera fase
    url_fase1 = "https://escolares.quimica.unam.mx/Horarios/hor_def_pre_e2.php4"
    
    # Encabezados de tu script original
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://escolares.quimica.unam.mx/Horarios/hor_def_pre_e1.php4",
        "Origin": "https://escolares.quimica.unam.mx",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # Payload para pedir la lista de materias
    payload_fase1 = {
        "gb_action": "todas"
    }
    
    print("1. Solicitando la página intermedia con las materias...")
    try:
        # Petición POST para obtener el HTML intermedio[cite: 5]
        response_fase1 = session.post(url_fase1, data=payload_fase1, headers=headers, timeout=15)
        response_fase1.encoding = 'iso-8859-1' #[cite: 5]
        
        if response_fase1.status_code != 200:
            print(f"Fallo en el Paso 1. Código: {response_fase1.status_code}")
            return
            
        print("¡Página intermedia obtenida con éxito!")
        html_intermedio = response_fase1.text
        
    except Exception as e:
        print(f"Fallo de conexión en el Paso 1: {e}")
        return

    # ==========================================
    # PASO 2: EXTRACCIÓN Y ENVÍO DEL SEGUNDO FORMULARIO
    # ==========================================
    print("2. Analizando el formulario y 'marcando' las casillas...")
    soup = BeautifulSoup(html_intermedio, "html.parser")
    payload_fase2 = {} 

    # A) Extraer tokens ocultos
    for hidden in soup.find_all("input", type=lambda t: t and t.lower() == "hidden"):
        name = hidden.get("name")
        value = hidden.get("value", "")
        if name:
            payload_fase2[name] = value

    # B) Extraer TODAS las casillas de materias
    patron_materias = re.compile(r"^num_uni\[\d+\]$")
    materias_encontradas = 0

    for checkbox in soup.find_all("input", attrs={"name": patron_materias}):
        name = checkbox.get("name")
        value = checkbox.get("value")
        
        if name and value:
            payload_fase2[name] = value  
            materias_encontradas += 1

    print(f"Se encontraron y empaquetaron {materias_encontradas} materias.")

    # C) Enviar el formulario final
    form_tag = soup.find("form")
    action_url = form_tag.get("action") if form_tag else "hor_tot_e2.php4" 
    base_url = "https://escolares.quimica.unam.mx/Horarios" 
    
    target_url = f"{base_url}/{action_url}"
    print(f"3. Enviando la solicitud final a: {target_url}")

    try:
        response_fase2 = session.post(target_url, data=payload_fase2, headers=headers, timeout=15)
        response_fase2.encoding = 'iso-8859-1'
        
        if response_fase2.status_code == 200:
            print("4. ¡Éxito total! El servidor devolvió los horarios.")
            
            # Guardamos la respuesta completa en HTML[cite: 5]
            with open("datos_crudos.html", "w", encoding="utf-8") as file:
                file.write(response_fase2.text)
            print("📁 Se guardó exitosamente el archivo 'datos_crudos.html' con los datos finales.")
            
        else:
            print(f"El servidor falló en el último paso con código {response_fase2.status_code}")

    except Exception as e:
        print(f"Ocurrió un error en el Paso 2: {e}")

# Ejecutar el proceso
extraer_horarios_completos()
