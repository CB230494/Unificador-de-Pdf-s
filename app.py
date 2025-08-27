# =========================
# 📚 Unificador de PDFs (Streamlit) — Sin límite de páginas
# =========================
import streamlit as st
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from datetime import datetime

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs (sin límite de páginas)")
st.caption("Sube varios PDFs de cualquier cantidad de páginas y genera un único archivo combinado.")

# ---------- Opciones ----------
colA, colB = st.columns(2)
with colA:
    ordenar = st.selectbox("Orden de unión", ["Orden de subida", "Nombre de archivo (A→Z)"])
with colB:
    agregar_portada = st.checkbox("Agregar una portada automática", value=False, help="Creará una primera página simple con metadatos básicos.")

st.divider()

# ---------- Carga de archivos ----------
files = st.file_uploader(
    "Selecciona tus PDFs",
    type=["pdf"],
    accept_multiple_files=True,
    help="Puedes seleccionar varios a la vez. Se unirán en el orden elegido arriba."
)

def contar_paginas(archivo) -> int:
    archivo.seek(0)
    reader = PdfReader(archivo)
    return len(reader.pages)

def crear_portada_simple(texto: str) -> BytesIO:
    """
    Crea una portada PDF muy sencilla (una página) usando solo pypdf.
    NOTA: pypdf no 'dibuja' texto nativamente; para mantener dependencias mínimas,
    generamos una portada en blanco con metadatos y un marcador.
    Si quieres texto visible en la portada, puedo añadir reportlab opcional.
    """
    writer = PdfWriter()
    # Crear una página en blanco tamaño A4
    from pypdf.generic import RectangleObject
    A4 = RectangleObject([0, 0, 595.276, 841.89])  # 72 dpi
    writer.add_blank_page(width=A4.width, height=A4.height)

    # Metadatos (el texto de portada lo dejamos en metadata)
    writer.add_metadata({
        "/Title": "Portada",
        "/Subject": texto,
        "/Author": "Unificador de PDFs",
        "/Creator": "Streamlit + pypdf",
        "/Producer": "pypdf",
        "/CreationDate": datetime.now().strftime("D:%Y%m%d%H%M%S")
    })

    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out

def unir_pdfs(archivos, incluir_portada=False, meta_fuente=None) -> BytesIO:
    writer = PdfWriter()

    # Portada opcional
    if incluir_portada:
        portada_info = f"PDF unificado — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        portada_pdf = crear_portada_simple(portada_info)
        portada_reader = PdfReader(portada_pdf)
        for p in portada_reader.pages:
            writer.add_page(p)

    # Unir contenido
    for af in archivos:
        af.seek(0)
        reader = PdfReader(af)
        if reader.is_encrypted:
            # Intentar desencriptado "vacío" (algunos vienen con owner-password pero sin user-password)
            try:
                reader.decrypt("")  # puede o no funcionar; si no, lanzará al leer
            except Exception:
                pass

        for page in reader.pages:
            writer.add_page(page)

    # Metadatos (tomamos del primer archivo si hay)
    if meta_fuente:
        try:
            meta_fuente.seek(0)
            meta_reader = PdfReader(meta_fuente)
            md = meta_reader.metadata or {}
        except Exception:
            md = {}
        base_meta = {
            "/Title": "PDF unificado",
            "/Author": "Unificador de PDFs",
            "/Creator": "Streamlit + pypdf",
            "/Producer": "pypdf",
            "/CreationDate": datetime.now().strftime("D:%Y%m%d%H%M%S")
        }
        base_meta.update({k: str(v) for k, v in md.items() if v})
        writer.add_metadata(base_meta)

    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out

if files:
    # Orden
    if ordenar == "Nombre de archivo (A→Z)":
        files = sorted(files, key=lambda x: x.name.lower())

    st.subheader("📄 Archivos detectados")
    cols = st.columns([3, 1])
    with cols[0]:
        st.markdown("**Nombre**")
    with cols[1]:
        st.markdown("**Páginas**")

    total_pag = 0
    legibles = True
    for f in files:
        try:
            n = contar_paginas(f)
            total_pag += n
            c1, c2 = st.columns([3, 1])
            c1.write(f"• {f.name}")
            c2.write(f"{n}")
        except Exception as e:
            st.error(f"❌ No se pudo leer **{f.name}**. Detalle: {e}")
            legibles = False

    st.divider()
    unir = st.button("🔗 Unir PDFs", use_container_width=True, disabled=(not files or not legibles))

    if unir and legibles:
        try:
            combinado = unir_pdfs(files, incluir_portada=agregar_portada, meta_fuente=files[0])
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
                st.write(f"Archivos unidos: **{len(files)}**")
                st.write(f"Páginas totales: **{total_pag}**")
                st.write("Orden aplicado: **{}**".format("Nombre (A→Z)" if ordenar != "Orden de subida" else "Orden de subida"))
                st.write(f"Portada añadida: **{'Sí' if agregar_portada else 'No'}**")

        except Exception as e:
            st.error(f"❌ Ocurrió un error al unir: {e}")
else:
    st.info("Sube uno o más archivos PDF para comenzar.")


