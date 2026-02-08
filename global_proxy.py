"""
模仿 Flask 的 current_app, request, g 等全局对象
"""
from typing import Optional

import IMWebSocketServer
# 导入上下文变量
from context import _request_ctx_var, _app_ctx_var, RequestContext, AppContext


class _RequestContextProxy:
    """request 上下文代理（类似 Flask 的 request）"""

    def __getattr__(self, name):
        ctx = _request_ctx_var.get()
        if ctx is None:
            raise RuntimeError(
                "Working outside of request context. "
                "Did you forget to create a RequestContext?"
            )
        return getattr(ctx, name)

    def __setattr__(self, name, value):
        ctx = _request_ctx_var.get()
        if ctx is None:
            raise RuntimeError(
                "Working outside of request context. "
                "Did you forget to create a RequestContext?"
            )
        setattr(ctx, name, value)

    @property
    def data(self):
        """快捷访问请求数据"""
        ctx = _request_ctx_var.get()
        if ctx is None:
            raise RuntimeError("Working outside of request context.")
        return ctx.request_data.get("data", {})

    @property
    def endpoint(self):
        """快捷访问 endpoint"""
        ctx = _request_ctx_var.get()
        if ctx is None:
            raise RuntimeError("Working outside of request context.")
        return ctx.request_data.get("endpoint", "")

    @property
    def group_manager(self):
        """获取群组管理器"""
        server = self.server
        if hasattr(server, 'group_manager'):
            return server.group_manager
        return None

    @property
    def is_group_member(self) -> bool:
        """检查当前用户是否是某群成员"""
        group_id = self.data.get("group_id")
        user_id = self.user_id

        if not group_id or not user_id or not self.group_manager:
            return False

        return self.group_manager.is_member(group_id, user_id)

    @property
    def group_role(self) -> Optional[str]:
        """获取当前用户在群中的角色"""
        group_id = self.data.get("group_id")
        user_id = self.user_id

        if not group_id or not user_id or not self.group_manager:
            return None

        role = self.group_manager.get_member_role(group_id, user_id)
        return role.value if role else None

    @property
    def server(self) -> IMWebSocketServer.IMWebSocketServer:
        """快捷访问请求数据"""
        ctx = _request_ctx_var.get()
        if ctx is None:
            raise RuntimeError("Working outside of request context.")
        return ctx.get("server", {})


class _AppContextProxy:
    """app 上下文代理（类似 Flask 的 current_app）"""

    def __getattr__(self, name):
        ctx = _app_ctx_var.get()
        if ctx is None:
            raise RuntimeError(
                "Working outside of application context. "
                "Did you forget to create an AppContext?"
            )
        return getattr(ctx.server, name)

    @property
    def server(self):
        """获取服务器实例"""
        ctx = _app_ctx_var.get()
        if ctx is None:
            raise RuntimeError("Working outside of application context.")
        return ctx.server


class _GlobalContextProxy:
    """全局上下文（类似 Flask 的 g）"""

    def __init__(self):
        self._data = {}

    def __getattr__(self, name):
        return self._data.get(name)

    def __setattr__(self, name, value):
        if name == '_data':
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def get(self, name, default=None):
        return self._data.get(name, default)

    def set(self, name, value):
        self._data[name] = value


# 创建全局代理对象
request = _RequestContextProxy()
current_app = _AppContextProxy()
g = _GlobalContextProxy()


# 快捷访问器
def get_request_context() -> Optional[RequestContext]:
    """获取当前请求上下文"""
    return _request_ctx_var.get()


def get_app_context() -> Optional[AppContext]:
    """获取当前应用上下文"""
    return _app_ctx_var.get()

# 在 global_proxy.py 中添加群聊相关的快捷方法
