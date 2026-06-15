import requests
import csv
import os
import re
import unicodedata
import html
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

print("PIPELINE CORREGIDO FINAL")

OUTPUT_FILE = "jobs_resultados.csv"

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "linked_descriptions.log")

ENV_FILE = ".env"


def load_env_file(path):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


load_env_file(ENV_FILE)

APP_ID = os.getenv("APP_ID")
APP_KEY = os.getenv("APP_KEY")


def ensure_api_credentials():
    missing = [name for name in ("APP_ID", "APP_KEY") if not os.getenv(name)]
    if missing:
        raise SystemExit(
            "Falta configuración de credenciales. "
            "Crea un archivo .env con APP_ID y APP_KEY o exporta las variables de entorno. "
            "No subas .env al repositorio."
        )

queries = [
    "linux engineer",
    "network engineer",
    "infrastructure engineer",
    "datacenter engineer"
]

SEARCH_FILTERS = [
    {"where": "España", "what_suffix": " remote"},
    {"where": "España", "what_suffix": " teletrabajo"},
    {"where": "Barcelona", "what_suffix": " hybrid"},
    {"where": "Barcelona", "what_suffix": " hibrido"}
]

LINKEDIN_SEARCH_FILTERS = [
    {"keywords_suffix": " remote", "location": "Spain"},
    {"keywords_suffix": " teletrabajo", "location": "Spain"},
    {"keywords_suffix": " hybrid", "location": "Barcelona"},
    {"keywords_suffix": " hibrido", "location": "Barcelona"}
]

# -------------------------
# EXISTENTES
# -------------------------

def cargar_existentes():
    links = set()
    keys = set()

    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("Link"):
                    links.add(r["Link"])
                keys.add((r.get("Titulo","") + r.get("Empresa","")).lower())

    print(f"📦 existentes: {len(links)}")
    return links, keys


# -------------------------
# ADZUNA (CORRECTO)
# -------------------------

def adzuna():
    jobs = []

    for q in queries:
        for filtro in SEARCH_FILTERS:
            search_text = q + filtro["what_suffix"]
            for page in range(1, 4):
                print(f"🔎 {search_text} - {filtro['where']} page {page}")

                url = f"https://api.adzuna.com/v1/api/jobs/es/search/{page}"
                params = {
                    "app_id": APP_ID,
                    "app_key": APP_KEY,
                    "what": search_text,
                    "where": filtro["where"],
                    "sort_by": "date"
                }

                try:
                    r = requests.get(url, params=params, timeout=10)

                    if r.status_code != 200:
                        print("❌ error HTTP:", r.status_code)
                        continue

                    data = r.json()

                    # DEBUG IMPORTANTE
                    if "results" not in data:
                        print("⚠️ respuesta sin results:", data)
                        continue

                    for j in data["results"]:
                        jobs.append({
                            "titulo": j.get("title","") or "",
                            "descripcion": j.get("description","") or "",
                            "empresa": j.get("company", {}).get("display_name","") or "",
                            "ubicacion": j.get("location", {}).get("display_name","") or "",
                            "link": j.get("redirect_url"),
                            "fuente": "Adzuna"
                        })

                except Exception as e:
                    print("❌ error request:", e)

    return jobs


# -------------------------
# LINKEDIN
# -------------------------

def strip_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def get_linkedin_full_description(url, headers):
    """Extrae la descripción completa de una oferta de LinkedIn."""
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return ""

        text = r.text
        patterns = [
            r'<div[^>]*class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*description__text[^"]*"[^>]*>(.*?)</div>',
            r'"descriptionText"\s*:\s*"([^"]+)"',
            r'"description"\s*:\s*\{\s*"text"\s*:\s*"([^"]+)"'
        ]

        for pat in patterns:
            match = re.search(pat, text, re.S)
            if match:
                result = html.unescape(match.group(1))
                result = strip_html(result)
                return re.sub(r"\s+", " ", result).strip()

        return ""
    except Exception:
        return ""


