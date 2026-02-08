# context.py
import asyncio
import contextvars
from typing import Optional, Any, Dict
import weakref


class RequestContext:
    """请求上下文（类似 Flask 的 request 上下文）"""
    __slots__ = ('_server_ref', '_connection_id', '_request_data',
                 '_cached_connection', '_cached_user', '_cached_user_id', 'request_id')

    def __init__(self, server, connection_id: str, request_data: Dict[str, Any], request_id: str):
        self._server_ref = weakref.ref(server)
        self._connection_id = connection_id
        self._request_data = request_data
        self._cached_connection = None
        self._cached_user = None
        self._cached_user_id = None
        self.request_id = request_id

    @property
    def server(self):
        s = self._server_ref()
        if s is None:
            raise RuntimeError("Server instance has been garbage collected")
        return s

    @property
    def connection_id(self):
        return self._connection_id

    @property
    def request_data(self):
        return self._request_data

    @property
    def connection(self):
        """懒加载连接对象"""
        if self._cached_connection is None:
            self._cached_connection = (
                self.server.connection_manager.get_connection_by_id(self._connection_id)
            )
        return self._cached_connection

    @property
    def websocket(self):
        """懒加载 websocket"""
        conn = self.connection
        return conn.websocket if conn else None

    @property
    def user_id(self):
        """懒加载 user_id"""
        if self._cached_user_id is None:
            conn = self.connection
            self._cached_user_id = conn.user_id if conn else None
        return self._cached_user_id

    @property
    def user(self):
        """懒加载用户对象"""
        if self._cached_user is None and self.user_id:
            self._cached_user = self.server.user_manager.get_user_by_id(self.user_id)
        return self._cached_user

    # 快捷访问器
    @property
    def user_manager(self):
        return self.server.user_manager

    @property
    def connection_manager(self):
        return self.server.connection_manager

    @property
    def jwt_manager(self):
        return self.server.jwt_manager

    @property
    def offline_store(self):
        return self.server.offline_store


class AppContext:
    """应用上下文（类似 Flask 的 app 上下文）"""
    __slots__ = ('_server_ref',)

    def __init__(self, server):
        self._server_ref = weakref.ref(server)

    @property
    def server(self):
        s = self._server_ref()
        if s is None:
            raise RuntimeError("Server instance has been garbage collected")
        return s


# 使用 contextvars 实现异步安全的上下文局部变量
_request_ctx_var: contextvars.ContextVar[Optional[RequestContext]] = contextvars.ContextVar(
    'request_context', default=None
)

_app_ctx_var: contextvars.ContextVar[Optional[AppContext]] = contextvars.ContextVar(
    'app_context', default=None
)


# 上下文管理器
class RequestContextManager:
    """请求上下文管理器"""

    def __init__(self, server, connection_id: str, request_data: Dict[str, Any], request_id: str = None):
        self.server = server
        self.connection_id = connection_id
        self.request_data = request_data
        self.request_id = request_id
        self.request_ctx_token = None
        self.app_ctx_token = None

    async def __aenter__(self):
        # 创建应用上下文
        app_ctx = AppContext(self.server)
        self.app_ctx_token = _app_ctx_var.set(app_ctx)

        # 创建请求上下文
        request_ctx = RequestContext(self.server, self.connection_id, self.request_data, request_id=self.request_id)
        self.request_ctx_token = _request_ctx_var.set(request_ctx)

        return request_ctx

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 清理上下文
        if self.request_ctx_token:
            _request_ctx_var.reset(self.request_ctx_token)

        if self.app_ctx_token:
            _app_ctx_var.reset(self.app_ctx_token)

        return False  # 不抑制异常
