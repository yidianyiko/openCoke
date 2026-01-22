- 获取评论列表

## 获取评论列表

请求URL：

- http://域名/finderCommentDetails

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| id | 是 | bigint | 视频号作品id |
| pageCode | 是 | String | 分页code，首次传空，后续传接口返回的 |
| sessionBuffer | 是 | String | 通过获取用户主页返回的sessionBuffer |
| refCommentId | 是 | String | 默认为0 |
| rootCommentId | 是 | bigint | 获取评论的回复详情时传上级评论的ID |
| nonceId | 是 | String | 视频号作品nonceId |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-x-8f03-b90e844b539f",
    "id": 14200825020179157073,
    "pageCode": "",
    "sessionBuffer": "eyJzZXNzaW9uX2lkIjoic2lkXzEzNDUxMDA3MDNfMTY5NDQ5MTA1MDk3NDcxMl8xMDkyODAzNzIwIiwiY3VyX2xpa2VfY291bnQiOjY2Mzc1MywiY3VyX2NvbW1lbnRfY291bnQiOjU1MjMsInJlY2FsbF90eXBlcyI6W10sImRlbGl2ZXJ5X3NjZW5lIjoyLCJkZWxpdmVyeV90aW1lIjoxNjk0NDkxMDUxLCJzZXRfY29uZGl0aW9uX2ZsYWciOjksInJlY2FsbF9pbmRleCI6W10sIm1lZGlhX3R5cGUiOjQsInZpZF9sZW4iOjYxLCJjcmVhdGVfdGltZSI6MTY5Mjg3MDI2MSwicmVjYWxsX2luZm8iOltdLCJzZWNyZXRlX2RhdGEiOiJCZ0FBVlwvMUhmdkVDM2s0QkdhMVJ1SXlYdGZQYVdYTzBGVVg4UHdnWHpHTVZrRnBBOHRBclJ0Q0MzVEFEZXVEUW1aOThRMUhiUVk1TitGWHFkRmYxQ1dwMXZPVThsMkhNK1E9PSIsImlkYyI6MSwiZGV2aWNlX3R5cGVfaWQiOjEzLCJkZXZpY2VfcGxhdGZvcm0iOiJpUGFkMTMsMTkiLCJmZWVkX3BvcyI6MCwiY2xpZW50X3JlcG9ydF9idWZmIjoie1wiaWZfc3BsaXRfc2NyZWVuX2lwYWRcIjowLFwiZW50ZXJTb3VyY2VJbmZvXCI6XCJ7XFxcImZpbmRlcnVzZXJuYW1lXFxcIjpcXFwiXFxcIixcXFwiZmVlZGlkXFxcIjpcXFwiXFxcIn1cIixcImV4dHJhaW5mb1wiOlwie1xcbiBcXFwicmVnY291bnRyeVxcXCIgOiBcXFwiQ05cXFwiXFxufVwiLFwic2Vzc2lvbklkXCI6XCJTcGxpdFZpZXdFbXB0eVZpZXdDb250cm9sbGVyXzE2OTQ0OTA5NjYxNTEjJDBfMTY5NDQ5MDk1MzUxNSNcIixcImp1bXBJZFwiOntcInRyYWNlaWRcIjpcIlwiLFwic291cmNlaWRcIjpcIlwifX0iLCJvYmplY3RfaWQiOjE0MjAwODI1MDIwMTc5MTU3MDczLCJmaW5kZXJfdWluIjoxMzEwNDgwNDQ5OTAxODE3OCwiZ2VvaGFzaCI6MzM3NzY5OTcyMDUyNzg3MiwicnFzdG0iOjE2OTQ0OTEwNTA1MzMsInJzc3RtIjoxNjk0NDkxMDUxMDEwLCJycWN0bSI6MTY5NDQ5MDk3NDQwOSwiZW50cmFuY2Vfc2NlbmUiOjIsImNhcmRfdHlwZSI6MywiZXhwdF9mbGFnIjoyMTY3OTA5MSwidXNlcl9tb2RlbF9mbGFnIjo4LCJjdHhfaWQiOiIyLTMtMzItMTI0N2E0YjVhOTQ4YzI4Yjg0NWZiM2Y0N2EyNTE4M2ExNjk0NDkwOTcxMjc3Iiwib2JqX2ZsYWciOjEzNDI1MDQ5NiwiZXJpbCI6W10sInBna2V5cyI6W10sIm9ial9leHRfZmxhZyI6OTg1MTJ9=",
    "refCommentId": 0,
    "rootCommentId": 0,
    "nonceId": "14967079156574588894_0_0_2_2_0"
}

