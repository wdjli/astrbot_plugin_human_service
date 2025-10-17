"""
黑名单格式化器
负责格式化黑名单显示
"""
from typing import Set


class BlacklistFormatter:
    """黑名单格式化器"""
    
    @staticmethod
    async def format_blacklist(blacklist: Set[str], event, title: str) -> str:
        """
        格式化黑名单为显示文本
        
        Args:
            blacklist: 黑名单用户ID集合
            event: 事件对象（用于获取用户信息）
            title: 标题
            
        Returns:
            str: 格式化后的黑名单文本
        """
        if not blacklist:
            return None
        
        # 构建黑名单列表
        blacklist_text = f"{title}\n" + "="*30 + "\n\n"
        
        for idx, user_id in enumerate(sorted(blacklist), 1):
            # 尝试获取用户昵称
            try:
                user_info = await event.bot.get_stranger_info(user_id=int(user_id))
                nickname = user_info.get("nickname", user_id)
                blacklist_text += f"{idx}. {nickname} ({user_id})\n"
            except Exception:
                # 获取用户信息失败，只显示QQ号
                blacklist_text += f"{idx}. {user_id}\n"
        
        blacklist_text += f"\n共 {len(blacklist)} 个用户"
        return blacklist_text

