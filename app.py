# =========================
# 📚 Unificador de PDFs (Streamlit)
# =========================
import streamlit as st
from io import BytesIO
from pypdf import PdfReader, PdfWriter

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs")
st.caption("Sube varios PDFs (por ejemplo, cada uno de 24 páginas) y genera un único archivo combinado.")

# ---------- Opciones ----------
colA, colB = st.columns(2)
with colA:
    validar_24 = st.checkbox("Validar que cada PDF tenga 24 páginas", value=True, help="Si está activo, se detiene si algún PDF no tiene 24 páginas.")
with colB:
    ordenar = st.selectbox("Orden de unión", ["Orden de subida", "Nombre de archivo (A→Z)"])

st.divider()

# ---------- Carga de archivos ----------
files = st.file_uploader(
    "Selecciona tus PDFs",
    type=["pdf"],
    accept_multiple_files=True,
    help="Puedes seleccionar varios a la vez. Se unirán en el orden elegido arriba."
)

def _leer_paginas(f) -> int:
    reader = PdfReader(f)
    return len(reader.pages)

def _unir_pdfs(archivos) -> BytesIO:
    writer = PdfWriter()
    for af in archivos:
        af.seek(0)
        reader = PdfReader(af)
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out

if files:
    # Clonar a memoria para poder leer varias veces
    # (Streamlit sube en memoria, pero aseguramos puntero al inicio)
    for f in files:
        f.seek(0)

    # Pre-orden
    if ordenar == "Nombre de archivo (A→Z)":
        files = sorted(files, key=lambda x: x.name.lower())

    st.subheader("📄 Archivos detectados")
    ok = True
    cols = st.columns([3, 1])
    with cols[0]:
        st.markdown("**Nombre**")
    with cols[1]:
        st.markdown("**Páginas**")

    for f in files:
        # Leer conteo de páginas (sin consumir archivo)
        f.seek(0)
        try:
            n = _leer_paginas(f)
        except Exception as e:
            st.error(f"❌ No se pudo leer **{f.name}**. Detalle: {e}")
            ok = False
            continue

        c1, c2 = st.columns([3, 1])
        c1.write(f"• {f.name}")
        if validar_24 and n != 24:
            c2.error(f"{n}")
            st.error(f"El archivo **{f.name}** no tiene 24 páginas (tiene {n}).")
            ok = False
        else:
            c2.write(f"{n}")

    st.divider()

    # Botón para unir
    unir = st.button("🔗 Unir PDFs", use_container_width=True, disabled=not ok)

    if unir and ok:
        try:
            # Volver a dejar punteros al inicio por seguridad
            for f in files:
                f.seek(0)

            combinado = _unir_pdfs(files)
            nombre_salida = "unificado.pdf"

            st.success("✅ PDF combinado generado correctamente.")
            st.download_button(
                "⬇️ Descargar PDF Unificado",
                data=combinado,
                file_name=nombre_salida,
                mime="application/pdf",
                use_container_width=True
            )

            with st.expander("📋 Resumen de la unión"):
                total_paginas = 0
                for f in files:
                    f.seek(0)
                    total_paginas += _leer_paginas(f)
                st.write(f"Archivos unidos: **{len(files)}**")
                st.write(f"Páginas totales: **{total_paginas}**")
                st.write("Orden aplicado: **{}**".format("Nombre (A→Z)" if ordenar != "Orden de subida" else "Orden de subida"))
        except Exception as e:
            st.error(f"❌ Ocurrió un error al unir: {e}")
else:
    st.info("Sube uno o más archivos PDF para comenzar.")




