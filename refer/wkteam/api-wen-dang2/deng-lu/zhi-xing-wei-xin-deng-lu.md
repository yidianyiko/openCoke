- 执行微信登录（第三步）

# 执行微信登录（第三步）

简要描述：

- 执行登录（确认登录）

请求URL：

- http://域名地址/getIPadLoginInfo

请求方式：

- POST

请求头Headers:（别忘了传）

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| autoCheck | 是 | boolean | 是否自动验证【说明:设备类型为Mac时使用，其它情况传false】 |
| verifyCode | 否 | string | 验证码 |

[!NOTE]快速TIP：登录模块是本平台的必须步骤，若觉得过于繁琐，可省略第2步与第3步的登录步骤，直接在后台在线登录获取wid与wcId调用接口

新用户必看：

- 使用ipad取码注意：ipad新设备调用执行登录接口后，手机会显示'在新设备完成验证'，此时本接口会返回一个二维码网址，开发者需下载安盾APP扫描二维码网址，扫描人脸通过后，再次调用本接口，然后手机点击确认，则本接口返回登录结果。
- 使用mac取码注意：mac新设备调用执行登录接口后，手机会显示'在新设备完成验证'，若autoCheck字段若传true：等待10秒后，手机会自动跳转至确定页面，点击确定即可完成登录。autoCheck字段若传false：此时本接口会返回一个二维码网址，开发者需下载认证APP扫描二维码网址，扫描通过后，再次调用本接口，然后手机点击确认，则本接口返回登录结果。【PS：用户若有自己平台App，则可代码接入，无需下载App】
- 此接口为检测耗时接口，最长250S返回请求，若用户需验证滑块/未滑动成功/登录成功则会返回执行结果。登录成功后则手机顶部会显示ipad/mac在线，才可以收发消息及调用其它接口！
- 首次登录平台，24小时内会掉线1次，且72小时内不能发送朋友圈，掉线后必须传wcid调用获取二维码接口再次扫码登录即可实现3月内不掉线哦，详细规范点击这里(第1大类1小节) PS：若出现登录60S内无故掉线也看这里哦!
- 本文档所有接口，登录模块是最繁琐且需要注意的，到这里恭喜您对接已完成一大半！

返回数据：

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
{
    "wId": "0000016e-63eb-f319-0001-ed01076abf1f",
    "autoCheck":false
}

```

返回示例

```

  //mac新设备登录 触发滑块示例
 {
    "code": "200",
    "message": "处理成功",
    "data": {
        "url": "http://api.asilu.com/qrcode/?t=http://182.40.196.1:8123/s/01K54DAFN9FH7TZVFZX54CKV6Z"
    }
}

  //登录成功示例
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
    "message": "失败",
    "code": "1001",
    "data": null
}

```