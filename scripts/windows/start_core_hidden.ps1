# JARVIS CORE hidden starter for Windows Task Scheduler.
#
# Launches the official entry point (scripts\run_node.py server) with the
# windowless interpreter (.venv\Scripts\pythonw.exe) and NO console window.
#
# Why pythonw.exe? python.exe is a console-subsystem binary and allocates
# its own console even under CreateProcess + CREATE_NO_WINDOW in this
# environment (verified operationally). pythonw.exe is the GUI-subsystem
# build: it never allocates a console. Task Scheduler keeps calling
# PowerShell (direct pythonw.exe as a task action proved unreliable), and
# PowerShell supervises the pythonw.exe child below. The child's std
# handles are redirected to NUL (pythonw has no console; without valid
# handles it dies on the first stdout/stderr write).
# Native Windows only: no extra software, no new Python dependencies.
#
# Location-independent: the project root is derived from this script's own
# path (scripts\windows\ -> two levels up). Does not touch .env or any
# runtime configuration.
#
# The launcher supervises the child (waits + propagates its exit code) so
# Task Scheduler failure/restart semantics keep working.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$rootDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$pythonExe = Join-Path $rootDir '.venv\Scripts\pythonw.exe'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Error "Interpreter not found: $pythonExe"
    exit 1
}

