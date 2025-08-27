# =========================
# 🧩 Unificador de PDFs — compatible con pypdf 6
# =========================
import streamlit as st
from io import BytesIO

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs (sin límite de páginas)")
st.caption("Sube varios PDFs con cualquier cantidad de páginas y genera un único archivo combinado.")

# Import dentro de try para mostrar errores claros si algo falla al arrancar
try:
    from pypdf import PdfReader, PdfMerger
except Exception as e:
    st.error("No se pudo importar pypdf. Verifica la versión en requirements.txt.")
    st.exception(e)
    st.stop()

# ---------- Opciones ----------
orden = st.selectbox("Orden de unión", ["Orden de subida", "Nombre de archivo (A→Z)"])
st.divider()

# ---------- Carga de archivos ----------
files = st.file_uploader(
    "Selecciona tus PDFs",
    type=["pdf"],
    accept_multiple_files=True,
    help="Puedes seleccionar varios a la vez."
)

def contar_paginas(file) -> int:
    """Devuelve el número de páginas; intenta abrir en modo laxo si está 'owner-encrypted'."""
    file.seek(0)
    reader = PdfReader(file, strict=False)
    # Si está cifrado con contraseña de usuario, lanzará error al acceder a pages
    return len(reader.pages)

def unir_con_merger(archivos) -> BytesIO:
    """Une PDFs con PdfMerger (pypdf 6), desactiva importación de marcadores para evitar bugs."""
    merger = PdfMerger(strict=False)
    for f in archivos:
        f.seek(0)
        # import_bookmarks=False evita errores por outlines corruptos
        merger.append(f, import_bookmarks=False)
    out = BytesIO()
    merger.write(out)
    merger.close()
    out.seek(0)
    return out

if files:
    if orden == "Nombre de archivo (A→Z)":
        files = sorted(files, key=lambda x: x.name.lower())

    st.subheader("📄 Archivos detectados")
    total_pag = 0
    legibles = True

    for f in files:
        try:
            n = contar_paginas(f)
            total_pag += n
            st.write(f"• **{f.name}** — {n} pág.")
        except Exception as e:
            st.error(f"❌ No se pudo leer **{f.name}** (posible PDF protegido o corrupto).")
            with st.expander(f"Ver detalle de error de {f.name}"):
                st.exception(e)
            legibles = False

    st.divider()
    unir = st.button("🔗 Unir PDFs", use_container_width=True, disabled=(not legibles))

    if unir and legibles:
        try:
            combinado = unir_con_merger(files)
            st.success("✅ PDF combinado generado correctamente.")
            st.download_button(
                "⬇️ Descargar PDF Unificado",
                data=combinado,
                file_name="unificado.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            with st.expander("📋 Resumen"):
                st.write(f"Archivos unidos: **{len(files)}**")
                st.write(f"Páginas totales: **{total_pag}**")
                st.write("Orden: **{}**".format("Nombre (A→Z)" if orden != "Orden de subida" else "Orden de subida"))
        except Exception as e:
            st.error("❌ Ocurrió un error al unir.")
            st.exception(e)
else:
    st.info("Sube uno o más archivos PDF para comenzar.")


