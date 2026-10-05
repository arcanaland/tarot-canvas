import ctypes
import ctypes.util
import sys

_ID = ctypes.c_void_p


def _objc():
    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation"))
    objc.objc_getClass.restype = _ID
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = _ID
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    return objc


def _send(objc, restype, *argtypes):
    """objc_msgSend cast to one signature; arm64 needs the exact prototype."""
    proto = ctypes.CFUNCTYPE(restype, _ID, _ID, *argtypes)
    return proto(("objc_msgSend", objc))


def _info_dictionary(objc):
    cls, sel = objc.objc_getClass, objc.sel_registerName
    send = _send(objc, _ID)
    return send(send(cls(b"NSBundle"), sel(b"mainBundle")), sel(b"infoDictionary"))


def _nsstring(objc, text):
    send = _send(objc, _ID, ctypes.c_char_p)
    return send(
        objc.objc_getClass(b"NSString"),
        objc.sel_registerName(b"stringWithUTF8String:"),
        text.encode(),
    )


def set_bundle_name(name, platform=sys.platform):
    """Needed for macOS menu bar when it runs outside bundle."""
    if platform != "darwin":
        return

    objc = _objc()
    info = _info_dictionary(objc)
    if not info:
        return
    _send(objc, None, _ID, _ID)(
        info,
        objc.sel_registerName(b"setObject:forKey:"),
        _nsstring(objc, name),
        _nsstring(objc, "CFBundleName"),
    )


def bundle_name():
    """macOS: the main bundle's CFBundleName or None."""
    objc = _objc()
    info = _info_dictionary(objc)
    value = _send(objc, _ID, _ID)(
        info, objc.sel_registerName(b"objectForKey:"), _nsstring(objc, "CFBundleName")
    )
    if not value:
        return None
    utf8 = _send(objc, ctypes.c_char_p)(value, objc.sel_registerName(b"UTF8String"))
    return utf8.decode()
