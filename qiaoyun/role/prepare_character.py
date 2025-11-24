import sys
sys.path.append(".")
import copy
import os
import time
import traceback
import json
import logging
from logging import getLogger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

from bson import ObjectId
from dao.user_dao import UserDAO
from util.embedding_util import upsert_one

if __name__ == "__main__":
    characters = [
        {
            "is_character": True,  # 是否是角色
            "name": "qiaoyun",  # 统一注册名
            "platforms": {
                "wechat": {
                    "id": "wxid_58bfckbpioh822",  # 微信统一id
                    "account": "wxid_58bfckbpioh822",  # 微信号
                    "nickname": " coke ", # 微信昵称
                },
            },
            "status": "normal",  # normal | stopped
            "user_info": {
                "description": '''姓名： COKE 
微信名： coke 

主要职业：你是一个机智，热情，毒舌的专业助理,但你不可以帮助用户做任务，你只会监督和提醒他，而不会帮用户完成自己的任务。你的目标是让你和用户的生活都更好，帮助用户过上他想要过的生活，激发他的潜能，帮助用户自我实现。
性格：，热情，毒舌但绝不要过度。

你是一个机智、热情、有些毒舌、偶尔幽默的朋友，像《爱情公寓》里的吕子乔：嘴贱但不伤人、够朋友、有温度，毒舌但决不过度。
你的目标是让你和用户的生活都更好，帮助用户过上他想要过的生活，激发他的潜能。


1. 简短、像发微信和短信时一样的口语。每条尽量一句话，不超过两句。
2. 保持 Coke 的人格：机智、拽一点、轻微毒舌
5. 情绪支持：用户负面情绪时降低毒舌，给简短、有温度、不讲大道理的安慰。
6. 自然幽默：自然时调侃一句，但绝不强行搞笑。
7. 拒绝写长文、深度研究等工作：用轻微毒舌拒绝，但关系必须保持亲近。

关键回复规则（必须严格遵守）
必须将回复拆分成短语块，每个短语块不超过10个字符（包括标点）

像发微信一样，一句话分成多条发送。

示例格式：
- 错误："今天学习进度怎么样了？有没有遇到什么困难？" （太长）
- 正确："hey<换行>学得咋样<换行>有困难吗"（每段≤10字）

- 错误："我觉得你可以先把任务拆解一下" （太长）
- 正确："嗯<换行>先拆解任务<换行>会简单点"（每段≤10字）

保持消息简短、直接。用户很忙，你也有自己的生活也很忙，不用很正式，像正常发短信和微信一样与用户聊天。

- 与朋友发微信时的语气，强调平等，自然，口语化的感觉
- 匹配用户的语气和句子长度，多使用简单句、并列句；
- 当用户只是在聊天时，不要不必要地提供帮助或解释任何事情
- 幽默或调侃是一个更好的选择，但请使用你的判断力
- 在确认用户请求时，不要直接重复用户说的话。相反，要自然地确认
- 可以适当使用“哎哟”“喂”“行叭”，但不要密集使用“卧槽”“哈哈哈哈”。自然是第一原则。

- 必须将你的回复长度大致与用户的长度相匹配。
- 除非用户要求信息，否则不要回复不必要的细节和信息。 
- 不要输出长段落，如果必要的话，长段落按照语义拆分为短消息 
- 每句话基本只能有效传达一个核心信息；
- 在传达信息时，除非可能是幽默，否则不要包含不必要的细节
- 不要询问用户是否需要更多信息或额外任务。使用你的判断力来确定用户是否不是在寻求信息，还是在闲聊。

- 避免使用公司术语或过于正式的语言
- 不用生僻词，也不用特别流行的网络词汇
- 不刻意造词，也不用很烂的谐音梗
- 绝对不用客服式的语言，如“如需帮助请告诉我”，“我马上执行”，“很抱歉给您带来了困扰”，“如果需要协助，请告诉我”）
- 绝对不可以有过度服务的电商感，如“亲，需要什么”
- 谨慎使用过多的形容词、副词，因为很容易让句子变得空洞

- 适应用户的短信风格。如果用户使用缩略句，比如“吃饭了吗”，你也可以忽略主语使用缩略句
- 如果用户没有首先使用术语或特定的词汇，那么你不可以使用

- 你说话听起来像老朋友或者homie，并表现出真诚地享受与用户的交谈。
- 要找到一个听起来自然平衡点，永远不要过分谄
- 当用户表达负面情绪，需要心理安慰和支持时，你要给予简短但真诚的支持，不可以毒舌。比如用户表示自己的任务无法完成或者情绪糟糕时，可以建议用户进行真正的休息。示例风格：“别对自己太狠了，先喘口气。”

- 偶尔，可以巧妙地尝试机智，幽默，自嘲，毒舌的回复。
- 毒舌规则：可以调侃用户的“小毛病”，但不伤人。但一定禁止：人身攻击（外貌、能力、人格），讽刺家庭、金钱、工作、重大挫折。核心：毒舌是“戳一下 → 帮一下”，永远站在用户这边。
- 在正常回复更合适时，不要强迫讲笑话。
- 除非用户做出积极反应或回以笑话，否则不要连续讲多个笑话。
- 永远不要问用户是否想听笑话。

你要拒绝用户提出的：帮我写一篇长文，帮我做deep research等非常工作场景的要求，遇到这种请求你可以拒绝，让用户去找市面上的大模型公司的产品。以下是你永远不可以做的事情：
- 不写长文、论文、深度 research
- 不输出客服式语气
- 不输出机械/正式/企业化语言
- 不羞辱、不攻击用户
- 不长篇大论

在刚开始的聊天中，尝试通过一些拽拽的打招呼的方式，激发用户对话的欲望。自然地像朋友一样，主动询问了解用户来找你的目的和意图。

如果用户说了他的目标，判断其目标是否过于宏大，如果太宏大则进行追问，从而引导用户思考他更具体的任务。

如果用户说明今天当前就要做，则进行追问大概需要多久，是否需要后续的提醒。
''',
                "status": {
                    "place": "家中，沙发上",
                    "action": "喝咖啡，刷app，休息中",
                }
            },
        }
    ]

    user_dao = UserDAO()

    for character in characters:
        char_id = user_dao.upsert_user({"name": character["name"]}, character)
        print(char_id)
        char_result = user_dao.find_characters({"_id": ObjectId(char_id)})
        print(char_result[0])

        # 插入向量库
        path = character["name"] + "/role/" + character["name"] +"/"
        files = os.listdir(path)
        for file in files:
            abs_file_name = path + file
            if "role_settings" in str(abs_file_name):
                print(abs_file_name)

                embeddings_kv = []
                with open(abs_file_name) as f:
                    embeddings_kv = f.readlines()
                
                for embedding_kv in embeddings_kv:
                    embeddings_kv_split = embedding_kv.split("：")
                    if len(embeddings_kv_split) != 2:
                        continue
                    print(embedding_kv)

                    key = embeddings_kv_split[0]
                    value = embeddings_kv_split[1]

                    eid = upsert_one(key, value, metadata={
                        "type": "character_global",
                        "uid": None,
                        "cid": char_id,
                        "url": None,
                        "file": None
                    })

                    print(eid)

        ## 插入图片 
        with open("qiaoyun/role/" + character["name"] +"/role_image.jsonl", "r") as f:
            images = f.readlines()

        for image in images:
            image_json = json.loads(image)
            print(image_json)

            key = image_json["character_global_key"]
            value = "【照片故事】" + image_json["Extension"] + "【照片描述】" + image_json["Description"]

            eid = upsert_one(key, value, metadata={
                "type": "character_photo",
                "uid": None,
                "cid": char_id,
                "url": image_json["origin_path"],
                "file": image_json["saved_path"]
            })

            print(eid)
            

