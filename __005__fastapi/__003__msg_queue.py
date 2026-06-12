import asyncio
import threading


# 创建消息队列管理器，为什么要创建？如果不创建，单单只用一个消息队列，那么当多个用户同时访问时，就会导致所有用户消息都挤在一个消息队列中，所以我们需要创建一个消息队列管理器
# 这里直接根据thread_id来创建消息队列，user_id就是thread_id
class MsgQueueManager:
    def __init__(self):
        self.msg_queue_dict = {}
        self.loop_dict = {}
        self.cancelled_ids = set()

    def get_msg_queue_by_user_id(self, user_id):
        if user_id not in self.msg_queue_dict:
            self.msg_queue_dict[user_id] = asyncio.Queue()
            self.loop_dict[user_id] = asyncio.get_running_loop()
            self.cancelled_ids.discard(user_id)
        return self.msg_queue_dict[user_id]

    def delete_msg_queue_by_user_id(self, user_id):
        self.cancelled_ids.add(user_id)
        if user_id in self.msg_queue_dict:
            del self.msg_queue_dict[user_id]
        if user_id in self.loop_dict:
            del self.loop_dict[user_id]

    def is_cancelled(self, user_id):
        return user_id in self.cancelled_ids

    def put_nowait_threadsafe(self, user_id, message):
        if self.is_cancelled(user_id):
            return
        msg_queue = self.msg_queue_dict.get(user_id)
        loop = self.loop_dict.get(user_id)
        if not msg_queue or not loop:
            return
        if threading.current_thread() is threading.main_thread():
            msg_queue.put_nowait(message)
            return
        loop.call_soon_threadsafe(msg_queue.put_nowait, message)


msg_queue_manager = MsgQueueManager()


# 将思考文本放入前端思考页面中
async def put_think_text_to_msg(user_id, text):
    msg_queue_manager.put_nowait_threadsafe(user_id, {"type": "think", "msg": f"{text}  \n"})
    await asyncio.sleep(0.1)

# 将流式文本放入前端流式页面中
async def put_stream_text_to_msg(user_id, text):
    msg_queue_manager.put_nowait_threadsafe(user_id, {"type": "stream", "msg": f"{text}"})
    await asyncio.sleep(0.1)


# 将思考流式文本放入前端思考页面中（cypher语句在思考过程中流式体现）
async def put_think_text_stream_to_msg(user_id, text):
    msg_queue_manager.put_nowait_threadsafe(user_id, {"type": "think", "msg": f"{text}"})
    await asyncio.sleep(0.1)


# 添加换行符换行符放入到前端思考页面中
async def put_think_huiche_text_to_msg(user_id):
    msg_queue_manager.put_nowait_threadsafe(user_id, {"type": "think", "msg": f"  \n"})
    await asyncio.sleep(0.1)


# 添加done
async def put_done_to_msg(user_id):
    msg_queue_manager.put_nowait_threadsafe(user_id, {"type": "done"})
