# =========================
# 🧩 Unificador de PDFs grandes — ultra ahorro (pikepdf + disco)
# =========================
import streamlit as st
import tempfile, os, shutil, gc
from typing import List

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs grandes (modo ultra ahorro)")
st.caption("Optimizado para archivos pesados. Derrama a disco, une incrementalmente y limpia memoria entre pasos.")

# --------- Dependencias ---------
try:
    import pikepdf
except Exception as e:
    st.error("No se pudo importar pikepdf. Revisa requirements.txt.")
    st.exception(e)
    st.stop()

# Mostrar límites para verificar config
st.caption(f"🔧 Límite actual por archivo (MB): {st.get_option('server.maxUploadSize')}")

# --------- Opciones ---------
c1, c2 = st.columns(2)
with c1:
    ordenar = st.selectbox("Orden", ["Orden de subida", "Nombre de archivo (A→Z)"])
with c2:
    conteo_paginas = st.toggle("Contar páginas (más consumo)", value=False)

st.divider()

# --------- Subida ---------
files = st.file_uploader("Selecciona tus PDFs", type=["pdf"], accept_multiple_files=True)

# ===== Utilidades =====
def to_disk(uploaded_files) -> List[str]:
    """Vuelca los UploadedFile a disco por chunks para no ocupar RAM."""
    paths = []
    if not uploaded_files:
        return paths
    prog = st.progress(0.0)
    for i, uf in enumerate(uploaded_files, 1):
        suffix = os.path.splitext(uf.name)[1].lower() or ".pdf"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        uf.seek(0)
        while True:
            chunk = uf.read(8 * 1024 * 1024)  # 8MB
            if not chunk:
                break
            tmp.write(chunk)
        tmp.flush(); tmp.close()
        paths.append(tmp.name)
        prog.progress(i / len(uploaded_files))
    return paths

def list_files(paths: List[str]) -> None:
    for p in paths:
        nm = os.path.basename(p)
        try:
            size_mb = os.path.getsize(p) / (1024 * 1024)
        except Exception:
            size_mb = 0
        st.write(f"• **{nm}** — {size_mb:.1f} MB")

def free_space_mb(path: str) -> float:
    """Espacio libre aproximado en el FS del archivo."""
    try:
        stat = os.statvfs(os.path.dirname(path) or ".")
        return (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
    except Exception:
        return 0.0

def estimate_needed_mb(paths: List[str]) -> float:
    """Estimación muy conservadora del pico de disco requerido."""
    sizes = [os.path.getsize(p) / (1024 * 1024) for p in paths]
    if not sizes:
        return 0.0
    # pico ≈ suma_actual + archivo_siguiente + margen
    return sum(sizes) + max(sizes, default=0) + 200.0  # +200MB de colchón

def merge_incremental(paths: List[str]) -> str:
    """Une N PDFs creando solo 1 intermedio por paso (máximo 2 PDFs abiertos)."""
    assert len(paths) >= 1
    base = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); base.close()
    shutil.copyfile(paths[0], base.name)
    current = base.name

    for idx, path in enumerate(paths[1:], start=2):
        nxt = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); nxt.close()
        # Abrimos base + siguiente; NO recomprimir ni linearizar (menos RAM/CPU)
        with pikepdf.open(current) as dst, pikepdf.open(path) as src:
            dst.pages.extend(src.pages)
            dst.save(nxt.name)  # guardar tal cual, sin re-empaquetar streams

        try:
            os.remove(current)
        except Exception:
            pass
        current = nxt.name
        # Limpieza agresiva
        gc.collect()
        st.caption(f"Paso {idx-1}/{len(paths)-1} listo…")

    return current

def merge_two(a_path: str, b_path: str) -> str:
    """Une exactamente dos PDFs en el disco, versión mínima."""
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); out.close()
    with pikepdf.open(a_path) as dst, pikepdf.open(b_path) as src:
        dst.pages.extend(src.pages)
        dst.save(out.name)
    gc.collect()
    return out.name

