# =========================
# 🧩 Unificador de PDFs (grandes) — merge incremental y disco
# =========================
import streamlit as st
import tempfile, os, shutil
from io import BytesIO
from typing import List

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs grandes (modo ahorro de memoria)")
st.caption("Optimizado para 150–300 MB por PDF: derrama a disco, une incrementalmente y descarga en streaming.")

# ---------- Dependencias ----------
try:
    import pikepdf
except Exception as e:
    st.error("No se pudo importar pikepdf. Revisa requirements.txt.")
    st.exception(e)
    st.stop()

# Mostrar el límite actual para confirmar la config cargada
limite = st.get_option("server.maxUploadSize")
st.caption(f"🔧 Límite actual por archivo: {limite} MB")

# ---------- Opciones ----------
c1, c2 = st.columns(2)
with c1:
    ordenar = st.selectbox("Orden de unión", ["Orden de subida", "Nombre de archivo (A→Z)"])
with c2:
    ultra_ahorro = st.toggle("Ultra-ahorro (no contar páginas)", value=True,
        help="Evita leer cada PDF para contar páginas. Recomendado para archivos muy grandes.")

st.divider()

# ---------- Subida ----------
files = st.file_uploader("Selecciona tus PDFs", type=["pdf"], accept_multiple_files=True)

# Guardamos a disco y borramos el objeto en memoria (reiniciando la sesión)
def _save_uploaded_files_to_disk(uploaded_files) -> List[str]:
    paths = []
    prog = st.progress(0.0)
    for i, uf in enumerate(uploaded_files, start=1):
        # Nombre temporal estable
        suffix = os.path.splitext(uf.name)[1].lower() or ".pdf"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        # Copia por chunks para no cargar el archivo entero en RAM
        uf.seek(0)
        while True:
            chunk = uf.read(10 * 1024 * 1024)  # 10 MB
            if not chunk:
                break
            tmp.write(chunk)
        tmp.flush()
        tmp.close()
        paths.append(tmp.name)
        prog.progress(i / len(uploaded_files))
    return paths

# Merge incremental: sólo 2 PDFs en memoria a la vez
def merge_incremental(paths: List[str]) -> str:
    assert len(paths) >= 1
    # Copiamos el primero a un temporal base
    base = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    base.close()
    shutil.copyfile(paths[0], base.name)
    current = base.name

    for idx, path in enumerate(paths[1:], start=2):
        nxt = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        nxt.close()
        # Abrimos base + siguiente, extendemos páginas y guardamos a nuevo archivo
        with pikepdf.open(current) as dst, pikepdf.open(path) as src:
            dst.pages.extend(src.pages)
            dst.save(
                nxt.name,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                linearize=True,
            )
        # Limpiamos archivo base anterior
        try:
            os.remove(current)
        except Exception:
            pass
        current = nxt.name
        st.progress(idx / len(paths))
    return current  # ruta final

# ---------- Estado de sesión ----------
if "temp_paths" not in st.session_state:
    st.session_state.temp_paths = None  # lista de rutas en disco
if "names" not in st.session_state:
    st.session_state.names = None

# Paso 1: preparar (derramar a disco y liberar memoria de uploader)
prep = st.button("📦 Preparar archivos (derramar a disco)", disabled=not files, use_container_width=True)
if prep and files:
    try:
        if ordenar == "Nombre de archivo (A→Z)":
            files = sorted(files, key=lambda x: x.name.lower())
        temp_paths = _save_uploaded_files_to_disk(files)
        st.session_state.temp_paths = temp_paths
        st.session_state.names = [f.name for f in files]
        # Limpiamos el uploader del estado para liberar memoria
        st.toast("Archivos preparados en disco. Reiniciando para liberar memoria…", icon="✅")
        st.rerun()
    except Exception as e:
        st.error("Error preparando archivos.")
        st.exception(e)

# Paso 2: mostrar lista preparada (ya sin UploadedFile en RAM)
if st.session_state.temp_paths:
    st.subheader("📄 Archivos listos para unir")
    for nm, p in zip(st.session_state.names, st.session_state.temp_paths):
        size_mb = os.path.getsize(p) / (1024 * 1024)
        st.write(f"• **{nm}** — {size_mb:.1f} MB")

    total_pag = None
    if not ultra_ahorro:
        # (Opcional) contar páginas con pikepdf (puede ser costoso)
        try:
            total_pag = 0
            for p in st.session_state.temp_paths:
                with pikepdf.open(p) as pdf:
                    total_pag += len(pdf.pages)
            st.caption(f"Páginas totales (aprox.): {total_pag}")
        except Exception as e:
            st.warning("No se pudieron contar páginas (modo ahorro sugerido).")
            st.exception(e)

    st.divider()
    if st.button("🔗 Unir PDFs (merge incremental)", use_container_width=True):
        try:
            prog = st.progress(0.0)
            status = st.empty()
            status.write("Unificando…")
            out_path = merge_incremental(st.session_state.temp_paths)
            prog.progress(1.0)
            status.write("Completado ✅")

            st.success("PDF combinado generado correctamente.")
            with open(out_path, "rb") as fh:
                st.download_button(
                    "⬇️ Descargar PDF Unificado",
                    data=fh, file_name="unificado.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

            with st.expander("📋 Resumen"):
                st.write(f"Archivos unidos: **{len(st.session_state.temp_paths)}**")
                if total_pag is not None:
                    st.write(f"Páginas totales (aprox.): **{total_pag}**")
                st.write(f"Orden aplicado: **{'Nombre (A→Z)' if ordenar != 'Orden de subida' else 'Orden de subida'}**")

            # Botón de limpieza de temporales
            if st.button("🧹 Borrar temporales", help="Libera espacio en disco", use_container_width=True):
                try:
                    for p in st.session_state.temp_paths:
                        if os.path.exists(p):
                            os.remove(p)
                    if os.path.exists(out_path):
                        os.remove(out_path)
                except Exception:
                    pass
                st.session_state.temp_paths = None
                st.session_state.names = None
                st.toast("Temporales eliminados.", icon="🧼")
                st.rerun()

        except Exception as e:
            st.error("❌ Ocurrió un error al unir.")
            st.exception(e)
else:
    st.info("Sube y luego pulsa **Preparar archivos** para derramar a disco antes de unir.")

