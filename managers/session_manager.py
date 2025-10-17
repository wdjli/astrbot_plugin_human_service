"""
会话管理器
负责管理客服与用户的对话会话
"""
from typing import Dict, Optional


class SessionManager:
    """会话管理器"""
    
    def __init__(self):
        """初始化会话管理器"""
        # 会话映射：{user_id: {servicer_id, status, group_id, ...}}
        self.session_map: Dict[str, Dict] = {}
        # 用户选择客服的临时状态
        self.selection_map: Dict[str, Dict] = {}
        # 查看黑名单时的临时选择状态
        self.blacklist_view_selection: Dict[str, Dict] = {}
    
    def create_session(self, user_id: str, session_data: Dict):
        """
        创建会话
        
        Args:
            user_id: 用户ID
            session_data: 会话数据
        """
        self.session_map[user_id] = session_data
    
    def get_session(self, user_id: str) -> Optional[Dict]:
        """
        获取会话
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[Dict]: 会话数据，不存在则返回None
        """
        return self.session_map.get(user_id)
    
    def delete_session(self, user_id: str):
        """
        删除会话
        
        Args:
            user_id: 用户ID
        """
        if user_id in self.session_map:
            del self.session_map[user_id]
    
    def has_session(self, user_id: str) -> bool:
        """
        检查用户是否在会话中
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 是否在会话中
        """
        return user_id in self.session_map
    
    def is_servicer_busy(self, servicer_id: str) -> bool:
        """
        检查客服是否正在服务中
        
        Args:
            servicer_id: 客服ID
            
        Returns:
            bool: 是否正在服务
        """
        for session in self.session_map.values():
            if session.get("servicer_id") == servicer_id and session.get("status") == "connected":
                return True
        return False
    
    def get_user_by_servicer(self, servicer_id: str) -> Optional[str]:
        """
        获取客服正在服务的用户ID
        
        Args:
            servicer_id: 客服ID
            
        Returns:
            Optional[str]: 用户ID，无则返回None
        """
        for user_id, session in self.session_map.items():
            if session.get("servicer_id") == servicer_id and session.get("status") == "connected":
                return user_id
        return None
    
    def update_session_status(self, user_id: str, status: str):
        """
        更新会话状态
        
        Args:
            user_id: 用户ID
            status: 新状态
        """
        if user_id in self.session_map:
            self.session_map[user_id]["status"] = status
    
    def set_servicer(self, user_id: str, servicer_id: str):
        """
        设置会话的客服
        
        Args:
            user_id: 用户ID
            servicer_id: 客服ID
        """
        if user_id in self.session_map:
            self.session_map[user_id]["servicer_id"] = servicer_id

