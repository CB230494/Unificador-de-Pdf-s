# =========================
# 🧩 Unificador de PDFs grandes — fusión al vuelo + descarga fraccionada
# =========================
import streamlit as st
import tempfile, os, gc, hashlib
from typing import List, Tuple

st.set_page_config(page_title="Unificador de PDFs grandes", layout="centered")
st.title("🧩 Unificar PDFs grandes (ultra ahorro de memoria)")
st.caption("Agrega cada PDF por separado. Se fusiona al vuelo en disco y se libera memoria de inmediato.")

# -------- Dependencias --------
try:
    import pikepdf
except Exception as e:
    st.error("No se pudo importar pikepdf. Revisa requirements.txt.")
    st.exception(e); st.stop()

# -------- Utilidades --------
def fs_free_mb(path: str = ".") -> float:
    try:
        stat = os.statvfs(path)
        return (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
    except Exception:
        return 0.0

def save_uploaded_to_disk(uf) -> str:
    """Vuelca un UploadedFile a disco por chunks (sin ocupar toda la RAM)."""
    suffix = os.path.splitext(uf.name)[1].lower() or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    uf.seek(0)
    while True:
        chunk = uf.read(8 * 1024 * 1024)  # 8 MB
        if not chunk:
            break
        tmp.write(chunk)
    tmp.flush(); tmp.close()
    return tmp.name

def pretty_size(path: str) -> str:
    mb = os.path.getsize(path) / (1024 * 1024)
    return f"{mb:.1f} MB"

def merge_two(a_path: str, b_path: str) -> str:
    """Une exactamente dos PDFs en disco, manteniendo 2 abiertos a la vez."""
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); out.close()
    with pikepdf.open(a_path) as dst, pikepdf.open(b_path) as src:
        dst.pages.extend(src.pages)
        # Guardar 'tal cual' (sin recomprimir/linearizar) -> menos RAM/CPU
        dst.save(out.name)
    gc.collect()
    return out.name

def split_file(path_local: str, part_size_mb: int, prog_cb=None) -> List[str]:
    """Divide un archivo grande en partes ~part_size_mb MB sin cargarlo a RAM."""
    part_paths = []
    part_bytes = part_size_mb * 1024 * 1024
    total = os.path.getsize(path_local); done = 0
    with open(path_local, "rb") as f:
        idx = 1
        while True:
            chunk = f.read(part_bytes)
            if not chunk:
                break
            part_path = f"{path_local}.part{idx:02d}"
            with open(part_path, "wb") as o:
                o.write(chunk)
            part_paths.append(part_path)
            done += len(chunk)
            if prog_cb: prog_cb(min(done / total, 1.0))
            idx += 1
    return part_paths

