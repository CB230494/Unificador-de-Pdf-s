# =========================
# 🧩 Unificador de PDFs grandes
# - Ingesta uno-a-uno (derrame a disco)
# - Merge incremental en disco (muy baja RAM)
# - Descarga fraccionada + manifest SHA-256 + scripts de recombinación
# =========================
import streamlit as st
import tempfile, os, shutil, gc, hashlib
from typing import List, Tuple

st.set_page_config(page_title="Unificador de PDFs grandes", layout="centered")
st.title("🧩 Unificar PDFs grandes (ultra ahorro de memoria)")
st.caption("Sube cada PDF por separado con “Agregar”. Se guarda en disco, se libera RAM y luego se unen incrementalmente.")

# ---------- Dependencias ----------
try:
    import pikepdf
except Exception as e:
    st.error("No se pudo importar pikepdf. Revisa requirements.txt.")
    st.exception(e); st.stop()

# ---------- Utilidades de sistema ----------
def fs_free_mb(path: str = ".") -> float:
    """Espacio libre aproximado del filesystem (MB)."""
    try:
        stat = os.statvfs(path)
        return (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
    except Exception:
        return 0.0

def pretty_size(path: str) -> str:
    b = os.path.getsize(path)
    mb = b / (1024 * 1024)
    return f"{mb:.1f} MB"

def save_uploaded_to_disk(uf) -> str:
    """Vuelca un UploadedFile a disco por chunks (no ocupa toda la RAM)."""
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

# ---------- Merge ----------
def merge_incremental(paths: List[str]) -> str:
    """
    Une N PDFs creando un intermedio por paso.
    Máx. 2 PDFs abiertos a la vez. Guarda sin recomprimir/linearizar -> menos RAM/CPU.
    """
    base = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); base.close()
    shutil.copyfile(paths[0], base.name)
    current = base.name
    for path in paths[1:]:
        nxt = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); nxt.close()
        with pikepdf.open(current) as dst, pikepdf.open(path) as src:
            dst.pages.extend(src.pages)
            dst.save(nxt.name)  # guardar "tal cual" para ahorrar recursos
        try: os.remove(current)
        except Exception: pass
        current = nxt.name
        gc.collect()
    return current  # ruta final

def merge_two(a_path: str, b_path: str) -> str:
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); out.close()
    with pikepdf.open(a_path) as dst, pikepdf.open(b_path) as src:
        dst.pages.extend(src.pages)
        dst.save(out.name)
    gc.collect()
    return out.name

# ---------- Descarga fraccionada + verificación ----------
def split_file(path_local: str, part_size_mb: int, prog_cb=None) -> List[str]:
    """Divide un archivo grande en partes ~part_size_mb MB sin cargarlo a RAM."""
    part_paths = []
    part_bytes = part_size_mb * 1024 * 1024
    total = os.path.getsize(path_local)
    done = 0
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
            if prog_cb:
                prog_cb(min(done / total, 1.0))
            idx += 1
    return part_paths

