# =========================
# 🧩 Unificador de PDFs — ingestión uno-a-uno + merge incremental + descarga fraccionada
# =========================
import streamlit as st
import tempfile, os, shutil, gc
from typing import List, Tuple

st.set_page_config(page_title="Unificador de PDFs grandes", layout="centered")
st.title("🧩 Unificar PDFs grandes (ultra ahorro de memoria)")
st.caption("Sube cada PDF por separado con “Agregar”. Se guarda en disco, se libera RAM y luego se unen incrementalmente.")

# -------- Dependencias --------
try:
    import pikepdf
except Exception as e:
    st.error("No se pudo importar pikepdf. Revisa requirements.txt.")
    st.exception(e); st.stop()

# -------- Helpers de disco/RAM --------
def fs_free_mb(path: str = ".") -> float:
    try:
        stat = os.statvfs(path)
        return (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
    except Exception:
        return 0.0

def save_uploaded_to_disk(uf) -> str:
    """Vuelca un UploadedFile a disco por chunks (no carga todo en RAM)."""
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
    b = os.path.getsize(path)
    mb = b / (1024 * 1024)
    return f"{mb:.1f} MB"

# -------- Merge --------
def merge_incremental(paths: List[str]) -> str:
    """Une N PDFs creando un intermedio por paso (máx. 2 abiertos a la vez)."""
    base = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); base.close()
    shutil.copyfile(paths[0], base.name)
    current = base.name
    for path in paths[1:]:
        nxt = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); nxt.close()
        with pikepdf.open(current) as dst, pikepdf.open(path) as src:
            dst.pages.extend(src.pages)
            # Guardar SIN recomprimir/linearizar: menos RAM y CPU
            dst.save(nxt.name)
        try: os.remove(current)
        except Exception: pass
        current = nxt.name
        gc.collect()
    return current  # ruta final

def split_file(path_local: str, part_size_mb: int) -> List[str]:
    """Divide el archivo en partes ~N MB (no usa RAM)."""
    parts = []
    part_bytes = part_size_mb * 1024 * 1024
    with open(path_local, "rb") as f:
        i = 1
        while True:
            chunk = f.read(part_bytes)
            if not chunk:
                break
            out = f"{path_local}.part{i:02d}"
            with open(out, "wb") as o:
                o.write(chunk)
            parts.append(out)
            i += 1
    return parts

def join_scripts(base_name: str, parts_count: int) -> Tuple[bytes, bytes]:
    parts = [f"{base_name}.part{i:02d}" for i in range(1, parts_count + 1)]
    bat = "@echo off\r\necho Recombinar partes en unificado.pdf\r\ncopy /b " + " + ".join(parts) + " unificado.pdf\r\n"
    sh  = "#!/bin/sh\necho \"Recombinar partes en unificado.pdf\"\ncat " + " ".join(parts) + " > unificado.pdf\n"
    return bat.encode("utf-8"), sh.encode("utf-8")

# -------- Estado --------
if "paths" not in st.session_state: st.session_state.paths = []
if "names" not in st.session_state: st.session_state.names = []

st.info(f"Espacio libre aprox. en disco temporal: **{fs_free_mb():.0f} MB**")

# ===== 1) Ingesta UNO-A-UNO =====
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
        # Liberar memoria del uploader reiniciando la vista
        st.rerun()
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

# Lista de archivos preparados
if st.session_state.paths:
    st.markdown("### Archivos preparados en disco")
    for nm, p in zip(st.session_state.names, st.session_state.paths):
        st.write(f"• **{nm}** — {pretty_size(p)}")

# ===== 2) Unir =====
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

    # Descarga directa completa SOLO si el tamaño es razonable (< 350 MB)
    if size_mb <= 350:
        with open(out_path, "rb") as fh:
            st.download_button("⬇️ Descargar PDF completo", data=fh, file_name="unificado.pdf",
                               mime="application/pdf", use_container_width=True)
    else:
        st.warning("El archivo es muy grande; usa **descarga fraccionada** para evitar que el servidor se quede sin RAM.")

    # Descarga fraccionada (recomendada para tamaños grandes)
    st.markdown("#### 📦 Descarga fraccionada")
    part_mb = st.slider("Tamaño por parte (MB)", 50, 300, 150, 25, key="slider_parts")
    parts = split_file(out_path, part_mb)
    st.caption(f"Partes generadas: **{len(parts)}** × ~{part_mb} MB")

    for i, p in enumerate(parts, 1):
        with open(p, "rb") as fh:
            st.download_button(f"⬇️ Parte {i:02d}/{len(parts)}",
                               data=fh, file_name=f"unificado.pdf.part{i:02d}",
                               mime="application/octet-stream", use_container_width=True)

    bat, sh = join_scripts("unificado.pdf", len(parts))
    colA, colB = st.columns(2)
    with colA:
        st.download_button("🪟 Recombinar (Windows .bat)", data=bat,
                           file_name="recombinar_windows.bat", mime="application/octet-stream", use_container_width=True)
    with colB:
        st.download_button("🐧 Recombinar (macOS/Linux .sh)", data=sh,
                           file_name="recombinar_unix.sh", mime="text/x-shellscript", use_container_width=True)
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
        # limpia intermedios
        for p in [t1, t2]:
            try: os.remove(p)
            except Exception: pass
        finalize_download(out_path)
    except Exception as e:
        st.error("❌ Error en modo 2+2→1."); st.exception(e)

# ===== 3) Limpieza general =====
st.divider()
if st.button("🧹 Borrar temporales y reiniciar", use_container_width=True):
    try:
        for p in st.session_state.paths:
            if os.path.exists(p): os.remove(p)
    except Exception:
        pass
    st.session_state.paths = []; st.session_state.names = []
    st.toast("Temporales eliminados.", icon="🧼"); st.rerun()

