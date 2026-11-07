# PyInstaller · modo onedir, sin consola, con icono.
# Uso (desde la raíz del repo):  .\.venv\Scripts\pyinstaller.exe --noconfirm --clean installer\repuestos.spec
# Resultado: dist\BorealisRepuestos\BorealisRepuestos.exe

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821  (SPECPATH lo define PyInstaller)
ICON = str(ROOT / "src" / "repuestos" / "ui" / "repuestos.ico")

a = Analysis(  # noqa: F821
    [str(ROOT / "installer" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("repuestos"),  # migraciones .sql e icono
    hiddenimports=["truststore"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BorealisRepuestos",
    icon=ICON,
    console=False,
    upx=False,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="BorealisRepuestos",
    upx=False,
)
