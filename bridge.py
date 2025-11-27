# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Thread Bridge

This module provides a thread-safe way to execute FreeCAD commands from the
MCP server's background thread. FreeCAD's GUI and document operations must
run on the main Qt thread, so we use Qt's signal/slot mechanism to marshal
calls from the background thread to the main thread.

Usage:
    bridge = MainThreadBridge()
    result = await bridge.execute(lambda: FreeCAD.newDocument("Test"))
"""

import asyncio
import concurrent.futures
from typing import Any, Callable, TypeVar
from functools import wraps

# FreeCAD uses PySide2 (or PySide6 in newer versions)
try:
    from PySide2.QtCore import QObject, Signal, Slot, QThread, QCoreApplication, Qt
except ImportError:
    from PySide6.QtCore import QObject, Signal, Slot, QThread, QCoreApplication, Qt

T = TypeVar('T')


class MainThreadBridge(QObject):
    """
    Bridge for executing functions on the main Qt thread from a background thread.
    
    This is necessary because FreeCAD's document operations and GUI updates
    must happen on the main thread. The MCP server runs in a background thread,
    so we need this bridge to safely execute FreeCAD commands.
    """
    
    # Signal to request execution on main thread
    # Arguments: (callable, concurrent.futures.Future)
    _execute_request = Signal(object, object)
    
    def __init__(self):
        super().__init__()
        # Move to main thread if not already there
        app = QCoreApplication.instance()
        if app:
            self.moveToThread(app.thread())
        
        # Connect signal to slot using proper PySide2 syntax
        self._execute_request.connect(self._execute_on_main, Qt.QueuedConnection)
    
    @Slot(object, object)
    def _execute_on_main(self, func: Callable, future: concurrent.futures.Future):
        """
        Execute a function on the main thread and set the result in the future.
        
        This slot is connected with QueuedConnection, so it will always run
        on the main thread regardless of which thread emits the signal.
        """
        if future.cancelled():
            return
            
        try:
            result = func()
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)
    
    def execute_sync(self, func: Callable[[], T], timeout: float = 30.0) -> T:
        """
        Execute a function on the main thread synchronously (blocking).
        
        Args:
            func: A callable that takes no arguments
            timeout: Maximum time to wait for the result (seconds)
        
        Returns:
            The result of calling func()
        
        Raises:
            TimeoutError: If the function doesn't complete within the timeout
            Any exception raised by func
        """
        # Check if we're already on the main thread
        app = QCoreApplication.instance()
        if app and QThread.currentThread() == app.thread():
            # Already on main thread, execute directly
            return func()
        
        # Create a future to receive the result
        future = concurrent.futures.Future()
        
        # Emit signal to request execution on main thread
        self._execute_request.emit(func, future)
        
        # Wait for result
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError(f"Function execution timed out after {timeout} seconds")
    
    async def execute(self, func: Callable[[], T], timeout: float = 30.0) -> T:
        """
        Execute a function on the main thread asynchronously.
        
        This is the async version for use in the MCP server's async handlers.
        
        Args:
            func: A callable that takes no arguments
            timeout: Maximum time to wait for the result (seconds)
        
        Returns:
            The result of calling func()
        
        Raises:
            TimeoutError: If the function doesn't complete within the timeout
            Any exception raised by func
        """
        # Run the synchronous version in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,  # Use default executor
            lambda: self.execute_sync(func, timeout)
        )


# Global bridge instance (created when server starts)
_bridge: MainThreadBridge = None


def get_bridge() -> MainThreadBridge:
    """Get the global MainThreadBridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = MainThreadBridge()
    return _bridge


def reset_bridge():
    """Reset the global bridge (for cleanup on server stop)."""
    global _bridge
    _bridge = None


def run_on_main_thread(func: Callable[[], T]) -> T:
    """
    Convenience function to run a callable on the main thread.
    
    This is a synchronous call that blocks until the function completes.
    
    Args:
        func: A callable that takes no arguments
    
    Returns:
        The result of calling func()
    """
    return get_bridge().execute_sync(func)


async def run_on_main_thread_async(func: Callable[[], T]) -> T:
    """
    Convenience function to run a callable on the main thread asynchronously.
    
    Args:
        func: A callable that takes no arguments
    
    Returns:
        The result of calling func()
    """
    return await get_bridge().execute(func)


def main_thread(func: Callable) -> Callable:
    """
    Decorator to make a function always execute on the main thread.
    
    Usage:
        @main_thread
        def my_freecad_function():
            return FreeCAD.ActiveDocument.Name
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        return run_on_main_thread(lambda: func(*args, **kwargs))
    return wrapper


def main_thread_async(func: Callable) -> Callable:
    """
    Decorator to make an async function execute on the main thread.
    
    Usage:
        @main_thread_async
        async def my_freecad_function():
            return FreeCAD.ActiveDocument.Name
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await run_on_main_thread_async(lambda: func(*args, **kwargs))
    return wrapper