```

成功返回示例

```
{
    {
    "code": "1000",
    "message": "处理成功",
    "data": {
        "videoDetails": null,
        "commentList": [
            {
                "userName": "v5_020b0a166104010000000000ae18109352a67c000000b1afa7d8728e3dd43ef4317a780e33c2718b019b67053251a030e444e04fd520e943bd3c5be4d603186002dd12e6ec5ed990dc378a101a5ee7ffe6ac04261c74d14196876054300d15f037bf39@stranger",
                "nickName": "润春15358865586",
                "content": "日本食品也是有水制造的，停止日本所以品种",
                "commentId": -4245909463265376127,
                "replyCommentId": null,
                "headUrl": "https://wx.qlogo.cn/mmhead/ver_1/oibcia4TUwfaxepzPkUVYo7ZhaXWOHvlBibG9S9aibgicQjxl9RicHFTt95tMAvdLudP5RAJN3qzcnIuhQEVdJnCxN6ny1usnj7OQhjwIQsLaDiaDU/132",
                "createTime": 1692871404,
                "likeCount": 46142,
                "ipRegion": "江苏",
                "replyContent": null,
                "replyUserName": null,
                "finderAuthorVo": {
                    "userName": "v5_020b0a166104010000000000ae18109352a67c000000b1afa7d8728e3dd43ef4317a780e33c2718b019b67053251a030e444e04fd520e943bd3c5be4d603186002dd12e6ec5ed990dc378a101a5ee7ffe6ac04261c74d14196876054300d15f037bf39@stranger",
                    "nickName": "润春15358865586",
                    "headUrl": "https://wx.qlogo.cn/mmhead/ver_1/oibcia4TUwfaxepzPkUVYo7ZhaXWOHvlBibG9S9aibgicQjxl9RicHFTt95tMAvdLudP5RAJN3qzcnIuhQEVdJnCxN6ny1usnj7OQhjwIQsLaDiaDU/132"
                }
            },
            {
                "userName": "v2_060000231003b20faec8c5e28e1fc5d6cf05eb32b077d9c01faaca62119f5312cb6c5bfacd82@finder",
                "nickName": "AAAAA科学运动森林",
                "content": "干日本，看一天了，生气",
                "commentId": -4245910022252656335,
                "replyCommentId": null,
                "headUrl": "http://wx.qlogo.cn/finderhead/Q3auHgzwzM5fYdITrDHxs73Vzf39Wp4F2eOqn8iad2x1acBfXpcia5cA/0",
                "createTime": 1692871338,
                "likeCount": 33836,
                "ipRegion": "北京",
                "replyContent": null,
                "replyUserName": null,
                "finderAuthorVo": {
                    "userName": "v2_060000231003b20faec8c5e28e1fc5d6cf05eb32b077d9c01faaca62119f5312cb6c5bfacd82@finder",
                    "nickName": "AAAAA科学运动森林",
                    "headUrl": "http://wx.qlogo.cn/finderhead/Q3auHgzwzM5fYdITrDHxs73Vzf39Wp4F2eOqn8iad2x1acBfXpcia5cA/0"
                }
            },
            {
                "userName": "v5_020b0a16610401000000000032e135bdcc5cc1000000b1afa7d8728e3dd43ef4317a780e33c2718b019b67053251a030e444e0d7dec76b5a88c65a36450566e96ec44dcbb4c2f9a3ecdb3dd724e686e1fbc809c32047545569222e4b0ffbbdf9c7d2ee@stranger",
                "nickName": "网络歌手",
                "content": "日本人在是不清醒 那就可以灭了 [菜刀][菜刀][菜刀]",
                "commentId": -4243590245011154896,
                "replyCommentId": null,
                "headUrl": "https://wx.qlogo.cn/mmhead/ver_1/Jice8MnhfFCYeYxy5JuqD8aVfzC3wy2ianFlWSmwAfG1RkIdU8TMbv7CsU5JQibM0pNQmHgvDnbWRBJJh1HHqxVahVPMP3hFhibNy8IkjxBL63U/132",
                "createTime": 1693147877,
                "likeCount": 3,
                "ipRegion": "云南",
                "replyContent": null,
                "replyUserName": null,
                "finderAuthorVo": {
                    "userName": "v5_020b0a16610401000000000032e135bdcc5cc1000000b1afa7d8728e3dd43ef4317a780e33c2718b019b67053251a030e444e0d7dec76b5a88c65a36450566e96ec44dcbb4c2f9a3ecdb3dd724e686e1fbc809c32047545569222e4b0ffbbdf9c7d2ee@stranger",
                    "nickName": "网络歌手",
                    "headUrl": "https://wx.qlogo.cn/mmhead/ver_1/Jice8MnhfFCYeYxy5JuqD8aVfzC3wy2ianFlWSmwAfG1RkIdU8TMbv7CsU5JQibM0pNQmHgvDnbWRBJJh1HHqxVahVPMP3hFhibNy8IkjxBL63U/132"
                }
            }
        ],
        "pageCode": "CrABCLCwsM79pO+NxQEYgZHkrOz634nFARixkvD6yerficUBGKqykPn5luKJxQEYkLKM+qm54InFARjAkvzI+cngicUBGM2wlLLh49+JxQEYrJKE0q/v4YnFARjWsPjhicXgicUBGNqw+KfRxeGJxQEY1LCc4KKt4InFARjTktjgwvziicUBGOmR9LrNouCJxQEYj7C4gJ+L44nFARinoOiB+oXkicUBGLOw/Imw6uKJxQE=",
        "commentCount": 5534,
        "likeCount": 100002,
        "forwardCount": 100002,
        "favCount": 100002
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

返回数据：

| 参数名 | 类型 | 说明 |
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |