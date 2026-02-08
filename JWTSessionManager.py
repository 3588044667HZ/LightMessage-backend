import datetime
import logging
import secrets
from typing import Optional, Set, Dict, Any

import jwt


class JWTSessionManager:
    """JWT会话管理"""

    def __init__(self, secret_key: Optional[str] = None, algorithm: str = 'HS256'):
        self.logger = logging.getLogger("JWTSessionManager")

        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = algorithm
        # 存储已吊销的Token（生产环境用Redis）
        self.revoked_tokens: Set[str] = set()

    def create_token(self, user_id: int, username: str, expires_in: int = 86400) -> str:
        """创建JWT Token"""
        payload = {
            'user_id': user_id,
            'username': username,
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in),
            'iat': datetime.datetime.now(datetime.timezone.utc),
            'jti': secrets.token_urlsafe(16),  # 唯一标识
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证并解析Token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # 检查Token是否被吊销
            jti = payload.get('jti')
            if jti in self.revoked_tokens:
                return None

            return payload
        except jwt.ExpiredSignatureError:
            self.logger.debug("Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            self.logger.debug(f"无效Token: {e}")
            return None

    def revoke_token(self, token: str) -> bool:
        """吊销Token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": False})
            jti = payload.get('jti')
            if jti:
                self.revoked_tokens.add(jti)
                return True
        except jwt.InvalidTokenError:
            pass
        return False

    def get_user_id_from_token(self, token: str) -> Optional[int]:
        """从Token获取用户ID"""
        payload = self.verify_token(token)
        if payload:
            user_id = payload.get('user_id')
            try:
                return int(user_id) if user_id is not None else None
            except (ValueError, TypeError):
                return None
        return None
