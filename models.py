import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set

from websockets import ServerConnection

from enums import GroupStatus, GroupRole, UserStatus, MessageType


@dataclass
class Group:
    """群组信息"""
    group_id: str
    name: str
    owner_id: int  # 群主ID
    description: str = ""
    avatar: str = "group_default.jpg"
    created_at: int = field(default_factory=lambda: int(datetime.datetime.now().timestamp()))
    status: GroupStatus = GroupStatus.ACTIVE
    max_members: int = 500  # 最大成员数
    member_count: int = 0  # 当前成员数
    settings: Dict[str, Any] = field(default_factory=dict)  # 群设置


@dataclass
class GroupMember:
    """群成员信息"""
    group_id: str
    user_id: int
    role: GroupRole = GroupRole.MEMBER
    joined_at: int = field(default_factory=lambda: int(datetime.datetime.now().timestamp()))
    nickname: str = ""  # 群昵称
    last_read_message_id: Optional[str] = None  # 最后读取的消息ID
    mute_until: int = 0  # 禁言到期时间戳，0表示不禁言


# 数据类定义
@dataclass
class User:
    """用户信息"""
    user_id: int = 0
    username: str = ""
    nickname: str = ""
    password_hash: str = ""  # 存储密码哈希
    avatar: str = "default.jpg"
    status: UserStatus = UserStatus.OFFLINE
    last_seen: int = 0
    department: str = ""
    tags: List[str] = field(default_factory=list)
    contact_list: List[int] = field(default_factory=list)  # 联系人ID列表


@dataclass
class ClientConnection:
    """客户端连接信息"""
    connection_id: str
    websocket: ServerConnection
    user_id: Optional[int] = None
    device_id: Optional[str] = None
    authenticated: bool = False
    last_heartbeat: datetime.datetime = field(default_factory=datetime.datetime.now)
    last_activity: datetime.datetime = field(default_factory=datetime.datetime.now)
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    client_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """消息结构"""
    message_id: str
    sender_id: int
    receiver_id: int  # 对于群聊，这里是group_id
    message_type: MessageType
    content: Dict[str, Any]
    timestamp: int
    read: bool = False
    delivered: bool = False
    is_group: bool = False  # 是否是群消息
    reply_to: Optional[str] = None  # 回复的消息ID
