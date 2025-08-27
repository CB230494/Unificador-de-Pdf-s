# =========================
# 🧩 Unificador de PDFs (robusto y sin límites)
# =========================
import streamlit as st
from io import BytesIO

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs (sin límite de páginas)")
st.caption("Sube varios PDFs de cualquier tamaño y descarga un único archivo combinado.")

# Import pypdf dentro de try para mostrar errores claros
try:
    from pypdf import PdfReader, PdfWriter
except Exception as e:
    st.error("No se pudo importar pypdf. Revisa la versión en requirements.txt.")
    st.exception(e)
    st.stop()

orden = st.selectbox("Orden de unión", ["Orden de subida", "Nombre de archivo (A→Z)"])
st.divider()

files = st.file_uploader(
    "Selecciona tus PDFs",
    type=["pdf"],
    accept_multiple_files=True,
    help="Puedes seleccionar varios a la vez."
)

def contar_paginas(archivo):
    archivo.seek(0)
    reader = PdfReader(archivo)
    # Si viniera encriptado con owner-password, algunos se abren sin clave:
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")  # si no aplica, no pasa nada
        except Exception:
            pass
    return len(reader.pages)

def unir_pdfs(archivos) -> BytesIO:
    writer = PdfWriter()
    for f in archivos:
        f.seek(0)
        reader = PdfReader(f)
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                pass
        for p in reader.pages:
            writer.add_page(p)
    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out

if files:
    if orden == "Nombre de archivo (A→Z)":
        files = sorted(files, key=lambda x: x.name.lower())

    st.subheader("📄 Archivos detectados")
    total = 0
    legibles = True
    for f in files:
        try:
            n = contar_paginas(f)
            total += n
            st.write(f"• **{f.name}** — {n} pág.")
        except Exception as e:
            st.error(f"❌ No se pudo leer **{f.name}**")
            with st.expander(f"Ver detalle de error de {f.name}"):
                st.exception(e)
            legibles = False

    st.divider()
    btn = st.button("🔗 Unir PDFs", use_container_width=True, disabled=(not legibles))
    if btn and legibles:
        try:
            combinado = unir_pdfs(files)
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
                st.write(f"Páginas totales: **{total}**")
                st.write("Orden: **{}**".format("Nombre (A→Z)" if orden != "Orden de subida" else "Orden de subida"))
        except Exception as e:
            st.error("❌ Ocurrió un error al unir.")
            st.exception(e)
else:
    st.info("Sube uno o más archivos PDF para comenzar.")



