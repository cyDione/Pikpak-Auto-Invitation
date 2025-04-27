# PikPak 自动邀请注册系统

这是一个基于原PikPak邀请注册项目的自动化扩展，使用PostgreSQL数据库管理邮箱和注册状态，实现批量自动注册PikPak账号。

## 功能特点

1. 自动从闪邮箱提取邮箱并存入数据库
2. 先使用数据库中未注册的邮箱，不足时再提取新邮箱
3. 自动完成滑块验证和邮箱验证
4. 记录注册状态和账号信息
5. 支持配置文件管理各项参数
6. Docker容器化部署
7. 支持查询闪邮箱余额和库存

## 使用方法

### 1. 修改配置文件

编辑`config.json`文件，填入以下信息：

```json
{
    "invite_code": "您的邀请码",
    "email_extraction": {
        "card_number": "闪邮箱卡号",
        "extraction_count": 10,
        "email_type": "outlook"  // 可选值: outlook 或 hotmail
    },
    "registration": {
        "batch_size": 5,
        "use_proxy": false,
        "proxy_url": "http://127.0.0.1:7890"
    },
    "database": {
        "connection_string": "postgresql://用户名:密码@主机地址:端口/数据库名"
    }
}
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
pip install psycopg2-binary
```

### 3. 初始化数据库

```bash
python db_init.py
```

### 4. 运行自动注册

```bash
python auto_register.py
```

### 5. 使用Docker部署

```bash
docker-compose -f docker-compose-auto.yml up -d
```

## 闪邮箱API

此项目使用闪邮箱官方API，包括以下功能：

1. **查询库存**：获取当前可用的outlook和hotmail邮箱数量
2. **查询余额**：获取闪邮箱卡号的剩余余额
3. **提取邮箱**：使用GET请求获取指定数量和类型的邮箱

## 文件说明

- `config.json`: 配置文件
- `db_init.py`: 数据库初始化脚本
- `email_manager.py`: 邮箱管理模块
- `pikpak_manager.py`: PikPak注册管理模块
- `auto_register.py`: 自动注册主程序
- `startup.sh`: Docker容器启动脚本

## 数据库结构

### emails 表

存储邮箱信息和注册状态

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 主键 |
| email | VARCHAR | 邮箱地址 |
| password | VARCHAR | 邮箱密码 |
| is_registered | BOOLEAN | 是否已注册 |
| register_time | TIMESTAMP | 注册时间 |
| account_info | JSONB | 账号信息 |
| created_at | TIMESTAMP | 创建时间 |

### registrations 表

存储注册记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 主键 |
| email_id | INTEGER | 关联邮箱ID |
| invite_code | VARCHAR | 使用的邀请码 |
| status | VARCHAR | 注册状态 |
| pikpak_username | VARCHAR | PikPak用户名 |
| pikpak_password | VARCHAR | PikPak密码 |
| device_id | VARCHAR | 设备ID |
| register_time | TIMESTAMP | 注册时间 |
| account_data | JSONB | 账号详细数据 |

## 注意事项

1. 请确保数据库连接正常
2. 闪邮箱API仅需要提供卡号即可，API地址已更新为官方地址
3. 支持outlook和hotmail两种邮箱类型，可在配置中选择
4. 运行时可能需要代理以绕过地区限制
5. 过于频繁的注册可能导致IP被封禁