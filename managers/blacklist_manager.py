"""
黑名单管理器
负责管理用户黑名单功能
"""
from typing import Set, Dict, List


class BlacklistManager:
    """黑名单管理器"""
    
    def __init__(self, servicers_id: List[str], share_blacklist: bool):
        """
        初始化黑名单管理器
        
        Args:
            servicers_id: 客服ID列表
            share_blacklist: 是否共用黑名单
        """
        self.share_blacklist = share_blacklist
        
        if share_blacklist:
            # 共用黑名单：一个集合
            self.blacklist: Set[str] = set()
        else:
            # 独立黑名单：每个客服一个集合
            self.blacklist_per_servicer: Dict[str, Set[str]] = {sid: set() for sid in servicers_id}
    
    def is_blacklisted(self, user_id: str, servicer_id: str = None) -> bool:
        """
        检查用户是否在黑名单中
        
        Args:
            user_id: 用户ID
            servicer_id: 客服ID（可选）
            
        Returns:
            bool: 是否在黑名单中
        """
        if self.share_blacklist:
            return user_id in self.blacklist
        else:
            if servicer_id:
                return user_id in self.blacklist_per_servicer.get(servicer_id, set())
            else:
                # 如果没有指定客服，检查是否在任何客服的黑名单中
                return any(user_id in blacklist for blacklist in self.blacklist_per_servicer.values())
    
    def add(self, user_id: str, servicer_id: str):
        """
        将用户添加到黑名单
        
        Args:
            user_id: 用户ID
            servicer_id: 客服ID
        """
        if self.share_blacklist:
            self.blacklist.add(user_id)
        else:
            if servicer_id in self.blacklist_per_servicer:
                self.blacklist_per_servicer[servicer_id].add(user_id)
    
    def remove(self, user_id: str, servicer_id: str) -> bool:
        """
        从黑名单中移除用户
        
        Args:
            user_id: 用户ID
            servicer_id: 客服ID
            
        Returns:
            bool: 是否成功移除
        """
        if self.share_blacklist:
            if user_id in self.blacklist:
                self.blacklist.remove(user_id)
                return True
            return False
        else:
            if servicer_id in self.blacklist_per_servicer and user_id in self.blacklist_per_servicer[servicer_id]:
                self.blacklist_per_servicer[servicer_id].remove(user_id)
                return True
            return False
    
    def get_blacklist(self, servicer_id: str = None) -> Set[str]:
        """
        获取黑名单
        
        Args:
            servicer_id: 客服ID（独立黑名单模式需要）
            
        Returns:
            Set[str]: 黑名单用户ID集合
        """
        if self.share_blacklist:
            return self.blacklist
        else:
            return self.blacklist_per_servicer.get(servicer_id, set())
    
    def get_count(self, servicer_id: str) -> int:
        """
        获取黑名单数量
        
        Args:
            servicer_id: 客服ID
            
        Returns:
            int: 黑名单用户数量
        """
        if self.share_blacklist:
            return len(self.blacklist)
        else:
            return len(self.blacklist_per_servicer.get(servicer_id, set()))

