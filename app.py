# =========================
# 🧩 Unificador de PDFs (alto volumen / baja memoria)
# =========================
import streamlit as st
from io import BytesIO
import tempfile
import os

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs (sin límite de páginas)")
st.caption("Optimizado para PDFs grandes: une secuencialmente y escribe a disco para reducir uso de memoria.")

# Usamos pikepdf (qpdf) — más eficiente en memoria que pypdf para archivos grandes
try:
    import pikepdf
except Exception as e:
    st.error("No se pudo importar pikepdf. Revisa requirements.txt.")
    st.exception(e)
    st.stop()

orden = st.selectbox("Orden de unión", ["Orden de subida", "Nombre de archivo (A→Z)"])
st.divider()

files = st.file_uploader("Selecciona tus PDFs", type=["pdf"], accept_multiple_files=True)

def contar_paginas(file) -> int:
    file.seek(0)
    with pikepdf.open(file) as pdf:
        return len(pdf.pages)

def unir_grandes(archivos, progress_cb=None) -> str:
    """
    Une PDFs pesados escribiendo directamente a un archivo temporal.
    Devuelve la ruta del PDF resultante (para abrir en modo 'rb' al descargar).
    """
    # Archivo temporal de salida en disco
    tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_out_path = tmp_out.name
    tmp_out.close()  # se cerrará; pikepdf guardará en esa ruta

    # PDF de destino vacío
    dst = pikepdf.Pdf.new()

    total = len(archivos)
    for idx, f in enumerate(archivos, start=1):
        f.seek(0)
        # Abrimos cada fuente y extendemos páginas; se cierra enseguida para liberar RAM
        with pikepdf.open(f) as src:
            dst.pages.extend(src.pages)

        if progress_cb:
            progress_cb(idx, total)

    # Guardar con optimización y linearización para descarga más ágil
    dst.save(
        tmp_out_path,
        compress_streams=True,
        object_stream_mode=pikepdf.ObjectStreamMode.generate,
        linearize=True,
    )
    dst.close()

    return tmp_out_path

if files:
    if orden == "Nombre de archivo (A→Z)":
        files = sorted(files, key=lambda x: x.name.lower())

    st.subheader("📄 Archivos detectados")
    legibles = True
    total_pag = 0

    # Mostrar nombres (contar páginas puede ser costoso; lo hacemos con cuidado)
    for f in files:
        try:
            n = contar_paginas(f)
            total_pag += n
            st.write(f"• **{f.name}** — {n} pág.")
        except Exception as e:
            st.error(f"❌ No se pudo leer **{f.name}** (posible PDF protegido o corrupto).")
            with st.expander(f"Detalle de {f.name}"):
                st.exception(e)
            legibles = False

    st.divider()
    btn = st.button("🔗 Unir PDFs", use_container_width=True, disabled=(not legibles))
    if btn and legibles:
        prog = st.progress(0.0)
        status = st.empty()

        def _cb(i, tot):
            prog.progress(i / tot)
            status.write(f"Unidos {i} de {tot} archivos…")

        try:
            out_path = unir_grandes(files, progress_cb=_cb)
            prog.progress(1.0)
            status.write("Completado ✅")

            st.success("PDF combinado generado correctamente.")
            # Importante: abrir en modo 'rb' para no cargar todo en memoria de golpe
            with open(out_path, "rb") as fh:
                st.download_button(
                    "⬇️ Descargar PDF Unificado",
                    data=fh,
                    file_name="unificado.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

            with st.expander("📋 Resumen"):
                st.write(f"Archivos unidos: **{len(files)}**")
                st.write(f"Páginas totales (estimadas): **{total_pag}**")
                st.write("Orden aplicado: **{}**".format("Nombre (A→Z)" if orden != "Orden de subida" else "Orden de subida"))

            # Limpieza opcional al finalizar la sesión (se borrará cuando el contenedor se recicle)
            st.caption(f"Temporal: {out_path}")

        except Exception as e:
            st.error("❌ Ocurrió un error al unir.")
            st.exception(e)
else:
    st.info("Sube uno o más archivos PDF para comenzar.")


