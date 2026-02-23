# OfflineMessageStore.py
import asyncio
import datetime
from typing import Dict, List, Any
import logging
from pymongo import AsyncMongoClient
import uuid
import config

uri = config.mongo_uri


class OfflineMessageStore:
    """离线消息存储"""

    def __init__(self):
        self.logger = logging.getLogger('OfflineMessageStore')
        self.dbclient = AsyncMongoClient(uri)
        self.db = self.dbclient["IM"]["offline_messages"]

        # 创建索引
        # asyncio.get_event_loop().run_until_complete(self._create_indexes())
        # asyncio.create_task(self._create_indexes())

    async def initialize(self):
        await self._create_indexes()

    async def _create_indexes(self):
        """创建数据库索引"""
        try:
            await self.db.create_index("user_id")
            await self.db.create_index([("user_id", 1), ("timestamp", -1)])
            self.logger.debug("离线消息存储索引创建完成")
        except Exception as e:
            self.logger.error(f"创建索引失败: {e}")

    async def add_offline_message(self, user_id: int, message: Dict[str, Any]):
        """添加离线消息"""
        try:
            message_record = {
                "message_id": str(uuid.uuid4()),
                "user_id": user_id,
                "message": message,
                "timestamp": message.get("data", {}).get("timestamp", 0),
                "created_at": datetime.datetime.now()
            }

            result = await self.db.insert_one(message_record)
            self.logger.debug(f"为用户 {user_id} 添加离线消息，ID: {result.inserted_id}")
        except Exception as e:
            self.logger.error(f"添加离线消息失败: {e}")

    async def get_offline_messages(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户的离线消息"""
        try:
            cursor = self.db.find({"user_id": user_id}).sort("timestamp", 1)
            messages = await cursor.to_list(length=None)
            # 转换为原始消息格式
            result = []
            for msg in messages:
                result.append(msg["message"])

            self.logger.debug(f"获取用户 {user_id} 的离线消息，数量: {len(result)}")
            return result
        except Exception as e:
            self.logger.error(f"获取离线消息失败: {e}")
            return []

    async def clear_offline_messages(self, user_id: int):
        """清空用户的离线消息"""
        try:
            result = await self.db.delete_many({"user_id": user_id})
            self.logger.debug(f"清空用户 {user_id} 的离线消息，删除数量: {result.deleted_count}")
        except Exception as e:
            self.logger.error(f"清空离线消息失败: {e}")
