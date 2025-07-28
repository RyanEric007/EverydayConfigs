#!/usr/bin/env python3
# ==========================================================
#   DarkEntropyFileServer.py
#   Author: Ryan Johanides
#   Email: RJ@DarkEntropy.org
#   Description: Cyber-themed file share server with SPA UI
# ==========================================================
#
# TABLE OF CONTENTS
# --------------------------
# - Imports, constants, user options (top)
# - CSS (CYBER_CSS)
# - HTML section functions (upload, nav, filetable, etc.)
# - HTTP Handler class (file/folder listing, upload, view, download)
# - Main/server code (argparse, kill option, run server)
#
# Quick usage:
#   python3 DarkEntropyFileServer.py [options]
#   -p/--port <PORT>        Port to use (default 9000)
#   -b/--bind <ADDR>        Bind to specific address (default 0.0.0.0)
#   -k/--kill <PORT>        Kill process using PORT
#   -s/--show-hidden        Show hidden files (starting with .)
# ==========================================================


import http.server, socketserver, os, sys, socket, argparse, threading, html, shutil, stat, subprocess, platform, signal, time
from urllib.parse import urlparse, parse_qs

try:
    import pwd, grp
    HAS_UNIX = True
except ImportError:
    HAS_UNIX = False

try:
    import cgi
    HAS_CGI = True
except ImportError:
    HAS_CGI = False

DEFAULT_PORT = 9000
DEFAULT_HASH = "md5"
HASH_OPTIONS = ["md5", "sha1", "sha224", "sha256", "sha384", "sha512"]

