"""
活动沉默模式管理器
负责控制活动沉默模式的拦截逻辑
"""
from typing import Set


class SilenceModeManager:
    """活动沉默模式管理器"""
    
    # 人工客服相关的命令列表
    SERVICE_COMMANDS = [
        "/转人工", "转人工",
        "/转人机", "转人机", 
        "/取消排队", "取消排队",
        "/排队状态", "排队状态",
        "/接入对话", "接入对话",
        "/拒绝接入", "拒绝接入",
        "/结束对话", "结束对话",
        "/拉黑", "拉黑",
        "/取消拉黑", "取消拉黑",
        "/查看黑名单", "查看黑名单",
        "/导出记录", "导出记录",
        "/翻译测试", "翻译测试",
        "/kfhelp", "kfhelp",
    ]
    
    def __init__(self, enabled: bool, servicers_id: list):
        """
        初始化活动沉默模式管理器
        
        Args:
            enabled: 是否启用沉默模式
            servicers_id: 客服ID列表
        """
        self.enabled = enabled
        self.servicers_id = set(servicers_id)
    
    def should_block_message(self, sender_id: str, message_text: str, 
                            session_map: dict, selection_map: dict, 
                            blacklist_view_selection: dict) -> bool:
        """
        判断是否应该阻止消息
        
        Args:
            sender_id: 发送者ID
            message_text: 消息文本
            session_map: 会话映射
            selection_map: 选择映射
            blacklist_view_selection: 黑名单查看选择映射
            
        Returns:
            bool: True表示应该阻止，False表示允许通过
        """
        if not self.enabled:
            return False  # 未启用沉默模式，不阻止
        
        # 检查是否是人工客服命令
        is_service_command = any(message_text.startswith(cmd) for cmd in self.SERVICE_COMMANDS)
        
        # 检查是否在对话相关状态中
        is_in_conversation = (
            sender_id in session_map or 
            sender_id in selection_map or
            sender_id in blacklist_view_selection or
            sender_id in self.servicers_id  # 客服的所有消息都允许
        )
        
        # 如果不是人工客服相关，则阻止
        return not (is_service_command or is_in_conversation)
    
    def is_service_command(self, message_text: str) -> bool:
        """
        检查是否是人工客服命令
        
        Args:
            message_text: 消息文本
            
        Returns:
            bool: 是否是人工客服命令
        """
        return any(message_text.startswith(cmd) for cmd in self.SERVICE_COMMANDS)
    
    def is_servicer(self, sender_id: str) -> bool:
        """
        检查是否是客服
        
        Args:
            sender_id: 发送者ID
            
        Returns:
            bool: 是否是客服
        """
        return sender_id in self.servicers_id

