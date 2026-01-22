# E云管家 API 文档索引

本目录包含从 https://wkteam.cn/ 拉取的 E云管家微信API文档，用于 Coke 项目开发参考。

**拉取时间**: 2026-01-22
**文档数量**: 135+ 页

## 目录结构

```
wkteam/
├── api-wen-dang2/              # API文档主目录
│   ├── deng-lu/                # 登录相关 (7个接口)
│   ├── xiao-xi-fa-song/        # 消息发送 (18个接口)
│   ├── xiao-xi-jie-shou/       # 消息接收 (9个接口)
│   ├── hao-you-cao-zuo/        # 好友操作 (15个接口)
│   ├── qun-cao-zuo/            # 群操作 (21个接口)
│   ├── peng-you-quan/          # 朋友圈 (18个接口)
│   ├── shipinhao/              # 视频号 (22个接口)
│   ├── biao-qian/              # 标签管理 (4个接口)
│   ├── shou-cang-jia/          # 收藏夹 (3个接口)
│   ├── te-shu/                 # 特殊接口 (7个接口)
│   └── wei-xin-guan-li/        # 微信管理 (3个接口)

```

## API 分类索引

### 1. 登录模块 (`deng-lu/`)
| 文件 | 功能 |
|------|------|
| deng-lu-wei-kong-ping-tai-di-yi-bu.md | 登录E云平台（第1步） |
| huo-qu-wei-xin-er-wei-ma2.md | 获取微信二维码（第2步） |
| zhi-xing-wei-xin-deng-lu.md | 执行微信登录（第3步） |
| er-ci-deng-lu.md | 弹框/二次登录 |
| initFriendList.md | 初始化通讯录 |
| queryFriendList.md | 获取通讯录列表 |
| zhang-hao-mi-ma-deng-lu.md | 账号密码登录 |

### 2. 消息发送 (`xiao-xi-fa-song/`)
| 文件 | 功能 |
|------|------|
| fa-song-wen-ben-xiao-xi.md | 发送文本消息 |
| sendFile.md | 发送文件 |
| sendFileBase64.md | 发送文件(Base64) |
| fa-song-tu-pian-xiao-xi2.md | 发送图片 |
| fa-song-shi-pin-xiao-xi.md | 发送视频 |
| fa-song-lian-jie-xiao-xi.md | 发送链接 |
| fa-song-ming-pian-xiao-xi.md | 发送名片 |
| fa-song-emoji.md | 发送表情 |
| sendApp.md | 发送App消息 |
| sendApplet.md | 发送小程序 |
| sendApplets.md | 发送小程序(新版) |
| qun-liao-at.md | 群聊@功能 |
| forwardUrl.md | 转发URL |
| revokeMsg.md | 撤回消息 |
| fa-song-yi-jing-shou-dao-de-*.md | 转发已收到的消息 |

### 3. 消息接收 (`xiao-xi-jie-shou/`)
- `shou-xiao-xi/` - 消息回调设置
  - she-zhi-http-hui-tiao-di-zhi.md - 设置HTTP回调地址
  - qu-xiao-xiao-xi-jie-shou.md - 取消消息接收
  - callback.md - 回调消息格式说明
- `xia-zai-xiao-xi-nei-rong/` - 下载消息内容
  - getMsgVideoRes.md - 下载视频
  - getMsgEmoji.md - 下载表情
  - asynGetMsgVideo.md - 异步下载视频

### 4. 好友操作 (`hao-you-cao-zuo/`)
| 文件 | 功能 |
|------|------|
| serchUser.md | 搜索用户 |
| addFriend.md | 添加好友 |
| acceptUser.md | 同意添加好友 |
| shan-chu-hao-you.md | 删除好友 |
| xiu-gai-hao-you-bei-zhu.md | 修改好友备注 |
| queryUserInfo.md | 查询用户信息 |
| checkZombie.md | 检测僵尸粉 |
| setFriendPermission.md | 设置好友权限 |
| setDisturb.md | 设置免打扰 |
| setTop.md | 设置置顶 |
| huo-qu-zi-ji-de-er-wei-ma.md | 获取自己的二维码 |
| she-zhi-ge-ren-tou-tou-xiang.md | 设置个人头像 |
| userPrivacySettings.md | 用户隐私设置 |

