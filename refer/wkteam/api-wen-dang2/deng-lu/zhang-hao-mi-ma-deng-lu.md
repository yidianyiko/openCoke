- 账号密码登录

# 账号密码登录

请求URL：

- http://域名地址/loginByAccountAndPassword

请求方式：

- POST

请求头Headers:

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 否 | string | 登录实例标识 |
| wcId | 否 | string | 微信原始id（首次登录平台的号传""，掉线重登必须传值，否则会频繁掉线！！！） |
| proxy | 是 | int | 测试长效代理线路1:北京    2:天津     3:上海     4:重庆     5:河北6:山西     7:江苏     8:浙江     9:安徽     10:福建11:江西     12:山东     13:河南     14:湖北     15:湖南16:广东     17:海南     18:四川     19:云南     20:陕西21:黑龙江     22:辽宁     23:贵州     24:广西     25:宁夏26:青海    27:甘肃    28:西藏    29:吉林    30:内蒙 |
| account | 是 | string | 微信账号 |
| password | 是 | string | 微信密码 |
| proxyIp | 否 | string | 自定义长效代理IP+端口 |
| proxyUser | 否 | string | 自定义长效代理IP平台账号 |
| proxyPassword | 否 | string | 自定义长效代理IP平台密码 |

[!DANGER]

- 本接口仅用于无法正常登录，手机出现需要验证的时候调用本接口
- 此接口分两步调用，第一步传account,password,proxy进行账号密码登录，登录成功后会返回wId和base64图片二维码，获取二维码后用原手机进行扫码验证，验证通过后传account,password,proxy,wId再次执行此接口，执行成功后及完成登录
- 当完成以上操作时候，手机上微信此时在退出状态，您可以手机上再次登录微信，然后必须传wcid调用第二步，第三步即可正常登录【不会再次出现验证】

返回数据：

- 第一步

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |  |  |
| wId | string | 登录实例标识（本值非固定的，每次重新登录会返回新的，数据库记得实时更新wid） |  |
| base64 | string | 图片二维码 |

- 第二步

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |
| wcId | string | 微信id(唯一值） |
| nickName | string | 昵称 |
| deviceType | string | 扫码的设备类型 |
| uin | int | 识别码 |
| headUrl | string | 头像url |
| wAccount | string | 手机上显示的微信号（用户若手机改变微信号，本值会变） |
| sex | int | 性别 |
| mobilePhone | string | 绑定手机 |
| status | string | 保留字段 |

请求参数示例

```
第一步
{
  "wId":"",
  "wcId":"",
  "account": "ax**321",
  "password": "ab**56",
  "proxy": "7",
  "proxyIp": "",
  "proxyUser": "",
  "proxyPassword": ""
}
第二步
{
  "wId":"4cc5**e53f8f",
  "wcId":"",
  "account": "ax**321",
  "password": "ab**56",
  "proxy": "7",
  "proxyIp": "",
  "proxyUser": "",
  "proxyPassword": ""
}

```

成功返回示例

```
第一步
{
  "code": "1000",
  "message": "处理成功",
  "data": {
    "wId": "4cc5809a-7e4b-4c61-9dc1-a2c90ee53f8f",
    "base64": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/wAALCAG5AbkBAREA/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oACAEBAAA/AP1Tooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooorx/9qD9qDwr+yZ4A0/xf4v0/WNR0291OPSo4tEhilmErxSyhiJJYxt2wuM5Jy**RX//Z"
  }
}
第二步
{
  "code": "1000",
  "message": "处理成功",
  "data": {
    "country": "CN",
    "wAccount": "hi1212",
    "deviceType": "android",
    "city": "",
    "signature": "我的签名如风一样难以琢磨",
    "nickName": "贝塔同学",
    "sex": 2,
    "headUrl": "http://wx.qlogo.cn/mmhead/ver_1/EImpg1FWcIdhPg3zRAnkVdVdV2hic1Mib7zZ9mLTwhv5QzhNrdTCL0nKAsOgiaRrJmQwrXnBY7c1QNDo4aNc8niaicYuQpLPbJqyaJ6sKjlm5mKY/0",
    "type": 2,
    "smallHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/EImpg1FWcIdhPg3zRAnkVdVdV2hic1Mib7zZ9mLTwhv5QzhNrdTCL0nKAsOgiaRrJmQwrXnBY7c1QNDo4aNc8niaicYuQpLPbJqyaJ6sKjlm5mKY/132",
    "wcId": "wxid_ylxtxxg0p8bx22",
    "wId": "25d50610-1a82-4531-b9db-dd80c5a3c14a",
    "mobilePhone": "19822121231",
    "uin": 124723525,
    "status": 3,
    "username": "18013350963"
  }
}

```

错误返回示例

```
{
    "message": "用户名或密码错误",
    "code": "1001",
    "data": null
}

```