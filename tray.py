"""Ícone da bandeja via API Win32, sem dependências adicionais."""
import atexit
import ctypes
import os
import sys
import webbrowser
from ctypes import wintypes as w
from pathlib import Path

TITLE = "Emulador EscBematech"
CLASS_PREFIX = "EscBematechTray_"
OPEN_HISTORY, EXIT = 1, 2
WM_COMMAND, WM_CLOSE, WM_DESTROY = 0x111, 0x10, 2
WM_TRAY = 0x8001
WM_LBUTTONDBLCLK, WM_RBUTTONUP, WM_CONTEXTMENU = 0x203, 0x205, 0x7b
NIM_ADD, NIM_DELETE = 0, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
MF_SEPARATOR, TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x800, 0x2, 0x100
IMAGE_ICON, LR_LOADFROMFILE, MB_ICONERROR = 1, 0x10, 0x10
SM_CXSMICON = 49
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
ATTACH_PARENT_PROCESS, TH32CS_SNAPPROCESS = 0xffffffff, 2
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HANDLE),
                ("hCursor", w.HANDLE), ("hbrBackground", w.HANDLE),
                ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                ("uCallbackMessage", w.UINT), ("hIcon", w.HANDLE), ("szTip", w.WCHAR * 128),
                ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
                ("uTimeoutOrVersion", w.UINT), ("szInfoTitle", w.WCHAR * 64),
                ("dwInfoFlags", w.DWORD), ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", w.HANDLE)]


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", w.DWORD),
                ("cntThreads", w.DWORD), ("th32ParentProcessID", w.DWORD), ("pcPriClassBase", w.LONG),
                ("dwFlags", w.DWORD), ("szExeFile", w.WCHAR * 260)]


