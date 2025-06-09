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
    "1.0.1",
    "https://github.com/Zhalslar/astrbot_plugin_human_service",
)
class HumanServicePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.admin_id: str = config.get("admin_id", "")
        if not self.admin_id:
            for admin_id in context.get_config()["admins_id"]:
                if admin_id.isdigit():
                    self.admin_id = admin_id
                    break
        self.session_map = {}
        self.prefix: list[str] = context.get_config()["wake_prefix"][0]

    @filter.command("转人工", priority=1)
    async def transfer_to_human(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        send_name = event.get_sender_name()
        group_id = event.get_group_id() or "0"

        if sender_id in self.session_map:
            yield event.plain_result("⚠ 您已在等待接入或正在对话")
            return

        self.session_map[sender_id] = {
            "admin": self.admin_id,
            "status": "waiting",
            "group_id": group_id,
        }

        reply = f"用户🗣{send_name}({sender_id}) 请求转人工\n请发送 {self.prefix}接入对话 {sender_id}"
        await self.send(event, message=reply, user_id=self.admin_id)
        yield event.plain_result("正在等待客服👤转接...")

    @filter.command("转人机", priority=1)
    async def cancel_wait(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()
        session = self.session_map.get(sender_id)

        if session and session["status"] == "connected":
            del self.session_map[sender_id]
            await self.send(
                event,
                message=f"❗{sender_name} 已取消人工请求",
                user_id=self.admin_id,
            )
            yield event.plain_result("好的，我现在是人机啦！")


    @filter.command("接入对话", priority=1)
    async def accept_conversation(self, event: AiocqhttpMessageEvent):
        if not event.is_admin():
            return
        target_id = event.message_str.split()[1]
        session = self.session_map.get(target_id)

        if not session or session["status"] != "waiting":
            yield event.plain_result("❎ 用户不存在或未请求人工")
            return

        if session["status"] == "connected":
            yield event.plain_result("❎ 您正在与该用户对话")

        session["status"] = "connected"
        await self.send(
            event,
            message="管理员👤已接入",
            group_id=session["group_id"],
            user_id=target_id,
        )
        yield event.plain_result(
            f"☑ 已接入, 接下来我将会把你的消息转发给对方\n"
            f"{self.prefix}暂停对话 {target_id} \n"
            f"{self.prefix}结束对话"
        )
        event.stop_event()

    @filter.command("暂停对话", priority=1)
    async def pause_conversation(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id != self.admin_id:
            return

        target_id = event.message_str.split()[1]
        session = self.session_map.get(target_id)

        if not session:
            yield event.plain_result("❎ 请输入需要暂停的用户id")
            return

        if session["status"] == "connected":
            session["status"] = "paused"
            await self.send(
                event,
                message="⚠ 管理员👤暂停了对话",
                group_id=session["group_id"],
                user_id=target_id,
            )
            yield event.plain_result(f"✅ 已暂停与用户 {target_id} 的对话")
        else:
            yield event.plain_result("❎ 无法暂停：用户不存在或未处于对话中")

    @filter.command("恢复对话", priority=1)
    async def resume_conversation(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id != self.admin_id:
            return

        target_id = event.message_str.split()[1]
        session = self.session_map.get(target_id)

        if session and session["status"] == "paused":
            session["status"] = "connected"
            await self.send(
                event,
                message="🔔 管理员👤已恢复对话，请继续",
                group_id=session["group_id"],
                user_id=target_id,
            )
            yield event.plain_result(f"✅ 已恢复与用户 {target_id} 的对话")
        else:
            yield event.plain_result("❎ 无法恢复：用户不存在或未处于暂停状态")

    @filter.command("结束对话")
    async def end_conversation(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        session = self.session_map.get(sender_id)

        # 用户主动结束会话
        if session:
            if session["status"] == "waiting":
                del self.session_map[sender_id]
                await self.send(
                    event,
                    message=f"🔔 用户 {sender_id} 已取消转人工请求",
                    user_id=self.admin_id,
                )
                yield event.plain_result("🆗 您已取消转人工请求")

            elif session["status"] in ["connected", "paused"]:
                await self.send(
                    event,
                    message=f"🔔 用户 {sender_id} 已结束对话",
                    user_id=self.admin_id,
                )
                del self.session_map[sender_id]
                yield event.plain_result("🆗 您已结束对话")
        # 管理员主动结束会话
        else:
            for uid, sess in self.session_map.items():
                if sess["admin"] == sender_id:
                    await self.send(
                        event,
                        message="🔔 管理员👤已结束对话",
                        group_id=sess["group_id"],
                        user_id=uid,
                    )
                    del self.session_map[uid]
                    yield event.plain_result(f"✅ 已结束与用户 {uid} 的对话")
                    return

            yield event.plain_result("❎ 当前无对话需要结束")

    async def send(
        self,
        event: AiocqhttpMessageEvent,
        message,
        group_id: int | str | None = None,
        user_id: int | str | None = None,
    ):
        """向用户发消息，兼容群聊或私聊"""
        if group_id and str(group_id) != "0":
            await event.bot.send_group_msg(group_id=int(group_id), message=message)
        elif user_id:
            await event.bot.send_private_msg(user_id=int(user_id), message=message)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_match(self, event: AiocqhttpMessageEvent):
        """监听对话消息转发"""
        message_str = event.get_message_str()

        # 管理员 → 用户
        if event.is_private_chat() and event.is_admin():
            # 查找管理员当前接入的用户
            for user_id, session in self.session_map.items():
                if (
                    session["admin"] == self.admin_id
                    and session["status"] == "connected"
                ):
                    await self.send(
                        event,
                        message=f"👤：{message_str}",
                        group_id=session["group_id"],
                        user_id=user_id,
                    )
                    event.stop_event()
                    break

        # 用户 → 管理员
        else:
            session = self.session_map.get(event.get_sender_id())
            if session and session["status"] == "connected":
                await self.send(
                    event,
                    message=f"🗣：{message_str}",
                    user_id=self.admin_id,
                )
                event.stop_event()
