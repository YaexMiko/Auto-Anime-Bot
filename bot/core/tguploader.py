from time import time, sleep
from traceback import format_exc
from math import floor
from os import path as ospath, stat
from aiofiles.os import remove as aioremove
from pyrogram.errors import FloodWait

from bot import bot, Var
from .func_utils import editMessage, sendMessage, convertBytes, convertTime
from .reporter import rep

class TgUploader:
    def __init__(self, message):
        self.cancelled = False
        self.message = message
        self.__name = ""
        self.__qual = ""
        self.__client = bot
        self.__start = time()
        self.__updater = time()

    async def validate_file(self, path):
        try:
            file_size = stat(path).st_size
            if file_size == 0:
                await rep.report(f"Empty file detected: {path}", "error")
                return False
            return True
        except OSError as e:
            await rep.report(f"File validation failed: {e}", "error")
            return False

    async def upload(self, path, qual):
        self.__name = ospath.basename(path)
        self.__qual = qual
        
        if not await self.validate_file(path):
            await aioremove(path)
            return None

        try:
            if Var.AS_DOC:
                return await self.__client.send_document(
                    chat_id=Var.FILE_STORE,
                    document=path,
                    thumb="thumb.jpg" if ospath.exists("thumb.jpg") else None,
                    caption=f"<i>{self.__name}</i>",
                    force_document=True,
                    progress=self.progress_status
                )
            else:
                return await self.__client.send_video(
                    chat_id=Var.FILE_STORE,
                    video=path,
                    thumb="thumb.jpg" if ospath.exists("thumb.jpg") else None,
                    caption=f"<i>{self.__name}</i>",
                    progress=self.progress_status
                )
        except FloodWait as e:
            sleep(e.value * 1.5)
            return await self.upload(path, qual)
        except Exception as e:
            await rep.report(format_exc(), "error")
            raise e
        finally:
            await aioremove(path)

    async def progress_status(self, current, total):
        if self.cancelled:
            self.__client.stop_transmission()
        now = time()
        diff = now - self.__start
        if (now - self.__updater) >= 7 or current == total:
            self.__updater = now
            percent = round(current / total * 100, 2)
            speed = current / diff 
            eta = round((total - current) / speed)
            bar = floor(percent/8)*"█" + (12 - floor(percent/8))*"▒"
            progress_str = f"""<blockquote>‣ <b>Anime Name :</b> <b>{self.__name}</b></blockquote>

<blockquote>‣ <b>𝚂𝚝𝚊𝚝𝚞𝚜 : </b> <b>𝚄𝚙𝚕𝚘𝚍𝚒𝚗𝚐 𝚈𝚘𝚞𝚛 𝙴𝚙𝚒𝚜𝚘𝚍𝚎</b> </blockquote>
    <code>[{bar}]</code> {percent}%
    
    <blockquote>‣ <b>𝚂𝚒𝚣𝚎 : </b> {convertBytes(current)} 𝙾𝚞𝚝 𝙾𝚏 ~ {convertBytes(total)}
    ‣ <b>𝚂𝚙𝚎𝚎𝚍 : </b> {convertBytes(speed)}/s
    ‣ <b>𝚃𝚒𝚖𝚎 𝚃𝚘𝚘𝚔 : </b> {convertTime(diff)}
    ‣ <b>𝚃𝚒𝚖𝚎 𝙻𝚎𝚏𝚝 : </b> {convertTime(eta)} </blockquote>

<blockquote>‣ <b>𝙵𝚒𝚕𝚎(𝚜) 𝙴𝚗𝚌𝚘𝚍𝚎𝚍 : </b> <code>{Var.QUALS.index(self.__qual)} / {len(Var.QUALS)}</code></blockquote>"""
            
            await editMessage(self.message, progress_str)
