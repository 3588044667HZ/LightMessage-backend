import asyncio
import datetime
import json
import logging
from typing import Dict, Optional, Any, Callable
import websockets
from websockets import ServerConnection
from websockets.exceptions import ConnectionClosed
from ConnectionManager import ConnectionManager
from GroupManager import GroupManager
from JWTSessionManager import JWTSessionManager
from MessageManager import MessageManager
from OfflineMessageStore import OfflineMessageStore
from UserManager import UserManager
from context import RequestContextManager
from enums import UserStatus


class IMWebSocketServer:
    """IM WebSocket服务器"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765,
                 heartbeat_timeout: int = 60, heartbeat_interval: int = 30):
        self.logger = logging.getLogger("IMWebSocketServer")
        self.host = host
        self.port = port
        self.heartbeat_timeout = heartbeat_timeout
        self.heartbeat_interval = heartbeat_interval
        # 初始化管理器
        self.jwt_manager = JWTSessionManager()
        self.user_manager = UserManager()
        self.connection_manager = ConnectionManager()
        self.offline_store = OfflineMessageStore()
        self.group_manager = GroupManager()
        self.message_manager = MessageManager()

        # 消息处理器路由
        self.handlers: Dict[str, Callable] = {

        }

        # 心跳检查任务
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.running = False

    async def initialize(self):
        await self.message_manager.initialize()
        await self.group_manager.initialize()
        await self.offline_store.initialize()
        await self.message_manager.initialize()
        self.logger.info("服务器组件初始化完成")

    async def start(self):
        """启动服务器"""
        self.running = True

        # 启动心跳检查任务
        self.heartbeat_task = asyncio.create_task(self.heartbeat_checker())

        self.logger.info(f"启动IM WebSocket服务器: ws://{self.host}:{self.port}")
        self.logger.info(f"心跳检查间隔: {self.heartbeat_interval}秒, 超时: {self.heartbeat_timeout}秒")

        try:
            async with websockets.serve(self.connection_handler, self.host, self.port):
                await asyncio.Future()  # 永久运行
        except Exception as e:
            self.logger.error(f"服务器启动失败: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self):
        """停止服务器"""
        self.running = False

        # 停止心跳检查任务
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass

        self.logger.info("服务器已停止")

    async def connection_handler(self, websocket: ServerConnection):
        """处理客户端连接"""
        connection_id = self.connection_manager.add_connection(websocket)

        try:
            # 发送连接成功消息
            await self.send_message(websocket, {
                "endpoint": "/system/connected",
                "data": {
                    "connection_id": connection_id,
                    "timestamp": int(datetime.datetime.now().timestamp()),
                    "heartbeat_interval": self.heartbeat_interval
                },
                "code": 200
            })
            # 处理消息循环
            async for message in websocket:
                try:
                    await self.process_message(connection_id, message)
                except json.JSONDecodeError:
                    await self.send_error(websocket, "无效的JSON格式", 400, connection_id)
                except DeprecationWarning as e:
                    self.logger.error(f"处理消息时出错: {e}")
                    await self.send_error(websocket, "服务器内部错误", 500, connection_id)

        except ConnectionClosed:
            self.logger.info(f"连接关闭: {connection_id}")
        except DeprecationWarning as e:
            self.logger.error(f"连接处理异常: {e}")
        finally:
            # 清理连接
            await self.cleanup_connection(connection_id)

    async def process_message(self, connection_id: str, raw_message: str):
        """处理接收到的消息"""
        data = json.loads(raw_message)
        endpoint = data.get("endpoint")
        request_id = data.get("request_id")

        # 更新活动时间
        self.connection_manager.update_activity(connection_id)
        # 查找处理器
        handler = self.handlers.get(endpoint)
        if handler:
            try:
                async with RequestContextManager(
                        server=self,
                        connection_id=connection_id,
                        request_data=data,
                        request_id=request_id
                ):
                    response = await handler()
                    await self._process_response(response, connection_id)
            except DeprecationWarning as e:
                self.logger.error(f"处理器执行出错 ({endpoint}): {e}")
                connection = self.connection_manager.get_connection_by_id(connection_id)
                if connection:
                    await self.send_error(connection.websocket,
                                          f"处理器执行出错: {str(e)}", 500, request_id)
        else:
            connection = self.connection_manager.get_connection_by_id(connection_id)
            if connection:
                await self.send_error(connection.websocket,
                                      f"未知的endpoint: {endpoint}", 404, request_id)

    async def _process_response(self, response: Dict[str, Any], connection_id: str):
        """处理路由返回的响应"""
        if not response:
            return

        # 发送响应给客户端
        connection = self.connection_manager.get_connection_by_id(connection_id)
        if connection:
            await connection.websocket.send(json.dumps(response))

    async def send_message(self, websocket: ServerConnection,
                           message: Dict[str, Any]):
        """发送消息到客户端"""
        try:
            await websocket.send(json.dumps(message))
        except ConnectionClosed:
            self.logger.debug("连接已关闭，无法发送消息")
        except Exception as e:
            self.logger.error(f"发送消息失败: {e}")

    async def send_error(self, websocket: ServerConnection,
                         message: str, code: int = 400,
                         request_id: Optional[str] = None):
        """发送错误响应"""
        error_msg = {
            "endpoint": "/error",
            "data": {
                "message": message,
                "code": code
            },
            "timestamp": int(datetime.datetime.now().timestamp())
        }

        if request_id:
            error_msg["request_id"] = request_id

        await self.send_message(websocket, error_msg)

    async def cleanup_connection(self, connection_id: str):
        """清理连接资源"""
        connection = self.connection_manager.get_connection_by_id(connection_id)
        if not connection:
            return

        user_id = connection.user_id

        # 移除连接
        self.connection_manager.remove_connection(connection_id)

        # 如果用户完全离线，更新状态
        if user_id and not self.connection_manager.is_user_online(user_id):
            await self.notify_user_offline(user_id)

    # 辅助方法
    async def push_message_to_user(self, user_id: int, message: Dict[str, Any]) -> bool:
        """推送消息给用户（所有设备）"""
        connections = self.connection_manager.get_user_connections(user_id)

        if not connections:
            return False

        success = False
        for connection in connections:
            try:
                await self.send_message(connection.websocket, message)
                success = True
            except Exception as e:
                self.logger.error(f"推送消息给用户 {user_id} 失败: {e}")
                # 如果连接失败，标记为需要清理
                self.connection_manager.remove_connection(connection.connection_id)

        return success

    async def push_offline_messages(self, user_id: int, websocket: ServerConnection):
        """推送离线消息给用户"""
        offline_messages = await self.offline_store.get_offline_messages(user_id)

        if not offline_messages:
            return

        self.logger.info(f"为用户 {user_id} 推送 {len(offline_messages)} 条离线消息")

        for message in offline_messages:
            try:
                await self.send_message(websocket, message)
                # 消息已送达回执
                if message.get("endpoint") == "/message/receive":
                    sender_id = message.get("data", {}).get("sender_id")
                    message_id = message.get("data", {}).get("message_id")

                    if sender_id and message_id and self.connection_manager.is_user_online(sender_id):
                        delivery_message = {
                            "endpoint": "/message/delivery_receipt",
                            "data": {
                                "message_ids": [message_id],
                                "timestamp": int(datetime.datetime.now().timestamp())
                            }
                        }
                        await self.push_message_to_user(sender_id, delivery_message)

            except Exception as e:
                self.logger.error(f"推送离线消息失败: {e}")

        # 清空离线消息
        await self.offline_store.clear_offline_messages(user_id)

    async def notify_user_online(self, user_id: int):
        """通知联系人用户上线"""
        user = await self.user_manager.get_user_by_id(user_id)
        if not user:
            return

        # 更新用户状态
        user.status = UserStatus.ONLINE
        user.last_seen = int(datetime.datetime.now().timestamp())

        # 通知所有联系人
        for contact_id in user.contact_list:
            if self.connection_manager.is_user_online(contact_id):
                presence_message = {
                    "endpoint": "/presence/change",
                    "data": {
                        "user_id": user_id,
                        "username": user.username,
                        "nickname": user.nickname,
                        "status": user.status.value,
                        "last_seen": user.last_seen,
                        "timestamp": int(datetime.datetime.now().timestamp())
                    }
                }
                await self.push_message_to_user(contact_id, presence_message)

    async def notify_user_offline(self, user_id: int):
        """通知联系人用户离线"""
        user = await self.user_manager.get_user_by_id(user_id)
        if not user:
            return

        # 更新用户状态
        user.status = UserStatus.OFFLINE
        user.last_seen = int(datetime.datetime.now().timestamp())

        # 通知所有联系人
        for contact_id in user.contact_list:
            if self.connection_manager.is_user_online(contact_id):
                presence_message = {
                    "endpoint": "/presence/change",
                    "data": {
                        "user_id": user_id,
                        "username": user.username,
                        "nickname": user.nickname,
                        "status": user.status.value,
                        "last_seen": user.last_seen,
                        "timestamp": int(datetime.datetime.now().timestamp())
                    }
                }
                await self.push_message_to_user(contact_id, presence_message)

    async def heartbeat_checker(self):
        """心跳检查任务"""
        self.logger.info("心跳检查任务已启动")

        while self.running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self.check_heartbeats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"心跳检查出错: {e}")

        self.logger.info("心跳检查任务已停止")

    def route(self, endpoint: str):
        def wrapper(func):
            self.handlers[endpoint] = func

        return wrapper

    async def check_heartbeats(self):
        """检查所有连接的心跳"""
        current_time = datetime.datetime.now()
        timeout_connections = []

        for connection_id, connection in self.connection_manager.connections.items():
            # 计算心跳时间差
            time_diff = (current_time - connection.last_heartbeat).total_seconds()
            # 如果心跳超时
            if time_diff > self.heartbeat_timeout:
                self.logger.warning(f"连接 {connection_id} 心跳超时 ({time_diff:.1f}s)")
                timeout_connections.append(connection_id)
        # 清理超时连接
        for connection_id in timeout_connections:
            connection = self.connection_manager.get_connection_by_id(connection_id)
            if connection:
                # 发送超时通知
                try:
                    timeout_message = {
                        "endpoint": "/system/notification",
                        "data": {
                            "type": "connection_timeout",
                            "message": "连接超时，请重新连接",
                            "timestamp": int(datetime.datetime.now().timestamp())
                        }
                    }
                    await self.send_message(connection.websocket, timeout_message)
                    await asyncio.sleep(0.1)  # 等待消息发送
                except:
                    pass

                # 清理连接
                await self.cleanup_connection(connection_id)
