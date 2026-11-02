import json, struct, zlib

TEMPLATES = [
    {'id':'status','icon':'📟','label':'Gerätestatus','hint':'Alle wichtigen Zustände','text':'Gib mir den aktuellen Status und die wichtigsten Readings von Gerät {device}. Nur abfragen, nichts verändern.'},
    {'id':'temperature','icon':'🌡️','label':'Temperatur','hint':'Aktueller Messwert','text':'Wie hoch ist die aktuell gemessene Temperatur von Gerät {device}? Nenne Einheit und Messzeit, falls vorhanden. Nicht den Sollwert mit dem Istwert verwechseln. Nur lesen.'},
    {'id':'switch','icon':'💡','label':'Schalterzustand','hint':'An, aus oder unbekannt','text':'Gib den aktuellen Schalterzustand von Gerät {device} aus. Ist es an oder aus? Fehlende oder unklare Daten nicht erraten. Nichts schalten.'},
    {'id':'humidity','icon':'💧','label':'Luftfeuchtigkeit','hint':'Relative Feuchte abfragen','text':'Gib die gemessene relative Luftfeuchtigkeit von Gerät {device} mit Einheit und Messzeit aus, soweit vorhanden. Nur lesen.'},
    {'id':'battery','icon':'🔋','label':'Batterie','hint':'Ladezustand und Warnungen','text':'Prüfe den Batteriestatus von Gerät {device}. Unterscheide Prozentwert, Spannung und Batteriewarnung. Nur vorhandene Werte nennen, nichts verändern.'},
    {'id':'reachable','icon':'📡','label':'Erreichbarkeit','hint':'Verbindung und Aktualität','text':'Prüfe die Erreichbarkeit von Gerät {device} anhand vorhandener Readings und deren Zeitstempel. Falls keine belastbaren Daten existieren, sage das. Nur lesen.'},
    {'id':'reading','icon':'📋','label':'Alle Readings','hint':'Details zum Gerät','text':'Liste die vorhandenen Readings von Gerät {device} übersichtlich mit Werten, Einheiten und Zeitstempeln auf. Nur lesen.'},
    {'id':'devices','icon':'🏠','label':'Geräte finden','hint':'Namen und Räume entdecken','text':'Zeige mir die verfügbaren FHEM-Geräte mit ihren exakten Namen und Räumen. Nutze möglichst eine kompakte Liste. Nur lesen.'}
]

def make_prompt(ident, device=''):
    template=next((t for t in TEMPLATES if t['id']==ident),None)
    if template is None:
        raise ValueError('Unbekannte Vorlage')
    if ident=='devices':
        return template['text']
    device=device.strip()
    if not device or len(device)>200 or any(ord(c)<32 for c in device):
        raise ValueError('Bitte einen Gerätenamen mit maximal 200 Zeichen eingeben.')
    return template['text'].format(device=json.dumps(device,ensure_ascii=False))

def keyboard():
    buttons=[{'text':t['icon']+' '+t['label'],'callback_data':'menu:'+t['id']} for t in TEMPLATES]
    return {'inline_keyboard':[buttons[i:i+2] for i in range(0,len(buttons),2)]}

def banner_png():
    width,height=640,240
    rows=[]
    for y in range(height):
        row=bytearray()
        for x in range(width):
            t=x/(width-1)
            color=(int(35+85*t),int(125-45*t),int(190+45*t))
            roof=abs(y-(60+abs(x-320)*0.65))<6 and 220<x<420
            walls=(220<x<230 or 410<x<420) and 125<y<205
            floor=220<x<420 and 199<y<209
            door=297<x<343 and 151<y<205
            if roof or walls or floor: color=(235,250,255)
            if door: color=(255,205,105)
            if (x-110)**2+(y-70)**2<500 or (x-530)**2+(y-170)**2<850: color=(87,220,197)
            row.extend(color)
        rows.append(b'\x00'+bytes(row))
    def chunk(kind,data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
