import base64
import hmac
import sys
import time
import uuid
from hashlib import sha1

import requests

sys.path.append(".")

from conf.config import CONF

host = "https://openapi.liblibai.cloud"


def make_sign(uri="/api/generate/webui/text2img"):
    """
    生成签名
    """
    # host = "https://openapi.liblibai.cloud"

    # API访问密钥
    access_key = CONF["liblib"]["AccessKey"]
    secret_key = CONF["liblib"]["SecretKey"]

    # 请求API接口的uri地址
    # uri = "/api/generate/webui/text2img"
    # 当前毫秒时间戳
    timestamp = str(int(time.time() * 1000))
    # 随机字符串
    signature_nonce = str(uuid.uuid4())
    # 拼接请求数据
    content = "&".join((uri, timestamp, signature_nonce))

    # 生成签名
    digest = hmac.new(secret_key.encode(), content.encode(), sha1).digest()
    # 移除为了补全base64位数而填充的尾部等号
    sign = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    uri_params = [
        "AccessKey=" + access_key,
        "Signature=" + sign,
        "Timestamp=" + timestamp,
        "SignatureNonce=" + signature_nonce,
    ]
    uri_param = "&".join(uri_params)

    return uri_param


# https://openapi.liblibai.cloud
# https://test.xxx.com/api/genImg?AccessKey=KIQMFXjHaobx7wqo9XvYKA&Signature=test1232132&Timestamp=1725458584000&SignatureNonce=random1232


def text2img(generateParams, templateUuid="6f7c4652458d4802969f8d089cf5b91"):
    uri = "/api/generate/webui/text2img"
    uri_param = make_sign(uri)

    resp = requests.post(
        url=host + uri + "?" + uri_param,
        headers={"Content-Type": "application/json"},
        json={"templateUuid": templateUuid, "generateParams": generateParams},
    )

    resp_json = resp.json()
    return resp_json


def getstatus(generateUuid):
    uri = "/api/generate/webui/status"
    uri_param = make_sign(uri)

    resp = requests.post(
        url=host + uri + "?" + uri_param,
        headers={"Content-Type": "application/json"},
        json={"generateUuid": generateUuid},
    )

    resp_json = resp.json()
    return resp_json
