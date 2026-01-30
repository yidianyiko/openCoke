## 启动实例
### 前置步骤
```
# python虚拟环境
source .venv/bin/activate

# docker
sudo systemctl start docker
sudo systemctl enable docker

# 数据库
docker run -d \
  --name mongodb \
  -p 27017:27017 \
  -v /home/ecs-user/luoyun/mongodb/data:/data/db \
  mongo:5.0.5

# Redis（消息队列）
docker run -d \
  --name redis \
  -p 6379:6379 \
  -v /home/ecs-user/luoyun/redis/data:/data \
  redis:7.2 redis-server --appendonly yes
```
## 启动服务
### mongo
```
docker start mongodb
```
### redis
```
docker start redis
```
### ecloud
```
bash 
```

> 使用 `./start.sh --mode pm2` 启动时，MongoDB 与 Redis 会自动检查并拉起，可跳过手动启动步骤。