# ========================== CSS ===========================
CYBER_CSS = """
<style>
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css');
body {
  margin: 0; background: #101215; color: #e3f9ff; font-family: 'Inter', 'Segoe UI', Arial, sans-serif; font-size: 1.1em;
}
.sticky-bar { position:sticky; top:0; z-index:200; background: #101215ee; box-shadow:0 1px 18px #00fff930;}
.nav-main {
  text-align:center; padding: 18px 5vw 0 5vw;
}
.title {
  font-size: 2.5em; font-weight: bold; color: #1bf6ff;
  text-shadow: 0 0 18px #0ff,0 0 38px #44f1fb8a;
  letter-spacing: 1.5px;
}
.subtitle {
  font-size: 1.07em; color: #c8eaff;
  text-shadow:0 0 4px #0ff6,0 0 12px #103e43d3;
  margin-bottom: 0.5em;
}
.hr {
  height: 4px; margin: 12px 0 0 0;
  background: linear-gradient(90deg, #00fff7cc 0%, #10121500 100%);
  border: none; border-radius: 2px; box-shadow:0 0 13px #00fff7d0;
}
.upload-header-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: 1.2em; max-width: 1000px; margin: 12px auto 0 auto;
}
.upload-toggle {
  background: none; border: none; color: #e3f9ff;
  font-size: 1.3em; font-weight: bold; display: flex; align-items:center;
  gap:.6em; cursor:pointer; padding:0; transition: color .17s;
}
.upload-toggle i { color: #a2f5ff; font-size:1.15em;}
.upload-toggle:hover { color: #36f6ff; text-shadow:0 0 8px #10ecfdad;}
.hash-select {
  font-size: 1.15em; color: #b8feff; display: flex; align-items: center;
  background: #101419; border-radius: 8px; padding: 4px 17px 4px 9px;
  border: 2px solid #14d4ec; box-shadow: 0 0 8px #00fff8a8;
}
.hash-select label { margin-right:8px; font-weight:500;}
.hash-select select {
  background: #101419; color: #18f8ff;
  border: none; font-size: 1.05em; border-radius: 6px;
  padding: 4px 11px; margin-left:.4em; outline: none;
}
.hash-select select:focus { background: #1e1f2e; color:#00fff7;}
.kill-btn {
  background: #1e0d11; color: #ff4c5b; border:2px solid #fd5b8b;
  border-radius: 10px; font-size: 1.1em; padding: 6px 18px;
  font-weight:500; cursor:pointer; margin-left:.5em;
  box-shadow:0 0 12px #ff0d4380; transition:.18s;
}
.kill-btn:hover { background:#fd5b8b; color:#fff; }
.card-wrap {
  max-width: none;
  width: 100%;
  margin: 38px auto 0 auto;
  padding: 0 15px;
}
.table-card, .upload-card {
  background: #131419;
  border-radius: 22px;
  margin: 0 0 32px 0;
  padding: 26px 28px 30px 28px;
  box-shadow: 0 0 24px #00fff767,0 0 1px #00fff744;
  border: 2.7px solid #00fff7be;
  width: 100%;
  max-width: none;
  overflow-x: auto;
}
.upload-drawer { display:none;}
.upload-drawer.open { display:block; animation: fadein .44s;}
@keyframes fadein { from { opacity:.22; transform: translateY(-22px);} to{opacity:1; transform:none;} }
.upload-zone {
  background: #191b21; border:2px dashed #36e9ff;
  border-radius: 12px; min-height: 100px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  font-size: 1.22em; color: #b8f7ff; margin: 24px auto 16px auto; padding: 20px 0 14px 0;
  transition:.14s; text-align:center;
  cursor: pointer;
}
.upload-zone.dragover { background: #222c2f; border-color: #fff; color: #36e9ff;}
.upload-zone i { font-size: 2.3em; margin-bottom:.2em; color: #b8feff;}
.upload-zone input[type=file] { display:none;}
.upload-zone label { cursor:pointer; color:#27e8fa; text-decoration:underline;}
.upload-status { color:#4cf6a1; text-align:center; margin:0 auto 9px auto;}
.upload-error { color:#ff4c5b; font-weight:bold; text-align:center; }
#mainTableCard { min-height: 430px;}
.files-table {
  width: 100%;
  border-collapse: collapse;
  margin: 0 auto;
  table-layout: auto;
}
.files-table th, .files-table td {
  padding: 8px 16px; font-size:1.06em; white-space: nowrap;
}
.files-table th {
  color:#1bf6ff;
  background: #181f23;
  border-bottom: 2.2px solid #00fff7a7;
  text-align: center;
}
.files-table tr {
  background:none;
}
.files-table tr.row-highlight, .files-table tr:hover {
  background: #0f28387a; cursor:pointer;
}
.files-table td, .files-table th {
  border-right: 1px solid #1b2c35;
  text-align: left;
}
.files-table td:last-child, .files-table th:last-child {
  border-right:none;
}
.files-table .icon {
  text-align:center; width:34px;
}
.files-table .icon .fa-folder {
  color: #1bf6ff;
}
.files-table .icon .fa-file {
  color: #ff6f61;
}
.files-table .icon .fa-level-up-alt {
  color: #ffaa00;
  font-weight: bold;
}
.files-table .file-name {
  color: #18f8ff; text-decoration: underline; cursor:pointer;
}
.files-table .dir-name {
  color:#f2fff9; font-weight: bold; font-size: 1.13em;
}
.files-table .active {
  color: #a1f8ff !important;
}
.files-table .hash {
  background: #14171f; color: #43fff7; font-family: monospace; border-radius: 6px; padding: 2px 8px;
}
.files-table .ownergrp {
  color:#a8e6f7;
}
.files-table .time {
  color: #b5e3ff;
}
.files-table .size {
  color: #bbffdc;
}
.files-table input[type="search"] {
  background: #161d22; color: #baeaff; border: 2px solid #0ff9; border-radius: 6px; font-size: 1em;
  padding: 7px 13px; width: 270px; margin-left: auto; margin-bottom: 18px; float: right;
}
.files-table .download-link {
  color: #1bf6ff; text-decoration: underline; font-weight: 600; font-size: 1.08em;
}
.files-table .download-link:hover {
  color: #fff; background: #00fff7; border-radius: 6px;
}
.copyright {
  margin: 42px auto 11px auto; color: #21c7f7; text-align: center; font-size: .93em; opacity: .8;
  position: fixed; bottom: 6px; width: 100%; left: 0;
  background: #101215cc; padding: 6px 0;
  box-shadow: 0 -4px 10px #00fff7bb inset;
  z-index: 100;
}
#file-modal {
  display:none; position:fixed; z-index:300; top:0; left:0; width:100vw; height:100vh;
  background:#01151b77; align-items:center; justify-content:center;
}
#file-modal .modal-content {
  background:#181e23; color:#f8f9fc; border-radius: 16px; max-width:66vw;
  box-shadow:0 0 33px #00fff7c8; padding: 33px 38px 28px 32px; position:relative;
  border:2.5px solid #00fff7ee; font-size:1.13em; min-width:410px;
}
#file-modal .modal-close {
  position:absolute; right:26px; top:11px; font-size:2.3em; color:#ff4c5b; font-weight:bold; cursor:pointer;
  text-shadow:0 0 10px #f00,0 0 13px #ff0000b2;
}
#file-modal pre {
  background: #161c23; color: #bcf6ff; font-size: 1em; padding: 12px 9px; border-radius: 8px; overflow-x: auto;
}
@media (max-width:900px) {
  .card-wrap {
    padding: 0 10px;
  }
  #file-modal .modal-content {
    max-width: 90vw; min-width: 1px;
  }
  .files-table input[type="search"] {
    width: 100%;
    margin-bottom: 16px;
    float: none;
  }
}
</style>
"""

