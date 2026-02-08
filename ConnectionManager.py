import datetime
import uuid
from typing import Dict, List, Optional, Any

from websockets import ServerConnection

from models import ClientConnection
import logging


class ConnectionManager:
    """连接管理"""

    def __init__(self):
        # connection_id -> ClientConnection
        self.connections: Dict[str, ClientConnection] = {}
        # user_id -> [connection_id]
        self.user_connections: Dict[int, List[str]] = {}
        # connection_id -> user_id（快速查找）
        self.connection_to_user: Dict[str, int] = {}
        self.logger = logging.getLogger("ConnectionManager")

    def add_connection(self, websocket: ServerConnection,
                       device_id: Optional[str] = None) -> str:
        """添加新连接"""
        connection_id = str(uuid.uuid4())
        connection = ClientConnection(
            connection_id=connection_id,
            websocket=websocket,
            device_id=device_id
        )

        self.connections[connection_id] = connection
        self.logger.info(f"新连接建立: {connection_id}")

        return connection_id

    async def authenticate_connection(self, connection_id: str, user_id: int):
        """认证连接"""
        if connection_id not in self.connections:
            return False

        connection = self.connections[connection_id]
        connection.user_id = user_id
        connection.authenticated = True
        connection.last_activity = datetime.datetime.now()

        # 添加到用户连接映射
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(connection_id)
        self.connection_to_user[connection_id] = user_id

        self.logger.info(f"用户 {user_id} 认证成功，连接: {connection_id}")
        return True

    def remove_connection(self, connection_id: str):
        """移除连接"""
        if connection_id not in self.connections:
            return

        connection = self.connections[connection_id]
        user_id = connection.user_id

        # 从用户连接映射中移除
        if user_id and user_id in self.user_connections:
            if connection_id in self.user_connections[user_id]:
                self.user_connections[user_id].remove(connection_id)

            # 如果用户没有其他连接，清理用户连接映射
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        # 从快速映射中移除
        if connection_id in self.connection_to_user:
            del self.connection_to_user[connection_id]

        # 从连接池中移除
        del self.connections[connection_id]

        self.logger.info(f"连接移除: {connection_id}")

    def get_user_connections(self, user_id: int) -> List[ClientConnection]:
        """获取用户的所有连接"""
        connection_ids = self.user_connections.get(user_id, [])
        connections = []
        for conn_id in connection_ids:
            if conn_id in self.connections:
                connections.append(self.connections[conn_id])
        return connections

    def is_user_online(self, user_id: int) -> bool:
        """检查用户是否在线"""
        return user_id in self.user_connections and len(self.user_connections[user_id]) > 0

    def get_connection_by_id(self, connection_id: str) -> Optional[ClientConnection]:
        """根据ID获取连接"""
        return self.connections.get(connection_id)

    def update_heartbeat(self, connection_id: str):
        """更新心跳时间"""
        if connection_id in self.connections:
            self.connections[connection_id].last_heartbeat = datetime.datetime.now()

    def update_activity(self, connection_id: str):
        """更新活动时间"""
        if connection_id in self.connections:
            self.connections[connection_id].last_activity = datetime.datetime.now()

    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        return {
            "total_connections": len(self.connections),
            "authenticated_connections": sum(1 for c in self.connections.values() if c.authenticated),
            "online_users": len(self.user_connections),
            "connections_by_user": {uid: len(conns) for uid, conns in self.user_connections.items()}
        }
