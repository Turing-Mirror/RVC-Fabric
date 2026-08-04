; RVC Fabric — Windows installer (Inno Setup 6)
; 企业/独立软件常用安装器技术，不要用自写 Tk 向导替代本脚本。
;
; 构建（在仓库根，先打出 payload）：
;   python scripts/build_setup.py
;   → 调用 ISCC 编译本文件 → dist/RVC_Fabric_Setup.exe
;
; 需要本机安装 Inno Setup 6：
;   https://jrsoftware.org/isinfo.php
;   默认路径: C:\Program Files (x86)\Inno Setup 6\ISCC.exe
;
; 用户动线：
;   Setup.exe（本安装器）安装通用薄包：RVC Fabric.exe + 可替换的 frontend/ + 引擎源码
;   → 首次打开由程序自身鉴别显卡、补全 Runtime + engine-core + VB-Cable
;   → 社区音色（LFS）
;
; 通用包：不再按显卡分版，运行时类型由程序自动鉴别后推荐，用户可改选。
; 单一程序：原「启动器.exe」已被 Tauri 版内置的首次引导取代，不再安装。

#define MyAppName "RVC Fabric"
#define MyAppNameCN "RVC Fabric · 图灵镜"
#define MyAppVersion "1.3.10"
; Windows 版本资源只接受纯数字 a.b.c.d
#define MyAppVerNum "1.3.10.0"
#define MyAppPublisher "Turing-Mirror"
#define MyAppURL "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases"
#define MyAppId "{{A1B2C3D4-E5F6-4789-ABCD-EF1234567890}"

; Payload 由 scripts/build_setup.py 生成（相对本 .iss 的路径）
#ifndef PayloadDir
  #define PayloadDir "..\dist\RVC_Fabric_Setup_payload"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef OutputBase
  #define OutputBase "RVC_Fabric_Setup"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 不要求管理员（装到用户目录）；若改 Program Files 请改 PrivilegesRequired=admin
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBase}
SetupIconFile=..\assets\brand\app.ico
; Point uninstall + Start Menu icons at the shipped .ico (not only the exe resource).
; gui_patch can refresh assets/brand/app.ico without re-embedding PyInstaller icons.
UninstallDisplayIcon={app}\assets\brand\app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVerNum}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
; 安装说明
InfoBeforeFile=
LicenseFile=
; 关闭完成后重启提示
CloseApplications=no
RestartApplications=no
; 目录页允许浏览
DisableDirPage=no
UsePreviousAppDir=yes
; 向导语言：一律简中
ShowLanguageDialog=no
; 关键：默认 yes 时升级安装会沿用注册表里上次安装的语言——
; 老用户从纯英文旧 Setup 升级会永远卡在英文。必须关掉。
UsePreviousLanguage=no

[Languages]
; 安装向导整体中文：简中语言文件随仓库自带（installer/ChineseSimplified.isl，
; UTF-8 带 BOM），相对本 .iss 引用，不依赖打包机的 Inno 语言包。
; 只保留简中一种语言：任何系统语言、任何升级路径都不会落回英文。
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Messages]
chinesesimplified.BeveledLabel=RVC Fabric 安装程序

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce

[InstallDelete]
; 从旧的 Python 双程序版本升级：Inno 的 [Files] 只覆盖不删除，不清理的话
; 旧的 启动器.exe / 变声器.exe / launcher\ 会留在安装目录，而且旧快捷方式
; 还能把老启动器拉起来——两个程序共用 User_Data、互斥锁又不是同一个，
; 可能同时起两个 worker 抢音频设备。
; 注意：Runtime\ 与 User_Data\ 绝不能进这一段，那是用户的运行时和音色。
Type: files; Name: "{app}\启动器.exe"
Type: files; Name: "{app}\变声器.exe"
Type: files; Name: "{app}\TM_Setup.exe"
Type: files; Name: "{app}\TM_Voice.exe"
Type: files; Name: "{app}\OpenApp.vbs"
Type: files; Name: "{app}\OpenSetup.vbs"
Type: files; Name: "{app}\start.bat"
Type: files; Name: "{app}\start_app.bat"
Type: files; Name: "{app}\启动器.vbs"
Type: files; Name: "{app}\启动软件.vbs"
Type: filesandordirs; Name: "{app}\launcher\pages"
Type: filesandordirs; Name: "{app}\launcher\ui"
Type: files; Name: "{app}\launcher\main_app.py"
Type: files; Name: "{app}\launcher\bootstrap.py"
Type: files; Name: "{app}\launcher\theme.py"
Type: files; Name: "{app}\launcher\tray.py"
Type: files; Name: "{app}\launcher\setup_app.py"
Type: files; Name: "{app}\launcher\_setup_shell.py"
Type: files; Name: "{app}\launcher\rvc_launcher.py"
; 旧快捷方式（新版只建一个）
Type: files; Name: "{group}\{#MyAppName} 启动器.lnk"
Type: files; Name: "{autodesktop}\{#MyAppName} 启动器.lnk"

