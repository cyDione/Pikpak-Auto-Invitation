import json
import psycopg2
import time
import requests
from datetime import datetime
from psycopg2 import sql

# 导入原项目的邮箱模块
from utils.pk_email import connect_imap

class EmailManager:
    def __init__(self, config_path='config.json'):
        """初始化邮箱管理器"""
        self.config = self._load_config(config_path)
        self.db_conn = None
        self.connect_db()
    
    def _load_config(self, config_path):
        """加载配置文件"""
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def connect_db(self):
        """连接数据库"""
        max_retries = 3
        retry_count = 0
        
        # 如果当前有连接且未关闭，先尝试关闭
        if hasattr(self, 'db_conn') and self.db_conn and not self.db_conn.closed:
            try:
                self.db_conn.close()
                print("已关闭旧的数据库连接")
            except Exception as e:
                print(f"关闭旧数据库连接时出错: {e}")
        
        while retry_count < max_retries:
            try:
                self.db_conn = psycopg2.connect(self.config['database']['connection_string'])
                # 设置自动提交为False，确保事务控制
                self.db_conn.autocommit = False
                print("数据库连接成功")
                return True
            except Exception as e:
                retry_count += 1
                print(f"数据库连接失败 (尝试 {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    time.sleep(1)  # 等待1秒后重试
                else:
                    print("达到最大重试次数，无法连接数据库")
                    raise
    
    def close_db(self):
        """安全关闭数据库连接"""
        if hasattr(self, 'db_conn') and self.db_conn:
            try:
                if not self.db_conn.closed:
                    self.db_conn.close()
                    print("数据库连接已安全关闭")
                else:
                    print("数据库连接已处于关闭状态")
            except Exception as e:
                print(f"关闭数据库连接时出错: {e}")
        else:
            print("没有活动的数据库连接需要关闭")
    
    def extract_emails(self, extraction_count=None):
        """从闪邮箱卡中提取邮箱，只使用卡号"""
        card_number = self.config['email_extraction']['card_number']
        # 如果有传入参数，使用参数值；否则使用配置中的值
        count = extraction_count if extraction_count is not None else self.config['email_extraction']['extraction_count']
        email_type = self.config['email_extraction'].get('email_type', 'outlook')  # 默认使用outlook
        
        # 使用正确的官方API调用
        try:
            # 使用闪邮箱官方API，GET请求
            api_url = "https://zizhu.shanyouxiang.com/huoqu"
            params = {
                "card": card_number,
                "shuliang": count,
                "leixing": email_type  # 使用配置中的邮箱类型
            }
            
            print(f"正在调用闪邮箱API提取 {count} 个 {email_type} 邮箱...")
            response = requests.get(api_url, params=params)
            
            if response.status_code == 200:
                # 解析返回的邮箱数据
                # 文档示例返回格式可能是: "邮箱----密码"或"邮箱----密码----其他数据"
                email_text = response.text.strip()
                if email_text:
                    emails = []
                    for line in email_text.split('\n'):
                        # 使用"----"分割，但只取前两部分（邮箱和密码）
                        parts = line.split('----')
                        if len(parts) >= 2:
                            email = parts[0].strip()
                            password = parts[1].strip()
                            emails.append({"email": email, "password": password})
                    
                    if emails:
                        self._save_emails_to_db(emails)
                        print(f"成功提取 {len(emails)} 个邮箱")
                        return len(emails)
                
                print("邮箱提取失败，返回数据格式不正确或为空")
                print(f"API返回内容: {email_text}")
                return 0
            else:
                print(f"邮箱提取失败，API返回状态码: {response.status_code}")
                print(f"API返回内容: {response.text}")
                return 0
                
        except Exception as e:
            print(f"邮箱提取过程中出错: {e}")
            return 0
    
    def check_email_balance(self):
        """查询闪邮箱卡余额"""
        card_number = self.config['email_extraction']['card_number']
        
        try:
            api_url = "https://zizhu.shanyouxiang.com/yue"
            params = {"card": card_number}
            
            response = requests.get(api_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if "num" in data:
                    return data["num"]
            
            return 0
        except Exception as e:
            print(f"查询余额失败: {e}")
            return 0
    
    def check_email_inventory(self):
        """查询闪邮箱库存"""
        try:
            api_url = "https://zizhu.shanyouxiang.com/kucun"
            
            response = requests.get(api_url)
            
            if response.status_code == 200:
                return response.json()
            
            return {"hotmail": 0, "outlook": 0}
        except Exception as e:
            print(f"查询库存失败: {e}")
            return {"hotmail": 0, "outlook": 0}
    
    def _save_emails_to_db(self, emails):
        """将提取的邮箱保存到数据库"""
        def operation(cursor):
            inserted_count = 0
            for email_data in emails:
                # 示例email_data格式: {"email": "xxx@shanyouxiang.com", "password": "xxx"}
                cursor.execute(
                    """
                    INSERT INTO emails (email, password, is_registered)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    (email_data['email'], email_data['password'], False)
                )
                # 检查是否实际插入了行
                if cursor.rowcount > 0:
                    inserted_count += 1
            
            print(f"成功保存 {inserted_count} 个邮箱到数据库")
            return inserted_count
            
        result = self._execute_db_operation(
            operation,
            error_message="保存邮箱到数据库失败"
        )
        
        return result if result is not None else 0
    
    def _execute_db_operation(self, operation_func, error_message="数据库操作失败", max_retries=3):
        """
        通用方法，用于安全地执行数据库操作，并处理连接错误
        
        参数:
            operation_func: 一个函数，接受cursor作为参数，并执行数据库操作
            error_message: 操作失败时的错误消息
            max_retries: 最大重试次数
        
        返回:
            操作结果或None（如果失败）
        """
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            cursor = None
            try:
                # 检查连接是否有效
                if not hasattr(self, 'db_conn') or not self.db_conn or self.db_conn.closed:
                    print("数据库连接不可用，尝试重新连接...")
                    self.connect_db()
                
                cursor = self.db_conn.cursor()
                result = operation_func(cursor)
                self.db_conn.commit()
                return result
                
            except psycopg2.OperationalError as e:
                last_error = e
                retry_count += 1
                print(f"{error_message} (尝试 {retry_count}/{max_retries}): {e}")
                
                try:
                    # 关闭当前连接并重新连接
                    if hasattr(self, 'db_conn') and self.db_conn and not self.db_conn.closed:
                        self.db_conn.close()
                    self.connect_db()
                except Exception as conn_error:
                    print(f"重新连接数据库失败: {conn_error}")
                    time.sleep(1)
                    
            except Exception as e:
                last_error = e
                print(f"{error_message}: {e}")
                
                try:
                    if hasattr(self, 'db_conn') and self.db_conn and not self.db_conn.closed:
                        self.db_conn.rollback()
                except Exception as rollback_error:
                    print(f"回滚事务失败: {rollback_error}")
                    
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(1)
                
            finally:
                # 安全关闭cursor
                if cursor:
                    try:
                        cursor.close()
                    except Exception as cursor_error:
                        print(f"关闭游标失败: {cursor_error}")
        
        # 如果所有尝试都失败
        print(f"达到最大重试次数 ({max_retries})，操作失败")
        if last_error:
            print(f"最后一次错误: {last_error}")
        return None
        
    def get_unregistered_emails(self, limit):
        """获取指定数量的未注册邮箱"""
        def operation(cursor):
            cursor.execute(
                """
                SELECT id, email, password 
                FROM emails 
                WHERE is_registered = FALSE 
                ORDER BY created_at ASC 
                LIMIT %s
                """,
                (limit,)
            )
            
            emails = cursor.fetchall()
            return [{"id": row[0], "email": row[1], "password": row[2]} for row in emails]
            
        result = self._execute_db_operation(
            operation,
            error_message="获取未注册邮箱失败"
        )
        
        return result if result is not None else []
    
    def mark_email_as_registered(self, email_id, account_info=None):
        """将邮箱标记为已注册"""
        def operation(cursor):
            cursor.execute(
                """
                UPDATE emails 
                SET is_registered = TRUE, 
                    register_time = %s,
                    account_info = %s
                WHERE id = %s
                """,
                (datetime.now(), json.dumps(account_info) if account_info else None, email_id)
            )
            print(f"邮箱 ID {email_id} 已标记为已注册")
            return True
            
        result = self._execute_db_operation(
            operation,
            error_message=f"标记邮箱ID {email_id} 为已注册失败"
        )
        
        return result if result is not None else False
    
    def save_registration_record(self, email_id, invite_code, status, pikpak_username=None, 
                               pikpak_password=None, device_id=None, account_data=None):
        """保存注册记录，包含完整的账号信息"""
        def prepare_columns(cursor):
            # 检查可能缺失的所有列
            required_columns = ['activation_result', 'access_token', 'refresh_token', 'user_id', 'account_data']
            missing_columns = []
            
            for column in required_columns:
                cursor.execute(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'registrations' 
                    AND column_name = '{column}'
                """)
                if cursor.fetchone() is None:
                    missing_columns.append(column)
            
            # 如果有缺失的列，添加它们
            if missing_columns:
                print(f"表结构缺少以下列: {', '.join(missing_columns)}，正在添加...")
                
                # 构建ALTER TABLE语句
                alter_query = "ALTER TABLE registrations "
                add_clauses = []
                
                for column in missing_columns:
                    if column == 'activation_result' or column == 'account_data':
                        add_clauses.append(f"ADD COLUMN {column} JSONB")
                    elif column == 'access_token' or column == 'refresh_token':
                        add_clauses.append(f"ADD COLUMN {column} TEXT")
                    elif column == 'user_id':
                        add_clauses.append(f"ADD COLUMN {column} VARCHAR(255)")
                
                alter_query += ", ".join(add_clauses)
                
                cursor.execute(alter_query)
                print(f"已成功添加缺失的列: {', '.join(missing_columns)}")
            
            return missing_columns
        
        def operation(cursor):
            # 先确保所有必需的列都存在
            missing_columns = prepare_columns(cursor)
            
            # 从account_data中提取关键字段
            user_id = ""
            access_token = ""
            refresh_token = ""
            activation_result = None
            
            if account_data:
                user_id = account_data.get("user_id", "")
                access_token = account_data.get("access_token", "")
                refresh_token = account_data.get("refresh_token", "")
                # 仅当account_data中确实包含activation_result时才设置值
                if "activation_result" in account_data:
                    # 检查activation_result的类型，确保它是有效的JSON
                    activation_data = account_data.get("activation_result")
                    print(f"原始激活结果数据类型: {type(activation_data)}")
                    print(f"激活结果数据: {activation_data}")
                    
                    # 根据数据类型正确处理
                    if isinstance(activation_data, (dict, list)):
                        activation_result = json.dumps(activation_data)
                    elif isinstance(activation_data, str):
                        # 如果已经是字符串，检查是否是有效的JSON字符串
                        try:
                            # 尝试解析它，确保它是有效的JSON
                            json.loads(activation_data)
                            activation_result = activation_data
                        except json.JSONDecodeError:
                            # 如果不是有效的JSON字符串，将其作为字符串值包装成JSON
                            activation_result = json.dumps(activation_data)
                    else:
                        # 其他类型，尝试直接转换为JSON
                        activation_result = json.dumps(activation_data)
                    
                    print(f"处理后的激活结果: {activation_result}")
            
            # 定义要插入的字段
            fields = ["email_id", "invite_code", "status", "pikpak_username", 
                      "pikpak_password", "device_id"]
            values = [email_id, invite_code, status, pikpak_username, 
                      pikpak_password, device_id]
            
            # 根据数据库中实际存在的列构建插入语句
            if 'user_id' in missing_columns or 'user_id' not in missing_columns:
                fields.append("user_id")
                values.append(user_id)
            
            if 'access_token' in missing_columns or 'access_token' not in missing_columns:
                fields.append("access_token")
                values.append(access_token)
                
            if 'refresh_token' in missing_columns or 'refresh_token' not in missing_columns:
                fields.append("refresh_token")
                values.append(refresh_token)
                
            if 'account_data' in missing_columns or 'account_data' not in missing_columns:
                fields.append("account_data")
                values.append(json.dumps(account_data) if account_data else None)
                
            if 'activation_result' in missing_columns or 'activation_result' not in missing_columns:
                fields.append("activation_result")
                values.append(activation_result)
            
            # 构建并执行插入语句
            fields_str = ", ".join(fields)
            placeholders = ", ".join(["%s"] * len(values))
            
            insert_query = f"""
                INSERT INTO registrations 
                ({fields_str})
                VALUES ({placeholders})
            """
            
            cursor.execute(insert_query, values)
            print(f"已保存邮箱 ID {email_id} 的注册记录，包含完整账号信息")
            return True
        
        result = self._execute_db_operation(
            operation,
            error_message=f"保存邮箱ID {email_id} 的注册记录失败",
            max_retries=5  # 增加重试次数
        )
        
        return result if result is not None else False
    
    def get_verification_code(self, email, password):
        """获取邮箱中的验证码"""
        print(f"开始从邮箱 {email} 获取验证码...")
        
        # 定义要检查的文件夹列表，优先级从高到低
        folders_to_check = [
            'INBOX',           # 标准收件箱
            'Junk Email',      # Outlook/Hotmail垃圾邮件文件夹
            'Junk',            # 有些邮箱使用Junk作为垃圾邮件文件夹名
            'Spam'             # 有些邮箱使用Spam作为垃圾邮件文件夹名
        ]
        
        # 从配置文件获取额外的文件夹（如果有）
        extra_folders = self.config.get('email_verification', {}).get('folders', [])
        if extra_folders:
            folders_to_check.extend(extra_folders)
        
        # 依次检查每个文件夹
        for folder in folders_to_check:
            print(f"正在检查文件夹: {folder}")
            result = connect_imap(email, password, folder=folder)
            
            if result["code"] == 200:
                print(f"从 {folder} 获取验证码成功: {result['verification_code']}, 接收时间: {result.get('time', '未知')}")
                return result["verification_code"]
            elif result["code"] == 0 and "未找到验证码" in result.get("msg", ""):
                print(f"在 {folder} 中未找到验证码，继续检查下一个文件夹")
            else:
                print(f"检查 {folder} 失败: {result.get('msg', '未知错误')}")
                # 如果是认证错误，不再继续检查其他文件夹
                if result["code"] == 401:
                    print(f"邮箱认证失败，请检查邮箱 {email} 的密码是否正确")
                    return None
        
        print(f"已检查所有文件夹，未找到验证码")
        return None

# 测试代码
if __name__ == "__main__":
    email_manager = EmailManager()
    try:
        # 检查闪邮箱余额
        balance = email_manager.check_email_balance()
        print(f"当前闪邮箱卡余额: {balance}")
        
        # 检查闪邮箱库存
        inventory = email_manager.check_email_inventory()
        print(f"当前闪邮箱库存: {inventory}")
        
        # 测试获取未注册邮箱
        unregistered_emails = email_manager.get_unregistered_emails(5)
        print(f"获取到 {len(unregistered_emails)} 个未注册邮箱")
        
        # 如果未注册邮箱不足，尝试提取新邮箱
        if len(unregistered_emails) < 5:
            extracted_count = email_manager.extract_emails()
            print(f"新提取了 {extracted_count} 个邮箱")
    finally:
        email_manager.close_db() 