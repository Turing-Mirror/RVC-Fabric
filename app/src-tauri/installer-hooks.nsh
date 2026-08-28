; RVC Fabric —— NSIS 安装器钩子
;
; 为什么有这个文件：以前手动下载走 Inno 打的包、自动更新走 Tauri 打的 NSIS 包，
; 两套安装程序并存。现在统一到 NSIS 一套，Inno 那边独有的清理动作必须搬过来，
; 否则从老版本升级的用户会留下一堆残骸。
;
; Tauri 的 NSIS 模板本来就做的事，这里不要重复做：
;   - 目录选择页（正常安装显示，OTA 静默安装自动跳过）
;   - 把安装目录写进 HKCU\Software\Turing-Mirror\RVC Fabric，下次升级读回来
;   - 默认装到 %LOCALAPPDATA%\RVC Fabric，不要管理员权限
;   - 卸载时只删自己装的文件，RMDir 不带 /r —— Runtime\ 和 User_Data\ 不会被删
;
; 安装钩子（PREINSTALL / POSTINSTALL）绝对不要碰 Runtime\ 和 User_Data\：
; 覆盖升级要靠它们留下来。卸载钩子（PREUNINSTALL / POSTUNINSTALL）相反：
; 薄包首次运行后会从 CNB 再下 Runtime、engine-core、音色、分离/训练底模，
; 这些不在安装清单里，模板清不掉。真正卸载时必须清 Runtime 等运行环境，
; User_Data 由用户勾选「同时删除用户数据」或弹窗选择，默认保留。
; OTA（/UPDATE）和被动安装（/P）会走卸载器时仍跳过，避免升级把运行时卸掉。
; VB-Cable 是系统驱动，卸载程序只删安装目录里的安装包，驱动要用户自己卸。

; 卸载时记住「要不要留 User_Data」。默认 1 = 保留。
Var KeepUserData