# ===================== HTML FUNCTIONS =======================

def upload_header_row_html(pid, hash_alg):
    hash_select = ''.join(
        f'<option value="{opt}" {"selected" if hash_alg==opt else ""}>{opt.upper()}</option>'
        for opt in HASH_OPTIONS
    )
    return f"""
    <div class="upload-header-row">
        <button class="upload-toggle" onclick="toggleUploadDrawer()">
          <i class="fa fa-cloud-upload"></i> Upload a file
        </button>
        <div class="hash-select">
            <label for="hashSelect">Hash:</label>
            <select id="hashSelect" onchange="changeHash(this.value)">
                {hash_select}
            </select>
        </div>
        <form method="POST" action="/kill" style="display:inline">
            <button class="kill-btn" type="submit" onclick="return confirm('Kill server process {pid}?')">kill {pid}</button>
        </form>
    </div>
    """

def upload_drawer_html():
    return """
    <div class="upload-card upload-drawer" id="uploadDrawer">
      <form id="uploadForm" method="POST" enctype="multipart/form-data" style="margin:0;">
        <div class="upload-zone" id="uploadZone" onclick="document.getElementById('fileInput').click();">
            <i class="fa fa-folder-open"></i>
            <span>Drop file here<br>or <label for="fileInput">browse</label></span>
            <input id="fileInput" type="file" name="file" multiple>
            <input type="hidden" id="uploadFolder" name="folder" value=".">
        </div>
        <div class="upload-status" id="uploadStatus"></div>
      </form>
    </div>
    """

