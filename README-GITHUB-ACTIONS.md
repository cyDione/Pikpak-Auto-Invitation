# PikPak 自动注册与激活 GitHub Actions 配置说明

本仓库使用 GitHub Actions 自动执行 PikPak 账号的注册和激活操作。为了保护敏感信息，我们需要在 GitHub 仓库中设置一些 Secrets。

## 设置 GitHub Actions Secrets

1. 在您的仓库页面，点击 **Settings** 选项卡
2. 在左侧菜单中，选择 **Secrets and variables** 然后点击 **Actions**
3. 点击 **New repository secret** 按钮
4. 依次添加以下 secrets：

### 必需的 Secrets

| Secret 名称 | 描述 |
|------------|------|
| `PIKPAK_INVITE_CODE` | PikPak 邀请码 |
| `PIKPAK_CARD_NUMBER` | 闪邮箱卡号 |
| `DB_CONNECTION_STRING` | PostgreSQL 数据库连接字符串 |

### 可选的 Secrets

| Secret 名称 | 描述 |
|------------|------|
| `ACTIVATION_BACKUP_KEY` | PikPak 激活备用密钥（当自动获取密钥失败时使用） |

## Workflow 运行计划

1. **自动注册脚本 (`auto_register.py`)**
   - 每天 UTC 时间 18:00 运行（中国时间凌晨 2:00）
   - 可以通过手动触发运行

2. **自动激活脚本 (`auto_activate.py`)**
   - 每天 UTC 时间 20:00 运行（中国时间凌晨 4:00）
   - 可以通过手动触发运行

## 手动触发 Workflow

如果需要立即运行工作流程，而不是等待计划的时间：

1. 在仓库页面，点击 **Actions** 选项卡
2. 在左侧列表中，选择要运行的 workflow（例如 **PikPak Auto Register** 或 **PikPak Auto Activate**）
3. 点击 **Run workflow** 按钮，然后点击 **Run workflow** 确认

## 查看运行日志

1. 在仓库页面，点击 **Actions** 选项卡
2. 点击最新的工作流运行记录
3. 点击 **auto-register** 或 **auto-activate** 作业查看详细日志

## 注意事项

- 首次运行前，请确保所有必要的 Secrets 都已设置
- 如果您修改了脚本或配置文件，workflow 会使用最新的代码运行
- 数据库需要能从 GitHub Actions 的运行环境访问，请确保您的数据库允许远程连接 