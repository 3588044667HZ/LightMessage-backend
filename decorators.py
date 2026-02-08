import datetime

from global_proxy import request

import functools
import datetime
from typing import Callable, Any

from global_proxy import request


def need_login(func: Callable) -> Callable:
    """
    登录验证装饰器（正确版本）
    使用示例：
        @server.route("/protected")
        @need_login
        async def protected_handler():
            return {"message": "认证成功"}
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        # 获取token（支持多种方式）
        data = request.data

        # 方式1：从data中获取
        token = data.get('token')

        # 方式2：从headers中获取（如果支持）
        # token = request.headers.get('Authorization', '').replace('Bearer ', '')

        if not token:
            return {
                "endpoint": "/error",
                "data": {
                    "message": "缺少token",
                    "code": 401
                },
                "timestamp": int(datetime.datetime.now().timestamp())
            }

        # 验证token
        if not request.server.jwt_manager.verify_token(token):
            return {
                "endpoint": "/error",
                "data": {
                    "message": "token无效或已过期",
                    "code": 401
                },
                "timestamp": int(datetime.datetime.now().timestamp())
            }

        # 认证通过，执行原函数
        return await func(*args, **kwargs)

    return wrapper  # ✅ 返回包装函数，而不是调用结果
