# Builds BonDriver_TUVL01.dll (x64) with the LLVM toolchain from WinLibs, without MSVC.
# The shell is compiled for the MSVC C++ ABI (vtable/RTTI layout TVTest expects); the
# portable C client is compiled for the MinGW target. No C runtime is linked.
param([string]$Out="$PSScriptRoot\build")
$ErrorActionPreference='Continue'
$clang=(Get-Command clang).Source;$bin=Split-Path $clang;$lib="$(Split-Path $bin)\x86_64-w64-mingw32\lib"
New-Item -ItemType Directory $Out -Force | Out-Null
$c="$PSScriptRoot\.."
& $clang --target=x86_64-w64-windows-gnu -O2 -std=c99 -Wall -Wextra -fno-stack-protector -ffreestanding -c "$c\tuvl01_proto.c" -o "$Out\proto.o" 2>&1 | Tee-Object -Variable log | Out-Null; if($LASTEXITCODE){ $log; throw "build step failed" }
& $clang --target=x86_64-w64-windows-gnu -O2 -std=c99 -Wall -Wextra -fno-stack-protector -c "$c\tuvl01_session.c" -o "$Out\session.o" 2>&1 | Tee-Object -Variable log | Out-Null; if($LASTEXITCODE){ $log; throw "build step failed" }
$cpp=@('--target=x86_64-pc-windows-msvc','-O2','-std=c++17','-Wall','-Wextra','-Wno-ignored-qualifiers','-Wno-overloaded-virtual','-Wno-delete-non-abstract-non-virtual-dtor','-fno-exceptions','-frtti','-fno-stack-protector','-ffreestanding','-fms-extensions')
& $clang @cpp -c "$PSScriptRoot\BonDriver_TUVL01.cpp" -o "$Out\bondriver.o" 2>&1 | Tee-Object -Variable log | Out-Null; if($LASTEXITCODE){ $log; throw "build step failed" }
& $clang @cpp -c "$PSScriptRoot\test_loader.cpp" -o "$Out\loader.o" 2>&1 | Tee-Object -Variable log | Out-Null; if($LASTEXITCODE){ $log; throw "build step failed" }
$libs=@("$lib\libkernel32.a","$lib\libws2_32.a","$lib\libmsvcrt.a")
& lld-link /nologo /dll /nodefaultlib /entry:DllMain /machine:x64 /export:CreateBonDriver "/out:$Out\BonDriver_TUVL01.dll" "$Out\bondriver.o" "$Out\proto.o" "$Out\session.o" @libs 2>&1 | Tee-Object -Variable log | Out-Null; if($LASTEXITCODE){ $log; throw "build step failed" }
# test loader needs __RTDynamicCast from the Visual C++ runtime that TVTest itself uses
"LIBRARY vcruntime140.dll`nEXPORTS`n__RTDynamicCast" | Set-Content "$Out\vc.def"
& llvm-dlltool -m i386:x86-64 -D vcruntime140.dll -d "$Out\vc.def" -l "$Out\vcruntime140.lib" 2>&1 | Tee-Object -Variable log | Out-Null; if($LASTEXITCODE){ $log; throw "build step failed" }
& lld-link /nologo /subsystem:console /nodefaultlib /entry:entry /machine:x64 "/out:$Out\test_loader.exe" "$Out\loader.o" "$Out\vcruntime140.lib" "$lib\libkernel32.a" "$lib\libmsvcrt.a" 2>&1 | Tee-Object -Variable log | Out-Null; if($LASTEXITCODE){ $log; throw "build step failed" }
Get-ChildItem "$Out\*.dll","$Out\*.exe" | Select-Object Name,Length


