from enum import Enum


# 消息类型枚举
class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    LINK = "link"
    SYSTEM = "system"


# 用户状态枚举
class UserStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    AWAY = "away"
    BUSY = "busy"


# 在原有的数据结构部分添加以下内容

# 群聊相关枚举
class GroupRole(str, Enum):
    """群成员角色"""
    OWNER = "owner"  # 群主
    ADMIN = "admin"  # 管理员
    MEMBER = "member"  # 普通成员


class GroupStatus(str, Enum):
    """群状态"""
    ACTIVE = "active"  # 活跃
    DISBANDED = "disbanded"  # 已解散
    FROZEN = "frozen"  # 冻结