def get_file_table_html(folder, hash_alg, show_hidden=False):
    import hashlib
    try:
        items = sorted(os.listdir(folder), key=lambda x: (not os.path.isdir(os.path.join(folder,x)), x.lower()))
        if not show_hidden:
            items = [i for i in items if not i.startswith('.')]
    except Exception as e:
        return f'<div class="upload-error">Error: {html.escape(str(e))}</div>'

    rows = []

    # Always add Up one level row
    parent_folder = os.path.abspath(os.path.join(folder, '..'))
    rows.append(
        f"<tr><td class='icon'><i class='fa fa-level-up-alt'></i></td>"
        f"<td><span class='dir-name' onclick='changeFolder(\"{html.escape(parent_folder)}\", this)'>.. (Up one level)</span></td>"
        f"<td></td><td></td><td></td><td></td><td></td></tr>"
    )

    for item in items:
        full = os.path.join(folder, item)
        try:
            st = os.lstat(full)
            size = st.st_size if os.path.isfile(full) else "-"
            # Use creation time where possible, fallback to modified time
            try:
                created = st.st_ctime
            except Exception:
                created = st.st_mtime
            created_str = time.strftime("%Y/%m/%d", time.localtime(created))
            try:
                owner = pwd.getpwuid(st.st_uid).pw_name
                group = grp.getgrgid(st.st_gid).gr_name
                ownergrp = f"{owner}:{group}"
            except Exception:
                ownergrp = f"{st.st_uid}:{st.st_gid}"
            is_dir = os.path.isdir(full)
            icon = '<i class="fa fa-folder"></i>' if is_dir else '<i class="fa fa-file"></i>'
            name_class = "dir-name" if is_dir else "file-name"
            hash_val = "-"
            if not is_dir:
                try:
                    with open(full, "rb") as f:
                        data = f.read()
                        if hash_alg == "sha1":
                            hash_val = hashlib.sha1(data).hexdigest()
                        elif hash_alg == "sha224":
                            hash_val = hashlib.sha224(data).hexdigest()
                        elif hash_alg == "sha256":
                            hash_val = hashlib.sha256(data).hexdigest()
                        elif hash_alg == "sha384":
                            hash_val = hashlib.sha384(data).hexdigest()
                        elif hash_alg == "sha512":
                            hash_val = hashlib.sha512(data).hexdigest()
                        else:
                            hash_val = hashlib.md5(data).hexdigest()
                except Exception:
                    hash_val = "-"
            size_str = "-" if size == "-" else "{:.2f}".format(float(size)/1024/1024)
            name_display = f'<span class="{name_class}" onclick="{"changeFolder" if is_dir else "viewFile"}(\'{html.escape(full)}\', this)">{html.escape(item) + ("/" if is_dir else "")}</span>'
            dl = f'<a class="download-link" href="/download?file={html.escape(full)}" onclick="event.stopPropagation()">Download</a>' if not is_dir else ''
            rows.append(
                f"<tr>"
                f"<td class='icon'>{icon}</td>"
                f"<td>{name_display}</td>"
                f"<td class='ownergrp'>{ownergrp}</td>"
                f"<td class='size'>{size_str}</td>"
                f"<td class='hash'>{hash_val}</td>"
                f"<td class='time'>{created_str}</td>"
                f"<td>{dl}</td>"
                f"</tr>"
            )
        except Exception as e:
            rows.append(f"<tr><td colspan='7' class='upload-error'>{html.escape(str(e))}</td></tr>")

    header = ("<tr>"
              "<th></th>"
              "<th>Name</th>"
              "<th>Owner:Group</th>"
              "<th>Size (MB)</th>"
              "<th>Hash</th>"
              "<th>Date Created</th>"
              "<th></th>"
              "</tr>")
    return f"""
    <div style="margin-bottom: 8px;">
      <input type="search" id="searchBox" oninput="filterFiles()" placeholder="Search files or folders...">
    </div>
    <table class="files-table" id="fileTable">{header}{''.join(rows)}</table>
    """

def render_table_card(folder, hash_alg, show_hidden):
    return f'''
    <div class="table-card" id="mainTableCard">
      {get_file_table_html(folder, hash_alg, show_hidden)}
    </div>
    '''

