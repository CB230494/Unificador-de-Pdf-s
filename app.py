# =========================
# 🧩 Unificador de PDFs grandes — merge incremental + descarga fraccionada
# =========================
import streamlit as st
import tempfile, os, shutil, gc
from typing import List

st.set_page_config(page_title="Unificador de PDFs", layout="centered")
st.title("🧩 Unificar PDFs grandes (ultra ahorro)")

# Dependencias
try:
    import pikepdf
except Exception as e:
    st.error("No se pudo importar pikepdf. Revisa requirements.txt.")
    st.exception(e); st.stop()

st.caption(f"🔧 Límite actual por archivo: {st.get_option('server.maxUploadSize')} MB")
st.divider()

# ---------- Opciones ----------
c1, c2 = st.columns(2)
with c1:
    ordenar = st.selectbox("Orden", ["Orden de subida", "Nombre de archivo (A→Z)"])
with c2:
    contar_paginas = st.toggle("Contar páginas (consume más)", value=False)

# Tamaño por parte para descarga fraccionada
parte_mb = st.slider("Tamaño por parte (MB) para descarga fraccionada", 50, 300, 150, 25,
                     help="Usa 100–200 MB si tu navegador/host falla con archivos muy grandes.")

st.divider()

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
            # Guardar 'tal cual' (sin recomprimir ni linearizar) para ahorrar RAM/CPU
            dst.save(nxt.name)
        try: os.remove(current)
        except Exception: pass
        current = nxt.name
        gc.collect()
    return current  # ruta final

def split_file(path_local: str, part_size_mb: int) -> List[str]:
    """Divide un archivo grande en partes .partXX de ~part_size_mb MB (sin cargar a RAM)."""
    part_paths = []
    part_bytes = part_size_mb * 1024 * 1024
    with open(path_local, "rb") as f:
        idx = 1
        while True:
            chunk = f.read(part_bytes)
            if not chunk:
                break
            part_path = f"{path_local}.part{idx:02d}"
            with open(part_path, "wb") as o:
                o.write(chunk)
            part_paths.append(part_path)
            idx += 1
    return part_paths

def make_join_scripts(base_name: str, parts_count: int):
    """
    Genera scripts para recombinar:
    - Windows .bat (copy /b)
    - macOS/Linux .sh (cat)
    """
    # Nombres esperados de partes
    parts = [f"{base_name}.part{idx:02d}" for idx in range(1, parts_count + 1)]
    # BAT
    bat_lines = ['@echo off',
                 'echo Recombinar partes en unificado.pdf',
                 'REM Asegurate de ejecutar este .bat en la carpeta donde descargaste las partes']
    bat_lines.append(f'copy /b {" + ".join(parts)} unificado.pdf')
    bat_content = "\r\n".join(bat_lines)
    # SH
    sh_lines = ['#!/bin/sh',
                'echo "Recombinar partes en unificado.pdf"',
                'echo "Ejecuta este script en la carpeta donde descargaste las partes"']
    sh_lines.append(f'cat {" ".join(parts)} > unificado.pdf')
    sh_content = "\n".join(sh_lines)
    return bat_content.encode("utf-8"), sh_content.encode("utf-8")

def show_files(paths: List[str]):
    for p in paths:
        nm = os.path.basename(p)
        size_mb = os.path.getsize(p) / (1024 * 1024)
        st.write(f"• **{nm}** — {size_mb:.1f} MB")

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
    unir_btn = st.button("🔗 Unir todo (incremental)", use_container_width=True)

    if unir_btn:
        try:
            out_path = merge_incremental(st.session_state.disk_paths)
            st.success("✅ PDF combinado generado.")

            # Datos del archivo final
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            st.write(f"**Tamaño del resultado:** {size_mb:.1f} MB")

            # Descarga directa (entera) — puede fallar si es muy grande
            with open(out_path, "rb") as fh:
                st.download_button("⬇️ Descargar PDF completo (puede requerir mucha RAM)",
                                   data=fh, file_name="unificado.pdf",
                                   mime="application/pdf", use_container_width=True)

            st.divider()
            st.markdown("### 📦 Descarga fraccionada (recomendada para archivos muy grandes)")
            parts = split_file(out_path, parte_mb)
            st.caption(f"Se generaron **{len(parts)}** partes de ~{parte_mb} MB.")

            # Botones para cada parte (más seguros)
            for i, p in enumerate(parts, start=1):
                with open(p, "rb") as fh:
                    st.download_button(
                        f"⬇️ Parte {i:02d}/{len(parts)}",
                        data=fh,
                        file_name=f"unificado.pdf.part{i:02d}",
                        mime="application/octet-stream",
                        use_container_width=True,
                    )

            # Scripts para recombinar localmente
            bat_bytes, sh_bytes = make_join_scripts("unificado.pdf", len(parts))
            st.divider()
            colA, colB = st.columns(2)
            with colA:
                st.download_button("🪟 Descargar recombinador Windows (.bat)",
                                   data=bat_bytes, file_name="recombinar_windows.bat",
                                   mime="application/octet-stream", use_container_width=True)
            with colB:
                st.download_button("🐧 Descargar recombinador macOS/Linux (.sh)",
                                   data=sh_bytes, file_name="recombinar_unix.sh",
                                   mime="text/x-shellscript", use_container_width=True)
            st.caption("En Windows: pon todas las partes y el .bat en una misma carpeta y ejecútalo. "
                       "En macOS/Linux: `chmod +x recombinar_unix.sh && ./recombinar_unix.sh`.")

        except Exception as e:
            st.error("❌ Error al unir/descargar."); st.exception(e)

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