def sha256_of(path: str, bufsize: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b: break
            h.update(b)
    return h.hexdigest()

def make_join_scripts(base_name: str, parts_count: int) -> Tuple[bytes, bytes]:
    parts = [f"{base_name}.part{idx:02d}" for idx in range(1, parts_count + 1)]
    bat = "@echo off\r\necho Recombinar partes en unificado.pdf\r\ncopy /b " + " + ".join(parts) + " unificado.pdf\r\n"
    sh  = "#!/bin/sh\necho \"Recombinar partes en unificado.pdf\"\ncat " + " ".join(parts) + " > unificado.pdf\n"
    return bat.encode("utf-8"), sh.encode("utf-8")

def build_manifest(parts: list) -> bytes:
    lines = [f"{os.path.basename(p)}  {sha256_of(p)}" for p in parts]
    lines.insert(0, "# Archivo: unificado.pdf\n# Formato: <nombre_parte>  <sha256>\n")
    return ("\n".join(lines) + "\n").encode("utf-8")

# -------- Estado --------
if "accum_path" not in st.session_state: st.session_state.accum_path = None   # PDF acumulado actual (en disco)
if "added_names" not in st.session_state: st.session_state.added_names = []   # nombres agregados
if "part_paths" not in st.session_state: st.session_state.part_paths = []     # partes generadas

# -------- Info de entorno --------
st.caption(f"🔧 Límite por archivo: {st.get_option('server.maxUploadSize')} MB")
st.info(f"💾 Espacio libre aprox. en disco temporal: **{fs_free_mb():.0f} MB**")

# ============ 1) Agregar PDFs (uno por vez, fusiones al vuelo) ============
st.markdown("### 1) Agregar y fusionar al vuelo")
uploader = st.file_uploader("Selecciona un PDF y pulsa **Agregar**", type=["pdf"], accept_multiple_files=False)

col1, col2, col3 = st.columns([1,1,1])
with col1:
    add = st.button("➕ Agregar (fusionar)", disabled=(uploader is None), use_container_width=True)
with col2:
    reset = st.button("🔄 Reiniciar todo", use_container_width=True)
with col3:
    borrar_partes = st.button("🧹 Borrar partes generadas", disabled=(len(st.session_state.part_paths)==0), use_container_width=True)

if reset:
    # Borra todo (acumulado + partes)
    try:
        if st.session_state.accum_path and os.path.exists(st.session_state.accum_path):
            os.remove(st.session_state.accum_path)
        for p in st.session_state.part_paths:
            if os.path.exists(p): os.remove(p)
    except Exception:
        pass
    st.session_state.accum_path = None
    st.session_state.added_names = []
    st.session_state.part_paths = []
    st.toast("Estado reiniciado y temporales borrados.", icon="🧼")
    st.rerun()

if borrar_partes and st.session_state.part_paths:
    try:
        for p in st.session_state.part_paths:
            if os.path.exists(p): os.remove(p)
    except Exception:
        pass
    st.session_state.part_paths = []
    st.toast("Partes eliminadas.", icon="🧽")
    st.rerun()

if add and uploader is not None:
    try:
        new_path = save_uploaded_to_disk(uploader)  # derrama a disco
        if st.session_state.accum_path is None:
            # primer archivo => pasa a ser el acumulado
            st.session_state.accum_path = new_path
        else:
            # fusionar acumulado + nuevo -> nuevo acumulado
            new_accum = merge_two(st.session_state.accum_path, new_path)
            # borrar viejo acumulado y el recién subido para liberar espacio
            try:
                if os.path.exists(st.session_state.accum_path): os.remove(st.session_state.accum_path)
                if os.path.exists(new_path): os.remove(new_path)
            except Exception:
                pass
            st.session_state.accum_path = new_accum
        st.session_state.added_names.append(uploader.name)
        st.toast(f"Fusionado: {uploader.name}", icon="✅")
        st.rerun()  # libera memoria del uploader
    except Exception as e:
        st.error("Error al fusionar el archivo.")
        st.exception(e)

# Lista de archivos agregados y tamaño actual
st.markdown("#### Archivos agregados")
if st.session_state.added_names:
    for i, nm in enumerate(st.session_state.added_names, 1):
        st.write(f"{i}. **{nm}**")
else:
    st.write("_Todavía no agregaste archivos._")

if st.session_state.accum_path:
    st.success(f"📦 Tamaño actual del acumulado: **{pretty_size(st.session_state.accum_path)}**")
else:
    st.info("Cuando agregues el primer PDF, se creará el acumulado aquí.")

# ============ 2) Descargar (entero o fraccionado) ============
st.divider()
st.markdown("### 2) Descargar resultado")

if st.session_state.accum_path and os.path.exists(st.session_state.accum_path):
    size_mb = os.path.getsize(st.session_state.accum_path) / (1024 * 1024)
    st.caption(f"Tamaño actual: **{size_mb:.1f} MB**")

    BIG_THRESHOLD = 300  # umbral para ocultar descarga completa si es muy grande

    # Descarga completa (solo si no es gigantesco)
    if size_mb <= BIG_THRESHOLD:
        with open(st.session_state.accum_path, "rb") as fh:
            st.download_button("⬇️ Descargar PDF completo",
                               data=fh, file_name="unificado.pdf",
                               mime="application/pdf", use_container_width=True)
        st.info("Si falla la descarga completa, usa la descarga fraccionada.")
    else:
        st.warning("El archivo es grande; usa **descarga fraccionada** para evitar cortes por memoria.")

    # Descarga fraccionada
    st.markdown("#### 📦 Descarga fraccionada")
    part_mb = st.slider("Tamaño por parte (MB)", 50, 300, 150, 25)
    gen_parts = st.button("✂️ Generar partes", use_container_width=True)

    if gen_parts:
        try:
            prog = st.progress(0.0)
            parts = split_file(st.session_state.accum_path, part_mb, prog_cb=prog.progress)
            st.session_state.part_paths = parts

            # Una vez creadas TODAS las partes, borra el original para liberar espacio
            try:
                os.remove(st.session_state.accum_path)
            except Exception:
                pass
            st.session_state.accum_path = None
            st.toast("Partes generadas y original eliminado para liberar espacio.", icon="📦")
            st.rerun()
        except Exception as e:
            st.error("Error al generar partes."); st.exception(e)

# Mostrar botones de descarga de partes si existen
if st.session_state.part_paths:
    st.markdown("#### ⬇️ Descarga tus partes")
    for i, p in enumerate(st.session_state.part_paths, 1):
        with open(p, "rb") as fh:
            st.download_button(f"Parte {i:02d}/{len(st.session_state.part_paths)}",
                               data=fh, file_name=f"unificado.pdf.part{i:02d}",
                               mime="application/octet-stream", use_container_width=True)

    # Scripts y manifest
    bat, sh = make_join_scripts("unificado.pdf", len(st.session_state.part_paths))
    manifest = build_manifest(st.session_state.part_paths)
    colA, colB, colC = st.columns(3)
    with colA:
        st.download_button("🪟 Recombinar (Windows .bat)", data=bat,
                           file_name="recombinar_windows.bat",
                           mime="application/octet-stream", use_container_width=True)
    with colB:
        st.download_button("🐧 Recombinar (macOS/Linux .sh)", data=sh,
                           file_name="recombinar_unix.sh",
                           mime="text/x-shellscript", use_container_width=True)
    with colC:
        st.download_button("🧾 Manifest SHA-256", data=manifest,
                           file_name="manifest_sha256.txt", mime="text/plain",
                           use_container_width=True)

# ============ 3) Limpieza ============
st.divider()
if st.button("🧹 Borrar todo y reiniciar", use_container_width=True):
    try:
        if st.session_state.accum_path and os.path.exists(st.session_state.accum_path):
            os.remove(st.session_state.accum_path)
        for p in st.session_state.part_paths:
            if os.path.exists(p): os.remove(p)
    except Exception:
        pass
    st.session_state.accum_path = None
    st.session_state.added_names = []
    st.session_state.part_paths = []
    st.toast("Temporales eliminados.", icon="🧼"); st.rerun()