# --------- Estado ---------
if "disk_paths" not in st.session_state:
    st.session_state.disk_paths = None
if "names" not in st.session_state:
    st.session_state.names = None

# --------- Preparar (volcar a disco) ---------
prep = st.button("📦 Preparar archivos (volcar a disco)", disabled=not files, use_container_width=True)
if prep and files:
    try:
        if ordenar == "Nombre de archivo (A→Z)":
            files = sorted(files, key=lambda x: x.name.lower())
        disk_paths = to_disk(files)
        st.session_state.disk_paths = disk_paths
        st.session_state.names = [f.name for f in files]
        st.toast("Listo: archivos en disco. Reiniciando para liberar memoria…", icon="✅")
        st.rerun()
    except Exception as e:
        st.error("Error preparando archivos.")
        st.exception(e)

# --------- Mostrar y unir ---------
if st.session_state.disk_paths:
    st.subheader("📄 Archivos listos")
    list_files(st.session_state.disk_paths)

    # (Opcional) conteo
    if conteo_paginas:
        try:
            total_pag = 0
            for p in st.session_state.disk_paths:
                with pikepdf.open(p) as pdf:
                    total_pag += len(pdf.pages)
            st.caption(f"Páginas totales (aprox.): {total_pag}")
        except Exception as e:
            st.warning("No se pudieron contar páginas.")
            st.exception(e)

    # Chequeo de espacio libre
    probe = st.session_state.disk_paths[0]
    fs_free = free_space_mb(probe)
    need = estimate_needed_mb(st.session_state.disk_paths)
    if fs_free and fs_free < need:
        st.warning(f"Espacio libre aprox.: {fs_free:.0f} MB < estimado necesario {need:.0f} MB. "
                   "Podría fallar al guardar. Prueba el modo 2+2 o une en dos tandas.")

    st.divider()

    # Botón principal
    if st.button("🔗 Unir todo (incremental, muy bajo consumo)", use_container_width=True):
        try:
            out_path = merge_incremental(st.session_state.disk_paths)
            st.success("✅ PDF combinado generado.")
            with open(out_path, "rb") as fh:
                st.download_button("⬇️ Descargar PDF Unificado", data=fh, file_name="unificado.pdf",
                                   mime="application/pdf", use_container_width=True)
        except Exception as e:
            st.error("❌ Error al unir (incremental).")
            st.exception(e)

    # Plan B: 2+2→1 (útil con 4 archivos grandes)
    if len(st.session_state.disk_paths) == 4:
        st.divider()
        if st.button("🪫 Plan B: unir 2+2 y luego unir resultados", use_container_width=True):
            try:
                a1, a2, b1, b2 = st.session_state.disk_paths
                # primer par
                pA = merge_two(a1, a2)
                # segundo par
                pB = merge_two(b1, b2)
                # final
                out_path = merge_two(pA, pB)
                # limpiar intermedios
                for p in [pA, pB]:
                    try: os.remove(p)
                    except Exception: pass

                st.success("✅ PDF final generado (2+2→1).")
                with open(out_path, "rb") as fh:
                    st.download_button("⬇️ Descargar PDF Unificado (2+2)", data=fh,
                                       file_name="unificado.pdf", mime="application/pdf",
                                       use_container_width=True)
            except Exception as e:
                st.error("❌ Error en modo 2+2.")
                st.exception(e)

    # Limpieza
    st.divider()
    if st.button("🧹 Borrar temporales y reiniciar", use_container_width=True):
        try:
            for p in st.session_state.disk_paths:
                if os.path.exists(p):
                    os.remove(p)
        except Exception:
            pass
        st.session_state.disk_paths = None
        st.session_state.names = None
        st.toast("Temporales eliminados.", icon="🧼")
        st.rerun()
else:
    st.info("Sube y pulsa **Preparar archivos** para volcarlos a disco antes de unir.")