def linkedin():
    jobs = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
    }
    pattern = re.compile(
        r'<a[^>]*class="[^"]*base-card__full-link[^"]*"[^>]*href="([^"]+)"[^>]*>'
        r'.*?<h3[^>]*>(.*?)</h3>.*?<h4[^>]*>(.*?)</h4>.*?<span[^>]*class="[^"]*job-search-card__location[^"]*"[^>]*>(.*?)</span>',
        re.S
    )

    for q in queries:
        for filtro in LINKEDIN_SEARCH_FILTERS:
            search_text = q + filtro["keywords_suffix"]
            for start in range(0, 25, 25):
                print(f"🔎 LinkedIn {search_text} - {filtro['location']} start {start}")

                url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                params = {
                    "keywords": search_text,
                    "location": filtro["location"],
                    "start": start
                }

                try:
                    r = requests.get(url, params=params, headers=headers, timeout=10)

                    if r.status_code != 200:
                        print("❌ error HTTP LinkedIn:", r.status_code)
                        continue

                    response_html = r.text
                    for link, titulo, empresa, ubicacion in pattern.findall(response_html):
                        link = html.unescape(link.strip())
                        if link and not link.startswith("http"):
                            link = "https://www.linkedin.com" + link

                        # Obtener descripción completa
                        descripcion_completa = get_linkedin_full_description(link, headers)

                        if descripcion_completa:
                            print("📄 LinkedIn descripcion:", link)
                            print(descripcion_completa[:400].replace("\n", " "))
                            print("---")

                        jobs.append({
                            "titulo": strip_html(titulo),
                            "descripcion": descripcion_completa,
                            "empresa": strip_html(empresa),
                            "ubicacion": strip_html(ubicacion),
                            "link": link,
                            "fuente": "LinkedIn"
                        })

                except Exception as e:
                    print("❌ error request LinkedIn:", e)

    return jobs


# -------------------------
# LIMPIAR DUPLICADOS
# -------------------------

def limpiar_jobs(jobs):
    unique_by_link = {}
    for j in jobs:
        link = j.get("link")
        if link:
            unique_by_link[link] = j

    unique = {}
    for j in unique_by_link.values():
        key = (
            j.get("titulo", "").strip().lower(),
            j.get("empresa", "").strip().lower(),
            j.get("ubicacion", "").strip().lower(),
        )
        if key not in unique:
            unique[key] = j

    jobs = list(unique.values())
    print(f"📊 jobs únicos: {len(jobs)}")
    return jobs


def log_linkedin_job(job, status, reason=None):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write("=== LinkedIn Job ===\n")
            lf.write(f"timestamp: {datetime.utcnow().isoformat()}Z\n")
            lf.write(f"status: {status}\n")
            if reason:
                lf.write(f"reason: {reason}\n")
            lf.write(f"url: {job.get('link')}\n")
            lf.write(f"title: {job.get('titulo')}\n")
            lf.write(f"company: {job.get('empresa')}\n")
            lf.write(f"location: {job.get('ubicacion')}\n")
            lf.write("description:\n")
            lf.write(job.get('descripcion', '') + "\n")
            lf.write("\n")
    except Exception as e:
        print("❌ error writing log:", e)


# -------------------------
# 🔥 FILTRO INGLÉS POTENTE
# -------------------------

def es_inglés_duro(text):
    def normalize(s):
        if not s:
            return ""
        s = s.lower()
        s = unicodedata.normalize('NFKD', s)
        s = ''.join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    nt = normalize(text)

    # patrones compuestos más específicos
    phrase_patterns = [
        r"\bc1\b",
        r"\bc2\b",
        r"\bfluent\b",
        r"\bbilingual\b",
        r"\bnative\b",
        r"\benglish\b",
        r"advanced english",
        r"excellent english",
        r"strong english",
        r"high level of english",
        r"written and verbal english",
        r"spoken and written english",
        r"communication skills in english",
        r"english is required",
        r"english required",
        r"very good .* english",
        r"english language",
        r"ingles",
        r"ingles requerido",
        r"nivel de ingles",
        r"nivel alto de ingles",
        r"buen nivel de ingles",
        r"inglés",
    ]

    # añadir más variantes y órdenes comunes
    extra_patterns = [
        r"\bgood english\b",
        r"\bvery good english\b",
        r"\bspeak english\b",
        r"\bmust speak english\b",
        r"\bmust have english\b",
        r"\bspoken english\b",
        r"\boral english\b",
        r"\benglish skills\b",
        r"\benglish level\b",
        r"\bse requiere ingles\b",
        r"\bingles requerido\b",
        r"\bingles nivel\b",
        r"\bingles hablado\b",
        r"\bingles escrito\b",
        r"\bfluent english\b",
        r"\badvanced english\b",
        r"\benglish\s*\(required\)\b",
    ]

    phrase_patterns = phrase_patterns + extra_patterns

    for pat in phrase_patterns:
        try:
            if re.search(pat, nt):
                return True
        except re.error:
            if pat in nt:
                return True

    # palabra aislada 'english' como fallback
    if re.search(r"\benglish\b", nt):
        return True

    return False