[Registry]
; NSIS OTA 定位键：Tauri 的 NSIS 安装器（OTA 签名包）安装前会读
; HKCU\Software\Turing-Mirror\RVC Fabric 的默认值当作「上次安装目录」。
; Setup 装到自定义目录的用户靠它让 OTA 装回同一目录，否则 NSIS 会按
; 全新安装落到 %LOCALAPPDATA%\RVC Fabric，Runtime / engine-core 全部重下。
;
; 键名里的「Turing-Mirror」必须和 NSIS 的 MANUFACTURER 一模一样，而
; MANUFACTURER 不是随便起的名字，tauri-bundler 是这么算的：
;
;   settings.publisher().unwrap_or_else(|| bundle_id.split('.').nth(1)...)
;
; publisher 不填的话就取 identifier 的第二段 —— com.turingmirror.rvcfabric
; 会算出「turingmirror」，和这里的「Turing-Mirror」差一个连字符，注册表
; 当成两个不同的键，这条就白写了。所以 tauri.conf.json 里显式写了
; "publisher": "Turing-Mirror"。改任何一边都要同时改另一边。
Root: HKCU; Subkey: "Software\Turing-Mirror\RVC Fabric"; ValueType: string; ValueName: ""; ValueData: "{app}"; Flags: uninsdeletevalue

[Files]
; 通用薄包：RVC Fabric.exe + 可替换的 frontend/ + 引擎源码
; 不含 Runtime / engine-core / VB-Cable，这三样首次运行时下载
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; IconFilename must be the loose .ico — Windows Start Menu caches exe resources and
; will keep the old swirl mark after gui_patch unless shortcuts pin app.ico explicitly.
Name: "{group}\{#MyAppName}"; Filename: "{app}\RVC Fabric.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\brand\app.ico"; Comment: "RVC Fabric"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\assets\brand\app.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\RVC Fabric.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\brand\app.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\RVC Fabric.exe"; Description: "打开 RVC Fabric（首次运行会自动补全环境）"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"

[UninstallDelete]
; 用户下载的 Runtime / 音色体积大，默认不在卸载时删除 User_Data 与 Runtime
; 若需干净卸载可改为删除（谨慎）
; Type: filesandordirs; Name: "{app}\Runtime"
; Type: filesandordirs; Name: "{app}\User_Data"

[Code]
// 通用安装包：安装时不再让用户选显卡分版。
// 运行时类型由程序首次启动时鉴别主显卡后推荐（可自行改选），
// 所以这里写空串，package_meta 不预先钉死任何变体。
function GpuVariant: String;
begin
  Result := '';
end;

function GpuLabel(const V: String): String;
begin
  if V = 'amd' then
    Result := 'AMD/Intel DirectML'
  else if V = 'nvidia50' then
    Result := 'NVIDIA 50 系 CUDA'
  else
    Result := 'NVIDIA CUDA';
end;

function AccelDefault(const V: String): String;
begin
  if V = 'amd' then
    Result := 'dml'
  else
    Result := 'cuda';
end;

procedure WriteTextFile(const FileName, Content: String);
begin
  if not ForceDirectories(ExtractFilePath(FileName)) then
  begin
    Log('ForceDirectories failed: ' + ExtractFilePath(FileName));
    Exit;
  end;
  SaveStringToFile(FileName, Content, False);
end;

procedure WritePackageMeta;
var
  V, Path, Json, UseDml: String;
  Existing: AnsiString;