# ====================== MAIN HTML TEMPLATE ===================
MAIN_TEMPLATE = lambda pid, hash_alg, show_hidden: f"""<!DOCTYPE html>
<html lang="en"><head>
<title>DarkEntropy File Share</title>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
{CYBER_CSS}
</head>
<body>
<div class="sticky-bar">
  <div class="nav-main">
    <div class="title">DarkEntropy File Share</div>
    <div class="subtitle">Your local network file share – cyber styled</div>
    {upload_header_row_html(pid, hash_alg)}
  </div>
  <div class="hr"></div>
</div>
<div class="card-wrap">
  {upload_drawer_html()}
  {render_table_card('.', hash_alg, show_hidden)}
</div>
<div id="file-modal" style="display:none;">
  <div class="modal-content">
    <span class="modal-close" title="Close">&times;</span>
    <div id="fileModalContent" style="max-height:63vh;overflow-y:auto;font-family:monospace;white-space:pre-wrap;">File...</div>
  </div>
</div>
<div class="copyright">Copyright &copy; DarkEntropy.org</div>
<script>
// SPA vars
let curFolder = '.';
let curHash = '{hash_alg}';

// Upload drawer toggle
function toggleUploadDrawer() {{
  let el = document.getElementById("uploadDrawer");
  el.classList.toggle("open");
  setTimeout(() => el.scrollIntoView({{behavior:"smooth"}}), 200);
}}

// Change hash algo
function changeHash(h) {{
  curHash = h;
  reloadTable();
}}

// Change folder
function changeFolder(folder, el) {{
  curFolder = folder;
  reloadTable();
}}

// Reload file table
function reloadTable() {{
  fetch(`/list?folder=${{encodeURIComponent(curFolder)}}&hash=${{curHash}}&showHidden=false`)
    .then(r => r.text())
    .then(html => {{
      document.getElementById("mainTableCard").outerHTML = html;
    }});
}}

// View file contents modal
function viewFile(file, el) {{
  fetch(`/viewfile?file=${{encodeURIComponent(file)}}`)
    .then(r => r.text())
    .then(txt => {{
      showModal(txt);
    }});
}}

// Show modal
function showModal(content) {{
  let modal = document.getElementById('file-modal');
  document.getElementById('fileModalContent').innerText = content;
  modal.style.display = 'flex';
}}

// Close modal handlers
document.addEventListener('DOMContentLoaded', () => {{
  document.querySelector('.modal-close').onclick = () => document.getElementById('file-modal').style.display = 'none';
}});
window.onclick = function(e) {{
  let m = document.getElementById('file-modal');
  if (e.target == m) m.style.display = 'none';
}};

// Upload handling
document.addEventListener('DOMContentLoaded', () => {{
  const form = document.getElementById('uploadForm');
  const fileInput = document.getElementById('fileInput');
  const uploadStatus = document.getElementById('uploadStatus');
  const uploadZone = document.getElementById('uploadZone');

  form.onsubmit = e => {{
    e.preventDefault();
    let data = new FormData(form);
    data.set('folder', curFolder);
    fetch('/upload', {{method: "POST", body: data}})
      .then(r => r.text())
      .then(msg => {{
        uploadStatus.innerText = msg;
        reloadTable();
      }})
      .catch(() => uploadStatus.innerText = 'Upload failed.');
  }};
  fileInput.onchange = () => form.requestSubmit();

  // Drag & drop support
  uploadZone.ondragover = e => {{ e.preventDefault(); uploadZone.classList.add('dragover'); }};
  uploadZone.ondragleave = e => {{ uploadZone.classList.remove('dragover'); }};
  uploadZone.ondrop = e => {{
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    fileInput.files = e.dataTransfer.files;
    form.requestSubmit();
  }};
}});

// Filter search table
function filterFiles() {{
  let q = document.getElementById("searchBox").value.toLowerCase();
  let rows = document.querySelectorAll("#fileTable tr");
  for (let i=1; i<rows.length; i++) {{
    let t = rows[i].innerText.toLowerCase();
    rows[i].style.display = t.indexOf(q) >= 0 ? "" : "none";
  }}
}}

// Table row hover highlight
document.addEventListener("mouseover", e => {{
  let r = e.target.closest("tr");
  if (r && r.parentNode.tagName == "TBODY") r.classList.add("row-highlight");
}});
document.addEventListener("mouseout", e => {{
  let r = e.target.closest("tr");
  if (r && r.parentNode.tagName == "TBODY") r.classList.remove("row-highlight");
}});
</script>
</body></html>
"""

# ========== HTTP SERVER CLASS ==========

