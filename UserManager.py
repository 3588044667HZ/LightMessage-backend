import hashlib
from typing import Dict, Optional, List

from models import User
from pymongo import AsyncMongoClient

uri = "mongodb://localhost:27017/"


class UserManager:
    """用户管理"""

    def __init__(self):
        # 内存存储用户数据（生产环境用数据库）
        # self.users: Dict[int, User] = {}
        self.username_to_id: Dict[str, int] = {}
        # self._initialize_sample_users()
        self.dbclient = AsyncMongoClient(uri)
        self.db = self.dbclient["IM"]["user"]

    def _initialize_sample_users(self):
        """初始化示例用户"""
        sample_users = [
            {
                "user_id": 1,
                "username": "lwr",
                "nickname": "LWR",
                "password": "NieQie123",  # 实际密码
                "department": "技术部",
                "tags": ["后端开发", "Python"],
                "avatar": "http://127.0.0.1:8080/avatar/1",
                "contacts": [2]  # 联系人ID
            },
            {
                "user_id": 2,
                "username": "zls",
                "nickname": "ZLS",
                "password": "YiQi123",
                "department": "设计部",
                "tags": ["UI设计", "产品"],
                "avatar": "http://127.0.0.1:8080/avatar/2",
                "contacts": [1]
            },
            {
                "user_id": 3,
                "username": "test",
                "nickname": "测试用户",
                "password": "test123",
                "department": "测试部",
                "tags": ["测试", "QA"],
                "contacts": [1, 2],
                "avatar": "http://127.0.0.1:8080/avatar/3"
            }
        ]

        for user_data in sample_users:
            user_id = user_data["user_id"]
            self.users[user_id] = User(
                user_id=user_id,
                username=user_data["username"],
                nickname=user_data["nickname"],
                password_hash=self.hash_password(user_data["password"], str(user_id)),
                department=user_data["department"],
                tags=user_data["tags"],
                contact_list=user_data["contacts"],
                avatar=user_data["avatar"],
            )
            self.username_to_id[user_data["username"]] = user_id

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        """密码哈希（生产环境应该用bcrypt）"""
        # 这里使用简单的SHA256，生产环境请用bcrypt或argon2
        return hashlib.sha256((password + salt).encode()).hexdigest()

    async def verify_password(self, user_id: int, password: str) -> bool:
        """验证密码"""
        res = await self.db.find_one({"user_id": user_id})
        user = User(
            user_id=user_id, password_hash=self.hash_password(res["password"], str(user_id)), )
        if not user:
            return False

        password_hash = self.hash_password(password, str(user_id))
        return password_hash == user.password_hash

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        # user_id = self.username_to_id.get(username)
        user_id = await self.db.find_one({"username": username})
        if user_id:
            return await self.db.find_one({"user_id": user_id})
        return None

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        res = await self.db.find_one({"user_id": user_id})
        return User(user_id=user_id, username=res.get("username", ""), nickname=res["nickname"],
                    password_hash=self.hash_password(res["password"], str(user_id)), avatar=res["avatar"],
                    department=res["department"], tags=res["tags"], contact_list=res["contacts"])

    async def get_user_contacts(self, user_id: int) -> List[User]:
        """获取用户的联系人列表"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return []

        contacts = []
        for contact_id in user.contact_list:
            contact = await self.get_user_by_id(contact_id)
            if contact:
                contacts.append(contact)

        return contacts

    async def search_users(self, keyword: str, limit: int = 20) -> List[User]:
        """搜索用户"""
        results = []
        for user in self.users.values():
            if (keyword.lower() in user.username.lower() or
                    keyword.lower() in user.nickname.lower() or
                    keyword.lower() in user.department.lower()):
                results.append(user)
                if len(results) >= limit:
                    break
        return results
