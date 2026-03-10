"""Compatibility shim for socket implementations missing sendmsg.

Some environments (gevent/eventlet) replace the standard socket with a
GreenSocket class that doesn't implement sendmsg. Certain libraries
(optionally pyarrow, multiprocessing, or internal IPC helpers) expect
socket.sendmsg to exist. To avoid runtime crashes in those environments
we add a safe shim that provides a minimal sendmsg implementation.

This shim is conservative: it only defines sendmsg when missing and
implements it by concatenating the buffers and delegating to send/sendto.
It avoids changing behavior when sendmsg is already present.
"""
from __future__ import annotations

import logging
import socket
from typing import Iterable, Tuple, Any

logger = logging.getLogger("socket_compat")


def _make_sendmsg_method(sock_cls):
    """Return a sendmsg implementation suitable for sock_cls.

    The simplified sendmsg concatenates buffers and calls send or sendto.
    This is not a full replacement for ancillary data; it's a pragmatic
    fallback for environments where sendmsg is only used for simple sends.
    """

    def sendmsg(self, buffers: Iterable[bytes], ancdata: Any = None, flags: int = 0, address: Any = None):
        # Concatenate bytes-like buffers
        try:
            data = b"".join(buffers)
        except TypeError:
            # If buffers is a single bytes object, allow it
            data = buffers if isinstance(buffers, (bytes, bytearray)) else bytes(buffers)

        if address is not None:
            # For connected UDP/AF_UNIX sockets we can use sendto
            return self.sendto(data, flags, address)

        # Default: use send with flags if supported (some sockets ignore flags)
        try:
            return self.send(data, flags)
        except TypeError:
            return self.send(data)

    return sendmsg


def ensure_sendmsg_compat():
    """Ensure socket classes have a sendmsg method when missing.

    This will attempt to patch:
      - the builtin socket.socket class
      - gevent.socket.GreenSocket (if gevent is installed)
    """
    patched = []

    # Patch stdlib socket.socket if missing
    try:
        if not hasattr(socket.socket, "sendmsg"):
            setattr(socket.socket, "sendmsg", _make_sendmsg_method(socket.socket))
            patched.append("socket.socket")
    except Exception as e:
        logger.debug("Failed to patch socket.socket: %s", e)

    # Try gevent's GreenSocket if available
    try:
        import gevent.socket as gsocket

        gsock = getattr(gsocket, "GreenSocket", None)
        if gsock is not None and not hasattr(gsock, "sendmsg"):
            setattr(gsock, "sendmsg", _make_sendmsg_method(gsock))
            patched.append("gevent.GreenSocket")
    except Exception:
        # gevent not installed or patch failed — ignore silently
        pass

    if patched:
        logger.info("Applied sendmsg compatibility shim to: %s", ", ".join(patched))


if __name__ == "__main__":
    ensure_sendmsg_compat()
