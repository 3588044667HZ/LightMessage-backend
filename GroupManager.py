# GroupManager.py
import datetime
import logging
import uuid
from typing import Dict, List, Optional, Any

from pymongo import AsyncMongoClient

from enums import GroupRole, GroupStatus
from models import Group, GroupMember

uri = "mongodb://localhost:27017/"


class GroupManager:
    """群组管理器"""

    def __init__(self):
        self.logger = logging.getLogger("GroupManager")
        self.dbclient = AsyncMongoClient(uri)
        self.db_groups = self.dbclient["IM"]["groups"]
        self.db_members = self.dbclient["IM"]["group_members"]

        # 创建索引
        # asyncio.run(self._create_indexes())

    async def initialize(self):
        await self._create_indexes()
        await self._initialize_sample_groups()

    async def _create_indexes(self):
        """创建数据库索引"""
        try:
            # 群组集合索引
            await self.db_groups.create_index("group_id", unique=True)
            await self.db_groups.create_index("owner_id")
            await self.db_groups.create_index("name")

            # 群成员集合索引
            await self.db_members.create_index([("group_id", 1), ("user_id", 1)], unique=True)
            await self.db_members.create_index("user_id")
            await self.db_members.create_index("role")

            self.logger.debug("群组管理器索引创建完成")
        except Exception as e:
            self.logger.error(f"创建索引失败: {e}")

    async def _initialize_sample_groups(self):
        """初始化示例群组"""
        # 检查是否已有群组
        count = await self.db_groups.count_documents({})
        print("count", count)
        if count > 0:
            return

        # 创建技术交流群
        tech_group = await self.create_group(
            name="技术交流群",
            owner_id=1,
            description="技术讨论、问题解答",
            avatar="tech_group.jpg"
        )

        if tech_group:
            # 添加初始成员
            await self.add_member(tech_group.group_id, 1, GroupRole.OWNER)
            await self.add_member(tech_group.group_id, 2, GroupRole.ADMIN)
            await self.add_member(tech_group.group_id, 3, GroupRole.MEMBER)

        # 创建设计交流群
        design_group = await self.create_group(
            name="设计交流群",
            owner_id=2,
            description="UI/UX设计讨论",
            avatar="design_group.jpg"
        )

        if design_group:
            await self.add_member(design_group.group_id, 2, GroupRole.OWNER)
            await self.add_member(design_group.group_id, 1, GroupRole.MEMBER)

    async def create_group(self, name: str, owner_id: int,
                           description: str = "", avatar: str = "") -> Optional[Group]:
        """创建新群组"""
        try:
            group_id = f"g_{uuid.uuid4().hex[:8]}"
            group = Group(
                group_id=group_id,
                name=name,
                owner_id=owner_id,
                description=description,
                avatar=avatar or "group_default.jpg",
                created_at=int(datetime.datetime.now().timestamp()),
                member_count=1,
                settings={
                    "invite_permission": "admin",
                    "message_permission": "all",
                    "max_members": 500,
                    "mute_all": False
                }
            )

            # 保存到数据库
            await self.db_groups.insert_one(
                {"group_id": group_id, "owner_id": owner_id, "name": name, "avatar": avatar or "group_default.jpg",
                 "created_at": int(datetime.datetime.now().timestamp()), "member_count": 1,
                 "settings": {
                     "invite_permission": "admin",
                     "message_permission": "all",
                     "max_members": 500,
                     "mute_all": False
                 }})

            # 自动添加群主为成员
            await self.add_member(group_id, owner_id, GroupRole.OWNER)

            self.logger.info(f"群组创建成功: {group_id} ({name}), 群主: {owner_id}")
            return group
        except Exception as e:
            self.logger.error(f"创建群组失败: {e}")
            return None

    async def add_member(self, group_id: str, user_id: int,
                         role: GroupRole = GroupRole.MEMBER) -> bool:
        """添加成员到群组"""
        try:
            # 检查群组是否存在
            group = await self.db_groups.find_one({"group_id": group_id})
            if not group:
                self.logger.warning(f"群组不存在: {group_id}")
                return False

            # 检查是否已满
            if group["member_count"] >= group["settings"].get("max_members", 500):
                self.logger.warning(f"群组 {group_id} 已达到最大成员数")
                return False

            # 检查是否已是成员
            existing_member = await self.db_members.find_one({
                "group_id": group_id,
                "user_id": user_id
            })
            if existing_member:
                self.logger.warning(f"用户 {user_id} 已是群组 {group_id} 的成员")
                return False

            # 创建群成员记录
            member = GroupMember(
                group_id=group_id,
                user_id=user_id,
                role=role,
                joined_at=int(datetime.datetime.now().timestamp()),
                nickname="",
                mute_until=0
            )

            # 保存成员
            await self.db_members.insert_one({
                "group_id": group_id,
                "user_id": user_id,
                "role": role,
                "joined_at": int(datetime.datetime.now().timestamp()),
                "nickname": member.nickname,
                "mute_until": 0,
            })

            # 更新群组成员数
            await self.db_groups.update_one(
                {"group_id": group_id},
                {"$inc": {"member_count": 1}}
            )
            self.logger.info(f"用户 {user_id} 加入群组 {group_id}, 角色: {role.value}")
            return True
        except Exception as e:
            self.logger.error(f"添加成员失败: {e}")
            return False

    async def remove_member(self, group_id: str, user_id: int) -> bool:
        """从群组移除成员"""
        try:
            # 检查群组和成员
            group = await self.db_groups.find_one({"group_id": group_id})
            if not group:
                return False

            # 不能移除群主
            if user_id == group["owner_id"]:
                self.logger.warning(f"不能移除群主 {user_id}，请先转移群主或解散群")
                return False

            # 移除成员记录
            result = await self.db_members.delete_one({
                "group_id": group_id,
                "user_id": user_id
            })

            if result.deleted_count == 0:
                return False

            # 更新群组成员数
            await self.db_groups.update_one(
                {"group_id": group_id},
                {"$inc": {"member_count": -1}}
            )

            self.logger.info(f"用户 {user_id} 从群组 {group_id} 移除")
            return True

        except Exception as e:
            self.logger.error(f"移除成员失败: {e}")
            return False

    async def update_member_role(self, group_id: str, user_id: int,
                                 new_role: GroupRole) -> bool:
        """更新成员角色"""
        try:
            result = await self.db_members.update_one(
                {"group_id": group_id, "user_id": user_id},
                {"$set": {"role": new_role.value}}
            )

            if result.modified_count > 0:
                self.logger.info(f"群组 {group_id} 用户 {user_id} 角色变更: {new_role.value}")
                return True
            return False

        except Exception as e:
            self.logger.error(f"更新成员角色失败: {e}")
            return False

    async def get_group(self, group_id: str) -> Optional[Group]:
        """获取群组信息"""
        try:
            group_data = await self.db_groups.find_one({"group_id": group_id})
            if group_data:
                return Group(**group_data)
            return None
        except Exception as e:
            self.logger.error(f"获取群组信息失败: {e}")
            return None

    async def get_group_members(self, group_id: str) -> List[GroupMember]:
        """获取群组成员列表"""
        try:
            cursor = self.db_members.find({"group_id": group_id})
            members = await cursor.to_list(length=None)
            return [GroupMember(**member) for member in members]
        except Exception as e:
            self.logger.error(f"获取群组成员失败: {e}")
            return []

    async def get_user_groups(self, user_id: int) -> List[Group]:
        """获取用户加入的所有群组"""
        try:
            # 获取用户加入的所有群组ID
            cursor = self.db_members.find({"user_id": user_id})
            members = await cursor.to_list(length=None)
            group_ids = [member["group_id"] for member in members]

            # 获取群组信息
            groups = []
            for group_id in group_ids:
                group_data = await self.db_groups.find_one({"group_id": group_id})
                if group_data:
                    group_data_: dict = group_data.copy()
                    del group_data_["_id"]
                    groups.append(Group(**group_data_))

            return groups
        except DeprecationWarning as e:
            self.logger.error(f"获取用户群组失败: {e}")
            return []

    async def is_member(self, group_id: str, user_id: int) -> bool:
        """检查用户是否是群组成员"""
        try:
            member = await self.db_members.find_one({
                "group_id": group_id,
                "user_id": user_id
            })
            return member is not None
        except Exception as e:
            self.logger.error(f"检查成员状态失败: {e}")
            return False

    async def get_member_role(self, group_id: str, user_id: int) -> Optional[GroupRole]:
        """获取成员在群组中的角色"""
        try:
            member = await self.db_members.find_one({
                "group_id": group_id,
                "user_id": user_id
            })
            if member:
                return GroupRole(member["role"])
            return None
        except Exception as e:
            self.logger.error(f"获取成员角色失败: {e}")
            return None

    async def search_groups(self, keyword: str, limit: int = 20) -> List[Group]:
        """搜索群组"""
        try:
            # 使用正则表达式进行模糊搜索
            query = {
                "$or": [
                    {"name": {"$regex": keyword, "$options": "i"}},
                    {"description": {"$regex": keyword, "$options": "i"}}
                ],
                "status": GroupStatus.ACTIVE.value
            }

            cursor = self.db_groups.find(query).limit(limit)
            groups_data = await cursor.to_list(length=limit)
            return [Group(**group) for group in groups_data]
        except Exception as e:
            self.logger.error(f"搜索群组失败: {e}")
            return []

    async def update_group_settings(self, group_id: str, settings: Dict[str, Any]) -> bool:
        """更新群组设置"""
        try:
            result = await self.db_groups.update_one(
                {"group_id": group_id},
                {"$set": {"settings": settings}}
            )
            return result.modified_count > 0
        except Exception as e:
            self.logger.error(f"更新群组设置失败: {e}")
            return False

    async def transfer_ownership(self, group_id: str, old_owner_id: int,
                                 new_owner_id: int) -> bool:
        """转移群主"""
        try:
            # 检查新群主是否是成员
            is_member = await self.is_member(group_id, new_owner_id)
            if not is_member:
                return False

            # 更新群主
            result = await self.db_groups.update_one(
                {"group_id": group_id, "owner_id": old_owner_id},
                {"$set": {"owner_id": new_owner_id}}
            )

            if result.modified_count == 0:
                return False

            # 更新角色
            await self.update_member_role(group_id, old_owner_id, GroupRole.ADMIN)
            await self.update_member_role(group_id, new_owner_id, GroupRole.OWNER)

            self.logger.info(f"群组 {group_id} 群主转移: {old_owner_id} -> {new_owner_id}")
            return True

        except Exception as e:
            self.logger.error(f"转移群主失败: {e}")
            return False

    async def disband_group(self, group_id: str, operator_id: int) -> bool:
        """解散群组"""
        try:
            # 检查操作者是否是群主
            group = await self.get_group(group_id)
            if not group or group.owner_id != operator_id:
                return False

            # 标记为已解散
            await self.db_groups.update_one(
                {"group_id": group_id},
                {"$set": {"status": GroupStatus.DISBANDED.value}}
            )

            # 删除所有成员记录
            await self.db_members.delete_many({"group_id": group_id})

            self.logger.info(f"群组 {group_id} 已解散，操作者: {operator_id}")
            return True

        except Exception as e:
            self.logger.error(f"解散群组失败: {e}")
            return False

    async def mute_member(self, group_id: str, user_id: int,
                          duration_minutes: int) -> bool:
        """禁言成员"""
        try:
            if not await self.is_member(group_id, user_id):
                return False

            if duration_minutes <= 0:
                mute_until = 0  # 解除禁言
            else:
                mute_until = int(datetime.datetime.now().timestamp()) + (duration_minutes * 60)

            result = await self.db_members.update_one(
                {"group_id": group_id, "user_id": user_id},
                {"$set": {"mute_until": mute_until}}
            )

            if result.modified_count > 0:
                self.logger.info(f"群组 {group_id} 用户 {user_id} 禁言 {duration_minutes} 分钟")
                return True
            return False

        except Exception as e:
            self.logger.error(f"禁言成员失败: {e}")
            return False

    async def is_muted(self, group_id: str, user_id: int) -> bool:
        """检查用户是否被禁言"""
        try:
            member = await self.db_members.find_one({
                "group_id": group_id,
                "user_id": user_id
            })
            if not member:
                return False

            mute_until = member.get("mute_until", 0)
            if mute_until <= 0:
                return False

            current_time = int(datetime.datetime.now().timestamp())
            return current_time < mute_until

        except Exception as e:
            self.logger.error(f"检查禁言状态失败: {e}")
            return False

    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            total_groups = await self.db_groups.count_documents({})
            active_groups = await self.db_groups.count_documents(
                {"status": GroupStatus.ACTIVE.value}
            )

            # 获取所有群组的成员数统计
            pipeline = [
                {"$group": {
                    "_id": None,
                    "total_members": {"$sum": "$member_count"}
                }}
            ]

            cursor = self.db_groups.aggregate(pipeline)
            result = await cursor.to_list(length=1)
            total_members = result[0]["total_members"] if result else 0

            # 按规模统计群组
            groups_by_size = {
                "1-10": 0,
                "11-50": 0,
                "51-100": 0,
                "100+": 0
            }

            cursor = self.db_groups.find({})
            async for group in cursor:
                count = group["member_count"]
                if 1 <= count <= 10:
                    groups_by_size["1-10"] += 1
                elif 11 <= count <= 50:
                    groups_by_size["11-50"] += 1
                elif 51 <= count <= 100:
                    groups_by_size["51-100"] += 1
                else:
                    groups_by_size["100+"] += 1

            return {
                "total_groups": total_groups,
                "active_groups": active_groups,
                "total_members": total_members,
                "groups_by_size": groups_by_size
            }
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")
            return {
                "total_groups": 0,
                "active_groups": 0,
                "total_members": 0,
                "groups_by_size": {}
            }
