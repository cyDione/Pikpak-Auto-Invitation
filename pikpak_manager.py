import json
import time
import uuid
import random
import string
from datetime import datetime

# 导入原项目中的PikPak模块功能
from utils.pikpak import (
    sign_encrypt,
    captcha_image_parse,
    ramdom_version,
    random_rtc_token,
    PikPak,
    save_account_info,
    test_proxy,
)

class PikpakManager:
    def __init__(self, config_path='config.json'):
        """初始化PikPak管理器"""
        self.config = self._load_config(config_path)
        self.invite_code = self.config['invite_code']
        self.use_proxy = self.config['registration']['use_proxy']
        self.proxy_url = self.config['registration']['proxy_url']
    
    def _load_config(self, config_path):
        """加载配置文件"""
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def register_account(self, email, email_password):
        """使用邮箱注册PikPak账号"""
        try:
            print(f"开始为邮箱 {email} 注册PikPak账号...")
            
            # 初始化注册参数
            current_version = ramdom_version()
            version = current_version["v"]
            algorithms = current_version["algorithms"]
            client_id = "YNxT9w7GMdWvEOKa"
            client_secret = "dbw2OtmVEeuUvIptb1Coyg"
            package_name = "com.pikcloud.pikpak"
            device_id = str(uuid.uuid4()).replace("-", "")
            rtc_token = random_rtc_token()
            
            print(f"生成注册参数: 版本={version}, 设备ID={device_id}")
            
            # 生成随机用户名和密码
            username = f"user_{self._random_string(8)}"
            password = self._random_string(12)
            print(f"生成随机用户名: {username}, 密码: {password}")
            
            # 创建PikPak实例
            pikpak = PikPak(
                self.invite_code,
                client_id,
                device_id,
                version,
                algorithms,
                email,
                rtc_token,
                client_secret,
                package_name,
                use_proxy=self.use_proxy,
                proxy_http=self.proxy_url,
                proxy_https=self.proxy_url,
            )
            
            print(f"使用邀请码: {self.invite_code}")
            if self.use_proxy:
                print(f"使用代理: {self.proxy_url}")
            
            # 1. 初始化验证码
            print("步骤1: 初始化验证码")
            init_result = pikpak.init("POST:/v1/auth/verification")
            if (not init_result or not isinstance(init_result, dict) or "captcha_token" not in init_result):
                print(f"初始化失败，返回内容: {init_result}")
                return {
                    "status": "error",
                    "message": "初始化失败，请检查网络连接或代理设置",
                    "device_id": device_id
                }
            
            print(f"验证码初始化成功，获取到captcha_token: {pikpak.captcha_token[:10]}...")
            
            # 2. 滑块验证
            print("步骤2: 滑块验证")
            max_captcha_attempts = 5
            captcha_result = None
            
            for attempt in range(max_captcha_attempts):
                print(f"尝试滑块验证 ({attempt+1}/{max_captcha_attempts})...")
                try:
                    captcha_result = captcha_image_parse(pikpak, device_id)
                    if (captcha_result and "response_data" in captcha_result 
                        and captcha_result["response_data"].get("result") == "accept"):
                        print("滑块验证成功")
                        break
                    print(f"滑块验证失败，结果: {captcha_result.get('response_data', {}).get('result', 'unknown')}")
                    time.sleep(2)
                except Exception as e:
                    print(f"滑块验证尝试 {attempt+1} 失败: {e}")
                    time.sleep(2)
            
            if (not captcha_result or "response_data" not in captcha_result 
                or captcha_result["response_data"].get("result") != "accept"):
                print("所有滑块验证尝试均失败")
                return {
                    "status": "error",
                    "message": "滑块验证失败，请重试",
                    "device_id": device_id
                }
            
            # 3. 滑块验证加密
            try:
                print("步骤3: 滑块验证加密")
                executor_info = pikpak.executor()
                if not executor_info:
                    print("获取executor信息失败")
                    return {
                        "status": "error",
                        "message": "获取executor信息失败",
                        "device_id": device_id
                    }
                
                print("获取executor信息成功，准备加密签名")
                sign_encrypt_info = sign_encrypt(
                    executor_info,
                    pikpak.captcha_token,
                    rtc_token,
                    pikpak.use_proxy,
                    pikpak.proxies,
                )
                
                if (not sign_encrypt_info or "request_id" not in sign_encrypt_info 
                    or "sign" not in sign_encrypt_info):
                    print(f"签名加密失败，返回内容: {sign_encrypt_info}")
                    return {
                        "status": "error",
                        "message": "签名加密失败",
                        "device_id": device_id
                    }
                
                print("签名加密成功，准备上报验证结果")
                
                # 更新验证码令牌
                report_result = pikpak.report(
                    sign_encrypt_info["request_id"],
                    sign_encrypt_info["sign"],
                    captcha_result["pid"],
                    captcha_result["traceid"],
                )
                print(f"上报验证结果: {report_result}")
                
                # 4. 请求邮箱验证码
                print("步骤4: 请求邮箱验证码")
                verification_result = pikpak.verification()
                if (not verification_result or not isinstance(verification_result, dict) 
                    or "verification_id" not in verification_result):
                    print(f"请求验证码失败，返回内容: {verification_result}")
                    return {
                        "status": "error",
                        "message": "请求验证码失败",
                        "device_id": device_id
                    }
                
                print(f"验证码请求成功，verification_id: {pikpak.verification_id[:10]}...")
                
                # 5. 等待验证码发送到邮箱
                print(f"步骤5: 验证码已发送至邮箱 {email}，等待用户获取验证码")
                
                # 这里需要从email_manager获取验证码
                # 在集成脚本中处理
                return {
                    "status": "need_verification",
                    "message": "需要邮箱验证码",
                    "pikpak_instance": pikpak,
                    "device_id": device_id,
                    "username": username,
                    "password": password
                }
                
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                print(f"验证过程出错: {e}")
                print(error_trace)
                return {
                    "status": "error",
                    "message": f"验证过程出错: {str(e)}",
                    "trace": error_trace,
                    "device_id": device_id
                }
        
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"注册过程出错: {e}")
            print(error_trace)
            return {
                "status": "error",
                "message": f"注册过程出错: {str(e)}",
                "trace": error_trace
            }
    
    def complete_registration(self, pikpak_instance, username, password, verification_code):
        """完成注册过程"""
        try:
            print(f"开始完成注册: 用户名={username}, 验证码={verification_code}")
            
            # 确保验证ID已设置
            if not pikpak_instance.verification_id:
                print(f"错误: verification_id 未设置，无法验证")
                return {
                    "status": "error",
                    "message": "验证ID未设置，请重新初始化注册流程",
                }
            
            print(f"当前verification_id: {pikpak_instance.verification_id}")
            
            # 验证邮箱验证码
            print(f"步骤1: 验证邮箱验证码 (verification_code={verification_code})")
            verify_result = pikpak_instance.verify_post(verification_code)
            
            # 详细检查验证结果
            if not verify_result:
                print("验证码验证失败: 未收到响应")
                return {
                    "status": "error",
                    "message": "验证码验证失败: 服务器未响应",
                }
            elif not isinstance(verify_result, dict):
                print(f"验证码验证失败: 非预期响应格式: {verify_result}")
                return {
                    "status": "error",
                    "message": "验证码验证失败: 响应格式错误",
                    "result": str(verify_result)
                }
            elif "verification_token" not in verify_result:
                print(f"验证码验证失败: 未返回verification_token: {verify_result}")
                return {
                    "status": "error",
                    "message": "验证码验证失败: 未返回令牌",
                    "result": verify_result
                }
            elif verify_result.get("result") != "success" and "error" in verify_result:
                print(f"验证码验证失败: {verify_result.get('error', {}).get('message', '未知错误')}")
                return {
                    "status": "error",
                    "message": f"验证码验证失败: {verify_result.get('error', {}).get('message', '未知错误')}",
                    "result": verify_result
                }
            
            print(f"验证码验证成功, 获取到verification_token: {pikpak_instance.verification_token[:10]}...")
            
            # 刷新captcha_token - 这是页面端流程中的关键步骤，在verify_post和signup之间
            print("步骤2: 刷新验证令牌")
            init_result = pikpak_instance.init("POST:/v1/auth/signup")
            if not init_result or not isinstance(init_result, dict) or "captcha_token" not in init_result:
                print(f"刷新验证令牌失败，返回内容: {init_result}")
                return {
                    "status": "error",
                    "message": "刷新验证令牌失败",
                    "result": init_result
                }
                
            print(f"验证令牌刷新成功, 新captcha_token: {pikpak_instance.captcha_token[:10]}...")
            
            # 完成注册
            print("步骤3: 完成账号注册")
            signup_result = pikpak_instance.signup(username, password, verification_code)
            if not signup_result or not isinstance(signup_result, dict) or "sub" not in signup_result:
                print(f"注册失败，返回内容: {signup_result}")
                return {
                    "status": "error",
                    "message": "注册失败",
                    "result": signup_result
                }
            
            print(f"注册成功，用户ID: {signup_result.get('sub', '')}")
            
            # 保存关键信息
            timestamp = int(time.time() * 1000)
            
            # 激活邀请码
            print("步骤4: 激活邀请码")
            activation_result = pikpak_instance.activation_code()
            print(f"激活邀请码结果: {activation_result}")
            
            # 创建完整账号信息，包含激活结果
            complete_account_info = {
                "access_token": signup_result.get("access_token", ""),
                "refresh_token": signup_result.get("refresh_token", ""),
                "user_id": signup_result.get("sub", ""),
                "captcha_token": pikpak_instance.captcha_token,
                "device_id": pikpak_instance.device_id,
                "email": pikpak_instance.email,
                "name": username,
                "password": password,
                "timestamp": str(timestamp),
                "version": pikpak_instance.version,
                "activation_result": activation_result  # 明确添加激活结果
            }
            
            print("记录完整账号信息:")
            print(json.dumps(complete_account_info, indent=2))
            
            print(f"账号注册完成: 用户名={username}, 密码={password}")
            
            return {
                "status": "success",
                "message": "注册成功",
                "username": username,
                "password": password,
                "user_id": signup_result.get("sub", ""),
                "account_info": signup_result,
                "complete_account_info": complete_account_info,
                "activation_result": activation_result
            }
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"完成注册过程出错: {e}")
            print(error_trace)
            return {
                "status": "error",
                "message": f"完成注册过程出错: {str(e)}",
                "trace": error_trace
            }
    
    def _random_string(self, length):
        """生成指定长度的随机字符串"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))


# 测试代码
if __name__ == "__main__":
    pikpak_manager = PikpakManager()
    # 测试注册流程将在主脚本中进行 