# -------------------------
# SCORING
# -------------------------

def score(job):
    raw = (
        job.get("titulo", "") + " " + job.get("descripcion", "") + " " + job.get("empresa", "") + " " + job.get("ubicacion", "")
    )

    # normalizar (minúsculas y quitar diacríticos)
    nt = unicodedata.normalize('NFKD', raw)
    nt = ''.join(ch for ch in nt if not unicodedata.combining(ch)).lower()
    nt = re.sub(r"\s+", " ", nt).strip()

    # 🚫 eliminar inglés fuerte (usando la función existente)
    if es_inglés_duro(raw):
        return -999

    # 🚫 evitar menciones generales: english, junior, técnico, devops
    if re.search(r"\b(english|junior|tecnico|devops|ingles)\b", nt):
        return -999

    s = 0

    if "linux" in nt: s += 3
    if "network" in nt: s += 2
    if "security" in nt: s += 2
    if "infra" in nt: s += 2
    if "datacenter" in nt: s += 3

    if "senior" in nt: s += 1

    return s


# -------------------------
# MAIN
# -------------------------

def main():
    ensure_api_credentials()

    # cargar registros previos para comparar
    prev_rows = []
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8", newline="") as f:
            prev_rows = list(csv.DictReader(f))

    def job_key(j):
        link = (j.get("link") or "").strip()
        if link:
            return link
        return (
            j.get("titulo", "").strip().lower()
            + "||"
            + j.get("empresa", "").strip().lower()
            + "||"
            + j.get("ubicacion", "").strip().lower()
        )

    jobs = adzuna() + linkedin()
    print(f"📊 jobs totales: {len(jobs)}")

    jobs = limpiar_jobs(jobs)

    nuevos = []
    for j in jobs:
        link = j.get("link")
        if not link:
            continue

        j["score"] = score(j)

        if j.get("fuente") == "LinkedIn":
            if j["score"] == -999:
                log_linkedin_job(j, "rejected", "english/devops/junior/tecnico filter")
            else:
                log_linkedin_job(j, "accepted")

        if j["score"] == -999:
            continue

        nuevos.append(j)

    print(f"🆕 nuevos: {len(nuevos)}")

    # fallback para evitar CSV vacío pero respetando filtros
    if len(nuevos) == 0 and len(jobs) > 0:
        print("⚠️ fallback activado (filtrando ofertas con ingles)")
        candidatos = []
        for j in jobs[:50]:
            sc = score(j)
            if sc == -999:
                continue
            j["score"] = sc
            candidatos.append(j)
            if len(candidatos) >= 10:
                break

        nuevos = candidatos

    nuevos = sorted(nuevos, key=lambda x: x["score"], reverse=True)

    # comparar con previos
    prev_keys = set()
    for r in prev_rows:
        k = (r.get("Link") or "").strip()
        if not k:
            k = (r.get("Titulo", "") + "||" + r.get("Empresa", "") + "||" + r.get("Ubicacion", ""))
        prev_keys.add(k)

    new_keys = set(job_key(j) for j in nuevos)
    removed = prev_keys - new_keys
    added = new_keys - prev_keys
    unchanged = prev_keys & new_keys

    # no se crea backup: sobrescribimos directamente

    # sobrescribir CSV con los nuevos resultados (borrar los que ya no están)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Titulo", "Empresa", "Ubicacion", "Score", "Link", "Fuente"])
        for j in nuevos:
            writer.writerow([
                j["titulo"],
                j["empresa"],
                j["ubicacion"],
                j["score"],
                j["link"],
                j["fuente"],
            ])

    print(f"✅ guardados: {len(nuevos)}")
    print(f"➕ añadidos: {len(added)}  ➖ eliminados: {len(removed)}  ➖ sin cambios: {len(unchanged)}")
    print("📁", os.path.abspath(OUTPUT_FILE))


# -------------------------
# RUN
# -------------------------

if __name__ == "__main__":
    main()