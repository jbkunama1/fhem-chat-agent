import asyncio, contextlib, json, time
from contextlib import asynccontextmanager
import httpx
from fastapi import Depends
from fastapi.responses import Response
import app as core
from menu import TEMPLATES, make_prompt, keyboard, banner_png

app=core.app
BANNER=banner_png()
waiting={}

@app.get('/api/menu')
async def menu(owner=Depends(core.auth)):
    return {'templates':TEMPLATES}

@app.get('/api/banner.png')
async def banner(owner=Depends(core.auth)):
    return Response(BANNER,media_type='image/png')

async def show_menu(uid,with_banner=False):
    caption='🏡 FHEM · Dein Smart-Home-Assistent\n\nWähle eine Abfrage. Danach gibst du den exakten Gerätenamen ein.\n🔒 Schaltaktionen brauchen weiterhin eine eigene Freigabe.\n/menu öffnet dieses Menü · /cancel verwirft die Vorlageneingabe.'
    if with_banner:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response=await client.post('https://api.telegram.org/bot'+core.BOT+'/sendPhoto',data={'chat_id':str(uid),'caption':caption,'reply_markup':json.dumps(keyboard(),ensure_ascii=False)},files={'photo':('fhem-home.png',BANNER,'image/png')})
                response.raise_for_status()
                if response.json().get('ok'):
                    return
        except Exception:
            pass
    await core.tg('sendMessage',{'chat_id':uid,'text':caption,'reply_markup':keyboard()})

async def send_state(uid,state,start):
    for message in state['messages'][start:]:
        if message['role']=='assistant' and message.get('content'):
            text=message['content']
            for i in range(0,len(text),3500):
                await core.tg('sendMessage',{'chat_id':uid,'text':text[i:i+3500]})
    p=state['pending']
    if p:
        text='🔐 Auftrag prüfen\nGültig bis '+time.strftime('%H:%M:%S',time.localtime(p['expires']))+' (Serverzeit)\n'+json.dumps(p['action'],ensure_ascii=False,indent=2)
        for i in range(0,len(text),3500):
            await core.tg('sendMessage',{'chat_id':uid,'text':text[i:i+3500]})
        await core.tg('sendMessage',{'chat_id':uid,'text':'Genau diesen Auftrag freigeben?', 'reply_markup':{'inline_keyboard':[[{'text':'✅ Ausführen','callback_data':'y:'+p['id']},{'text':'❌ Abbrechen','callback_data':'n:'+p['id']}]]}})
    else:
        await core.tg('sendMessage',{'chat_id':uid,'text':'✨ Nächste Abfrage auswählen oder frei schreiben:','reply_markup':keyboard()})

async def handle(update):
    cb=update.get('callback_query')
    msg=cb.get('message',{}) if cb else update.get('message',{})
    uid=(cb or msg).get('from',{}).get('id')
    if uid not in core.ALLOWED or msg.get('chat',{}).get('type')!='private' or msg['chat']['id']!=uid:
        return
    owner='tg:'+str(uid)
    start=len(core.store.load(owner))
    if cb:
        await core.tg('answerCallbackQuery',{'callback_query_id':cb['id']})
        data=cb.get('data','')
        if data.startswith(('y:','n:')):
            waiting.pop(uid,None)
            state=await core.decide(owner,data[2:],data[:2]=='y:')
            with contextlib.suppress(Exception):
                await core.tg('editMessageReplyMarkup',{'chat_id':uid,'message_id':msg['message_id'],'reply_markup':{'inline_keyboard':[]}})
            await send_state(uid,state,start)
            return
        if not data.startswith('menu:'):
            return
        if core.store.pending(owner):
            await core.tg('sendMessage',{'chat_id':uid,'text':'🔐 Zuerst den offenen Auftrag ausführen oder abbrechen.'})
            return
        ident=data[5:]
        template=next((t for t in TEMPLATES if t['id']==ident),None)
        if template is None:
            return
        if ident=='devices':
            waiting.pop(uid,None)
            state=await core.chat(owner,make_prompt(ident))
            await send_state(uid,state,start)
        else:
            waiting[uid]=(ident,time.time()+600)
            await core.tg('sendMessage',{'chat_id':uid,'text':template['icon']+' '+template['label']+'\n\nWie heißt das Gerät in FHEM? Sende jetzt nur den Gerätenamen.\n/cancel bricht diese Eingabe ab.'})
        return
    text=msg.get('text','').strip()
    if not text:
        return
    if text in ('/start','/menu','/help'):
        waiting.pop(uid,None)
        await show_menu(uid,with_banner=text=='/start')
        return
    if text=='/cancel':
        waiting.pop(uid,None)
        await core.tg('sendMessage',{'chat_id':uid,'text':'Vorlageneingabe verworfen. Offene Ausführungsfreigaben bleiben separat bestehen.'})
        await show_menu(uid)
        return
    if len(text)>8000:
        await core.tg('sendMessage',{'chat_id':uid,'text':'Nachricht zu lang (maximal 8000 Zeichen).'})
        return
    selection=waiting.get(uid)
    if selection:
        if selection[1]<time.time():
            waiting.pop(uid,None)
            await core.tg('sendMessage',{'chat_id':uid,'text':'Vorlageneingabe abgelaufen. Bitte /menu neu öffnen.'})
            return
        try:
            text=make_prompt(selection[0],text)
        except ValueError as exc:
            await core.tg('sendMessage',{'chat_id':uid,'text':str(exc)})
            return
        waiting.pop(uid,None)
        await core.tg('sendMessage',{'chat_id':uid,'text':'📝 Deine Abfrage:\n'+text})
    await send_state(uid,await core.chat(owner,text),start)

async def telegram():
    offset=0
    with contextlib.suppress(Exception):
        await core.tg('setMyCommands',{'commands':[{'command':'menu','description':'🏠 Abfragemenü öffnen'},{'command':'start','description':'✨ Start mit Grafik'},{'command':'cancel','description':'Vorlageneingabe abbrechen'}]})
    while True:
        try:
            updates=await core.tg('getUpdates',{'offset':offset,'timeout':25,'allowed_updates':['message','callback_query']})
            for update in updates:
                offset=update['update_id']+1
                try:
                    await handle(update)
                except Exception:
                    cb=update.get('callback_query')
                    uid=(cb or update.get('message',{})).get('from',{}).get('id')
                    if uid in core.ALLOWED:
                        with contextlib.suppress(Exception):
                            await core.tg('sendMessage',{'chat_id':uid,'text':'⚠️ Anfrage fehlgeschlagen oder Freigabe ungültig. Nicht automatisch wiederholt. /menu öffnet die Vorlagen.'})
        except Exception:
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app):
    task=asyncio.create_task(telegram()) if core.BOT and core.ALLOWED else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

app.router.lifespan_context=lifespan
