"""Ícone da bandeja via API Win32, sem dependências adicionais."""

import atexit
import ctypes
import os
import sys
import webbrowser
from ctypes import wintypes
from pathlib import Path

TITLE = "Emulador EscBematech"
CLASS_PREFIX = "EscBematechTray_"
ICON_PATH = Path(__file__).with_name("printer.ico")

OPEN_HISTORY = 1
EXIT = 2

WM_CLOSE = 0x10
WM_COMMAND = 0x111
WM_CONTEXTMENU = 0x7B
WM_DESTROY = 0x2
WM_LBUTTONDBLCLK = 0x203
WM_RBUTTONUP = 0x205
WM_TRAY = 0x8001

NIM_ADD = 0
NIM_DELETE = 2
NIF_MESSAGE = 0x1
NIF_ICON = 0x2
NIF_TIP = 0x4

MF_SEPARATOR = 0x800
TPM_RIGHTBUTTON = 0x2
TPM_RETURNCMD = 0x100

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x10
MB_ICONERROR = 0x10
SM_CXSMICON = 49
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

ATTACH_PARENT_PROCESS = 0xFFFFFFFF
TH32CS_SNAPPROCESS = 0x2
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HANDLE),
    ]


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def api(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

HWND = wintypes.HWND
HANDLE = wintypes.HANDLE
UINT = wintypes.UINT
BOOL = wintypes.BOOL
DWORD = wintypes.DWORD
LPCWSTR = wintypes.LPCWSTR
INT = ctypes.c_int
MESSAGE_POINTER = ctypes.POINTER(wintypes.MSG)

GetModuleHandle = api(kernel32, "GetModuleHandleW", wintypes.HINSTANCE, LPCWSTR)
RegisterClass = api(user32, "RegisterClassW", wintypes.ATOM, ctypes.POINTER(WNDCLASS))
UnregisterClass = api(user32, "UnregisterClassW", BOOL, LPCWSTR, wintypes.HINSTANCE)
CreateWindow = api(
    user32,
    "CreateWindowExW",
    HWND,
    *(DWORD, LPCWSTR, LPCWSTR, DWORD, INT, INT, INT, INT, HWND, HANDLE, wintypes.HINSTANCE, wintypes.LPVOID),
)
DefWindowProc = api(user32, "DefWindowProcW", ctypes.c_ssize_t, HWND, UINT, wintypes.WPARAM, wintypes.LPARAM)
DestroyWindow = api(user32, "DestroyWindow", BOOL, HWND)
PostQuitMessage = api(user32, "PostQuitMessage", None, INT)
GetMessage = api(user32, "GetMessageW", INT, MESSAGE_POINTER, HWND, UINT, UINT)
TranslateMessage = api(user32, "TranslateMessage", BOOL, MESSAGE_POINTER)
DispatchMessage = api(user32, "DispatchMessageW", ctypes.c_ssize_t, MESSAGE_POINTER)
PostMessage = api(user32, "PostMessageW", BOOL, HWND, UINT, wintypes.WPARAM, wintypes.LPARAM)
RegisterWindowMessage = api(user32, "RegisterWindowMessageW", UINT, LPCWSTR)

NotifyIcon = api(shell32, "Shell_NotifyIconW", BOOL, DWORD, ctypes.POINTER(NOTIFYICONDATA))
LoadImage = api(user32, "LoadImageW", HANDLE, wintypes.HINSTANCE, LPCWSTR, UINT, INT, INT, UINT)
DestroyIcon = api(user32, "DestroyIcon", BOOL, HANDLE)
GetSystemMetrics = api(user32, "GetSystemMetrics", INT, INT)

CreatePopupMenu = api(user32, "CreatePopupMenu", HANDLE)
AppendMenu = api(user32, "AppendMenuW", BOOL, HANDLE, UINT, ctypes.c_size_t, LPCWSTR)
SetMenuDefaultItem = api(user32, "SetMenuDefaultItem", BOOL, HANDLE, UINT, UINT)
TrackPopupMenu = api(user32, "TrackPopupMenu", UINT, HANDLE, UINT, INT, INT, INT, HWND, ctypes.POINTER(wintypes.RECT))
DestroyMenu = api(user32, "DestroyMenu", BOOL, HANDLE)
GetCursorPos = api(user32, "GetCursorPos", BOOL, ctypes.POINTER(wintypes.POINT))
SetForegroundWindow = api(user32, "SetForegroundWindow", BOOL, HWND)
MessageBox = api(user32, "MessageBoxW", INT, HWND, LPCWSTR, LPCWSTR, UINT)

AttachConsole = api(kernel32, "AttachConsole", BOOL, DWORD)
AllocConsole = api(kernel32, "AllocConsole", BOOL)
SetConsoleCtrlHandler = api(kernel32, "SetConsoleCtrlHandler", BOOL, ctypes.c_void_p, BOOL)
CreateToolhelp32Snapshot = api(kernel32, "CreateToolhelp32Snapshot", HANDLE, DWORD, DWORD)
Process32First = api(kernel32, "Process32FirstW", BOOL, HANDLE, ctypes.POINTER(PROCESSENTRY32))
Process32Next = api(kernel32, "Process32NextW", BOOL, HANDLE, ctypes.POINTER(PROCESSENTRY32))
CloseHandle = api(kernel32, "CloseHandle", BOOL, HANDLE)


def last_error():
    return ctypes.WinError(ctypes.get_last_error())


def enable_dpi_awareness():
    # Sem isso o Windows estica ícone e menu como imagem em escalas acima de 100%.
    # Falha em silêncio se o modo já foi definido ou o Windows for anterior ao 10 1703.
    if hasattr(user32, "SetProcessDpiAwarenessContext"):
        set_context = api(user32, "SetProcessDpiAwarenessContext", BOOL, HANDLE)
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
    attached = not own_window and (AttachConsole(ATTACH_PARENT_PROCESS) or AttachConsole(parent_pid(os.getppid())))
    if not attached and not AllocConsole():
        raise last_error()

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


def load_tray_icon():
    # O sistema pede 16 px a 100%, 24 a 150% e 32 a 200%.
    size = GetSystemMetrics(SM_CXSMICON)

    icon = LoadImage(None, str(ICON_PATH), IMAGE_ICON, size, size, LR_LOADFROMFILE)
    if not icon:
        raise last_error()

    return icon


def run_tray(url, port=None, open_browser=None):
    open_browser = open_browser or webbrowser.open
    enable_dpi_awareness()

    instance = GetModuleHandle(None)
    class_name = CLASS_PREFIX + str(os.getpid())
    taskbar_created = RegisterWindowMessage("TaskbarCreated")
    icon = load_tray_icon()

    icon_data = NOTIFYICONDATA(
        cbSize=ctypes.sizeof(NOTIFYICONDATA),
        uID=1,
        uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP,
        uCallbackMessage=WM_TRAY,
        hIcon=icon,
        szTip=f"{TITLE} · porta {port}" if port else TITLE,
    )
    window = None
    registered = False
    visible = False
    callback_errors = []

    def run_command(hwnd, selected):
        if selected == OPEN_HISTORY:
            if not open_browser(url):
                show_error(f"Não foi possível abrir o navegador. Acesse {url}")
        elif selected == EXIT:
            DestroyWindow(hwnd)

    def show_menu(hwnd):
        menu = CreatePopupMenu()
        if not menu:
            raise last_error()

        try:
            AppendMenu(menu, 0, OPEN_HISTORY, "Abrir histórico")
            AppendMenu(menu, MF_SEPARATOR, 0, None)
            AppendMenu(menu, 0, EXIT, "Sair")
            SetMenuDefaultItem(menu, OPEN_HISTORY, 0)

            cursor = wintypes.POINT()
            GetCursorPos(ctypes.byref(cursor))
            SetForegroundWindow(hwnd)
            selected = TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, cursor.x, cursor.y, 0, hwnd, None)
            PostMessage(hwnd, 0, 0, 0)  # Permite ao menu fechar ao clicar fora.

            run_command(hwnd, selected)
        finally:
            DestroyMenu(menu)

    @WNDPROC
    def window_procedure(hwnd, message, wparam, lparam):
        try:
            if message == WM_TRAY:
                if lparam == WM_LBUTTONDBLCLK:
                    run_command(hwnd, OPEN_HISTORY)
                elif lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    show_menu(hwnd)
                return 0

            if message == WM_COMMAND:
                run_command(hwnd, wparam & 0xFFFF)
                return 0

            if message == WM_CLOSE:
                DestroyWindow(hwnd)
                return 0

            if message == WM_DESTROY:
                NotifyIcon(NIM_DELETE, ctypes.byref(icon_data))
                PostQuitMessage(0)
                return 0

            if message == taskbar_created:
                if not NotifyIcon(NIM_ADD, ctypes.byref(icon_data)):
                    raise RuntimeError("Não foi possível restaurar o ícone na bandeja.")
                return 0

            return DefWindowProc(hwnd, message, wparam, lparam)
        except Exception as error:
            callback_errors.append(error)
            PostQuitMessage(1)
            return 0

    try:
        window_class = WNDCLASS(lpfnWndProc=window_procedure, hInstance=instance, lpszClassName=class_name)
        if not RegisterClass(ctypes.byref(window_class)):
            raise last_error()
        registered = True

        # Janela invisível recebe as mensagens do Explorer e do menu.
        window = CreateWindow(0, class_name, TITLE, 0, 0, 0, 0, 0, None, None, instance, None)
        if not window:
            raise last_error()

        icon_data.hWnd = window
        if not NotifyIcon(NIM_ADD, ctypes.byref(icon_data)):
            raise RuntimeError("Não foi possível criar o ícone na bandeja do Windows.")
        visible = True

        message = wintypes.MSG()
        while True:
            result = GetMessage(ctypes.byref(message), None, 0, 0)
            if result == -1:
                raise last_error()
            if result == 0:
                break

            TranslateMessage(ctypes.byref(message))
            DispatchMessage(ctypes.byref(message))

        if callback_errors:
            raise callback_errors[0]
    finally:
        if visible:
            NotifyIcon(NIM_DELETE, ctypes.byref(icon_data))
        if window:
            DestroyWindow(window)
        if registered:
            UnregisterClass(class_name, instance)
        DestroyIcon(icon)