### 5. 群操作 (`qun-cao-zuo/`)
| 文件 | 功能 |
|------|------|
| chuang-jian-wei-xin-qun.md | 创建微信群 |
| queryGroupList.md | 获取群列表 |
| queryGroupDetail.md | 获取群详情 |
| queryGroupMemberDetail.md | 获取群成员详情 |
| updateGroupName.md | 修改群名称 |
| updateGroupRemark.md | 修改群备注 |
| setGroupAnnounct.md | 设置群公告 |
| addGroupMember.md | 添加群成员 |
| inviteGroupMember.md | 邀请群成员 |
| delGroupMember.md | 删除群成员 |
| quitGroup.md | 退出群聊 |
| queryGroupQrCode.md | 获取群二维码 |
| scanJoinRoom.md | 扫码加群 |

### 6. 朋友圈 (`peng-you-quan/`)
| 文件 | 功能 |
|------|------|
| snsSend.md | 发送文字朋友圈 |
| snsSendImage.md | 发送图片朋友圈 |
| snsSendUrl.md | 发送链接朋友圈 |
| asynSnsSendVideo.md | 异步发送视频朋友圈 |
| snsPraise.md | 朋友圈点赞 |
| snsCancelPraise.md | 取消点赞 |
| snsComment.md | 朋友圈评论 |
| snsCommentDel.md | 删除评论 |
| deleteSns.md | 删除朋友圈 |
| forwardSns.md | 转发朋友圈 |
| getCircle.md | 获取朋友圈列表 |
| getFriendCircle.md | 获取好友朋友圈 |
| getSnsObject.md | 获取朋友圈详情 |

### 7. 视频号 (`shipinhao/`)
| 文件 | 功能 |
|------|------|
| createFinder.md | 创建视频号 |
| finderPublish.md | 发布视频 |
| finderUpload.md | 上传视频 |
| finderFollow.md | 关注视频号 |
| finderIdLike.md | 视频点赞 |
| finderIdFav.md | 视频收藏 |
| finderComment.md | 视频评论 |
| finderBrowse.md | 浏览视频 |
| searchFinder.md | 搜索视频号 |
| privateSend.md | 私信发送 |
| privateSendImg.md | 私信发送图片 |

### 8. 标签管理 (`biao-qian/`)
| 文件 | 功能 |
|------|------|
| getContactLabelList.md | 获取标签列表 |
| addContactLabel.md | 添加标签 |
| delContactLabel.md | 删除标签 |
| modifyContactLabel.md | 修改标签 |

### 9. 收藏夹 (`shou-cang-jia/`)
| 文件 | 功能 |
|------|------|
| huo-qu-shou-cang-jia-lie-biao.md | 获取收藏夹列表 |
| huo-qu-shou-cang-jia-nei-rong.md | 获取收藏夹内容 |
| shan-chu-shou-cang-jia-nei-rong.md | 删除收藏夹内容 |

### 10. 特殊接口 (`te-shu/`)
| 文件 | 功能 |
|------|------|
| sendCdnVideo.md | 发送CDN视频 |
| uploadCdnImage.md | 上传CDN图片 |
| cdnDownFile.md | CDN文件下载 |
| setproxy.md | 设置代理 |
| getUserFlow.md | 获取用户流量 |
| getReqTimes.md | 获取请求次数 |
| offlineReason.md | 获取下线原因 |

### 11. 微信管理 (`wei-xin-guan-li/`)
| 文件 | 功能 |
|------|------|
| cha-xun-wei-xin-shi-fou-zai-xian.md | 查询微信是否在线 |
| duan-xian-chong-lian.md | 断线重连 |
| pi-liang-xia-xian-wei-xin-hao.md | 批量下线微信号 |

## 使用说明

1. **消息回调**: 参考 `xiao-xi-jie-shou/shou-xiao-xi/callback.md` 了解回调消息格式
2. **登录流程**: 按照 deng-lu 目录下的文档顺序执行登录
3. **API调用**: 参考 `kai-fa-zhe-gui-fan.md` 了解调用规范

## 与 Coke 项目的关系

Coke 项目使用 E云管家 作为微信接入层，主要使用以下 API:
- 消息接收回调 - 接收用户消息
- 消息发送 - 发送文本/图片/语音回复
- 好友操作 - 查询用户信息
- 群操作 - 获取群信息、成员信息
