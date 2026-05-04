import webview
import pyautogui
import pytesseract
import threading
import time
import os
import difflib
import csv
import json
import base64
import tkinter as tk
from tkinter import filedialog
from PIL import Image

# --- CONFIGURATION ET PERSISTENCE ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# Valeurs par défaut
default_config = {
    "tesseract_path": "",
    "scan_zone": [100, 100, 400, 150]
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return default_config
    return default_config

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"Erreur sauvegarde config: {e}")

# Initialisation de la config
config = load_config()

def select_tesseract_path():
    """Ouvre une boîte de dialogue pour sélectionner l'exécutable Tesseract."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Sélectionnez l'exécutable Tesseract (tesseract.exe)",
        filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
    )
    root.destroy()
    return file_path

# Vérification/Demande du chemin Tesseract
if not config.get("tesseract_path") or not os.path.exists(config["tesseract_path"]):
    new_path = select_tesseract_path()
    if new_path:
        config["tesseract_path"] = new_path
        save_config(config)
    else:
        print("Avertissement: Aucun chemin Tesseract valide fourni.")

pytesseract.pytesseract.tesseract_cmd = config.get("tesseract_path", "")

# --- VARIABLES GLOBALES ---
pokemon_data = {}
pokemon_groups = {}
type_chart = {}
icons_cache = {}
sprites_cache = {}
is_scanning = True 

# Récupération de la zone de scan depuis la config
SCAN_ZONE = tuple(config.get("scan_zone", [100, 100, 400, 150]))

current_forms = []
current_form_index = 0

def load_data():
    global pokemon_data, pokemon_groups, type_chart, icons_cache, sprites_cache
    
    # 1. Charger list.csv
    try:
        csv_path = os.path.join(BASE_DIR, 'list.csv')
        if not os.path.exists(csv_path):
            print(f"ERREUR: list.csv introuvable à {csv_path}")
        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_id = row['#'].strip()
                raw_name = row['Name'].replace('\n', ' ').strip()
                
                types = row['Type'].split('\n')
                t1 = types[0].strip() if len(types) > 0 else ""
                t2 = types[1].strip() if len(types) > 1 else ""

                p_info = {
                    'id': p_id,
                    'name': raw_name,
                    'type1': t1,
                    'type2': t2,
                    'hp': row['HP'],
                    'atk': row['Attack'],
                    'def': row['Defense'],
                    'sp_atk': row['Sp. Atk'],
                    'sp_def': row['Sp. Def'],
                    'speed': row['Speed'],
                    'total': row['Total']
                }
                pokemon_data[raw_name] = p_info
                if p_id not in pokemon_groups:
                    pokemon_groups[p_id] = []
                pokemon_groups[p_id].append(p_info)
    except Exception as e:
        print(f"Erreur chargement list.csv: {e}")

    # 2. Charger weakness.csv
    try:
        weak_path = os.path.join(BASE_DIR, 'weakness.csv')
        with open(weak_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            headers = next(reader)[1:]
            for row in reader:
                attacking_type = row[0]
                multipliers = row[1:]
                type_chart[attacking_type] = {headers[i]: float(multipliers[i]) for i in range(len(headers))}
    except Exception as e:
        print(f"Erreur chargement weakness.csv: {e}")

    # 3. Icônes de Types
    icons_dir = os.path.join(BASE_DIR, 'icons')
    if os.path.exists(icons_dir):
        for file in os.listdir(icons_dir):
            if file.lower().endswith('.png'):
                type_name = file.replace('.png', '').replace('.PNG', '').lower()
                try:
                    with open(os.path.join(icons_dir, file), "rb") as img_file:
                        b64_string = base64.b64encode(img_file.read()).decode('utf-8')
                        icons_cache[type_name] = f"data:image/png;base64,{b64_string}"
                except: pass

    # 4. Sprites Pokémon
    sprites_dir = os.path.join(BASE_DIR, 'sprites')
    if os.path.exists(sprites_dir):
        for file in os.listdir(sprites_dir):
            if file.lower().endswith('.png'):
                pkm_key = file.lower().replace('.png', '')
                try:
                    with open(os.path.join(sprites_dir, file), "rb") as img_file:
                        b64_string = base64.b64encode(img_file.read()).decode('utf-8')
                        sprites_cache[pkm_key] = f"data:image/png;base64,{b64_string}"
                except: pass

def calculate_weaknesses(t1, t2):
    weaknesses = {}
    for atk_type in type_chart.keys():
        m1 = type_chart.get(atk_type, {}).get(t1, 1.0)
        m2 = 1.0
        if t2 and t2.strip():
            m2 = type_chart.get(atk_type, {}).get(t2, 1.0)
        total_m = m1 * m2
        if total_m != 1.0:
            weaknesses[atk_type] = total_m
    return weaknesses

def get_type_icon_html(type_name, size_class="type-icon"):
    if not type_name: return ""
    t_key = type_name.strip().lower()
    if t_key in icons_cache:
        return f'<img src="{icons_cache[t_key]}" class="{size_class}" alt="{type_name}">'
    return f'<span class="type-fallback">{type_name}</span>'

def get_pokemon_sprite_html(pkm_data):
    name_key = pkm_data['name'].strip().lower()
    id_key = pkm_data['id'].strip()
    if name_key in sprites_cache:
        return f'<img src="{sprites_cache[name_key]}" class="pkm-sprite">'
    if id_key in sprites_cache:
        return f'<img src="{sprites_cache[id_key]}" class="pkm-sprite">'
    return "<div style='color:#666; font-size:12px;'>Pas d'image</div>"

def update_ui_with_pokemon(data):
    weaknesses = calculate_weaknesses(data['type1'], data['type2'])
    sprite_html = get_pokemon_sprite_html(data)
    types_html = get_type_icon_html(data['type1'], "type-icon-large") + get_type_icon_html(data['type2'], "type-icon-large")
    
    weak_html = ""
    res_html = ""
    for t, m in sorted(weaknesses.items(), key=lambda x: x[1], reverse=True):
        icon = get_type_icon_html(t, "type-icon-badge") 
        item_html = f'<div class="badge-item">{icon}<div class="multiplier">x{m:g}</div></div>'
        if m > 1: weak_html += item_html
        else: res_html += item_html

    forms = pokemon_groups.get(data['id'], [])
    show_nav = len(forms) > 1
    
    js_update = f"""
    document.getElementById('pkm-name').innerText = {json.dumps(data['name'])};
    document.getElementById('pkm-sprite-container').innerHTML = {json.dumps(sprite_html)};
    document.getElementById('pkm-types').innerHTML = {json.dumps(types_html)};
    document.getElementById('stat-hp').innerText = {json.dumps(data['hp'])};
    document.getElementById('stat-atk').innerText = {json.dumps(data['atk'])};
    document.getElementById('stat-def').innerText = {json.dumps(data['def'])};
    document.getElementById('stat-spa').innerText = {json.dumps(data['sp_atk'])};
    document.getElementById('stat-spd').innerText = {json.dumps(data['sp_def'])};
    document.getElementById('stat-spe').innerText = {json.dumps(data['speed'])};
    document.getElementById('stat-total').innerText = {json.dumps(data['total'])};
    document.getElementById('weak-list').innerHTML = {json.dumps(weak_html if weak_html else "Aucune")};
    document.getElementById('res-list').innerHTML = {json.dumps(res_html if res_html else "Aucune")};
    document.getElementById('form-nav').style.display = "{'flex' if show_nav else 'none'}";
    document.getElementById('form-info').innerText = "Forme {current_form_index + 1}/{len(forms)}";
    """
    main_window.evaluate_js(js_update)

# --- API ---
class Api:
    def calibrate(self):
        global SCAN_ZONE, config
        main_window.evaluate_js("showCalibrationStep(1)")
        time.sleep(3.0) 
        x1, y1 = pyautogui.position()
        main_window.evaluate_js("showCalibrationStep(2)")
        time.sleep(3.0)
        x2, y2 = pyautogui.position()
        
        SCAN_ZONE = (x1, y1, x2 - x1, y2 - y1)
        
        # Sauvegarde dans la config
        config["scan_zone"] = list(SCAN_ZONE)
        save_config(config)
        
        main_window.evaluate_js("showCalibrationStep(0)")
        return f"Zone calibrée et sauvegardée: {SCAN_ZONE}"

    def toggle_scan(self):
        global is_scanning
        is_scanning = not is_scanning
        return is_scanning

    def next_form(self):
        global current_form_index
        if len(current_forms) > 1:
            current_form_index = (current_form_index + 1) % len(current_forms)
            update_ui_with_pokemon(current_forms[current_form_index])

    def prev_form(self):
        global current_form_index
        if len(current_forms) > 1:
            current_form_index = (current_form_index - 1) % len(current_forms)
            update_ui_with_pokemon(current_forms[current_form_index])

def scan_loop():
    global current_forms, current_form_index, SCAN_ZONE
    last_detected_id = ""
    pokemon_names = list(pokemon_data.keys())
    
    while True:
        if is_scanning:
            try:
                screenshot = pyautogui.screenshot(region=SCAN_ZONE)
                text = pytesseract.image_to_string(screenshot, lang='eng').strip()
                words = text.split()
                if words:
                    clean_word = words[0].strip(",.!?\"'").capitalize()
                    matches = difflib.get_close_matches(clean_word, pokemon_names, n=1, cutoff=0.6)
                    if matches:
                        best_match_name = matches[0]
                        data = pokemon_data[best_match_name]
                        if data['id'] != last_detected_id:
                            current_forms = pokemon_groups.get(data['id'], [])
                            current_form_index = 0
                            for idx, f in enumerate(current_forms):
                                if f['name'] == best_match_name:
                                    current_form_index = idx
                                    break
                            update_ui_with_pokemon(current_forms[current_form_index])
                            last_detected_id = data['id']
            except: pass
        time.sleep(1.0)

# --- INTERFACE HTML ---
HTML_UI = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; padding: 10px; margin: 0; overflow-x: hidden; }
        .card { background: #1e1e1e; border-radius: 12px; padding: 12px; box-shadow: 0 8px 16px rgba(0,0,0,0.6); border: 1px solid #333; position: relative; }
        #calib-overlay { display: none; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); border-radius: 12px; z-index: 100; flex-direction: column; justify-content: center; align-items: center; text-align: center; padding: 20px; }
        .calib-step { font-size: 1.2em; color: #fffa65; font-weight: bold; margin-bottom: 10px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0px; gap: 10px; }
        h1 { color: #ff4757; margin: 0; font-size: 1.3em; text-align: center; flex-grow: 1; font-weight: 800; }
        .toggle-btn { padding: 5px 8px; border-radius: 6px; border: none; cursor: pointer; font-weight: bold; font-size: 0.7em; }
        .btn-on { background: #2ed573; color: #000; }
        .btn-off { background: #ff4757; color: #fff; }
        .form-nav { display: none; justify-content: center; align-items: center; gap: 10px; margin-bottom: 5px; background: #252525; padding: 4px; border-radius: 8px; }
        .nav-btn { background: #444; color: white; border: none; padding: 2px 8px; border-radius: 5px; cursor: pointer; }
        .sprite-container { display: flex; justify-content: center; align-items: center; min-height: 240px; margin-top: -5px; }
        .pkm-sprite { width: 240px; height: 240px; object-fit: contain; filter: drop-shadow(0 6px 12px rgba(0,0,0,0.6)); }
        .types-container { display: flex; justify-content: center; gap: 15px; margin-bottom: 15px; min-height: 100px; align-items: center; }
        .type-icon-large { width: 100px; height: 100px; object-fit: contain; filter: drop-shadow(0 4px 6px rgba(0,0,0,0.4)); }
        .type-icon-badge { width: 64px; height: 64px; object-fit: contain; display: block; margin-bottom: -15px; margin-top: -10px; }
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-bottom: 8px; }
        .stat-item { background: #2a2a2a; padding: 4px 8px; border-radius: 6px; font-size: 0.75em; display: flex; justify-content: space-between; }
        .stat-item.full { grid-column: span 2; background: #333; border: 1px solid #444; }
        .stat-value { font-weight: bold; color: #70a1ff; }
        .section-title { font-size: 0.65em; text-transform: uppercase; color: #888; margin-bottom: 5px; letter-spacing: 1px; border-bottom: 1px solid #333; padding-bottom: 2px; margin-top: 8px; }
        .badge-list { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }
        .badge-item { background: #252525; padding: 2px; border-radius: 4px; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; border: 1px solid #333; min-width: 60px; height: 42px; overflow: visible; }
        .multiplier { font-weight: bold; font-size: 0.75em; color: #fff; width: 100%; text-align: center; margin-top: auto; padding-bottom: 2px; }
        .btn-calibrate { width: 100%; padding: 8px; background: #3742fa; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 0.8em; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="card">
        <div id="calib-overlay">
            <div class="calib-step" id="step-text">Calibration</div>
            <div id="step-desc">...</div>
        </div>
        <div class="header">
            <button id="btn-toggle" class="toggle-btn btn-on" onclick="pywebview.api.toggle_scan().then(s=> { document.getElementById('btn-toggle').innerText = s ? 'SCAN: ON':'SCAN: OFF'; document.getElementById('btn-toggle').className = s ? 'toggle-btn btn-on':'toggle-btn btn-off'; })">SCAN: ON</button>
            <h1 id="pkm-name">Prêt</h1>
        </div>
        <div class="sprite-container" id="pkm-sprite-container"></div>
        <div class="form-nav" id="form-nav">
            <button class="nav-btn" onclick="pywebview.api.prev_form()">◀</button>
            <span id="form-info">Forme 1/1</span>
            <button class="nav-btn" onclick="pywebview.api.next_form()">▶</button>
        </div>
        <div class="types-container" id="pkm-types"></div>
        <div class="section-title">Base Stats</div>
        <div class="stats-grid">
            <div class="stat-item">PV <span class="stat-value" id="stat-hp">-</span></div>
            <div class="stat-item">VIT <span class="stat-value" id="stat-spe">-</span></div>
            <div class="stat-item">ATK <span class="stat-value" id="stat-atk">-</span></div>
            <div class="stat-item">ATK Sp. <span class="stat-value" id="stat-spa">-</span></div>
            <div class="stat-item">DEF <span class="stat-value" id="stat-def">-</span></div>
            <div class="stat-item">DEF Sp. <span class="stat-value" id="stat-spd">-</span></div>
            <div class="stat-item full">TOTAL <span class="stat-value" style="color:#fffa65" id="stat-total">-</span></div>
        </div>
        <div class="section-title">Faiblesses</div>
        <div class="badge-list" id="weak-list"></div>
        <div class="section-title">Résistances</div>
        <div class="badge-list" id="res-list"></div>
        <button class="btn-calibrate" onclick="pywebview.api.calibrate()">CALIBRER LA ZONE</button>
    </div>
    <script>
        function showCalibrationStep(step) {
            const overlay = document.getElementById('calib-overlay');
            const stepText = document.getElementById('step-text');
            const descText = document.getElementById('step-desc');
            if (step === 0) { overlay.style.display = 'none'; return; }
            overlay.style.display = 'flex';
            if (step === 1) { stepText.innerText = "Étape 1"; descText.innerText = "Haut-gauche du nom..."; }
            else { stepText.innerText = "Étape 2"; descText.innerText = "Bas-droit du nom..."; }
        }
    </script>
</body>
</html>
"""

def start_app():
    global main_window
    load_data()
    api = Api()
    main_window = webview.create_window('Poké-Scanner', html=HTML_UI, js_api=api, width=400, height=980, on_top=True)
    threading.Thread(target=scan_loop, daemon=True).start()
    webview.start()

if __name__ == "__main__":
    start_app()