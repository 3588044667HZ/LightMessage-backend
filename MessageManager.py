# MessageManager.py
import uuid
import datetime
import asyncio
from typing import Dict, List, Optional, Any
from pymongo import AsyncMongoClient
from enums import MessageType
import logging

uri = "mongodb://localhost:27017/"


class MessageManager:
    """消息管理器"""

    def __init__(self):
        self.logger = logging.getLogger("MessageManager")
        self.dbclient = AsyncMongoClient(uri)
        self.db_messages = self.dbclient["IM"]["messages"]

        # 创建索引
        # asyncio.run(self._create_indexes())

    async def initialize(self):
        await self._create_indexes()

    async def _create_indexes(self):
        """创建数据库索引"""
        try:
            # 复合索引，支持快速查询
            await self.db_messages.create_index([("sender_id", 1), ("receiver_id", 1), ("timestamp", -1)])
            await self.db_messages.create_index([("group_id", 1), ("timestamp", -1)])
            await self.db_messages.create_index([("sender_id", 1), ("timestamp", -1)])
            await self.db_messages.create_index([("receiver_id", 1), ("timestamp", -1)])
            await self.db_messages.create_index("message_id", unique=True)
            await self.db_messages.create_index("timestamp")

            self.logger.debug("消息管理器索引创建完成")
        except Exception as e:
            self.logger.error(f"创建索引失败: {e}")

    async def save_private_message(self, message_data: Dict[str, Any]) -> str:
        """保存私聊消息"""
        try:
            message_id = message_data.get("message_id", str(uuid.uuid4()))
            timestamp = message_data.get("timestamp", int(datetime.datetime.now().timestamp()))

            message_record = {
                "message_id": message_id,
                "sender_id": message_data["sender_id"],
                "receiver_id": message_data["receiver_id"],
                "type": message_data.get("type", MessageType.TEXT.value),
                "content": message_data["content"],
                "timestamp": timestamp,
                "client_msg_id": message_data.get("client_msg_id"),
                "delivered": message_data.get("delivered", False),
                "read": message_data.get("read", False),
                "created_at": datetime.datetime.now(),
                "is_group": False
            }

            await self.db_messages.insert_one(message_record)
            self.logger.debug(f"保存私聊消息: {message_id}")
            return message_id

        except DeprecationWarning as e:
            self.logger.error(f"保存私聊消息失败: {e}")
            return ""

    async def save_group_message(self, message_data: Dict[str, Any]) -> str:
        """保存群聊消息"""
        try:
            message_id = message_data.get("message_id", str(uuid.uuid4()))
            timestamp = message_data.get("timestamp", int(datetime.datetime.now().timestamp()))

            message_record = {
                "message_id": message_id,
                "sender_id": message_data["sender_id"],
                "group_id": message_data["group_id"],
                "type": message_data.get("type", MessageType.TEXT.value),
                "content": message_data["content"],
                "timestamp": timestamp,
                "client_msg_id": message_data.get("client_msg_id"),
                "at_users": message_data.get("at_users", []),
                "at_all": message_data.get("at_all", False),
                "created_at": datetime.datetime.now(),
                "is_group": True
            }

            result = await self.db_messages.insert_one(message_record)
            self.logger.debug(f"保存群聊消息: {message_id} 群组: {message_data['group_id']}")
            return message_id

        except Exception as e:
            self.logger.error(f"保存群聊消息失败: {e}")
            return ""

    async def get_private_messages(self, user1_id: int, user2_id: int,
                                   limit: int = 50, last_msg_id: Optional[str] = None,
                                   start_time: Optional[int] = None,
                                   end_time: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取私聊历史消息"""
        try:
            # 构建查询条件
            query = {
                "is_group": False,
                "$or": [
                    {"sender_id": user1_id, "receiver_id": user2_id},
                    {"sender_id": user2_id, "receiver_id": user1_id}
                ]
            }

            # 添加时间范围条件
            if start_time or end_time:
                time_query = {}
                if start_time:
                    time_query["$gte"] = start_time
                if end_time:
                    time_query["$lte"] = end_time
                if time_query:
                    query["timestamp"] = time_query

            # 如果指定了最后一条消息ID，获取该消息的时间戳
            if last_msg_id:
                last_msg = await self.db_messages.find_one({"message_id": last_msg_id})
                if last_msg:
                    query["timestamp"] = {"$lt": last_msg["timestamp"]}

            # 查询消息
            cursor = self.db_messages.find(query).sort("timestamp", -1).limit(limit)
            messages = await cursor.to_list(length=limit)

            # 转换为标准格式
            result = []
            for msg in reversed(messages):  # 反转以获取正序时间
                result.append({
                    "message_id": msg["message_id"],
                    "sender_id": msg["sender_id"],
                    "receiver_id": msg["receiver_id"],
                    "type": msg["type"],
                    "content": msg["content"],
                    "timestamp": msg["timestamp"],
                    "client_msg_id": msg.get("client_msg_id"),
                    "delivered": msg.get("delivered", False),
                    "read": msg.get("read", False)
                })

            return result

        except Exception as e:
            self.logger.error(f"获取私聊历史消息失败: {e}")
            return []

    async def get_group_messages(self, group_id: str, limit: int = 50,
                                 last_msg_id: Optional[str] = None,
                                 start_time: Optional[int] = None,
                                 end_time: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取群聊历史消息"""
        try:
            # 构建查询条件
            query = {
                "is_group": True,
                "group_id": group_id
            }
            # 添加时间范围条件
            if start_time or end_time:
                time_query = {}
                if start_time:
                    time_query["$gte"] = start_time
                if end_time:
                    time_query["$lte"] = end_time
                if time_query:
                    query["timestamp"] = time_query

            # 如果指定了最后一条消息ID，获取该消息的时间戳
            if last_msg_id:
                last_msg = await self.db_messages.find_one({"message_id": last_msg_id})
                if last_msg:
                    query["timestamp"] = {"$lt": last_msg["timestamp"]}

            # 查询消息
            cursor = self.db_messages.find(query).sort("timestamp", -1).limit(limit)
            messages = await cursor.to_list(length=limit)

            # 转换为标准格式
            result = []
            for msg in reversed(messages):  # 反转以获取正序时间
                result.append({
                    "message_id": msg["message_id"],
                    "group_id": msg["group_id"],
                    "sender_id": msg["sender_id"],
                    "type": msg["type"],
                    "content": msg["content"],
                    "timestamp": msg["timestamp"],
                    "client_msg_id": msg.get("client_msg_id"),
                    "at_users": msg.get("at_users", []),
                    "at_all": msg.get("at_all", False)
                })

            return result

        except Exception as e:
            self.logger.error(f"获取群聊历史消息失败: {e}")
            return []

    async def get_user_messages_by_time(self, user_id: int,
                                        start_time: int,
                                        end_time: int,
                                        message_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """按时间段获取用户的所有消息（包括发送和接收）"""
        try:
            query = {
                "timestamp": {"$gte": start_time, "$lte": end_time},
                "$or": [
                    {"sender_id": user_id},
                    {"receiver_id": user_id}
                ]
            }

            # 添加消息类型筛选
            if message_type:
                query["type"] = message_type

            cursor = self.db_messages.find(query).sort("timestamp", 1)
            messages = await cursor.to_list(length=None)

            result = []
            for msg in messages:
                message_info = {
                    "message_id": msg["message_id"],
                    "sender_id": msg["sender_id"],
                    "type": msg["type"],
                    "content": msg["content"],
                    "timestamp": msg["timestamp"],
                    "client_msg_id": msg.get("client_msg_id"),
                    "is_group": msg["is_group"]
                }

                if msg["is_group"]:
                    message_info["group_id"] = msg["group_id"]
                else:
                    message_info["receiver_id"] = msg["receiver_id"]

                result.append(message_info)

            return result

        except Exception as e:
            self.logger.error(f"按时间段获取消息失败: {e}")
            return []

    async def mark_message_delivered(self, message_id: str) -> bool:
        """标记消息为已送达"""
        try:
            result = await self.db_messages.update_one(
                {"message_id": message_id},
                {"$set": {"delivered": True}}
            )
            return result.modified_count > 0
        except Exception as e:
            self.logger.error(f"标记消息为已送达失败: {e}")
            return False

    async def mark_message_read(self, message_id: str) -> bool:
        """标记消息为已读"""
        try:
            result = await self.db_messages.update_one(
                {"message_id": message_id},
                {"$set": {"read": True}}
            )
            return result.modified_count > 0
        except Exception as e:
            self.logger.error(f"标记消息为已读失败: {e}")
            return False

    async def get_unread_count(self, user_id: int) -> int:
        """获取用户未读消息数量"""
        try:
            count = await self.db_messages.count_documents({
                "receiver_id": user_id,
                "read": False,
                "is_group": False
            })
            return count
        except Exception as e:
            self.logger.error(f"获取未读消息数量失败: {e}")
            return 0

    async def delete_message(self, message_id: str, user_id: int) -> bool:
        """删除消息（软删除）"""
        try:
            result = await self.db_messages.update_one(
                {
                    "message_id": message_id,
                    "$or": [
                        {"sender_id": user_id},
                        {"receiver_id": user_id}
                    ]
                },
                {"$set": {"deleted": True, "deleted_at": datetime.datetime.now()}}
            )
            return result.modified_count > 0
        except Exception as e:
            self.logger.error(f"删除消息失败: {e}")
            return False

    async def get_message_statistics(self, user_id: Optional[int] = None,
                                     group_id: Optional[str] = None) -> Dict[str, Any]:
        """获取消息统计信息"""
        try:
            pipeline = []

            # 构建查询条件
            match_condition = {}
            if user_id:
                match_condition["$or"] = [
                    {"sender_id": user_id},
                    {"receiver_id": user_id}
                ]
            if group_id:
                match_condition["group_id"] = group_id

            if match_condition:
                pipeline.append({"$match": match_condition})

            # 聚合统计
            pipeline.extend([
                {
                    "$group": {
                        "_id": {
                            "year": {"$year": "$created_at"},
                            "month": {"$month": "$created_at"},
                            "day": {"$dayOfMonth": "$created_at"}
                        },
                        "count": {"$sum": 1},
                        "private_count": {
                            "$sum": {"$cond": [{"$eq": ["$is_group", False]}, 1, 0]}
                        },
                        "group_count": {
                            "$sum": {"$cond": [{"$eq": ["$is_group", True]}, 1, 0]}
                        }
                    }
                },
                {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}}
            ])

            cursor = await self.db_messages.aggregate(pipeline)
            stats = await cursor.to_list(length=None)
            # 计算总数
            total = 0
            for stat in stats:
                total += stat["count"]

            return {
                "total_messages": total,
                "daily_stats": stats,
                "private_total": sum(stat["private_count"] for stat in stats),
                "group_total": sum(stat["group_count"] for stat in stats)
            }

        except Exception as e:
            self.logger.error(f"获取消息统计失败: {e}")
            return {
                "total_messages": 0,
                "daily_stats": [],
                "private_total": 0,
                "group_total": 0
            }
