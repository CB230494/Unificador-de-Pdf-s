# =========================
# 🧩 Unificador de PDFs grandes — ultra ahorro + Supabase link
# =========================
import streamlit as st
import tempfile, os, shutil, gc
from typing import List
from uuid import uuid4

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs grandes (ultra ahorro)")

# ---------- Dependencias ----------
try:
    import pikepdf
except Exception as e:
    st.error("No se pudo importar pikepdf. Revisa requirements.txt.")
    st.exception(e); st.stop()

# Supabase opcional (para descarga sin usar RAM del servidor)
SB = None; SB_BUCKET = None
usar_supabase = st.toggle("Subir resultado a Supabase (recomendado >200 MB)", value=True)
if usar_supabase:
    try:
        from supabase import create_client
        sb_secrets = st.secrets.get("supabase", {})
        SB = create_client(sb_secrets["url"], sb_secrets["key"])
        SB_BUCKET = sb_secrets.get("bucket", "pdf-unificados")  # crea este bucket en tu proyecto
    except Exception:
        SB = None
        st.warning("No hay credenciales de Supabase en secrets. Se usará descarga directa (puede fallar con archivos muy grandes).")

st.caption(f"🔧 Límite actual por archivo: {st.get_option('server.maxUploadSize')} MB")
st.divider()

# ---------- Opciones ----------
c1, c2 = st.columns(2)
with c1:
    ordenar = st.selectbox("Orden", ["Orden de subida", "Nombre de archivo (A→Z)"])
with c2:
    contar_paginas = st.toggle("Contar páginas (consume más)", value=False)

# ---------- Subida ----------
files = st.file_uploader("Selecciona tus PDFs", type=["pdf"], accept_multiple_files=True)

# ===== Utilidades =====
def to_disk(uploaded_files) -> List[str]:
    """Vuelca UploadedFile a disco por chunks (sin ocupar mucha RAM)."""
    paths = []
    if not uploaded_files: return paths
    prog = st.progress(0.0)
    for i, uf in enumerate(uploaded_files, 1):
        suffix = os.path.splitext(uf.name)[1].lower() or ".pdf"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        uf.seek(0)
        while True:
            chunk = uf.read(8 * 1024 * 1024)  # 8MB
            if not chunk: break
            tmp.write(chunk)
        tmp.flush(); tmp.close()
        paths.append(tmp.name)
        prog.progress(i / len(uploaded_files))
    return paths

def merge_incremental(paths: List[str]) -> str:
    """Une N PDFs creando un intermedio por paso (máx. 2 abiertos a la vez)."""
    base = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); base.close()
    shutil.copyfile(paths[0], base.name)
    current = base.name
    for path in paths[1:]:
        nxt = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); nxt.close()
        with pikepdf.open(current) as dst, pikepdf.open(path) as src:
            dst.pages.extend(src.pages)
            dst.save(nxt.name)  # sin recomprimir/linearizar -> menos RAM/CPU
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

def show_files(paths: List[str]):
    for p in paths:
        nm = os.path.basename(p)
        size_mb = os.path.getsize(p) / (1024 * 1024)
        st.write(f"• **{nm}** — {size_mb:.1f} MB")

def upload_to_supabase(path_local: str) -> str:
    """Sube a Supabase Storage y devuelve URL firmada (24h)."""
    assert SB is not None and SB_BUCKET is not None
    key = f"salidas/{uuid4().hex}.pdf"
    with open(path_local, "rb") as fh:
        # upsert=True para sobrescribir si existiera
        SB.storage.from_(SB_BUCKET).upload(key, fh, file_options={"contentType": "application/pdf", "upsert": True})
    signed = SB.storage.from_(SB_BUCKET).create_signed_url(key, 60 * 60 * 24)
    # compat: dict o objeto con atributo
    if isinstance(signed, dict):
        return signed.get("signed_url") or signed.get("url") or ""
    return getattr(signed, "signed_url", "") or str(signed)

# ===== Estado =====
if "disk_paths" not in st.session_state: st.session_state.disk_paths = None
if "names" not in st.session_state: st.session_state.names = None

# Paso 1: preparar (volcar a disco)
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
        st.error("Error preparando archivos."); st.exception(e)

# Paso 2: unir
if st.session_state.disk_paths:
    st.subheader("📄 Archivos listos")
    show_files(st.session_state.disk_paths)

    if contar_paginas:
        try:
            total_pag = 0
            for p in st.session_state.disk_paths:
                with pikepdf.open(p) as pdf:
                    total_pag += len(pdf.pages)
            st.caption(f"Páginas totales (aprox.): {total_pag}")
        except Exception as e:
            st.warning("No se pudieron contar páginas."); st.exception(e)

    st.divider()

    colA, colB = st.columns(2)
    with colA:
        unir_btn = st.button("🔗 Unir todo (incremental)", use_container_width=True)
    with colB:
        b22_btn = st.button("🪫 Plan B: 2+2→1", use_container_width=True,
                            disabled=len(st.session_state.disk_paths) != 4)

    def _finalizar(out_path: str):
        st.success("✅ PDF combinado generado.")
        if usar_supabase and SB is not None:
            try:
                url = upload_to_supabase(out_path)
                if url:
                    st.link_button("⬇️ Descargar desde Supabase (recomendado)", url, use_container_width=True)
                    st.caption("Enlace firmado válido 24 h.")
                    return
            except Exception as e:
                st.warning("Falló la subida a Supabase, se intentará descarga directa."); st.exception(e)

        # Fallback: descarga directa (puede consumir RAM con archivos muy grandes)
        with open(out_path, "rb") as fh:
            st.download_button("⬇️ Descargar PDF Unificado (directo)", data=fh,
                               file_name="unificado.pdf", mime="application/pdf",
                               use_container_width=True)

    try:
        if unir_btn:
            out_path = merge_incremental(st.session_state.disk_paths)
            _finalizar(out_path)

        if b22_btn:
            a1, a2, b1, b2 = st.session_state.disk_paths
            pA = merge_two(a1, a2)
            pB = merge_two(b1, b2)
            out_path = merge_two(pA, pB)
            try: os.remove(pA); os.remove(pB)
            except Exception: pass
            _finalizar(out_path)

    except Exception as e:
        st.error("❌ Error al unir."); st.exception(e)

    st.divider()
    if st.button("🧹 Borrar temporales y reiniciar", use_container_width=True):
        try:
            for p in st.session_state.disk_paths:
                if os.path.exists(p): os.remove(p)
        except Exception: pass
        st.session_state.disk_paths = None; st.session_state.names = None
        st.toast("Temporales eliminados.", icon="🧼"); st.rerun()
else:
    st.info("Sube y pulsa **Preparar archivos** para volcarlos a disco antes de unir.")


