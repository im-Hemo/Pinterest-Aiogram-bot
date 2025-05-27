import asyncio
import re
import logging
import shutil  
from pathlib import Path
from typing import List
from concurrent.futures import ThreadPoolExecutor
from aiogram import Bot as xgv, Dispatcher, Router as Hemo
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    FSInputFile 
)
from aiogram.filters import Command
import requests
import yt_dlp
from fake_useragent import UserAgent

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)  

token = 'توكن بوتك'

class PinterestDownloader:
    def __init__(self, bot: xgv):
        self.x = bot
        self.ua = UserAgent()
        self.pin_dir = Path('Pin')
        self.pin_dir.mkdir(exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.Hemo = Hemo()
        self.Hemo.message.register(self.Start_CMD, Command(commands=["start"]))
        self.Hemo.message.register(self.message_mng)

    async def Start_CMD(self, message: Message):
        x1 = InlineKeyboardButton(text='‹ Me ›', url='https://t.me/x_g_v')
        x2 = InlineKeyboardButton(text='‹ Ch ›', url='https://t.me/lmmm5')
        markup = InlineKeyboardMarkup(inline_keyboard=[[x1, x2]])
        
        um = message.from_user.username
        fm = message.from_user.first_name
        mention = (
            f'<a href="https://t.me/{um}">{fm}</a>'
            if um else f'<b>{fm}</b>'
        )
        
        try:
            await self.x.send_photo(
                chat_id=message.chat.id,
                photo='https://i.ibb.co/0yzZHrjc/image.jpg',
                caption=(
                    f'• مرحباً بك، {mention}! 👋\n'
                    '• أنا بوت تحميل من <b>Pinterest</b> 🎨\n\n'
                    '<blockquote> دز رابط صورة او فيديو بنترست وراح احمله لك 😁</blockquote>'
                ),
                has_spoiler=True,
                parse_mode='HTML',
                reply_markup=markup
            )
        except Exception:
            pass

    def _resolve_url(self, url: str) -> str:
        resp = requests.get(url, headers={'User-Agent': self.ua.random}, allow_redirects=True, timeout=10)
        resp.raise_for_status()
        return resp.url

    def _extract_pin_id(self, url: str) -> str:
        patterns = [r'pinterest\.com/pin/(\d+)', r'pin\.it/(\w+)']
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def _fetch_pin_metadata(self, pin_id: str) -> dict:
        api_url = 'https://www.pinterest.com/resource/PinResource/get/'
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': self.ua.random,
            'X-Pinterest-PWS-Handler': f'www/pin/{pin_id}/feedback.js'
        }
        params = {
            'source_url': f'/pin/{pin_id}',
            'data': f'{{"options":{{"id":"{pin_id}","field_set_key":"auth_web_main_pin"}}}}'
        }
        resp = requests.get(api_url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get('resource_response', {}).get('data', {})

    def _extract_media(self, pin_data: dict) -> dict:
        media = {'type': None, 'resources': [], 'signature': pin_data.get('id') or str(hash(str(pin_data)))}
        if pin_data.get('videos'):
            video_list = pin_data['videos'].get('video_list', {})
            for quality in ['V_EXP7', 'V_720P', 'V_480P']:
                if video_list.get(quality):
                    media['type'] = 'video'
                    media['resources'] = [video_list[quality]['url']]
                    return media
        if pin_data.get('carousel_data'):
            slots = pin_data['carousel_data'].get('carousel_slots', [])
            urls = [item.get('images', {}).get('orig', {}).get('url') for item in slots if item.get('images', {}).get('orig', {}).get('url')]
            if urls:
                media['type'] = 'carousel'
                media['resources'] = urls
                return media
        img = pin_data.get('images', {}).get('orig', {}).get('url')
        if img:
            media['type'] = 'image'
            media['resources'] = [img]
            return media
        raise ValueError('Unsupported pin content')

    def _download_resource(self, url: str, file_path: Path):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if url.endswith('.m3u8'):
            opts = {'outtmpl': str(file_path)}
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        else:
            r = requests.get(url, stream=True, timeout=10)
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)

    async def process_pin(self, url: str, chat_id: int):
        loop = asyncio.get_running_loop()
        try:
            resolved = await loop.run_in_executor(self.executor, self._resolve_url, url)
            pin_id = await loop.run_in_executor(self.executor, self._extract_pin_id, resolved)
            if not pin_id:
                await self.x.send_message(chat_id, '• رابط غلط !')
                return

            msg = await self.x.send_message(chat_id, '⏳ جاري البحث...')
            pin_data = await loop.run_in_executor(self.executor, self._fetch_pin_metadata, pin_id)
            media_info = await loop.run_in_executor(self.executor, self._extract_media, pin_data)
            
            await msg.edit_text('📥 جاري التحميل...')
            
            download_dir = self.pin_dir / media_info['signature']
            download_dir.mkdir(exist_ok=True)
            files = await self._download_media(media_info, download_dir, loop)
            
            await self._send_media(chat_id, files, media_info['type'])
            await msg.delete()
            self._cleanup(download_dir) 
            
        except Exception as e:
            logger.error(f"Process error: {e}") 
            await self.x.send_message(chat_id, f'• خطأ: {e}')

    async def _download_media(self, media_info: dict, dir_path: Path, loop) -> List[Path]:
        files = []
        for idx, res in enumerate(media_info['resources']):
            ext = 'mp4' if media_info['type'] == 'video' else 'jpg'
            name = f"{idx}.{ext}" if media_info['type'] == 'carousel' else f"content.{ext}"
            path = dir_path / name
            await loop.run_in_executor(self.executor, self._download_resource, res, path)
            files.append(path)
        return files

    async def _send_media(self, chat_id: int, files: List[Path], media_type: str):
        X = await self.x.get_me()
        caption = f'• تم التحميل ☑️ | بواسطـة @{X.username}'
        
        for fpath in files:
            try:
                file = FSInputFile(str(fpath))  #  FSInputFile
                if media_type == 'video':
                    await self.x.send_video(chat_id, video=file, caption=caption)
                else:
                    await self.x.send_photo(chat_id, photo=file, caption=caption)
            except Exception as e:
                logger.error(f"Failed to send media: {e}")

    def _cleanup(self, download_dir: Path):  # del dir
  
        try:
            shutil.rmtree(download_dir) 
        except Exception:
            pass

    async def message_mng(self, message: Message):
        url = message.text.strip()
        if re.search(r'pinterest\.com|pin\.it', url):
            asyncio.create_task(self.process_pin(url, message.chat.id))
                        
                        
         
async def yemen():
    Ok = xgv(token=token)
    PD = PinterestDownloader(Ok)
    run = Dispatcher()
    run.include_router(PD.Hemo)
    try:
        await run.start_polling(Ok)
    finally:
        await Ok.session.close()

if __name__ == '__main__':
    asyncio.run(yemen())    
    
    
    
    
    
    