Add-Type -Namespace Jarvis -Name Native -MemberDefinition @'
    [System.Runtime.InteropServices.StructLayout(
        System.Runtime.InteropServices.LayoutKind.Sequential,
        CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    public struct STARTUPINFO {
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX;
        public int dwY;
        public int dwXSize;
        public int dwYSize;
        public int dwXCountChars;
        public int dwYCountChars;
        public int dwFillAttribute;
        public int dwFlags;
        public short wShowWindow;
        public short cbReserved2;
        public System.IntPtr lpReserved2;
        public System.IntPtr hStdInput;
        public System.IntPtr hStdOutput;
        public System.IntPtr hStdError;
    }

    [System.Runtime.InteropServices.StructLayout(
        System.Runtime.InteropServices.LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION {
        public System.IntPtr hProcess;
        public System.IntPtr hThread;
        public int dwProcessId;
        public int dwThreadId;
    }

    [System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true,
        CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    public static extern bool CreateProcess(
        string lpApplicationName,
        System.Text.StringBuilder lpCommandLine,
        System.IntPtr lpProcessAttributes,
        System.IntPtr lpThreadAttributes,
        bool bInheritHandles,
        uint dwCreationFlags,
        System.IntPtr lpEnvironment,
        string lpCurrentDirectory,
        ref STARTUPINFO lpStartupInfo,
        out PROCESS_INFORMATION lpProcessInformation);

    [System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint WaitForSingleObject(
        System.IntPtr hHandle, uint dwMilliseconds);

    [System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool GetExitCodeProcess(
        System.IntPtr hProcess, out uint lpExitCode);

    [System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool CloseHandle(System.IntPtr hObject);

    [System.Runtime.InteropServices.StructLayout(
        System.Runtime.InteropServices.LayoutKind.Sequential)]
    public struct SECURITY_ATTRIBUTES {
        public int nLength;
        public System.IntPtr lpSecurityDescriptor;
        public bool bInheritHandle;
    }

    [System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true,
        CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    public static extern System.IntPtr CreateFile(
        string lpFileName,
        uint dwDesiredAccess,
        uint dwShareMode,
        ref SECURITY_ATTRIBUTES lpSecurityAttributes,
        uint dwCreationDisposition,
        uint dwFlagsAndAttributes,
        System.IntPtr hTemplateFile);
'@

$CREATE_NO_WINDOW = 0x08000000
$STARTF_USESHOWWINDOW = 0x00000001
$STARTF_USESTDHANDLES = 0x00000100
$SW_HIDE = 0
$INFINITE = [uint32]4294967295

$si = New-Object Jarvis.Native+STARTUPINFO
$si.cb = [System.Runtime.InteropServices.Marshal]::SizeOf($si)
$si.dwFlags = $STARTF_USESHOWWINDOW -bor $STARTF_USESTDHANDLES
$si.wShowWindow = $SW_HIDE

# pythonw.exe has no console: without valid std handles the child dies on
# its first stdout/stderr write (Uvicorn startup logging). Redirect std
# handles to NUL with an inheritable handle.
$sa = New-Object Jarvis.Native+SECURITY_ATTRIBUTES
$sa.nLength = [System.Runtime.InteropServices.Marshal]::SizeOf($sa)
$sa.bInheritHandle = $true
$nulHandle = [Jarvis.Native]::CreateFile(
    'NUL', [uint32]3221225472, 7, [ref]$sa, 3, 0, [System.IntPtr]::Zero)
if ($nulHandle -eq [System.IntPtr]::Zero -or $nulHandle.ToInt64() -eq -1) {
    Write-Error 'Failed to open NUL for std handle redirection'
    exit 1
}
$si.hStdInput = $nulHandle
$si.hStdOutput = $nulHandle
$si.hStdError = $nulHandle

$pi = New-Object Jarvis.Native+PROCESS_INFORMATION
$cmdLine = New-Object System.Text.StringBuilder(
    '"' + $pythonExe + '" "scripts\run_node.py" server')

# Child-only environment: inherit everything, override JARVIS_DEBUG=false
# for the child only (pythonw + JARVIS_DEBUG=true hangs in StatReload).
# Serialized as a UTF-16 double-null-terminated block for CreateProcess.
$CREATE_UNICODE_ENVIRONMENT = 0x00000400
$childEnv = [System.Collections.Generic.SortedDictionary[string,string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase)
foreach ($entry in [System.Environment]::GetEnvironmentVariables().GetEnumerator()) {
    $childEnv[[string]$entry.Key] = [string]$entry.Value
}
$childEnv['JARVIS_DEBUG'] = 'false'
$envBytes = [System.Collections.Generic.List[byte]]::new()
foreach ($pair in $childEnv.GetEnumerator()) {
    $envBytes.AddRange([System.Text.Encoding]::Unicode.GetBytes(
        $pair.Key + '=' + $pair.Value + "`0"))
}
$envBytes.AddRange([byte[]](0, 0))
$envPtr = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($envBytes.Count)
[System.Runtime.InteropServices.Marshal]::Copy($envBytes.ToArray(), 0, $envPtr, $envBytes.Count)

try {
    $ok = [Jarvis.Native]::CreateProcess(
        $pythonExe, $cmdLine,
        [System.IntPtr]::Zero, [System.IntPtr]::Zero,
        $true, ($CREATE_NO_WINDOW -bor $CREATE_UNICODE_ENVIRONMENT), $envPtr,
        $rootDir, [ref]$si, [ref]$pi)
}
finally {
    # The child inherited its own reference; the parent closes its copy
    # exactly once, on both success and failure paths.
    [void][Jarvis.Native]::CloseHandle($nulHandle)
    [System.Runtime.InteropServices.Marshal]::FreeHGlobal($envPtr)
}

if (-not $ok) {
    $err = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
    Write-Error "CreateProcess failed (Win32 error $err)"
    exit 1
}

try {
    [void][Jarvis.Native]::WaitForSingleObject($pi.hProcess, $INFINITE)
    $exitCode = [uint32]0
    if (-not [Jarvis.Native]::GetExitCodeProcess($pi.hProcess, [ref]$exitCode)) {
        Write-Error 'GetExitCodeProcess failed'
        exit 1
    }
    exit [int]$exitCode
}
finally {
    [void][Jarvis.Native]::CloseHandle($pi.hProcess)
    [void][Jarvis.Native]::CloseHandle($pi.hThread)
}
