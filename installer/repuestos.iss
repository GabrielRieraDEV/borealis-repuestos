; Inno Setup 6 · instalador de Borealis Repuestos
; Compilar con installer\build.ps1 (pasa /DAppVersion=x.y.z) o:  ISCC.exe /DAppVersion=0.1.0 installer\repuestos.iss
;
; Reglas (RNF-06):
; - El programa va en Program Files. Los datos van en C:\ProgramData\BorealisRepuestos\{datos,respaldos,logs}
;   con permiso de modificación para los usuarios.
; - Actualizar o desinstalar NUNCA borra ni sobrescribe la carpeta de datos: el instalador no copia archivos ahí
;   y las carpetas llevan uninsneveruninstall.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Channel
  #define Channel ""
#endif

#define AppName "Borealis Repuestos"
#define AppExe "BorealisRepuestos.exe"
#define DataRoot "{commonappdata}\BorealisRepuestos"

[Setup]
AppId={{7C1B2E0A-5D43-4B8E-9A5F-3E2C1D0B9A71}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Borealis Software Solutions
AppCopyright=Borealis Software Solutions
VersionInfoCompany=Borealis Software Solutions
VersionInfoDescription=Borealis Repuestos - inventario, ventas y caja
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=Output
OutputBaseFilename=BorealisRepuestos-{#AppVersion}{#Channel}-instalador
SetupIconFile=..\src\repuestos\ui\repuestos.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "testicon"; Description: "Crear también «modo de prueba» en el escritorio (para la visita; se puede borrar después)"; GroupDescription: "Accesos directos:"

[Dirs]
; Datos de la clienta: se crean si no existen, con permiso de escritura para los usuarios, y nunca se borran.
Name: "{#DataRoot}"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{#DataRoot}\datos"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{#DataRoot}\respaldos"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{#DataRoot}\logs"; Permissions: users-modify; Flags: uninsneveruninstall
; Modo de prueba: base aparte para las pruebas de la visita y para practicar (no toca los datos reales).
Name: "{commonappdata}\BorealisRepuestos-prueba"; Permissions: users-modify

[InstallDelete]
; Al actualizar, limpia las librerías viejas del programa (solo dentro de {app}, nunca los datos).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\BorealisRepuestos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} (modo de prueba)"; Filename: "{app}\{#AppExe}"; Parameters: "--prueba"; Comment: "Para practicar: no toca los datos reales"
Name: "{group}\Guía rápida"; Filename: "{app}\_internal\repuestos\ui\guia-rapida.pdf"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{autodesktop}\{#AppName} (modo de prueba)"; Filename: "{app}\{#AppExe}"; Parameters: "--prueba"; Tasks: testicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
