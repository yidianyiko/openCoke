# -*- coding: utf-8 -*-
import json
import sys

import requests

sys.path.append(".")

from util.log_util import get_logger

logger = get_logger(__name__)

from conf.config import CONF

auth = CONF["ecloud"]["Authorization"]
host = "http://125.122.152.142:9899"


class Ecloud_API:
    @staticmethod
    def getContact(wcId, target_user_alias):
        wid = CONF["ecloud"]["wId"][target_user_alias]
        data = {"wId": wid, "wcId": wcId}
        logger.info(data)
        resp = requests.post(
            url=host + "/getContact",
            json=data,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )

        resp_json = json.loads(resp.content.decode("utf-8"))
        return resp_json

    @staticmethod
    def sendText(data):
        resp = requests.post(
            url=host + "/sendText",
            json=data,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )

        resp_json = json.loads(resp.content.decode("utf-8"))
        return resp_json

    @staticmethod
    def sendVoice(data):
        resp = requests.post(
            url=host + "/sendVoice",
            json=data,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )

        resp_json = json.loads(resp.content.decode("utf-8"))
        return resp_json

    @staticmethod
    def sendImage(data):
        resp = requests.post(
            url=host + "/sendImage2",
            json=data,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )

        resp_json = json.loads(resp.content.decode("utf-8"))
        return resp_json

    @staticmethod
    def getMsgVoice(data):
        resp = requests.post(
            url=host + "/getMsgVoice",
            json=data,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )

        resp_json = json.loads(resp.content.decode("utf-8"))
        return resp_json

    @staticmethod
    def getMsgImg(data):
        resp = requests.post(
            url=host + "/getMsgImg",
            json=data,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )

        resp_json = json.loads(resp.content.decode("utf-8"))
        return resp_json

    @staticmethod
    def snsSendImage(data):
        resp = requests.post(
            url=host + "/snsSendImage",
            json=data,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )

        resp_json = json.loads(resp.content.decode("utf-8"))
        return resp_json


if __name__ == "__main__":
    target_user_alias = CONF.get("default_character_alias", "coke")
    data = {
        "wId": CONF["ecloud"]["wId"][target_user_alias],
        "wcId": "example_user",
        # "content": "/home/ecs-user/coke/framework/tool/text2voice/test.silk",
        "content": "https://example.com/test.silk?signature=REDACTED",
        "length": 24,
    }
    resp_json = Ecloud_API.sendVoice(data)
    print(resp_json)
