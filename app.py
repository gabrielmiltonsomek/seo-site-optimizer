
from __future__ import annotations
from flask import Flask, request, render_template, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from xml.etree.ElementTree import Element, SubElement, tostring
from datetime import datetime
import os, zipfile, shutil, re, json, io, tempfile

# --- Config
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev")
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "optimized"
TEMP_FOLDER = "temp"
MAX_ZIP_SIZE_MB = 200

for p in (UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER):
    os.makedirs(p, exist_ok=True)

ALLOWED_ZIP = {".zip"}

def _minify_spaces(s: str) -> str:
    return re.sub(r"\\s+", " ", s).strip()

def _safe_bool_attr(tag, name: str, value: bool = True):
    # HTML boolean attributes render without value
    if value:
        tag.attrs[name] = True

def generate_seo_metadata(title, description, keywords, canonical_url):
    # Basic OpenGraph + JSON-LD
    structured_data = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "url": canonical_url,
        "name": title,
        "description": description,
        "keywords": keywords
    }

    structured_json = json.dumps(structured_data, ensure_ascii=False)

    head_bits = [
        f"<title>{title}</title>",
        f'<meta name="description" content="{description}">',
        f'<meta name="keywords" content="{keywords}">',
        f'<link rel="canonical" href="{canonical_url}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{description}">',
        f'<meta property="og:type" content="website">',
        f'<meta property="og:url" content="{canonical_url}">',
        f'<script type="application/ld+json">{structured_json}</script>',
    ]
    return "\\n".join(head_bits)

def upsert_head_tags(soup: BeautifulSoup, title, desc, kw, canon):
    # Ensure <head> exists
    if not soup.head:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)

    head = soup.head

    # Preserve charset + viewport if present; remove old SEO duplicates
    preserve = []
    for tag in list(head.children):
        if getattr(tag, "name", None) == "meta" and tag.get("charset"):
            preserve.append(tag.extract())
        elif getattr(tag, "name", None) == "meta" and tag.get("name") == "viewport":
            preserve.append(tag.extract())

    for tag in head.find_all(["title","link","meta","script"], recursive=False):
        # remove only our common SEO tags (title, description, keywords, canonical, og:, ld+json)
        if tag.name == "title":
            tag.decompose()
        elif tag.name == "link" and tag.get("rel") == ["canonical"]:
            tag.decompose()
        elif tag.name == "meta":
            n = tag.get("name","").lower()
            p = tag.get("property","").lower()
            if n in {"description","keywords"} or p.startswith("og:"):
                tag.decompose()
        elif tag.name == "script" and tag.get("type") == "application/ld+json":
            tag.decompose()

    # Insert new SEO
    seo_html = BeautifulSoup(generate_seo_metadata(title, desc, kw, canon), "html.parser")
    head.append(seo_html)

    # Re-add preserved metas at top
    for p in preserve:
        head.insert(0, p)

    # Ensure viewport exists
    if not head.find("meta", attrs={"name": "viewport"}):
        meta_view = soup.new_tag("meta")
        meta_view.attrs["name"] = "viewport"
        meta_view.attrs["content"] = "width=device-width, initial-scale=1"
        head.insert(0, meta_view)

    # Ensure charset
    if not head.find("meta", attrs={"charset": True}):
        meta_charset = soup.new_tag("meta")
        meta_charset.attrs["charset"] = "utf-8"
        head.insert(0, meta_charset)

