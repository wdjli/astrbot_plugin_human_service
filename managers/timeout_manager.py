"""
超时管理器
负责管理对话超时和排队超时
"""
import time
from typing import Dict, List


class TimeoutManager:
    """超时管理器"""
    
    def __init__(self, conversation_timeout: int, warning_seconds: int):
        """
        初始化超时管理器
        
        Args:
            conversation_timeout: 对话超时时间（秒）
            warning_seconds: 超时警告提前时间（秒）
        """
        self.conversation_timeout = conversation_timeout
        self.warning_seconds = warning_seconds
        # 对话开始时间记录：{user_id: {"start_time": timestamp, "warned": bool}}
        self.timers: Dict[str, Dict] = {}
    
    def start_timer(self, user_id: str):
        """
        开始计时
        
        Args:
            user_id: 用户ID
        """
        if self.conversation_timeout > 0:
            self.timers[user_id] = {
                "start_time": time.time(),
                "warned": False
            }
    
    def stop_timer(self, user_id: str):
        """
        停止计时
        
        Args:
            user_id: 用户ID
        """
        if user_id in self.timers:
            del self.timers[user_id]
    
    def get_elapsed_time(self, user_id: str) -> float:
        """
        获取已用时间
        
        Args:
            user_id: 用户ID
            
        Returns:
            float: 已用时间（秒）
        """
        if user_id not in self.timers:
            return 0
        return time.time() - self.timers[user_id]["start_time"]
    
    def get_remaining_time(self, user_id: str) -> float:
        """
        获取剩余时间
        
        Args:
            user_id: 用户ID
            
        Returns:
            float: 剩余时间（秒）
        """
        if self.conversation_timeout <= 0 or user_id not in self.timers:
            return float('inf')
        elapsed = self.get_elapsed_time(user_id)
        return self.conversation_timeout - elapsed
    
    def is_timeout(self, user_id: str) -> bool:
        """
        检查是否超时
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 是否超时
        """
        if self.conversation_timeout <= 0 or user_id not in self.timers:
            return False
        return self.get_elapsed_time(user_id) >= self.conversation_timeout
    
    def should_warn(self, user_id: str) -> bool:
        """
        是否应该发送警告
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 是否应该发送警告
        """
        if self.warning_seconds <= 0 or user_id not in self.timers:
            return False
        
        timer_info = self.timers[user_id]
        if timer_info.get("warned", False):
            return False
        
        remaining = self.get_remaining_time(user_id)
        return remaining <= self.warning_seconds and remaining > 0
    
    def mark_warned(self, user_id: str):
        """
        标记已警告
        
        Args:
            user_id: 用户ID
        """
        if user_id in self.timers:
            self.timers[user_id]["warned"] = True
    
    def get_timeout_users(self) -> List[str]:
        """
        获取所有超时的用户
        
        Returns:
            List[str]: 超时用户ID列表
        """
        return [user_id for user_id in self.timers.keys() if self.is_timeout(user_id)]
    
    def get_users_need_warning(self) -> List[str]:
        """
        获取所有需要警告的用户
        
        Returns:
            List[str]: 需要警告的用户ID列表
        """
        return [user_id for user_id in self.timers.keys() if self.should_warn(user_id)]

