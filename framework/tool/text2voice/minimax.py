import sys

import requests

sys.path.append(".")
import os

from conf.config import CONF
from connector.ecloud.ecloud_api import Ecloud_API
from util.file_util import pcm_to_silk
from util.oss import bucket, upload_file

group_id = os.environ.get("MINIMAX_GROUP_ID")
api_key = os.environ.get("MINIMAX_API_KEY")


def minimax_t2a(
    text,
    timber_weights,
    speed=1,
    pitch=0,
    vol=1,
    emotion=None,
    sample_rate=24000,
    bitrate=128000,
    format="pcm",
):
    url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={group_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content - Type": "application/json",
    }
    payload = {
        "model": "speech - 02 - hd",
        "text": text,
        "timber_weights": timber_weights,
        "voice_setting": {
            "voice_id": "",
            "speed": speed,
            "pitch": pitch,
            "vol": vol,
            "emotion": emotion,
            "latex_read": False,
        },
        "audio_setting": {
            "sample_rate": sample_rate,
            "bitrate": bitrate,
            "format": format,
        },
        "language_boost": "auto",
    }

    response = requests.post(url, headers=headers, json=payload)

    return response.json()


# 启动脚本
if __name__ == "__main__":
    text = "哈哈😆 其实不是煮一起分不开哈.在土耳其文化里，咖啡渣可有大作用呢🤭 等喝完咖啡，把杯子倒扣，等渣子沉淀，据说能从渣子的形状‘读’出未来运势哟，就跟咱们看手相差不多😜 所以得连渣一起喝，这样才能感受这独特的文化魅力呀~你觉得这种‘读运’的方式神奇不"

    timber_weights = [
        {"voice_id": "Chinese (Mandarin)_Warm_Bestie", "weight": 50},
        {"voice_id": "Chinese (Mandarin)_Warm_Girl", "weight": 30},
        {"voice_id": "Chinese (Mandarin)_Laid_BackGirl", "weight": 40},
    ]

    resp_json = minimax_t2a(text, timber_weights, pitch=-1)
    hex = resp_json["data"]["audio"]
    decoded_hex = bytes.fromhex(hex)

    file_path = "framework/tool/text2voice/test.pcm"
    with open(file_path, "wb") as f:
        f.write(decoded_hex)

    new_file_path = pcm_to_silk(file_path)

    with open(new_file_path, "rb") as f:
        data = f.read()
    upload_file(bucket, "test.silk", data)

    url = bucket.sign_url("GET", "test.silk", 5 * 60)
    print(url)

    resp_json = Ecloud_API.sendVoice(
        data={
            "wId": CONF["ecloud"]["wId"][target_user_alias],
            "wcId": "LeanInWind",
            "content": url,
            "length": 24 * 1000,
        }
    )

    print(resp_json)
