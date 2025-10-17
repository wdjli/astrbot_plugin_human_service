"""
帮助文档构建器
负责生成用户和客服的帮助文档
"""


class HelpTextBuilder:
    """帮助文档构建器"""
    
    @staticmethod
    def build_user_help(config: dict) -> str:
        """
        构建用户帮助文档
        
        Args:
            config: 配置字典 {conversation_timeout, queue_timeout}
            
        Returns:
            str: 用户帮助文档
        """
        help_text = "📖 人工客服插件 - 使用帮助\n" + "="*35 + "\n\n"
        help_text += "• /转人工\n  请求转接人工客服，如有多个客服可选择\n\n"
        help_text += "• /转人机\n  取消转人工请求或结束对话\n\n"
        help_text += "• /取消排队\n  退出排队队列\n\n"
        help_text += "• /排队状态\n  查看当前排队位置和人数\n\n"
        help_text += "• /kfhelp\n  显示此帮助信息\n\n"
        
        help_text += "💡 提示：\n"
        help_text += "━"*35 + "\n"
        help_text += "• 客服忙碌时会自动加入排队\n"
        help_text += "• 可随时使用 /转人机 取消\n"
        
        if config.get("conversation_timeout", 0) > 0:
            help_text += f"• 对话限时 {config['conversation_timeout']} 秒\n"
        if config.get("queue_timeout", 0) > 0:
            help_text += f"• 排队限时 {config['queue_timeout']} 秒\n"
        
        return help_text
    
    @staticmethod
    def build_servicer_help(config: dict) -> str:
        """
        构建客服帮助文档
        
        Args:
            config: 配置字典
            
        Returns:
            str: 客服帮助文档
        """
        help_text = "📖 人工客服插件 - 帮助文档\n" + "="*35 + "\n\n"
        help_text += "👤 用户命令：\n"
        help_text += "━"*35 + "\n"
        help_text += "• /转人工\n  请求转接人工客服\n\n"
        help_text += "• /转人机\n  取消转人工或结束对话\n\n"
        help_text += "• /取消排队\n  退出排队队列\n\n"
        help_text += "• /排队状态\n  查看当前排队位置\n\n"
        
        help_text += "\n👨‍💼 客服命令：\n"
        help_text += "━"*35 + "\n"
        help_text += "• /接入对话\n  接入用户对话（回复用户消息）\n\n"
        help_text += "• /拒绝接入\n  拒绝用户接入请求\n\n"
        help_text += "• /结束对话\n  结束当前对话\n\n"
        help_text += "• /拉黑 QQ号\n  拉黑指定用户\n  示例：/拉黑 123456\n\n"
        help_text += "• /取消拉黑 QQ号\n  取消拉黑指定用户\n  示例：/取消拉黑 123456\n\n"
        help_text += "• /查看黑名单\n  查看黑名单列表\n\n"
        
        if config.get("enable_translation"):
            help_text += "• /翻译测试\n  测试翻译功能是否正常\n\n"
        
        if config.get("enable_chat_history"):
            help_text += "• /导出记录\n  导出当前会话聊天记录\n\n"
        
        help_text += "• /kfhelp\n  显示此帮助信息\n\n"
        
        # 添加配置信息
        help_text += "\n⚙️ 当前配置：\n"
        help_text += "━"*35 + "\n"
        help_text += f"• 客服数量：{config.get('servicers_count', 0)} 人\n"
        help_text += f"• 客服选择：{'开启' if config.get('enable_servicer_selection') else '关闭'}\n"
        help_text += f"• 黑名单模式：{'共用' if config.get('share_blacklist') else '独立'}\n"
        help_text += f"• 聊天记录：{'开启' if config.get('enable_chat_history') else '关闭'}\n"
        help_text += f"• 活动沉默：{'开启' if config.get('enable_silence_mode') else '关闭'}\n"
        
        if config.get("message_prefix"):
            help_text += f"• 消息前缀：\"{config['message_prefix']}\"\n"
        
        if config.get("message_suffix"):
            help_text += f"• 消息后缀：\"{config['message_suffix']}\"\n"
        
        if config.get("enable_random_reply"):
            help_text += f"• 答非所问：开启（文字：\"{config['random_reply_chars']}\"）\n"
        
        if config.get("enable_translation"):
            help_text += f"• 智能翻译：开启（{config.get('translation_main_language')}↔{config.get('translation_target_language')}，模型：{config.get('openai_model')}）\n"
        
        if config.get("conversation_timeout", 0) > 0:
            help_text += f"• 对话时限：{config['conversation_timeout']} 秒\n"
        if config.get("queue_timeout", 0) > 0:
            help_text += f"• 排队时限：{config['queue_timeout']} 秒\n"
        
        return help_text

