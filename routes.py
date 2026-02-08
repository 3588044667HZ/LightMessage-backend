# routes.py
"""
完全 Flask 风格的路由定义
无需显式传递任何上下文参数
"""
import asyncio
import datetime
import uuid
from typing import Dict, Any

# 导入装饰器和全局对象
from decorators import route, before_request, after_request, login_required
from global_proxy import request, current_app, g
from enums import UserStatus, MessageType


# ========== 钩子函数 ==========

@before_request
async def before_each_request():
    """每个请求前执行（类似 Flask before_request）"""
    # 记录请求开始时间
    g.request_start_time = asyncio.get_event_loop().time()

    # 更新活动时间
    if request.connection_id:
        current_app.connection_manager.update_activity(request.connection_id)


@after_request
async def after_each_request(response: Dict[str, Any]) -> Dict[str, Any]:
    """每个请求后执行（类似 Flask after_request）"""
    # 记录请求处理时间
    if hasattr(g, 'request_start_time'):
        process_time = asyncio.get_event_loop().time() - g.request_start_time
        current_app.logger.debug(f"Request processed in {process_time:.3f}s")

    # 可以在这里修改响应
    if response and 'timestamp' not in response:
        response['timestamp'] = int(datetime.datetime.now().timestamp())

    return response


# ========== 路由定义 ==========

@route("/auth/login", require_auth=False, rate_limit=10)
async def handle_login():
    """登录路由 - 完全 Flask 风格"""
    data = request.data
    userid = data.get("userid")
    password = data.get("password")

    if not userid or not password:
        return {
            "error": "用户名和密码不能为空",
            "code": 400,
            "endpoint": "/auth/login_response"
        }

    # 查找用户
    user = current_app.user_manager.get_user_by_id(userid)
    if not user:
        return {
            "error": "用户不存在",
            "code": 401,
            "endpoint": "/auth/login_response"
        }

    # 验证密码
    if not current_app.user_manager.verify_password(user.user_id, password):
        return {
            "error": "密码错误",
            "code": 401,
            "endpoint": "/auth/login_response"
        }

    # 生成 Token
    token = current_app.jwt_manager.create_token(user.user_id, user.username)

    # 认证连接
    await current_app.connection_manager.authenticate_connection(
        request.connection_id, user.user_id
    )

    # 返回响应
    return {
        "type": "direct",
        "endpoint": "/auth/login_response",
        "data": {
            "user_id": user.user_id,
            "username": user.username,
            "nickname": user.nickname,
            "token": token,
            "expires_in": 86400,
            "user_info": {
                "avatar": user.avatar,
                "department": user.department,
                "status": user.status.value,
                "last_seen": user.last_seen
            }
        },
        "code": 200,
        "actions": [
            {
                "type": "push_offline_messages",
                "user_id": user.user_id
            },
            {
                "type": "notify_contacts_online",
                "user_id": user.user_id
            }
        ]
    }


@route("/message/send", require_auth=True, rate_limit=50)
@login_required
async def handle_send_message():
    """发送消息 - 完全 Flask 风格"""
    data = request.data
    receiver_id = data.get("receiver_id")
    message_type = data.get("type", MessageType.TEXT.value)
    content = data.get("content", {})

    if not receiver_id:
        return {
            "error": "接收者ID不能为空",
            "code": 400,
            "endpoint": "/message/send_response"
        }

    # 检查接收者是否存在
    receiver = current_app.user_manager.get_user_by_id(receiver_id)
    if not receiver:
        return {
            "error": "接收者不存在",
            "code": 404,
            "endpoint": "/message/send_response"
        }

    # 生成消息ID
    message_id = str(uuid.uuid4())
    timestamp = int(datetime.datetime.now().timestamp())

    sender_id = request.user_id
    sender = request.user

    # 构建消息
    receive_message = {
        "endpoint": "/message/receive",
        "data": {
            "message_id": message_id,
            "sender_id": sender_id,
            "sender_info": {
                "user_id": sender_id,
                "username": sender.username,
                "nickname": sender.nickname,
                "avatar": sender.avatar
            },
            "receiver_id": receiver_id,
            "type": message_type,
            "content": content,
            "timestamp": timestamp,
            "client_msg_id": data.get("client_msg_id")
        }
    }

    # 检查接收者是否在线
    delivered = False
    if current_app.connection_manager.is_user_online(receiver_id):
        delivered = await current_app.push_message_to_user(receiver_id, receive_message)

    # 返回响应（包含后续操作）
    return {
        "type": "direct",
        "endpoint": "/message/send_response",
        "data": {
            "client_msg_id": data.get("client_msg_id"),
            "server_msg_id": message_id,
            "delivered": delivered,
            "timestamp": timestamp
        },
        "code": 200 if delivered else 202,
        "actions": [
            {
                "type": "store_offline_message" if not delivered else None,
                "user_id": receiver_id,
                "message": receive_message
            }
        ]
    }


@route("/heartbeat", require_auth=False, rate_limit=1000)
async def handle_heartbeat():
    """心跳处理 - 完全 Flask 风格"""
    # 更新心跳时间
    current_app.connection_manager.update_heartbeat(request.connection_id)

    return {
        "type": "direct",
        "endpoint": "/heartbeat_response",
        "data": {
            "server_timestamp": int(datetime.datetime.now().timestamp()),
            "client_timestamp": request.data.get("timestamp"),
            "status": "alive"
        },
        "code": 200
    }
