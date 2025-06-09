from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@register(
    "astrbot_plugin_human_service",
    "Zhalslar",
    "人工客服插件",
    "1.0.0",
    "https://github.com/Zhalslar/astrbot_plugin_human_service",
)
class HumanServicePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 管理员 QQ
        self.admin_id = context.get_config()["admins_id"][0]
        # 用于存储会话信息的字典
        self.session_map = {}

    @filter.command("转人工")
    async def transfer_to_human(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        send_name = event.get_sender_name()
        if sender_id in self.session_map:
            yield event.plain_result("⚠ 您已经在等待接入或正在对话中")
            return
        self.session_map[sender_id] = {"admin": self.admin_id, "status": "waiting"}
        reply = (
            f"用户 {send_name}({sender_id}) 请求转人工\n请发送 #接入对话 {sender_id}"
        )
        await event.bot.send_private_msg(user_id=self.admin_id, message=reply)
        yield event.plain_result(
            "🕓 您已请求转人工，请等待管理员接入\n如需取消请发送 #取消等待"
        )

    @filter.command("取消等待")
    async def cancel_wait(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if (
            sender_id in self.session_map
            and self.session_map[sender_id]["status"] == "waiting"
        ):
            del self.session_map[sender_id]
            reply = f"❗ 用户 {sender_id} 已取消人工请求"
            await event.bot.send_private_msg(user_id=self.admin_id, message=reply)
            yield event.plain_result("🆗 您已取消人工请求")
        else:
            yield event.plain_result("❎ 您当前没有待接入的人工请求")

    @filter.command("接入对话")
    async def accept_conversation(self, event: AiocqhttpMessageEvent):
        if not event.is_admin():
            return
        # 获取目标用户的 ID
        target_id = int(event.message_str.split()[1])
        if (
            target_id not in self.session_map
            or self.session_map[target_id]["status"] != "waiting"
        ):
            yield event.plain_result("❎ 用户不存在或未请求人工")
            return
        self.session_map[target_id]["status"] = "connected"
        yield event.bot.send_private_msg(
            user_id=target_id,
            message="☑ 管理员已接入，您现在可以开始对话了\n如需结束请发送 #结束对话",
        )
        yield event.plain_result(
            f"☑ 已接入用户 {target_id} 的对话\n暂停请发送 #暂停对话 {target_id} \n结束请发 #结束对话"
        )

    @filter.command("暂停对话")
    async def pause_conversation(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id != self.admin_id:
            return
        # 获取目标用户的 ID
        target_id = int(event.message_str.split()[1])
        session = self.session_map.get(target_id)
        if not session:
            yield event.plain_result("❎ 请输入需要暂停的用户id")
            return
        if session["status"] == "connected":
            session["status"] = "paused"
            yield event.bot.send_private_msg(
                user_id=target_id,
                message="⚠ 管理员已暂停对话，请稍候\n取消等待发送 #结束对话",
            )
            yield event.plain_result(f"✅ 已暂停与用户 {target_id} 的对话")
        else:
            yield event.plain_result("❎ 无法暂停：用户不存在或未处于对话中")

    @filter.command("恢复对话")
    async def resume_conversation(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id != self.admin_id:
            return
        # 获取目标用户的 ID
        target_id = int(event.message_str.split()[1])
        session = self.session_map.get(target_id)
        if session and session["status"] == "paused":
            session["status"] = "connected"
            yield event.bot.send_private_msg(
                user_id=target_id, message="🔔 管理员已恢复对话，请继续"
            )
            yield event.plain_result(f"✅ 已恢复与用户 {target_id} 的对话")
        else:
            yield event.plain_result("❎ 无法恢复：用户不存在或未处于暂停状态")

    @filter.command("结束对话")
    async def end_conversation(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        session = self.session_map.get(sender_id)
        if session:
            if session["status"] == "waiting":
                del self.session_map[sender_id]
                yield event.bot.send_private_msg(
                    user_id=self.admin_id,
                    message=f"🔔 用户 {sender_id} 已取消转人工请求（通过结束命令）",
                )
                yield event.plain_result("🆗 您已取消转人工请求")
            elif session["status"] in ["connected", "paused"]:
                del self.session_map[sender_id]
                yield event.bot.send_private_msg(
                    user_id=self.admin_id, message=f"🔔 用户 {sender_id} 已结束对话"
                )
                yield event.plain_result("🆗 您已结束对话")
        else:
            for uid, session in self.session_map.items():
                if session["admin"] == sender_id:
                    del self.session_map[uid]
                    yield event.bot.send_private_msg(
                        user_id=uid, message="🔔 管理员已结束对话"
                    )
                    yield event.plain_result(f"✅ 已结束与用户 {uid} 的对话")
                    return
            yield event.plain_result("❎ 当前无对话需要结束")