def sha256_of(path: str, bufsize: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def make_join_scripts(base_name: str, parts_count: int) -> Tuple[bytes, bytes]:
    parts = [f"{base_name}.part{idx:02d}" for idx in range(1, parts_count + 1)]
    bat = "@echo off\r\necho Recombinar partes en unificado.pdf\r\ncopy /b " + " + ".join(parts) + " unificado.pdf\r\n"
    sh  = "#!/bin/sh\necho \"Recombinar partes en unificado.pdf\"\ncat " + " ".join(parts) + " > unificado.pdf\n"
    return bat.encode("utf-8"), sh.encode("utf-8")

def build_manifest(parts: list) -> bytes:
    """Manifest de verificación: <nombre_parte>  <sha256>."""
    lines = [f"{os.path.basename(p)}  {sha256_of(p)}" for p in parts]
    lines.insert(0, "# Archivo: unificado.pdf\n# Formato: <nombre_parte>  <sha256>\n")
    return ("\n".join(lines) + "\n").encode("utf-8")

# ---------- Estado ----------
if "paths" not in st.session_state: st.session_state.paths = []
if "names" not in st.session_state: st.session_state.names = []

# ---------- Info de entorno ----------
st.caption(f"🔧 Límite actual por archivo: {st.get_option('server.maxUploadSize')} MB")
st.info(f"💾 Espacio libre aprox. en disco temporal: **{fs_free_mb():.0f} MB**")

# ============ 1) Ingesta UNO-A-UNO ============
st.markdown("### 1) Agregar archivos (uno por vez)")
uploader = st.file_uploader("Selecciona un PDF y pulsa **Agregar**", type=["pdf"], accept_multiple_files=False)

col_up1, col_up2 = st.columns([1,1])
with col_up1:
    add = st.button("➕ Agregar", disabled=(uploader is None), use_container_width=True)
with col_up2:
    clear = st.button("🧹 Limpiar lista", disabled=(len(st.session_state.paths) == 0), use_container_width=True)

if add and uploader is not None:
    try:
        path = save_uploaded_to_disk(uploader)
        st.session_state.paths.append(path)
        st.session_state.names.append(uploader.name)
        st.toast(f"Agregado: {uploader.name}", icon="✅")
        st.rerun()  # libera memoria del uploader
    except Exception as e:
        st.error("Error al guardar el archivo en disco.")
        st.exception(e)

if clear and st.session_state.paths:
    try:
        for p in st.session_state.paths:
            if os.path.exists(p): os.remove(p)
    except Exception:
        pass
    st.session_state.paths = []
    st.session_state.names = []
    st.toast("Lista vaciada y temporales borrados.", icon="🧼")
    st.rerun()

if st.session_state.paths:
    st.markdown("### Archivos preparados en disco")
    for nm, p in zip(st.session_state.names, st.session_state.paths):
        st.write(f"• **{nm}** — {pretty_size(p)}")

# ============ 2) Unir ============
st.divider()
st.markdown("### 2) Unir archivos")
col_merge1, col_merge2 = st.columns([1,1])
with col_merge1:
    unir = st.button("🔗 Unir todo (incremental)", disabled=(len(st.session_state.paths) < 2), use_container_width=True)
with col_merge2:
    unir_22 = st.button("🪫 Plan B: 2+2→1", disabled=(len(st.session_state.paths) != 4), use_container_width=True)

def finalize_download(out_path: str):
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    st.success(f"PDF combinado generado. Tamaño: **{size_mb:.1f} MB**")

    BIG_THRESHOLD = 300  # umbral para ocultar descarga completa

    if size_mb <= BIG_THRESHOLD:
        with open(out_path, "rb") as fh:
            st.download_button("⬇️ Descargar PDF completo",
                               data=fh, file_name="unificado.pdf",
                               mime="application/pdf", use_container_width=True)
        st.info("Si tu navegador falla con el archivo completo, usa la descarga fraccionada abajo.")
    else:
        st.warning("El archivo es muy grande; usa **descarga fraccionada** para evitar que el servidor se quede sin RAM.")

    # Descarga fraccionada
    st.markdown("#### 📦 Descarga fraccionada")
    part_mb = st.slider("Tamaño por parte (MB)", 50, 300, 150, 25, key="slider_parts")
    prog = st.progress(0.0)
    parts = split_file(out_path, part_mb, prog_cb=prog.progress)
    st.caption(f"Partes generadas: **{len(parts)}** × ~{part_mb} MB")

    for i, p in enumerate(parts, 1):
        with open(p, "rb") as fh:
            st.download_button(
                f"⬇️ Parte {i:02d}/{len(parts)}",
                data=fh,
                file_name=f"unificado.pdf.part{i:02d}",
                mime="application/octet-stream",
                use_container_width=True,
            )

    # Scripts y manifest
    bat, sh = make_join_scripts("unificado.pdf", len(parts))
    manifest = build_manifest(parts)

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
                           file_name="manifest_sha256.txt",
                           mime="text/plain", use_container_width=True)

    st.caption("Coloca todas las partes y el script en la misma carpeta. "
               "Windows: doble clic al .bat.  macOS/Linux: `chmod +x recombinar_unix.sh && ./recombinar_unix.sh`.")

if unir:
    try:
        out_path = merge_incremental(st.session_state.paths)
        finalize_download(out_path)
    except Exception as e:
        st.error("❌ Error al unir (incremental)."); st.exception(e)

if unir_22:
    try:
        a1, a2, b1, b2 = st.session_state.paths
        t1 = merge_incremental([a1, a2])
        t2 = merge_incremental([b1, b2])
        out_path = merge_incremental([t1, t2])
        # limpiar intermedios
        for p in [t1, t2]:
            try: os.remove(p)
            except Exception: pass
        finalize_download(out_path)
    except Exception as e:
        st.error("❌ Error en modo 2+2→1."); st.exception(e)

# ============ 3) Limpieza general ============
st.divider()
if st.button("🧹 Borrar temporales y reiniciar", use_container_width=True):
    try:
        for p in st.session_state.paths:
            if os.path.exists(p): os.remove(p)
    except Exception:
        pass
    st.session_state.paths = []; st.session_state.names = []
    st.toast("Temporales eliminados.", icon="🧼"); st.rerun()

