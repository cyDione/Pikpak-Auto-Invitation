#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import logging
import os
from datetime import datetime

# 导入自定义模块
from email_manager import EmailManager
from pikpak_manager import PikpakManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("auto_register.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("PikPak-Auto")

class AutoRegister:
    def __init__(self, config_path='config.json'):
        """初始化自动注册器"""
        self.config = self._load_config(config_path)
        self.email_manager = EmailManager(config_path)
        self.pikpak_manager = PikpakManager(config_path)
        self.batch_size = self.config['registration']['batch_size']
        
        # 确保account目录存在
        os.makedirs('account', exist_ok=True)
        
        logger.info(f"自动注册器初始化完成，邀请码：{self.config['invite_code']}, 批量大小：{self.batch_size}")
    
    def _load_config(self, config_path):
        """加载配置文件"""
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def run(self):
        """运行自动注册流程"""
        logger.info("============== 开始自动注册流程 ==============")
        
        # 获取未注册邮箱
        unregistered_emails = self.email_manager.get_unregistered_emails(self.batch_size)
        logger.info(f"从数据库中获取到 {len(unregistered_emails)} 个未注册邮箱")
        
        # 如果未注册邮箱不足，尝试提取新邮箱
        if len(unregistered_emails) < self.batch_size:
            needed_count = self.batch_size - len(unregistered_emails)
            logger.info(f"未注册邮箱不足，尝试提取 {needed_count} 个新邮箱")
            
            # 检查卡余额
            balance = self.email_manager.check_email_balance()
            logger.info(f"闪邮箱卡当前余额: {balance}")
            
            if balance < needed_count:
                logger.warning(f"闪邮箱卡余额不足，需要 {needed_count} 个，但只有 {balance} 个")
            
            extracted_count = self.email_manager.extract_emails()
            logger.info(f"新提取了 {extracted_count} 个邮箱")
            
            # 再次获取未注册邮箱
            unregistered_emails = self.email_manager.get_unregistered_emails(self.batch_size)
            logger.info(f"现在有 {len(unregistered_emails)} 个未注册邮箱可用")
        
        # 依次注册每个邮箱
        successful_registrations = 0
        failed_registrations = 0
        
        logger.info("============== 开始批量注册账号 ==============")
        
        index = 0
        while index < len(unregistered_emails):
            email_data = unregistered_emails[index]
            email_id = email_data['id']
            email = email_data['email']
            password = email_data['password']
            
            logger.info(f"======== 开始注册邮箱 ({index+1}/{len(unregistered_emails)}): {email} ========")
            
            # 第一阶段：初始化注册流程，获取验证码
            logger.info("1. 初始化注册流程")
            register_init_result = self.pikpak_manager.register_account(email, password)
            
            # 检查初始化结果
            if register_init_result['status'] == 'error':
                logger.error(f"注册初始化失败: {register_init_result['message']}")
                self.email_manager.save_registration_record(
                    email_id, 
                    self.config['invite_code'], 
                    'init_failed',
                    account_data=register_init_result
                )
                failed_registrations += 1
                logger.info(f"邮箱 {email} 注册失败，已记录失败原因")
                index += 1
                continue
            
            # 需要验证码，获取验证码
            if register_init_result['status'] == 'need_verification':
                logger.info("2. 发送邮箱验证码")
                logger.info(f"验证码已发送到邮箱: {email}")
                
                # 从配置获取重试次数和间隔
                max_verification_attempts = self.config.get('email_verification', {}).get('retry_count', 10)
                retry_interval = self.config.get('email_verification', {}).get('retry_interval', 15)
                verification_code = None
                
                # 重新注册次数计数
                registration_retry_count = 0
                max_registration_retries = self.config.get('email_verification', {}).get('max_registration_retries', 3)
                abandon_after_retries = self.config.get('email_verification', {}).get('abandon_after_retries', True)
                
                while registration_retry_count < max_registration_retries:
                    # 验证码获取尝试
                    for attempt in range(1, max_verification_attempts + 1):
                        logger.info(f"尝试获取验证码 ({attempt}/{max_verification_attempts})...")
                        time.sleep(retry_interval)  # 等待配置的间隔时间再尝试获取验证码
                        
                        # 从邮箱获取验证码
                        verification_code = self.email_manager.get_verification_code(email, password)
                        
                        if verification_code:
                            logger.info(f"成功获取到验证码: {verification_code}")
                            break
                        else:
                            logger.warning(f"第 {attempt} 次尝试未获取到验证码，将继续尝试...")
                            # 如果接近最后几次尝试，适当延长等待时间
                            if attempt > max_verification_attempts * 0.7:
                                extra_wait = int(retry_interval * 0.5)
                                logger.info(f"距离最大尝试次数不远，额外等待 {extra_wait} 秒...")
                                time.sleep(extra_wait)
                    
                    # 如果成功获取到验证码，跳出重试循环
                    if verification_code:
                        break
                    
                    # 未能获取验证码，尝试重新注册
                    registration_retry_count += 1
                    if registration_retry_count < max_registration_retries:
                        logger.warning(f"无法获取验证码，尝试重新注册 (第 {registration_retry_count}/{max_registration_retries} 次)...")
                        
                        # 重新开始注册流程
                        logger.info("重新开始注册流程...")
                        register_init_result = self.pikpak_manager.register_account(email, password)
                        
                        # 检查初始化结果
                        if register_init_result['status'] == 'error':
                            logger.error(f"重新注册初始化失败: {register_init_result['message']}")
                            continue  # 继续下一次重试
                        
                        if register_init_result['status'] != 'need_verification':
                            logger.error(f"重新注册状态异常: {register_init_result['status']}")
                            continue  # 继续下一次重试
                        
                        logger.info("重新发送验证码成功，等待获取...")
                
                # 验证码重试和重新注册都失败，记录失败并继续下一个邮箱
                if not verification_code:
                    if registration_retry_count >= max_registration_retries:
                        logger.error(f"经过 {registration_retry_count} 次重新注册尝试，仍无法获取邮箱 {email} 的验证码，放弃该邮箱")
                        self.email_manager.save_registration_record(
                            email_id, 
                            self.config['invite_code'], 
                            'verification_failed',
                            device_id=register_init_result.get('device_id')
                        )
                        failed_registrations += 1
                        logger.info(f"邮箱 {email} 注册失败，无法获取验证码，已放弃")
                        
                        # 如果配置了放弃后注册新账号
                        if abandon_after_retries:
                            logger.info("尝试提取新邮箱进行注册...")
                            # 提取一个新邮箱
                            extracted_count = self.email_manager.extract_emails(1)
                            if extracted_count > 0:
                                logger.info(f"已提取 {extracted_count} 个新邮箱，将在下一个循环中使用")
                        
                        # 增加索引，处理下一个邮箱
                        index += 1
                        continue
                    else:
                        logger.error(f"经过 {max_verification_attempts} 次尝试，仍无法获取邮箱 {email} 的验证码")
                        self.email_manager.save_registration_record(
                            email_id, 
                            self.config['invite_code'], 
                            'verification_failed',
                            device_id=register_init_result.get('device_id')
                        )
                        failed_registrations += 1
                        logger.info(f"邮箱 {email} 注册失败，无法获取验证码")
                        # 增加索引，处理下一个邮箱
                        index += 1
                        continue
                
                logger.info("3. 验证码获取成功，继续注册流程")
                
                # 第二阶段：完成注册流程
                pikpak_instance = register_init_result['pikpak_instance']
                username = register_init_result['username']
                pikpak_password = register_init_result['password']
                
                # 完成注册
                logger.info("4. 使用验证码完成注册")
                complete_result = self.pikpak_manager.complete_registration(
                    pikpak_instance, 
                    username, 
                    pikpak_password, 
                    verification_code
                )
                
                if complete_result['status'] == 'error':
                    logger.error(f"完成注册失败: {complete_result['message']}")
                    self.email_manager.save_registration_record(
                        email_id, 
                        self.config['invite_code'], 
                        'register_failed',
                        device_id=register_init_result.get('device_id'),
                        account_data=complete_result
                    )
                    failed_registrations += 1
                    logger.info(f"邮箱 {email} 完成注册失败")
                    index += 1
                    continue
                
                if complete_result['status'] == 'success':
                    logger.info(f"5. 注册成功: 用户名={username}, 密码={pikpak_password}")
                    
                    # 将邮箱标记为已注册
                    self.email_manager.mark_email_as_registered(
                        email_id, 
                        account_info=complete_result.get('account_info')
                    )
                    
                    # 保存注册记录
                    complete_account_info = complete_result.get('complete_account_info', {})
                    self.email_manager.save_registration_record(
                        email_id, 
                        self.config['invite_code'], 
                        'success',
                        pikpak_username=username,
                        pikpak_password=pikpak_password,
                        device_id=register_init_result.get('device_id'),
                        account_data=complete_account_info  # 使用完整账号信息
                    )
                    
                    # 同时保存到PikPak原格式的账号文件
                    account_data = complete_account_info  # 直接使用完整账号信息
                    # 添加其他可能缺少的字段
                    if "invite_code" not in account_data:
                        account_data["invite_code"] = self.config['invite_code']
                    if "register_time" not in account_data:
                        account_data["register_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    self._save_pikpak_account(username, account_data)
                    
                    successful_registrations += 1
                    logger.info(f"邮箱 {email} 注册成功并已记录完整账号信息")
                    logger.info(f"账号信息包含: access_token, refresh_token, user_id, captcha_token等关键数据")
                    
                    # 每次注册成功后等待一段时间，避免频繁注册
                    if index < len(unregistered_emails) - 1:  # 如果不是最后一个
                        wait_time = 5
                        logger.info(f"等待 {wait_time} 秒后继续下一个注册...")
                        time.sleep(wait_time)
                    
                    # 递增索引
                    index += 1
            
            # 在验证码获取失败后重新获取邮箱的情况下，需要更新未注册邮箱列表
            if index >= len(unregistered_emails) and successful_registrations < self.batch_size:
                new_emails = self.email_manager.get_unregistered_emails(self.batch_size - successful_registrations)
                logger.info(f"获取了 {len(new_emails)} 个新的未注册邮箱")
                if new_emails:
                    # 扩展邮箱列表
                    unregistered_emails.extend(new_emails)
                    logger.info(f"更新后总共有 {len(unregistered_emails)} 个未注册邮箱")
        
        logger.info("============== 注册流程统计 ==============")
        logger.info(f"成功注册: {successful_registrations} 个账号")
        logger.info(f"失败注册: {failed_registrations} 个账号")
        logger.info(f"剩余未处理: {len(unregistered_emails) - index} 个邮箱")
        logger.info("============== 注册流程完成 ==============")
        
        return successful_registrations
    
    def _save_pikpak_account(self, username, account_data):
        """保存账号信息到PikPak原格式的文件"""
        try:
            filepath = f"account/{username}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(account_data, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存账号信息到 {filepath}")
            return True
        except Exception as e:
            logger.error(f"保存账号信息失败: {e}")
            return False

if __name__ == "__main__":
    try:
        auto_register = AutoRegister()
        auto_register.run()
    except Exception as e:
        logger.exception(f"自动注册过程中出错: {e}")
    finally:
        # 确保关闭数据库连接
        if 'auto_register' in locals() and hasattr(auto_register, 'email_manager'):
            auto_register.email_manager.close_db() 