!macro NSIS_HOOK_PREINSTALL
  ; 路径里有中文时 faiss 读不了检索库。OTA 静默升级不要挡（已经装在中文目录
  ; 的人卸了重来更糟），正常安装弹一句，让他改到 D:\RVCFabric 这种纯英文路径。
  IfSilent skip_nonascii_warn
    Push $R0
    Push $R1
    StrCpy $R1 0
    ; CP_USASCII=20127，WC_NO_BEST_FIT_CHARS=0x400。替换过字符则路径含非 ASCII。
    System::Call 'kernel32::WideCharToMultiByte(i 20127, i 1024, w "$INSTDIR", i -1, i 0, i 0, i 0, *i .R1) i .R0'
    IntCmp $R1 0 skip_nonascii_pop
    MessageBox MB_YESNO|MB_ICONEXCLAMATION "安装路径里有中文或其他非英文字符。$\r$\n$\r$\n音色检索等功能在这种路径下无法使用。$\r$\n请改到纯英文路径，例如 D:\RVCFabric。$\r$\n$\r$\n仍要安装到这里吗？" IDYES skip_nonascii_pop
    Abort
    skip_nonascii_pop:
    Pop $R1
    Pop $R0
  skip_nonascii_warn:

  ; ── 一、清掉更早的「Python 双程序版」残骸 ────────────────────────────
  ; 那一版装的是 启动器.exe + 变声器.exe 两个程序。装新版只覆盖不删除的话，
  ; 旧的启动器还留在目录里，旧快捷方式还能把它拉起来 —— 两个程序共用
  ; User_Data、互斥锁又不是同一个，可能同时起两个 worker 抢音频设备。
  Delete "$INSTDIR\启动器.exe"
  Delete "$INSTDIR\变声器.exe"
  Delete "$INSTDIR\TM_Setup.exe"
  Delete "$INSTDIR\TM_Voice.exe"
  Delete "$INSTDIR\OpenApp.vbs"
  Delete "$INSTDIR\OpenSetup.vbs"
  Delete "$INSTDIR\start.bat"
  Delete "$INSTDIR\start_app.bat"
  Delete "$INSTDIR\启动器.vbs"
  Delete "$INSTDIR\启动软件.vbs"

  RMDir /r "$INSTDIR\launcher\pages"
  RMDir /r "$INSTDIR\launcher\ui"
  Delete "$INSTDIR\launcher\main_app.py"
  Delete "$INSTDIR\launcher\bootstrap.py"
  Delete "$INSTDIR\launcher\theme.py"
  Delete "$INSTDIR\launcher\tray.py"
  Delete "$INSTDIR\launcher\setup_app.py"
  Delete "$INSTDIR\launcher\_setup_shell.py"
  Delete "$INSTDIR\launcher\rvc_launcher.py"
  RMDir "$INSTDIR\launcher"

  ; 旧快捷方式（新版只建一个，名字里没有「启动器」）
  Delete "$SMPROGRAMS\RVC Fabric 启动器.lnk"
  Delete "$DESKTOP\RVC Fabric 启动器.lnk"

  ; ── 二、拆掉 Inno 那一套的痕迹 ───────────────────────────────────────
  ; 不拆的话「添加/删除程序」里会同时出现两个 RVC Fabric：一个是 Inno 留的，
  ; 点它会走 Inno 的卸载流程，把 NSIS 装的文件删一半，剩一个装不上也卸不掉的
  ; 半残安装。Inno 是 PrivilegesRequired=lowest，条目通常在 HKCU，但它允许用户
  ; 提权安装，所以 HKLM 也要清。
  ; 这串 GUID 是 Inno 脚本里的 AppId，`_is1` 后缀是 Inno 自己加的。改 AppId
  ; 就要同步改这里，不过 Inno 那套马上要退役，正常不会再动。
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-4789-ABCD-EF1234567890}_is1"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-4789-ABCD-EF1234567890}_is1"

  ; Inno 的卸载程序本体。留着它没有入口能调用，纯粹占地方，而且用户手动双击
  ; 它一样会把新装的文件删坏。
  Delete "$INSTDIR\unins000.exe"
  Delete "$INSTDIR\unins000.dat"
  Delete "$INSTDIR\unins000.msg"
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; 安装目录的注册表键由 Tauri 的模板自己写（WriteRegStr SHCTX MANUPRODUCTKEY），
  ; 这里不用重复写。重复写反而危险：写歪一个字符，下次 OTA 就找不到安装目录，
  ; 当成全新安装落到 %LOCALAPPDATA%，用户几个 GB 的运行时要重下一遍。
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ; 默认保留用户数据。OTA / 被动升级把 /UPDATE、/P 传给卸载器时整段跳过。
  StrCpy $KeepUserData 1
  StrCmp $UpdateMode 1 skip_uninst_kill
  StrCmp $PassiveMode 1 skip_uninst_kill

  ; 确认页勾了「同时删除用户数据」就不再问；没勾则弹窗让用户选。
  ; 两种路径都要提到 VB-Cable：它是系统驱动，这里卸不掉。
  StrCmp $DeleteAppDataCheckboxState 1 uninst_force_delete_data
  IfSilent skip_uninst_prompt
    MessageBox MB_YESNO|MB_ICONQUESTION "是否保留用户数据（音色、设置、日志）？$\r$\n$\r$\n选「是」将保留 User_Data，下次安装后可继续使用。$\r$\n选「否」将连同用户数据一起删除。$\r$\n$\r$\nRuntime 等下载的运行环境会一并清除。$\r$\n$\r$\n注意：VB-Cable 虚拟声卡是系统驱动，需要到 Windows「应用和功能」中单独卸载 VB-Audio Virtual Cable。本程序不会卸载它。" IDYES skip_uninst_prompt
    StrCpy $KeepUserData 0
    Goto skip_uninst_prompt
  uninst_force_delete_data:
    StrCpy $KeepUserData 0
    IfSilent skip_uninst_prompt
    MessageBox MB_OK|MB_ICONINFORMATION "注意：VB-Cable 虚拟声卡是系统驱动，需要到 Windows「应用和功能」中单独卸载 VB-Audio Virtual Cable。本程序不会卸载它。"
  skip_uninst_prompt:

  ; 停掉安装目录里的进程，否则 Runtime\pythonw.exe 还攥着 DLL，后面 RMDir 会剩半截。
  ; 只按 ExecutablePath 前缀匹配 $INSTDIR，绝不 taskkill pythonw（会误伤别的程序）。
  nsExec::ExecToLog 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "$$p = [IO.Path]::GetFullPath(''$INSTDIR''); Get-CimInstance Win32_Process | ForEach-Object { $$e = [string]$$_.ExecutablePath; if ($$e -and $$e.StartsWith($$p, [StringComparison]::OrdinalIgnoreCase)) { Stop-Process -Id $$_.ProcessId -Force -ErrorAction SilentlyContinue } }"'
  Sleep 800
  skip_uninst_kill:
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; 模板已经按清单删完随包文件。这里只清事后下载/生成的残留。
  ; 不 RMDir /r "$INSTDIR"：用户万一装到 D:\ 这种宽目录，递归删会把同盘别的东西一起带走。
  StrCmp $UpdateMode 1 skip_uninst_clean
  StrCmp $PassiveMode 1 skip_uninst_clean

  RMDir /r "$INSTDIR\Runtime"
  RMDir /r "$INSTDIR\runtime"
  StrCmp $KeepUserData 1 skip_uninst_userdata
    RMDir /r "$INSTDIR\User_Data"
    RMDir /r "$INSTDIR\UserData"
  skip_uninst_userdata:
  RMDir /r "$INSTDIR\TEMP"
  RMDir /r "$INSTDIR\VBCABLE"
  ; OTA gui_patch 换过 frontend 后哈希文件名对不上清单，模板删不干净
  RMDir /r "$INSTDIR\frontend"
  Delete "$INSTDIR\ffmpeg.exe"
  Delete "$INSTDIR\ffprobe.exe"
  Delete "$INSTDIR\package_meta.json"
  Delete "$INSTDIR\assets\hubert\hubert_base.pt"
  Delete "$INSTDIR\assets\rmvpe\rmvpe.pt"
  Delete "$INSTDIR\assets\rmvpe\rmvpe.onnx"
  RMDir /r "$INSTDIR\assets\pretrained_v2"
  RMDir /r "$INSTDIR\assets\pretrained"
  RMDir /r "$INSTDIR\assets\uvr5_weights"
  RMDir /r "$INSTDIR\assets\pymss"
  RMDir /r "$INSTDIR\assets\hubert"
  RMDir /r "$INSTDIR\assets\rmvpe"
  RMDir /r "$INSTDIR\assets\weights"
  RMDir "$INSTDIR\assets"
  RMDir "$INSTDIR"
  skip_uninst_clean:
!macroend
