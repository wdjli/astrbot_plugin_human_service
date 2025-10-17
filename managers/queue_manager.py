"""
队列管理器
负责管理用户排队功能
"""
import time
from typing import Dict, List, Optional


class QueueManager:
    """队列管理器"""
    
    def __init__(self, servicers_id: List[str]):
        """
        初始化队列管理器
        
        Args:
            servicers_id: 客服ID列表
        """
        # 客服队列：{servicer_id: [{"user_id": "xxx", "name": "xxx", "group_id": "xxx", "time": timestamp}]}
        self.servicer_queue: Dict[str, List[Dict]] = {sid: [] for sid in servicers_id}
    
    def add(self, servicer_id: str, user_id: str, user_name: str, group_id: str) -> bool:
        """
        将用户添加到客服队列
        
        Args:
            servicer_id: 客服ID
            user_id: 用户ID
            user_name: 用户名称
            group_id: 群组ID
            
        Returns:
            bool: 是否成功添加（已在队列中则返回False）
        """
        if servicer_id not in self.servicer_queue:
            self.servicer_queue[servicer_id] = []
        
        # 检查用户是否已在队列中
        for item in self.servicer_queue[servicer_id]:
            if item["user_id"] == user_id:
                return False
        
        self.servicer_queue[servicer_id].append({
            "user_id": user_id,
            "name": user_name,
            "group_id": group_id,
            "time": time.time()
        })
        return True
    
    def get_position(self, servicer_id: str, user_id: str) -> int:
        """
        获取用户在队列中的位置
        
        Args:
            servicer_id: 客服ID
            user_id: 用户ID
            
        Returns:
            int: 位置（从1开始），-1表示不在队列中
        """
        if servicer_id not in self.servicer_queue:
            return -1
        for i, item in enumerate(self.servicer_queue[servicer_id]):
            if item["user_id"] == user_id:
                return i + 1
        return -1
    
    def remove(self, user_id: str) -> bool:
        """
        从所有队列中移除用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 是否成功移除
        """
        removed = False
        for servicer_id in self.servicer_queue:
            original_len = len(self.servicer_queue[servicer_id])
            self.servicer_queue[servicer_id] = [
                item for item in self.servicer_queue[servicer_id] 
                if item["user_id"] != user_id
            ]
            if len(self.servicer_queue[servicer_id]) < original_len:
                removed = True
        return removed
    
    def get_size(self, servicer_id: str) -> int:
        """
        获取队列大小
        
        Args:
            servicer_id: 客服ID
            
        Returns:
            int: 队列中的用户数量
        """
        return len(self.servicer_queue.get(servicer_id, []))
    
    def pop_next(self, servicer_id: str) -> Optional[Dict]:
        """
        从队列中取出下一个用户
        
        Args:
            servicer_id: 客服ID
            
        Returns:
            Optional[Dict]: 下一个用户信息，无则返回None
        """
        if servicer_id in self.servicer_queue and len(self.servicer_queue[servicer_id]) > 0:
            return self.servicer_queue[servicer_id].pop(0)
        return None
    
    def check_timeout(self, queue_timeout: int) -> List[Dict]:
        """
        检查排队超时的用户
        
        Args:
            queue_timeout: 超时时间（秒）
            
        Returns:
            List[Dict]: 超时用户列表
        """
        if queue_timeout <= 0:
            return []
        
        current_time = time.time()
        timeout_users = []
        
        for servicer_id in list(self.servicer_queue.keys()):
            queue = self.servicer_queue[servicer_id]
            remaining_queue = []
            
            for item in queue:
                elapsed = current_time - item["time"]
                
                if elapsed >= queue_timeout:
                    timeout_users.append(item)
                else:
                    remaining_queue.append(item)
            
            self.servicer_queue[servicer_id] = remaining_queue
        
        return timeout_users

