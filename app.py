# =========================
# 🧩 Unificador de PDFs — pypdf 6.0.0
# =========================
import streamlit as st
from io import BytesIO

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs (sin límite de páginas)")
st.caption("Sube varios PDFs con cualquier cantidad de páginas y genera un único archivo combinado.")

# Importaciones correctas para pypdf 6.0.0
try:
    from pypdf import PdfReader, PdfMerger
except Exception as e:
    st.error("❌ Error al importar pypdf.")
    st.exception(e)
    st.stop()

# ---------- Opciones ----------
orden = st.selectbox("Orden de unión", ["Orden de subida", "Nombre de archivo (A→Z)"])
st.divider()

files = st.file_uploader(
    "Selecciona tus PDFs",
    type=["pdf"],
    accept_multiple_files=True,
    help="Puedes seleccionar varios a la vez."
)

def contar_paginas(file) -> int:
    file.seek(0)
    reader = PdfReader(file, strict=False)
    return len(reader.pages)

def unir_pdfs(archivos) -> BytesIO:
    merger = PdfMerger(strict=False)
    for f in archivos:
        f.seek(0)
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
            st.error(f"❌ No se pudo leer **{f.name}**")
            st.exception(e)
            legibles = False

    st.divider()
    if st.button("🔗 Unir PDFs", use_container_width=True, disabled=(not legibles)):
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
                st.write(f"Páginas totales: **{total_pag}**")
                st.write("Orden aplicado: **{}**".format("Nombre (A→Z)" if orden != "Orden de subida" else "Orden de subida"))
        except Exception as e:
            st.error("❌ Ocurrió un error al unir.")
            st.exception(e)
else:
    st.info("Sube uno o más archivos PDF para comenzar.")
