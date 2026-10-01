# -*- coding: utf-8 -*-
"""產生旁白語音（edge-tts 台灣口音）、時間軸，並組出可播放的 HTML 動畫簡報。

用法：python3 src/build.py
輸出：presentation/narration.mp3、presentation/index.html
"""
import asyncio
import hashlib
import json
import os
import ssl
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from content import SCENES, TITLE  # noqa: E402

import edge_tts.communicate as ec  # noqa: E402

# 經由代理連線時需信任代理憑證；本機執行則使用預設
_CA = "/root/.ccr/ca-bundle.crt"
if os.path.exists(_CA):
    ec._SSL_CTX = ssl.create_default_context(cafile=_CA)

VOICES = {
    "A": dict(voice="zh-TW-YunJheNeural", rate="+6%", pitch="+0Hz"),     # Allan Lo：台灣男聲
    "R": dict(voice="zh-TW-HsiaoYuNeural", rate="+12%", pitch="+30Hz"),  # 阿拉蕾：高亢童聲
}
SR = 24000
CACHE = os.path.join(ROOT, "presentation", "audio_cache")
OUT = os.path.join(ROOT, "presentation")

SCENE_LEAD = 0.7     # 換場後到第一句的空白
LINE_GAP = 0.38      # 句與句之間
SCENE_TAIL = 1.0     # 每場最後一句後的停留
SCENE_MIN = 4.0      # 每場最短秒數


def tts_text(text):
    return text.replace("～", "，").replace("＋", "加")


def cache_path(who, text):
    v = VOICES[who]
    h = hashlib.sha1(json.dumps([v, text], ensure_ascii=False).encode()).hexdigest()[:16]
    return os.path.join(CACHE, f"{who}_{h}")


async def synth(who, text, sem):
    base = cache_path(who, text)
    wav = base + ".wav"
    if os.path.exists(wav):
        return
    async with sem:
        v = VOICES[who]
        for attempt in range(5):
            try:
                com = ec.Communicate(tts_text(text), v["voice"], rate=v["rate"], pitch=v["pitch"],
                                     proxy=os.environ.get("HTTPS_PROXY"))
                await com.save(base + ".mp3")
                break
            except Exception as e:  # 網路不穩時重試
                print("retry", attempt, e)
                await asyncio.sleep(2 ** attempt)
        else:
            raise RuntimeError("TTS failed: " + text)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", base + ".mp3",
                    "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", wav], check=True)


async def synth_all():
    os.makedirs(CACHE, exist_ok=True)
    sem = asyncio.Semaphore(4)
    jobs = [synth(who, text, sem) for s in SCENES for (who, text, _r) in s["lines"]]
    await asyncio.gather(*jobs)


def read_pcm(path):
    with wave.open(path) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        return w.readframes(w.getnframes())


def build():
    asyncio.run(synth_all())
    pcm = bytearray()
    t = 0.0

    def silence(sec):
        nonlocal t
        n = int(round(sec * SR))
        pcm.extend(b"\x00\x00" * n)
        t += n / SR

    deck = []
    for s in SCENES:
        scene = {k: v for k, v in s.items() if k != "lines"}
        scene["start"] = round(t, 3)
        silence(SCENE_LEAD)
        lines = []
        for i, (who, text, reveal) in enumerate(s["lines"]):
            if i:
                silence(LINE_GAP)
            data = read_pcm(cache_path(who, text) + ".wav")
            start = t
            pcm.extend(data)
            t += len(data) / 2 / SR
            lines.append(dict(who=who, text=text, reveal=reveal, start=round(start, 3), end=round(t, 3)))
        silence(SCENE_TAIL)
        if t - scene["start"] < SCENE_MIN:
            silence(SCENE_MIN - (t - scene["start"]))
        scene["end"] = round(t, 3)
        scene["lines"] = lines
        deck.append(scene)

    wav_out = os.path.join(CACHE, "narration.wav")
    with wave.open(wav_out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(pcm))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav_out, "-codec:a", "libmp3lame",
                    "-b:a", "64k", os.path.join(OUT, "narration.mp3")], check=True)

    data = dict(title=TITLE, duration=round(t, 3), scenes=deck)
    js = "window.DECK = " + json.dumps(data, ensure_ascii=False) + ";"
    with open(os.path.join(ROOT, "src", "player.html"), encoding="utf-8") as f:
        player = f.read().replace("/*__DECK__*/", js)
    # Artifact 版（無 doctype 外框）
    with open(os.path.join(OUT, "artifact.html"), "w", encoding="utf-8") as f:
        f.write(player)
    # 本機可直接開啟的完整 HTML
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                '</head>\n<body>\n' + player + '\n</body>\n</html>\n')
    # 根目錄入口（GitHub Pages 等可直接開啟），音檔指向 presentation/
    with open(os.path.join(OUT, "index.html"), encoding="utf-8") as f:
        root_html = f.read().replace('src="narration.mp3"', 'src="presentation/narration.mp3"')
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(root_html)
    print(f"scenes={len(deck)} lines={sum(len(s['lines']) for s in deck)} duration={t/60:.1f} min")


if __name__ == "__main__":
    build()
