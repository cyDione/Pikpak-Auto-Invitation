#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import psycopg2
import requests
import re
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("auto_activate.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("auto_activate")

class AccountActivator:
    def __init__(self, config_path='config.json'):
        """初始化账号活跃器"""
        self.config = self._load_config(config_path)
        self.db_conn = None
        self.connect_db()
        self.key = None
    
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
                logger.info("已关闭旧的数据库连接")
            except Exception as e:
                logger.error(f"关闭旧数据库连接时出错: {e}")
        
        while retry_count < max_retries:
            try:
                self.db_conn = psycopg2.connect(self.config['database']['connection_string'])
                # 设置自动提交为False，确保事务控制
                self.db_conn.autocommit = False
                logger.info("数据库连接成功")
                return True
            except Exception as e:
                retry_count += 1
                logger.error(f"数据库连接失败 (尝试 {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    time.sleep(1)  # 等待1秒后重试
                else:
                    logger.error("达到最大重试次数，无法连接数据库")
                    raise
    
    def close_db(self):
        """安全关闭数据库连接"""
        if hasattr(self, 'db_conn') and self.db_conn:
            try:
                if not self.db_conn.closed:
                    self.db_conn.close()
                    logger.info("数据库连接已安全关闭")
                else:
                    logger.info("数据库连接已处于关闭状态")
            except Exception as e:
                logger.error(f"关闭数据库连接时出错: {e}")
        else:
            logger.info("没有活动的数据库连接需要关闭")
    
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
                    logger.info("数据库连接不可用，尝试重新连接...")
                    self.connect_db()
                
                cursor = self.db_conn.cursor()
                result = operation_func(cursor)
                self.db_conn.commit()
                return result
                
            except psycopg2.OperationalError as e:
                last_error = e
                retry_count += 1
                logger.error(f"{error_message} (尝试 {retry_count}/{max_retries}): {e}")
                
                try:
                    # 关闭当前连接并重新连接
                    if hasattr(self, 'db_conn') and self.db_conn and not self.db_conn.closed:
                        self.db_conn.close()
                    self.connect_db()
                except Exception as conn_error:
                    logger.error(f"重新连接数据库失败: {conn_error}")
                    time.sleep(1)
                    
            except Exception as e:
                last_error = e
                logger.error(f"{error_message}: {e}")
                
                try:
                    if hasattr(self, 'db_conn') and self.db_conn and not self.db_conn.closed:
                        self.db_conn.rollback()
                except Exception as rollback_error:
                    logger.error(f"回滚事务失败: {rollback_error}")
                    
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(1)
                
            finally:
                # 安全关闭cursor
                if cursor:
                    try:
                        cursor.close()
                    except Exception as cursor_error:
                        logger.error(f"关闭游标失败: {cursor_error}")
        
        # 如果所有尝试都失败
        logger.error(f"达到最大重试次数 ({max_retries})，操作失败")
        if last_error:
            logger.error(f"最后一次错误: {last_error}")
        return None
    
    def add_is_invalid_column(self):
        """添加is_invalid列到registrations表，用于标记失效账号"""
        def operation(cursor):
            # 检查列是否已存在
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'registrations' 
                AND column_name = 'is_invalid'
            """)
            
            if cursor.fetchone() is None:
                logger.info("正在添加is_invalid列到registrations表...")
                cursor.execute("""
                    ALTER TABLE registrations 
                    ADD COLUMN is_invalid BOOLEAN DEFAULT FALSE
                """)
                logger.info("已成功添加is_invalid列")
            else:
                logger.info("is_invalid列已存在")
            
            return True
        
        return self._execute_db_operation(
            operation, 
            error_message="添加is_invalid列失败"
        )
    
    def add_last_activated_column(self):
        """添加last_activated列到registrations表，用于记录最后激活时间"""
        def operation(cursor):
            # 检查列是否已存在
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'registrations' 
                AND column_name = 'last_activated'
            """)
            
            if cursor.fetchone() is None:
                logger.info("正在添加last_activated列到registrations表...")
                cursor.execute("""
                    ALTER TABLE registrations 
                    ADD COLUMN last_activated TIMESTAMP
                """)
                logger.info("已成功添加last_activated列")
            else:
                logger.info("last_activated列已存在")
            
            return True
        
        return self._execute_db_operation(
            operation, 
            error_message="添加last_activated列失败"
        )
    
    def get_activation_key(self):
        """从网站获取活跃密钥"""
        try:
            logger.info("正在从网站获取活跃密钥...")
            
            # 先尝试使用配置中的备用密钥
            backup_key = self.config.get('activation', {}).get('backup_key')
            if backup_key:
                logger.info(f"使用配置文件中的备用密钥: {backup_key}")
                return backup_key
            
            # 使用 Selenium 模拟 Chromium 访问
            options = Options()
            options.add_argument('--headless')  # 无头模式
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            
            driver = webdriver.Chrome(options=options)
            try:
                # 访问正确的密钥页面
                driver.get("https://kiteyuan.info/")
                
                # 等待页面加载完成
                wait = WebDriverWait(driver, 10)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                # 获取页面内容
                page_source = driver.page_source
                
                # 查找密钥元素
                match = re.search(r'\[密钥:(.*?)\]', page_source)
                if match:
                    key = match.group(1).strip()
                    logger.info(f"成功获取密钥: {key}")
                    return key
                else:
                    logger.warning("未在页面中找到密钥")
            finally:
                driver.quit()
            
            # 无法获取密钥，使用默认值
            default_key = "Se4851d85b"
            logger.warning(f"未能获取活跃密钥，使用默认值: {default_key}")
            return default_key
            
        except Exception as e:
            logger.error(f"获取密钥时出错: {e}")
            # 使用默认密钥作为后备
            default_key = "Se4851d85b"
            logger.warning(f"获取密钥出错，使用默认值: {default_key}")
            return default_key
    
    def get_registered_accounts(self, limit=100):
        """获取已注册但未标记为失效的账号"""
        def operation(cursor):
            cursor.execute("""
                SELECT r.id, r.account_data
                FROM registrations r
                WHERE r.status = 'success'
                AND (r.is_invalid IS NULL OR r.is_invalid = FALSE)
                ORDER BY r.register_time DESC
                LIMIT %s
            """, (limit,))
            
            accounts = cursor.fetchall()
            return accounts
        
        result = self._execute_db_operation(
            operation,
            error_message="获取已注册账号失败"
        )
        
        if result is not None:
            logger.info(f"获取到 {len(result)} 个已注册账号")
            return result
        else:
            logger.error("获取已注册账号失败")
            return []
    
    def mark_account_invalid(self, account_id):
        """将账号标记为失效"""
        def operation(cursor):
            cursor.execute("""
                UPDATE registrations
                SET is_invalid = TRUE
                WHERE id = %s
            """, (account_id,))
            
            logger.info(f"已将账号 ID {account_id} 标记为失效")
            return True
        
        return self._execute_db_operation(
            operation,
            error_message=f"标记账号 ID {account_id} 为失效失败"
        )
    
    def update_activation_time(self, account_id):
        """更新账号的最后激活时间"""
        def operation(cursor):
            cursor.execute("""
                UPDATE registrations
                SET last_activated = %s
                WHERE id = %s
            """, (datetime.now(), account_id))
            
            logger.info(f"已更新账号 ID {account_id} 的最后激活时间")
            return True
        
        return self._execute_db_operation(
            operation,
            error_message=f"更新账号 ID {account_id} 的激活时间失败"
        )
    
    def save_activation_result(self, account_id, result):
        """保存账号的激活结果"""
        def operation(cursor):
            cursor.execute("""
                UPDATE registrations
                SET activation_result = %s
                WHERE id = %s
            """, (json.dumps(result), account_id))
            
            logger.info(f"已保存账号 ID {account_id} 的激活结果")
            return True
        
        return self._execute_db_operation(
            operation,
            error_message=f"保存账号 ID {account_id} 的激活结果失败"
        )
    
    def activate_account(self, account_id, account_data):
        """激活单个账号"""
        if not self.key:
            self.key = self.get_activation_key()
            if not self.key:
                logger.error("无法获取激活密钥，终止激活流程")
                return False
        
        try:
            logger.info(f"开始激活账号 ID {account_id}...")
            
            # 一些账号信息可能是嵌套的JSON对象，需要确保转换成正确的JSON
            if isinstance(account_data, str):
                try:
                    account_data = json.loads(account_data)
                except json.JSONDecodeError:
                    logger.error(f"账号 ID {account_id} 的数据无法解析为JSON")
                    self.mark_account_invalid(account_id)
                    return False
            
            # 准备请求数据
            payload = {
                "info": account_data,
                "key": self.key
            }
            
            # 发送请求到活跃API
            response = requests.post(
                "https://inject.kiteyuan.info/infoInject",
                headers={
                    "Content-Type": "application/json",
                    "referer": "https://inject.kiteyuan.info/",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                },
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('code') == 200:
                    logger.info(f"账号 ID {account_id} 激活成功: {result.get('msg', '')}")
                    # 保存激活结果
                    self.save_activation_result(account_id, result)
                    # 更新激活时间
                    self.update_activation_time(account_id)
                    return True
                else:
                    logger.warning(f"账号 ID {account_id} 激活失败: {result.get('detail', '未知错误')}")
                    # 检查是否是因为账号失效导致的失败
                    error_msg = result.get('detail', '').lower()
                    if "账号过期" in error_msg or "token" in error_msg or "登录失败" in error_msg or "无效" in error_msg:
                        logger.warning(f"账号 ID {account_id} 可能已失效，标记为无效")
                        self.mark_account_invalid(account_id)
                    return False
            else:
                logger.error(f"激活请求失败: HTTP {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"激活账号 ID {account_id} 时出错: {e}")
            return False
    
    def activate_all_accounts(self):
        """激活所有已注册的账号"""
        # 先确保必要的数据库列已添加
        self.add_is_invalid_column()
        self.add_last_activated_column()
        
        # 获取激活密钥
        self.key = self.get_activation_key()
        if not self.key:
            logger.error("无法获取激活密钥，终止激活流程")
            return False
        
        # 获取所有已注册账号
        accounts = self.get_registered_accounts()
        if not accounts:
            logger.warning("没有找到已注册的账号")
            return False
        
        # 统计
        total_accounts = len(accounts)
        successful_activations = 0
        failed_activations = 0
        invalid_accounts = 0
        
        logger.info(f"开始激活 {total_accounts} 个账号...")
        
        for account_id, account_data in accounts:
            try:
                success = self.activate_account(account_id, account_data)
                if success:
                    successful_activations += 1
                else:
                    failed_activations += 1
                    # 检查是否被标记为失效
                    def check_invalid(cursor):
                        cursor.execute("""
                            SELECT is_invalid FROM registrations WHERE id = %s
                        """, (account_id,))
                        result = cursor.fetchone()
                        return result and result[0]
                    
                    is_invalid = self._execute_db_operation(check_invalid)
                    if is_invalid:
                        invalid_accounts += 1
                
                # 每个账号之间稍作等待，避免过快请求
                time.sleep(2)
            
            except Exception as e:
                logger.error(f"处理账号 ID {account_id} 时出现未知错误: {e}")
                failed_activations += 1
        
        # 打印结果统计
        logger.info("============== 激活流程统计 ==============")
        logger.info(f"总共处理: {total_accounts} 个账号")
        logger.info(f"成功激活: {successful_activations} 个账号")
        logger.info(f"激活失败: {failed_activations} 个账号")
        logger.info(f"标记失效: {invalid_accounts} 个账号")
        logger.info("=========================================")
        
        return successful_activations > 0

def main():
    """主函数"""
    activator = None
    try:
        logger.info("======== 开始PikPak账号一键活跃流程 ========")
        activator = AccountActivator()
        activator.activate_all_accounts()
        logger.info("======== PikPak账号一键活跃流程结束 ========")
    except Exception as e:
        logger.exception(f"一键活跃过程中出现未捕获的异常: {e}")
    finally:
        if activator:
            activator.close_db()

if __name__ == "__main__":
    main() 