begin
  V := GpuVariant;
  UseDml := 'false';
  Path := ExpandConstant('{app}\package_meta.json');
  { 覆盖升级：老装机已经补好过 Runtime，package_meta 里有变体。通用包
    这里写的是空串，直接覆盖会让程序以为从没选过变体，进而要求重新补全。
    已有内容且带 variant 就整份保留，不动它。 }
  if FileExists(Path) then
  begin
    if LoadStringFromFile(Path, Existing) then
    begin
      if Pos('"variant": ""', Existing) = 0 then
      begin
        Log('package_meta.json already has a provisioned variant — keeping it');
        Exit;
      end;
    end;
  end;
  Json :=
    '{' + #13#10 +
    '  "variant": "' + V + '",' + #13#10 +
    '  "label": "' + GpuLabel(V) + '",' + #13#10 +
    '  "accel_default": "' + AccelDefault(V) + '",' + #13#10 +
    '  "use_dml": ' + UseDml + ',' + #13#10 +
    '  "tagged": false,' + #13#10 +
    '  "install_via": "inno_setup",' + #13#10 +
    '  "runtime_channel": "cnb_release",' + #13#10 +
    '  "runtime_release_tag": "RVC-runtime",' + #13#10 +
    '  "cnb_repo": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases"' + #13#10 +
    '}';
  WriteTextFile(Path, Json);
  Log('Wrote ' + Path);
end;

procedure WriteSetupPending;
var
  V, Path, Json: String;
begin
  V := GpuVariant;
  Path := ExpandConstant('{app}\User_Data\setup_pending.json');
  Json :=
    '{' + #13#10 +
    '  "pending_runtime": true,' + #13#10 +
    '  "variant": "' + V + '",' + #13#10 +
    '  "install_via": "inno_setup"' + #13#10 +
    '}';
  WriteTextFile(Path, Json);
  Log('Wrote ' + Path);
end;

{ WebView2 运行时。
  界面跑在 WebView2 里，没有它主程序打不开窗口 —— 而且什么都不会显示，
  用户只会看到「双击没反应」。Win11 和更新过的 Win10 自带；LTSC、精简版、
  长期没更新的 Win10 可能没有。tauri.conf.json 里的 downloadBootstrapper
  只对 Tauri 自带的 NSIS/MSI 打包生效，我们发的是这个 Inno 包，走不到。
  官方 Evergreen 运行时的注册表标记（HKLM 为全机器安装，HKCU 为单用户）。 }
function WebView2Installed: Boolean;
var
  V: String;
begin
  Result :=
    (RegQueryStringValue(HKEY_LOCAL_MACHINE,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', V) and (V <> '') and (V <> '0.0.0.0')) or
    (RegQueryStringValue(HKEY_LOCAL_MACHINE,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', V) and (V <> '') and (V <> '0.0.0.0')) or
    (RegQueryStringValue(HKEY_CURRENT_USER,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', V) and (V <> '') and (V <> '0.0.0.0'));
end;

procedure EnsureWebView2;
var
  Boot: String;
  Code: Integer;
  Got: Boolean;
begin
  if WebView2Installed then
    Exit;
  Boot := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');
  Got := False;
  { 下载或安装失败都不挡这次安装：主程序装完了，用户还能自己补 WebView2，
    在这里硬拦住只会更糟。 }
  try
    DownloadTemporaryFile('https://go.microsoft.com/fwlink/p/?LinkId=2124703',
      'MicrosoftEdgeWebview2Setup.exe', '', nil);
    Got := FileExists(Boot);
  except
    Log('WebView2 bootstrapper download failed: ' + GetExceptionMessage);
  end;
  if Got then
    if Exec(Boot, '/silent /install', '', SW_SHOW, ewWaitUntilTerminated, Code) then
      if WebView2Installed then
        Exit;
  MsgBox('这台电脑缺少 WebView2 运行时，RVC Fabric 的界面需要它。' + #13#10 + #13#10 +
    '如果装完之后双击没反应，请到微软官网安装「Microsoft Edge WebView2 Runtime」' +
    '（Evergreen 版）后重开：' + #13#10 +
    'https://go.microsoft.com/fwlink/p/?LinkId=2124703',
    mbInformation, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    EnsureWebView2;
    WritePackageMeta;
    WriteSetupPending;
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  S := '';
  if MemoDirInfo <> '' then
    S := S + MemoDirInfo + NewLine + NewLine;
  S := S + '显卡分版: ' + GpuLabel(GpuVariant) + NewLine;
  S := S + '安装后启动器将从 CNB 下载 Runtime（按显卡）与 engine-core（共用，约 700MB+），需联网。' + NewLine;
  if MemoTasksInfo <> '' then
    S := S + NewLine + MemoTasksInfo;
  Result := S;
end;
