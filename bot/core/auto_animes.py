from asyncio import gather, create_task, sleep as asleep, Event
from asyncio.subprocess import PIPE
from os import path as ospath, stat
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove
from traceback import format_exc
from base64 import urlsafe_b64encode
from time import time
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import bot, bot_loop, Var, ani_cache, ffQueue, ffLock, ff_queued
from .tordownload import TorDownloader
from .database import db
from .func_utils import getfeed, encode, editMessage, sendMessage, convertBytes
from .text_utils import TextEditor
from .ffencoder import FFEncoder
from .tguploader import TgUploader
from .reporter import rep

btn_formatter = {
    '1080':'1080𝚙',
    '720':'720𝚙',
    '480':'480𝚙',
    '360':'360𝚙',
    }

async def validate_media_file(path):
    try:
        return ospath.exists(path) and stat(path).st_size > 0
    except OSError:
        return False

async def fetch_animes():
    await rep.report("Fetch Animes Started !!", "info")
    while True:
        await asleep(60)
        if ani_cache['fetch_animes']:
            for link in Var.RSS_ITEMS:
                if (info := await getfeed(link, 0)):
                    bot_loop.create_task(get_animes(info.title, info.link))

async def get_animes(name, torrent, force=False):
    try:
        aniInfo = TextEditor(name)
        await aniInfo.load_anilist()
        ani_id, ep_no = aniInfo.adata.get('id'), aniInfo.pdata.get("episode_number")
        
        if ani_id not in ani_cache['ongoing']:
            ani_cache['ongoing'].add(ani_id)
        elif not force:
            return
            
        if not force and ani_id in ani_cache['completed']:
            return
            
        if force or (not (ani_data := await db.getAnime(ani_id))) \
            or (ani_data and not (qual_data := ani_data.get(ep_no))) \
            or (ani_data and qual_data and not all(qual for qual in qual_data.values())):
            
            if "[Batch]" in name:
                await rep.report(f"𝚃𝚘𝚛𝚛𝚎𝚗𝚝 𝚂𝚔𝚒𝚙𝚙𝚎𝚍!\n\n{name}", "warning")
                return
            
            await rep.report(f"𝙽𝚎𝚠 𝙰𝚗𝚒𝚖𝚎 𝚃𝚘𝚛𝚛𝚎𝚗𝚝 𝙵𝚘𝚞𝚗𝚍!\n\n{name}", "info")
            
            try:
                post_msg = await bot.send_photo(
                    Var.MAIN_CHANNEL,
                    photo=await aniInfo.get_poster(),
                    caption=await aniInfo.get_caption()
                )
            except Exception as e:
                await rep.report(f"Failed to create post: {e}", "error")
                return
                
            await asleep(1.5)
            stat_msg = await sendMessage(Var.MAIN_CHANNEL, 
                f"<blockquote>‣ <b>𝙰𝚗𝚒𝚖𝚎 𝙽𝚊𝚖𝚎 :</b> <b>{name}</b></blockquote>\n\n"
                "<blockquote><b>𝙳𝚘𝚠𝚗𝚕𝚘𝚊𝚍𝚒𝚗𝚐 �𝚘𝚞𝚛 𝙴𝚙𝚒𝚜𝚘𝚍𝚎...</b></blockquote>"
            )
            
            try:
                dl = await TorDownloader("./downloads").download(torrent, name)
                if not await validate_media_file(dl):
                    await rep.report("Downloaded file is invalid", "error")
                    await stat_msg.delete()
                    return
            except Exception as e:
                await rep.report(f"Download failed: {e}", "error")
                await stat_msg.delete()
                return

            post_id = post_msg.id
            ffEvent = Event()
            ff_queued[post_id] = ffEvent
            
            if ffLock.locked():
                await editMessage(stat_msg, 
                    f"<blockquote>‣ <b>𝙰𝚗𝚒𝚖𝚎 𝙽𝚊𝚖𝚎 :</b> <b>{name}</b></blockquote>\n\n"
                    "<blockquote><b>𝚀𝚞𝚎𝚞𝚎𝚍 𝚃𝚘 𝙴𝚗𝚌𝚘𝚍𝚎 𝚈𝚘𝚞𝚛 𝙴𝚙𝚒𝚜𝚘𝚍𝚎...</b></blockquote>"
                )
                await rep.report("Added task to queue...", "info")
                
            await ffQueue.put(post_id)
            await ffEvent.wait()
            
            await ffLock.acquire()
            btns = []
            
            for qual in Var.QUALS:
                filename = await aniInfo.get_upname(qual)
                await editMessage(stat_msg, 
                    f"<blockquote>‣ <b>𝙰𝚗𝚒𝚖𝚎 𝙽𝚊𝚖𝚎 :</b> <b>{name}</b></blockquote>\n\n"
                    "<blockquote><b>𝚁𝚎𝚊𝚍𝚢 𝚃𝚘 𝙴𝚗𝚌𝚘𝚍𝚎 𝚈𝚘𝚞𝚛 𝙴𝚙𝚒𝚜𝚘𝚍𝚎...</b></blockquote>"
                )
                
                await asleep(1.5)
                await rep.report("Starting encode...", "info")
                
                try:
                    out_path = await FFEncoder(stat_msg, dl, filename, qual).start_encode()
                    if not out_path:
                        await rep.report("Encoding failed, skipping quality", "error")
                        continue
                except Exception as e:
                    await rep.report(f"Encode error: {e}, skipping quality", "error")
                    continue
                    
                await rep.report("Successfully compressed, now uploading...", "info")
                
                await editMessage(stat_msg, 
                    f"<blockquote>‣ <b>𝙰𝚗𝚒𝚖𝚎 𝙽𝚊𝚖𝚎 :</b> <b>{filename}</b></blockquote>\n\n"
                    "<blockquote><b>𝚁𝚎𝚊𝚍𝚢 𝚃𝚘 𝚄𝚙𝚕𝚘𝚊𝚍 𝚈𝚘𝚞𝚛 𝙴𝚙𝚒𝚜𝚘𝚍𝚎...</b></blockquote>"
                )
                
                await asleep(1.5)
                try:
                    msg = await TgUploader(stat_msg).upload(out_path, qual)
                    if not msg:
                        await rep.report("Upload failed, skipping quality", "error")
                        continue
                except Exception as e:
                    await rep.report(f"Upload error: {e}, skipping quality", "error")
                    continue
                    
                msg_id = msg.id
                link = f"https://telegram.me/{(await bot.get_me()).username}?start={await encode('get-'+str(msg_id * abs(Var.FILE_STORE)))}"
                
                if post_msg:
                    if len(btns) != 0 and len(btns[-1]) == 1:
                        btns[-1].insert(1, InlineKeyboardButton(
                            f"{btn_formatter[qual]} - {convertBytes(msg.document.file_size)}", 
                            url=link
                        ))
                    else:
                        btns.append([InlineKeyboardButton(
                            f"{btn_formatter[qual]} - {convertBytes(msg.document.file_size)}", 
                            url=link
                        )])
                    await editMessage(
                        post_msg, 
                        post_msg.caption.html if post_msg.caption else "", 
                        InlineKeyboardMarkup(btns)
                    )
                    
                await db.saveAnime(ani_id, ep_no, qual, post_id)
                bot_loop.create_task(extra_utils(msg_id, out_path))
                
            ffLock.release()
            await stat_msg.delete()
            await aioremove(dl)
            
        ani_cache['completed'].add(ani_id)
    except Exception as error:
        await rep.report(f"Anime processing failed: {format_exc()}", "error")

async def extra_utils(msg_id, out_path):
    try:
        msg = await bot.get_messages(Var.FILE_STORE, message_ids=msg_id)
        if Var.BACKUP_CHANNEL != 0:
            for chat_id in Var.BACKUP_CHANNEL.split():
                await msg.copy(int(chat_id))
    except Exception as e:
        await rep.report(f"Backup failed: {e}", "error")