class DarkEntropyFileServerHandler(http.server.SimpleHTTPRequestHandler):
    server_version = "DarkEntropyFileServer/1.8"
    show_hidden = False  # set by CLI option

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query = parse_qs(parsed_path.query)
        if path == '/' or path == '/index.html':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(MAIN_TEMPLATE(os.getpid(), DEFAULT_HASH, self.show_hidden).encode('utf-8'))
            return
        elif path == '/list':
            folder = query.get('folder', ['.'])[0]
            hash_alg = query.get('hash', [DEFAULT_HASH])[0].lower()
            show_hidden = query.get('showHidden', ['false'])[0].lower() == 'true' or self.show_hidden
            html_fragment = render_table_card(folder, hash_alg, show_hidden)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html_fragment.encode('utf-8'))
            return
        elif path == '/viewfile':
            file_path = query.get('file', [None])[0]
            if file_path:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(content.encode('utf-8'))
                except Exception as e:
                    self.send_error(404, f"File not found or error: {e}")
            else:
                self.send_error(400, "File parameter missing")
            return
        elif path == '/download':
            file_path = query.get('file', [None])[0]
            if file_path and os.path.isfile(file_path):
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(file_path)}"')
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                except Exception as e:
                    self.send_error(500, f"Error reading file: {e}")
            else:
                self.send_error(404, "File not found")
            return
        else:
            # fallback for favicon or other static
            if path == '/favicon.ico':
                self.send_response(404)
                self.end_headers()
                return
            # else fallback to parent
            super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == "/upload":
            ctype, pdict = cgi.parse_header(self.headers.get('content-type'))
            if ctype == 'multipart/form-data':
                try:
                    form = cgi.FieldStorage(fp=self.rfile,
                                            headers=self.headers,
                                            environ={'REQUEST_METHOD':'POST',
                                                     'CONTENT_TYPE':self.headers['Content-Type'],})
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"Error parsing form data: {e}".encode('utf-8'))
                    return
                folder = form.getvalue("folder") or "."
                files = form["file"]
                if not isinstance(files, list):
                    files = [files]
                saved_files = []
                try:
                    os.makedirs(folder, exist_ok=True)
                    for fileitem in files:
                        if fileitem.filename:
                            filename = os.path.basename(fileitem.filename)
                            safe_path = os.path.join(folder, filename)
                            with open(safe_path, 'wb') as f:
                                shutil.copyfileobj(fileitem.file, f)
                            saved_files.append(filename)
                    msg = f"Uploaded: {', '.join(saved_files)}" if saved_files else "No files uploaded."
                except Exception as e:
                    msg = f"Upload failed: {e}"
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(msg.encode('utf-8'))
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid upload request.")
            return
        elif parsed_path.path == "/kill":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Server is shutting down...")
            threading.Thread(target=os.kill, args=(os.getpid(), signal.SIGTERM)).start()
            return
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Unsupported POST path.")
            return

def kill_pid_on_port(port):
    if platform.system() == 'Linux':
        try:
            output = subprocess.check_output(f"lsof -t -i:{port}", shell=True).decode().strip()
            pids = output.split('\n')
            for pid in pids:
                if pid.isdigit():
                    os.kill(int(pid), signal.SIGTERM)
            print(f"Killed processes on port {port}: {', '.join(pids)}")
        except Exception as e:
            print(f"Failed to kill process on port {port}: {e}")
    else:
        print("Kill by port not implemented for this OS.")

def run_server(bind_addr, port, show_hidden):
    handler = DarkEntropyFileServerHandler
    handler.show_hidden = show_hidden
    with socketserver.ThreadingTCPServer((bind_addr, port), handler) as httpd:
        sa = httpd.socket.getsockname()
        print("[DarkEntropy File Share]")
        print(f"PID: {os.getpid()}")
        print(f"Port: {sa[1]}")
        print("\nLinks:")
        print(f"  http://127.0.0.1:{sa[1]}/")
        try:
            ip = socket.gethostbyname(socket.gethostname())
            print(f"  http://{ip}:{sa[1]}/")
        except Exception:
            pass
        print(f"  http://localhost:{sa[1]}/")
        print(f"\n(Press Ctrl+C to quit or use 'kill {os.getpid()}')")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            httpd.server_close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DarkEntropy Cyber-Themed File Share Server")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="Port to bind (default 9000)")
    parser.add_argument("-b", "--bind", default="0.0.0.0", help="Address to bind (default 0.0.0.0)")
    parser.add_argument("-k", "--kill", type=int, help="Kill process using this port and exit")
    parser.add_argument("-s", "--show-hidden", action="store_true", help="Show hidden files in listings")
    args = parser.parse_args()

    if args.kill:
        kill_pid_on_port(args.kill)
        sys.exit(0)

    run_server(args.bind, args.port, args.show_hidden)
