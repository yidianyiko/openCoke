- 登录E云平台（第一步）

# 登录E云平台（第一步）

简要描述：

- 登录E云平台

请求URL：

- http://域名地址/member/login

请求方式：

- POST

请求头Headers：

- Content-Type：application/json

参数：

| 参数名 | 必选 | 类型 | 说明 |
| account | 是 | string | 开发者账号 |
| password | 是 | string | 开发者密码 |

[!DANGER]

- 域名地址和开发者信息:请登录后台->我的API->开通信息中查看

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| Authorization | string | 授权密钥，生成后永久有效 |
| callbackUrl | string | 消息回调地址 |
| status | string | 状态（0：正常，1：冻结，2：到期） |

请求参数示例

```
{    
   "account": "18611211111",
   "password": "123456"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "callbackUrl": null,
        "status": 0,
        "Authorization": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJwYXNzd29yZCI6ImUxMGFkYzM5NDliYTU5YWJiZTU2ZTA1N2YyMGY4ODNlYXZ1cHE9SGNTNXQwKGJvJiIsImlzcyI6InhpbmdzaGVuZyIsImFjY291bnQiOiIxMjM0NTY3ODkxMCJ9.x9bT9wDPAwGhJg7rTo0k4I0FlteKqK4AW7G9FsANgce"
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