def optimize_html(filepath, title, desc, kw, canon):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        soup = BeautifulSoup(content, "html.parser")

        upsert_head_tags(soup, title, desc, kw, canon)

        # Accessibility + perf
        for img in soup.find_all("img"):
            if not img.get("alt"):
                img["alt"] = "image"
            img["loading"] = "lazy"
            if not img.get("width") or not img.get("height"):
                # Leave dimensions untouched if not easily derivable
                pass

        for script in soup.find_all("script"):
            if not script.get("src"):
                continue
            if not script.get("async") and not script.get("defer"):
                script["defer"] = True

        for video in soup.find_all("video"):
            _safe_bool_attr(video, "preload", True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(str(soup))
    except Exception as e:
        print("HTML optimize error:", filepath, e)

def optimize_css(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            css = f.read()
        # crude minify
        css = re.sub(r"/\\*.*?\\*/", "", css, flags=re.S)  # comments
        css = re.sub(r"\\s+", " ", css).strip()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(css)
    except Exception as e:
        print("CSS optimize error:", filepath, e)

def optimize_js(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            js = f.read()
        js = re.sub(r"/\\*.*?\\*/", "", js, flags=re.S)  # comments
        js = re.sub(r"\\s+", " ", js).strip()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(js)
    except Exception as e:
        print("JS optimize error:", filepath, e)

def compress_image(filepath):
    try:
        img = Image.open(filepath)
        fmt = (img.format or "").upper()
        if fmt in {"JPEG","JPG"}:
            img.save(filepath, optimize=True, quality=75)
        elif fmt == "PNG":
            img.save(filepath, optimize=True)
        elif fmt in {"WEBP"}:
            img.save(filepath, method=6, quality=80)
        else:
            # try saving as original
            img.save(filepath, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError):
        pass

def clean_svg(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            svg = f.read()
        cleaned = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
        cleaned = re.sub(r"\\s+", " ", cleaned)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(cleaned.strip())
    except Exception as e:
        print("SVG clean error:", filepath, e)

def generate_robots_txt(folder):
    with open(os.path.join(folder, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\\nAllow: /\\nSitemap: /sitemap.xml\\n")

def generate_sitemap(folder, base_url):
    urlset = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for subdir, _, files in os.walk(folder):
        for file in files:
            if file.lower().endswith((".html", ".htm")):
                loc = base_url.rstrip("/") + "/" + os.path.relpath(os.path.join(subdir, file), folder).replace("\\\\","/")
                url = SubElement(urlset, "url")
                SubElement(url, "loc").text = loc
                SubElement(url, "lastmod").text = datetime.utcnow().date().isoformat()
    sitemap_path = os.path.join(folder, "sitemap.xml")
    with open(sitemap_path, "wb") as f:
        f.write(tostring(urlset))

def ensure_pwa_assets(folder):
    manifest_path = os.path.join(folder, "manifest.json")
    if not os.path.exists(manifest_path):
        manifest = {
            "name": "SEO Optimized Site",
            "short_name": "SEO",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#111827",
            "icons": []
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    sw_path = os.path.join(folder, "service-worker.js")
    if not os.path.exists(sw_path):
        with open(sw_path, "w", encoding="utf-8") as f:
            f.write(
                "self.addEventListener('install',e=>self.skipWaiting());\\n"
                "self.addEventListener('activate',e=>clients.claim());\\n"
                "self.addEventListener('fetch',()=>{});\\n"
            )

def walk_and_optimize(root, title, desc, kw, canon):
    generate_robots_txt(root)
    generate_sitemap(root, canon)
    ensure_pwa_assets(root)

    for subdir, _, files in os.walk(root):
        for file in files:
            path = os.path.join(subdir, file)
            lower = file.lower()
            if lower.endswith((".html", ".htm")):
                optimize_html(path, title, desc, kw, canon)
            elif lower.endswith((".css", ".scss", ".sass", ".less")):
                optimize_css(path)
            elif lower.endswith((".js", ".mjs", ".jsx", ".tsx", ".ts")):
                optimize_js(path)
            elif lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp")):
                compress_image(path)
            elif lower.endswith(".svg"):
                clean_svg(path)

def is_zipfile_safe(path: str) -> bool:
    # very basic ZIP validation
    try:
        with zipfile.ZipFile(path, "r") as z:
            bad = z.testzip()
            return bad is None
    except zipfile.BadZipFile:
        return False

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("sitezip")
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    keywords = (request.form.get("keywords") or "").strip()
    canonical = (request.form.get("canonical") or "").strip()

    if not file or file.filename == "":
        flash("Please choose a .zip file of your site.")
        return redirect(url_for("index"))
    if not file.filename.lower().endswith(".zip"):
        flash("File must be a .zip archive.")
        return redirect(url_for("index"))
    if not title or not description or not canonical:
        flash("Title, description, and canonical URL are required.")
        return redirect(url_for("index"))

    fname = secure_filename(file.filename)
    zip_path = os.path.join(UPLOAD_FOLDER, fname)
    file.save(zip_path)

    # Size check
    if os.path.getsize(zip_path) > MAX_ZIP_SIZE_MB * 1024 * 1024:
        os.remove(zip_path)
        flash(f"Zip is larger than {MAX_ZIP_SIZE_MB}MB. Split it and try again.")
        return redirect(url_for("index"))

    if not is_zipfile_safe(zip_path):
        os.remove(zip_path)
        flash("Invalid or corrupted ZIP.")
        return redirect(url_for("index"))

    temp_dir = os.path.join(TEMP_FOLDER, fname[:-4])
    out_zip = os.path.join(OUTPUT_FOLDER, fname[:-4] + "_optimized.zip")

    # Clean temp/output if leftover
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(temp_dir)

    # If zip root contains a single folder, dive into it for nicer paths
    entries = [e for e in os.listdir(temp_dir) if not e.startswith("__MACOSX")]
    if len(entries) == 1 and os.path.isdir(os.path.join(temp_dir, entries[0])):
        base_root = os.path.join(temp_dir, entries[0])
    else:
        base_root = temp_dir

    walk_and_optimize(base_root, title, description, keywords, canonical)

    # Re-zip
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for foldername, subfolders, filenames in os.walk(base_root):
            for filename in filenames:
                filepath = os.path.join(foldername, filename)
                arcname = os.path.relpath(filepath, base_root)
                zipf.write(filepath, arcname)

    # Cleanup upload + temp
    try:
        os.remove(zip_path)
    except Exception:
        pass
    shutil.rmtree(temp_dir, ignore_errors=True)

    return send_file(out_zip, as_attachment=True, download_name=os.path.basename(out_zip))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