def api(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype, function.argtypes = result, arguments
    return function


user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
GetModuleHandle = api(kernel32, "GetModuleHandleW", w.HINSTANCE, w.LPCWSTR)
RegisterClass = api(user32, "RegisterClassW", w.ATOM, ctypes.POINTER(WNDCLASS))
UnregisterClass = api(user32, "UnregisterClassW", w.BOOL, w.LPCWSTR, w.HINSTANCE)
CreateWindow = api(user32, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR,
                   w.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                   w.HWND, w.HANDLE, w.HINSTANCE, w.LPVOID)
DefWindowProc = api(user32, "DefWindowProcW", ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
DestroyWindow = api(user32, "DestroyWindow", w.BOOL, w.HWND)
PostQuitMessage = api(user32, "PostQuitMessage", None, ctypes.c_int)
GetMessage = api(user32, "GetMessageW", ctypes.c_int, ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
TranslateMessage = api(user32, "TranslateMessage", w.BOOL, ctypes.POINTER(w.MSG))
DispatchMessage = api(user32, "DispatchMessageW", ctypes.c_ssize_t, ctypes.POINTER(w.MSG))
NotifyIcon = api(shell32, "Shell_NotifyIconW", w.BOOL, w.DWORD, ctypes.POINTER(NOTIFYICONDATA))
LoadImage = api(user32, "LoadImageW", w.HANDLE, w.HINSTANCE, w.LPCWSTR, w.UINT,
                ctypes.c_int, ctypes.c_int, w.UINT)
DestroyIcon = api(user32, "DestroyIcon", w.BOOL, w.HANDLE)
CreatePopupMenu = api(user32, "CreatePopupMenu", w.HANDLE)
AppendMenu = api(user32, "AppendMenuW", w.BOOL, w.HANDLE, w.UINT, ctypes.c_size_t, w.LPCWSTR)
SetMenuDefaultItem = api(user32, "SetMenuDefaultItem", w.BOOL, w.HANDLE, w.UINT, w.UINT)
TrackPopupMenu = api(user32, "TrackPopupMenu", w.UINT, w.HANDLE, w.UINT, ctypes.c_int,
                     ctypes.c_int, ctypes.c_int, w.HWND, ctypes.POINTER(w.RECT))
DestroyMenu = api(user32, "DestroyMenu", w.BOOL, w.HANDLE)
GetCursorPos = api(user32, "GetCursorPos", w.BOOL, ctypes.POINTER(w.POINT))
SetForegroundWindow = api(user32, "SetForegroundWindow", w.BOOL, w.HWND)
PostMessage = api(user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
RegisterWindowMessage = api(user32, "RegisterWindowMessageW", w.UINT, w.LPCWSTR)
MessageBox = api(user32, "MessageBoxW", ctypes.c_int, w.HWND, w.LPCWSTR, w.LPCWSTR, w.UINT)
GetSystemMetrics = api(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
AttachConsole = api(kernel32, "AttachConsole", w.BOOL, w.DWORD)
AllocConsole = api(kernel32, "AllocConsole", w.BOOL)
SetConsoleCtrlHandler = api(kernel32, "SetConsoleCtrlHandler", w.BOOL, ctypes.c_void_p, w.BOOL)
CreateToolhelp32Snapshot = api(kernel32, "CreateToolhelp32Snapshot", w.HANDLE, w.DWORD, w.DWORD)
Process32First = api(kernel32, "Process32FirstW", w.BOOL, w.HANDLE, ctypes.POINTER(PROCESSENTRY32))
Process32Next = api(kernel32, "Process32NextW", w.BOOL, w.HANDLE, ctypes.POINTER(PROCESSENTRY32))
CloseHandle = api(kernel32, "CloseHandle", w.BOOL, w.HANDLE)


def enable_dpi_awareness():
    # Sem isso o Windows estica ícone e menu como imagem em escalas acima de 100%.
    # Falha em silêncio se o modo já foi definido ou o Windows for anterior ao 10 1703.
    if hasattr(user32, "SetProcessDpiAwarenessContext"):
        set_context = api(user32, "SetProcessDpiAwarenessContext", w.BOOL, w.HANDLE)
        set_context(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)


def parent_pid(pid):
    snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, INVALID_HANDLE_VALUE):
        return 0
    try:
        entry = PROCESSENTRY32(dwSize=ctypes.sizeof(PROCESSENTRY32))
        found = Process32First(snapshot, ctypes.byref(entry))
        while found:
            if entry.th32ProcessID == pid:
                return entry.th32ParentProcessID
            found = Process32Next(snapshot, ctypes.byref(entry))
        return 0
    finally:
        CloseHandle(snapshot)


def ensure_console(own_window=False):
    if sys.stdout is not None:
        return
    # No .exe de arquivo único, o pai é o lançador do PyInstaller, que não tem
    # console; o terminal que executou o programa é o avô.
    attached = not own_window and (AttachConsole(ATTACH_PARENT_PROCESS)
                                   or AttachConsole(parent_pid(os.getppid())))
    if not attached and not AllocConsole():
        raise ctypes.WinError(ctypes.get_last_error())
    # O lançador ignora Ctrl+C e o processo do Python herda isso; sem religar,
    # o modo console não encerra pelo teclado.
    SetConsoleCtrlHandler(None, False)
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    sys.stdin = open("CONIN$", "r", encoding="utf-8")
    if not attached:
        atexit.register(input, "\nPressione Enter para fechar.")


def show_error(message):
    enable_dpi_awareness()
    MessageBox(None, message, TITLE, MB_ICONERROR)


def run_tray(url, port=None, open_browser=None):
    open_browser = open_browser or webbrowser.open
    enable_dpi_awareness()
    instance = GetModuleHandle(None)
    class_name = CLASS_PREFIX + str(os.getpid())
    # O sistema pede 16 px a 100%, 24 a 150% e 32 a 200%.
    size = GetSystemMetrics(SM_CXSMICON)
    icon = LoadImage(None, str(Path(__file__).with_name("printer.ico")), IMAGE_ICON, size, size, LR_LOADFROMFILE)
    if not icon:
        raise ctypes.WinError(ctypes.get_last_error())
    window, registered, visible = None, False, False
    taskbar_created = RegisterWindowMessage("TaskbarCreated")
    tip = f"{TITLE} · porta {port}" if port else TITLE
    data = NOTIFYICONDATA(cbSize=ctypes.sizeof(NOTIFYICONDATA), uID=1, uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP,
                          uCallbackMessage=WM_TRAY, hIcon=icon, szTip=tip)
    callback_errors = []

    def command(hwnd, selected):
        if selected == OPEN_HISTORY:
            if not open_browser(url):
                show_error(f"Não foi possível abrir o navegador. Acesse {url}")
        elif selected == EXIT:
            DestroyWindow(hwnd)

    def popup(hwnd):
        menu = CreatePopupMenu()
        if not menu:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            AppendMenu(menu, 0, OPEN_HISTORY, "Abrir histórico")
            AppendMenu(menu, MF_SEPARATOR, 0, None)
            AppendMenu(menu, 0, EXIT, "Sair")
            SetMenuDefaultItem(menu, OPEN_HISTORY, 0)
            point = w.POINT()
            GetCursorPos(ctypes.byref(point))
            SetForegroundWindow(hwnd)
            selected = TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, point.x, point.y, 0, hwnd, None)
            PostMessage(hwnd, 0, 0, 0)  # Permite ao menu fechar ao clicar fora.
            command(hwnd, selected)
        finally:
            DestroyMenu(menu)

    @WNDPROC
    def window_proc(hwnd, message, wp, lp):
        try:
            if message == WM_TRAY:
                if lp == WM_LBUTTONDBLCLK:
                    command(hwnd, OPEN_HISTORY)
                elif lp in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    popup(hwnd)
                return 0
            if message == WM_COMMAND:
                command(hwnd, wp & 0xffff)
                return 0
            if message == WM_CLOSE:
                DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                NotifyIcon(NIM_DELETE, ctypes.byref(data))
                PostQuitMessage(0)
                return 0
            if message == taskbar_created:
                if not NotifyIcon(NIM_ADD, ctypes.byref(data)):
                    raise RuntimeError("Não foi possível restaurar o ícone na bandeja.")
                return 0
            return DefWindowProc(hwnd, message, wp, lp)
        except Exception as error:
            callback_errors.append(error)
            PostQuitMessage(1)
            return 0

    try:
        definition = WNDCLASS(lpfnWndProc=window_proc, hInstance=instance, lpszClassName=class_name)
        if not RegisterClass(ctypes.byref(definition)):
            raise ctypes.WinError(ctypes.get_last_error())
        registered = True
        # Janela invisível recebe as mensagens do Explorer e do menu.
        window = CreateWindow(0, class_name, TITLE, 0, 0, 0, 0, 0, None, None, instance, None)
        if not window:
            raise ctypes.WinError(ctypes.get_last_error())
        data.hWnd = window
        if not NotifyIcon(NIM_ADD, ctypes.byref(data)):
            raise RuntimeError("Não foi possível criar o ícone na bandeja do Windows.")
        visible = True
        message = w.MSG()
        while True:
            result = GetMessage(ctypes.byref(message), None, 0, 0)
            if result == -1:
                raise ctypes.WinError(ctypes.get_last_error())
            if result == 0:
                break
            TranslateMessage(ctypes.byref(message))
            DispatchMessage(ctypes.byref(message))
        if callback_errors:
            raise callback_errors[0]
    finally:
        if visible:
            NotifyIcon(NIM_DELETE, ctypes.byref(data))
        if window:
            DestroyWindow(window)
        if registered:
            UnregisterClass(class_name, instance)
        DestroyIcon(icon)
