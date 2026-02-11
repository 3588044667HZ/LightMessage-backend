import datetime
import uuid
from typing import Optional

from IMWebSocketServer import IMWebSocketServer
from enums import UserStatus, MessageType, GroupRole, GroupStatus
from global_proxy import request
from decorators import need_login

server = IMWebSocketServer(
    host="0.0.0.0",
    port=8765,
    heartbeat_timeout=60,  # 60秒心跳超时
    heartbeat_interval=30  # 30秒检查一次
)


@server.route("/auth/login")
async def handle_login():
    """处理登录请求"""
    request.server.connection_manager.get_connection_by_id(request.connection_id)
    login_data = request.data
    print(login_data, "in 27")
    userid = login_data.get("userid")
    password = login_data.get("password")
    login_data.get("device_id", "")

    if not userid or not password:
        return {
            "endpoint": "/auth/login_response",
            "data": {
                "message": "用户名和密码不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 查找用户
    user = await request.server.user_manager.get_user_by_id(userid)
    if not user:
        return {
            "endpoint": "/auth/login_response",
            "data": {
                "message": "用户不存在",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 验证密码
    if not await request.server.user_manager.verify_password(user.user_id, password):
        return {
            "endpoint": "/auth/login_response",
            "data": {
                "message": "密码错误",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 生成Token
    token = request.server.jwt_manager.create_token(user.user_id, user.username)

    # 认证连接
    await request.server.connection_manager.authenticate_connection(request.connection_id, user.user_id)

    # 更新用户状态
    user.status = UserStatus.ONLINE
    user.last_seen = int(datetime.datetime.now().timestamp())

    # 发送登录成功响应
    response = {
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
        "timestamp": int(datetime.datetime.now().timestamp())
    }

    if request.connection_id:
        response["request_id"] = request.connection_id

    return response


@server.route("/auth/logout")
@need_login
async def handle_logout():
    """处理登出请求"""
    connection = request.server.connection_manager.get_connection_by_id(request.connection_id)
    if not connection or not connection.authenticated:
        return {
            "endpoint": "/error",
            "data": {
                "message": "未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    token = request.data.get("data", {}).get("token")
    if token:
        request.server.jwt_manager.revoke_token(token)

    # 发送响应
    response = {
        "endpoint": "/auth/logout_response",
        "data": {
            "message": "登出成功"
        },
        "code": 200
    }

    await request.server.cleanup_connection(request.connection_id)

    return response


@server.route("/auth/verify")
async def handle_token_verify():
    self = request.server
    data = request.data
    connection_id = request.server.get_connection_by_id(data["connection_id"])
    request_id: Optional[str] = None
    """验证Token"""
    connection = self.connection_manager.get_connection_by_id(connection_id)
    if not connection:
        return

    token = data.get("data", {}).get("token")
    if not token:
        await self.send_error(connection.websocket,
                              "Token不能为空", 400, request_id)
        return

    payload = self.jwt_manager.verify_token(token)

    response = {
        "endpoint": "/auth/verify_response",
        "data": {
            "valid": payload is not None,
            "payload": payload
        },
        "code": 200
    }

    if request_id:
        response["request_id"] = request_id

    await self.send_message(connection.websocket, response)


# 联系人处理器
@server.route("/contacts/list")
@need_login
async def handle_contacts_list():
    self = request.server
    data = request.data
    connection_id = request.connection_id
    request_id: Optional[str] = None
    """获取联系人列表"""
    connection = self.connection_manager.get_connection_by_id(connection_id)

    user_id = connection.user_id
    contacts_data = []

    # 获取联系人
    contacts = await self.user_manager.get_user_contacts(user_id)
    for contact in contacts:
        # 检查在线状态
        is_online = self.connection_manager.is_user_online(contact.user_id)
        status = UserStatus.ONLINE if is_online else UserStatus.OFFLINE

        contacts_data.append({
            "user_id": contact.user_id,
            "username": contact.username,
            "nickname": contact.nickname,
            "avatar": contact.avatar,
            "status": status.value,
            "last_seen": contact.last_seen,
            "department": contact.department,
            "tags": contact.tags
        })

    response = {
        "endpoint": "/contacts/list_response",
        "data": {
            "contacts": contacts_data,
            "count": len(contacts_data)
        },
        "code": 200
    }

    if request_id:
        response["request_id"] = request_id

    return response


@server.route("/contacts/search")
@need_login
async def handle_contacts_search():
    self = request.server
    data = request.data
    connection_id = request.server.get_connection_by_id(data["connection_id"])
    request_id: Optional[str] = None
    """搜索用户"""
    connection = self.connection_manager.get_connection_by_id(connection_id)
    if not connection or not connection.authenticated:
        await self.send_error(connection.websocket,
                              "未登录", 401, request_id)
        return

    search_data = data.get("data", {})
    keyword = search_data.get("keyword", "")
    limit = search_data.get("limit", 20)

    if not keyword or len(keyword.strip()) < 2:
        await self.send_error(connection.websocket,
                              "搜索关键词至少2个字符", 400, request_id)
        return

    # 搜索用户
    users = await self.user_manager.search_users(keyword, limit)
    users_data = []

    for user in users:
        is_online = self.connection_manager.is_user_online(user.user_id)
        status = UserStatus.ONLINE if is_online else UserStatus.OFFLINE

        users_data.append({
            "user_id": user.user_id,
            "username": user.username,
            "nickname": user.nickname,
            "avatar": user.avatar,
            "status": status.value,
            "last_seen": user.last_seen,
            "department": user.department,
            "tags": user.tags
        })

    response = {
        "endpoint": "/contacts/search_response",
        "data": {
            "users": users_data,
            "keyword": keyword,
            "count": len(users_data)
        },
        "code": 200
    }

    if request_id:
        response["request_id"] = request_id

    await self.send_message(connection.websocket, response)


@server.route("/contacts/add")
@need_login
async def handle_contacts_add():
    self = request.server
    data = request.data
    connection_id = request.server.get_connection_by_id(data["connection_id"])
    request_id: Optional[str] = None
    """添加联系人"""
    connection = self.connection_manager.get_connection_by_id(connection_id)
    if not connection or not connection.authenticated:
        await self.send_error(connection.websocket,
                              "未登录", 401, request_id)
        return

    add_data = data.get("data", {})
    target_user_id = add_data.get("target_user_id")
    add_data.get("message", "")

    if not target_user_id:
        await self.send_error(connection.websocket,
                              "目标用户ID不能为空", 400, request_id)
        return

    # 检查目标用户是否存在
    target_user = await self.user_manager.get_user_by_id(target_user_id)
    if not target_user:
        await self.send_error(connection.websocket,
                              "目标用户不存在", 404, request_id)
        return

    # 这里简化处理，直接添加为联系人
    user_id = connection.user_id
    user = await self.user_manager.get_user_by_id(user_id)

    if target_user_id not in user.contact_list:
        user.contact_list.append(target_user_id)

    # 双向添加（简化）
    if user_id not in target_user.contact_list:
        target_user.contact_list.append(user_id)

    response = {
        "endpoint": "/contacts/add_response",
        "data": {
            "success": True,
            "user_id": target_user_id,
            "nickname": target_user.nickname
        },
        "code": 200
    }

    if request_id:
        response["request_id"] = request_id

    await self.send_message(connection.websocket, response)


@server.route("/message/send")
# 消息处理器
@need_login
async def handle_message_send():
    self = request.server
    data = request.data
    # print(data)
    connection_id = request.connection_id
    request_id: Optional[str] = None
    connection = self.connection_manager.get_connection_by_id(connection_id)
    if not connection or not connection.authenticated:
        await self.send_error(connection.websocket,
                              "未登录", 401, request_id)
        return

    msg_data = data
    receiver_id = msg_data.get("receiver_id")
    message_type = msg_data.get("type", MessageType.TEXT.value)
    content = msg_data.get("content", {})
    client_msg_id = msg_data.get("client_msg_id")

    if not receiver_id:
        await self.send_error(connection.websocket,
                              "接收者ID不能为空", 400, request_id)
        return

    # 检查接收者是否存在
    receiver = await self.user_manager.get_user_by_id(receiver_id)
    print(receiver_id)
    if not receiver:
        await self.send_error(connection.websocket,
                              "接收者不存在", 404, request_id)
        return

    sender_id = connection.user_id
    sender = await self.user_manager.get_user_by_id(sender_id)

    # 生成消息ID
    message_id = str(uuid.uuid4())
    timestamp = int(datetime.datetime.now().timestamp())

    # 构建接收消息
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
            "client_msg_id": client_msg_id
        }
    }

    # 检查接收者是否在线
    delivered = False
    if self.connection_manager.is_user_online(receiver_id):
        # 尝试发送消息
        delivered = await self.push_message_to_user(receiver_id, receive_message)

    # 发送响应给发送者
    response = {
        "endpoint": "/message/send_response",
        "data": {
            "client_msg_id": client_msg_id,
            "server_msg_id": message_id,
            "delivered": delivered,
            "timestamp": timestamp,
            "message_id": message_id
        },
        "code": 200 if delivered else 202  # 202表示已接收但未送达
    }

    if request_id:
        response["request_id"] = request_id

    await self.send_message(connection.websocket, response)
    await server.message_manager.save_private_message({
        "message_id": message_id,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "type": "text",
        "content": content,
        "timestamp": timestamp,
        "client_msg_id": msg_data['client_msg_id'],
        "delivered": False,
        "read": False,
        "created_at": datetime.datetime.now(),
        "is_group": False
    })

    # 如果未送达，存储为离线消息
    if not delivered:
        await self.offline_store.add_offline_message(receiver_id, receive_message)
        self.logger.info(f"消息 {message_id} 存储为离线消息，接收者: {receiver_id}")


@server.route("/message/read_receipt")
async def handle_message_read_receipt():
    self = request.server
    data = request.data
    connection_id = request.server.get_connection_by_id(data["connection_id"])
    request_id: Optional[str] = None
    """处理已读回执"""
    connection = self.connection_manager.get_connection_by_id(connection_id)
    if not connection or not connection.authenticated:
        await self.send_error(connection.websocket,
                              "未登录", 401, request_id)
        return

    receipt_data = data.get("data", {})
    sender_id = receipt_data.get("sender_id")
    message_ids = receipt_data.get("message_ids", [])

    if not message_ids:
        await self.send_error(connection.websocket,
                              "消息ID列表不能为空", 400, request_id)
        return

    # 发送已读回执给发送者
    if sender_id and self.connection_manager.is_user_online(sender_id):
        receipt_message = {
            "endpoint": "/message/read_receipt",
            "data": {
                "user_id": connection.user_id,
                "message_ids": message_ids,
                "timestamp": int(datetime.datetime.now().timestamp())
            }
        }

        await self.push_message_to_user(sender_id, receipt_message)

    response = {
        "endpoint": "/message/read_receipt_response",
        "data": {
            "success": True,
            "count": len(message_ids)
        },
        "code": 200
    }

    if request_id:
        response["request_id"] = request_id

    await self.send_message(connection.websocket, response)


@server.route("/message/typing")
@need_login
async def handle_message_typing():
    self = request.server
    data = request.data
    connection_id = request.server.get_connection_by_id(data["connection_id"])
    request_id: Optional[str] = None
    """处理正在输入状态"""
    connection = self.connection_manager.get_connection_by_id(connection_id)
    typing_data = data.get("data", {})
    receiver_id = typing_data.get("receiver_id")
    is_typing = typing_data.get("is_typing", False)

    if not receiver_id:
        await self.send_error(connection.websocket,
                              "接收者ID不能为空", 400, request_id)
        return

    # 发送正在输入状态给接收者
    if self.connection_manager.is_user_online(receiver_id):
        typing_message = {
            "endpoint": "/message/typing",
            "data": {
                "sender_id": connection.user_id,
                "is_typing": is_typing,
                "timestamp": int(datetime.datetime.now().timestamp())
            }
        }

        await self.push_message_to_user(receiver_id, typing_message)

    response = {
        "endpoint": "/message/typing_response",
        "data": {
            "success": True,
            "receiver_id": receiver_id,
            "is_typing": is_typing
        },
        "code": 200
    }

    if request_id:
        response["request_id"] = request_id

    await self.send_message(connection.websocket, response)


@server.route("/heartbeat")
# 心跳处理器
async def handle_heartbeat():
    self: IMWebSocketServer = request.server
    data = request.data
    # print(request.data, "in 521")
    connection_id = request.connection_id
    request_id: Optional[str] = None
    """处理心跳"""
    # 更新心跳时间
    self.connection_manager.update_heartbeat(connection_id)

    connection = self.connection_manager.get_connection_by_id(connection_id)
    if connection:
        heartbeat_data = data.get("data", {})
        client_timestamp = heartbeat_data.get("timestamp")

        response = {
            "endpoint": "/heartbeat_response",
            "data": {
                "server_timestamp": int(datetime.datetime.now().timestamp()),
                "client_timestamp": client_timestamp,
                "status": "alive"
            },
            "code": 200
        }

        if request_id:
            response["request_id"] = request_id

        await self.send_message(connection.websocket, response)


@server.route("/system/info")
async def handle_system_info():
    self = request.server
    data = request.data
    connection_id = request.server.get_connection_by_id(data["connection_id"])
    request_id: Optional[str] = None
    """处理系统信息请求"""
    connection = self.connection_manager.get_connection_by_id(connection_id)
    if not connection:
        return

    # 获取连接统计信息
    conn_stats = self.connection_manager.get_connection_stats()

    response = {
        "endpoint": "/system/info_response",
        "data": {
            "server_time": int(datetime.datetime.now().timestamp()),
            "heartbeat_interval": self.heartbeat_interval,
            "heartbeat_timeout": self.heartbeat_timeout,
            "connection_stats": conn_stats,
            "total_users": len(list(self.user_manager.db.find({})))
            #     todo
        },
        "code": 200
    }

    if request_id:
        response["request_id"] = request_id

    await self.send_message(connection.websocket, response)


@server.route('/history/get')
@need_login
async def handle_history_get():
    self: IMWebSocketServer = request.server
    data = request.data
    user_id = data["target_id"]
    # 对方的user_id
    connection_id = request.connection_id
    if data['target_type'] == "user":
        messages = await self.message_manager.get_private_messages(
            user1_id=self.jwt_manager.get_user_id_from_token(data["token"]), user2_id=user_id,
            start_time=data.get("start_time"),
            limit=data.get('limit', 50), end_time=data["end_time"], )
        print("handle_history_get", messages)
    else:
        messages = await self.message_manager.get_group_messages(group_id=data["target_id"],
                                                                 start_time=data.get("start_time"),
                                                                 limit=data.get('limit', 50),
                                                                 end_time=data["end_time"], )
        # offline_messages = await self.offline_store.get_offline_messages(user_id)
    return {
        "endpoint": "/history/get_response",
        "data": {
            "messages": messages,
            "has_more": "false",
            "last_msg_id": messages[-1]["message_id"] if len(messages) > 1 else "null"
        }
    }


@server.route("/group/create")
@need_login
async def handle_group_create():
    """创建群组"""
    data = request.data
    user_id = request.user_id  # 从上下文中获取当前用户ID

    if not user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "用户未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }
    # 获取群组信息
    group_name = data.get("name", "").strip()
    description = data.get("description", "")
    avatar = data.get("avatar", "")
    initial_members = data.get("initial_members", [])  # 初始成员列表
    if not group_name:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组名称不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 创建群组
    group_manager = request.server.group_manager
    group = await group_manager.create_group(
        name=group_name,
        owner_id=user_id,
        description=description,
        avatar=avatar
    )

    if not group:
        return {
            "endpoint": "/error",
            "data": {
                "message": "创建群组失败",
                "code": 500
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 添加初始成员
    added_members = []
    for member_id in initial_members:
        if member_id != user_id:  # 不重复添加自己
            if await group_manager.add_member(group.group_id, member_id, GroupRole.MEMBER):
                added_members.append(member_id)

    return {
        "endpoint": "/group/create_response",
        "data": {
            "success": True,
            "group_id": group.group_id,
            "group_name": group.name,
            "description": group.description,
            "owner_id": group.owner_id,
            "created_at": group.created_at,
            "member_count": group.member_count,
            "initial_members_added": added_members
        },
        "code": 200,
        "timestamp": int(datetime.datetime.now().timestamp())
    }


# 群聊开始
@server.route("/group/list")
@need_login
async def handle_group_list():
    """获取用户加入的群组列表"""
    user_id = request.server.jwt_manager.get_user_id_from_token(request.request_data["data"]["token"])
    group_manager = request.server.group_manager
    groups = await group_manager.get_user_groups(user_id)
    groups_data = []
    for group in groups:
        # 获取用户在群中的角色
        role = await group_manager.get_member_role(group.group_id, user_id)
        groups_data.append({
            "group_id": group.group_id,
            "name": group.name,
            "description": group.description,
            "avatar": group.avatar,
            "owner_id": group.owner_id,
            "member_count": group.member_count,
            "created_at": group.created_at,
            "status": group.status.value,
            "user_role": role.value if role else "none",
            "unread_count": 0,  # 可以扩展为未读消息计数
            "last_message": None  # 可以扩展为最后一条消息
        })

    return {
        "endpoint": "/group/list_response",
        "data": {
            "groups": groups_data,
            "count": len(groups_data)
        },
        "code": 200,
        "timestamp": int(datetime.datetime.now().timestamp())
    }


@server.route("/group/info")
@need_login
async def handle_group_info():
    """获取群组详细信息"""
    data = request.data
    user_id = request.user_id

    if not user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "用户未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_id = data.get("group_id")
    if not group_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组ID不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_manager = request.server.group_manager
    group = await group_manager.get_group(group_id)

    if not group:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组不存在",
                "code": 404
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查用户是否在群中
    if not await group_manager.is_member(group_id, user_id):
        return {
            "endpoint": "/error",
            "data": {
                "message": "您不是该群成员",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 获取成员列表（只返回基本信息，避免敏感信息）
    members = await group_manager.get_group_members(group_id)

    members_data = []
    for member in members:
        # 获取用户信息
        user_info = await request.server.user_manager.get_user_by_id(member.user_id)
        if user_info:
            members_data.append({
                "user_id": member.user_id,
                "username": user_info.username,
                "nickname": user_info.nickname,
                "avatar": user_info.avatar,
                "role": member.role.value,
                "joined_at": member.joined_at,
                "group_nickname": member.nickname,
                "is_online": request.server.connection_manager.is_user_online(member.user_id)
            })

    # 获取用户在群中的角色
    user_role = await group_manager.get_member_role(group_id, user_id)

    return {
        "endpoint": "/group/info_response",
        "data": {
            "group_info": {
                "group_id": group.group_id,
                "name": group.name,
                "description": group.description,
                "avatar": group.avatar,
                "owner_id": group.owner_id,
                "owner_name": (await request.server.user_manager.get_user_by_id(group.owner_id)).nickname,
                "member_count": group.member_count,
                "created_at": group.created_at,
                "status": group.status.value,
                "settings": group.settings
            },
            "members": members_data,
            "user_role": user_role.value if user_role else "none",
            "can_invite": (user_role in [GroupRole.OWNER, GroupRole.ADMIN]) or
                          group.settings.get("invite_permission") == "member"
        },
        "code": 200,
        "timestamp": int(datetime.datetime.now().timestamp())
    }


@server.route("/group/join")
@need_login
async def handle_group_join():
    """加入群组"""
    data = request.data
    user_id = request.user_id

    if not user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "用户未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_id = data.get("group_id")
    password = data.get("password", "")  # 如果需要密码验证

    if not group_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组ID不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_manager = request.server.group_manager

    # 检查群组是否存在
    group = await group_manager.get_group(group_id)
    if not group or group.status != GroupStatus.ACTIVE:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组不存在或已解散",
                "code": 404
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查是否已是成员
    if await group_manager.is_member(group_id, user_id):
        return {
            "endpoint": "/error",
            "data": {
                "message": "您已是该群成员",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 这里可以添加密码验证逻辑
    # if group.settings.get("need_password") and password != group.settings.get("password"):
    #     return {"error": "密码错误", "code": 401}

    # 加入群组
    success = await group_manager.add_member(group_id, user_id, GroupRole.MEMBER)

    if not success:
        return {
            "endpoint": "/error",
            "data": {
                "message": "加入群组失败，可能群组已满",
                "code": 500
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 发送加入通知给群成员
    await _send_group_notification(
        group_id=group_id,
        notification_type="member_joined",
        user_id=user_id,
        operator_id=user_id
    )

    return {
        "endpoint": "/group/join_response",
        "data": {
            "success": True,
            "group_id": group_id,
            "group_name": group.name,
            "message": "成功加入群组"
        },
        "code": 200,
        "timestamp": int(datetime.datetime.now().timestamp())
    }


@server.route("/group/invite")
@need_login
async def handle_group_invite():
    """邀请用户加入群组"""
    data = request.data
    user_id = request.user_id

    if not user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "用户未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_id = data.get("group_id")
    invitee_ids = data.get("invitee_ids", [])

    if not group_id or not invitee_ids:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组ID和被邀请者ID不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_manager = request.server.group_manager
    user_manager = request.server.user_manager

    # 检查群组是否存在
    group = await group_manager.get_group(group_id)
    if not group or group.status != GroupStatus.ACTIVE:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组不存在或已解散",
                "code": 404
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查邀请者权限
    inviter_role = await group_manager.get_member_role(group_id, user_id)
    invite_permission = group.settings.get("invite_permission", "admin")

    can_invite = False
    if invite_permission == "all":
        can_invite = True
    elif invite_permission == "member" and inviter_role:
        can_invite = True
    elif invite_permission == "admin" and inviter_role in [GroupRole.ADMIN, GroupRole.OWNER]:
        can_invite = True
    elif invite_permission == "owner" and inviter_role == GroupRole.OWNER:
        can_invite = True

    if not can_invite:
        return {
            "endpoint": "/error",
            "data": {
                "message": "您没有邀请权限",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 邀请用户
    success_invites = []
    failed_invites = []

    for invitee_id in invitee_ids:
        # 检查用户是否存在
        invitee = await user_manager.get_user_by_id(invitee_id)
        if not invitee:
            failed_invites.append({"user_id": invitee_id, "reason": "用户不存在"})
            continue

        # 检查是否已是成员
        if await group_manager.is_member(group_id, invitee_id):
            failed_invites.append({"user_id": invitee_id, "reason": "已是群成员"})
            continue

        # 发送邀请通知给被邀请者
        if request.server.connection_manager.is_user_online(invitee_id):
            invitation_message = {
                "endpoint": "/group/invitation_received",
                "data": {
                    "invitation_id": f"inv_{uuid.uuid4().hex[:8]}",
                    "group_id": group_id,
                    "group_name": group.name,
                    "group_description": group.description,
                    "inviter_id": user_id,
                    "inviter_name": await user_manager.get_user_by_id(user_id).nickname,
                    "created_at": int(datetime.datetime.now().timestamp())
                }
            }

            await request.server.push_message_to_user(invitee_id, invitation_message)
            success_invites.append(invitee_id)
        else:
            failed_invites.append({"user_id": invitee_id, "reason": "用户离线"})

    return {
        "endpoint": "/group/invite_response",
        "data": {
            "success": True,
            "group_id": group_id,
            "inviter_id": user_id,
            "success_invites": success_invites,
            "failed_invites": failed_invites,
            "total_invited": len(invitee_ids)
        },
        "code": 200,
        "timestamp": int(datetime.datetime.now().timestamp())
    }


@server.route("/group/leave")
@need_login
async def handle_group_leave():
    """退出群组"""
    data = request.data
    user_id = request.user_id

    if not user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "用户未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_id = data.get("group_id")
    if not group_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组ID不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_manager = request.server.group_manager

    # 检查群组是否存在
    group = await group_manager.get_group(group_id)
    if not group or group.status != GroupStatus.ACTIVE:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组不存在或已解散",
                "code": 404
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查是否是成员
    if not await group_manager.is_member(group_id, user_id):
        return {
            "endpoint": "/error",
            "data": {
                "message": "您不是该群成员",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 群主不能直接退出，需要先转移群主或解散群
    if user_id == group.owner_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群主不能直接退出，请先转移群主或解散群",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 退出群组
    success = await group_manager.remove_member(group_id, user_id)

    if not success:
        return {
            "endpoint": "/error",
            "data": {
                "message": "退出群组失败",
                "code": 500
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 发送退出通知给群成员
    await _send_group_notification(
        group_id=group_id,
        notification_type="member_left",
        user_id=user_id,
        operator_id=user_id
    )

    return {
        "endpoint": "/group/leave_response",
        "data": {
            "success": True,
            "group_id": group_id,
            "message": "已成功退出群组"
        },
        "code": 200,
        "timestamp": int(datetime.datetime.now().timestamp())
    }


@server.route("/group/kick")
@need_login
async def handle_group_kick():
    """踢出群成员"""
    data = request.data
    user_id = request.user_id

    if not user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "用户未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_id = data.get("group_id")
    target_user_id = data.get("target_user_id")
    reason = data.get("reason", "")

    if not group_id or not target_user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组ID和目标用户ID不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_manager = request.server.group_manager

    # 检查群组是否存在
    group = await group_manager.get_group(group_id)
    if not group or group.status != GroupStatus.ACTIVE:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组不存在或已解散",
                "code": 404
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查操作者权限
    operator_role = await group_manager.get_member_role(group_id, user_id)
    if operator_role not in [GroupRole.OWNER, GroupRole.ADMIN]:
        return {
            "endpoint": "/error",
            "data": {
                "message": "您没有踢人权限",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查目标用户是否是成员
    if not await group_manager.is_member(group_id, target_user_id):
        return {
            "endpoint": "/error",
            "data": {
                "message": "目标用户不是群成员",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查不能踢出自己
    if target_user_id == user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "不能踢出自己",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 管理员不能踢出群主，管理员只能被群主踢出
    target_role = await group_manager.get_member_role(group_id, target_user_id)
    if target_role == GroupRole.OWNER:
        return {
            "endpoint": "/error",
            "data": {
                "message": "不能踢出群主",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    if target_role == GroupRole.ADMIN and operator_role != GroupRole.OWNER:
        return {
            "endpoint": "/error",
            "data": {
                "message": "只有群主可以踢出管理员",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 踢出成员
    success = await group_manager.remove_member(group_id, target_user_id)

    if not success:
        return {
            "endpoint": "/error",
            "data": {
                "message": "踢出成员失败",
                "code": 500
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 发送踢出通知给群成员
    await _send_group_notification(
        group_id=group_id,
        notification_type="member_kicked",
        user_id=target_user_id,
        operator_id=user_id,
        reason=reason
    )

    return {
        "endpoint": "/group/kick_response",
        "data": {
            "success": True,
            "group_id": group_id,
            "target_user_id": target_user_id,
            "message": "已成功踢出成员"
        },
        "code": 200,
        "timestamp": int(datetime.datetime.now().timestamp())
    }


@server.route("/group/settings/update")
@need_login
async def handle_group_settings_update():
    """更新群组设置"""
    data = request.data
    user_id = request.user_id

    if not user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "用户未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_id = data.get("group_id")
    settings = data.get("settings", {})

    if not group_id or not settings:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组ID和设置不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_manager = request.server.group_manager

    # 检查群组是否存在
    group = await group_manager.get_group(group_id)
    if not group or group.status != GroupStatus.ACTIVE:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组不存在或已解散",
                "code": 404
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查操作者权限（只有群主和管理员可以修改设置）
    operator_role = await group_manager.get_member_role(group_id, user_id)
    if operator_role not in [GroupRole.OWNER, GroupRole.ADMIN]:
        return {
            "endpoint": "/error",
            "data": {
                "message": "您没有修改设置的权限",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 某些设置只能群主修改
    restricted_settings = ["invite_permission", "message_permission"]
    if operator_role != GroupRole.OWNER:
        # 管理员不能修改受限设置
        for key in restricted_settings:
            if key in settings:
                return {
                    "endpoint": "/error",
                    "data": {
                        "message": f"只有群主可以修改 {key} 设置",
                        "code": 403
                    },
                    "timestamp": int(datetime.datetime.now().timestamp())
                }

    # 更新设置
    success = await group_manager.update_group_settings(group_id, settings)

    if not success:
        return {
            "endpoint": "/error",
            "data": {
                "message": "更新设置失败",
                "code": 500
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 发送设置更新通知给群成员
    await _send_group_notification(
        group_id=group_id,
        notification_type="settings_updated",
        operator_id=user_id,
        settings_changed=list(settings.keys())
    )

    return {
        "endpoint": "/group/settings/update_response",
        "data": {
            "success": True,
            "group_id": group_id,
            "updated_settings": settings,
            "message": "群组设置已更新"
        },
        "code": 200,
        "timestamp": int(datetime.datetime.now().timestamp())
    }


# ========== 群消息路由 ==========

@server.route("/group/message/send")
@need_login
async def handle_group_message_send():
    """发送群消息"""
    data = request.data
    user_id = request.user_id

    if not user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "用户未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_id = data.get("group_id")
    message_type = data.get("type", MessageType.TEXT.value)
    content = data.get("content", {})
    client_msg_id = data.get("client_msg_id")
    at_users = data.get("at_users", [])
    at_all = data.get("at_all", False)

    if not group_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组ID不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    if not content:
        return {
            "endpoint": "/error",
            "data": {
                "message": "消息内容不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_manager = request.server.group_manager
    user_manager = request.server.user_manager

    # 检查群组是否存在
    group = await group_manager.get_group(group_id)
    if not group or group.status != GroupStatus.ACTIVE:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组不存在或已解散",
                "code": 404
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查用户是否是群成员
    if not await group_manager.is_member(group_id, user_id):
        return {
            "endpoint": "/error",
            "data": {
                "message": "您不是该群成员",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查用户是否被禁言
    if await group_manager.is_muted(group_id, user_id):
        return {
            "endpoint": "/error",
            "data": {
                "message": "您已被禁言，不能发送消息",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查发言权限
    user_role = await group_manager.get_member_role(group_id, user_id)
    message_permission = group.settings.get("message_permission", "all")

    can_send = False
    if message_permission == "all":
        can_send = True
    elif message_permission == "member_only" and user_role:
        can_send = True
    elif message_permission == "admin_only" and user_role in [GroupRole.ADMIN, GroupRole.OWNER]:
        can_send = True

    if not can_send:
        return {
            "endpoint": "/error",
            "data": {
                "message": "您没有发言权限",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 生成消息ID
    message_id = str(uuid.uuid4())
    timestamp = int(datetime.datetime.now().timestamp())

    # 获取发送者信息
    sender = await user_manager.get_user_by_id(user_id)

    # 构建群消息
    group_message = {
        "endpoint": "/group/message/receive",
        "data": {
            "message_id": message_id,
            "group_id": group_id,
            "group_name": group.name,
            "sender_id": user_id,
            "sender_info": {
                "user_id": user_id,
                "username": sender.username,
                "nickname": sender.nickname,
                "avatar": sender.avatar,
                "group_role": user_role.value if user_role else "member"
            },
            "type": message_type,
            "content": content,
            "timestamp": timestamp,
            "client_msg_id": client_msg_id,
            "at_users": at_users,
            "at_all": at_all,
            "is_system": False
        }
    }
    await server.message_manager.save_group_message(group_message)

    # 获取群成员
    members = await group_manager.get_group_members(group_id)

    # 发送消息给所有在线成员（除了发送者自己）
    delivered_to = []
    offline_members = []

    for member in members:
        if member.user_id == user_id:
            continue  # 不发送给自己

        # 检查是否在线
        if request.server.connection_manager.is_user_online(member.user_id):
            await request.server.push_message_to_user(member.user_id, group_message)
            delivered_to.append(member.user_id)
        else:
            # 存储为离线消息
            await request.server.offline_store.add_offline_message(
                member.user_id, group_message
            )
            offline_members.append(member.user_id)

    # 发送响应给发送者
    response = {
        "endpoint": "/group/message/send_response",
        "data": {
            "success": True,
            "message_id": message_id,
            "group_id": group_id,
            "client_msg_id": client_msg_id,
            "timestamp": timestamp,
            "delivered_to": delivered_to,
            "offline_members": offline_members,
            "total_members": len(members) - 1  # 排除发送者
        },
        "code": 200,
        "timestamp": timestamp
    }

    return response


@server.route("/group/messages/history")
@need_login
async def handle_group_messages_history():
    """获取群聊历史消息"""
    data = request.data
    user_id = request.user_id

    if not user_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "用户未登录",
                "code": 401
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_id = data.get("group_id")
    limit = data.get("limit", 50)
    last_msg_id = data.get("last_msg_id")

    if not group_id:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组ID不能为空",
                "code": 400
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    group_manager = request.server.group_manager

    # 检查群组是否存在
    group = await group_manager.get_group(group_id)
    if not group or group.status != GroupStatus.ACTIVE:
        return {
            "endpoint": "/error",
            "data": {
                "message": "群组不存在或已解散",
                "code": 404
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 检查用户是否是群成员
    if not await group_manager.is_member(group_id, user_id):
        return {
            "endpoint": "/error",
            "data": {
                "message": "您不是该群成员",
                "code": 403
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

    # 这里应该从数据库获取历史消息
    # 由于是内存存储，我们返回空列表，实际项目中需要实现消息存储
    # messages = []
    messages = await request.server.message_manager.get_group_messages(
        group_id=group_id,
        limit=limit,
        last_msg_id=last_msg_id
    )

    return {
        "endpoint": "/group/messages/history_response",
        "data": {
            "group_id": group_id,
            "messages": messages,
            "has_more": False,
            "last_msg_id": last_msg_id,
            "count": len(messages)
        },
        "code": 200,
        "timestamp": int(datetime.datetime.now().timestamp())
    }


# ========== 辅助函数 ==========

async def _send_group_notification(group_id: str, notification_type: str,
                                   user_id: Optional[int] = None,
                                   operator_id: Optional[int] = None,
                                   **extra_data):
    """
    发送群通知给所有成员

    Args:
        group_id: 群组ID
        notification_type: 通知类型
        user_id: 相关用户ID（被操作的用户）
        operator_id: 操作者ID
        extra_data: 额外数据
    """
    group_manager = request.server.group_manager
    user_manager = request.server.user_manager

    # 获取群组和成员
    group = await group_manager.get_group(group_id)
    if not group:
        return

    members = await group_manager.get_group_members(group_id)

    # 构建通知消息
    notification_data = {
        "type": notification_type,
        "group_id": group_id,
        "group_name": group.name,
        "timestamp": int(datetime.datetime.now().timestamp()),
        **extra_data
    }

    # 添加用户信息
    if user_id:
        user = await user_manager.get_user_by_id(user_id)
        if user:
            notification_data["user_id"] = user_id
            notification_data["user_name"] = user.nickname

    # 添加操作者信息
    if operator_id:
        operator = await user_manager.get_user_by_id(operator_id)
        if operator:
            notification_data["operator_id"] = operator_id
            notification_data["operator_name"] = operator.nickname

    # 构建通知消息
    notification_message = {
        "endpoint": "/group/notification",
        "data": notification_data
    }
    # 发送给所有在线成员
    for member in members:
        if request.server.connection_manager.is_user_online(member.user_id):
            await request.server.push_message_to_user(member.user_id, notification_message)


@server.route("/offline/get")
@need_login
async def handle_offline_get():
    user_id = request.data.get("user_id")
    if not user_id:
        return {
            "endpoint": "/offline/get_response",
            "data": {
                "message": "uid不能为空",
                "code": 404
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }
    else:
        messages = await request.server.offline_store.get_offline_messages(user_id)
        await request.server.offline_store.clear_offline_messages(user_id)
        # for i in messages:
        #     if "group_id" in i['data']:
        #         await request.server.message_manager.save_group_message(i["data"])
        #     else:
        #         await request.server.message_manager.save_private_message(i["data"])
        # await request.server.message_manager.
        return {
            "endpoint": "/offline/get_response",
            "data": {
                "messages": messages,
                "count": len(messages)

            }
        }
